# -*- coding: utf-8 -*-
"""KnightModder 安装器（安装版分发用）。

为什么要这个东西：
    单文件(onefile)版每次启动都要把整个 bundle 解压到 %TEMP%，冷启动因此要
    3~4 秒。改成安装版后，程序被一次性释放到安装目录，之后每次都从那里直接
    加载，省掉解压环节，冷启动降到 1.5 秒上下。分发形态仍然是单个 exe。

交互方式：
    默认：图形安装向导（可选安装位置、可选是否建桌面快捷方式/装完启动）
    命令行：
        installer.exe                      图形向导
        installer.exe --dir <路径>          直接装到指定位置，不弹窗
        installer.exe --silent              静默装到默认位置（不启动）
        installer.exe --no-launch           图形/直装时都不自动启动程序

安装做了什么：
    1) 把内置的 payload.tar.xz（程序目录）释放到用户选择的位置；
    2) 升级时只替换程序文件（_internal 与 *.exe），保留 config.json（夸克 Cookie
       与游戏路径）和 downloads/（已下载的 Mod 包）；
    3) 写一份 uninstall.cmd，并在「应用和功能」里注册卸载项；
    4) 按用户勾选创建开始菜单 / 桌面快捷方式；
    5) 装完按勾选启动程序。
"""
import os
import sys
import stat
import shutil
import tarfile
import threading
import subprocess

APP_NAME = "KnightModder"
PUBLISHER = "KnightModder"

# 升级时必须保留的用户数据（装新版不能把配置/已下载的包冲掉）
KEEP_NAMES = {"config.json", "downloads", "crash.log"}

# 安装后大致占用的磁盘空间（用于空间检查，放宽一些）
_ESTIMATED_BYTES = 130 * 1024 * 1024


def resource_path(name):
    """取随包发布的文件（onefile 下在 sys._MEIPASS）"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def read_version():
    try:
        with open(resource_path("version.txt"), "r", encoding="utf-8") as f:
            return f.read().strip() or "0.0.0"
    except Exception:
        return "0.0.0"


def default_install_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Programs", APP_NAME)


def last_install_dir():
    """上次装到哪儿了（读卸载项里的 InstallLocation），没有就返回默认位置。

    这样重装/升级时不用再选一次路径；卸载会顺带删掉这条记录，下次安装
    自然回到默认位置。
    """
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Uninstall\\" + APP_NAME)
        val, _ = winreg.QueryValueEx(key, "InstallLocation")
        winreg.CloseKey(key)
        if val and os.path.isdir(val):
            return os.path.normpath(val)
    except Exception:
        pass
    return default_install_dir()


def _norm(path):
    """统一成 Windows 反斜杠路径。

    tkinter 的 filedialog 返回的是 Tk 风格正斜杠（D:/Games），直接 os.path.join
    会拼出 "D:/Games\\KnightModder" 这种正反斜杠混杂的怪东西，必须在所有入口
    （浏览按钮、命令行 --dir、注册表读回）都规范一遍。
    """
    return os.path.normpath(os.path.abspath(path)) if path else path


def _rmtree(path):
    """删除目录（含只读文件；Windows 上先去掉只读属性）"""
    def _on_error(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    if os.path.isdir(path):
        shutil.rmtree(path, onerror=_on_error)


def clear_old_program(dest):
    """清掉上一版的程序文件，保留用户数据（config.json / downloads）"""
    if not os.path.isdir(dest):
        return
    for name in os.listdir(dest):
        if name in KEEP_NAMES:
            continue
        p = os.path.join(dest, name)
        try:
            if os.path.isdir(p):
                _rmtree(p)
            else:
                os.chmod(p, stat.S_IWRITE)
                os.remove(p)
        except Exception as e:
            print(f"  [跳过] 无法删除 {name}: {e}")


def extract_payload(payload, dest, on_progress=None):
    """释放载荷（tar.xz）。on_progress(百分比:int) 可为空。"""
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(payload, "r:xz") as tf:
        members = tf.getmembers()
        total = max(1, len(members))
        for i, m in enumerate(members, 1):
            target = os.path.realpath(os.path.join(dest, m.name))
            if not target.startswith(os.path.realpath(dest) + os.sep):
                continue
            try:
                tf.extract(m, dest, filter="data")
            except TypeError:
                # Python 3.10 没有 filter 参数（3.12+ 才有），退回直接解压
                tf.extract(m, dest)
            except Exception as e:
                print(f"  [跳过] {m.name}: {e}")
            if on_progress and (i % 10 == 0 or i == total):
                on_progress(int(i * 100 / total))


def find_exe(dest):
    """在安装目录里找到主程序 exe"""
    for name in os.listdir(dest):
        if name.lower().endswith(".exe") and APP_NAME.lower() in name.lower():
            return os.path.join(dest, name)
    for name in os.listdir(dest):
        if name.lower().endswith(".exe") and name.lower() != "uninstall.cmd":
            return os.path.join(dest, name)
    return None


def write_uninstall_cmd(dest):
    """生成卸载脚本：删安装目录 + 删快捷方式 + 删注册表项"""
    start_menu = os.path.join(
        os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    script = f"""@echo off
