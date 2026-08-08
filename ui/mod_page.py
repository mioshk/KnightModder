# -*- coding: utf-8 -*-
"""模组管理页面"""
import os
import re
import webbrowser
from PySide6.QtCore import Qt, QTimer, QSignalBlocker, QSize
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextEdit,
    QScrollArea,
    QMessageBox,
    QApplication,
    QSizePolicy,
    QLineEdit,
    QComboBox,
    QFrame,
    QSpacerItem,
    QCheckBox,
    QToolButton,
)
from PySide6.QtGui import QFont, QColor, QPalette, QIcon, QPixmap, QPainter, QPaintEvent
from utils import get_mods_dir
from core import disable_mod, enable_mod, delete_mod, is_mod_enabled


def get_modlog_path():
    """获取 ModLog.txt 文件路径"""
    user_profile = os.environ.get('USERPROFILE', os.path.expanduser('~'))
    return os.path.join(user_profile, 'AppData', 'LocalLow', 'Team Cherry', 'Hollow Knight', 'ModLog.txt')


def parse_modlog():
    if not os.path.isfile(get_modlog_path()):
        return {}

    result = {}
    try:
        with open(get_modlog_path(), 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line.startswith('[INFO]:[API] -'):
                    continue

                content = line.replace('[INFO]:[API] -', '', 1).strip()
                match = re.match(r'^(.+?)\s*:\s*([\d.]+(?:-[a-f0-9]+)?)$', content)
                if match:
                    name = match.group(1).strip()
                    version = match.group(2).strip()
                    main_version = version.split('-')[0].strip()
                    normalized = normalize_name(name)
                    result[normalized] = (name, main_version)
    except Exception:
        pass

    return result


def normalize_name(name):
    name = name.lower()
    name = re.sub(r'[ \-_\.]', '', name)
    return name


def normalize_version(version):
    if not version:
        return version

    main_version = version.split('-')[0].strip()
    parts = main_version.split('.')

    while len(parts) > 1 and parts[-1] == '0':
        parts.pop()

    return '.'.join(parts)


# ============================================================
# 通用样式工具
# ============================================================

def _section_card_style(border_color="#252525"):
    return f"""
        QFrame {{
            background-color: #1c1c1e;
            border: 1px solid {border_color};
            border-radius: 12px;
        }}
    """


def _divider_line(color="#2e2e30"):
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Plain)
    line.setStyleSheet(f"border: none; background-color: {color}; max-height: 1px;")
    line.setFixedHeight(1)
    return line


def _make_section_header(icon, title):
    lbl = QLabel(f"{icon}  {title}")
    lbl.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
    lbl.setStyleSheet("""
        QLabel {
            color: #a0a0a8;
            background: transparent;
            border: none;
            padding: 0px;
            letter-spacing: 1px;
        }
    """)
    return lbl


# ============================================================
# 自定义详情卡片组件
# ============================================================

class DetailCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_section_card_style())
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 14, 18, 14)
        self._layout.setSpacing(8)

    def add_header(self, icon, title):
        self._layout.addWidget(_make_section_header(icon, title))

    def add_divider(self, color="#2e2e30"):
        self._layout.addWidget(_divider_line(color))

    def add_widget(self, widget):
        self._layout.addWidget(widget)

    def add_spacer(self, height=6):
        spacer = QSpacerItem(0, height, QSizePolicy.Minimum, QSizePolicy.Fixed)
        self._layout.addItem(spacer)

    def clear_content(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()


class StatusBadge(QLabel):
    def __init__(self, text, color, bg_color, parent=None):
        super().__init__(text, parent)
        self.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background-color: {bg_color};
                border: none;
                border-radius: 10px;
                padding: 3px 14px;
                font-size: 12px;
                letter-spacing: 0.5px;
            }}
        """)
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)


class DepItem(QFrame):
    def __init__(self, mod_name, installed, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        icon_text = "✅" if installed else "❌"
        name_color = "#34c759" if installed else "#ff6b6b"

        icon_lbl = QLabel(icon_text)
        icon_lbl.setFont(QFont("Segoe UI Emoji", 13))
        icon_lbl.setFixedWidth(22)
        icon_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_lbl)

        name_lbl = QLabel(mod_name)
        name_lbl.setFont(QFont("Microsoft YaHei", 12))
        name_lbl.setStyleSheet(f"""
            QLabel {{
                color: {name_color};
                background: transparent;
                border: none;
                padding: 0px;
            }}
        """)
        layout.addWidget(name_lbl)
        layout.addStretch()


# ============================================================
# 列表项组件
# ============================================================

class ModListItemWidget(QWidget):
    def __init__(self, mod_name, display_name, enabled=True, parent=None, list_item=None):
        super().__init__(parent)

        self.mod_name = mod_name
        self.display_name = display_name
        self.enabled = enabled
        self.is_selected = False
        self.list_item = list_item
        self.list_widget = parent

        self.setStyleSheet("background: transparent; border: none;")
        self.setAutoFillBackground(False)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(0)

        self.bg_frame = QFrame()
        self.bg_frame.setFixedHeight(50)
        self.bg_frame.setFrameShape(QFrame.NoFrame)
        self._update_bg_style()

        bg_layout = QHBoxLayout(self.bg_frame)
        bg_layout.setContentsMargins(14, 6, 14, 6)
        bg_layout.setSpacing(10)

        self.status_dot = QLabel()
        self.status_dot.setFixedSize(10, 10)
        self.status_dot.setMinimumSize(10, 10)
        self.status_dot.setMaximumSize(10, 10)
        self._update_status_dot(enabled)
        bg_layout.addWidget(self.status_dot)

        self.name_label = QLabel(display_name)
        self.name_label.setFont(QFont("Microsoft YaHei", 11))
        self.name_label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                background: transparent;
                border: none;
                padding: 0px;
            }
        """)
        self.name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bg_layout.addWidget(self.name_label)

        bg_layout.addStretch()

        self.status_label = QLabel("已启用" if enabled else "已禁用")
        self.status_label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        if enabled:
            self.status_label.setStyleSheet("""
                QLabel {
                    color: #34c759;
                    background: transparent;
                    border: none;
                    padding: 0px;
                    font-size: 11px;
                }
            """)
        else:
            self.status_label.setStyleSheet("""
                QLabel {
                    color: #888888;
                    background: transparent;
                    border: none;
                    padding: 0px;
                    font-size: 11px;
                }
            """)
        bg_layout.addWidget(self.status_label)

        main_layout.addWidget(self.bg_frame)
        self.setFixedHeight(58)

    def _update_bg_style(self):
        if self.is_selected:
            self.bg_frame.setStyleSheet("""
                QFrame {
                    background-color: #0d2b0d;
                    border-radius: 8px;
                    border: 2px solid #34c759;
                }
                QFrame * {
                    background: transparent;
                }
            """)
        else:
            self.bg_frame.setStyleSheet("""
                QFrame {
                    background-color: #191919;
                    border-radius: 8px;
                    border: 1px solid #333333;
                }
                QFrame:hover {
                    background-color: #2a2a2a;
                }
                QFrame * {
                    background: transparent;
                }
            """)

    def _update_status_dot(self, enabled):
        color = "#34c759" if enabled else "#666666"
        self.status_dot.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                border-radius: 5px;
                min-width: 10px;
                min-height: 10px;
                max-width: 10px;
                max-height: 10px;
                border: none;
            }}
        """)

    def set_selected(self, selected):
        self.is_selected = selected
        self._update_bg_style()

    def update_status(self, enabled):
        self.enabled = enabled
        self._update_status_dot(enabled)
        self.status_label.setText("已开启" if enabled else "已关闭")
        if enabled:
            self.status_label.setStyleSheet("""
                QLabel {
                    color: #34c759;
                    background: transparent;
                    border: none;
                    padding: 0px;
                    font-size: 11px;
                }
            """)
        else:
            self.status_label.setStyleSheet("""
                QLabel {
                    color: #888888;
                    background: transparent;
                    border: none;
                    padding: 0px;
                    font-size: 11px;
                }
            """)


class OnlineModListItemWidget(QWidget):
    def __init__(self, mod_name, display_name, is_installed=False, has_update=False, parent=None, list_item=None):
        super().__init__(parent)

        self.mod_name = mod_name
        self.display_name = display_name
        self.is_installed = is_installed
        self.has_update = has_update
        self.is_selected = False
        self.list_item = list_item
        self.list_widget = parent

        self.setStyleSheet("background: transparent; border: none;")
        self.setAutoFillBackground(False)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(0)

        self.bg_frame = QFrame()
        self.bg_frame.setFixedHeight(50)
        self.bg_frame.setFrameShape(QFrame.NoFrame)
        self._update_bg_style()

        bg_layout = QHBoxLayout(self.bg_frame)
        bg_layout.setContentsMargins(14, 6, 14, 6)
        bg_layout.setSpacing(10)

        self.status_dot = QLabel()
        self.status_dot.setFixedSize(10, 10)
        self._update_status_dot()
        bg_layout.addWidget(self.status_dot)

        self.name_label = QLabel(display_name)
        self.name_label.setFont(QFont("Microsoft YaHei", 11))
        self.name_label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                background: transparent;
                border: none;
                padding: 0px;
            }
        """)
        self.name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.name_label.setWordWrap(False)
        self.name_label.setTextFormat(Qt.PlainText)
        bg_layout.addWidget(self.name_label)

        bg_layout.addStretch()

        self.action_btn = QPushButton()
        self.action_btn.setFixedSize(64, 28)
        self.action_btn.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        self._update_action_btn()
        bg_layout.addWidget(self.action_btn)

        main_layout.addWidget(self.bg_frame)
        self.setFixedHeight(58)

    def _update_bg_style(self):
        if self.is_selected:
            self.bg_frame.setStyleSheet("""
                QFrame {
                    background-color: #0d2b0d;
                    border-radius: 8px;
                    border: 2px solid #34c759;
                }
                QFrame * {
                    background: transparent;
                }
            """)
        else:
            self.bg_frame.setStyleSheet("""
                QFrame {
                    background-color: #191919;
                    border-radius: 8px;
                    border: 1px solid #333333;
                }
                QFrame:hover {
                    background-color: #2a2a2a;
                }
                QFrame * {
                    background: transparent;
                }
            """)

    def _update_status_dot(self):
        if self.has_update:
            color = "#ff9500"
        elif self.is_installed:
            color = "#34c759"
        else:
            color = "#ff6b6b"

        self.status_dot.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                border-radius: 5px;
                min-width: 10px;
                min-height: 10px;
                max-width: 10px;
                max-height: 10px;
                border: none;
            }}
        """)

    def _update_action_btn(self):
        if self.has_update:
            self.action_btn.setText("待更新")
            self.action_btn.setCursor(Qt.PointingHandCursor)
            self.action_btn.setEnabled(True)
            self.action_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ff9500;
                    color: white;
                    border: none;
                    border-radius: 14px;
                    font-size: 11px;
                    font-weight: 700;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #e68a00;
                }
                QPushButton:pressed {
                    background-color: #cc7a00;
                }
            """)
        elif self.is_installed:
            self.action_btn.setText("已安装")
            self.action_btn.setCursor(Qt.ArrowCursor)
            self.action_btn.setEnabled(False)
            self.action_btn.setStyleSheet("""
                QPushButton {
                    background-color: #444444;
                    color: #888888;
                    border: none;
                    border-radius: 14px;
                    font-size: 11px;
                    font-weight: 700;
                    padding: 0px;
                }
            """)
        else:
            self.action_btn.setText("安装")
            self.action_btn.setCursor(Qt.PointingHandCursor)
            self.action_btn.setEnabled(True)
            self.action_btn.setStyleSheet("""
                QPushButton {
                    background-color: #007aff;
                    color: white;
                    border: none;
                    border-radius: 14px;
                    font-size: 11px;
                    font-weight: 700;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #0062cc;
                }
                QPushButton:pressed {
                    background-color: #004a99;
                }
            """)

    def set_status(self, is_installed, has_update=False):
        self.is_installed = is_installed
        self.has_update = has_update
        self._update_status_dot()
        self._update_action_btn()

    def set_selected(self, selected):
        self.is_selected = selected
        self._update_bg_style()


