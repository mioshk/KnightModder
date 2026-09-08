# -*- coding: utf-8 -*-
"""
在线 Mod 下载安装协调模块（M2 后半段内核）

职责：把「一键下载并安装」串成一条链：
  XML 解析出的 Mod 条目（含依赖闭包） -> 夸克分享下载 zip -> 下载包校验
  -> install_zip() 智能解压安装（套同名文件夹 / 合并覆盖，绝不留用户文件）。

执行模型（两阶段，解决「前置/本体只能依次下载」的痛点）：
  阶段一（并发下载）：任务闭包（前置们 + 目标本体）的 zip **同时**并行下载，
                      进度按任务分别上报，不再等一个下完才下下一个；
  阶段二（串行安装）：按「依赖在前」的任务顺序逐个 install_zip，保证游戏目录
                      与 .metadata.json 的写入跨线程互斥、依赖先就绪。

本地缓存复用：每次下载的 zip 会留在 downloads/<Mod名>/ 下不删除。重新安装 /
补装时先在本地找「sha256 与远程 XML 一致」的包（无 sha 时取唯一包），命中则
直接安装、跳过夸克下载；作者更新版本后因 sha 不再匹配会自动让位重新下载。

决策规则（与 install_manager.py 对齐）：
  - XML <Sha256> 为空            -> 无法比对，按安装规则直接覆盖合并
  - 本地 package_sha256 == 远程  -> 已是最新，跳过
  - 本地未记录 / 值不同          -> 下载并覆盖更新

依赖语义：
  - AllDependencies 为传递闭包；collect_install_plan 做 DFS 去重，缺失依赖排在
    目标之前（该顺序即阶段二的安装顺序）。下载阶段对顺序无要求，全部并行。
  - 依赖在 XML 列表中存在但没有 QLink -> 仅目标缺失 QLink 时抛错；依赖缺失链接只告警跳过。
"""
import os
import re
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Callable

from core.quark import QuarkClient, QuarkError
from core.install_manager import (calc_file_sha256, install_zip,
                                  sanitize_mod_name, verify_zip_sha256)
from core.installer import load_metadata
from utils.common import get_download_dir, get_mods_dir, load_quark_cookie


# ==================== 多任务并发控制 ====================
# 一键安装拆成两个阶段：
#   阶段一（下载）: 目标 + 缺失依赖的 zip 全部并发下载（并行度见 run_install_batch.parallel）；
#   阶段二（安装）: 按「依赖在前」的任务顺序串行 install_zip（全局安装锁互斥）。
# 同一 Mod 名（被多个并行下载目标共享的前置）由一把全局条件锁看护：
#   - 任意时刻只有第一个到达的线程真正下载该 zip（状态 downloading），其余线程
#     cond.wait() 等它完成，然后直接复用下载结果（状态 done）。
#     => 同一份依赖在整个会话只真实下载一次，互不重复，也不会并发写坏同一本地文件。
#  - 安装锁（install_zip 全段）：解压合并写 Mods 目录、整体读改写 .metadata.json
#    必须跨线程串行（元数据是整体读改写，非原子），防止竞态丢记录/损坏。
_DL_COND_GUARD = threading.Lock()
_DL_CONDS: dict = {}
_DL_STATES: dict = {}   # _name_norm(name) -> {"phase":"downloading"} | {"phase":"done","res":...}
_INSTALL_LOCK = threading.RLock()


def _dl_condition(name: str):
    """按归一化 Mod 名返回全局条件锁（同依赖的下载/复用互斥，异依赖并行不互斥）"""
    key = _name_norm(name)
    with _DL_COND_GUARD:
        cond = _DL_CONDS.setdefault(key, threading.Condition())
    return cond


# ==================== 名称 / 状态小工具 ====================

def _name_norm(name: str) -> str:
    """把 Mod 名归一化（去掉空格/横线/下划线/点并转小写），用于文件夹/依赖名比对"""
    return re.sub(r"[ \-_\.]", "", (name or "").lower())


