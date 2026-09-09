# -*- coding: utf-8 -*-
"""
在线 Mod 安装内核（M2）

职责：把从夸克网盘下载下来的 Mod 安装包（zip）安全地安装/更新进
Hollow Knight 的 Mods 目录，同时遵守"绝不删除用户文件"的硬约束。

安装语义（与 ModLoader 的目录规则对齐）：
  1. Hollow Knight 的 ModLoader 按 Mods/ 下的目录加载 Mod，每个 Mod 的
     dll 应位于自己的文件夹中。
  2. 若 zip 顶层只有一个目录（最常见，例如 Custom Knight/），直接把该
     目录整体并入 Mods/，保留其原目录名。
  3. 若 zip 顶层是散文件（散装单 dll / 资源），则自动套一个以 Mod 名
     命名的文件夹再放入 Mods/，避免 dll 裸放导致 ModLoader 无法识别。

更新语义（关键安全约束）：
  更新一律采用"逐文件合并覆盖"：新包里的文件逐个覆盖进目标目录；
  目标目录中 zip 里不存在的文件（例如用户自放在皮肤 Mod 里的 png）
  一律保留，全程绝不使用 shutil.rmtree 清空再解压。

Sha256 决策表（remote_sha256 来自 ModLinksCN.xml 的 <Sha256>，语义为
"下载安装包 zip 的 sha256"）：
  - remote_sha256 为空           -> 无法判断，直接覆盖合并
  - 本地 package_sha256 == 远程  -> 已安装同一版本，跳过
  - 本地未记录 / 值不同          -> 覆盖合并，并把 package_sha256 更新为远程值

元数据字段约定（.metadata.json，每个 Mod 一条）：
  - sha256           : Mod 主 dll 的哈希，由现有扫描功能维护（本地装包用）
  - package_sha256   : 安装来源 zip 的哈希，由本模块维护（在线更新判断用）
  - version/install_time : 沿用现有字段
"""
import os
import re
import shutil
import tempfile
import hashlib
import zipfile
from typing import List, Optional, Tuple, Callable

from utils.common import get_mods_dir
from core.installer import load_metadata, save_metadata


# ==================== 基础工具 ====================

def calc_file_sha256(file_path: str) -> Optional[str]:
    """计算文件的 SHA256（大写十六进制）。失败返回 None"""
    try:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(1 << 16), b""):
                h.update(block)
        return h.hexdigest().upper()
    except Exception:
        return None


def _norm_sha(value) -> str:
    """把任意来源的 sha 统一成大写无空白格式，空值返回空串"""
    return (value or "").strip().upper()


def sanitize_mod_name(name: str) -> str:
    """清理目录名中的 Windows 非法字符，空结果兜底为 Mod"""
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]', "", name or "").strip()
    return cleaned or "Mod"


# ==================== zip 结构分析 ====================

def analyze_zip(zip_path: str) -> Tuple[List[str], List[str]]:
    """
    分析 zip 顶层结构（忽略 __MACOSX 等打包垃圾）。

    :return: (top_dirs, top_files)
        top_dirs : zip 内顶层目录名（去重），如 ["Custom Knight"]
        top_files: zip 内顶层散文件名，如 ["MyMod.dll", "说明.txt"]
    """
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
    names = [n for n in names if not n.startswith("__MACOSX/")]
    top_dirs: List[str] = []
    top_files: List[str] = []
    for n in names:
        if "/" in n:
            d = n.split("/", 1)[0]
            if d not in top_dirs:
                top_dirs.append(d)
        else:
            top_files.append(n)
    return top_dirs, top_files


def plan_install(zip_path: str, mod_name: str) -> Tuple[Optional[str], str]:
    """
    决定安装源与安装目标目录名。

    :return: (source_top_dir, dest_dir_name)
        source_top_dir: zip 内唯一顶层目录名；若 zip 顶层是散装结构则为 None，
                        此时安装源是整个解压目录
        dest_dir_name : Mods 下应使用的目录名（始终以 XML <Name> 为准，
                        不再盲信 zip 内部目录名——很多 Mod 打包时保留了基座
                        如 ItemChanger/ 的原始目录结构）
    """
    top_dirs, top_files = analyze_zip(zip_path)
    if len(top_dirs) == 1 and not top_files:
        # 单一顶层目录且无散文件 -> 源指向该目录，但目标文件夹用 XML 名称
        return top_dirs[0], sanitize_mod_name(mod_name)
    # 散装/多顶层条目 -> 套一个以 Mod 名命名的文件夹
    return None, sanitize_mod_name(mod_name)


# ==================== 合并复制（绝不删用户文件） ====================

def merge_tree(src_dir: str, dst_dir: str) -> None:
    """
    把 src_dir 的内容逐文件合并进 dst_dir。

    规则：已存在同路径文件 -> 用新文件覆盖；src 里新出现的文件 -> 加入；
    dst 中 src 没有的文件 -> 保留。绝不会删除 dst 下的任何文件。
    """
    os.makedirs(dst_dir, exist_ok=True)
    for entry in os.listdir(src_dir):
        # macOS 打 zip 时会在包里塞一个 __MACOSX 垃圾目录，绝不能装进游戏 Mods
        if entry == "__MACOSX":
            continue
        s = os.path.join(src_dir, entry)
        d = os.path.join(dst_dir, entry)
        if os.path.isdir(s):
            merge_tree(s, d)
        else:
            if os.path.isdir(d):
                # 极端情形：旧的是文件夹、新的同名是文件，需整体替换这个节点
                shutil.rmtree(d, ignore_errors=True)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)


# ==================== 元数据读取 ====================