# ============================================================
# 详情面板
# ============================================================

class ModDetailPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(14)

        # 标题卡片
        self.title_card = QFrame()
        self.title_card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a2a1a, stop:1 #1c1c2e);
                border: 1px solid #2a3a2a;
                border-radius: 14px;
            }
        """)
        title_layout = QVBoxLayout(self.title_card)
        title_layout.setContentsMargins(22, 18, 22, 18)
        title_layout.setSpacing(6)

        title_top_row = QHBoxLayout()
        title_top_row.setSpacing(10)
        title_top_row.setContentsMargins(0, 0, 0, 0)

        self.title_en = QLabel("")
        self.title_en.setFont(QFont("Microsoft YaHei", 20, QFont.Bold))
        self.title_en.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background: transparent;
                border: none;
                padding: 0px;
                letter-spacing: 0.5px;
            }
        """)
        self.title_en.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        title_top_row.addWidget(self.title_en)

        self.version_badge = QLabel("")
        self.version_badge.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        self.version_badge.setStyleSheet("""
            QLabel {
                color: #007aff;
                background-color: rgba(0, 122, 255, 0.15);
                border: 1px solid rgba(0, 122, 255, 0.35);
                border-radius: 10px;
                padding: 2px 12px;
                font-size: 12px;
            }
        """)
        self.version_badge.setFixedHeight(22)
        self.version_badge.setAlignment(Qt.AlignCenter)
        title_top_row.addWidget(self.version_badge)

        title_layout.addLayout(title_top_row)
        self.main_layout.addWidget(self.title_card)

        # 状态卡片
        self.status_card = DetailCard()
        status_inner = QHBoxLayout()
        status_inner.setContentsMargins(0, 0, 0, 0)
        status_inner.setSpacing(10)

        self.status_label = QLabel("")
        self.status_label.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        self.status_label.setStyleSheet("color: #ffffff; background: transparent; border: none;")
        status_inner.addWidget(self.status_label)
        status_inner.addStretch()

        self.status_badge_container = QWidget()
        self.status_badge_layout = QHBoxLayout(self.status_badge_container)
        self.status_badge_layout.setContentsMargins(0, 0, 0, 0)
        self.status_badge_layout.setSpacing(8)
        status_inner.addWidget(self.status_badge_container)

        self.status_card.add_widget(self._wrap_in_layout_widget(status_inner))
        self.main_layout.addWidget(self.status_card)

        # 描述卡片
        self.desc_card = DetailCard()
        self.desc_card.add_header("📝", "描  述")
        self.desc_card.add_divider()

        self.desc_cn_lbl = QLabel("")
        self.desc_cn_lbl.setFont(QFont("Microsoft YaHei", 13))
        self.desc_cn_lbl.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                background: transparent;
                border: none;
                padding: 0px;
            }
        """)
        self.desc_cn_lbl.setWordWrap(True)
        self.desc_cn_lbl.setTextFormat(Qt.RichText)
        self.desc_card.add_widget(self.desc_cn_lbl)

        self.desc_en_lbl = QLabel("")
        self.desc_en_lbl.setFont(QFont("Microsoft YaHei", 12))
        self.desc_en_lbl.setStyleSheet("""
            QLabel {
                color: #a0a0a8;
                background: transparent;
                border: none;
                padding: 0px;
            }
        """)
        self.desc_en_lbl.setWordWrap(True)
        self.desc_en_lbl.setTextFormat(Qt.RichText)
        self.desc_card.add_widget(self.desc_en_lbl)

        self.main_layout.addWidget(self.desc_card)

        # 依赖卡片
        self.deps_card = DetailCard()
        self.deps_card.add_header("🔗", "前置依赖")
        self.deps_card.add_divider()
        self.deps_list_widget = QWidget()
        self.deps_list_layout = QVBoxLayout(self.deps_list_widget)
        self.deps_list_layout.setContentsMargins(0, 0, 0, 0)
        self.deps_list_layout.setSpacing(4)
        self.deps_card.add_widget(self.deps_list_widget)
        self.main_layout.addWidget(self.deps_card)

        # 联动卡片
        self.integ_card = DetailCard()
        self.integ_card.add_header("🔌", "联动 Mod")
        self.integ_card.add_divider()
        self.integ_list_widget = QWidget()
        self.integ_list_layout = QVBoxLayout(self.integ_list_widget)
        self.integ_list_layout.setContentsMargins(0, 0, 0, 0)
        self.integ_list_layout.setSpacing(4)
        self.integ_card.add_widget(self.integ_list_widget)
        self.main_layout.addWidget(self.integ_card)

        self.main_layout.addStretch()

        self._dep_checker = None
        self._show_empty_state()

    def _wrap_in_layout_widget(self, layout):
        w = QWidget()
        w.setStyleSheet("background: transparent; border: none;")
        w.setLayout(layout)
        return w

    def _clear_status_badges(self):
        while self.status_badge_layout.count():
            item = self.status_badge_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _add_status_badge(self, text, color, bg_color):
        badge = StatusBadge(text, color, bg_color)
        self.status_badge_layout.addWidget(badge)

    def _clear_deps_list(self):
        while self.deps_list_layout.count():
            item = self.deps_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _clear_integ_list(self):
        while self.integ_list_layout.count():
            item = self.integ_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _show_empty_state(self):
        self.title_en.setText("选择一个模组")
        self.title_en.setStyleSheet("color: #555555; background: transparent; border: none;")
        self.version_badge.setText("")
        self.version_badge.setVisible(False)
        self.status_label.setText("👈 点击左侧列表查看详情")
        self.status_label.setStyleSheet("color: #666666; background: transparent; border: none;")
        self._clear_status_badges()
        self.desc_card.setVisible(False)
        self.deps_card.setVisible(False)
        self.integ_card.setVisible(False)

    def set_mod_info(
        self,
        mod_name,
        chinese_name="",
        version="",
        enabled=None,
        is_installed=None,
        has_update=None,
        desc_cn="",
        desc_en="",
        dependencies=None,
        integrations=None,
        is_online_page=False,
    ):
        self.title_en.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background: transparent;
                border: none;
                padding: 0px;
                letter-spacing: 0.5px;
            }
        """)
        self.title_en.setText(f"{mod_name}（{chinese_name}）" if chinese_name else mod_name)

        if version:
            self.version_badge.setText(f"v{version}")
            self.version_badge.setVisible(True)
        else:
            self.version_badge.setText("")
            self.version_badge.setVisible(False)

        self._clear_status_badges()

        if is_online_page:
            if has_update:
                self.status_label.setText("🔄 发现新版本")
                self.status_label.setStyleSheet("color: #ff9500; background: transparent; border: none;")
                self._add_status_badge("待更新", "#ffffff", "#ff9500")
            elif is_installed:
                self.status_label.setText("✅ 已安装到本地")
                self.status_label.setStyleSheet("color: #34c759; background: transparent; border: none;")
                self._add_status_badge("已安装", "#ffffff", "#34c759")
            else:
                self.status_label.setText("📥 尚未安装")
                self.status_label.setStyleSheet("color: #ff6b6b; background: transparent; border: none;")
                self._add_status_badge("未安装", "#ffffff", "#ff6b6b")
        else:
            if enabled:
                self.status_label.setText("✅ 模组已启用")
                self.status_label.setStyleSheet("color: #34c759; background: transparent; border: none;")
                self._add_status_badge("已启用", "#ffffff", "#34c759")
            else:
                self.status_label.setText("⛔ 模组已禁用")
                self.status_label.setStyleSheet("color: #ff6b6b; background: transparent; border: none;")
                self._add_status_badge("已禁用", "#ffffff", "#888888")

        has_desc = bool(desc_cn.strip() or desc_en.strip())
        self.desc_card.setVisible(has_desc)

        self.desc_cn_lbl.setText(desc_cn if desc_cn.strip() else "")
        self.desc_cn_lbl.setVisible(bool(desc_cn.strip()))

        self.desc_en_lbl.setText(desc_en if desc_en.strip() else "")
        self.desc_en_lbl.setVisible(bool(desc_en.strip()))

        deps = dependencies or []
        self.deps_card.setVisible(bool(deps))
        self._clear_deps_list()
        for dep_name in deps:
            dep_installed = self._dep_checker(dep_name) if self._dep_checker else False
            self.deps_list_layout.addWidget(DepItem(dep_name, dep_installed))

        integ = integrations or []
        self.integ_card.setVisible(bool(integ))
        self._clear_integ_list()
        for integ_name in integ:
            integ_installed = self._dep_checker(integ_name) if self._dep_checker else False
            self.integ_list_layout.addWidget(DepItem(integ_name, integ_installed))

    def set_local_mod_info(self, mod_name, enabled, version="", mod_info=None):
        chinese_name = desc_cn = desc_en = ""
        deps = integ = []
        if mod_info:
            chinese_name = mod_info.get('chinese_name', '')
            desc_cn = mod_info.get('desc_cn', '')
            desc_en = mod_info.get('desc_en', '')
            deps = mod_info.get('dependencies', [])
            integ = mod_info.get('integrations', [])

        self.set_mod_info(
            mod_name=mod_name,
            chinese_name=chinese_name,
            version=version,
            enabled=enabled,
            desc_cn=desc_cn,
            desc_en=desc_en,
            dependencies=deps,
            integrations=integ,
            is_online_page=False,
        )

    def set_online_mod_info(self, mod_name, is_installed, has_update, mod_info=None):
        chinese_name = version = desc_cn = desc_en = ""
        deps = integ = []
        if mod_info:
            chinese_name = mod_info.get('chinese_name', '')
            version = mod_info.get('version', '')
            desc_cn = mod_info.get('desc_cn', '')
            desc_en = mod_info.get('desc_en', '')
            deps = mod_info.get('dependencies', [])
            integ = mod_info.get('integrations', [])

        self.set_mod_info(
            mod_name=mod_name,
            chinese_name=chinese_name,
            version=version,
            is_installed=is_installed,
            has_update=has_update,
            desc_cn=desc_cn,
            desc_en=desc_en,
            dependencies=deps,
            integrations=integ,
            is_online_page=True,
        )


class ModDetailScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #1e1e1e;
                width: 8px;
                border-radius: 4px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background-color: #444444;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #555555;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setWidgetResizable(True)

        self.detail_panel = ModDetailPanel()
        self.setWidget(self.detail_panel)


# ============================================================
# IconButton
# ============================================================

class IconButton(QWidget):
    def __init__(self, icon_text, text, bg_color, hover_color, text_color="white",
                 parent=None, fixed_height=38, fixed_width=None, font_size=13, bold=True):
        super().__init__(parent)

        self._bg_color = bg_color
        self._hover_color = hover_color
        self._disabled_color = "#444444"
        self._text_color = text_color
        self._disabled_text_color = "#888888"
        self._enabled = True
        self._pressed = False
        self._click_callback = None

        self.setCursor(Qt.PointingHandCursor)
        if fixed_width:
            self.setFixedWidth(fixed_width)
        self.setFixedHeight(fixed_height)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._bg_frame = QFrame()
        self._bg_frame.setStyleSheet(self._make_bg_style(self._bg_color))
        bg_layout = QHBoxLayout(self._bg_frame)
        bg_layout.setContentsMargins(14, 4, 14, 4)
        bg_layout.setSpacing(5)
        bg_layout.setAlignment(Qt.AlignCenter)

        self.icon_label = QLabel(icon_text)
        self.icon_label.setFont(QFont("Segoe UI Emoji", font_size + 2))
        self.icon_label.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }}
        """)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        bg_layout.addWidget(self.icon_label)

        self.text_label = QLabel(text)
        fw = QFont.Weight.Bold if bold else QFont.Weight.Normal
        self.text_label.setFont(QFont("Microsoft YaHei", font_size, fw))
        self.text_label.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }}
        """)
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        bg_layout.addWidget(self.text_label)

        outer.addWidget(self._bg_frame)

    def _make_bg_style(self, color):
        radius = self.height() // 2
        return f"""
            QFrame {{
                background-color: {color};
                border: none;
                border-radius: {radius}px;
            }}
        """

    def connect(self, callback):
        self._click_callback = callback

    def setEnabled(self, enabled):
        self._enabled = enabled
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        if enabled:
            self._bg_frame.setStyleSheet(self._make_bg_style(self._bg_color))
        else:
            self._bg_frame.setStyleSheet(self._make_bg_style(self._disabled_color))
        super().setEnabled(enabled)

    def isEnabled(self):
        return self._enabled

    def set_text(self, icon_text, text):
        self.icon_label.setText(icon_text)
        self.text_label.setText(text)

    def mousePressEvent(self, event):
        if not self._enabled:
            return
        self._pressed = True
        self._bg_frame.setStyleSheet(self._make_bg_style(self._hover_color))

    def mouseReleaseEvent(self, event):
        if not self._enabled:
            return
        was_pressed = self._pressed
        self._pressed = False
        if was_pressed and self.underMouse():
            self._bg_frame.setStyleSheet(self._make_bg_style(self._hover_color))
            if self._click_callback:
                self._click_callback()
        else:
            self._bg_frame.setStyleSheet(self._make_bg_style(self._bg_color))

    def enterEvent(self, event):
        if self._enabled:
            self._bg_frame.setStyleSheet(self._make_bg_style(self._hover_color))

    def leaveEvent(self, event):
        if self._enabled and not self._pressed:
            self._bg_frame.setStyleSheet(self._make_bg_style(self._bg_color))


