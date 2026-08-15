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
    STEAM_APPID,
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


def get_asset_path(*names):
    """获取 assets 资源路径（兼容 PyInstaller 打包与源码运行）"""
    base = getattr(sys, "_MEIPASS", None) or get_base_dir()
    return os.path.join(base, "assets", *names)


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
# Steam 库定位工具（区分官方版与自定义副本）
# ============================================================
def get_steam_app_install_dir(appid=STEAM_APPID):
    """
    返回 Steam 库中指定 AppID 的官方安装目录（跨所有 Steam 库查找）。

    通过注册表定位 Steam 根目录，解析 libraryfolders.vdf 获取全部库路径，
    再读取 appmanifest_<appid>.acf 中的 installdir 拼出实际安装位置。
    找不到返回 None。
    """
    import re
    import winreg

    # 1. 定位 Steam 根目录（注册表优先，常见默认路径兜底）
    steam_root = None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam") as key:
            steam_root = winreg.QueryValueEx(key, "SteamPath")[0]
    except Exception:
        pass
    if not steam_root or not os.path.isdir(steam_root):
        pf86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        pf = os.environ.get("ProgramFiles", "C:\\Program Files")
        for cand in [os.path.join(pf86, "Steam"), os.path.join(pf, "Steam")]:
            if os.path.isdir(cand):
                steam_root = cand
                break
    if not steam_root or not os.path.isdir(steam_root):
        return None

    # 2. 收集所有 Steam 库路径（首个库即 Steam 根目录自身）
    libraries = [steam_root]
    vdf = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
    if os.path.isfile(vdf):
        try:
            with open(vdf, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            for m in re.finditer(r'"path"\s*"([^"]+)"', content):
                lib = m.group(1).replace("\\\\", "\\")
                if os.path.isdir(lib) and os.path.normcase(lib) not in [
                    os.path.normcase(x) for x in libraries
                ]:
                    libraries.append(lib)
        except Exception:
            pass

    # 3. 逐库查 appmanifest_<appid>.acf 的 installdir，拼出官方安装目录
    manifest_name = f"appmanifest_{appid}.acf"
    for lib in libraries:
        manifest = os.path.join(lib, "steamapps", manifest_name)
        if not os.path.isfile(manifest):
            continue
        try:
            with open(manifest, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            m = re.search(r'"installdir"\s*"([^"]+)"', content)
            if m:
                install_dir = m.group(1).replace("\\\\", "\\")
                full = os.path.join(lib, "steamapps", "common", install_dir)
                if os.path.isdir(full):
                    return normalize_path(full)
        except Exception:
            continue
    return None


def is_steam_official_path(game_path, appid=STEAM_APPID):
    """
    判断用户选择的游戏目录是否为 Steam 官方安装目录
    （与 Steam 库为 AppID 注册的安装位置一致）。

    只有官方目录才应通过 steam:// 启动——自定义副本（哪怕放在
    steamapps\\common 下）必须直启用户指定的 exe，否则 steam://
    会无视选择、永远启动 Steam 库里的官方版。
    """
    real = get_steam_app_install_dir(appid)
    if not real:
        return False
    return os.path.normcase(normalize_path(game_path)) == os.path.normcase(real)


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
            # 跳过不存在的盘符（光驱、未挂载盘会导致 isdir 极慢）
            if not os.path.exists(d + ":\\"):
                continue
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
            if not os.path.exists(d + ":\\"):
                continue
            gog_paths.append(normalize_path(os.path.join(d, "GOG Games", "Hollow Knight")))
            gog_paths.append(normalize_path(os.path.join(d, "GOG Galaxy", "Games", "Hollow Knight")))

        for gp in gog_paths:
            if os.path.isdir(gp):
                exe = os.path.join(gp, "hollow_knight.exe")
                if os.path.isfile(exe):
                    results.append((exe, normalize_path(gp)))

        # 去重（Windows 路径大小写不敏感）
        seen = set()
        unique_results = []
        for exe, path in results:
            key = os.path.normcase(path)
            if key not in seen:
                seen.add(key)
                unique_results.append((exe, path))
        results = unique_results

    return results


# ============================================================
# 网络请求工具（SSL 降级兼容）
# ============================================================
def safe_requests_get(url, timeout=10, fallback_on_ssl=True, ssl_warn_callback=None, **kwargs):
    """
    带 SSL 证书验证失败自动降级的 requests.get 包装。
    个别精简/老版本 Windows 系统可能出现根证书缺失，导致证书验证失败。
    此函数在首次验证失败时自动使用 verify=False 重试一次。
    """
    import requests
    try:
        return requests.get(url, timeout=timeout, **kwargs)
    except requests.exceptions.SSLError:
        if not fallback_on_ssl:
            raise
        if ssl_warn_callback:
            ssl_warn_callback("⚠️ 检测到 SSL 证书验证失败，正在尝试跳过证书验证继续下载...")
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        return requests.get(url, timeout=timeout, verify=False, **kwargs)


# ============================================================
# Unity 单实例 Mutex 探测（Hollow Knight 单实例机制）
# ============================================================
def get_unity_mutex_candidates():
    """
    生成 Hollow Knight 单实例 Mutex 的候选名称。

    Unity 单实例机制：创建命名 Mutex（格式 Local\\Unity_<Product>_<Company>），
    游戏启动时若检测到同名 Mutex 已存在，即弹 "another instance is already running" 并退出。
    HK 由 Team Cherry 开发，存档目录为 <User>\\AppData\\LocalLow\\Team Cherry\\Hollow Knight，
    因此 Product/Company 存在含空格与不含空格多种写法，这里全部生成以便探测。
    """
    products = ["Hollow Knight", "HollowKnight", "Hollow_Knight", "hollowknight"]
    companies = ["Team Cherry", "TeamCherry", "Team_Cherry", "teamcherry"]
    names = []
    for p in products:
        for c in companies:
            n = f"Local\\Unity_{p}_{c}"
            if n not in names:
                names.append(n)
    return names


def is_unity_mutex_held(candidates=None):
    """
    用 OpenMutexW 探测 Unity 单实例 Mutex 是否被占用。

    与 CreateMutexW 不同，OpenMutexW 只查询、不创建，零副作用：
    - 不会占用/创建 mutex，绝不影响游戏启动
    - 能发现"没有可见进程但锁被占用"的隐藏/挂起/残留实例
      （例如被杀软挂起、其他会话残留、其他 Mod 工具持有的同名锁）
    返回被占用 mutex 的名称，无占用返回 None。
    """
    import ctypes
    from ctypes import wintypes

    if candidates is None:
        candidates = get_unity_mutex_candidates()

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        OpenMutexW = kernel32.OpenMutexW
        OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        OpenMutexW.restype = wintypes.HANDLE
        CloseHandle = kernel32.CloseHandle

        SYNCHRONIZE = 0x00100000  # 只需同步权限即可探测存在性
        for name in candidates:
            try:
                h = OpenMutexW(SYNCHRONIZE, False, name)
                if h:
                    CloseHandle(h)
                    return name
            except Exception:
                continue
    except Exception:
        pass
    return None
