# -*- coding: utf-8 -*-
"""
全局配置模块
包含应用常量、路径配置、主题配色等
"""
import os
import sys

# ---------- 应用基本信息 ----------
APP_NAME = "KnightModder 骑士模组师"
APP_VERSION = "1.3.2"

# ---------- Steam 相关 ----------
# 《空洞骑士》Steam AppID 与启动协议
STEAM_APPID = "367520"
STEAM_RUN_URL = "steam://rungameid/367520"

# ---------- 路径相关常量 ----------
API_FOLDER_NAME = "API"
MODS_RELATIVE_PATH = r"hollow_knight_Data\Managed\Mods"
MANAGED_RELATIVE_PATH = r"hollow_knight_Data\Managed"
CONFIG_FILE = "config.json"

# ---------- 网络资源 URL ----------
# 每个 GitHub 仓库文件均提供双源：
#   *_CDN = jsDelivr CDN 加速地址（优先读取）
#   *_RAW = GitHub raw 原地址（CDN 拉取失败 / 缓存未刷新时兜底）
# 统一经 utils.common.fetch_remote_content() 读取：先读 CDN，读不到就读
# raw；两者内容不一致说明 CDN 缓存未刷新，采用 raw 的内容。
GH_RAW_BASE = "https://raw.githubusercontent.com/mioshk/KnightModder/refs/heads/main"
GH_CDN_BASE = "https://cdn.jsdelivr.net/gh/mioshk/KnightModder@main"

# 作者主页（B 站）
AUTHOR_URL = "https://space.bilibili.com/538844794"

# 更新检查（version.json）
UPDATE_CHECK_URL_CDN = f"{GH_CDN_BASE}/version.json"
UPDATE_CHECK_URL_RAW = f"{GH_RAW_BASE}/version.json"

# 在线模组链接（ModLinksCN.xml）
MODLINKS_URL_CDN = f"{GH_CDN_BASE}/ModLinksCN.xml"
MODLINKS_URL_RAW = f"{GH_RAW_BASE}/ModLinksCN.xml"

# Markdown 文档（关于 / 使用教程）
README_URL_CDN = f"{GH_CDN_BASE}/README.md"
README_URL_RAW = f"{GH_RAW_BASE}/README.md"
USAGE_URL_CDN = f"{GH_CDN_BASE}/USAGE.md"
USAGE_URL_RAW = f"{GH_RAW_BASE}/USAGE.md"

# ---------- API 压缩包平台映射 ----------
API_ZIP_MAP = {
    "Windows": "moddingapi.v77.windows.zip",
    "Darwin":  "moddingapi.v77.macos.zip",
    "Linux":   "moddingapi.v77.linux.zip",
}

# ---------- 暗黑极简配色方案 ----------
COLOR_BG = "#0F0F0F"
COLOR_CARD = "#1E1E1E"
COLOR_CARD_HOVER = "#2A2A2A"
COLOR_TEXT_PRIMARY = "#FFFFFF"
COLOR_TEXT_SECONDARY = "#B0B0B0"
COLOR_TEXT_TERTIARY = "#6A6A6A"
COLOR_ACCENT_PINK = "#E91E63"
COLOR_ACCENT_BLUE = "#00BCD4"
COLOR_ACCENT_GREEN = "#4CAF50"
COLOR_ACCENT_ORANGE = "#FF9800"
COLOR_ACCENT_RED = "#F44336"
COLOR_ACCENT_PURPLE = "#9C27B0"
COLOR_INPUT_BG = "#2C2C2C"
COLOR_BORDER = "#424242"
COLOR_BORDER_HOVER = "#666666"


def get_base_dir():
    """获取程序基础目录（打包后或源码运行均适用）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))
