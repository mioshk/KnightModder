# -*- coding: utf-8 -*-
"""
主窗口模块 - 现代化视觉设计（原生 Painter 窗口按钮）
"""
import os
import re
import sys
import threading
import webbrowser
import psutil  # 需要安装: pip install psutil
from PySide6.QtCore import Qt, QTimer, QTime, QSize, QByteArray, QSettings
from PySide6.QtGui import QFont, QColor, QLinearGradient, QPixmap, QPainter, QIcon, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QGraphicsDropShadowEffect
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextEdit,
    QScrollArea,
    QFrame,
    QFileDialog,
    QMessageBox,
    QApplication,
    QSizePolicy,
)
from config import (
    APP_NAME,
    MANAGED_RELATIVE_PATH,
    MODLINKS_URL,
    COLOR_BG,
    COLOR_BORDER,
    COLOR_ACCENT_GREEN,
    COLOR_ACCENT_RED,
    COLOR_ACCENT_PINK,
    COLOR_TEXT_SECONDARY,
)
from ui.styles import DARK_STYLE_SHEET
from ui.dialogs import (
    show_about_dialog,
    show_path_select_dialog,
    show_missing_deps_dialog,
    show_mod_errors_dialog,
    AboutMarkdownDialog,
)
from ui.mod_page import ModPage, OnlineModPage
from ui.update_checker import check_for_updates
from utils import (
    load_saved_path,
    save_path,
    normalize_path,
    get_root_from_exe,
    get_mods_dir,
    get_save_folder,
    get_api_zip_path,
    find_hollow_knight_exe,
)
from core import (
    DependencyResolver,
    install_api,
    restore_vanilla,
    install_mods,
    launch_game,
)