# ============================================================
# 本地模组页面
# ============================================================

class ModPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self._current_mod = None
        self._current_widget = None
        self._current_row = -1
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        nav_bar = QWidget()
        nav_bar.setFixedHeight(64)
        nav_bar.setStyleSheet("""
            background-color: transparent;
            border-bottom: 1px solid #333333;
        """)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(24, 0, 24, 0)

        title = QLabel("📂 本地模组")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        title.setStyleSheet("color: #ffffff; background: transparent;")

        self.multi_select_hint = QLabel("按住 Ctrl 或 Shift 可进行多选，双击模组可以快速启用或禁用")
        self.multi_select_hint.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        self.multi_select_hint.setStyleSheet("""
            QLabel {
                color: #ff9500;
                background-color: rgba(255, 149, 0, 0.12);
                border: 1px solid rgba(255, 149, 0, 0.4);
                border-radius: 10px;
                padding: 4px 12px;
                margin-left: 16px;
            }
        """)
        self.multi_select_hint.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.multi_select_hint.setWordWrap(False)

        nav_layout.addWidget(title)
        nav_layout.addWidget(self.multi_select_hint)
        nav_layout.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索模组...")
        self.search_input.setFixedSize(200, 32)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #2a2a2a;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 16px;
                padding: 0 14px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #34c759;
            }
            QLineEdit::placeholder {
                color: #888888;
            }
        """)
        self.search_input.textChanged.connect(self._filter_mods)
        nav_layout.addWidget(self.search_input)

        nav_layout.addSpacing(10)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setFixedHeight(32)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 16px;
                padding: 0 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #444444;
                border-color: #34c759;
            }
        """)
        refresh_btn.clicked.connect(self._manual_refresh)
        nav_layout.addWidget(refresh_btn)

        layout.addWidget(nav_bar)

        filter_bar = QWidget()
        filter_bar.setFixedHeight(48)
        filter_bar.setStyleSheet("background-color: transparent; border-bottom: 1px solid #2a2a2a;")
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(24, 0, 24, 0)
        filter_layout.setSpacing(8)

        self.filter_combo = QComboBox()
        with QSignalBlocker(self.filter_combo):
            self.filter_combo.addItems(["全部模组", "已启用", "已禁用"])
        self.filter_combo.setFixedWidth(120)
        self.filter_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 13px;
            }
            QComboBox:hover {
                border: 1px solid #34c759;
            }
            QComboBox::drop-down {
                border: none;
                width: 22px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: #ffffff;
                border: 1px solid #444444;
                selection-background-color: #34c759;
                selection-color: white;
            }
        """)
        self.filter_combo.currentIndexChanged.connect(self._filter_mods)
        filter_layout.addWidget(self.filter_combo)

        self.batch_actions_widget = QWidget()
        self.batch_actions_widget.setVisible(False)
        batch_layout = QHBoxLayout(self.batch_actions_widget)
        batch_layout.setContentsMargins(10, 0, 0, 0)
        batch_layout.setSpacing(10)

        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setFixedHeight(32)
        self.select_all_btn.setFixedWidth(72)
        self.select_all_btn.setFont(QFont("Microsoft YaHei", 12))
        self.select_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                color: #cccccc;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border-color: #777777;
            }
            QPushButton:disabled {
                background-color: #222222;
                color: #666666;
                border-color: #333333;
            }
        """)
        self.select_all_btn.clicked.connect(self._toggle_select_all)
        batch_layout.addWidget(self.select_all_btn)

        self.batch_enable_btn = IconButton(
            icon_text="✅", text="启用",
            bg_color="#34c759", hover_color="#28a745",
            text_color="white", fixed_height=32, fixed_width=96,
            font_size=10, bold=False
        )
        self.batch_enable_btn.connect(self._batch_enable)
        self.batch_enable_btn.setEnabled(False)
        batch_layout.addWidget(self.batch_enable_btn)

        self.batch_disable_btn = IconButton(
            icon_text="⛔", text="禁用",
            bg_color="#ff9500", hover_color="#e68a00",
            text_color="white", fixed_height=32, fixed_width=96,
            font_size=10, bold=False
        )
        self.batch_disable_btn.connect(self._batch_disable)
        self.batch_disable_btn.setEnabled(False)
        batch_layout.addWidget(self.batch_disable_btn)

        self.batch_delete_btn = IconButton(
            icon_text="🗑", text="删除",
            bg_color="#ff3b30", hover_color="#dc3545",
            text_color="white", fixed_height=32, fixed_width=96,
            font_size=10, bold=False
        )
        self.batch_delete_btn.connect(self._batch_delete)
        self.batch_delete_btn.setEnabled(False)
        batch_layout.addWidget(self.batch_delete_btn)

        self.batch_count_label = QLabel("已选 0 个")
        self.batch_count_label.setStyleSheet("color: #888888; font-size: 12px; background: transparent;")
        batch_layout.addWidget(self.batch_count_label)

        filter_layout.addWidget(self.batch_actions_widget)
        filter_layout.addStretch()

        self.count_label = QLabel("共 0 个模组")
        self.count_label.setStyleSheet("color: #888888; font-size: 12px; background: transparent;")
        filter_layout.addWidget(self.count_label)

        layout.addWidget(filter_bar)

        content = QWidget()
        content.setStyleSheet("background-color: transparent;")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(20, 14, 20, 14)
        content_layout.setSpacing(14)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.mod_list = QListWidget()
        self.mod_list.setAlternatingRowColors(False)
        self.mod_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.mod_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.mod_list.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
                padding: 2px;
                outline: none;
            }
            QListWidget::item {
                background-color: transparent;
                border: none;
                margin: 4px 2px;
                padding: 0px;
            }
            QListWidget::item:selected {
                background-color: transparent;
                color: #e0e0e0;
            }
            QListWidget::item:selected:active {
                background-color: transparent;
            }
            QListWidget::item:selected:!active {
                background-color: transparent;
            }
            QListWidget::item:hover {
                background-color: transparent;
            }
        """)
        self.mod_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.mod_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        left_layout.addWidget(self.mod_list)

        right_panel = QWidget()
        right_panel.setStyleSheet("""
            background-color: #191919;
            border: none;
            border-radius: 10px;
        """)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(10)

        self.detail_scroll = ModDetailScrollArea()
        right_layout.addWidget(self.detail_scroll, stretch=1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.copy_link_btn = QPushButton("📋 复制Mod下载地址")
        self.copy_link_btn.setStyleSheet("""
            QPushButton {
                background-color: #34c759;
                color: white;
                border: none;
                border-radius: 16px;
                padding: 8px 18px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #28a745;
            }
            QPushButton:disabled {
                background-color: #444444;
                color: #888888;
            }
        """)
        self.copy_link_btn.clicked.connect(self._copy_mod_link)
        self.copy_link_btn.setEnabled(False)
        btn_layout.addWidget(self.copy_link_btn)

        self.copy_batch_btn = QPushButton("📦 复制Mod本体+前置下载地址")
        self.copy_batch_btn.setStyleSheet("""
            QPushButton {
                background-color: #007aff;
                color: white;
                border: none;
                border-radius: 16px;
                padding: 8px 18px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #0062cc;
            }
            QPushButton:disabled {
                background-color: #444444;
                color: #888888;
            }
        """)
        self.copy_batch_btn.clicked.connect(self._copy_batch_links)
        self.copy_batch_btn.setEnabled(False)
        btn_layout.addWidget(self.copy_batch_btn)

        btn_layout.addStretch()
        right_layout.addLayout(btn_layout)

        # ---- 右下角复制提示 ----
        self._copy_tip_label = QLabel("")
        self._copy_tip_label.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        self._copy_tip_label.setStyleSheet("""
            QLabel {
                color: #b5ffc6;
                background-color: rgba(40, 167, 69, 0.92);
                border: 1px solid rgba(52, 199, 89, 0.65);
                border-radius: 8px;
                padding: 8px 18px;
            }
        """)
        self._copy_tip_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._copy_tip_label.setVisible(False)
        self._copy_tip_label.setWordWrap(False)
        self._copy_tip_label.setParent(right_panel)
        self._copy_tip_label.raise_()

        self._copy_tip_timer = QTimer(self)
        self._copy_tip_timer.setSingleShot(True)
        self._copy_tip_timer.timeout.connect(self._hide_copy_tip)

        right_panel.installEventFilter(self)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 500])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        content_layout.addWidget(splitter)
        layout.addWidget(content, stretch=1)

    # ---------- 右下角提示相关 ----------
    def eventFilter(self, obj, event):
        if obj == self.detail_scroll.parent() and event.type() == event.Type.Resize:
            self._reposition_copy_tip()
        return super().eventFilter(obj, event)

    def _reposition_copy_tip(self):
        parent_widget = self._copy_tip_label.parent()
        if parent_widget:
            rect = parent_widget.rect()
            size = self._copy_tip_label.sizeHint()
            margin = 16
            self._copy_tip_label.move(
                rect.width() - size.width() - margin,
                rect.height() - size.height() - margin
            )
            self._copy_tip_label.raise_()

    def _show_copy_tip(self, text):
        self._copy_tip_label.setText(text)
        self._copy_tip_label.adjustSize()
        self._reposition_copy_tip()
        self._copy_tip_label.setVisible(True)
        self._copy_tip_label.raise_()
        self._copy_tip_timer.start(4000)

    def _hide_copy_tip(self):
        self._copy_tip_label.setVisible(False)

    # ---------- 原有业务逻辑 ----------
    def _on_item_double_clicked(self, item):
        mod_name = item.data(Qt.UserRole)
        if not mod_name or mod_name == "暂无已安装模组":
            return

        widget = self.mod_list.itemWidget(item)
        if not widget:
            return

        game_path = self.parent.game_path if self.parent else None
        if not game_path:
            return

        try:
            if widget.enabled:
                disable_mod(game_path, mod_name)
                widget.update_status(False)
            else:
                enable_mod(game_path, mod_name)
                widget.update_status(True)

            if self._current_mod == mod_name:
                self._show_mod_detail(mod_name)

            self._update_count()
            self._on_selection_changed()
        except Exception:
            pass

    def _toggle_select_all(self):
        if self.select_all_btn.text() == "全选":
            for i in range(self.mod_list.count()):
                item = self.mod_list.item(i)
                if not item.isHidden():
                    item.setSelected(True)
            self.select_all_btn.setText("取消")
        else:
            self.mod_list.clearSelection()
            self.select_all_btn.setText("全选")

    def _on_selection_changed(self):
        selected_items = self.mod_list.selectedItems()
        valid_selected = [
            item for item in selected_items
            if (mod_name := item.data(Qt.UserRole)) and mod_name != "暂无已安装模组" and not item.isHidden()
        ]

        count = len(valid_selected)

        if count > 0:
            total_visible = sum(1 for i in range(self.mod_list.count()) if not self.mod_list.item(i).isHidden())
            self.select_all_btn.setText("取消" if count == total_visible else "全选")
        else:
            self.select_all_btn.setText("全选")

        for i in range(self.mod_list.count()):
            item = self.mod_list.item(i)
            widget = self.mod_list.itemWidget(item)
            if widget and hasattr(widget, 'set_selected'):
                widget.set_selected(item in valid_selected)

        if count > 0:
            self.batch_actions_widget.setVisible(True)
            self.batch_count_label.setText(f"已选 {count} 个")
            self.batch_enable_btn.setEnabled(True)
            self.batch_disable_btn.setEnabled(True)
            self.batch_delete_btn.setEnabled(True)
        else:
            self.batch_actions_widget.setVisible(False)
            self.batch_count_label.setText("已选 0 个")
            self.batch_enable_btn.setEnabled(False)
            self.batch_disable_btn.setEnabled(False)
            self.batch_delete_btn.setEnabled(False)

        if count == 1:
            item = valid_selected[0]
            mod_name = item.data(Qt.UserRole)
            if mod_name and mod_name != "暂无已安装模组":
                self._current_mod = mod_name
                self._current_widget = self.mod_list.itemWidget(item)
                self._show_mod_detail(mod_name)
        elif count == 0:
            self._current_mod = None
            self._current_widget = None
            self.copy_link_btn.setEnabled(False)
            self.copy_batch_btn.setEnabled(False)
            self.detail_scroll.detail_panel._show_empty_state()
        elif count > 1:
            self.copy_link_btn.setEnabled(False)
            self.copy_batch_btn.setEnabled(False)

    def _get_selected_mods(self):
        result = []
        for item in self.mod_list.selectedItems():
            mod_name = item.data(Qt.UserRole)
            if mod_name and mod_name != "暂无已安装模组" and not item.isHidden():
                widget = self.mod_list.itemWidget(item)
                if widget:
                    result.append((mod_name, widget))
        return result

    def _batch_enable(self):
        game_path = self.parent.game_path if self.parent else None
        if not game_path:
            return

        for mod_name, widget in self._get_selected_mods():
            if widget.enabled:
                continue
            try:
                enable_mod(game_path, mod_name)
                widget.update_status(True)
            except Exception:
                pass

        if self._current_mod and self.mod_list.selectedItems():
            self._show_mod_detail(self._current_mod)

        self._update_count()
        self._on_selection_changed()

    def _batch_disable(self):
        game_path = self.parent.game_path if self.parent else None
        if not game_path:
            return

        for mod_name, widget in self._get_selected_mods():
            if not widget.enabled:
                continue
            try:
                disable_mod(game_path, mod_name)
                widget.update_status(False)
            except Exception:
                pass

        if self._current_mod and self.mod_list.selectedItems():
            self._show_mod_detail(self._current_mod)

        self._update_count()
        self._on_selection_changed()

    def _batch_delete(self):
        game_path = self.parent.game_path if self.parent else None
        if not game_path:
            return

        selected = self._get_selected_mods()
        if not selected:
            return

        mod_names = [name for name, _ in selected]

        try:
            for mod_name, _ in selected:
                delete_mod(game_path, mod_name)

            if self._current_mod in mod_names:
                self._current_mod = None
                self._current_widget = None
                self.copy_link_btn.setEnabled(False)
                self.copy_batch_btn.setEnabled(False)
                self.detail_scroll.detail_panel._show_empty_state()

            self.refresh_mod_list(game_path)
        except Exception:
            pass

    def refresh_mod_list(self, game_path):
        try:
            selected_mod = self._current_mod
            saved_filter_index = self.filter_combo.currentIndex()
            saved_search_text = self.search_input.text()

            self.mod_list.clear()
            self._current_mod = None
            self._current_widget = None
            self._current_row = -1
            self.copy_link_btn.setEnabled(False)
            self.copy_batch_btn.setEnabled(False)
            self.detail_scroll.detail_panel._show_empty_state()
            self.batch_actions_widget.setVisible(False)
            self.select_all_btn.setText("全选")

            if not game_path:
                self.detail_scroll.detail_panel.title_en.setText("请先设置游戏路径")
                self.detail_scroll.detail_panel.title_en.setStyleSheet(
                    "color: #888888; background: transparent; border: none;")
                with QSignalBlocker(self.filter_combo):
                    self.filter_combo.setCurrentIndex(saved_filter_index)
                self.search_input.setText(saved_search_text)
                return

            mods_dir = get_mods_dir(game_path)
            disabled_dir = os.path.join(mods_dir, "Disabled")

            if not os.path.exists(mods_dir) and not os.path.exists(disabled_dir):
                self.detail_scroll.detail_panel.title_en.setText("Mods 文件夹不存在")
                self.detail_scroll.detail_panel.title_en.setStyleSheet(
                    "color: #888888; background: transparent; border: none;")
                with QSignalBlocker(self.filter_combo):
                    self.filter_combo.setCurrentIndex(saved_filter_index)
                self.search_input.setText(saved_search_text)
                self._filter_mods()
                return

            found_mods = []

            if os.path.exists(mods_dir):
                for item in os.listdir(mods_dir):
                    if item == "Disabled":
                        continue
                    item_path = os.path.join(mods_dir, item)
                    if os.path.isdir(item_path):
                        if any(f.endswith('.dll') for f in os.listdir(item_path)):
                            found_mods.append((item, True))
                    elif os.path.isfile(item_path) and item.endswith('.dll'):
                        found_mods.append((os.path.splitext(item)[0], True))

            if os.path.exists(disabled_dir):
                for item in os.listdir(disabled_dir):
                    item_path = os.path.join(disabled_dir, item)
                    if os.path.isdir(item_path):
                        if any(f.endswith('.dll') for f in os.listdir(item_path)):
                            found_mods.append((item, False))
                    elif os.path.isfile(item_path) and item.endswith('.dll'):
                        found_mods.append((os.path.splitext(item)[0], False))

            if not found_mods:
                self.mod_list.addItem("暂无已安装模组")
                self.detail_scroll.detail_panel.title_en.setText("暂无已安装模组")
                self.detail_scroll.detail_panel.title_en.setStyleSheet(
                    "color: #888888; background: transparent; border: none;")
                with QSignalBlocker(self.filter_combo):
                    self.filter_combo.setCurrentIndex(saved_filter_index)
                self.search_input.setText(saved_search_text)
                self._filter_mods()
                return

            found_mods.sort(key=lambda x: x[0].lower())

            resolver = self.parent.resolver if self.parent and hasattr(self.parent, 'resolver') else None

            for mod_name, enabled in found_mods:
                chinese_name = ""
                if resolver and hasattr(resolver, 'mod_data_by_name'):
                    chinese_name = resolver.mod_data_by_name.get(mod_name, {}).get('chinese_name', '')

                display_name = f"{mod_name}（{chinese_name}）" if chinese_name else mod_name

                item = QListWidgetItem()
                item.setData(Qt.UserRole, mod_name)
                item.setData(Qt.UserRole + 1, enabled)

                widget = ModListItemWidget(
                    mod_name=mod_name,
                    display_name=display_name,
                    enabled=enabled,
                    parent=self.mod_list,
                    list_item=item
                )
                item.setSizeHint(widget.sizeHint())
                self.mod_list.addItem(item)
                self.mod_list.setItemWidget(item, widget)

            self._update_count()
            self.search_input.setText(saved_search_text)
            with QSignalBlocker(self.filter_combo):
                self.filter_combo.setCurrentIndex(saved_filter_index)

            if selected_mod:
                for i in range(self.mod_list.count()):
                    if self.mod_list.item(i).data(Qt.UserRole) == selected_mod:
                        self.mod_list.setCurrentRow(i)
                        break

            self._filter_mods()

            if not self.mod_list.selectedItems():
                self.detail_scroll.detail_panel.title_en.setText(f"共 {len(found_mods)} 个模组")
                self.detail_scroll.detail_panel.title_en.setStyleSheet(
                    "color: #888888; background: transparent; border: none;")
                self.detail_scroll.detail_panel.status_label.setText("👈 点击左侧列表查看详情")
                self.detail_scroll.detail_panel.status_label.setStyleSheet(
                    "color: #666666; background: transparent; border: none;")
        except Exception:
            pass

    def _update_count(self):
        self.count_label.setText(f"共 {self.mod_list.count()} 个模组")

    def _filter_mods(self):
        search_text = self.search_input.text().lower()
        filter_index = self.filter_combo.currentIndex()

        for i in range(self.mod_list.count()):
            item = self.mod_list.item(i)
            widget = self.mod_list.itemWidget(item)
            if widget:
                visible = True
                if search_text and search_text not in widget.display_name.lower() and search_text not in widget.mod_name.lower():
                    visible = False
                if filter_index == 1 and not widget.enabled:
                    visible = False
                elif filter_index == 2 and widget.enabled:
                    visible = False
                item.setHidden(not visible)

        visible_count = sum(1 for i in range(self.mod_list.count()) if not self.mod_list.item(i).isHidden())
        self.count_label.setText(f"共 {visible_count} 个模组")
        self._on_selection_changed()

    def _manual_refresh(self):
        if self.parent and hasattr(self.parent, 'game_path'):
            self.refresh_mod_list(self.parent.game_path)

    def _show_mod_detail(self, mod_name):
        try:
            enabled = False
            for i in range(self.mod_list.count()):
                item = self.mod_list.item(i)
                if item.data(Qt.UserRole) == mod_name:
                    widget = self.mod_list.itemWidget(item)
                    if widget:
                        enabled = widget.enabled
                    break

            version_from_modlog = ""
            local_mods = parse_modlog()
            normalized = normalize_name(mod_name)
            local_info = local_mods.get(normalized)
            if local_info:
                version_from_modlog = local_info[1]

            mod_info = None
            if self.parent and hasattr(self.parent, 'resolver'):
                resolver = self.parent.resolver
                if hasattr(resolver, 'mod_data_by_name'):
                    mod_info = resolver.mod_data_by_name.get(mod_name)

            self.detail_scroll.detail_panel._dep_checker = lambda n: self._is_mod_installed(n)
            self.detail_scroll.detail_panel.set_local_mod_info(
                mod_name=mod_name,
                enabled=enabled,
                version=version_from_modlog,
                mod_info=mod_info,
            )

            if mod_info:
                link = mod_info.get('link', '')
                batch_links = mod_info.get('batch_links', [])
                self.copy_link_btn.setEnabled(bool(link))
                self.copy_batch_btn.setEnabled(bool(batch_links))
            else:
                self.copy_link_btn.setEnabled(False)
                self.copy_batch_btn.setEnabled(False)
        except RuntimeError:
            pass

    def _copy_mod_link(self):
        if not self._current_mod or not self.parent:
            return

        resolver = self.parent.resolver
        if hasattr(resolver, 'mod_data_by_name') and self._current_mod in resolver.mod_data_by_name:
            link = resolver.mod_data_by_name[self._current_mod].get('link', '')
            if link:
                QApplication.clipboard().setText(link)
                self._show_copy_tip("已复制本体地址")

    def _copy_batch_links(self):
        if not self._current_mod or not self.parent:
            return

        resolver = self.parent.resolver
        if hasattr(resolver, 'mod_data_by_name') and self._current_mod in resolver.mod_data_by_name:
            batch_links = resolver.mod_data_by_name[self._current_mod].get('batch_links', [])
            if batch_links:
                QApplication.clipboard().setText("\n".join(batch_links))
                self._show_copy_tip("已复制本体+前置地址")

    def _is_mod_installed(self, mod_name):
        try:
            if not (self.parent and hasattr(self.parent, 'game_path') and self.parent.game_path):
                return False

            game_path = self.parent.game_path
            mods_dir = get_mods_dir(game_path)
            disabled_dir = os.path.join(mods_dir, "Disabled")

            if os.path.exists(mods_dir):
                if os.path.isdir(os.path.join(mods_dir, mod_name)):
                    return True
                if os.path.isfile(os.path.join(mods_dir, mod_name + '.dll')):
                    return True

            if os.path.exists(disabled_dir):
                if os.path.isdir(os.path.join(disabled_dir, mod_name)):
                    return True
                if os.path.isfile(os.path.join(disabled_dir, mod_name + '.dll')):
                    return True

            return False
        except RuntimeError:
            return False


# ============================================================
# 在线模组页面
# ============================================================

class OnlineModPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self._current_mod = None
        self._current_widget = None
        self._current_row = -1
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        nav_bar = QWidget()
        nav_bar.setFixedHeight(64)
        nav_bar.setStyleSheet("""
            background-color: transparent;
            border-bottom: 1px solid #333333;
        """)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(24, 0, 24, 0)

        title = QLabel("🌐 在线模组")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        title.setStyleSheet("color: #ffffff; background: transparent;")

        hint_label = QLabel("⚠ 已安装模组状态依赖 ModLog 检测版本，启动游戏后才能正确检测已安装版本信息！")
        hint_label.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        hint_label.setStyleSheet("""
            QLabel {
                color: #ff9500;
                background-color: rgba(255, 149, 0, 0.12);
                border: 1px solid rgba(255, 149, 0, 0.4);
                border-radius: 10px;
                padding: 4px 12px;
                margin-left: 16px;
            }
        """)
        hint_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        hint_label.setWordWrap(False)

        nav_layout.addWidget(title)
        nav_layout.addWidget(hint_label)
        nav_layout.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索模组...")
        self.search_input.setFixedSize(200, 32)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #2a2a2a;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 16px;
                padding: 0 14px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #34c759;
            }
            QLineEdit::placeholder {
                color: #888888;
            }
        """)
        self.search_input.textChanged.connect(self._filter_mods)
        nav_layout.addWidget(self.search_input)

        nav_layout.addSpacing(10)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setFixedHeight(32)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 16px;
                padding: 0 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #444444;
                border-color: #34c759;
            }
        """)
        refresh_btn.clicked.connect(self._manual_refresh)
        nav_layout.addWidget(refresh_btn)

        layout.addWidget(nav_bar)

        filter_bar = QWidget()
        filter_bar.setFixedHeight(44)
        filter_bar.setStyleSheet("background-color: transparent; border-bottom: 1px solid #2a2a2a;")
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(24, 0, 24, 0)

        self.filter_combo = QComboBox()
        with QSignalBlocker(self.filter_combo):
            self.filter_combo.addItems(["全部模组", "已安装", "待更新", "未安装"])
        self.filter_combo.setFixedWidth(120)
        self.filter_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 13px;
            }
            QComboBox:hover {
                border: 1px solid #34c759;
            }
            QComboBox::drop-down {
                border: none;
                width: 22px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: #ffffff;
                border: 1px solid #444444;
                selection-background-color: #34c759;
                selection-color: white;
            }
        """)
        self.filter_combo.currentIndexChanged.connect(self._filter_mods)
        filter_layout.addWidget(self.filter_combo)
        filter_layout.addStretch()

        self.count_label = QLabel("共 0 个模组")
        self.count_label.setStyleSheet("color: #888888; font-size: 12px; background: transparent;")
        filter_layout.addWidget(self.count_label)

        layout.addWidget(filter_bar)

        content = QWidget()
        content.setStyleSheet("background-color: transparent;")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(20, 14, 20, 14)
        content_layout.setSpacing(14)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.mod_list = QListWidget()
        self.mod_list.setAlternatingRowColors(False)
        self.mod_list.setSelectionMode(QListWidget.SingleSelection)
        self.mod_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.mod_list.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
                padding: 2px;
                outline: none;
            }
            QListWidget::item {
                background-color: transparent;
                border: none;
                margin: 4px 2px;
                padding: 0px;
            }
            QListWidget::item:selected {
                background-color: transparent;
                color: #e0e0e0;
            }
            QListWidget::item:selected:active {
                background-color: transparent;
            }
            QListWidget::item:selected:!active {
                background-color: transparent;
            }
            QListWidget::item:hover {
                background-color: transparent;
            }
        """)
        self.mod_list.itemClicked.connect(self._on_item_clicked)
        left_layout.addWidget(self.mod_list)

        right_panel = QWidget()
        right_panel.setStyleSheet("""
            background-color: #191919;
            border: none;
            border-radius: 10px;
        """)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(10)

        self.detail_scroll = ModDetailScrollArea()
        right_layout.addWidget(self.detail_scroll, stretch=1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.copy_link_btn = QPushButton("📋 复制Mod下载地址")
        self.copy_link_btn.setStyleSheet("""
            QPushButton {
                background-color: #34c759;
                color: white;
                border: none;
                border-radius: 16px;
                padding: 8px 18px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #28a745;
            }
            QPushButton:disabled {
                background-color: #444444;
                color: #888888;
            }
        """)
        self.copy_link_btn.clicked.connect(self._copy_mod_link)
        self.copy_link_btn.setEnabled(False)
        btn_layout.addWidget(self.copy_link_btn)

        self.copy_batch_btn = QPushButton("📦 复制Mod本体+前置下载地址")
        self.copy_batch_btn.setStyleSheet("""
            QPushButton {
                background-color: #007aff;
                color: white;
                border: none;
                border-radius: 16px;
                padding: 8px 18px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #0062cc;
            }
            QPushButton:disabled {
                background-color: #444444;
                color: #888888;
            }
        """)
        self.copy_batch_btn.clicked.connect(self._copy_batch_links)
        self.copy_batch_btn.setEnabled(False)
        btn_layout.addWidget(self.copy_batch_btn)

        btn_layout.addStretch()
        right_layout.addLayout(btn_layout)

        # ---- 右下角复制提示 ----
        self._copy_tip_label = QLabel("")
        self._copy_tip_label.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        self._copy_tip_label.setStyleSheet("""
            QLabel {
                color: #b5ffc6;
                background-color: rgba(40, 167, 69, 0.92);
                border: 1px solid rgba(52, 199, 89, 0.65);
                border-radius: 8px;
                padding: 8px 18px;
            }
        """)
        self._copy_tip_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._copy_tip_label.setVisible(False)
        self._copy_tip_label.setWordWrap(False)
        self._copy_tip_label.setParent(right_panel)
        self._copy_tip_label.raise_()

        self._copy_tip_timer = QTimer(self)
        self._copy_tip_timer.setSingleShot(True)
        self._copy_tip_timer.timeout.connect(self._hide_copy_tip)

        right_panel.installEventFilter(self)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 500])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        content_layout.addWidget(splitter)
        layout.addWidget(content, stretch=1)

    # ---------- 右下角提示相关 ----------
    def eventFilter(self, obj, event):
        if obj == self.detail_scroll.parent() and event.type() == event.Type.Resize:
            self._reposition_copy_tip()
        return super().eventFilter(obj, event)

    def _reposition_copy_tip(self):
        parent_widget = self._copy_tip_label.parent()
        if parent_widget:
            rect = parent_widget.rect()
            size = self._copy_tip_label.sizeHint()
            margin = 16
            self._copy_tip_label.move(
                rect.width() - size.width() - margin,
                rect.height() - size.height() - margin
            )
            self._copy_tip_label.raise_()

    def _show_copy_tip(self, text):
        self._copy_tip_label.setText(text)
        self._copy_tip_label.adjustSize()
        self._reposition_copy_tip()
        self._copy_tip_label.setVisible(True)
        self._copy_tip_label.raise_()
        self._copy_tip_timer.start(4000)

    def _hide_copy_tip(self):
        self._copy_tip_label.setVisible(False)

    # ---------- 原有业务逻辑 ----------
    def refresh_mod_list(self, game_path):
        try:
            selected_mod = self._current_mod
            saved_filter_index = self.filter_combo.currentIndex()
            saved_search_text = self.search_input.text()

            self.mod_list.clear()
            self._current_mod = None
            self._current_widget = None
            self._current_row = -1
            self.copy_link_btn.setEnabled(False)
            self.copy_batch_btn.setEnabled(False)
            self.detail_scroll.detail_panel._show_empty_state()

            if not self.parent or not hasattr(self.parent, 'resolver'):
                self.detail_scroll.detail_panel.title_en.setText("请先更新链接")
                self.detail_scroll.detail_panel.title_en.setStyleSheet(
                    "color: #888888; background: transparent; border: none;")
                with QSignalBlocker(self.filter_combo):
                    self.filter_combo.setCurrentIndex(saved_filter_index)
                self.search_input.setText(saved_search_text)
                self._filter_mods()
                return

            resolver = self.parent.resolver
            if not resolver.is_loaded:
                self.detail_scroll.detail_panel.title_en.setText("⏳ 加载中...")
                self.detail_scroll.detail_panel.title_en.setStyleSheet(
                    "color: #888888; background: transparent; border: none;")
                self.mod_list.addItem("⏳ 加载中...")
                with QSignalBlocker(self.filter_combo):
                    self.filter_combo.setCurrentIndex(saved_filter_index)
                self.search_input.setText(saved_search_text)
                self._filter_mods()
                return

            mod_data = resolver.mod_data
            if not mod_data:
                self.detail_scroll.detail_panel.title_en.setText("暂无在线模组数据")
                self.detail_scroll.detail_panel.title_en.setStyleSheet(
                    "color: #888888; background: transparent; border: none;")
                with QSignalBlocker(self.filter_combo):
                    self.filter_combo.setCurrentIndex(saved_filter_index)
                self.search_input.setText(saved_search_text)
                self._filter_mods()
                return

            local_mods = parse_modlog()
            found_mods = []

            for mod_info in mod_data:
                mod_name = mod_info.get('name', '')
                if not mod_name:
                    continue

                chinese_name = mod_info.get('chinese_name', '')
                online_version = mod_info.get('version', '')
                normalized_online = normalize_name(mod_name)
                local_info = local_mods.get(normalized_online)
                is_installed = local_info is not None
                has_update = False

                if is_installed and online_version:
                    if normalize_version(online_version) != normalize_version(local_info[1]):
                        has_update = True

                found_mods.append((mod_name, chinese_name, is_installed, has_update))

            if not found_mods:
                self.mod_list.addItem("暂无在线模组")
                self.detail_scroll.detail_panel.title_en.setText("暂无在线模组")
                self.detail_scroll.detail_panel.title_en.setStyleSheet(
                    "color: #888888; background: transparent; border: none;")
                with QSignalBlocker(self.filter_combo):
                    self.filter_combo.setCurrentIndex(saved_filter_index)
                self.search_input.setText(saved_search_text)
                self._filter_mods()
                return

            found_mods.sort(key=lambda x: x[0].lower())

            for mod_name, chinese_name, is_installed, has_update in found_mods:
                display_name = f"{mod_name}（{chinese_name}）" if chinese_name else mod_name

                item = QListWidgetItem()
                item.setData(Qt.UserRole, mod_name)
                item.setData(Qt.UserRole + 1, is_installed)
                item.setData(Qt.UserRole + 2, has_update)

                widget = OnlineModListItemWidget(
                    mod_name=mod_name,
                    display_name=display_name,
                    is_installed=is_installed,
                    has_update=has_update,
                    parent=self.mod_list,
                    list_item=item
                )
                item.setSizeHint(widget.sizeHint())
                self.mod_list.addItem(item)
                self.mod_list.setItemWidget(item, widget)

                widget.action_btn.clicked.connect(
                    lambda checked=False, mn=mod_name, w=widget: self._on_action_clicked(mn, w)
                )

            self._update_count()
            self.search_input.setText(saved_search_text)
            with QSignalBlocker(self.filter_combo):
                self.filter_combo.setCurrentIndex(saved_filter_index)

            if selected_mod:
                for i in range(self.mod_list.count()):
                    if self.mod_list.item(i).data(Qt.UserRole) == selected_mod:
                        self.mod_list.setCurrentRow(i)
                        self._on_item_clicked(self.mod_list.item(i))
                        break

            self._filter_mods()

            if not selected_mod or self.mod_list.currentRow() < 0:
                self.detail_scroll.detail_panel.title_en.setText(f"共 {len(found_mods)} 个在线模组")
                self.detail_scroll.detail_panel.title_en.setStyleSheet(
                    "color: #888888; background: transparent; border: none;")
                self.detail_scroll.detail_panel.status_label.setText("👈 点击左侧列表查看详情")
                self.detail_scroll.detail_panel.status_label.setStyleSheet(
                    "color: #666666; background: transparent; border: none;")
        except Exception:
            pass

    def _update_count(self):
        self.count_label.setText(f"共 {self.mod_list.count()} 个模组")

    def _filter_mods(self):
        search_text = self.search_input.text().lower()
        filter_index = self.filter_combo.currentIndex()

        for i in range(self.mod_list.count()):
            item = self.mod_list.item(i)
            widget = self.mod_list.itemWidget(item)
            if widget:
                visible = True
                if search_text and search_text not in widget.display_name.lower() and search_text not in widget.mod_name.lower():
                    visible = False
                if filter_index == 1 and not widget.is_installed:
                    visible = False
                elif filter_index == 2 and not widget.has_update:
                    visible = False
                elif filter_index == 3 and widget.is_installed:
                    visible = False
                item.setHidden(not visible)

        visible_count = sum(1 for i in range(self.mod_list.count()) if not self.mod_list.item(i).isHidden())
        self.count_label.setText(f"共 {visible_count} 个模组")

    def _manual_refresh(self):
        if self.parent and hasattr(self.parent, 'game_path'):
            self.refresh_mod_list(self.parent.game_path)

    def _on_item_clicked(self, item):
        mod_name = item.data(Qt.UserRole)
        if not mod_name or mod_name == "暂无在线模组":
            return

        current_widget = self.mod_list.itemWidget(item)
        if current_widget is self._current_widget:
            return

        if self._current_widget:
            self._current_widget.set_selected(False)

        if current_widget:
            current_widget.set_selected(True)
            self._current_widget = current_widget

        self._current_mod = mod_name
        self._show_mod_detail(mod_name)

    def _show_mod_detail(self, mod_name):
        try:
            is_installed = has_update = False
            for i in range(self.mod_list.count()):
                item = self.mod_list.item(i)
                if item.data(Qt.UserRole) == mod_name:
                    is_installed = item.data(Qt.UserRole + 1)
                    has_update = item.data(Qt.UserRole + 2)
                    break

            mod_info = None
            if self.parent and hasattr(self.parent, 'resolver'):
                resolver = self.parent.resolver
                if hasattr(resolver, 'mod_data_by_name'):
                    mod_info = resolver.mod_data_by_name.get(mod_name)

            self.detail_scroll.detail_panel._dep_checker = lambda n: self._is_mod_installed(n)
            self.detail_scroll.detail_panel.set_online_mod_info(
                mod_name=mod_name,
                is_installed=is_installed,
                has_update=has_update,
                mod_info=mod_info,
            )

            if mod_info:
                link = mod_info.get('link', '')
                batch_links = mod_info.get('batch_links', [])
                self.copy_link_btn.setEnabled(bool(link))
                self.copy_batch_btn.setEnabled(bool(batch_links))
            else:
                self.copy_link_btn.setEnabled(False)
                self.copy_batch_btn.setEnabled(False)
        except RuntimeError:
            pass

    def _on_action_clicked(self, mod_name, widget):
        if widget.is_installed and not widget.has_update:
            return

        if not self.parent or not hasattr(self.parent, 'resolver'):
            return

        resolver = self.parent.resolver
        if mod_name not in resolver.mod_data_by_name:
            return

        batch_links = resolver.mod_data_by_name[mod_name].get('batch_links', [])
        if not batch_links:
            return

        QApplication.clipboard().setText("\n".join(batch_links))
        self._show_copy_tip("已复制本体+前置地址")

    def _copy_mod_link(self):
        if not self._current_mod or not self.parent:
            return

        resolver = self.parent.resolver
        if hasattr(resolver, 'mod_data_by_name') and self._current_mod in resolver.mod_data_by_name:
            link = resolver.mod_data_by_name[self._current_mod].get('link', '')
            if link:
                QApplication.clipboard().setText(link)
                self._show_copy_tip("已复制本体地址")

    def _copy_batch_links(self):
        if not self._current_mod or not self.parent:
            return

        resolver = self.parent.resolver
        if hasattr(resolver, 'mod_data_by_name') and self._current_mod in resolver.mod_data_by_name:
            batch_links = resolver.mod_data_by_name[self._current_mod].get('batch_links', [])
            if batch_links:
                QApplication.clipboard().setText("\n".join(batch_links))
                self._show_copy_tip("已复制本体+前置地址")

    def _is_mod_installed(self, mod_name):
        local_mods = parse_modlog()
        return normalize_name(mod_name) in local_mods