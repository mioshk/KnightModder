# -*- coding: utf-8 -*-
"""
安装器核心模块
包含API安装、原版还原、Mod安装、游戏启动、模组启用/禁用/删除、依赖解析等功能
"""
import os
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

from config import MANAGED_RELATIVE_PATH, MODS_RELATIVE_PATH, MODLINKS_URL, MODLINKS_BACKUP_URL, get_base_dir
from utils.common import get_api_zip_path, get_api_folder_path, get_game_exe_path, get_mods_dir, safe_requests_get


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
    if mod_name in metadata:
        return metadata[mod_name].get("version")
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


# ==================== API 安装与还原 ====================

def install_api(game_path, progress_callback=None):
    """
    安装Modding API到游戏目录
    :param game_path: 游戏根目录
    :param progress_callback: 进度回调函数
    """
    managed = os.path.join(game_path, MANAGED_RELATIVE_PATH)
    if not os.path.isdir(managed):
        if progress_callback:
            progress_callback("❌ 未找到 Managed 文件夹", "error")
        raise NotADirectoryError(f"未找到 Managed：{managed}")

    zp = get_api_zip_path()
    if not os.path.isfile(zp):
        if progress_callback:
            progress_callback("❌ API 压缩包不存在", "error")
        raise FileNotFoundError(f"API 压缩包不存在：{zp}")

    # 静默解压，不打日志
    with zipfile.ZipFile(zp, 'r') as zf:
        zf.extractall(managed)

    if progress_callback:
        progress_callback("✅ API 安装完成！", "success")


def restore_vanilla(game_path, progress_callback=None):
    """
    还原原版游戏（移除API，保留Mods文件夹）
    :param game_path: 游戏根目录
    :param progress_callback: 进度回调函数
    """
    managed = os.path.join(game_path, MANAGED_RELATIVE_PATH)
    orig = os.path.join(managed, "Assembly-CSharp.dll")

    api_folder = get_api_folder_path()
    api_dll_path = os.path.join(api_folder, "Assembly-CSharp.dll")

    if not os.path.isfile(api_dll_path):
        if progress_callback:
            progress_callback("❌ API 文件夹中未找到 Assembly-CSharp.dll", "error")
        raise FileNotFoundError(f"API 文件夹中未找到 Assembly-CSharp.dll：{api_dll_path}")

    # 静默复制，不打"正在还原"日志
    shutil.copy2(api_dll_path, orig)

    if progress_callback:
        progress_callback("✅ 已还原原版 dll", "success")


# ==================== Mod 安装 ====================

def install_mods(game_path, file_paths, progress_callback=None):
    """
    安装Mod文件（支持zip和dll）
    :param game_path: 游戏根目录
    :param file_paths: Mod文件路径列表
    :param progress_callback: 进度回调函数
    """
    mods_dir = os.path.join(game_path, MODS_RELATIVE_PATH)
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
    exe_path = get_game_exe_path(game_path)
    if not exe_path:
        if progress_callback:
            progress_callback("❌ 未找到 hollow_knight.exe", "error")
        raise FileNotFoundError(f"未找到 hollow_knight.exe：{game_path}")

    try:
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
        从URL加载Mod依赖数据（多源容灾：主源失败自动回退备用源）
        :param url: Mod列表XML地址，默认使用 config.MODLINKS_URL
        :param progress_callback: 进度回调函数
        :return: 是否加载成功
        """
        import requests  # 延迟导入，避免拖慢启动

        # 主备地址去重
        urls = [url or MODLINKS_URL]
        if MODLINKS_BACKUP_URL and MODLINKS_BACKUP_URL not in urls:
            urls.append(MODLINKS_BACKUP_URL)

        last_err = None
        for i, u in enumerate(urls):
            label = "主源" if i == 0 else "备用源"
            try:
                if progress_callback:
                    progress_callback(f"🔍 正在从{label}加载 Mod 链接...", "info")

                response = safe_requests_get(
                    u, timeout=15,
                    ssl_warn_callback=lambda msg: progress_callback(msg, "warning") if progress_callback else None
                )
                response.raise_for_status()

                if progress_callback:
                    progress_callback("📥 正在解析 Mod 数据...", "info")

                if self._parse_xml_content(response.content, progress_callback):
                    # 解析成功后才写入本地缓存，避免坏数据覆盖缓存
                    self.save_cache(response.content)
                    return True
                last_err = "数据解析失败"
            except requests.exceptions.RequestException as e:
                last_err = str(e)
            except Exception as e:
                last_err = str(e)
            if progress_callback:
                progress_callback(f"⚠️ {label}拉取失败：{last_err}，正在尝试其他源...", "warning")

        if progress_callback:
            progress_callback(f"❌ 所有源均拉取失败：{last_err}", "error")
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