# ============================================================
# 原生绘制窗口控制按钮（完全替代 SVG）
# ============================================================
class WindowControlButton(QPushButton):
    """原生 Painter 绘制的窗口控制按钮（图标更小更精致）"""

    def __init__(self, icon_type="min", parent=None):
        super().__init__(parent)
        self.icon_type = icon_type
        self.hover = False
        self.pressed = False

        self.setFixedSize(30, 30)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setStyleSheet("border: none; background: transparent;")

    def enterEvent(self, event):
        self.hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        dpr = self.devicePixelRatioF()
        w, h = self.width(), self.height()

        # ---------- 背景 ----------
        if self.icon_type == "close":
            if self.hover:
                bg = QColor("#e53935") if not self.pressed else QColor("#c62828")
            else:
                bg = QColor(255, 255, 255, 18)
        else:
            if self.hover:
                bg = QColor(255, 255, 255, 30)
            elif self.pressed:
                bg = QColor(255, 255, 255, 45)
            else:
                bg = QColor(255, 255, 255, 12)

        painter.setBrush(bg)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, w, h)

        # ---------- 图标 ----------
        if self.icon_type == "close" and self.hover:
            pen_color = QColor("#ffffff")
        else:
            pen_color = QColor("#e0e0e0")

        pen = QPen(pen_color)
        pen.setWidthF(1.2 * dpr)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)

        m = 9

        if self.icon_type == "min":
            painter.drawLine(m, h // 2, w - m, h // 2)

        elif self.icon_type == "max":
            r = 8
            painter.drawRoundedRect(r, r, w - r * 2, h - r * 2, 2.5, 2.5)

        elif self.icon_type == "restore":
            painter.drawRoundedRect(8, 10, 12, 10, 2, 2)
            painter.drawRoundedRect(10, 8, 12, 10, 2, 2)

        elif self.icon_type == "close":
            painter.drawLine(m, m, w - m, h - m)
            painter.drawLine(w - m, m, m, h - m)

        painter.end()


# ============================================================
# 自定义圆角按钮 - 保证最大圆角
# ============================================================
class RoundedButton(QPushButton):
    """保证最大圆角的按钮"""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setObjectName("btnLaunch")
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.setMinimumHeight(52)
        self.setMinimumWidth(160)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style(False)

    def _apply_style(self, running):
        if running:
            self.setText("停止游戏")
            self.setStyleSheet("""
                QPushButton#btnLaunch {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #e53935,
                        stop:1 #c62828);
                    border: none;
                    border-radius: 26px;
                    color: white;
                    font-size: 16px;
                    font-weight: 700;
                    padding: 14px 32px;
                    letter-spacing: 0.5px;
                }
            """)
        else:
            self.setText("启动游戏")
            self.setStyleSheet("""
                QPushButton#btnLaunch {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #66bb6a,
                        stop:1 #43a047);
                    border: none;
                    border-radius: 26px;
                    color: white;
                    font-size: 16px;
                    font-weight: 700;
                    padding: 14px 32px;
                    letter-spacing: 0.5px;
                }
            """)

    def update_style(self, running):
        self._apply_style(running)


# ============================================================
# DLL信息提取工具
# ============================================================
def get_dll_identity(dll_path):
    identity = {
        'product_name': '',
        'assembly_name': '',
        'file_version': '',
        'product_version': '',
        'internal_name': '',
        'original_filename': ''
    }

    try:
        if sys.platform == 'win32':
            import ctypes
            from ctypes import wintypes

            ver_size = ctypes.windll.version.GetFileVersionInfoSizeW(dll_path, None)
            if ver_size == 0:
                return identity

            data = ctypes.create_string_buffer(ver_size)
            ctypes.windll.version.GetFileVersionInfoW(dll_path, 0, ver_size, data)

            def get_string_info(sub_block):
                try:
                    lang_codepage = None
                    struct_ptr = ctypes.c_void_p()
                    struct_len = ctypes.c_uint()
                    if ctypes.windll.version.VerQueryValueW(
                        data,
                        '\\VarFileInfo\\Translation',
                        ctypes.byref(struct_ptr),
                        ctypes.byref(struct_len)
                    ):
                        if struct_len.value >= 4:
                            lang_codepage = ctypes.cast(struct_ptr, ctypes.POINTER(wintypes.DWORD)).contents.value
                            lang = lang_codepage & 0xFFFF
                            codepage = (lang_codepage >> 16) & 0xFFFF
                            query = f'\\StringFileInfo\\{lang:04x}{codepage:04x}\\{sub_block}'
                            struct_ptr2 = ctypes.c_void_p()
                            struct_len2 = ctypes.c_uint()
                            if ctypes.windll.version.VerQueryValueW(
                                data,
                                query,
                                ctypes.byref(struct_ptr2),
                                ctypes.byref(struct_len2)
                            ):
                                if struct_len2.value and struct_len2.value > 0 and struct_ptr2.value is not None:
                                    return ctypes.wstring_at(struct_ptr2.value, struct_len2.value // 2)
                except Exception:
                    pass
                return ''

            identity['product_name'] = get_string_info('ProductName')
            identity['file_version'] = get_string_info('FileVersion')
            identity['product_version'] = get_string_info('ProductVersion')
            identity['internal_name'] = get_string_info('InternalName')
            identity['original_filename'] = get_string_info('OriginalFilename')

            if not identity['product_name']:
                identity['product_name'] = get_string_info('InternalName')
            if not identity['product_name']:
                identity['product_name'] = get_string_info('OriginalFilename')

    except Exception:
        pass

    if not identity['product_name'] and not identity['assembly_name']:
        identity['product_name'] = os.path.basename(dll_path).replace('.dll', '')

    return identity


def get_dll_key(identity):
    if identity['product_name']:
        name = identity['product_name']
        name = re.sub(r'[-_\.]?v?\d+\.\d+\.\d+.*$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'[-_\.]?\d+\.\d+\.\d+.*$', '', name, flags=re.IGNORECASE)
        return name.strip()
    return os.path.basename(identity.get('original_filename', '')).replace('.dll', '')


# ============================================================
# 主窗口
# ============================================================
class MainWindow(QMainWindow):
    """主窗口类"""

    def __init__(self):
        super().__init__()
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle(APP_NAME)

        screen = QApplication.primaryScreen()
        screen_size = screen.size() if screen else QSize(1920, 1080)
        min_w = int(screen_size.width() * 0.48)
        min_h = int(screen_size.height() * 0.70)
        self.setMinimumSize(max(800, min_w), max(550, min_h))
        self.setStyleSheet(DARK_STYLE_SHEET)

        self._drag_pos = None
        self._is_maximized = False

        # 业务状态
        self.game_path = ""
        self.resolver = DependencyResolver()
        self.missing_deps = set()
        self.is_loading = False

        self.settings = QSettings("KnightModder", "Settings")

        # ✅ 本次启动是否已询问过（防止重复弹）
        self._asked_this_session = False

        # 游戏进程监控相关
        self.game_process = None
        self.game_pid = None
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self._check_game_running)
        self.monitor_timer.start(1000)

        self._setup_ui()
        self._load_saved_path()
        QTimer.singleShot(500, self._auto_load_dependency)

    # ==================== 新增：config 是否存在 ====================
    import os

    def _has_config(self):
        p = load_saved_path()
        if not p:
            return False
        if not isinstance(p, str):
            return False
        if not os.path.isdir(p):
            return False
        if not os.path.isdir(os.path.join(p, MANAGED_RELATIVE_PATH)):
            return False
        return True

    # ==================== 路径显示工具 ====================
    @staticmethod
    def _display_path(root):
        """将游戏根目录转为 exe 路径用于 UI 显示"""
        if not root:
            return root
        exe = os.path.join(root, "hollow_knight.exe")
        return normalize_path(exe)

    # ==================== 路径加载（不弹窗、不写文件） ====================
    def _load_saved_path(self):
        p = load_saved_path()
        if not p:
            return
        if os.path.isdir(os.path.join(p, MANAGED_RELATIVE_PATH)):
            self.game_path = p
            self.path_input.setText(self._display_path(p))

    # ==================== 对外接口：首次启动弹窗 ====================
    def trigger_first_run_dialog(self):
        if self._asked_this_session:
            return
        if self._has_config():
            return
        self._asked_this_session = True
        self._auto_detect_and_prompt()

    # ==================== 自动检测并询问 ====================
    def _auto_detect_and_prompt(self):
        res = find_hollow_knight_exe()
        if res and len(res) == 1:
            _, root = res[0]
            root = normalize_path(root)
            r = QMessageBox.question(
                self, "检测到游戏安装",
                f"我们在以下位置检测到了《空洞骑士》：\n\n{root}\n\n"
                "这是你的游戏安装路径吗？",
                QMessageBox.Yes | QMessageBox.No
            )
            if r == QMessageBox.Yes:
                self._commit_path(root)
            return

        if res and len(res) > 1:
            sel = show_path_select_dialog(self, res)
            if sel:
                self._commit_path(sel)
            return

        QMessageBox.information(
            self, "未检测到游戏",
            "未能自动找到《空洞骑士》的安装路径。\n\n"
            "请点击「浏览」按钮手动选择 hollow_knight.exe。"
        )

    # ==================== 唯一写 config 的地方 ====================
    def _commit_path(self, root):
        self.game_path = root
        self.path_input.setText(self._display_path(root))
        save_path(root)

    # ==================== UI 构建（完全原样） ====================
    def _setup_ui(self):
        outer = QWidget()
        outer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        outer.setStyleSheet("background: transparent;")
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(20, 20, 20, 20)
        outer_layout.setSpacing(0)

        root = QWidget()
        root.setObjectName("MainWindowCard")
        root.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.setAttribute(Qt.WA_StyledBackground, True)
        root.setStyleSheet(
            f"#MainWindowCard {{ "
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 #1a1a1a, stop:1 #0f0f0f); "
            f"border-radius: 20px; "
            f"border: 1px solid rgba(255, 255, 255, 0.08); }}"
        )

        self._root = root
        self._outer = outer
        self._outer.setMouseTracking(True)
        self._outer.installEventFilter(self)
        self._outer_layout = outer_layout
        self._shadow = QGraphicsDropShadowEffect(root)
        self._shadow.setBlurRadius(50)
        self._shadow.setXOffset(0)
        self._shadow.setYOffset(15)
        self._shadow.setColor(QColor(0, 0, 0, 150))
        root.setGraphicsEffect(self._shadow)

        outer_layout.addWidget(root)
        self.setCentralWidget(outer)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._create_title_bar())
        root_layout.addWidget(self._create_nav_bar())
        root_layout.addWidget(self._create_stack())

    def _create_title_bar(self):
        bar = QWidget()
        bar.setObjectName("TitleBar")
        bar.setFixedHeight(64)
        bar.mousePressEvent = self._titlebar_mouse_press
        bar.mouseMoveEvent = self._titlebar_mouse_move
        bar.mouseDoubleClickEvent = lambda e: self._toggle_maximize()
        bar.setStyleSheet("""
            QWidget#TitleBar {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1e1e24,
                    stop:1 #25252b);
                border: none;
                border-top-left-radius: 20px;
                border-top-right-radius: 20px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 14, 0)
        layout.setSpacing(8)

        logo = QLabel("⚔️")
        logo.setStyleSheet("font-size: 26px; background: transparent; padding: 4px;")
        layout.addWidget(logo)

        title = QLabel(APP_NAME)
        title.setObjectName("titleLabel")
        title.setStyleSheet("""
            background: transparent;
            color: #ffffff;
            font-size: 18px;
            font-weight: 600;
            letter-spacing: 0.5px;
        """)
        layout.addWidget(title)

        announcement = QLabel("📢 仅限 1.5.78 版本游戏！")
        announcement.setObjectName("announcementLabel")
        announcement.setFixedHeight(28)
        announcement.setStyleSheet("""
            font-size: 12px;
            font-weight: 600;
            color: #ff9800;
            background: rgba(255, 152, 0, 0.1);
            border: 1px solid rgba(255, 152, 0, 0.3);
            border-radius: 12px;
            padding: 4px 12px;
        """)
        layout.addWidget(announcement)

        layout.addStretch()

        tutorial_btn = QPushButton("📖 使用教程")
        tutorial_btn.setObjectName("btnGhost")
        tutorial_btn.setFixedHeight(34)
        tutorial_btn.setStyleSheet("""
            QPushButton#btnGhost {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: #aaaaaa;
                border-radius: 12px;
                padding: 6px 18px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton#btnGhost:hover {
                background: rgba(255, 255, 255, 0.08);
                border-color: rgba(255, 255, 255, 0.2);
                color: #ffffff;
            }
        """)
        tutorial_btn.clicked.connect(self._show_usage_md)
        layout.addWidget(tutorial_btn)

        update_btn = QPushButton("📥 检查更新")
        update_btn.setObjectName("btnGhost")
        update_btn.setFixedHeight(34)
        update_btn.setStyleSheet(tutorial_btn.styleSheet())
        update_btn.clicked.connect(lambda: check_for_updates(self, show_no_update=True))
        layout.addWidget(update_btn)

        about_btn = QPushButton("ℹ️ 关于")
        about_btn.setObjectName("btnGhost")
        about_btn.setFixedHeight(34)
        about_btn.setStyleSheet(tutorial_btn.styleSheet())
        about_btn.clicked.connect(self._show_about_md)
        layout.addWidget(about_btn)

        self.min_btn = WindowControlButton("min")
        self.min_btn.setToolTip("最小化")
        self.min_btn.clicked.connect(self.showMinimized)
        layout.addWidget(self.min_btn)

        self.max_btn = WindowControlButton("max")
        self.max_btn.setToolTip("最大化")
        self.max_btn.clicked.connect(self._toggle_maximize)
        layout.addWidget(self.max_btn)

        close_btn = WindowControlButton("close")
        close_btn.setToolTip("关闭")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        return bar

    def _toggle_maximize(self):
        if self._is_maximized:
            self.showNormal()
        else:
            self.showMaximized()

    # ==================== 最大化/还原时的 UI 适配 ====================
    _NORMAL_STYLE = (
        "#MainWindowCard { "
        "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
        "stop:0 #1a1a1a, stop:1 #0f0f0f); "
        "border-radius: 20px; "
        "border: 1px solid rgba(255, 255, 255, 0.08); }"
    )
    _MAXIMIZED_STYLE = (
        "#MainWindowCard { "
        "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
        "stop:0 #1a1a1a, stop:1 #0f0f0f); "
        "border-radius: 0px; "
        "border: none; }"
    )

    def changeEvent(self, event):
        if event.type() == event.Type.WindowStateChange:
            if not hasattr(self, '_outer_layout') or not hasattr(self, 'max_btn'):
                return super().changeEvent(event)
            if self.windowState() & Qt.WindowMaximized:
                self._is_maximized = True
                self.max_btn.icon_type = "restore"
                self._outer_layout.setContentsMargins(0, 0, 0, 0)
                self._root.setStyleSheet(self._MAXIMIZED_STYLE)
            elif not (self.windowState() & Qt.WindowMaximized):
                self._is_maximized = False
                self.max_btn.icon_type = "max"
                self._outer_layout.setContentsMargins(20, 20, 20, 20)
                self._root.setStyleSheet(self._NORMAL_STYLE)
            self.max_btn.update()
        super().changeEvent(event)

    # ==================== 边缘拖拽调整窗口大小 ====================
    _BORDER = 6  # 边缘拖拽识别宽度（像素），以窗口真实边缘为准

    def _hit_edge(self, pos):
        """返回鼠标所在的窗口边缘（用于 resize），不在边缘则返回 None"""
        b = self._BORDER
        w, h = self.width(), self.height()
        on_left = pos.x() <= b
        on_right = pos.x() >= w - b
        on_top = pos.y() <= b
        on_bottom = pos.y() >= h - b

        if on_top and on_left:
            return Qt.TopEdge | Qt.LeftEdge
        if on_top and on_right:
            return Qt.TopEdge | Qt.RightEdge
        if on_bottom and on_left:
            return Qt.BottomEdge | Qt.LeftEdge
        if on_bottom and on_right:
            return Qt.BottomEdge | Qt.RightEdge
        if on_left:
            return Qt.LeftEdge
        if on_right:
            return Qt.RightEdge
        if on_top:
            return Qt.TopEdge
        if on_bottom:
            return Qt.BottomEdge
        return None

    def eventFilter(self, obj, event):
        if obj is not self._outer or self._is_maximized:
            return super().eventFilter(obj, event)

        t = event.type()
        if t == event.Type.MouseMove:
            pos = self.mapFromGlobal(event.globalPosition().toPoint())
            edge = self._hit_edge(pos)
            cursor = {
                Qt.TopEdge | Qt.LeftEdge: Qt.SizeFDiagCursor,
                Qt.BottomEdge | Qt.RightEdge: Qt.SizeFDiagCursor,
                Qt.TopEdge | Qt.RightEdge: Qt.SizeBDiagCursor,
                Qt.BottomEdge | Qt.LeftEdge: Qt.SizeBDiagCursor,
                Qt.LeftEdge: Qt.SizeHorCursor,
                Qt.RightEdge: Qt.SizeHorCursor,
                Qt.TopEdge: Qt.SizeVerCursor,
                Qt.BottomEdge: Qt.SizeVerCursor,
            }
            self.setCursor(cursor.get(edge, Qt.ArrowCursor))
            self._resize_edge = edge
        elif t == event.Type.MouseButtonPress and event.button() == Qt.LeftButton:
            if self._resize_edge is not None:
                wh = self.windowHandle()
                if wh:
                    wh.startSystemResize(self._resize_edge)
                return True
        elif t == event.Type.Leave:
            self.setCursor(Qt.ArrowCursor)
            self._resize_edge = None

        return super().eventFilter(obj, event)

    def _show_about_md(self):
        dialog = AboutMarkdownDialog(self)
        dialog.exec()

    def _show_usage_md(self):
        usage_url = "https://cdn.jsdelivr.net/gh/mioshk/KnightModder@main/USAGE.md"
        dialog = AboutMarkdownDialog(self, url=usage_url, title="使用教程")
        dialog.exec()

    def _create_nav_bar(self):
        nav_bar = QWidget()
        nav_bar.setObjectName("NavBar")
        nav_bar.setFixedHeight(52)
        nav_bar.setStyleSheet("""
            QWidget#NavBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(30, 30, 35, 0.95),
                    stop:1 rgba(20, 20, 25, 0.95));
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
        """)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(28, 0, 28, 0)
        nav_layout.setSpacing(6)

        self.tab_main_btn = QPushButton("🏠  首页")
        self.tab_local_btn = QPushButton("📂  本地模组")
        self.tab_online_btn = QPushButton("🌐  在线模组")

        for btn in [self.tab_main_btn, self.tab_local_btn, self.tab_online_btn]:
            btn.setObjectName("tabBtn")
            btn.setCheckable(True)

        self.tab_main_btn.setChecked(True)

        tab_style = """
            QPushButton#tabBtn {
                background: transparent;
                border: none;
                border-bottom: 3px solid transparent;
                color: #777777;
                font-size: 14px;
                font-weight: 500;
                padding: 8px 20px;
                min-width: 80px;
            }
            QPushButton#tabBtn:hover {
                color: #bbbbbb;
                border-bottom: 3px solid #444444;
            }
            QPushButton#tabBtn:checked {
                color: #ffffff;
                border-bottom: 3px solid qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #66bb6a, stop:1 #43a047);
            }
        """
        for btn in [self.tab_main_btn, self.tab_local_btn, self.tab_online_btn]:
            btn.setStyleSheet(tab_style)

        self.tab_main_btn.clicked.connect(lambda: self._switch_tab(0))
        self.tab_local_btn.clicked.connect(lambda: self._switch_tab(1))
        self.tab_online_btn.clicked.connect(lambda: self._switch_tab(2))

        nav_layout.addWidget(self.tab_main_btn)
        nav_layout.addWidget(self.tab_local_btn)
        nav_layout.addWidget(self.tab_online_btn)
        nav_layout.addStretch()

        return nav_bar

    def _create_stack(self):
        self.stack = QWidget()
        self.stack_layout = QVBoxLayout(self.stack)
        self.stack_layout.setContentsMargins(0, 0, 0, 0)
        self.stack_layout.setSpacing(0)

        self.page_main = self._create_main_page()
        self.stack_layout.addWidget(self.page_main)

        self.page_local = ModPage(self)
        self.page_local.setVisible(False)
        self.stack_layout.addWidget(self.page_local)

        self.page_online = OnlineModPage(self)
        self.page_online.setVisible(False)
        self.stack_layout.addWidget(self.page_online)

        return self.stack

    def _switch_tab(self, index):
        self.tab_main_btn.setChecked(index == 0)
        self.tab_local_btn.setChecked(index == 1)
        self.tab_online_btn.setChecked(index == 2)

        self.page_main.setVisible(index == 0)
        self.page_local.setVisible(index == 1)
        self.page_online.setVisible(index == 2)

        if index == 1:
            QTimer.singleShot(50, lambda: self.page_local.refresh_mod_list(self.game_path))
        if index == 2:
            QTimer.singleShot(50, lambda: self.page_online.refresh_mod_list(self.game_path))

    def _create_main_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        content = QWidget()
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(16)

        hero_widget = self._create_hero_card()
        hero_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        content_layout.addWidget(hero_widget)

        split_widget = QWidget()
        split_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        split_widget.setStyleSheet("background: transparent;")
        split_layout = QHBoxLayout(split_widget)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(16)

        func_widget = self._create_function_grid()
        func_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        split_layout.addWidget(func_widget, stretch=2)

        log_widget = self._create_log_area()
        log_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        split_layout.addWidget(log_widget, stretch=3)

        content_layout.addWidget(split_widget, stretch=1)

        scroll.setWidget(content)
        return scroll

    def _create_hero_card(self):
        card = QFrame()
        card.setObjectName("HeroCard")
        card.setStyleSheet("""
            QFrame#HeroCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2a2a30,
                    stop:1 #1f1f25);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 18px;
            }
        """)

        card_shadow = QGraphicsDropShadowEffect(card)
        card_shadow.setBlurRadius(35)
        card_shadow.setXOffset(0)
        card_shadow.setYOffset(8)
        card_shadow.setColor(QColor(0, 0, 0, 120))
        card.setGraphicsEffect(card_shadow)

        main_layout = QVBoxLayout(card)
        main_layout.setContentsMargins(28, 26, 28, 26)
        main_layout.setSpacing(16)

        top_row = QWidget()
        top_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        top_row.setStyleSheet("background: transparent;")
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(24)

        left_col = QVBoxLayout()
        left_col.setSpacing(10)

        head_row = QHBoxLayout()
        head_title = QLabel("请先把你的游戏退回至 1.5.78 版本")
        head_title.setObjectName("headingLabel")
        head_title.setStyleSheet("""
            font-size: 18px;
            font-weight: 600;
            color: #ffffff;
            background: transparent;
        """)
        head_row.addWidget(head_title)
        head_row.addStretch()

        self.version_status_label = QLabel("")
        self.version_status_label.setObjectName("statusLabel")
        head_row.addWidget(self.version_status_label)

        left_col.addLayout(head_row)

        desc = QLabel("选择你的《空洞骑士》安装路径，即可一键安装 API 与 Mod")
        desc.setObjectName("subtitleLabel")
        desc.setWordWrap(True)
        desc.setStyleSheet("""
            font-size: 14px;
            color: #999999;
            background: transparent;
            line-height: 1.5;
        """)
        left_col.addWidget(desc)

        top_layout.addLayout(left_col, stretch=3)

        right_col = QVBoxLayout()
        right_col.addStretch()

        self.launch_btn = RoundedButton("启动游戏")
        self.launch_btn.clicked.connect(self._handle_launch_or_stop)
        right_col.addWidget(self.launch_btn)
        right_col.addStretch()

        top_layout.addLayout(right_col, stretch=1)
        main_layout.addWidget(top_row)

        path_row = QHBoxLayout()
        path_row.setSpacing(12)

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("选择 hollow_knight.exe ...")
        self.path_input.textChanged.connect(self._on_path_changed)
        self.path_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.path_input.setStyleSheet("""
            QLineEdit {
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                padding: 12px 16px;
                color: #ffffff;
                font-size: 14px;
                selection-background-color: #66bb6a;
            }
            QLineEdit:focus {
                border: 1px solid #66bb6a;
            }
            QLineEdit:hover {
                border-color: rgba(255, 255, 255, 0.2);
            }
        """)
        path_row.addWidget(self.path_input, stretch=1)

        browse_btn = QPushButton("📁 浏览")
        browse_btn.setObjectName("btnSecondary")
        browse_btn.clicked.connect(self._browse_exe)
        browse_btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        browse_btn.setStyleSheet("""
            QPushButton#btnSecondary {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #26c6da,
                    stop:1 #00acc1);
                border: none;
                color: white;
                font-size: 14px;
                font-weight: 600;
                padding: 12px 24px;
                border-radius: 12px;
            }
            QPushButton#btnSecondary:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #36d6ea,
                    stop:1 #10bcc1);
            }
            QPushButton#btnSecondary:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #16b6ca,
                    stop:0 #009ca1);
            }
        """)
        path_row.addWidget(browse_btn)

        main_layout.addLayout(path_row)
        return card

    def _create_function_grid(self):
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        title = QLabel("常用功能")
        title.setObjectName("headingLabel")
        title.setStyleSheet("""
            font-size: 17px;
            font-weight: 600;
            color: #ffffff;
            background: transparent;
            padding: 0 0 4px 0;
        """)
        layout.addWidget(title)

        button_layout = QVBoxLayout()
        button_layout.setSpacing(10)

        buttons = [
            ("⚙️", "安装 API", "为游戏注入 Modding API", self._install_api),
            ("↩️", "还原原版", "移除 API，恢复原版 dll", self._restore),
            ("📦", "安装 Mod", "从本地选择 zip/dll 安装", self._install_mods),
            ("📂", "Mods 文件夹", "打开 Mods 安装目录", self._open_mods),
            ("💾", "存档文件夹", "打开游戏存档所在位置", self._open_save),
            ("🔍", "检查前置依赖", "扫描已装 Mod 缺失的依赖", self._check_missing_dependencies),
            ("🛠️", "检查Mod错误", "游戏中出现报错点我", self._check_mod_errors),
            ("🔄", "更新链接", "重新拉取最新 Mod 数据", self._reload_dependency),
        ]

        for icon, name, desc, handler in buttons:
            btn = self._make_function_card(icon, name, desc)
            btn.clicked.connect(handler)
            button_layout.addWidget(btn)

        layout.addLayout(button_layout)
        layout.addStretch()
        return wrap

    def _make_function_card(self, icon, name, desc):
        btn = QPushButton()
        btn.setObjectName("btnFuncCard")
        btn.setMinimumHeight(60)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton#btnFuncCard {
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
                text-align: left;
                padding: 14px 18px;
                font-size: 14px;
                font-weight: 500;
            }
            QPushButton#btnFuncCard:hover {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(102, 187, 106, 0.85);
            }
            QPushButton#btnFuncCard:pressed {
                background: rgba(255, 255, 255, 0.04);
            }
        """)

        inner_layout = QHBoxLayout(btn)
        inner_layout.setContentsMargins(16, 10, 16, 10)
        inner_layout.setSpacing(14)

        icon_label = QLabel(icon)
        icon_label.setFixedSize(40, 40)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("""
            background: rgba(102, 187, 106, 0.1);
            border-radius: 10px;
            font-size: 22px;
        """)
        inner_layout.addWidget(icon_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        name_label = QLabel(name)
        name_label.setStyleSheet("""
            color: #ffffff;
            font-size: 14px;
            font-weight: 600;
            background: transparent;
        """)
        name_label.setAlignment(Qt.AlignLeft)
        text_layout.addWidget(name_label)

        desc_label = QLabel(desc)
        desc_label.setStyleSheet("""
            color: #888888;
            font-size: 12px;
            background: transparent;
        """)
        desc_label.setWordWrap(False)
        desc_label.setAlignment(Qt.AlignLeft)
        text_layout.addWidget(desc_label)

        inner_layout.addLayout(text_layout)
        inner_layout.addStretch()
        return btn

    def _create_log_area(self):
        panel = QWidget()
        panel.setStyleSheet("""
            QWidget {
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(10)

        header_row = QHBoxLayout()

        log_title = QLabel("📋 运行日志")
        log_title.setObjectName("logTitleLabel")
        log_title.setStyleSheet("""
            font-size: 15px;
            font-weight: 600;
            color: #ffffff;
            background: transparent;
            border: none;
        """)
        header_row.addWidget(log_title)
        header_row.addStretch()

        clear_btn = QPushButton("清空")
        clear_btn.setObjectName("btnGhost")
        clear_btn.setFixedHeight(28)
        clear_btn.setStyleSheet("""
            QPushButton#btnGhost {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: #999999;
                border-radius: 10px;
                padding: 4px 14px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton#btnGhost:hover {
                background: rgba(255, 255, 255, 0.08);
                color: #ffffff;
            }
        """)
        clear_btn.clicked.connect(self._clear_log)
        header_row.addWidget(clear_btn)

        layout.addLayout(header_row)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background: rgba(0, 0, 0, 0.2);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 10px;
                padding: 12px;
                font-size: 13px;
                color: #cccccc;
                font-family: "Consolas", "Microsoft YaHei", monospace;
            }
        """)
        self.log_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.log_text)

        return panel

    # ==================== 日志工具 ====================
    def _log(self, text, level="info"):
        color_map = {
            "info": "#888888",
            "success": "#66bb6a",
            "warning": "#ff9800",
            "error": "#e53935",
        }
        color = color_map.get(level, "#888888")

        timestamp = QTime.currentTime().toString("HH:mm:ss")
        html = (
            f'<span style="color:#666666;">[{timestamp}]</span> '
            f'<span style="color:{color};">{text}</span>'
        )
        self.log_text.append(html)

        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _clear_log(self):
        self.log_text.clear()

    # ==================== 标题栏交互 ====================
    def _titlebar_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _titlebar_mouse_move(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    # ==================== 路径相关 ====================
    def _on_path_changed(self, text):
        if not text:
            return

        if text.endswith('.exe'):
            game_path = get_root_from_exe(text)
        else:
            game_path = text

        if os.path.isdir(os.path.join(game_path, MANAGED_RELATIVE_PATH)):
            self._commit_path(game_path)

    def _browse_exe(self):
        last_path = self.settings.value("game_exe_path", "")
        last_dir = os.path.dirname(last_path) if last_path else ""

        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 hollow_knight.exe",
            last_dir,
            "EXE (hollow_knight.exe);;All Files (*.*)"
        )
        if file_path:
            root = get_root_from_exe(file_path)
            self._commit_path(root)

    def _valid_path(self, silent=False):
        p = self.path_input.text().strip()
        if not p:
            if not silent:
                QMessageBox.warning(self, "错误", "请先设置游戏路径")
            return False

        if p.endswith('.exe'):
            p = get_root_from_exe(p)

        if not os.path.isdir(os.path.join(p, MANAGED_RELATIVE_PATH)):
            if not silent:
                QMessageBox.warning(self, "错误", "路径无效，未找到 Managed 文件夹")
            return False

        return True

    # ==================== 游戏进程检测与停止 ====================
    def _find_game_process(self):
        try:
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    if proc.info['name'] and proc.info['name'].lower() == 'hollow_knight.exe':
                        return proc
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass
        return None

    def _check_game_running(self):
        proc = self._find_game_process()
        if proc is not None:
            self.game_pid = proc.info['pid']
            if self.launch_btn.text() != "停止游戏":
                self.launch_btn.update_style(True)
        else:
            self.game_pid = None
            if self.launch_btn.text() != "启动游戏":
                self.launch_btn.update_style(False)

    def _handle_launch_or_stop(self):
        if self.launch_btn.text() == "停止游戏":
            self._stop_game()
        else:
            self._launch_game()

    def _stop_game(self):
        if self.game_pid is None:
            proc = self._find_game_process()
            if proc is None:
                return
            self.game_pid = proc.info['pid']

        try:
            reply = QMessageBox.question(
                self, "确认停止",
                "确定要强制停止游戏吗？未保存的进度可能会丢失！",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

            proc = psutil.Process(self.game_pid)
            proc.terminate()
            gone, alive = psutil.wait_procs([proc], timeout=5)
            if alive:
                proc.kill()

            self.game_pid = None
            self.launch_btn.update_style(False)
        except psutil.NoSuchProcess:
            self.game_pid = None
            self.launch_btn.update_style(False)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"停止游戏失败: {e}")

    def _launch_game(self):
        if not self._valid_path():
            return

        game_path = self.path_input.text()
        if game_path.endswith('.exe'):
            game_path = get_root_from_exe(game_path)

        try:
            import subprocess
            exe_path = os.path.join(game_path, "hollow_knight.exe")
            self.game_process = subprocess.Popen(
                [exe_path],
                cwd=game_path,
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            )
            self.game_pid = self.game_process.pid
            self.launch_btn.update_style(True)
        except Exception as e:
            QMessageBox.warning(self, "启动失败", str(e))

    # ==================== 功能按钮回调 ====================
    def _install_api(self):
        if not self._valid_path():
            return

        try:
            if not os.path.isfile(get_api_zip_path()):
                QMessageBox.warning(self, "错误", "API 压缩包不存在")
                return

            game_path = self.path_input.text()
            if game_path.endswith('.exe'):
                game_path = get_root_from_exe(game_path)

            install_api(game_path, self._log)
            QMessageBox.information(self, "完成", "API 安装完成")
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))

    def _restore(self):
        if not self._valid_path():
            return

        try:
            game_path = self.path_input.text()
            if game_path.endswith('.exe'):
                game_path = get_root_from_exe(game_path)

            restore_vanilla(game_path, self._log)
            QMessageBox.information(self, "完成", "已还原原版 dll")
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))

    def _install_mods(self):
        if not self._valid_path():
            return

        last_mod_path = self.settings.value("last_mod_path", "")

        files, _ = QFileDialog.getOpenFileNames(
            self, "选择 Mod 文件",
            last_mod_path,
            "Mod (*.zip *.dll);;All Files (*.*)"
        )
        if not files:
            return

        if files:
            self.settings.setValue("last_mod_path", os.path.dirname(files[0]))

        try:
            game_path = self.path_input.text()
            if game_path.endswith('.exe'):
                game_path = get_root_from_exe(game_path)

            install_mods(game_path, files, self._log)
            QMessageBox.information(self, "完成", "Mod 安装完成")
            QTimer.singleShot(500, lambda: self.page_local.refresh_mod_list(self.game_path))
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))

    def _open_mods(self):
        p = self.path_input.text().strip()
        if not p:
            QMessageBox.warning(self, "错误", "先设置游戏路径")
            return

        if p.endswith('.exe'):
            p = get_root_from_exe(p)

        d = get_mods_dir(p)
        os.makedirs(d, exist_ok=True)

        try:
            os.startfile(d)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))

    def _open_save(self):
        d = get_save_folder()
        if not d or not os.path.isdir(d):
            QMessageBox.warning(self, "错误", "存档文件夹不存在")
            return

        try:
            os.startfile(d)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))

    # ==================== 依赖相关 ====================
    def _auto_load_dependency(self):
        threading.Thread(target=self._load_dependency_task, daemon=True).start()

    def _load_dependency_task(self):
        success = self.resolver.load_from_url(MODLINKS_URL, self._log)
        QTimer.singleShot(0, lambda: self._on_load_finished(success))

    def _on_load_finished(self, success):
        if success:
            if self.page_online.isVisible():
                self.page_online.refresh_mod_list(self.game_path)
        else:
            QMessageBox.warning(self, "错误", "Mod链接加载失败，请检查网络连接后点击「更新链接」重试")

    def _reload_dependency(self):
        threading.Thread(target=self._load_dependency_task, daemon=True).start()

    def _check_missing_dependencies(self):
        if not self._valid_path():
            return

        if not self.resolver.is_loaded:
            QMessageBox.warning(self, "提示", "请先点击「更新链接」加载数据")
            return

        game_path = self.path_input.text()
        if game_path.endswith('.exe'):
            game_path = get_root_from_exe(game_path)

        mods_dir = get_mods_dir(game_path)
        if not os.path.exists(mods_dir):
            QMessageBox.information(self, "提示", "Mods 文件夹不存在，请先安装 Mod")
            return

        self._log("🔍 正在扫描已安装 Mod 的前置依赖...", "info")

        installed_mods = set()
        for item in os.listdir(mods_dir):
            item_path = os.path.join(mods_dir, item)
            if os.path.isdir(item_path):
                installed_mods.add(item)
            elif os.path.isfile(item_path) and item.endswith('.dll'):
                installed_mods.add(os.path.splitext(item)[0])

        if not installed_mods:
            QMessageBox.information(self, "提示", "Mods 文件夹为空")
            return

        missing = self.resolver.check_missing_dependencies(installed_mods)
        self.missing_deps = missing

        if missing is None:
            return

        if missing:
            self._log(f"⚠️ 缺失 {len(missing)} 个前置 Mod：{'、'.join(sorted(missing))}", "warning")
            show_missing_deps_dialog(self, missing, self.resolver)
        else:
            self._log("✅ 所有前置依赖完整", "success")
            QMessageBox.information(self, "检查完成", "所有已安装 Mod 的前置依赖完整！")

    # ==================== Mod错误检查 ====================
    def _check_mod_errors(self):
        if not self._valid_path():
            return

        game_path = self.path_input.text()
        if game_path.endswith('.exe'):
            game_path = get_root_from_exe(game_path)

        mods_dir = get_mods_dir(game_path)
        if not os.path.exists(mods_dir):
            QMessageBox.information(self, "提示", "Mods 文件夹不存在，请先安装 Mod")
            return

        self._log("🔍 正在检查 Mod 安装错误...", "info")

        errors = []
        root_dlls = []
        dll_owners = {}  # dll文件名 -> [所属文件夹列表]

        items = [item for item in os.listdir(mods_dir) if item != "Disabled"]

        for item in items:
            item_path = os.path.join(mods_dir, item)
            if os.path.isdir(item_path):
                dll_files = [f for f in os.listdir(item_path) if f.endswith('.dll')]
                for dll in dll_files:
                    name_lower = dll.lower()
                    if name_lower not in dll_owners:
                        dll_owners[name_lower] = []
                    dll_owners[name_lower].append(item)
            elif os.path.isfile(item_path) and item.endswith('.dll'):
                root_dlls.append(item)

        if root_dlls:
            self._log(f"⚠️ Mods 根目录存在 {len(root_dlls)} 个 .dll 文件（不会生效）", "warning")
            error_msg = "Mods根目录存在 .dll 文件（Mod不会生效）:\n"
            for dll in root_dlls:
                error_msg += f"  • {dll}\n"
            errors.append(error_msg)

        # 同名 dll 检测：同一 dll 名出现在多个不同文件夹
        dup_dlls = {k: v for k, v in dll_owners.items() if len(v) > 1}
        if dup_dlls:
            self._log(f"⚠️ 发现 {len(dup_dlls)} 个同名 .dll 文件冲突", "warning")
            errors.append(("同名dll文件冲突", dup_dlls))

        if errors:
            # 有结构化错误（tuple 类型）则用对话框渲染
            structured_errors = [e for e in errors if isinstance(e, tuple)]
            plain_errors = [e for e in errors if isinstance(e, str)]
            if structured_errors:
                # 把 plain 错误也转成结构化，统一用对话框显示
                if plain_errors:
                    structured_errors.append(("Mods根目录存在 .dll 文件", {"_items": plain_errors}))
                show_mod_errors_dialog(self, structured_errors)
            else:
                full_error_msg = "发现以下Mod安装错误:\n\n"
                for i, error in enumerate(errors, 1):
                    full_error_msg += f"{i}. {error}\n"
                QMessageBox.warning(self, "Mod错误检查", full_error_msg)
        else:
            self._log("✅ Mod 错误检查通过，未发现异常", "success")
            QMessageBox.information(self, "检查完成", "所有Mod安装正确，未发现错误！")

    # ==================== 窗口事件 ====================
    def closeEvent(self, event):
        self.monitor_timer.stop()
        event.accept()