def installed_mod_set(game_path: str) -> set:
    """
    扫描游戏 Mods 目录（含 Disabled），返回「已安装 Mod 名称的归一化集合」。
    顶层目录 / 顶层单文件 dll 均视为一个 Mod；.metadata.json 等隐藏文件忽略。
    """
    result = set()
    mods_dir = get_mods_dir(game_path)
    if not os.path.isdir(mods_dir):
        return result

    def _scan(directory: str):
        try:
            names = os.listdir(directory)
        except OSError:
            return
        for item in names:
            if item.startswith("."):
                continue
            p = os.path.join(directory, item)
            if os.path.isdir(p):
                result.add(_name_norm(item))
            elif item.lower().endswith(".dll"):
                result.add(_name_norm(os.path.splitext(item)[0]))

    _scan(mods_dir)
    _scan(os.path.join(mods_dir, "Disabled"))
    return result


def local_package_sha(game_path: str, mod_name: str) -> str:
    """读取某 Mod 上次安装来源 zip 的 sha（.metadata.json 的 package_sha256），无则空串"""
    md = load_metadata(game_path)
    target = _name_norm(mod_name)
    for key, info in md.items():
        if _name_norm(key) == target and isinstance(info, dict):
            return (info.get("package_sha256") or "").strip().upper()
    return ""


def already_installed_same(game_path: str, mod_name: str, remote_sha: str) -> str:
    """
    判断某 Mod 是否已装「同一版本」（远程 sha 已知且本地记录一致、目录真实存在）。
    语义与 install_zip 的跳过规则完全一致，用于在下载前拦截共享依赖——
    多个并行任务同时需要同一依赖时，后到者等锁后在这里直接命中，不再重复下载。

    :return: 命中时返回 Mods 下对应目录名，否则空串
    """
    remote_sha = (remote_sha or "").strip().upper()
    if not remote_sha:
        return ""
    md = load_metadata(game_path)
    target = _name_norm(mod_name)
    mods_dir = get_mods_dir(game_path)
    for key, info in md.items():
        if not (isinstance(info, dict) and _name_norm(key) == target):
            continue
        if (info.get("package_sha256") or "").strip().upper() == remote_sha:
            # 目录必须真实存在：防 metadata 残留（用户手动删了 Mod 文件夹）导致误跳过
            if os.path.isdir(os.path.join(mods_dir, key)):
                return key
    return ""


# ==================== 夸克客户端 / cookie ====================

def _normalize_level(level: str) -> str:
    return "warning" if level == "warn" else (level or "info")


def make_quark_client(log: Optional[Callable] = None,
                      progress: Optional[Callable] = None,
                      status: Optional[Callable] = None) -> QuarkClient:
    """
    依据 config.json 里保存的夸克 Cookie 构造客户端。
    Cookie 缺失或已失效时抛 QuarkError（消息已经友好化，可直接上 UI）。
    :param progress: 下载进度回调 (done_bytes, total_bytes, file_name)，透传给 QuarkClient
    :param status: 实时阶段消息回调（解析分享/转存中/取下载地址/开始下载...），用于 UI 提示当前在做什么
    """
    log = log or (lambda *a: None)
    cookie = load_quark_cookie()
    if not cookie:
        raise QuarkError("尚未配置夸克账号。请点击顶部「设置」→「登录夸克账号」后再试")

    def _status(msg: str, lvl: str):
        # 夸克登录/解析等中间状态属于实现细节，不再逐条打印到日志
        return

    client = QuarkClient(
        cookie_str=cookie,
        status_callback=_status,
        progress_callback=progress,
    )
    if not client.is_logged_in:
        raise QuarkError("夸克 Cookie 已失效，请重新在「夸克账号」中更新")
    return client


