# -*- coding: utf-8 -*-
"""
路径处理工具模块
包含路径规范化、配置读写、路径转换等函数
"""
import os
import json

from config import CONFIG_FILE, MODS_RELATIVE_PATH


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
    from utils.system_utils import get_system_type
    system = get_system_type()
    if system == "Windows":
        exe = os.path.join(game_path, "hollow_knight.exe")
        if os.path.isfile(exe):
            return exe
    return None


def find_hollow_knight_exe():
    """
    自动查找 hollow_knight.exe 的位置
    扫描常见安装路径
    :return: 列表 [(exe_path, root_path), ...]
    """
    common_paths = []

    # Windows 常见路径
    if os.name == 'nt':
        drives = ['C:', 'D:', 'E:', 'F:']
        for drive in drives:
            if os.path.exists(drive + '\\'):
                common_paths.append(os.path.join(drive, 'Program Files (x86)', 'Steam', 'steamapps', 'common', 'Hollow Knight'))
                common_paths.append(os.path.join(drive, 'Program Files', 'Steam', 'steamapps', 'common', 'Hollow Knight'))
                common_paths.append(os.path.join(drive, 'SteamLibrary', 'steamapps', 'common', 'Hollow Knight'))
                common_paths.append(os.path.join(drive, 'GOG Games', 'Hollow Knight'))

        # Steam 库路径（从 libraryfolders.vdf 读取）
        steam_path = os.path.expanduser('~') + '\\AppData\\Local\\Programs\\Steam'
        if not os.path.exists(steam_path):
            steam_path = 'C:\\Program Files (x86)\\Steam'
        library_file = os.path.join(steam_path, 'steamapps', 'libraryfolders.vdf')
        if os.path.isfile(library_file):
            try:
                with open(library_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if '"path"' in line:
                            path = line.split('"')[3] if '"' in line else ''
                            if path and os.path.isdir(path):
                                common_paths.append(os.path.join(path, 'steamapps', 'common', 'Hollow Knight'))
            except Exception:
                pass

    # macOS 常见路径
    elif os.name == 'posix':
        common_paths.append(os.path.expanduser('~/Library/Application Support/Steam/steamapps/common/Hollow Knight'))
        common_paths.append(os.path.expanduser('~/Library/Application Support/GOG Games/Hollow Knight'))
        common_paths.append('/Applications/Hollow Knight.app/Contents/Resources')

    results = []
    for path in common_paths:
        exe_path = os.path.join(path, 'hollow_knight.exe')
        if os.path.isfile(exe_path):
            results.append((exe_path, path))

    return results