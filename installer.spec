# -*- mode: python ; coding: utf-8 -*-
"""安装器打包配置（安装版分发用）。

与 main.spec 的分工：
    main.spec      -> 主程序本体
    installer.spec -> 把「主程序目录」塞进一个单文件安装器，用户双击后一次性
                      释放到 %LOCALAPPDATA%\\Programs\\KnightModder，之后每次
                      都从那里直接启动（省掉 onefile 的解压环节）。

构建流程见 build_installer.py，不要直接跑这个 spec（payload.zip 得先生成）。
"""
import os
import sys

sys.path.insert(0, SPECPATH)

import config  # noqa: E402

_ver_str = getattr(config, 'APP_VERSION', '1.0.0')
_ver_parts = [int(x) for x in _ver_str.split('.') if str(x).strip().isdigit()]
while len(_ver_parts) < 4:
    _ver_parts.append(0)
_filevers = tuple(_ver_parts[:4])

APP_NAME = 'KnightModder'
EXE_NAME = f'{APP_NAME} v{_ver_str} 安装版'

ICON_PATH = os.path.join(SPECPATH, 'assets', 'icon.ico')
_VERSION_INFO = os.path.join(SPECPATH, 'build', 'file_version_info.txt')

a = Analysis(
    ['installer.py'],
    pathex=[],
    binaries=[],
    datas=[('build/payload.tar.xz', '.'), ('build/version.txt', '.'),
           ('assets/icon.ico', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6', 'numpy', 'scipy', 'pandas', 'PIL', 'requests', 'psutil'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # 无控制台：安装器是图形向导，进度条已经在窗口里显示了，
    # 再跟一个黑乎乎的 cmd 窗口既难看又容易让用户以为出错。
    # （命令行模式的 print 在 windowed 下会静默丢弃，不会报错）
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH,
    version=_VERSION_INFO,
)
