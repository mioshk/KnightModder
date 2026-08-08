# -*- coding: utf-8 -*-
"""
游戏工具模块
包含游戏版本检测、自动查找游戏安装目录等函数
"""
import os
import re

from config import MANAGED_RELATIVE_PATH
from utils.path_utils import normalize_path
from utils.system_utils import get_system_type


def get_game_version(game_path):
    """
    获取游戏版本号
    优先从version文件读取，其次尝试读取dll/exe文件版本信息
    """
    try:
        # 方法1: 读取 version 文件
        version_file = os.path.join(game_path, "hollow_knight_Data", "version")
        if os.path.isfile(version_file):
            with open(version_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                match = re.search(r'(\d+\.\d+\.\d+)', content)
                if match:
                    return match.group(1)
                return content

        # 方法2: 读取 Assembly-CSharp.dll 版本
        dll_path = os.path.join(game_path, MANAGED_RELATIVE_PATH, "Assembly-CSharp.dll")
        if os.path.isfile(dll_path):
            try:
                import win32api
                info = win32api.GetFileVersionInfo(dll_path, "\\")
                version = f"{info['FileVersionMS'] >> 16}.{info['FileVersionMS'] & 0xFFFF}.{info['FileVersionLS'] >> 16}.{info['FileVersionLS'] & 0xFFFF}"
                parts = version.split('.')
                if len(parts) >= 3:
                    return f"{parts[0]}.{parts[1]}.{parts[2]}"
                return version
            except Exception:
                pass

        # 方法3: 读取 exe 版本
        exe_path = os.path.join(game_path, "hollow_knight.exe")
        if os.path.isfile(exe_path):
            try:
                import win32api
                info = win32api.GetFileVersionInfo(exe_path, "\\")
                version = f"{info['FileVersionMS'] >> 16}.{info['FileVersionMS'] & 0xFFFF}.{info['FileVersionLS'] >> 16}.{info['FileVersionLS'] & 0xFFFF}"
                parts = version.split('.')
                if len(parts) >= 3:
                    return f"{parts[0]}.{parts[1]}.{parts[2]}"
                return version
            except Exception:
                pass

        # 方法4: StreamingAssets/version
        version_file2 = os.path.join(game_path, "hollow_knight_Data", "StreamingAssets", "version")
        if os.path.isfile(version_file2):
            with open(version_file2, "r", encoding="utf-8") as f:
                content = f.read().strip()
                match = re.search(r'(\d+\.\d+\.\d+)', content)
                if match:
                    return match.group(1)
                return content

    except Exception:
        pass
    return None


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
