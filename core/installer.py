# -*- coding: utf-8 -*-
"""
安装器核心模块
包含API安装、原版还原、Mod安装、游戏启动、模组启用/禁用/删除、依赖解析等功能
"""
import os
import re
import json
import shutil
import subprocess
import os
import time
import zipfile
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Set, Dict, Optional, Callable

from config import MODLINKS_URL_CDN, MODLINKS_URL_RAW, STEAM_APPID, STEAM_RUN_URL, get_base_dir, API_ZIP_MAP, API_QUARK_LINKS
from utils.common import get_game_exe_path, get_managed_dir, get_mods_dir, get_download_dir, load_quark_cookie, get_system_type, safe_requests_get, fetch_remote_content, is_steam_official_path
from core.quark import QuarkClient, QuarkError


# ==================== 文件工具函数 ====================

def calculate_file_sha256(file_path):
    """
    计算文件的 SHA256 值
    :param file_path: 文件路径
    :return: SHA256 十六进制字符串，失败返回 None
    """
    try:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest().upper()
    except Exception:
        return None


def get_metadata_path(game_path):
    """
    获取元数据文件路径
    :param game_path: 游戏根目录
    :return: 元数据文件路径
    """
    mods_dir = get_mods_dir(game_path)
    return os.path.join(mods_dir, ".metadata.json")


def load_metadata(game_path):
    """
    加载元数据文件
    :param game_path: 游戏根目录
    :return: 元数据字典
    """
    metadata_path = get_metadata_path(game_path)
    if os.path.isfile(metadata_path):
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            pass
    return {}


def save_metadata(game_path, metadata):
    """
    保存元数据文件
    :param game_path: 游戏根目录
    :param metadata: 元数据字典
    """
    metadata_path = get_metadata_path(game_path)
    try:
        mods_dir = get_mods_dir(game_path)
        os.makedirs(mods_dir, exist_ok=True)
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def update_mod_metadata(game_path, mod_name, sha256=None, version=None):
    """
    更新单个模组的元数据
    :param game_path: 游戏根目录
    :param mod_name: 模组名称
    :param sha256: SHA256值（可选）
    :param version: 版本号（可选）
    """
    metadata = load_metadata(game_path)

    if mod_name not in metadata:
        metadata[mod_name] = {}

    if sha256 is not None:
        metadata[mod_name]["sha256"] = sha256
    if version is not None:
        metadata[mod_name]["version"] = version
    if "install_time" not in metadata[mod_name]:
        metadata[mod_name]["install_time"] = datetime.now().isoformat()

    save_metadata(game_path, metadata)


def remove_mod_metadata(game_path, mod_name):
    """
    移除模组的元数据
    :param game_path: 游戏根目录
    :param mod_name: 模组名称
    """
    metadata = load_metadata(game_path)
    if mod_name in metadata:
        del metadata[mod_name]
        save_metadata(game_path, metadata)


def get_mod_sha256(game_path, mod_name):
    """
    获取本地模组的SHA256值（从元数据读取）
    :param game_path: 游戏根目录
    :param mod_name: 模组名称
    :return: SHA256字符串，不存在则返回None
    """
    metadata = load_metadata(game_path)
    if mod_name in metadata:
        return metadata[mod_name].get("sha256")
    return None


def get_mod_version_from_metadata(game_path, mod_name):
    """
    获取本地模组的版本号（从元数据读取）
    :param game_path: 游戏根目录
    :param mod_name: 模组名称
    :return: 版本号字符串，不存在则返回None
    """
    metadata = load_metadata(game_path)
    target = re.sub(r"[ \-_\.]", "", (mod_name or "").lower())
    for key, info in metadata.items():
        if re.sub(r"[ \-_\.]", "", (key or "").lower()) == target and isinstance(info, dict):
            return info.get("version")
    return None