def verify_cookie(cookie: str, log: Optional[Callable] = None) -> tuple:
    """
    校验一段 Cookie 是否有效（供设置对话框即时验证）。
    :return: (是否登录成功, 昵称或失败原因)
    """
    log = log or (lambda *a: None)
    try:
        client = QuarkClient(
            cookie_str=cookie or "",
            status_callback=lambda msg, lvl: log(msg, _normalize_level(lvl)),
            timeout=20,
        )
        if not client.is_logged_in:
            return False, "Cookie 无效或已过期（需包含 __pus 与 __puus）"
        nickname = client.get_nickname()
        return True, nickname or "夸克用户"
    except Exception as e:
        return False, f"验证失败：{e}"


# ==================== 安装计划（依赖闭包） ====================

def collect_install_plan(game_path: str, mod_name: str, resolver=None,
                         force: bool = False) -> dict:
    """
    计算要安装的 Mod 列表：目标 + 所有未安装的在线依赖，依赖排在前面。

    :param force: True 时即使目标 Mod 已安装也纳入计划（用于「待更新」的更新安装）；
                  依赖是否缺失仍按游戏 Mods 目录判断，不会被强制重装。
    :return: {tasks: [mod_info, ...], missing_links: [名称], offline_deps: [名称]}
    """
    installed = installed_mod_set(game_path)
    tasks: List[dict] = []
    seen = set()
    missing_links: List[str] = []   # 在列表里但没配 QLink 的依赖
    offline_deps: List[str] = []    # 不在在线列表里的依赖（需手动处理）
    all_mods = getattr(resolver, "mod_data_by_name", {}) if resolver else {}
    target_key = _name_norm(mod_name)

    def _dfs(name: str):
        if name in seen:
            return
        # 强制（更新）时放过目标 Mod 本身；其余已安装的一律跳过
        if _name_norm(name) in installed and not (force and _name_norm(name) == target_key):
            return
        seen.add(name)
        info = all_mods.get(name)
        if not info:
            offline_deps.append(name)
            return
        for dep in (info.get("dependencies") or []):
            _dfs(dep)
        if name not in {t["name"] for t in tasks}:
            tasks.append(info)

    _dfs(mod_name)

    # 无法自动安装的依赖：仅保留真正缺失（未安装）的
    missing_links = [n for n in offline_deps if _name_norm(n) not in installed]
    # 列表里有条目但没配链接的缺失依赖
    no_link = []
    for info in tasks:
        if not info.get("link") and not (info.get("batch_links") or []):
            no_link.append(info["name"])
    return {
        "tasks": tasks,
        "offline_deps": missing_links,
        "no_link": no_link,
    }


# ==================== 单个 Mod 下载并安装 ====================

def _pick_package(paths: List[str], mod_info: dict) -> str:
    """从下载产物里精确定位安装包：优先 zip；分享里没有 zip 时接受唯一的裸 dll"""
    zips = [p for p in paths if str(p).lower().endswith(".zip")]
    if not zips:
        dlls = [p for p in paths if str(p).lower().endswith(".dll")]
        if len(dlls) == 1:
            return dlls[0]
        if len(dlls) > 1:
            names = "、".join(os.path.basename(p) for p in dlls)
            raise QuarkError(f"分享里包含多个 dll（{names}），请在 XML 的 <DownloadName> 指定要安装的文件")
        raise QuarkError("下载内容中没有找到 zip 安装包")

    download_name = (mod_info.get("download_name") or "").strip()
    if download_name:
        for p in zips:
            if os.path.basename(p).lower() == download_name.lower():
                return p
        raise QuarkError(f"未找到指定的安装包：{download_name}")

    if len(zips) == 1:
        return zips[0]

    # 多个 zip：优先挑文件名与 Mod 名一致的
    base = _name_norm(mod_info.get("name") or "")
    for p in zips:
        stem = _name_norm(os.path.splitext(os.path.basename(p))[0])
        if base and stem == base:
            return p
    names = "、".join(os.path.basename(p) for p in zips)
    raise QuarkError(f"分享里包含多个 zip（{names}），请在 XML 的 <DownloadName> 指定要安装的安装包")


