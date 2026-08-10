# -*- coding: utf-8 -*-
"""
对话框模块
包含关于、缺失依赖、Mod错误、Markdown内容显示等各类对话框
"""
import os
import re
import requests

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QScrollArea,
    QWidget,
    QFrame,
    QMessageBox,
    QApplication,
    QSizePolicy,
    QTextBrowser,
)
from PySide6.QtGui import QFont

from config import (
    APP_NAME,
    COLOR_ACCENT_BLUE,
    COLOR_ACCENT_RED,
    COLOR_ACCENT_ORANGE,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_TEXT_TERTIARY,
    COLOR_INPUT_BG,
    COLOR_BORDER,
)
from ui.styles import DARK_STYLE_SHEET


def show_about_dialog(parent):
    """显示关于对话框"""
    dialog = QDialog(parent)
    dialog.setWindowTitle("关于")
    dialog.setFixedWidth(360)
    dialog.setStyleSheet(DARK_STYLE_SHEET)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(28, 26, 28, 24)
    layout.setSpacing(14)

    # 图标
    icon_row = QHBoxLayout()
    icon_row.addStretch()
    icon = QLabel("⚔️")
    icon.setStyleSheet("font-size: 40px; background: transparent;")
    icon.setAlignment(Qt.AlignCenter)
    icon_row.addWidget(icon)
    icon_row.addStretch()
    layout.addLayout(icon_row)

    # 名称
    name_label = QLabel(APP_NAME)
    name_label.setObjectName("headingLabel")
    name_label.setAlignment(Qt.AlignCenter)
    layout.addWidget(name_label)

    # 作者
    author_label = QLabel(
        '作者：B站 '
        '<a href="https://space.bilibili.com/538844794" '
        f'style="color:{COLOR_ACCENT_BLUE}; text-decoration:none; font-weight:bold;">[MioSs-]</a>'
    )
    author_label.setTextFormat(Qt.RichText)
    author_label.setOpenExternalLinks(True)
    author_label.setAlignment(Qt.AlignCenter)
    author_label.setStyleSheet(
        f"background: transparent; color:{COLOR_TEXT_SECONDARY}; font-size: 13px;"
    )
    layout.addWidget(author_label)

    # 关闭按钮
    close_btn = QPushButton("关闭")
    close_btn.setObjectName("btnSecondary")
    close_btn.clicked.connect(dialog.accept)
    layout.addWidget(close_btn)

    dialog.exec()


def show_path_select_dialog(parent, paths_data):
    """
    显示多游戏路径选择对话框
    :param paths_data: [(exe_path, root_path), ...]
    :return: 选中的root_path，取消返回None
    """
    dialog = QDialog(parent)
    dialog.setWindowTitle("选择游戏安装目录")
    dialog.setMinimumWidth(500)
    dialog.setMinimumHeight(350)
    dialog.setStyleSheet(DARK_STYLE_SHEET)

    layout = QVBoxLayout(dialog)
    layout.setSpacing(16)

    title_label = QLabel("检测到多个游戏安装，请选择：")
    title_label.setObjectName("headingLabel")
    layout.addWidget(title_label)

    list_widget = QListWidget()
    for exe, root in paths_data:
        list_widget.addItem(root)
    layout.addWidget(list_widget)

    selected_path = [None]

    btn_row = QHBoxLayout()
    ok_btn = QPushButton("确认")
    ok_btn.setObjectName("btnSecondary")
    cancel_btn = QPushButton("取消")
    cancel_btn.setObjectName("btnGhost")
    btn_row.addStretch()
    btn_row.addWidget(ok_btn)
    btn_row.addWidget(cancel_btn)
    layout.addLayout(btn_row)

    def on_ok():
        selected = list_widget.currentItem()
        if selected:
            selected_path[0] = selected.text()
            dialog.accept()
        else:
            QMessageBox.warning(dialog, "提示", "请选择一个路径")

    ok_btn.clicked.connect(on_ok)
    cancel_btn.clicked.connect(dialog.reject)

    dialog.exec()
    return selected_path[0]