def scan_and_update_metadata(game_path, progress_callback=None):
    """
    扫描 Mods 目录下所有模组，计算 SHA256 并更新元数据文件
    :param game_path: 游戏根目录
    :param progress_callback: 进度回调函数
    """
    mods_dir = get_mods_dir(game_path)
    if not os.path.exists(mods_dir):
        if progress_callback:
            progress_callback("⚠️ Mods 文件夹不存在，跳过扫描", "warning")
        return {}

    metadata = load_metadata(game_path)
    modified = False

    # 遍历 Mods 目录（跳过 Disabled 文件夹）
    for item in os.listdir(mods_dir):
        if item == "Disabled":
            continue

        item_path = os.path.join(mods_dir, item)
        sha256 = None
        mod_name = item

        if os.path.isdir(item_path):
            # 文件夹形式：查找第一个 .dll 文件
            for root, dirs, files in os.walk(item_path):
                for file in files:
                    if file.endswith('.dll'):
                        dll_path = os.path.join(root, file)
                        sha256 = calculate_file_sha256(dll_path)
                        break
                if sha256:
                    break
        elif os.path.isfile(item_path) and item.endswith('.dll'):
            # 单文件形式
            sha256 = calculate_file_sha256(item_path)
            mod_name = os.path.splitext(item)[0]

        if sha256:
            if mod_name not in metadata:
                metadata[mod_name] = {}
            if metadata[mod_name].get('sha256') != sha256:
                metadata[mod_name]['sha256'] = sha256
                if 'install_time' not in metadata[mod_name]:
                    metadata[mod_name]['install_time'] = datetime.now().isoformat()
                modified = True
                if progress_callback:
                    progress_callback(f"✅ 更新元数据：{mod_name}", "success")

    # 检查是否有已删除的模组需要清理
    existing_mods = set()
    for item in os.listdir(mods_dir):
        if item == "Disabled":
            continue
        if os.path.isdir(os.path.join(mods_dir, item)):
            existing_mods.add(item)
        elif os.path.isfile(os.path.join(mods_dir, item)) and item.endswith('.dll'):
            existing_mods.add(os.path.splitext(item)[0])

    # 移除已不存在的模组元数据
    for mod_name in list(metadata.keys()):
        if mod_name not in existing_mods:
            del metadata[mod_name]
            modified = True
            if progress_callback:
                progress_callback(f"🗑 清理已删除模组元数据：{mod_name}", "warning")

    if modified:
        save_metadata(game_path, metadata)
        if progress_callback:
            progress_callback(f"✅ 元数据已更新，共 {len(metadata)} 个模组", "success")
    else:
        if progress_callback:
            progress_callback("✅ 所有模组元数据已是最新", "info")

    return metadata


# ==================== API 安装与还原（对齐 Lumafly 三文件互换） ====================

# 游戏实际加载的 dll，以及 Lumafly 式的原版 / 模组版备份文件名
_DLL_NAME = "Assembly-CSharp.dll"
_VANILLA_SUFFIX = ".v"
_MODDED_SUFFIX = ".m"


def _api_paths(managed):
    """返回 (当前dll, 原版备份, 模组版备份) 三个绝对路径"""
    cur = os.path.join(managed, _DLL_NAME)
    van = os.path.join(managed, _DLL_NAME + _VANILLA_SUFFIX)
    mod = os.path.join(managed, _DLL_NAME + _MODDED_SUFFIX)
    return cur, van, mod


def _is_modded_dll(dll_path):
    """
    判断 dll 是否为已注入 Modding API 的版本（对齐 Lumafly 的 Mono.Cecil 检测）。
    Lumafly 用 Cecil 读 ModHooks 类型判定；Python 里整读 dll 字节，命中注入进
    Assembly-CSharp.dll 的 'ModHooks' / 'ModLoader' 类型名即视为模组版；原版 dll
    不含这些字符串（已用 API/ 自带原版 dll 校准，不会误判）。
    """
    if not os.path.isfile(dll_path):
        return False
    try:
        with open(dll_path, "rb") as f:
            data = f.read()  # dll 约数 MB，整读以可靠命中元数据中的类型名
    except Exception:
        return False
    return b"ModHooks" in data or b"ModLoader" in data


def get_api_state(game_path):
    """
    返回当前 API 状态字典：
      enabled            : 当前加载的是否为模组版（True=模组版, False=原版）
      has_api            : 是否曾安装过 API（.m 备份存在）
      has_vanilla_backup : 是否有原版备份（.v 存在且确为原版）
    """
    managed = get_managed_dir(game_path)
    cur, van, mod = _api_paths(managed)
    current_modded = _is_modded_dll(cur)
    has_vanilla_backup = os.path.isfile(van) and not _is_modded_dll(van)
    if current_modded:
        return {"enabled": True, "has_api": True, "has_vanilla_backup": has_vanilla_backup}
    return {"enabled": False, "has_api": os.path.isfile(mod),
            "has_vanilla_backup": has_vanilla_backup}


