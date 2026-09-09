# -*- coding: utf-8 -*-
"""
核心业务逻辑包
包含依赖解析、安装、还原等核心功能
"""
from core.installer import (
    # 依赖解析
    DependencyResolver,
    # API 安装与还原
    install_api,
    restore_vanilla,
    # Mod 安装
    install_mods,
    # 模组管理
    disable_mod,
    enable_mod,
    delete_mod,
    is_mod_enabled,
)

__all__ = [
    "DependencyResolver",
    "install_api",
    "restore_vanilla",
    "install_mods",
    "disable_mod",
    "enable_mod",
    "delete_mod",
    "is_mod_enabled",
]