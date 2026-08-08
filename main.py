# -*- coding: utf-8 -*-
"""
空洞骑士 Mod 安装器 - 主入口
Hollow Knight Mod Manager (HKMM)
"""
import sys
import os
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

# ---------- 依赖检查 ----------
try:
    from PySide6.QtCore import Qt, QSize, QTimer
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication
except ImportError:
    print("请安装 PySide6: pip install PySide6")
    sys.exit(1)

# ---------- UI & 更新模块 ----------
from ui import MainWindow
from ui.update_checker import auto_check_for_updates


def main():
    """程序主入口"""

    # DPI 自适应缩放（必须在 QApplication 创建前调用）
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 根据屏幕分辨率动态计算窗口和字体大小
    screen = app.primaryScreen()
    screen_size = screen.size() if screen else QSize(1920, 1080)

    # 窗口尺寸：宽度占屏幕 72%，高度占 85%
    win_width = min(1400, int(screen_size.width() * 0.72))
    win_height = min(920, int(screen_size.height() * 0.85))

    # 字体大小随窗口宽度变化
    font_size = max(9, min(13, int(win_width / 110)))
    font = QFont("Microsoft YaHei", font_size)
    app.setFont(font)

    # 创建并显示主窗口
    window = MainWindow()
    window.resize(win_width, win_height)
    window.show()

    # ✅ 窗口显示后再弹窗（100% 生效）
    QTimer.singleShot(400, window.trigger_first_run_dialog)

    # ✅ 启动后 3 秒静默检查更新（仅在新版本时弹窗）
    QTimer.singleShot(3000, lambda: auto_check_for_updates(window))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()