def show_missing_deps_dialog(parent, missing_deps, resolver):
    """
    显示缺失的前置依赖对话框
    :param missing_deps: 缺失的Mod名称集合
    :param resolver: DependencyResolver实例
    """
    dialog = QDialog(parent)
    dialog.setWindowTitle("缺失的前置依赖")
    dialog.setMinimumSize(600, 450)
    dialog.setStyleSheet(DARK_STYLE_SHEET)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(28, 22, 28, 22)
    layout.setSpacing(12)

    # 标题行
    title = QLabel("⚠️ 缺失的前置依赖")
    title.setObjectName("headingLabel")
    layout.addWidget(title)

    info = QLabel(f"共 {len(missing_deps)} 个缺失的前置依赖，点击Mod名称可跳转下载链接")
    info.setStyleSheet(
        f"color: {COLOR_TEXT_SECONDARY}; background: transparent; font-size: 12px;"
    )
    layout.addWidget(info)

    links = resolver.get_mod_links(missing_deps)

    # 滚动区域 - 修正：让内容从上到下排列
    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    scroll_area.setStyleSheet(f"""
        QScrollArea {{
            background-color: {COLOR_INPUT_BG};
            border: 1px solid {COLOR_BORDER};
            border-radius: 8px;
        }}
        QScrollArea > QWidget > QWidget {{
            background: transparent;
        }}
    """)

    scroll_content = QWidget()
    scroll_content.setStyleSheet("background: transparent;")
    scroll_layout = QVBoxLayout(scroll_content)
    scroll_layout.setSpacing(4)
    scroll_layout.setContentsMargins(12, 8, 12, 8)
    scroll_layout.setAlignment(Qt.AlignTop)

    for mod_name in sorted(missing_deps):
        link = links.get(mod_name)
        row_widget = QWidget()
        row_widget.setStyleSheet("background: transparent; border: none;")
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(4, 3, 4, 3)

        if link:
            link_label = QLabel(
                f'<a href="{link}" style="color: {COLOR_TEXT_PRIMARY}; '
                f'text-decoration: underline; font-weight: 500;">{mod_name}</a>'
            )
            link_label.setOpenExternalLinks(True)
            link_label.setStyleSheet("background: transparent; border: none;")
            link_label.setTextFormat(Qt.RichText)
            row_layout.addWidget(link_label)
        else:
            name_label = QLabel(mod_name)
            name_label.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; background: transparent; border: none;")
            row_layout.addWidget(name_label)

        row_layout.addStretch()
        scroll_layout.addWidget(row_widget)

    scroll_area.setWidget(scroll_content)
    layout.addWidget(scroll_area, stretch=1)

    # 按钮行
    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)

    get_all_btn = QPushButton("📋 获取全部链接")
    get_all_btn.setObjectName("btnSecondary")

    def get_all_links():
            link_text = ""
            for mod_name in sorted(links.keys()):
                link = links.get(mod_name)
                if link:
                    link_text += f"{mod_name}: {link}\n"

            if not link_text:
                get_all_btn.setText("❌ 无可用链接")
                return

            QApplication.clipboard().setText(link_text.strip())

            get_all_btn.setText("✅ 已复制")
            get_all_btn.setEnabled(False)

    get_all_btn.clicked.connect(get_all_links)
    btn_row.addWidget(get_all_btn)
    btn_row.addStretch()

    close_btn = QPushButton("关闭")
    close_btn.setObjectName("btnSecondary")
    close_btn.clicked.connect(dialog.accept)
    btn_row.addWidget(close_btn)

    layout.addLayout(btn_row)
    dialog.exec()


