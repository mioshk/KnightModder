# -*- coding: utf-8 -*-
"""
空洞骑士 Mod 安装器 - 主入口
Hollow Knight Mod Manager (HKMM)
"""
import sys
import os
import threading
import traceback

# ---------- 确保根目录在 sys.path ----------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------- 全局崩溃日志 ----------
def exception_hook(exc_type, exc_value, exc_tb):
    """全局异常捕获，写入崩溃日志"""
    lines = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        with open("crash.log", "w", encoding="utf-8") as f:
            f.write(lines)
    except Exception:
        pass
    print(lines)


sys.excepthook = exception_hook


# ---------- 线程异常捕获（线程崩溃不会触发 sys.excepthook） ----------
def thread_exception_hook(args):
    """捕获工作线程中的未处理异常，写入崩溃日志"""
    # Python 3.10+ 线程异常钩子参数是 _thread._ExceptHookArgs，
    # 回溯字段名为 exc_traceback（不是 exc_tb），统一用 getattr 兼容
    exc_type = args.exc_type
    exc_value = args.exc_value
    exc_tb = getattr(args, "exc_traceback", None)
    lines = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        with open("crash.log", "w", encoding="utf-8") as f:
            f.write("[线程异常]\n" + lines)
    except Exception:
        pass
    print(lines)


if hasattr(threading, "excepthook"):
    threading.excepthook = thread_exception_hook

# ---------- 依赖检查 ----------
try:
    from PySide6.QtCore import Qt, QRect, QTimer
    from PySide6.QtGui import QFont, QIcon
    from PySide6.QtWidgets import QApplication
except ImportError:
    print("请安装 PySide6: pip install PySide6")
    sys.exit(1)

from utils.common import get_asset_path, get_base_dir

# ---------- UI 模块 ----------
from ui import MainWindow


def _install_qt_translation(app):
    """给 Qt 自带控件装上中文：QMessageBox 的「确定 / 是 / 否」、
    QFileDialog 的「打开 / 取消」、QLineEdit 右键菜单等。

    这些文案默认跟随系统语言，非中文系统上就会显示 OK / Yes / No。翻译文件来自
    PySide6 自带的 translations 目录（qtbase_zh_CN.qm 才是基础控件那批）。

    打包后目录结构会变，所以几个位置都找一遍；QTranslator 必须一直被引用着，
    被垃圾回收后翻译会失效，所以挂在 app 上。
    """
    import PySide6
    from PySide6.QtCore import QLibraryInfo, QTranslator

    candidates = [
        QLibraryInfo.path(QLibraryInfo.TranslationsPath),
        os.path.join(os.path.dirname(PySide6.__file__), "translations"),
        os.path.join(get_base_dir(), "PySide6", "translations"),
        os.path.join(get_base_dir(), "translations"),
    ]
    loaded = []
    # 外层按翻译文件、内层按候选路径：同一个文件装上一次就停，
    # 否则每条候选路径都命中时会把同一个 .qm 装好几遍。
    for name in ("qtbase_zh_CN", "qt_zh_CN"):
        for base in candidates:
            if not base:
                continue
            path = os.path.join(base, name + ".qm")
            if not os.path.isfile(path):
                continue
            trans = QTranslator()
            if trans.load(path):
                app.installTranslator(trans)
                loaded.append(trans)
                break

    app._qt_translators = loaded   # 保持引用
    return loaded


def _delayed_check_update(window):
    """延迟检查更新：函数内导入 update_checker，避免启动时加载 requests/qrcode 等重模块"""
    from ui.update_checker import auto_check_for_updates
    auto_check_for_updates(window)


def _center_window(window):
    """把窗口居中到它所在屏幕的**可用区域**。

    主窗口是无边框的（Qt.FramelessWindowHint，见 ui/main_window.py），拖动全靠
    顶部那条自定义标题栏。位置一旦落到屏幕外、或被任务栏压住，标题栏就够不着，
    用户再也拖不动窗口。而无边框窗口不像普通窗口那样会被系统稳妥地摆放
    （尤其 4K / 高缩放 / 任务栏在顶部时，默认位置经常把顶边甩到屏幕外），
    所以必须自己按 availableGeometry 摆位 —— 它已经排除了任务栏。
    """
    screen = window.screen() or QApplication.primaryScreen()
    avail = screen.availableGeometry() if screen is not None else None
    if avail is None or avail.isEmpty():
        return
    # 窗口不能比可用区域还大，否则居中后上下两边会同时溢出屏幕
    w = max(1, min(window.width(), avail.width()))
    h = max(1, min(window.height(), avail.height()))
    if (w, h) != (window.width(), window.height()):
        window.resize(w, h)
    window.move(avail.x() + (avail.width() - w) // 2,
                avail.y() + (avail.height() - h) // 2)


def main():
    """程序主入口"""

    # DPI 自适应缩放（必须在 QApplication 创建前调用）
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    # 弹窗按钮（确定 / 是 / 否 …）显示中文，而不是跟随系统语言的 OK / Yes / No
    _install_qt_translation(app)

    # 任务栏/标题栏图标（打包后从 _MEIPASS 读取，源码运行从项目目录读取）
    app.setWindowIcon(QIcon(get_asset_path("icon.ico")))

    # 按屏幕「可用区域」计算窗口和字体大小。
    # 用 availableGeometry 而不是 size()：后者含任务栏，4K 屏上按整屏算出来的
    # 高度会把窗口顶边顶到任务栏底下甚至屏幕外。
    screen = app.primaryScreen()
    avail = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

    # 窗口尺寸：宽度占屏幕 72%，高度占 75%（上限 780）。
    # 原先 85%/920 太高，删掉两个按钮后首页内容变短，没必要占满屏幕。
    win_width = min(1400, int(avail.width() * 0.72))
    win_height = min(780, int(avail.height() * 0.75))

    # 字体大小随窗口宽度变化
    font_size = max(9, min(13, int(win_width / 110)))
    font = QFont("Microsoft YaHei", font_size)
    app.setFont(font)

    # 创建并显示主窗口：先摆好位置再 show，免得先在错误位置闪一下
    window = MainWindow()
    window.resize(win_width, win_height)
    # 高度按首页内容自适应：默认打开就能完整显示，不用滚轮上下滚
    window.fit_height_to_home(avail.height())
    _center_window(window)
    window.show()
    # show 之后再校正一次：多屏时 primaryScreen 未必是窗口真正所在的那块屏
    _center_window(window)

    # ✅ 窗口显示后再弹窗（100% 生效）
    QTimer.singleShot(400, window.trigger_first_run_dialog)

    # ✅ 启动后 3 秒静默检查更新（仅在新版本时弹窗）
    QTimer.singleShot(3000, lambda: _delayed_check_update(window))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()