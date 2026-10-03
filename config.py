# -*- coding: utf-8 -*-
"""
全局配置模块
包含应用常量、路径配置、主题配色等
"""
import os
import sys

# ---------- 应用基本信息 ----------
APP_NAME = "KnightModder 骑士模组师"
APP_VERSION = "1.4.10"

# ---------- Steam 相关 ----------
# 《空洞骑士》Steam AppID 与启动协议
STEAM_APPID = "367520"
STEAM_RUN_URL = "steam://rungameid/367520"

# ---------- 路径相关常量 ----------
CONFIG_FILE = "config.json"
DOWNLOAD_DIR_NAME = "downloads"

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

# Mod 链接的「多源容灾」清单：按顺序排列，load_from_url 逐一尝试、谁先成功用谁。
#
# 背景（踩坑）：国内大量用户网络下 jsDelivr 和 raw.githubusercontent.com 都被墙 /
# 超时（本机实测 raw.githubusercontent.com 直接 12s 超时）。旧版只试这两个源，于是
# 「更新链接」永远失败、报「Mod 链接加载失败」。下面额外挂了几个国内通常可达的
# GitHub 镜像源兜底，能救回绝大多数用户。若要再加自己的镜像（最稳的是挂一个你自托管的
# 国内可达地址，比如阿里云 OSS / Gitee Pages / 个人服务器），直接往这个列表里塞即可。
MODLINKS_URLS = [
    "https://fastly.jsdelivr.net/gh/mioshk/KnightModder@main/ModLinksCN.xml",   # Fastly 版 jsDelivr：国内常可达，优先
    "https://gcore.jsdelivr.net/gh/mioshk/KnightModder@main/ModLinksCN.xml",    # Gcore 版 jsDelivr：另一组国内可达节点
    f"{GH_CDN_BASE}/ModLinksCN.xml",                                  # jsDelivr 默认域名（cdn.jsdelivr.net）
    f"{GH_RAW_BASE}/ModLinksCN.xml",                                  # GitHub raw
    "https://raw.gitmirror.com/mioshk/KnightModder/main/ModLinksCN.xml",
    "https://ghproxy.net/https://raw.githubusercontent.com/mioshk/KnightModder/refs/heads/main/ModLinksCN.xml",
    "https://mirror.ghproxy.com/https://raw.githubusercontent.com/mioshk/KnightModder/refs/heads/main/ModLinksCN.xml",
]

# 手动「更新链接」优先走、不经过 CDN 缓存的「实时源」：直接反代 GitHub raw，推完即最新。
# 背景（实测踩坑）：jsDelivr 的 shield 层缓存按「仓库+路径」存，query 戳只打穿 edge、
# shield 仍吐旧副本（同 etag），所以给 jsDelivr 加 ?_= 时间戳并不能即时刷新；而 ghproxy /
# gitmirror 这类反代源实时代理 raw.githubusercontent，etag 随 GitHub 最新提交变化。
# 手动刷新就用这份列表（ghproxy 优先，因为它在多数被墙网络下仍可通），拿不到再退回上面的 CDN 列表。
MODLINKS_FRESH_URLS = [
    "https://ghproxy.net/https://raw.githubusercontent.com/mioshk/KnightModder/refs/heads/main/ModLinksCN.xml",
    f"{GH_RAW_BASE}/ModLinksCN.xml",
    "https://raw.gitmirror.com/mioshk/KnightModder/main/ModLinksCN.xml",
]

# Markdown 文档（关于 / 使用教程）
README_URL_CDN = f"{GH_CDN_BASE}/README.md"
README_URL_RAW = f"{GH_RAW_BASE}/README.md"
USAGE_URL_CDN = f"{GH_CDN_BASE}/USAGE.md"
USAGE_URL_RAW = f"{GH_RAW_BASE}/USAGE.md"

# ---------- API 安装清单（api_manifest.json） ----------
# API 的下载地址不再写死在软件里：仓库根目录的 api_manifest.json 才是唯一来源，
# 作者改完往 GitHub 一推，所有已安装的软件下次装 API 时就会自动读到新清单，
# 不必重新发版。读取与兜底逻辑见 core/api_manifest.py。
API_MANIFEST_FILE = "api_manifest.json"
API_MANIFEST_URL_CDN = f"{GH_CDN_BASE}/{API_MANIFEST_FILE}"
API_MANIFEST_URL_RAW = f"{GH_RAW_BASE}/{API_MANIFEST_FILE}"

# 下面两个字典是**最后的离线兜底**：只有 GitHub 上的清单和程序目录里那份本地
# 清单都读不到时才会用到（见 core/api_manifest.py 的 _builtin_manifest）。
# 平时改 API 地址请改 api_manifest.json，不要动这里。
API_ZIP_MAP = {
    "Windows": "moddingapi.v77.windows.zip",
}

API_QUARK_LINKS = {
    "Windows": "https://pan.quark.cn/s/21185cedf1e2",
}

# ---------- 暗黑极简配色方案 ----------
COLOR_TEXT_PRIMARY = "#FFFFFF"
COLOR_TEXT_SECONDARY = "#B0B0B0"
COLOR_TEXT_TERTIARY = "#6A6A6A"
COLOR_ACCENT_BLUE = "#00BCD4"
COLOR_ACCENT_ORANGE = "#FF9800"
COLOR_ACCENT_RED = "#F44336"
COLOR_INPUT_BG = "#2C2C2C"
COLOR_BORDER = "#424242"


def get_base_dir():
    """获取程序基础目录（打包后或源码运行均适用）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))