def _resolve_api_package(status_callback, progress_callback):
    """
    取得 API 安装包：downloads/ 里已有则优先用本地缓存；否则从夸克网盘下载
    （下载后落盘到 downloads/ 供下次离线复用）。
    :return: 本地 zip 路径
    """
    system = get_system_type()
    if system not in API_ZIP_MAP:
        raise RuntimeError(f"不支持的系统：{system}")
    zip_name = API_ZIP_MAP[system]
    link = API_QUARK_LINKS.get(system)
    dl_dir = get_download_dir()
    os.makedirs(dl_dir, exist_ok=True)
    local_path = os.path.join(dl_dir, zip_name)

    # 本地缓存优先：命中则直接复用，无需触碰夸克
    if os.path.isfile(local_path) and os.path.getsize(local_path) > 0:
        status_callback(f"使用本地缓存的 API 安装包：{zip_name}", "info")
        return local_path

    if not link:
        raise RuntimeError(f"未配置 {system} 的夸克 API 下载链接")

    cookie = load_quark_cookie()
    if not cookie:
        raise QuarkError("尚未配置夸克账号。请先点击顶部「设置」→「登录夸克账号」后再安装 API")

    status_callback("正在从夸克网盘下载 API 安装包...", "info")
    client = QuarkClient(
        cookie_str=cookie,
        status_callback=lambda msg, lvl: status_callback(msg, lvl),
        progress_callback=progress_callback or (lambda *a: None),
    )
    if not client.is_logged_in:
        raise QuarkError("夸克 Cookie 已失效，请重新在「设置 → 夸克账号」中更新")

    platform_key = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}[system]

    def _sel(f):
        n = str(f.get("file_name") or "").lower()
        return platform_key in n and n.endswith(".zip")

    try:
        dest_dir = client.download_share(link, local_dir=dl_dir,
                                         remote_dir_name="api", select_file=_sel)
    except QuarkError:
        # 兜底：下载分享里任意 zip（分享内文件名不含平台关键字时）
        dest_dir = client.download_share(
            link, local_dir=dl_dir, remote_dir_name="api",
            select_file=lambda f: str(f.get("file_name") or "").lower().endswith(".zip"))

    # 在返回目录里定位 zip：优先平台名匹配的
    for root, _dirs, files in os.walk(dest_dir):
        for fn in files:
            if fn.lower().endswith(".zip") and platform_key in fn.lower():
                return os.path.join(root, fn)
    for root, _dirs, files in os.walk(dest_dir):
        for fn in files:
            if fn.lower().endswith(".zip"):
                return os.path.join(root, fn)
    raise FileNotFoundError("夸克下载目录中未找到 API 压缩包")


def install_api(game_path, status_callback=None, progress_callback=None):
    """
    安装 / 启用 Modding API（对齐 Lumafly 的「安装即备份、开关靠互换」机制）：
      - 全新安装：先备份当前原版 dll -> .v；下载/解压 API 包覆盖 Managed；再备份
        模组版 dll -> .m。
      - 已装但被关：直接把模组版 .m 切回 Current（无需下载）。
      - 已启用：幂等，无操作（仅确保 .m 备份存在）。
    """
    status_callback = status_callback or (lambda *a: None)
    managed = get_managed_dir(game_path)
    os.makedirs(managed, exist_ok=True)
    cur, van, mod = _api_paths(managed)
    state = get_api_state(game_path)

    if state["enabled"]:
        # 已启用：确保模组版备份存在，便于日后「还原原版」互换
        if os.path.isfile(cur) and not os.path.isfile(mod):
            shutil.copy2(cur, mod)
        status_callback("Modding API 已处于启用状态", "info")
        return state

    if state["has_api"] and not state["enabled"]:
        # 已装但被关：当前是原版 -> 备份为 .v，再把 .m 切回 Current
        if os.path.isfile(cur) and not os.path.isfile(van):
            shutil.copy2(cur, van)
        if os.path.isfile(cur):
            shutil.move(cur, van)
        shutil.move(mod, cur)
        status_callback("已重新启用 Modding API（模组版）", "success")
        return get_api_state(game_path)

    # —— 全新安装 ——
    # 1) 备份用户自己的原版 dll（仅当当前确为原版且尚无备份）
    if os.path.isfile(cur) and not _is_modded_dll(cur) and not os.path.isfile(van):
        shutil.copy2(cur, van)

    # 2) 取得安装包（本地缓存优先，否则夸克下载）并解压覆盖 Managed
    zip_path = _resolve_api_package(status_callback, progress_callback)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(managed)

    # 3) 备份新装的模组版 dll
    if os.path.isfile(cur):
        shutil.copy2(cur, mod)

    status_callback("✅ Modding API 安装完成！", "success")
    return get_api_state(game_path)