def _pick_cached_zip(mod_info: dict) -> Optional[str]:
    """
    在本地 downloads/ 里找一份可复用的安装包（zip 或裸 dll），找不到返回 None。

    目录布局：下载内容直接平铺在 downloads/ 下（不再按 Mod 建子文件夹）；
    向下递归扫描是为了兼容旧版本按 downloads/<Mod名>/ 缓存的存量文件。

    命中规则（保证不会装错版本）：
      - 远程 sha256 已知：只要某文件 sha 与远程一致即可复用（完整性最强，
        也能在作者更新版本后自动让位、重新下载新包）；
      - 远程无 sha：必须文件名能对上——XML <DownloadName> 同名，
        或与「Mod 名.zip / Mod 名.dll」同名；对不上宁可重新下载。
        （平铺后目录里是所有 Mod 的文件，“目录内唯一”不再能作为命中依据）
    """
    name = (mod_info.get("name") or "").strip()
    if not name:
        return None
    dl_dir = get_download_dir()
    if not os.path.isdir(dl_dir):
        return None
    packages = []
    for root, _dirs, files in os.walk(dl_dir):
        for f in files:
            if f.lower().endswith((".zip", ".dll")):
                packages.append(os.path.join(root, f))
    if not packages:
        return None

    remote_sha = (mod_info.get("sha256") or "").strip().upper()
    if remote_sha:
        for p in packages:
            if calc_file_sha256(p) == remote_sha:
                return p
        return None

    wanted = {(mod_info.get("download_name") or "").strip().lower()}
    sanitized = sanitize_mod_name(name).lower()
    collapsed = re.sub(r"[\s\-_]+", "", sanitized)
    for base in {sanitized, collapsed}:
        if base:
            wanted.add(base + ".zip")
            wanted.add(base + ".dll")
    wanted.discard("")
    for p in packages:
        if os.path.basename(p).lower() in wanted:
            return p
    return None


def purge_local_packages(mod_name: str) -> List[str]:
    """
    删除 downloads/ 里属于该 Mod 的旧安装包（zip / dll，以及残留的 .part），
    返回被删除的文件名列表。

    用于「更新安装」场景：保证 downloads 里只保留最新下载的那一份，
    不会既留旧包又把旧包装回去。匹配规则（避免误伤同前缀的其它 Mod）：
      - 文件名去掉空格/连字符/下划线后与 Mod 名完全相同；或
      - 以 Mod 名开头，且紧随其后的字符不是字母/数字（如 -v1.2、(1)、.zip）
    """
    dl_dir = get_download_dir()
    if not os.path.isdir(dl_dir):
        return []
    key = re.sub(r"[\s\-_]+", "", sanitize_mod_name(mod_name).lower())
    if not key:
        return []
    removed: List[str] = []
    for root, _dirs, files in os.walk(dl_dir):
        for f in files:
            low = f.lower()
            if not low.endswith((".zip", ".dll", ".part")):
                continue
            stem = os.path.splitext(f)[0]
            collapsed = re.sub(r"[\s\-_]+", "", stem).lower()
            hit = False
            if collapsed == key:
                hit = True
            elif low.startswith(key):
                tail = low[len(key):]
                hit = (not tail) or (not tail[0].isalnum())
            if not hit:
                continue
            try:
                os.remove(os.path.join(root, f))
                removed.append(f)
            except OSError:
                pass
    return removed


def find_local_package(mod_info: dict) -> Optional[str]:
    """
    在 downloads/ 里找一份可用的本地安装包（zip 或裸 dll），找不到返回 None。
    仅查缓存目录（不读 .metadata.json、不做安装状态判断），用于列表行
    「本地已有安装包」标记等轻量预判。
    """
    cached = _pick_cached_zip(mod_info)
    if cached and zipfile.is_zipfile(cached):
        return cached
    return None