chcp 65001 >nul
echo 正在卸载 {APP_NAME}...
taskkill /F /IM "{APP_NAME}*.exe" >nul 2>&1
timeout /t 1 /nobreak >nul
del /F /Q "{os.path.join(start_menu, APP_NAME + '.lnk')}" >nul 2>&1
del /F /Q "{os.path.join(desktop, APP_NAME + '.lnk')}" >nul 2>&1
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" /f >nul 2>&1
rd /S /Q "{dest}" >nul 2>&1
echo 卸载完成。
pause
"""
    path = os.path.join(dest, "uninstall.cmd")
    with open(path, "w", encoding="utf-8") as f:
        f.write(script)
    return path


def register_uninstall(dest, version, uninstall_cmd):
    try:
        import winreg
        key = winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Uninstall\\" + APP_NAME)
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, f"{APP_NAME} {version}")
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, version)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, PUBLISHER)
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, dest)
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ,
                          f'cmd /c "{uninstall_cmd}"')
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"  [警告] 注册卸载项失败：{e}")
        return False


def create_shortcut(target, working_dir, lnk_path, icon_path=None):
    """用 PowerShell + WScript.Shell 创建 .lnk（无需第三方库）"""
    try:
        os.makedirs(os.path.dirname(lnk_path), exist_ok=True)
    except Exception:
        pass
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{lnk_path}'); "
        f"$s.TargetPath = '{target}'; "
        f"$s.WorkingDirectory = '{working_dir}'; "
        f"$s.Description = '{APP_NAME}'; "
    )
    if icon_path:
        ps += f"$s.IconLocation = '{icon_path},0'; "
    ps += "$s.Save()"
    try:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-Command", ps],
                       check=True, capture_output=True, timeout=30,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return os.path.isfile(lnk_path)
    except Exception as e:
        print(f"  [警告] 创建快捷方式失败 {lnk_path}: {e}")
        return False


def maybe_import_config(dest):
    """把旧配置带过去：安装器所在目录里若有 config.json（例如用户把安装器放在
    绿色版旁边双击运行），就复制到安装目录，省得重装后重新选游戏路径 + 登录夸克。
    已存在配置时不覆盖。"""
    target = os.path.join(dest, "config.json")
    if os.path.isfile(target):
        return None
    candidates = [
        os.path.dirname(os.path.abspath(sys.argv[0])),
        os.path.dirname(sys.executable),
        os.getcwd(),
    ]
    for cand in candidates:
        src = os.path.join(cand, "config.json")
        if os.path.isfile(src):
            try:
                shutil.copy2(src, target)
                return src
            except Exception as e:
                print(f"  [警告] 复制旧配置失败：{e}")
    return None


def check_dest(dest):
    """检查安装位置是否可用，返回 (是否可用, 提示文字)"""
    if not dest:
        return False, "请选择安装位置。"
    dest = _norm(dest)
    try:
        parent = os.path.dirname(dest.rstrip("\\/")) or dest
        os.makedirs(dest, exist_ok=True)
    except Exception as e:
        return False, f"无法在此位置创建文件夹（可能需要管理员权限）：{e}"
    # 可写性
    try:
        probe = os.path.join(dest, ".km_write_test")
        with open(probe, "w") as f:
            f.write("x")
        os.remove(probe)
    except Exception as e:
        return False, f"没有写入权限（可尝试以管理员身份运行）：{e}"
    # 磁盘空间
    try:
        free = shutil.disk_usage(dest).free
        if free < _ESTIMATED_BYTES:
            return False, (f"磁盘空间不足：需要约 {_ESTIMATED_BYTES//1024//1024} MB，"
                           f"当前可用 {free//1024//1024} MB。")
    except Exception:
        pass
    return True, ""


def do_install(dest, payload, make_desktop=True, make_start_menu=True,
               on_progress=None, on_log=None):
    """执行安装，返回主程序 exe 路径；失败抛异常。"""
    def log(msg):
        if on_log:
            on_log(msg)
        else:
            print(msg)

    ok, why = check_dest(dest)
    if not ok:
        raise RuntimeError(why)

    if os.path.isdir(dest) and find_exe(dest):
        log("检测到已安装，正在更新（保留 config.json 与 downloads/）...")
        clear_old_program(dest)
    else:
        os.makedirs(dest, exist_ok=True)

    log("正在释放程序文件...")
    extract_payload(payload, dest, on_progress=on_progress)

    exe = find_exe(dest)
    if not exe:
        raise RuntimeError("释放后未找到主程序。")

    imported = maybe_import_config(dest)
    if imported:
        log(f"已沿用旧配置：{imported}")

    log("正在创建卸载入口与快捷方式...")
    uninstall_cmd = write_uninstall_cmd(dest)
    register_uninstall(dest, read_version(), uninstall_cmd)

    if make_start_menu:
        start_menu = os.path.join(
            os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")
        create_shortcut(exe, dest, os.path.join(start_menu, APP_NAME + ".lnk"), exe)
    if make_desktop:
        create_shortcut(exe, dest,
                        os.path.join(os.path.expanduser("~"), "Desktop", APP_NAME + ".lnk"),
                        exe)
    return exe


# ============================================================
# 图形安装向导
# ============================================================
def run_gui(version, payload):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    root = tk.Tk()
    root.title(f"{APP_NAME} {version} 安装")
    root.resizable(False, False)
    root.configure(bg="#f5f5f5")

    icon = resource_path("icon.ico")
    if os.path.isfile(icon):
        try:
            root.iconbitmap(icon)
        except Exception:
            pass

    # 窗口居中
    root.update_idletasks()
    w, h = 560, 460
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    # 默认沿用上一次的安装位置（没装过才是 %LOCALAPPDATA%\Programs\...）
    path_var = tk.StringVar(value=last_install_dir())
    notice_var = tk.StringVar(value="")
    desk_var = tk.BooleanVar(value=True)
    menu_var = tk.BooleanVar(value=True)
    launch_var = tk.BooleanVar(value=True)
    status_var = tk.StringVar(value="")
    installing = {"flag": False}

    # ---------- 页面容器 ----------
    container = tk.Frame(root, bg="#f5f5f5")
    container.pack(fill="both", expand=True, padx=24, pady=18)

    page1 = tk.Frame(container, bg="#f5f5f5")
    page2 = tk.Frame(container, bg="#f5f5f5")

    def show(page):
        for p in (page1, page2):
            p.pack_forget()
        page.pack(fill="both", expand=True)

    # ---------- 第一页：位置与选项 ----------
    tk.Label(page1, text=f"安装 {APP_NAME} {version}", bg="#f5f5f5",
             font=("Microsoft YaHei", 15, "bold")).pack(anchor="w")
    tk.Label(page1,
             text="选择安装位置后点「安装」。若该位置已装过本程序，将自动更新，\n"
                  "你的游戏路径、夸克登录信息和已下载的 Mod 包都会保留。",
             bg="#f5f5f5", fg="#555555", font=("Microsoft YaHei", 9),
             justify="left").pack(anchor="w", pady=(6, 14))

    tk.Label(page1, text="安装位置：", bg="#f5f5f5",
             font=("Microsoft YaHei", 10)).pack(anchor="w")
    row = tk.Frame(page1, bg="#f5f5f5")
    row.pack(fill="x", pady=(4, 10))
    entry = tk.Entry(row, textvariable=path_var, font=("Microsoft YaHei", 9))
    entry.pack(side="left", fill="x", expand=True)
    tk.Button(row, text="浏览…", width=8,
              command=lambda: _browse()).pack(side="left", padx=(6, 0))

    def _browse():
        initial = path_var.get() or last_install_dir()
        d = filedialog.askdirectory(parent=root, initialdir=initial,
                                    title="选择安装位置")
        if d:
            # Tk 返回的是正斜杠，先规范化；用户选了父目录时再补上程序名，
            # 避免一堆文件散在所选目录里
            d = _norm(d)
            base = os.path.basename(d)
            path_var.set(d if base == APP_NAME else _norm(os.path.join(d, APP_NAME)))

    opts = tk.Frame(page1, bg="#f5f5f5")
    opts.pack(fill="x", pady=(2, 8))
    tk.Checkbutton(opts, text="创建桌面快捷方式", variable=desk_var,
                   bg="#f5f5f5", font=("Microsoft YaHei", 9),
                   activebackground="#f5f5f5").pack(anchor="w")
    tk.Checkbutton(opts, text="创建开始菜单快捷方式", variable=menu_var,
                   bg="#f5f5f5", font=("Microsoft YaHei", 9),
                   activebackground="#f5f5f5").pack(anchor="w")
    tk.Checkbutton(opts, text="安装完成后启动程序", variable=launch_var,
                   bg="#f5f5f5", font=("Microsoft YaHei", 9),
                   activebackground="#f5f5f5").pack(anchor="w")

    tk.Label(page1, textvariable=notice_var, bg="#f5f5f5", fg="#1565c0",
             font=("Microsoft YaHei", 9), wraplength=500,
             justify="left").pack(anchor="w", pady=(6, 0))
    hint = tk.Label(page1, textvariable=status_var, bg="#f5f5f5", fg="#c62828",
                    font=("Microsoft YaHei", 9), wraplength=500, justify="left")
    hint.pack(anchor="w", pady=(4, 0))

    def _refresh_notice(*_args):
        dest = path_var.get().strip()
        try:
            already = bool(dest) and os.path.isdir(dest) and find_exe(dest)
        except Exception:
            already = False
        notice_var.set("该位置已安装过本程序，将更新并保留你的设置与已下载内容。"
                       if already else "")

    path_var.trace_add("write", _refresh_notice)
    _refresh_notice()

    btns = tk.Frame(page1, bg="#f5f5f5")
    btns.pack(side="bottom", fill="x", pady=(10, 0))
    tk.Button(btns, text="取消", width=10,
              command=root.destroy).pack(side="right")

    def _start():
        if installing["flag"]:
            return
        dest = _norm(path_var.get().strip())
        path_var.set(dest)          # 把规范化后的路径回显给用户
        ok, why = check_dest(dest)
        if not ok:
            status_var.set(why)
            return
        installing["flag"] = True
        install_btn.config(state="disabled")
        show(page2)

        def progress(pct):
            root.after(0, lambda: (bar.config(value=pct),
                                   pct_var.set(f"{pct}%")))

        def log(msg):
            root.after(0, lambda: status_var2.set(msg))

        def worker():
            try:
                exe = do_install(dest, payload, make_desktop=desk_var.get(),
                                 make_start_menu=menu_var.get(),
                                 on_progress=progress, on_log=log)
            except Exception as e:
                root.after(0, lambda: _fail(str(e)))
                return
            root.after(0, lambda: _done(exe))

        threading.Thread(target=worker, daemon=True).start()

    install_btn = tk.Button(btns, text="安装", width=10, command=_start)
    install_btn.pack(side="right", padx=(0, 8))

    # ---------- 第二页：进度 ----------
    pct_var = tk.StringVar(value="0%")
    status_var2 = tk.StringVar(value="正在准备…")
    tk.Label(page2, text="正在安装", bg="#f5f5f5",
             font=("Microsoft YaHei", 13, "bold")).pack(anchor="w", pady=(0, 10))
    bar = ttk.Progressbar(page2, orient="horizontal", length=480,
                          mode="determinate", maximum=100)
    bar.pack(fill="x", pady=(0, 6))
    tk.Label(page2, textvariable=pct_var, bg="#f5f5f5",
             font=("Microsoft YaHei", 9)).pack(anchor="w")
    tk.Label(page2, textvariable=status_var2, bg="#f5f5f5", fg="#555555",
             font=("Microsoft YaHei", 9), wraplength=500,
             justify="left").pack(anchor="w", pady=(6, 0))

    def _done(exe):
        bar.config(value=100)
        pct_var.set("100%")
        status_var2.set(f"安装完成。\n程序位置：{exe}")
        finish_btn = tk.Button(page2, text="完成", width=10,
                               command=lambda: _close(exe))
        finish_btn.pack(side="bottom", pady=(10, 0))
        if launch_var.get():
            try:
                subprocess.Popen([exe], cwd=os.path.dirname(exe))
            except Exception:
                pass

    def _fail(msg):
        status_var2.set(f"安装失败：{msg}")
        tk.Button(page2, text="关闭", width=10,
                  command=root.destroy).pack(side="bottom", pady=(10, 0))

    def _close(_exe):
        root.destroy()

    show(page1)
    root.mainloop()


def main():
    args = sys.argv[1:]
    version = read_version()
    payload = resource_path("payload.tar.xz")
    if not os.path.isfile(payload):
        print("错误：安装包内缺少 payload.tar.xz，安装器中止。")
        return 1

    # 无 GUI 的直装/静默模式（保留给批处理或高级用户）
    if "--dir" in args or "--silent" in args:
        # 没显式指定位置时，静默模式也沿用上一次的安装位置（升级场景）
        dest = last_install_dir()
        if "--dir" in args:
            idx = args.index("--dir")
            if idx + 1 < len(args):
                dest = _norm(os.path.abspath(args[idx + 1]))
        launch = "--no-launch" not in args and "--silent" not in args
        print(f"{APP_NAME} {version} 安装程序 -> {dest}")
        exe = do_install(dest, payload, on_progress=lambda p: print(
            f"\r  释放文件 {p}%", end="", flush=True))
        print(f"\n安装完成：{exe}")
        if launch:
            subprocess.Popen([exe], cwd=os.path.dirname(exe))
        return 0

    run_gui(version, payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