def restore_vanilla(game_path, status_callback=None):
    """
    还原原版（对齐 Lumafly 的「关掉 API」= 把原版 dll 切回 Current）：
      - 若 .v 原版备份存在：Current(模组) -> .m，.v -> Current，游戏加载原版。
      - 若 .v 缺失：无法离线还原，返回 {"ok": False, "reason": "no_vanilla_backup"}，
        由调用方提示用户用 Steam「验证游戏完整性」恢复官方原版。
    """
    status_callback = status_callback or (lambda *a: None)
    managed = get_managed_dir(game_path)
    cur, van, mod = _api_paths(managed)
    state = get_api_state(game_path)

    # 当前已是原版（没装 API，或已被关且原版就位）：无需操作
    if not state["enabled"]:
        status_callback("当前已是原版游戏，无需还原", "info")
        return {"ok": True, "already_vanilla": True}

    # 当前是模组版，需切回原版
    if not state["has_vanilla_backup"]:
        return {"ok": False, "reason": "no_vanilla_backup"}

    # 互换：Current(模组) -> .m；.v -> Current
    shutil.move(cur, mod)
    shutil.move(van, cur)
    status_callback("✅ 已还原为原版游戏（Modding API 已关闭）", "success")
    return {"ok": True, "already_vanilla": False}


# ==================== Mod 安装 ====================

def install_mods(game_path, file_paths, progress_callback=None):
    """
    安装Mod文件（支持zip和dll）
    :param game_path: 游戏根目录
    :param file_paths: Mod文件路径列表
    :param progress_callback: 进度回调函数
    """
    mods_dir = get_mods_dir(game_path)
    os.makedirs(mods_dir, exist_ok=True)

    success_count = 0
    fail_count = 0
    success_names = []

    for fp in file_paths:
        base = os.path.basename(fp)
        ext = os.path.splitext(base)[1].lower()
        mod_name = os.path.splitext(base)[0]
        dest = os.path.join(mods_dir, mod_name)

        try:
            if ext == '.zip':
                os.makedirs(dest, exist_ok=True)
                with zipfile.ZipFile(fp, 'r') as zf:
                    zf.extractall(dest)
            elif ext == '.dll':
                os.makedirs(dest, exist_ok=True)
                shutil.copy2(fp, os.path.join(dest, base))
            else:
                shutil.copy2(fp, os.path.join(mods_dir, base))
                mod_name = base
        except Exception as e:
            fail_count += 1
            if progress_callback:
                progress_callback(f"❌ {base} 安装失败：{e}", "error")
            continue

        success_count += 1
        success_names.append(mod_name)

        # 安装完成后自动计算 SHA256 并记录
        sha256 = None
        mod_path = os.path.join(mods_dir, mod_name)

        if os.path.isdir(mod_path):
            for root, dirs, files in os.walk(mod_path):
                for file in files:
                    if file.endswith('.dll'):
                        dll_path = os.path.join(root, file)
                        sha256 = calculate_file_sha256(dll_path)
                        break
                if sha256:
                    break
        else:
            file_path = os.path.join(mods_dir, mod_name)
            if os.path.isfile(file_path):
                sha256 = calculate_file_sha256(file_path)

        update_mod_metadata(game_path, mod_name, sha256=sha256)

    # 统一输出安装结果（带 Mod 名称）
    if success_count > 0:
        names_str = "、".join(success_names)
        if progress_callback:
            progress_callback(f"✅ 已安装 {success_count} 个 Mod：{names_str}", "success")

    if fail_count > 0:
        if progress_callback:
            progress_callback(f"⚠️ {fail_count} 个 Mod 安装失败", "warning")

    if success_count == 0 and fail_count == 0:
        if progress_callback:
            progress_callback("没有需要安装的 Mod", "info")


# ==================== 游戏启动 ====================

def launch_game(game_path, progress_callback=None):
    """
    启动游戏
    :param game_path: 游戏根目录
    :param progress_callback: 进度回调函数
    """
    system = get_system_type()
    exe_path = get_game_exe_path(game_path)
    if not exe_path:
        if progress_callback:
            progress_callback("❌ 未找到游戏可执行文件", "error")
        raise FileNotFoundError(f"未找到游戏可执行文件：{game_path}")

    try:
        # 仅当用户选择的是 Steam 官方安装目录（与 Steam 库注册的 AppID 安装位置
        # 一致）才经 Steam 启动：Popen 直启官方版会触发 Steamworks DRM 让游戏退出
        # 并重启自己，造成双实例撞单实例锁弹 "another instance is already running"。
        # 自定义副本（哪怕放在 steamapps\\common 下）必须直启用户指定目录，否则
        # steam:// 会无视选择、永远启动 Steam 库里的官方版。
        if is_steam_official_path(game_path, STEAM_APPID):
            if system == "Windows":
                os.startfile(STEAM_RUN_URL)
            else:
                subprocess.Popen(["open" if system == "Darwin" else "xdg-open", STEAM_RUN_URL])
            if progress_callback:
                progress_callback("✅ 已请求 Steam 启动游戏", "success")
            return
        if system == "Darwin":
            # macOS 必须经由 open 启动 .app（直接 Popen .app 路径无效）
            subprocess.Popen(["open", exe_path])
        else:
            subprocess.Popen([exe_path], cwd=game_path)
        if progress_callback:
            progress_callback("✅ 游戏已启动", "success")
    except Exception as e:
        if progress_callback:
            progress_callback(f"❌ 启动失败：{e}", "error")
        raise RuntimeError(f"启动失败：{e}")


