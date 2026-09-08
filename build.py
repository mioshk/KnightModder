#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跨平台 PyInstaller 构建脚本（Windows / macOS / Linux 通用）。

用法：
    pip install -r requirements.txt pyinstaller
    python build.py

输出：
    - Windows : dist/KnightModder.exe
    - macOS   : dist/KnightModder.app
    - Linux   : dist/KnightModder
"""
import os
import sys
import subprocess

APP_NAME = "KnightModder"
ENTRY = "main.py"
ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(ROOT, "assets")

# 夸克登录用到 QWebEngineView，需要把 QtWebEngine 相关子模块显式收集进包，
# 否则打包后运行会报 QtWebEngineProcess / 资源文件找不到。
HIDDEN_IMPORTS = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
]

DATA_SEP = ";" if sys.platform == "win32" else ":"


def main():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        f"--name={APP_NAME}",
        "--onefile",
        "--windowed",
        "--noconfirm",
    ]
    for imp in HIDDEN_IMPORTS:
        cmd.append(f"--hidden-import={imp}")
    # 收集 QtWebEngine 运行所需的二进制与资源（进程助手、翻译、资源等）
    cmd += ["--collect-submodules", "PySide6.QtWebEngineCore"]
    if os.path.isdir(ASSETS):
        cmd.append(f"--add-data={ASSETS}{DATA_SEP}assets")
    # macOS：指定 bundle identifier 与 entitlements，让 PyInstaller 在打包时以
    # 标准方式签名（QtWebEngine 需要 JIT / 可执行内存等 entitlement 才能运行）
    if sys.platform == "darwin":
        cmd += ["--osx-bundle-identifier", "com.mioss.knightmodder"]
        entitlements = os.path.join(ROOT, "entitlements.plist")
        if os.path.isfile(entitlements):
            cmd += ["--osx-entitlements-file", entitlements]
    cmd.append(ENTRY)

    print(">>> " + " ".join(cmd))
    subprocess.check_call(cmd)


if __name__ == "__main__":
    main()
