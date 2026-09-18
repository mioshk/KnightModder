# -*- coding: utf-8 -*-
"""Modding API 安装清单（api_manifest.json）的读取与兜底。

为什么要有这个东西：
    以前 API 的压缩包文件名和下载链接是写死在 config.py 里的，API 一换版本、
    或者网盘链接失效，就只能改代码 → 重新打包 → 重新发版，用户还得升级软件。
    现在清单放在仓库根目录的 api_manifest.json，作者改完往 GitHub 一推，所有
    已安装的软件下次装 API 时就会自动读到新清单。

读取顺序（逐级兜底，任何一级出问题都不会让"安装 API"整体失败）：
    ① GitHub 上的清单（jsDelivr CDN 优先、raw 兜底，见 fetch_remote_content）
    ② 程序目录里的 api_manifest.json（打包时随程序带的那份）
    ③ config.py 里的 API_ZIP_MAP / API_QUARK_LINKS（最后保底）
"""
import json
import os

from config import (
    API_MANIFEST_FILE,
    API_MANIFEST_URL_CDN,
    API_MANIFEST_URL_RAW,
    API_QUARK_LINKS,
    API_ZIP_MAP,
)
from utils.common import fetch_remote_content, get_base_dir


class ApiPackage:
    """某个平台的 API 安装包描述"""

    def __init__(self, system, file_name, quark_links=None, direct_links=None,
                 sha256="", size=0):
        self.system = system
        self.file_name = file_name
        self.quark_links = [str(x).strip() for x in (quark_links or []) if str(x).strip()]
        self.direct_links = [str(x).strip() for x in (direct_links or []) if str(x).strip()]
        self.sha256 = str(sha256 or "").strip().lower()
        try:
            self.size = int(size or 0)
        except (TypeError, ValueError):
            self.size = 0

    @property
    def all_links(self):
        """候选链接顺序：直链优先（不用登录夸克、也不用转存），网盘兜后"""
        return list(self.direct_links) + list(self.quark_links)

    def __repr__(self):  # 便于日志/调试
        return f"<ApiPackage {self.system} {self.file_name} links={len(self.all_links)}>"


def _local_manifest_path():
    """程序自带的那份清单（源码运行 = 项目根目录；打包后 = exe 同目录）"""
    return os.path.join(get_base_dir(), API_MANIFEST_FILE)


def _builtin_manifest():
    """config.py 里的硬编码值，网络与本地文件都不可用时的最后保底"""
    packages = {}
    for system, zip_name in API_ZIP_MAP.items():
        link = API_QUARK_LINKS.get(system)
        packages[system] = {
            "file": zip_name,
            "quark_links": [link] if link else [],
            "direct_links": [],
        }
    return {"version": 0, "packages": packages}


def _parse(raw, source):
    """把清单 JSON 解析成 {平台: ApiPackage}，并记下它来自哪一级"""
    packages = {}
    for system, item in (raw.get("packages") or {}).items():
        if not isinstance(item, dict):
            continue
        file_name = str(item.get("file") or "").strip()
        if not file_name:
            continue
        # 兼容单数写法：清单里写 quark / url 也能认
        quark = item.get("quark_links")
        if quark is None and item.get("quark"):
            quark = [item["quark"]]
        direct = item.get("direct_links")
        if direct is None and item.get("url"):
            direct = [item["url"]]
        packages[system] = ApiPackage(
            system=system,
            file_name=file_name,
            quark_links=quark or [],
            direct_links=direct or [],
            sha256=item.get("sha256", ""),
            size=item.get("size", 0),
        )
    return {
        "source": source,
        "version": raw.get("version", 0),
        "updated": raw.get("updated", ""),
        "packages": packages,
    }


def load_manifest(status_callback=None, timeout=10):
    """读取 API 清单，返回 {"source", "version", "updated", "packages"}。

    packages 形如 {"Windows": ApiPackage, ...}；三级都拿不到时 packages 可能为空。
    """
    def _log(msg, level="info"):
        if status_callback:
            try:
                status_callback(msg, level)
            except Exception:
                pass

    # ① GitHub 上的清单（CDN 加速优先，raw 兜底）
    try:
        content, src = fetch_remote_content(API_MANIFEST_URL_CDN,
                                            API_MANIFEST_URL_RAW,
                                            timeout=timeout)
        if content:
            parsed = _parse(json.loads(content.decode("utf-8", "replace")),
                            f"github:{src}")
            if parsed["packages"]:
                _log(f"已读取线上 API 清单（{src}），版本 {parsed['version']}", "info")
                return parsed
            _log("线上 API 清单里没有可用的安装包，改用本地清单", "warn")
        else:
            _log("未能读取线上 API 清单，改用本地清单", "warn")
    except Exception as e:  # noqa: BLE001 清单坏了也要能继续装 API
        _log(f"线上 API 清单解析失败（{e}），改用本地清单", "warn")

    # ② 程序目录里的清单
    try:
        path = _local_manifest_path()
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                parsed = _parse(json.load(f), "local")
            if parsed["packages"]:
                _log("已使用程序自带的 API 清单", "info")
                return parsed
    except Exception as e:  # noqa: BLE001
        _log(f"本地 API 清单读取失败（{e}）", "warn")

    # ③ config.py 内置
    _log("使用内置 API 配置（兜底）", "warn")
    return _parse(_builtin_manifest(), "builtin")


def get_package(system, status_callback=None):
    """取指定平台的 ApiPackage；清单里没有则返回 None"""
    return load_manifest(status_callback=status_callback)["packages"].get(system)