# ==================== 模组启用/禁用/删除 ====================

def get_disabled_dir(game_path):
    """
    获取 Disabled 文件夹路径（在 Mods 目录下）
    """
    mods_dir = get_mods_dir(game_path)
    return os.path.join(mods_dir, "Disabled")


def disable_mod(game_path, mod_name, progress_callback=None):
    """
    禁用模组：将模组移动到 Mods/Disabled 文件夹
    :param game_path: 游戏根目录
    :param mod_name: 模组名称
    :param progress_callback: 进度回调函数
    """
    mods_dir = get_mods_dir(game_path)
    disabled_dir = get_disabled_dir(game_path)

    if not os.path.exists(disabled_dir):
        os.makedirs(disabled_dir)
        if progress_callback:
            progress_callback(f"创建 Disabled 文件夹", "info")

    mod_path = os.path.join(mods_dir, mod_name)
    dll_path = os.path.join(mods_dir, mod_name + '.dll')

    if os.path.isdir(mod_path):
        target = os.path.join(disabled_dir, mod_name)
        try:
            if os.path.exists(target):
                shutil.rmtree(target)
            shutil.move(mod_path, target)
        except OSError as e:
            if progress_callback:
                progress_callback(f"❌ 禁用失败（文件被占用或无权限）：{mod_name} - {e}", "error")
            return False
        if progress_callback:
            progress_callback(f"⛔ 已禁用：{mod_name}", "warning")
        return True

    elif os.path.isfile(dll_path):
        target = os.path.join(disabled_dir, mod_name + '.dll')
        try:
            if os.path.exists(target):
                os.remove(target)
            shutil.move(dll_path, target)
        except OSError as e:
            if progress_callback:
                progress_callback(f"❌ 禁用失败（文件被占用或无权限）：{mod_name} - {e}", "error")
            return False
        if progress_callback:
            progress_callback(f"⛔ 已禁用：{mod_name}", "warning")
        return True

    disabled_mod_path = os.path.join(disabled_dir, mod_name)
    disabled_dll_path = os.path.join(disabled_dir, mod_name + '.dll')

    if os.path.isdir(disabled_mod_path) or os.path.isfile(disabled_dll_path):
        if progress_callback:
            progress_callback(f"模组已禁用：{mod_name}", "info")
        return True

    else:
        if progress_callback:
            progress_callback(f"❌ 未找到模组：{mod_name}", "error")
        return False


def enable_mod(game_path, mod_name, progress_callback=None):
    """
    启用模组：将模组从 Mods/Disabled 移回 Mods
    :param game_path: 游戏根目录
    :param mod_name: 模组名称
    :param progress_callback: 进度回调函数
    """
    mods_dir = get_mods_dir(game_path)
    disabled_dir = get_disabled_dir(game_path)

    if not os.path.exists(disabled_dir):
        if progress_callback:
            progress_callback(f"❌ Disabled 文件夹不存在", "error")
        return False

    disabled_mod_path = os.path.join(disabled_dir, mod_name)
    disabled_dll_path = os.path.join(disabled_dir, mod_name + '.dll')

    if os.path.isdir(disabled_mod_path):
        target = os.path.join(mods_dir, mod_name)
        try:
            if os.path.exists(target):
                shutil.rmtree(target)
            shutil.move(disabled_mod_path, target)
        except OSError as e:
            if progress_callback:
                progress_callback(f"❌ 启用失败（文件被占用或无权限）：{mod_name} - {e}", "error")
            return False
        if progress_callback:
            progress_callback(f"✅ 已启用：{mod_name}", "success")
        return True

    elif os.path.isfile(disabled_dll_path):
        target = os.path.join(mods_dir, mod_name + '.dll')
        try:
            if os.path.exists(target):
                os.remove(target)
            shutil.move(disabled_dll_path, target)
        except OSError as e:
            if progress_callback:
                progress_callback(f"❌ 启用失败（文件被占用或无权限）：{mod_name} - {e}", "error")
            return False
        if progress_callback:
            progress_callback(f"✅ 已启用：{mod_name}", "success")
        return True

    mod_path = os.path.join(mods_dir, mod_name)
    dll_path = os.path.join(mods_dir, mod_name + '.dll')

    if os.path.isdir(mod_path) or os.path.isfile(dll_path):
        if progress_callback:
            progress_callback(f"模组已启用：{mod_name}", "info")
        return True

    else:
        if progress_callback:
            progress_callback(f"❌ 未找到已禁用的模组：{mod_name}", "error")
        return False