def local_ready_result(game_path: str, mod_info: dict) -> Optional[dict]:
    """
    预判某个任务能否「完全不触网」直接进入安装：
      1) 游戏 Mods 目录里已装同版本（package_sha 与远程一致且文件夹真实存在）-> skip；
      2) downloads/<Mod名>/ 里有可用本地安装包 zip（sha 一致 / 无 sha 唯一包）-> zip。
    命中返回安装阶段可直接消费的 {"zip": 路径} 或 {"skip": 目录}，否则返回 None
    （表示必须走夸克下载）。
    """
    remote_sha = (mod_info.get("sha256") or "").strip().upper()
    existing = already_installed_same(game_path, mod_info["name"], remote_sha)
    if existing:
        return {"skip": os.path.join(get_mods_dir(game_path), existing)}
    cached = find_local_package(mod_info)
    if cached:
        return {"zip": cached}
    return None


def _download_and_verify(cookie: str, game_path: str, mod_info: dict,
                         log: Optional[Callable] = None,
                         task_progress: Optional[Callable] = None,
                         on_status: Optional[Callable] = None) -> dict:
    """阶段一的真实下载动作（仅在成为该依赖的唯一下载者后被调用）：
    独立 QuarkClient（verify_login=False，登录态已由批入口验证过一次），
    使各并发下载拥有互不干扰的进度/阶段回调；
    先做「已装同版本」预检（并行中的其它批可能刚装好），命中则不再下载。
    :return: {"zip": 本地安装包路径} 或 {"skip": 已装同名 Mod 目录}
    """
    log = log or (lambda *a: None)
    name = mod_info["name"]

    remote_sha = (mod_info.get("sha256") or "").strip().upper()
    existing_dir = already_installed_same(game_path, name, remote_sha)
    if existing_dir:
        log(f"已安装相同版本（sha256 一致），跳过下载：{name}", "success")
        return {"skip": os.path.join(get_mods_dir(game_path), existing_dir)}

    # 本地缓存复用：之前下载过的安装包就平铺在 downloads/ 里，卸载/重装
    # 直接拿它装，不必再碰夸克。sha 命中即保证与远程同版本、且文件完好。
    cached = _pick_cached_zip(mod_info)
    if cached:
        looks_valid = zipfile.is_zipfile(cached) or cached.lower().endswith(".dll")
        if not remote_sha and not looks_valid:
            log(f"本地缓存包已损坏（{os.path.basename(cached)}），改为重新下载：{name}", "warn")
        else:
            log(f"✔ 命中本地下载缓存，无需重新下载：{name}", "success")
            return {"zip": cached}

    # 每路下载绑定独立进度/阶段回调：进度能精确归属到对应的任务行
    def _status(msg: str, lvl: str):
        # 夸克解析/转存/下载等中间状态属于实现细节，不再逐条打印（结果行已足够）
        return

    client = QuarkClient(
        cookie_str=cookie, verify_login=False,
        progress_callback=((lambda d, t, _fn: task_progress(name, d, t))
                           if task_progress else None),
        status_callback=_status,
    )

    # 候选下载链接：主 QLink 在前，QLinks 里的其它分享兜底（作者常给多个镜像）。
    # 单一链接可能在分享失效/内容不含 zip 时解析失败，需逐条尝试，最后一条仍失败才放弃。
    link_candidates = []
    if (mod_info.get("link") or "").strip():
        link_candidates.append(mod_info["link"].strip())
    for _l in (mod_info.get("batch_links") or []):
        if _l and _l.strip() and _l.strip() not in link_candidates:
            link_candidates.append(_l.strip())
    if not link_candidates:
        raise QuarkError(f"{name} 未配置下载链接（XML 缺少 <QLink>），请手动复制下载地址")

    # 下载内容直接平铺在 downloads/ 根目录（zip 或裸 dll），不再按 Mod 套子文件夹；
    # 「套同名文件夹」只发生在安装阶段写入 Mods 时
    dest_dir = get_download_dir()
    os.makedirs(dest_dir, exist_ok=True)

    def _fetch(force_transfer: bool):
        """按候选链接顺序尝试下载一次，返回安装包路径"""
        last = ""
        for link in link_candidates:
            try:
                _, downloaded = client.download_share(
                    url=link,
                    local_dir=dest_dir,
                    # 传入 Mod 名：用于判断云端同名文件是否属于本 Mod（决定能否复用）
                    remote_dir_name=sanitize_mod_name(name),
                    select_file=lambda f: str(f.get("file_name") or "").lower()
                    .endswith((".zip", ".dll")),
                    return_files=True,
                    force_transfer=force_transfer,
                )
                return _pick_package(downloaded, mod_info)
            except QuarkError as e:
                last = str(e)
                log(f"⚠️ 链接 {link} 不可用，尝试下一个：{last}", "warn")
        raise QuarkError(
            f"{name} 所有分享链接均不可用（{last}），请检查分享是否失效或到官网获取新地址")

    package_path = _fetch(force_transfer=False)

    # sha 校验（XML <Sha256>）：不一致说明拿到的是旧包/损坏包。
    # 常见原因是云端复用了"同名同大小"的旧文件，因此强制重新转存再下一次自愈。
    if remote_sha and not verify_zip_sha256(package_path, remote_sha):
        log(f"⚠️ {name} 下载包 sha 与 XML 不一致，强制重新转存后重试一次", "warn")
        try:
            os.remove(package_path)
        except OSError:
            pass
        package_path = _fetch(force_transfer=True)
    if package_path is None:
        raise QuarkError(f"{name} 所有分享链接均不可用，请检查分享是否失效或到官网获取新地址")

    if remote_sha:
        if not verify_zip_sha256(package_path, remote_sha):
            raise QuarkError(f"{name} 下载包校验失败（sha256 与发布数据不一致），已中止安装，请勿强行使用")
    return {"zip": package_path}