def show_mod_errors_dialog(parent, errors):
    """
    显示Mod错误检查报告对话框
    :param errors: 错误列表 [(error_type, error_data), ...]
    """
    dialog = QDialog(parent)
    dialog.setWindowTitle("Mod 错误检查报告")
    dialog.setMinimumSize(600, 450)
    dialog.setStyleSheet(DARK_STYLE_SHEET)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(28, 22, 28, 22)
    layout.setSpacing(12)

    title = QLabel("⚠️ Mod 安装错误报告")
    title.setObjectName("headingLabel")
    layout.addWidget(title)

    info = QLabel(f"共发现 {len(errors)} 类错误，请及时修复以免游戏报错")
    info.setStyleSheet(
        f"color: {COLOR_TEXT_SECONDARY}; background: transparent; font-size: 12px;"
    )
    layout.addWidget(info)

    # 滚动区域
    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    scroll_area.setStyleSheet(f"""
        QScrollArea {{
            background-color: {COLOR_INPUT_BG};
            border: 1px solid {COLOR_BORDER};
            border-radius: 8px;
        }}
        QScrollArea > QWidget > QWidget {{
            background: transparent;
        }}
    """)

    scroll_content = QWidget()
    scroll_content.setStyleSheet("background: transparent;")
    scroll_layout = QVBoxLayout(scroll_content)
    scroll_layout.setSpacing(8)
    scroll_layout.setContentsMargins(12, 10, 12, 10)
    scroll_layout.setAlignment(Qt.AlignTop)

    for error_type, error_data in errors:
        type_label = QLabel(f"❌ {error_type}")
        type_label.setStyleSheet(
            f"color: {COLOR_ACCENT_RED}; font-weight: bold; font-size: 13px; background: transparent; border: none;"
        )
        scroll_layout.addWidget(type_label)

        if error_type == "Mods目录存在 .dll 文件":
            for dll in error_data:
                item_label = QLabel(f"  📄 {dll}")
                item_label.setStyleSheet(
                    f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; background: transparent; border: none;"
                )
                scroll_layout.addWidget(item_label)

        elif error_type == "同一文件夹内存在多个 .dll 文件":
            for folder_name, dll_list in error_data:
                folder_label = QLabel(f"  📁 {folder_name}")
                folder_label.setStyleSheet(
                    f"color: {COLOR_ACCENT_ORANGE}; font-size: 12px; background: transparent; border: none;"
                )
                scroll_layout.addWidget(folder_label)
                for dll in dll_list:
                    dll_label = QLabel(f"    • {dll}")
                    dll_label.setStyleSheet(
                        f"color: {COLOR_TEXT_TERTIARY}; font-size: 12px; background: transparent; border: none;"
                    )
                    scroll_layout.addWidget(dll_label)

        elif error_type == "同名dll文件冲突":
            for dll_name, folders in error_data.items():
                conflict_label = QLabel(f"  ⚡ {dll_name}")
                conflict_label.setStyleSheet(
                    f"color: {COLOR_ACCENT_RED}; font-size: 12px; background: transparent; border: none;"
                )
                scroll_layout.addWidget(conflict_label)
                for folder in folders:
                    folder_item = QLabel(f"    📁 {folder}")
                    folder_item.setStyleSheet(
                        f"color: {COLOR_TEXT_TERTIARY}; font-size: 12px; background: transparent; border: none;"
                    )
                    scroll_layout.addWidget(folder_item)

        elif error_type == "存在重复的Mod":
            for clean_name, items in error_data.items():
                name_label = QLabel(f"  🔄 {clean_name}")
                name_label.setStyleSheet(
                    f"color: {COLOR_ACCENT_ORANGE}; font-size: 12px; background: transparent; border: none;"
                )
                scroll_layout.addWidget(name_label)
                for item_type, name in items:
                    item_label = QLabel(f"    • {item_type}: {name}")
                    item_label.setStyleSheet(
                        f"color: {COLOR_TEXT_TERTIARY}; font-size: 12px; background: transparent; border: none;"
                    )
                    scroll_layout.addWidget(item_label)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {COLOR_BORDER}; max-height: 1px; border: none;")
        scroll_layout.addWidget(line)

    scroll_area.setWidget(scroll_content)
    layout.addWidget(scroll_area, stretch=1)

    # 关闭按钮
    btn_row = QHBoxLayout()
    btn_row.addStretch()
    close_btn = QPushButton("关闭")
    close_btn.setObjectName("btnSecondary")
    close_btn.clicked.connect(dialog.accept)
    btn_row.addWidget(close_btn)
    layout.addLayout(btn_row)

    dialog.exec()


