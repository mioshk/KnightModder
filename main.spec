# -*- mode: python ; coding: utf-8 -*-
import os
import sys

sys.path.insert(0, SPECPATH)

# ---------- 读取版本号（来自 config.py 的 APP_VERSION） ----------
import config
_ver_str = getattr(config, 'APP_VERSION', '1.0.0')

_ver_parts = [int(x) for x in _ver_str.split('.') if str(x).strip().isdigit()]
while len(_ver_parts) < 4:
    _ver_parts.append(0)
_filevers = tuple(_ver_parts[:4])

APP_NAME = 'KnightModder'
EXE_NAME = f'{APP_NAME} v{_ver_str}'

# ---------- 图标：按平台选择（Windows=ico, macOS=icns, Linux 无法内嵌图标） ----------
ICON_PATH = os.path.join(SPECPATH, 'assets', 'icon.ico')
if sys.platform == 'darwin':
    ICON_PATH = os.path.join(SPECPATH, 'assets', 'icon.icns')
elif sys.platform == 'linux':
    ICON_PATH = os.path.join(SPECPATH, 'assets', 'icon.png')

# ---------- 生成 Windows 版本信息资源文件（写入 exe 右键属性的版本信息） ----------
# 仅在 Windows 上生效；macOS/Linux 上 PyInstaller 会忽略 version 参数。
_version_info = f'''# UTF-8
VSVersionInfo(
    ffi=FixedFileInfo(
        filevers={_filevers},
        prodvers={_filevers},
        mask=0x3f,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo([
            StringTable(
                u'040904B0',
                [StringStruct(u'CompanyName', u'{APP_NAME}'),
                 StringStruct(u'FileDescription', u'空洞骑士 Mod 安装器'),
                 StringStruct(u'FileVersion', u'{_ver_str}'),
                 StringStruct(u'InternalName', u'{APP_NAME}'),
                 StringStruct(u'OriginalFilename', u'{EXE_NAME}.exe'),
                 StringStruct(u'ProductName', u'{APP_NAME}'),
                 StringStruct(u'ProductVersion', u'{_ver_str}')],
            ),
        ]),
        VarFileInfo([VarStruct(u'Translation', [1033, 1200])]),
    ],
)
'''
_version_info_path = os.path.join(SPECPATH, 'build', 'file_version_info.txt')
os.makedirs(os.path.dirname(_version_info_path), exist_ok=True)
with open(_version_info_path, 'w', encoding='utf-8') as _f:
    _f.write(_version_info)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=['qrcode', 'requests', 'psutil'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

# macOS 上 PyInstaller 单文件(onefile) + PySide6 会在 GUI 初始化阶段 segfault
# （cocoa 平台插件问题），因此 macOS 改用 onedir（文件夹）模式，Windows/Linux 仍用单文件。
if sys.platform == 'darwin':
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=EXE_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=([ICON_PATH] if sys.platform != 'linux' else []),
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name=EXE_NAME,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        name=EXE_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=([ICON_PATH] if sys.platform != 'linux' else []),
        version=(_version_info_path if sys.platform == 'win32' else None),
    )
