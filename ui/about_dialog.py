# -*- coding: utf-8 -*-
"""关于对话框 - 从远程加载 Markdown 内容"""
import re
import requests
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QFrame,
    QMessageBox,
)
from PySide6.QtGui import QFont


class AboutMarkdownDialog(QDialog):
    """关于对话框 - 从远程加载 Markdown 并渲染"""

    # 默认使用 README.md
    REMOTE_URL = "https://cdn.jsdelivr.net/gh/mioshk/KnightModder@main/README.md"

    def __init__(self, parent=None, url=None, title="关于"):
        super().__init__(parent)
        self.parent = parent
        # 如果传入了 url，使用传入的；否则使用默认
        self.remote_url = url if url else self.REMOTE_URL
        self.dialog_title = title
        self._setup_ui()
        self._load_content()

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

        # 标题行
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

        # 分隔线
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

        # ✅ 底部按钮 - 只有关闭
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
        """加载远程内容"""
        self.content_area.setHtml('<div style="color:#888888; text-align:center; padding:40px 0;">加载中...</div>')
        self.version_label.setText("加载中...")

        self.loader = MdLoader(self.remote_url)
        self.loader.finished.connect(self._on_content_loaded)
        self.loader.start()

    def _on_content_loaded(self, success, content):
        """内容加载完成"""
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
        """本地默认内容"""
        return """
## 内容加载失败

请检查网络连接后点击「刷新」重试。
"""

    def _extract_version(self, content):
        """从 Markdown 中提取版本号"""
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