# ============================================================
# Markdown 内容对话框（原 about_dialog.py）
# ============================================================

class AboutMarkdownDialog(QDialog):
    """从远程加载 Markdown 并渲染的对话框"""

    REMOTE_URL = "https://cdn.jsdelivr.net/gh/mioshk/KnightModder@main/README.md"

    def __init__(self, parent=None, url=None, title="关于"):
        super().__init__(parent)
        self.parent = parent
        self.remote_url = url if url else self.REMOTE_URL
        self.dialog_title = title
        self.loader = None
        self._setup_ui()
        self._load_content()

    def done(self, result):
        """关闭对话框时安全清理后台加载线程"""
        if self.loader is not None:
            try:
                self.loader.finished.disconnect(self._on_content_loaded)
            except Exception:
                pass
            if self.loader.isRunning():
                self.loader.quit()
                if not self.loader.wait(2000):
                    self.loader.terminate()
                    self.loader.wait(1000)
            self.loader = None
        super().done(result)

    def _setup_ui(self):
        self.setWindowTitle(self.dialog_title)
        self.setMinimumSize(580, 480)
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(12)

        title_row = QHBoxLayout()
        icon_label = QLabel("⚔️")
        icon_label.setStyleSheet("font-size: 24px; background: transparent;")
        title_row.addWidget(icon_label)

        title_label = QLabel(self.dialog_title)
        title_label.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        title_label.setStyleSheet("color: #ffffff; background: transparent;")
        title_row.addWidget(title_label)

        title_row.addStretch()

        self.version_label = QLabel("加载中...")
        self.version_label.setStyleSheet("color: #888888; font-size: 12px; background: transparent;")
        title_row.addWidget(self.version_label)

        layout.addLayout(title_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #333333; max-height: 1px; border: none;")
        layout.addWidget(sep)

        self.content_area = QTextBrowser()
        self.content_area.setOpenExternalLinks(True)
        self.content_area.setStyleSheet("""
            QTextBrowser {
                background-color: #1e1e1e;
                border: 1px solid #333333;
                border-radius: 8px;
                padding: 16px 18px;
            }
        """)
        layout.addWidget(self.content_area)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.setObjectName("btnSecondary")
        close_btn.clicked.connect(self.accept)
        close_btn.setFixedHeight(32)
        close_btn.setStyleSheet("padding: 4px 16px;")
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _load_content(self):
        self.content_area.setHtml('<div style="color:#888888; text-align:center; padding:40px 0;">加载中...</div>')
        self.version_label.setText("加载中...")

        self.loader = MdLoader(self.remote_url)
        self.loader.finished.connect(self._on_content_loaded)
        self.loader.start()

    def _on_content_loaded(self, success, content):
        if success and content:
            self.content_area.setMarkdown(content)
        else:
            self.content_area.setMarkdown(self._get_default_content())

        version = self._extract_version(content if success else "")
        if version:
            self.version_label.setText(f"v{version}")
        else:
            self.version_label.setText("")

    def _get_default_content(self):
        return """
## 内容加载失败

请检查网络连接后重试。
"""

    def _extract_version(self, content):
        if not content:
            return ""
        match = re.search(r'[-*]?\s*版本[：:]\s*v?([\d.]+)', content)
        if match:
            return match.group(1)
        return ""


class MdLoader(QThread):
    """后台线程加载远程 Markdown"""
    finished = Signal(bool, str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            response = requests.get(self.url, timeout=10)
            if response.status_code == 200:
                self.finished.emit(True, response.text)
            else:
                self.finished.emit(False, "")
        except Exception:
            self.finished.emit(False, "")