def delete_mod(game_path, mod_name, progress_callback=None):
    """
    删除模组（从 Mods 或 Mods/Disabled 中永久删除）
    :param game_path: 游戏根目录
    :param mod_name: 模组名称
    :param progress_callback: 进度回调函数
    """
    mods_dir = get_mods_dir(game_path)
    disabled_dir = get_disabled_dir(game_path)

    deleted = False

    if os.path.exists(mods_dir):
        mod_path = os.path.join(mods_dir, mod_name)
        dll_path = os.path.join(mods_dir, mod_name + '.dll')

        try:
            if os.path.isdir(mod_path):
                shutil.rmtree(mod_path)
                deleted = True
            elif os.path.isfile(dll_path):
                os.remove(dll_path)
                deleted = True
        except OSError as e:
            if progress_callback:
                progress_callback(f"❌ 删除失败（文件被占用或无权限）：{mod_name} - {e}", "error")
            return False

    if os.path.exists(disabled_dir):
        disabled_mod_path = os.path.join(disabled_dir, mod_name)
        disabled_dll_path = os.path.join(disabled_dir, mod_name + '.dll')

        try:
            if os.path.isdir(disabled_mod_path):
                shutil.rmtree(disabled_mod_path)
                deleted = True
            elif os.path.isfile(disabled_dll_path):
                os.remove(disabled_dll_path)
                deleted = True
        except OSError as e:
            if progress_callback:
                progress_callback(f"❌ 删除失败（文件被占用或无权限）：{mod_name} - {e}", "error")
            return False

    if deleted:
        remove_mod_metadata(game_path, mod_name)
        if progress_callback:
            progress_callback(f"🗑 已删除：{mod_name}", "warning")
        return True
    else:
        if progress_callback:
            progress_callback(f"❌ 未找到模组：{mod_name}", "error")
        return False


def is_mod_enabled(game_path, mod_name):
    """
    检查模组是否启用
    :param game_path: 游戏根目录
    :param mod_name: 模组名称
    :return: True=启用, False=禁用, None=未安装
    """
    mods_dir = get_mods_dir(game_path)
    disabled_dir = get_disabled_dir(game_path)

    if os.path.exists(mods_dir):
        mod_path = os.path.join(mods_dir, mod_name)
        dll_path = os.path.join(mods_dir, mod_name + '.dll')
        if os.path.isdir(mod_path) or os.path.isfile(dll_path):
            return True

    if os.path.exists(disabled_dir):
        disabled_mod_path = os.path.join(disabled_dir, mod_name)
        disabled_dll_path = os.path.join(disabled_dir, mod_name + '.dll')
        if os.path.isdir(disabled_mod_path) or os.path.isfile(disabled_dll_path):
            return False

    return None


# ==================== 依赖解析模块 ====================

