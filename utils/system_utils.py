# -*- coding: utf-8 -*-
"""
系统工具模块
包含系统类型检测、路径获取、存档目录等函数
"""
import os
import platform
import sys

from config import API_ZIP_MAP, API_FOLDER_NAME, get_base_dir


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