def _download_task(cookie: str, game_path: str, mod_info: dict,
                   log: Optional[Callable] = None,
                   task_progress: Optional[Callable] = None,
                   on_status: Optional[Callable] = None) -> dict:
    """同名依赖的「下载/复用」入口：同一 Mod（跨目标、跨并行线程共享）只会被
    第一个到达的线程真实下载（state=downloading），其余线程在条件锁上等待，
    完成后直接复用结果（state=done）。失败则清空状态、唤醒等待者自行重试。
    :return: {"zip": 路径} 或 {"skip": 已装目录}
    """
    name = mod_info["name"]
    key = _name_norm(name)
    cond = _dl_condition(name)
    while True:
        with cond:
            st = _DL_STATES.get(key)
            if st is None:
                _DL_STATES[key] = {"phase": "downloading"}
                try:
                    res = _download_and_verify(
                        cookie, game_path, mod_info, log=log,
                        task_progress=task_progress, on_status=on_status)
                    _DL_STATES[key] = {"phase": "done", "res": res}
                    cond.notify_all()
                    return res
                except BaseException:
                    _DL_STATES.pop(key, None)
                    cond.notify_all()
                    raise
            if st["phase"] == "done":
                return st["res"]       # 复用他人刚下载好的同一份 zip
            cond.wait()


# ==================== 批量执行入口 ====================

