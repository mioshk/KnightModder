# -*- coding: utf-8 -*-
"""一键构建「安装版」。

    python build_installer.py

产出：
    dist/KnightModder v<版本> 安装版.exe     <-- 分发给用户这一个文件

流程：
    1) 用 KM_ONEDIR=1 跑 main.spec，得到主程序目录 dist/KnightModder/
       （里面的 exe 固定叫 KnightModder.exe，不带版本号）
    2) 把该目录压成 build/payload.zip
    3) 用 installer.spec 把 installer.py + payload.zip 打成一个单文件安装器

分发的仍是单个 exe；用户装完后程序从本地目录启动，不再每次解压 305 MB。
"""
import os
import sys
import time
import shutil
import tarfile
import lzma
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# Windows 的标准输出默认是本地代码页（GitHub Actions 的 runner 是 cp1252），
# 而下面全是中文进度提示——直接 print 会抛 UnicodeEncodeError 把整个构建搞挂。
# 所以在打印任何东西之前，先把 stdout / stderr 切成 UTF-8。
# （子进程那边由 run() 里的 PYTHONIOENCODING 兜底，这里只管本进程。）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 极少数环境下 stdout 被替换过，切不了就算了
        pass

import config  # noqa: E402

VER = getattr(config, "APP_VERSION", "1.0.0")
# 目录名不带版本号：这里只是构建中间产物，最终装到用户机器上的 exe 固定叫
# KnightModder.exe（见 main.spec 的 EXE_NAME）——带版本的话每次升级文件名都变，
# 用户上次安装建好的快捷方式就会指向不存在的旧 exe。
PROGRAM_DIR = os.path.join(ROOT, "dist", "KnightModder")
# 用 tar.xz 而不是 zip：solid 压缩能跨文件消除重复模式（几百个 Qt DLL 之间
# 有大量相似段），同样算法下比逐文件压缩小得多。实测 zip(deflate) 压出 128 MB，
# tar.xz(preset=1) 能压到 90 MB 上下，用户下载量直接少三成。
PAYLOAD = os.path.join(ROOT, "build", "payload.tar.xz")
VERSION_TXT = os.path.join(ROOT, "build", "version.txt")
BUILD_DIR = os.path.join(ROOT, "build")


def step(msg):
    print(f"\n{'='*60}\n{msg}\n{'='*60}", flush=True)


def run(cmd, env=None):
    print("$", " ".join(cmd), flush=True)
    env = dict(os.environ if env is None else env)
    # PyInstaller 的输出含中文，子进程按 gbk 解码会抛 UnicodeDecodeError
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    t = time.time()
    r = subprocess.run(cmd, cwd=ROOT, env=env)
    print(f"  用时 {time.time()-t:.1f}s, 退出码 {r.returncode}", flush=True)
    if r.returncode != 0:
        sys.exit(r.returncode)


def build_program_dir():
    step(f"1/3 构建主程序目录（onedir）: {PROGRAM_DIR}")
    if os.path.isdir(PROGRAM_DIR):
        shutil.rmtree(PROGRAM_DIR, ignore_errors=True)
    env = dict(os.environ)
    env["KM_ONEDIR"] = "1"
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "main.spec"], env=env)
    if not os.path.isdir(PROGRAM_DIR):
        print("未找到构建产物目录：", PROGRAM_DIR)
        sys.exit(1)


def make_payload():
    step(f"2/3 压缩成载荷: {PAYLOAD}")
    os.makedirs(BUILD_DIR, exist_ok=True)
    if os.path.isfile(PAYLOAD):
        os.remove(PAYLOAD)

    t = time.time()
    files = 0
    raw = 0
    # Python 3.10 的 tarfile 不接受 compresslevel，手动套一层 lzma 才能指定 preset
    with lzma.open(PAYLOAD, "wb", preset=1) as fobj:
        with tarfile.open(fileobj=fobj, mode="w") as tf:
            for root, _dirs, names in os.walk(PROGRAM_DIR):
                for n in names:
                    full = os.path.join(root, n)
                    raw += os.path.getsize(full)
                    tf.add(full, arcname=os.path.relpath(full, PROGRAM_DIR),
                           recursive=False)
                    files += 1
    size = os.path.getsize(PAYLOAD)
    print(f"  {files} 个文件, {raw/1024/1024:.1f} MB -> {size/1024/1024:.1f} MB "
          f"(压缩率 {size/raw*100:.0f}%), 用时 {time.time()-t:.1f}s", flush=True)

    with open(VERSION_TXT, "w", encoding="utf-8") as f:
        f.write(VER)


def build_installer():
    step("3/3 打包单文件安装器")
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "installer.spec"])
    out = os.path.join(ROOT, "dist", f"KnightModder v{VER} 安装版.exe")
    if os.path.isfile(out):
        print(f"\n完成：{out}  ({os.path.getsize(out)/1024/1024:.1f} MB)")
    else:
        print("\n未找到安装器产物")


if __name__ == "__main__":
    t0 = time.time()
    build_program_dir()
    make_payload()
    build_installer()
    print(f"\n全部完成，总用时 {time.time()-t0:.1f}s")
