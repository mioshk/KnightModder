# -*- coding: utf-8 -*-
"""
KnightModder 启动诊断 v3.1（临时，定位后删除）
用法（在测试机，【务必用命令行运行，不要双击】）：
  cd <KnightModder 所在目录>
  python diag_game_launch.py

保持脚本运行 → 另开窗口用 KnightModder 点「启动游戏」
→ 等游戏弹窗/闪退后，回到脚本窗口按 Ctrl+C 停止
→ 把生成的 diag_log.txt 内容发给开发者

v3.1 修复：
  - 不再使用 wintypes.WNDENUMPROC（部分 Python 版本没有该属性，导致启动即闪退）
  - user32 相关初始化全部改为函数内懒加载，任何错误都不会在进入主循环前崩溃
  - 全局异常捕获 + 启动即写文件，出错也能看到原因
  - 进程路径查询只针对含 hollow/knight/unity 关键词的进程
纯标准库，无需安装任何依赖。
"""
import sys
import os
import time
import subprocess
import traceback
import ctypes
from ctypes import wintypes

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "diag_log.txt")

lines = []


def safe_print(s):
    try:
        print(s, flush=True)
    except Exception:
        try:
            print(s.encode("ascii", "replace").decode("ascii"), flush=True)
        except Exception:
            pass


def log(line):
    lines.append(line)
    safe_print(line)


def flush_file():
    try:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass


def ts():
    return time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"


# ==================== Mutex 探测（Local + Global） ====================
def get_mutex_candidates():
    products = ["Hollow Knight", "HollowKnight", "Hollow_Knight", "hollowknight"]
    companies = ["Team Cherry", "TeamCherry", "Team_Cherry", "teamcherry"]
    names = []
    for scope in ("Local", "Global"):
        for p in products:
            for c in companies:
                n = f"{scope}\\Unity_{p}_{c}"
                if n not in names:
                    names.append(n)
    return names


def probe_mutex(candidates):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    OpenMutexW = kernel32.OpenMutexW
    OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    OpenMutexW.restype = wintypes.HANDLE
    CloseHandle = kernel32.CloseHandle
    SYNCHRONIZE = 0x00100000
    held = []
    for name in candidates:
        try:
            h = OpenMutexW(SYNCHRONIZE, False, name)
            if h:
                CloseHandle(h)
                held.append(name)
        except Exception:
            pass
    return held


# ==================== 全量进程枚举 ====================
SELF_NOISE = {"tasklist.exe", "conhost.exe", "powershell.exe"}


def all_procs():
    procs = {}
    try:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in out.stdout.splitlines():
            parts = [p.strip('" ') for p in line.strip().split('","')]
            if len(parts) >= 2 and parts[1].isdigit():
                name = parts[0].lower()
                if name not in SELF_NOISE:
                    procs[int(parts[1])] = parts[0]
    except Exception:
        pass
    return procs


def proc_path(pid):
    """只对含关键词的进程查询完整路径；任何失败都不影响主循环。"""
    try:
        ps = (f"$p = Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' "
              f"-ErrorAction SilentlyContinue; if ($p) {{ $p.ExecutablePath }}")
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return (out.stdout or "").strip()
    except Exception:
        return ""


# ==================== 可见窗口枚举（懒加载） ====================
def visible_windows():
    """枚举可见窗口 -> {pid: 标题}。任何错误返回空 dict，绝不影响主循环。"""
    result = {}
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        EnumWindows = user32.EnumWindows
        EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
        EnumWindows.restype = wintypes.BOOL

        GetWindowThreadProcessId = user32.GetWindowThreadProcessId
        GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        GetWindowThreadProcessId.restype = wintypes.DWORD

        GetWindowTextW = user32.GetWindowTextW
        GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        GetWindowTextW.restype = ctypes.c_int

        IsWindowVisible = user32.IsWindowVisible
        IsWindowVisible.argtypes = [wintypes.HWND]
        IsWindowVisible.restype = wintypes.BOOL

        @WNDENUMPROC
        def cb(hwnd, lparam):
            try:
                if IsWindowVisible(hwnd):
                    pid = wintypes.DWORD()
                    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    buf = ctypes.create_unicode_buffer(256)
                    n = GetWindowTextW(hwnd, buf, 256)
                    if n > 0:
                        result.setdefault(pid.value, buf.value)
            except Exception:
                pass
            return True

        EnumWindows(cb, 0)
    except Exception:
        pass
    return result


# ==================== 主循环 ====================
def run():
    cands = get_mutex_candidates()
    log(f"=== 诊断开始 {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    log(f"Mutex 候选 {len(cands)} 个 (Local + Global)")
    flush_file()

    prev_procs = all_procs()
    prev_mutex = probe_mutex(cands)
    prev_wins = visible_windows()
    log(f"监控起点：已有进程 {len(prev_procs)} 个，可见窗口 {len(prev_wins)} 个")
    log("现在请另开窗口，用 KnightModder 点「启动游戏」。游戏弹窗/闪退后回来按 Ctrl+C。")
    flush_file()

    while True:
        t = ts()
        cur = all_procs()
        mutex = probe_mutex(cands)
        wins = visible_windows()

        new_ids = set(cur) - set(prev_procs)
        for pid in sorted(new_ids):
            name = cur[pid]
            low = name.lower()
            p = proc_path(pid) if any(k in low for k in ("hollow", "knight", "unity")) else ""
            log(f"[{t}] +进程 {pid} {name}" + (f" | {p}" if p else ""))

        gone_ids = set(prev_procs) - set(cur)
        for pid in sorted(gone_ids):
            log(f"[{t}] -进程 {pid} {prev_procs[pid]}")

        if set(mutex) != set(prev_mutex):
            if mutex:
                log(f"[{t}] 锁被占用: {mutex}")
            else:
                log(f"[{t}] 锁已释放")

        new_wins = {k: v for k, v in wins.items()
                    if k not in prev_wins and v.strip()}
        for pid, title in sorted(new_wins.items()):
            low = title.lower()
            if any(k in low for k in ("hollow", "knight", "another",
                                      "instance", "unity", "error",
                                      "fatal", "crash", "steam")):
                log(f"[{t}] 新窗口 PID={pid} 标题=\"{title}\"")

        flush_file()
        prev_procs, prev_mutex, prev_wins = cur, mutex, wins
        time.sleep(0.3)


def main():
    try:
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        run()
    except KeyboardInterrupt:
        pass
    except Exception:
        log("!! 脚本异常，请把本文件内容发给开发者:")
        for l in traceback.format_exc().splitlines():
            log("   " + l)
    finally:
        log(f"=== 诊断结束 {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
        flush_file()
        safe_print(f"\n已保存到 {OUT}（请把该文件内容发给开发者）")


if __name__ == "__main__":
    main()
