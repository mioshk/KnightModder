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

# ---------- 与本项目无关的第三方包（禁止打进 bundle）----------
# 打包环境的 Python 里装了很多其它项目的依赖（scipy/pandas/cryptography/
# pythonnet 等），这些包虽未被本项目 import，却会被一并卷进 bundle：
# 仅 numpy.libs 的 openblas 就有 19.4 MB、cryptography 的 _rust.pyd 9.6 MB。
# onefile 模式下它们每次启动都要白白解压一遍。
_THIRD_PARTY_EXCLUDES = [
    'numpy', 'scipy', 'pandas', 'matplotlib', 'sklearn', 'PIL.ImageQt',
    'cryptography', 'pythonnet', 'clr', 'yaml', 'jinja2',
    'tkinter', 'PyQt5', 'PySide2',
    'torch', 'tensorflow', 'transformers',
    'IPython', 'pytest', 'setuptools', 'wheel', 'pip',
]

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
    excludes=_THIRD_PARTY_EXCLUDES,
    noarchive=False,
)

# ============================================================
# 瘦身：剔除用不到的 Qt DLL / 纯调试资源 / 被污染的第三方依赖
# ------------------------------------------------------------
# 为什么必须做：PySide6 的打包 hook 会把安装目录下【所有】Qt DLL 与 Python
# 绑定都塞进 bundle（原 531 MB），而本项目实际只用
# Core/Gui/Widgets/Network/PrintSupport/WebChannel/WebEngineCore/WebEngineWidgets。
# onefile 每次启动都要把整个 bundle 解压到 %TEMP%，体积直接等于启动耗时。
#
# 下面的清单来源：
#   ① _QT_DLL_KEEP —— 递归解析 PE 导入表得到的 QtWebEngine/Widgets 真实依赖闭包；
#   ② Qt Python 绑定 —— 实测 import PySide6.QtWebEngineWidgets 后 sys.modules，
#      其余 Qt*.pyd 从未被加载，可安全剔除（底层 DLL 仍在 _QT_DLL_KEEP 里保留）；
#   ③ *.debug.pak / *.debug.bin —— 崩溃符号之类的调试资源，运行时完全用不到。
#
# ⚠️ 改动前请重新核对依赖闭包，勿凭猜测增删 _QT_DLL_KEEP。
# ============================================================
_QT_DLL_KEEP = {
    'qt6core.dll', 'qt6gui.dll', 'qt6network.dll', 'qt6opengl.dll',
    'qt6positioning.dll', 'qt6printsupport.dll',
    'qt6qml.dll', 'qt6qmlmeta.dll', 'qt6qmlmodels.dll',
    'qt6qmlworkerscript.dll', 'qt6quick.dll', 'qt6quickwidgets.dll',
    'qt6webchannel.dll', 'qt6webenginecore.dll', 'qt6webenginewidgets.dll',
    'qt6widgets.dll',
}

_QT_BINDING_KEEP = {
    'qtcore', 'qtgui', 'qtwidgets', 'qtnetwork', 'qtprintsupport',
    'qtwebchannel', 'qtwebenginecore', 'qtwebenginewidgets',
}


def _is_slim_entry(entry) -> bool:
    """判断 bundle 条目是否需要保留"""
    dest = entry[0].replace('\\', '/')
    base = dest.rsplit('/', 1)[-1].lower()

    # ① 纯调试资源（qtwebengine_devtools_resources.debug.pak 就占 72 MB）
    if base.endswith('.debug.pak') or base.endswith('.debug.bin'):
        return False
    # ② SwiftShader 软件渲染：Qt Widgets 应用用不到（19.7 MB）
    if base == 'opengl32sw.dll':
        return False
    # ③ 依赖闭包之外的 Qt 运行时 DLL
    if base.startswith('qt6') and base.endswith('.dll') and base not in _QT_DLL_KEEP:
        return False
    # ④ 从未被加载的 Qt Python 绑定（QtOpenGL.pyd 8.3MB、QtCharts/Qt3D…）
    if base.endswith('.pyd') and base.startswith('qt') and base[:-4] not in _QT_BINDING_KEEP:
        return False
    # ⑤ Chromium 多语言包：208 个语种白占 48 MB，界面只需要中/英
    #    （缺失语种 Chromium 会自动回退默认，不会影响网页渲染）
    if 'translations/qtwebengine_locales/' in dest.lower():
        return base in ('zh-cn.pak', 'en-us.pak')
    # ⑥ WebEngine 开发者工具资源（11 MB）：只在调试 Web 页面时用到
    if base == 'qtwebengine_devtools_resources.pak':
        return False
    # ⑦ Pillow 的 AVIF 插件（7.5 MB）：本项目只用它渲染二维码图片
    if base.startswith('_avif'):
        return False
    # ⑧ QML 模块目录（23.7 MB / 2510 个文件）：QtWebEngineWidgets 从不加载 QML，
    #    已实测把整个 qml 目录移走后仍能正常打开夸克登录页。砍掉它的一半意义
    #    在于「文件数」——onefile 解压成本 ≈ 体积 + 文件数 × 单次 I/O，这里的
    #    2510 个废文件占了总文件数的近九成。
    if dest.lower().startswith('pyside6/qml/'):
        return False
    return True


a.binaries = [e for e in a.binaries if _is_slim_entry(e)]
a.datas = [e for e in a.datas if _is_slim_entry(e)]

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
        # UPX 显式关闭：onefile 每次启动都要把 bundle 解压到 %TEMP%，对
        # Qt6WebEngineCore.dll 这种 195 MB 的巨型 DLL 再加一层 UPX 解压只会
        # 拖慢冷启动；且 UPX 加壳的 exe 常被 Windows Defender 误报为可疑。
        # （实测开/关的 exe 体积与启动时间完全一致。）
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=([ICON_PATH] if sys.platform != 'linux' else []),
        version=(_version_info_path if sys.platform == 'win32' else None),
    )