def get_package_sha(game_path: str, mod_key: str) -> str:
    """读取某 Mod 上次安装来源 zip 的 sha（package_sha256），无则返回空串"""
    md = load_metadata(game_path)
    info = md.get(mod_key) or {}
    return _norm_sha(info.get("package_sha256"))


def record_package_sha(game_path: str, mod_key: str, sha: str) -> None:
    """记录某 Mod 安装来源 zip 的 sha（package_sha256）"""
    sha = _norm_sha(sha)
    md = load_metadata(game_path)
    entry = md.setdefault(mod_key, {})
    if sha:
        entry["package_sha256"] = sha
    else:
        entry.pop("package_sha256", None)
    save_metadata(game_path, md)


# ==================== 安装主流程 ====================

def install_zip(game_path: str, zip_path: str,
                mod_name: str = "", remote_sha256: str = "",
                log: Optional[Callable] = None) -> dict:
    """
    把一份 Mod 安装包 zip 安装/更新进游戏 Mods 目录。

    :param game_path: 游戏根目录（含 hollow_knight_Data）
    :param zip_path:  本地已下载好的 zip 安装包路径
    :param mod_name:  Mod 名称（来自 XML <Name>）。散装 zip 套文件夹时使用；
                      为 None 时以 zip 文件名兜底
    :param remote_sha256: 远程包 sha（XML <Sha256>）；空则无条件覆盖合并
    :param log:       日志回调 log(message, level)
    :return: 结果字典 {status, name, dir_path}
        status: "installed" 全新安装 / "updated" 覆盖更新 / "skipped" 已是最新
    """
    log = log or (lambda *a: None)

    if not os.path.isfile(zip_path):
        raise FileNotFoundError(f"安装包不存在：{zip_path}")
    if not zipfile.is_zipfile(zip_path):
        # 裸 dll 单文件 Mod：直接放进 Mods/<Mod名>/ 并记录 sha
        if str(zip_path).lower().endswith(".dll"):
            return _install_single_dll(game_path, zip_path, mod_name,
                                       remote_sha256, log)
        raise RuntimeError(f"不是有效的 zip 安装包：{os.path.basename(zip_path)}")

    # 文件名兜底作为 Mod 名
    mod_name = mod_name or os.path.splitext(os.path.basename(zip_path))[0]

    mods_dir = get_mods_dir(game_path)
    os.makedirs(mods_dir, exist_ok=True)

    # 1. 结构分析 -> 确定安装目标目录名
    source_top, dest_name = plan_install(zip_path, mod_name)
    target_dir = os.path.join(mods_dir, dest_name)

    # 2. sha 决策：远程已知且本地一致 -> 跳过
    #    注意：必须同时确认目标文件夹真实存在。用户手动删除 Mod 文件夹后，
    #    .metadata.json 可能残留 package_sha 记录，若不检查文件夹会导致重装被误跳过。
    remote_sha = _norm_sha(remote_sha256)
    if remote_sha and os.path.isdir(target_dir) and get_package_sha(game_path, dest_name) == remote_sha:
        log(f"已安装相同版本（sha256 一致），跳过：{dest_name}", "success")
        return {"status": "skipped", "name": dest_name, "dir_path": target_dir}

    # 3. 解压到临时目录 -> 合并进 Mods（绝不删除用户已有文件）
    existed = os.path.isdir(target_dir)
    staging = tempfile.mkdtemp(prefix="km_install_")
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(staging)
        source_root = staging
        if source_top:
            source_root = os.path.join(staging, source_top)
            if not os.path.isdir(source_root):
                raise RuntimeError(f"安装包内缺少目录：{source_top}")
        log(("更新" if existed else "安装") + f" Mod：{dest_name}", "info")
        merge_tree(source_root, target_dir)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    # 4. 记录安装来源包的 sha（供下次判断"已是最新"）
    record_package_sha(game_path, dest_name, remote_sha)

    status = "updated" if existed else "installed"
    return {"status": status, "name": dest_name, "dir_path": target_dir}


# ==================== 便捷工具（供下载队列/UI 使用） ====================

def _install_single_dll(game_path: str, dll_path: str, mod_name: str = "",
                        remote_sha256: str = "",
                        log: Optional[Callable] = None) -> dict:
    """
    安装"裸 dll"单文件 Mod：复制到 Mods/<Mod名>/<原文件名> 并记录来源 sha。

    与 zip 安装一致的行为：sha 一致且目标目录存在 -> skipped；否则覆盖复制。
    """
    log = log or (lambda *a: None)
    mod_name = mod_name or os.path.splitext(os.path.basename(dll_path))[0]
    target_dir = os.path.join(get_mods_dir(game_path), mod_name)

    remote_sha = _norm_sha(remote_sha256)
    if remote_sha and os.path.isdir(target_dir) and get_package_sha(game_path, mod_name) == remote_sha:
        log(f"已安装相同版本（sha256 一致），跳过：{mod_name}", "success")
        return {"status": "skipped", "name": mod_name, "dir_path": target_dir}

    existed = os.path.isdir(target_dir)
    os.makedirs(target_dir, exist_ok=True)
    dest = os.path.join(target_dir, os.path.basename(dll_path))
    shutil.copy2(dll_path, dest)
    record_package_sha(game_path, mod_name, remote_sha)
    status = "updated" if existed else "installed"
    return {"status": status, "name": mod_name, "dir_path": target_dir}


def verify_zip_sha256(zip_path: str, expected_sha: str) -> bool:
    """校验下载包的 sha256 与预期是否一致（防损坏/防串包）。"""
    expected = _norm_sha(expected_sha)
    if not expected:
        return True
    return calc_file_sha256(zip_path) == expected


def dedupe_target_path(mods_dir: str, dest_name: str) -> str:
    """返回目标目录路径（安装前用于确认是否已存在同名 Mod）。"""
    return os.path.join(mods_dir, dest_name)