class DependencyResolver:
    """Mod依赖解析器"""

    # 缓存有效期：6 小时内直接用缓存秒开，后台再静默刷新
    CACHE_TTL = 6 * 3600

    def __init__(self):
        self.dependency_map = {}      # mod_name -> 依赖列表
        self.link_map = {}            # mod_name -> 单个下载链接
        self.batch_links_map = {}     # mod_name -> 批量下载链接列表
        self.all_mods = set()
        self.is_loaded = False
        self.mod_data = []
        self.mod_data_by_name = {}

    # ---------- 本地缓存（避免每次启动都等网络） ----------
    @staticmethod
    def _cache_file() -> str:
        """缓存文件路径：优先用户 AppData，fallback 到程序目录"""
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "KnightModder")
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            d = get_base_dir()
        return os.path.join(d, "ModLinksCN.xml")

    def save_cache(self, content: bytes) -> bool:
        """保存 Mod 链接 XML 到本地缓存"""
        try:
            with open(self._cache_file(), "wb") as f:
                f.write(content)
            return True
        except OSError:
            return False

    def load_cached(self, progress_callback: Optional[Callable] = None) -> bool:
        """从本地缓存加载（不联网），成功返回 True"""
        try:
            path = self._cache_file()
            if not os.path.isfile(path):
                return False
            with open(path, "rb") as f:
                content = f.read()
            return self._parse_xml_content(content, progress_callback)
        except OSError:
            return False

    def load_from_url(self, url: Optional[str] = None, progress_callback: Optional[Callable] = None) -> bool:
        """
        从URL加载Mod依赖数据（CDN 优先、GitHub raw 兜底）
        :param url: 自定义单源XML地址；默认使用 CDN + raw 双源容灾
        :param progress_callback: 进度回调函数
        :return: 是否加载成功
        """
        try:
            if url:
                # 显式传入单个地址：直接请求该地址
                if progress_callback:
                    progress_callback("🔍 正在加载 Mod 链接...", "info")
                response = safe_requests_get(
                    url, timeout=15,
                    ssl_warn_callback=lambda msg: progress_callback(msg, "warning") if progress_callback else None
                )
                response.raise_for_status()
                content = response.content
            else:
                if progress_callback:
                    progress_callback("🔍 正在获取最新的 Mod 数据...", "info")
                content, source = fetch_remote_content(
                    MODLINKS_URL_CDN, MODLINKS_URL_RAW, timeout=15,
                    ssl_warn_callback=lambda msg: progress_callback(msg, "warning") if progress_callback else None
                )
                if content is None:
                    if progress_callback:
                        progress_callback("❌ 网络请求失败，请检查网络连接", "error")
                    return False
                if source == "github-raw" and progress_callback:
                    progress_callback("⚠️ 检测到远程数据未同步，已自动使用最新数据", "warning")

            if progress_callback:
                progress_callback("📥 正在解析 Mod 数据...", "info")

            if self._parse_xml_content(content, progress_callback):
                # 解析成功后才写入本地缓存，避免坏数据覆盖缓存
                self.save_cache(content)
                return True
            if progress_callback:
                progress_callback("❌ 数据解析失败", "error")
            return False
        except Exception as e:
            if progress_callback:
                progress_callback(f"❌ Mod 链接加载失败：{e}", "error")
            return False

    def _parse_xml_content(self, content, progress_callback: Optional[Callable] = None) -> bool:
        """解析XML内容"""
        try:
            root = ET.fromstring(content)

            self.dependency_map.clear()
            self.link_map.clear()
            self.batch_links_map.clear()
            self.all_mods.clear()
            self.mod_data = []
            self.mod_data_by_name = {}

            mods = root.findall('.//Mod')
            if not mods:
                if progress_callback:
                    progress_callback("❌ 未找到任何 Mod 条目", "error")
                return False

            for mod in mods:
                name_elem = mod.find('./Name')
                if name_elem is None or not name_elem.text:
                    continue
                name = name_elem.text.strip()

                # 提取中文名称
                name_cn_elem = mod.find('./NameCN')
                chinese_name = name_cn_elem.text.strip() if name_cn_elem is not None and name_cn_elem.text else ""

                # 提取版本
                version_elem = mod.find('./Version')
                version = version_elem.text.strip() if version_elem is not None and version_elem.text else ""

                # 提取描述
                desc_elem = mod.find('./Description')
                desc_en = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""

                desc_cn_elem = mod.find('./DescriptionCN')
                desc_cn = desc_cn_elem.text.strip() if desc_cn_elem is not None and desc_cn_elem.text else ""

                # 提取中文标签
                tags_elem = mod.find('./TagsCN')
                tags = tags_elem.text.strip() if tags_elem is not None and tags_elem.text else ""

                # 提取夸克网盘单个链接
                qlink_elem = mod.find('./QLink')
                qlink = qlink_elem.text.strip() if qlink_elem is not None and qlink_elem.text else ""

                # 提取远程安装包文件名（分享内的 zip 名，用于下载后精确匹配）
                download_name_elem = mod.find('./DownloadName')
                download_name = download_name_elem.text.strip() if download_name_elem is not None and download_name_elem.text else ""

                # 提取远程安装包 sha256（分享 zip 的哈希，用于“已是最新/可更新”判断与防损坏校验）
                # 注意：线上数据源用的是全大写 <SHA256>，而早期本地 XML 用 <Sha256>，
                # ElementTree.find 区分大小写，必须按大小写不敏感匹配，否则 online_sha 恒为空、
                # 所有 Mod 的“待更新”判定都会失效（一律显示已安装）。
                sha256 = ""
                for _child in mod:
                    if _child.tag.lower() == "sha256" and _child.text:
                        sha256 = _child.text.strip()
                        break

                # 提取夸克网盘批量链接
                qlinks_elem = mod.find('./QLinks')
                qlinks = []
                if qlinks_elem is not None and qlinks_elem.text:
                    qlinks = [link.strip() for link in qlinks_elem.text.split(';') if link.strip()]

                # 提取依赖
                deps = []
                deps_elem = mod.find('./AllDependencies')
                if deps_elem is not None and deps_elem.text:
                    deps = [dep.strip() for dep in deps_elem.text.split(';') if dep.strip()]

                # 提取联动
                integrations = []
                integrations_elem = mod.find('./Integrations')
                if integrations_elem is not None and integrations_elem.text:
                    integrations = [intg.strip() for intg in integrations_elem.text.split(';') if intg.strip()]

                self.all_mods.add(name)

                if qlink:
                    self.link_map[name] = qlink
                elif qlinks:
                    self.link_map[name] = qlinks[0]

                if qlinks:
                    self.batch_links_map[name] = qlinks

                if deps:
                    self.dependency_map[name] = deps

                mod_info = {
                    "name": name,
                    "chinese_name": chinese_name,
                    "version": version,
                    "link": qlink,
                    "batch_links": qlinks,
                    "download_name": download_name,
                    "sha256": sha256,
                    "dependencies": deps,
                    "tags": tags,
                    "desc_cn": desc_cn,
                    "desc_en": desc_en,
                    "integrations": integrations,
                }
                self.mod_data.append(mod_info)
                self.mod_data_by_name[name] = mod_info

            self.mod_data.sort(key=lambda x: x["name"].lower())
            self.is_loaded = True

            if progress_callback:
                progress_callback(f"✅ 在网络上找到 {len(self.all_mods)} 个 Mod", "success")
            return True

        except ET.ParseError as e:
            if progress_callback:
                progress_callback(f"❌ XML 解析失败：{e}", "error")
            return False
        except Exception as e:
            if progress_callback:
                progress_callback(f"❌ 解析失败：{e}", "error")
            return False

    def get_all_dependencies(self, mod_name: str) -> Set[str]:
        """获取某个Mod的所有依赖"""
        deps = self.dependency_map.get(mod_name, [])
        return set(deps)

    def check_missing_dependencies(self, installed_mods: Set[str]) -> Optional[Set[str]]:
        """
        检查已安装Mod中缺失的依赖
        :param installed_mods: 已安装Mod名称集合
        :return: 缺失的依赖集合，加载失败返回None
        """
        if not self.is_loaded:
            return None

        all_needed = set()
        for mod in installed_mods:
            if mod in self.dependency_map:
                all_needed.update(self.get_all_dependencies(mod))

        missing = all_needed - installed_mods
        return missing

    def get_mod_links(self, mod_names: List[str]) -> Dict[str, Optional[str]]:
        """批量获取Mod下载链接"""
        result = {}
        for name in mod_names:
            result[name] = self.link_map.get(name)
        return result

    def get_mod_batch_links(self, mod_names: List[str]) -> Dict[str, Optional[List[str]]]:
        """批量获取Mod批量下载链接"""
        result = {}
        for name in mod_names:
            result[name] = self.batch_links_map.get(name)
        return result

    def get_mod_data_by_name(self, mod_name: str) -> Optional[Dict]:
        """根据Mod名称获取完整信息"""
        return self.mod_data_by_name.get(mod_name)

    def search_mods(self, keyword: str, search_in: str = "all") -> List[Dict]:
        """
        搜索Mod
        :param keyword: 搜索关键词
        :param search_in: 搜索字段 ("name", "chinese_name", "desc", "tags", "all")
        :return: 匹配的Mod列表
        """
        if not self.is_loaded:
            return []

        keyword_lower = keyword.lower()
        results = []

        search_fields = {
            "name": lambda m: keyword_lower in m["name"].lower(),
            "chinese_name": lambda m: keyword_lower in m["chinese_name"].lower(),
            "desc": lambda m: keyword_lower in m["desc_cn"].lower() or keyword_lower in m["desc_en"].lower(),
            "tags": lambda m: keyword_lower in m["tags"].lower(),
            "all": lambda m: (
                keyword_lower in m["name"].lower() or
                keyword_lower in m["chinese_name"].lower() or
                keyword_lower in m["desc_cn"].lower() or
                keyword_lower in m["desc_en"].lower() or
                keyword_lower in m["tags"].lower()
            )
        }

        match_func = search_fields.get(search_in, search_fields["all"])

        for mod_info in self.mod_data:
            if match_func(mod_info):
                results.append(mod_info)

        return results

    def get_all_mod_names(self) -> List[str]:
        """获取所有Mod名称列表"""
        return sorted(list(self.all_mods))

    def get_mod_count(self) -> int:
        """获取已加载的Mod数量"""
        return len(self.all_mods)

    def is_mod_exist(self, mod_name: str) -> bool:
        """检查Mod是否存在"""
        return mod_name in self.all_mods
