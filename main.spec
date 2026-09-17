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
    # 注意：clr / pythonnet 不能排除 —— 登录窗口（pywebview 的 Windows 后端）
    # 依赖它加载 WinForms + WebView2
    'cryptography', 'yaml', 'jinja2',
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
    # webview：登录窗口改用系统 Edge 内核（WebView2）后新增的依赖。
    # pywebview 的 Windows 后端（edgechromium）是运行时动态导入的，静态分析扫不到，
    # 而它内部还要 import clr（pythonnet）并加载 System.Windows.Forms —— 缺了 clr
    # 登录窗口根本起不来，所以两个都要显式声明。
    hiddenimports=['qrcode', 'requests', 'psutil', 'webview',
                   'webview.platforms.edgechromium', 'clr'],
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
    # QtSvg：详情页的 GitHub 等矢量图标靠 QSvgRenderer 渲染（ui/mod_page.py），
    # 少了它图标会静默退化成文字。别再当成"用不到"的 DLL 剔掉。
    'qt6svg.dll',
    'qt6qml.dll', 'qt6qmlmeta.dll', 'qt6qmlmodels.dll',
    'qt6qmlworkerscript.dll', 'qt6quick.dll', 'qt6quickwidgets.dll',
    'qt6webchannel.dll', 'qt6webenginecore.dll', 'qt6webenginewidgets.dll',
    'qt6widgets.dll',
}

_QT_BINDING_KEEP = {
    'qtcore', 'qtgui', 'qtwidgets', 'qtnetwork', 'qtprintsupport',
    # qtsvg：对应 Qt6Svg.dll，用于渲染 GitHub 等内置矢量图标
    'qtsvg',
    # 下面三个已随 QtWebEngine 一起停用（登录改用 pywebview），保留名字只是说明
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
    # ⑧ QtWebEngine 整套（约 210 MB）：登录已改用系统 Edge 内核（WebView2），
    #    见 ui/quark_login_dialog.py。实测 WebView2 的 CookieManager 能读回
    #    HttpOnly 的登录令牌，登录功能不受影响，于是这颗最大的"瘤"可以摘掉。
    if 'webengine' in base:
        return False
    # ⑨ QML 模块目录（23.7 MB / 2510 个文件）：QtWebEngineWidgets 从不加载 QML，
    #    已实测把整个 qml 目录移走后仍能正常打开夸克登录页。砍掉它的一半意义
    #    在于「文件数」——onefile 解压成本 ≈ 体积 + 文件数 × 单次 I/O，这里的
    #    2510 个废文件占了总文件数的近九成。
    if dest.lower().startswith('pyside6/qml/'):
        return False
    return True


a.binaries = [e for e in a.binaries if _is_slim_entry(e)]
a.datas = [e for e in a.datas if _is_slim_entry(e)]

pyz = PYZ(a.pure)

# 注：曾尝试过 PyInstaller 的 Splash 启动画面来掩盖解压期的空白等待，但在
# PyInstaller 6.22 + 本项目下 tcl 运行时虽打包成功、窗口却始终不显示（静默失败），
# 投入产出比不划算，故放弃。若要再试，需先单独验证 tcl 能否在本机起窗。

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
    # KM_ONEDIR=1：产出「目录版」（exe + _internal 文件夹），供安装器打包成
    # 「安装版」。与 onefile 的区别是运行时不必把整个 bundle 解压到 %TEMP%，
    # 直接从安装目录加载，冷启动能省掉约 2 秒的解压时间。
    _ONEDIR = os.environ.get('KM_ONEDIR') == '1'

    exe = EXE(
        pyz,
        a.scripts,
        ([] if _ONEDIR else a.binaries),
        ([] if _ONEDIR else a.datas),
        exclude_binaries=_ONEDIR,
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

if _ONEDIR:
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name=EXE_NAME,
    )