def run_install_batch(game_path: str, tasks: List[dict],
                      log: Optional[Callable] = None,
                      task_progress: Optional[Callable] = None,
                      on_task_started: Optional[Callable[[str], None]] = None,
                      on_installing: Optional[Callable[[str], None]] = None,
                      task_done: Optional[Callable[[str, str], None]] = None,
                      on_status: Optional[Callable[[str], None]] = None,
                      parallel: int = 8) -> dict:
    """
    两阶段执行一个任务列表（依赖在前，但下载全并行）：
      阶段一：tasks 里所有待装 zip 并发下载（同名共享依赖全局只下一次）；
      阶段二：按任务顺序（依赖先于目标）串行 install_zip。

    :param task_progress: 下载进度回调 (Mod名, done_bytes, total_bytes)
    :param on_task_started: 任务开始下载/进入队列回调 Mod 名（供 UI 标记行）
    :param on_installing: 单个 Mod 进入校验/安装前回调 Mod 名
    :param task_done: 单个 Mod 完成回调 (Mod名, installed/updated/skipped)
    :param on_status: 实时阶段消息回调（解析/转存/取地址/开始下载...）
    :param parallel: 同时下载的最大任务数（默认 8，可在「设置」里调整；
                     超过同批次任务数时自动收敛）
    :return: {statuses: {Mod名: installed/updated/skipped}}
    :raises QuarkError: 登录/链接/校验错误；任务级错误包装「任务名：原因」后抛出。
    """
    log = log or (lambda *a: None)

    # 每批开始必须清空全局下载状态：_DL_STATES 里缓存着上一批的 zip 路径，
    # 用户随时可能删掉 downloads 里的文件；跨批复用旧路径会导致
    # 「安装包不存在」却永不重新下载。去重只需在“本批并行线程”内生效。
    _DL_STATES.clear()

    if not tasks:
        return {"statuses": {}}

    # 本地预判：已装同版本 / downloads 缓存 zip 命中的任务不触网，
    # 直接从本地结果进入安装；只有真需要下载的任务才开线程池与夸克登录。
    results: dict = {}
    need_net: List[dict] = []
    for info in tasks:
        res = local_ready_result(game_path, info)
        if res is None:
            need_net.append(info)
        else:
            results[info["name"]] = res
            if "zip" in res:
                log(f"✔ 命中本地下载缓存，无需重新下载：{info['name']}", "success")

    # ---------- 阶段一（仅确有下载）：并发下载缺失的 zip ----------
    if need_net:
        # 登录态只探测一次（失败抛友好错误），各并发下载线程复用 cookie 字符串
        make_quark_client(log=log, status=on_status)
        cookie = load_quark_cookie()
        workers = max(1, min(len(need_net), parallel if parallel and parallel > 0 else 8))
        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="km-dl")
        futures = {}
        try:
            for info in need_net:
                name = info["name"]
                if on_task_started:
                    on_task_started(name)
                futures[pool.submit(
                    _download_task, cookie, game_path, info, log,
                    task_progress, on_status)] = info
            first_err = None
            for fut in as_completed(futures):
                info = futures[fut]
                try:
                    results[info["name"]] = fut.result()
                except BaseException as e:  # noqa: BLE001
                    # 记录首个错误；其余并行下载仍等其自然收尾（线程无法安全中断，
                    # 且其它批正等待共享结果），收尾后再统一中止本批安装。
                    if first_err is None:
                        first_err = e
            if first_err is not None:
                log(f"❌ 下载中止：{first_err}", "error")
                raise type(first_err)(f"{first_err}") from first_err
        finally:
            pool.shutdown(wait=True)

    # ---------- 阶段二：按依赖在前的顺序串行安装 ----------
    statuses: dict = {}
    for info in tasks:
        name = info["name"]
        res = results.get(name)
        if not res:
            continue
        if "skip" in res:
            statuses[name] = "skipped"
            if task_done:
                task_done(name, "skipped")
            continue
        remote_sha = (info.get("sha256") or "").strip().upper()
        try:
            if on_installing:
                on_installing(name)
            with _INSTALL_LOCK:
                r = install_zip(game_path, res["zip"], mod_name=name,
                                remote_sha256=remote_sha, log=log)
            statuses[name] = r.get("status", "installed")
            if task_done:
                task_done(name, statuses[name])
        except Exception as e:  # noqa: BLE001
            log(f"❌ {name} 处理失败：{e}", "error")
            raise type(e)(f"{name}：{e}") from e

    return {"statuses": statuses}
