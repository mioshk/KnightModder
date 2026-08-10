# -*- coding: utf-8 -*-
"""
通用工具模块（合并自 system_utils / path_utils / game_utils）
包含系统类型检测、路径处理、游戏安装查找等功能
"""
import os
import json
import platform
import sys

from config import (
    CONFIG_FILE, MODS_RELATIVE_PATH,
    API_ZIP_MAP, API_FOLDER_NAME,
    get_base_dir,
)


# ============================================================
# 系统工具（原 system_utils.py）
# ============================================================
def get_system_type():
    """获取当前操作系统类型"""
    return platform.system()


def get_api_zip_path():
    """获取API压缩包文件路径"""
    system = get_system_type()
    zname = API_ZIP_MAP.get(system)
    if not zname:
        raise RuntimeError(f"不支持的系统：{system}")
    return os.path.join(get_base_dir(), API_FOLDER_NAME, zname)


def get_api_folder_path():
    """获取 API 文件夹路径"""
    return os.path.join(get_base_dir(), API_FOLDER_NAME)


def get_save_folder():
    """获取游戏存档文件夹路径"""
    s = get_system_type()
    if s == "Windows":
        return os.path.expandvars(r"%USERPROFILE%\AppData\LocalLow\Team Cherry\Hollow Knight")
    return None


# ============================================================
# 路径工具（原 path_utils.py）
# ============================================================
def load_saved_path():
    """从配置文件加载保存的游戏路径"""
    try:
        if os.path.isfile(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("game_path", "")
    except Exception:
        pass
    return ""


def save_path(path):
    """保存游戏路径到配置文件"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"game_path": path}, f, ensure_ascii=False)
    except Exception:
        pass


def normalize_path(path):
    """
    统一路径格式：
    - 盘符大写
    - 使用正斜杠 /
    - 确保盘符后有斜杠
    """
    if not path:
        return path
    if len(path) >= 2 and path[1] == ':':
        path = path[0].upper() + path[1:]
        if len(path) == 2 or path[2] not in ('/', '\\'):
            path = path[:2] + '/' + path[2:]
    path = path.replace('\\', '/')
    return path


def get_root_from_exe(exe_path):
    """从exe路径获取游戏根目录"""
    return normalize_path(os.path.dirname(exe_path))


def get_mods_dir(game_path):
    """获取Mods目录路径"""
    return os.path.join(game_path, MODS_RELATIVE_PATH)


def get_disabled_dir(game_path):
    """
    获取 Disabled 文件夹路径（在 Mods 目录下）
    """
    mods_dir = get_mods_dir(game_path)
    return os.path.join(mods_dir, "Disabled")


def get_metadata_path(game_path):
    """
    获取元数据文件路径 (.metadata.json)
    """
    mods_dir = get_mods_dir(game_path)
    return os.path.join(mods_dir, ".metadata.json")


def get_game_exe_path(game_path):
    """获取游戏可执行文件路径"""
    system = get_system_type()
    if system == "Windows":
        exe = os.path.join(game_path, "hollow_knight.exe")
        if os.path.isfile(exe):
            return exe
    return None


# ============================================================
# 游戏查找工具（原 game_utils.py）
# ============================================================
def find_hollow_knight_exe():
    """
    自动检测Steam/GOG安装目录中的空洞骑士
    返回列表: [(exe_path, game_root_path), ...]
    """
    system = get_system_type()
    results = []

    if system == "Windows":
        # ----- Steam 检测 -----
        steam_paths = []
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam")
            steam_path = winreg.QueryValueEx(key, "SteamPath")[0]
            if steam_path:
                steam_paths.append(steam_path)
        except Exception:
            pass

        pf86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        pf = os.environ.get("ProgramFiles", "C:\\Program Files")
        steam_paths.extend([
            os.path.join(pf86, "Steam"),
            os.path.join(pf, "Steam"),
        ])
        for d in ["D:", "E:", "F:", "G:"]:
            steam_paths.append(os.path.join(d, "SteamLibrary"))
            steam_paths.append(os.path.join(d, "Steam"))

        for sp in steam_paths:
            if os.path.isdir(sp):
                base = os.path.join(sp, "steamapps", "common", "Hollow Knight")
                exe = os.path.join(base, "hollow_knight.exe")
                if os.path.isfile(exe):
                    results.append((exe, normalize_path(base)))

        # ----- GOG 检测 -----
        gog_paths = []
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\GOG.com\Games")
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name)
                    try:
                        game_name = winreg.QueryValueEx(subkey, "gameName")[0]
                        if "hollow" in game_name.lower() or "knight" in game_name.lower():
                            install_path = winreg.QueryValueEx(subkey, "path")[0]
                            if install_path:
                                gog_paths.append(normalize_path(install_path))
                    except Exception:
                        pass
                    i += 1
                except WindowsError:
                    break
        except Exception:
            pass

        gog_paths.extend([
            normalize_path(os.path.join(pf86, "GOG Galaxy", "Games", "Hollow Knight")),
            normalize_path(os.path.join(pf, "GOG Galaxy", "Games", "Hollow Knight")),
        ])
        for d in ["D:", "E:", "F:", "G:"]:
            gog_paths.append(normalize_path(os.path.join(d, "GOG Games", "Hollow Knight")))
            gog_paths.append(normalize_path(os.path.join(d, "GOG Galaxy", "Games", "Hollow Knight")))

        for gp in gog_paths:
            if os.path.isdir(gp):
                exe = os.path.join(gp, "hollow_knight.exe")
                if os.path.isfile(exe):
                    results.append((exe, normalize_path(gp)))

        # 去重
        seen = set()
        unique_results = []
        for exe, path in results:
            if path not in seen:
                seen.add(path)
                unique_results.append((exe, path))
        results = unique_results

    return results
