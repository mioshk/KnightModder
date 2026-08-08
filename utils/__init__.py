# -*- coding: utf-8 -*-
"""
工具函数包
包含路径处理、系统检测、游戏查找等通用工具
"""
from utils.path_utils import (
    load_saved_path,
    save_path,
    normalize_path,
    get_root_from_exe,
    get_mods_dir,
    get_game_exe_path,
)
from utils.system_utils import (
    get_system_type,
    get_save_folder,
    get_api_zip_path,
    get_api_folder_path,
)
from utils.game_utils import (
    get_game_version,
    find_hollow_knight_exe,
)

__all__ = [
    # path_utils
    "load_saved_path",
    "save_path",
    "normalize_path",
    "get_root_from_exe",
    "get_mods_dir",
    "get_game_exe_path",
    # system_utils
    "get_system_type",
    "get_save_folder",
    "get_api_zip_path",
    "get_api_folder_path",
    # game_utils
    "get_game_version",
    "find_hollow_knight_exe",
]
