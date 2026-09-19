# -*- coding: utf-8 -*-
"""模组管理页面"""
import os
import re
import sys
import time
from typing import Callable, Optional
from PySide6.QtCore import (
    Qt,
    QTimer,
    QSignalBlocker,
    QFileSystemWatcher,
    QSize,
    QByteArray,
    QEvent,
    QThread,
    Signal,
    QItemSelection,
    QItemSelectionModel,
    QPoint,
    QUrl,
)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QScrollArea,
    QMessageBox,
    QSizePolicy,
    QLineEdit,
    QComboBox,
    QFrame,
    QSpacerItem,
    QProgressBar,
    QToolTip,
    QDialog,
    QTextBrowser,
)
from PySide6.QtGui import (QFont, QCursor, QPixmap, QPainter, QDesktopServices,
                           QTextCursor, QImage)
from urllib.parse import urljoin, quote
from utils import get_mods_dir
from core import disable_mod, enable_mod, delete_mod, is_mod_enabled
from ui.md_render import MarkdownBrowser, collect_image_widths, lookup_url

try:  # 精简安装可能不带 QtSvg：图标渲染时优雅降级为文字
    from PySide6.QtSvg import QSvgRenderer
except Exception:
    QSvgRenderer = None


def get_modlog_path():
    """获取 ModLog.txt 文件路径"""
    user_profile = os.environ.get('USERPROFILE', os.path.expanduser('~'))
    return os.path.join(user_profile, 'AppData', 'LocalLow', 'Team Cherry', 'Hollow Knight', 'ModLog.txt')


# ModLog 解析结果缓存（按文件 mtime+size 失效）：
# 单次点击/刷新都会调用，避免重复读盘（列表大时影响明显）
_modlog_cache = {"key": None, "data": {}}


def parse_modlog(_path=None):
    path = _path or get_modlog_path()
    if not os.path.isfile(path):
        _modlog_cache["key"] = None
        _modlog_cache["data"] = {}
        return {}

    try:
        st = os.stat(path)
        key = (st.st_mtime, st.st_size)
    except OSError:
        key = None
    if key is not None and _modlog_cache["key"] == key:
        return dict(_modlog_cache["data"])

    result = {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
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

    _modlog_cache["key"] = key
    _modlog_cache["data"] = result
    return dict(result)


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
    """卡片样式。

    必须用 objectName 限定选择器：裸写 "QFrame { ... }" 会命中卡片内所有后代
    QFrame，而 QLabel 正是 QFrame 的子类 —— 卡片里每一行文字都会被套上一条边框。
    """
    return f"""
        #DetailCard {{
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
    lbl.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
    lbl.setStyleSheet("""
        QLabel {
            color: #9aa3b8;
            background: transparent;
            border: none;
            padding: 0px;
            font-size: 13px;
            font-weight: bold;
        }
    """)
    return lbl


def _version_badge_style(color, bg, border):
    """版本徽章样式：普通蓝 / 待更新橙"""
    return f"""
        QLabel {{
            color: {color};
            background-color: {bg};
            border: 1px solid {border};
            border-radius: 11px;
            padding: 3px 12px;
            font-size: 12px;
        }}
    """


# 内置矢量图标：名称 -> (viewBox, path d)。均为实心单路径，可直接填色。
_ICON_PATHS = {
    "github": ("0 0 16 16",
               "M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59"
               ".4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94"
               ".09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82"
               ".72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95"
               " 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82"
               ".64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82"
               ".44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95"
               ".29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38"
               "A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"),
    "edit": ("0 0 24 24",
             "M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25z"
             "M20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 "
             "3.75 3.75 1.83-1.83z"),
    "folder": ("0 0 24 24",
               "M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8"
               "c0-1.1-.9-2-2-2h-8l-2-2z"),
    "share": ("0 0 24 24",
              "M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7"
              "l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3"
              "c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3"
              "c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92"
              "s2.92-1.31 2.92-2.92-1.31-2.92-2.92-2.92z"),
}

# 无 QtSvg 时的退化文字
_ICON_FALLBACK_TEXT = {"edit": "✏", "folder": "📁", "share": "🔗", "github": "GitHub"}

# 动作图标悬浮提示的弹出延迟（毫秒）。
# 不用 Qt 原生 setToolTip（默认约 1 秒才弹，太慢），改为图标自己用定时器控制；
# 也刻意不去碰 QApplication.setStyle()——在控件构造期替换全局样式会让后续
# 控件构造返回 NULL 直接崩溃。
_TOOLTIP_WAKE_DELAY_MS = 120


def _render_svg_icon(name, size=18, color="#c8c8d0"):
    """把内置图标渲染成 QPixmap；无 QtSvg 或渲染失败时返回 None（调用方退化为文字）。"""
    if QSvgRenderer is None:
        return None
    view_box, path_d = _ICON_PATHS[name]
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}" '
        f'width="{size}" height="{size}">'
        f'<path fill="{color}" d="{path_d}"/></svg>'
    )
    try:
        renderer = QSvgRenderer(bytearray(svg.encode("utf-8")))
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing, True)
        renderer.render(painter)
        painter.end()
        return pix
    except Exception:
        return None


def _first_link(mod_info):
    """取 Mod 的夸克分享链接：优先 <QLink>，没有则取 <QLinks> 里第一条。"""
    if not mod_info:
        return ""
    link = (mod_info.get("link") or "").strip()
    if link:
        return link
    for l in (mod_info.get("batch_links") or []):
        if l and l.strip():
            return l.strip()
    return ""


def find_mod_dir(game_path, mod_name):
    """
    找 Mod 在本地的安装目录：Mods/<名> 或 Mods/Disabled/<名>。

    少数 Mod 是散装 dll（没有自己的文件夹），此时返回该 dll 所在的目录。
    目录名与 Mod 名做归一化比较（容忍大小写/符号差异）。找不到返回 ""。
    """
    if not game_path or not mod_name:
        return ""
    try:
        mods_dir = get_mods_dir(game_path)
    except Exception:
        return ""
    if not os.path.isdir(mods_dir):
        return ""

    target = normalize_name(mod_name)
    for base in (mods_dir, os.path.join(mods_dir, "Disabled")):
        if not os.path.isdir(base):
            continue
        try:
            for entry in os.listdir(base):
                p = os.path.join(base, entry)
                if os.path.isdir(p) and normalize_name(entry) == target:
                    return p
                # 散装 dll：Mod 名与文件名（去扩展名）一致时，打开它所在目录
                if (os.path.isfile(p) and entry.lower().endswith(".dll")
                        and normalize_name(os.path.splitext(entry)[0]) == target):
                    return base
        except OSError:
            continue
    return ""


def get_mod_settings_dir():
    """
    Hollow Knight 的持久化数据目录：Mod 的全局设置（GlobalSettings）都写在这里。
    即 Unity 的 Application.persistentDataPath，与 ModLog.txt 同级。
    """
    user_profile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    return os.path.join(user_profile, "AppData", "LocalLow", "Team Cherry", "Hollow Knight")


_GLOBAL_SETTINGS_SUFFIX = ".GlobalSettings.json"


def _config_name_candidates(mod_name):
    """
    配置文件名的候选（不含 .GlobalSettings.json 后缀）。

    Mod 的显示名与设置文件名常不一致，例如：
      ItemChanger  -> ItemChangerMod
      SFCore       -> SFCoreMod
      Randomizer 4 -> RandomizerMod
    因此按「原名 / 加 Mod 后缀 / 去尾部版本号再加 Mod 后缀 / 去空格」等逐一尝试。
    """
    name = (mod_name or "").strip()
    if not name:
        return []
    cands = [name, name + "Mod"]
    if name.lower().endswith("mod"):
        cands.append(name[:-3])
    # 去掉结尾的版本号/数字：Randomizer 4 -> Randomizer
    stripped = re.sub(r"[\s\d._-]+$", "", name).strip()
    if stripped and stripped != name:
        cands.append(stripped)
        cands.append(stripped + "Mod")
    no_space = name.replace(" ", "")
    if no_space != name:
        cands.append(no_space)
        cands.append(no_space + "Mod")
    seen, out = set(), []
    for c in cands:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def find_mod_config_file(game_path, mod_name):
    """
    找 Mod 的配置文件（GlobalSettings），与 Lumafly 一致的做法。

    主查位置：Hollow Knight 持久化目录下的 <Mod名>.GlobalSettings.json
      Windows: %USERPROFILE%/AppData/LocalLow/Team Cherry/Hollow Knight/
    匹配顺序：候选名精确命中 → 大小写不敏感命中 → 归一化比较（容忍空格/符号差异）。
    兜底：极少数 Mod 把 json 直接放在自己的安装目录里（Mods/<名>/、含 Disabled）。

    找不到返回 ""（调用方据此把编辑图标置灰）。
    """
    if not mod_name:
        return ""

    # 1) 持久化目录：绝大多数 Mod 的 GlobalSettings 都在这里
    settings_dir = get_mod_settings_dir()
    if os.path.isdir(settings_dir):
        try:
            files = [f for f in os.listdir(settings_dir)
                     if f.lower().endswith(_GLOBAL_SETTINGS_SUFFIX.lower())]
        except OSError:
            files = []
        stem_map = {f[:-len(_GLOBAL_SETTINGS_SUFFIX)]: os.path.join(settings_dir, f)
                    for f in files}
        cands = _config_name_candidates(mod_name)
        for stem in cands:
            if stem in stem_map:
                return stem_map[stem]
            low = stem.lower()
            for k, v in stem_map.items():
                if k.lower() == low:
                    return v
        targets = {normalize_name(s) for s in cands}
        for k, v in stem_map.items():
            if normalize_name(k) in targets:
                return v

    # 2) 兜底：Mod 安装目录内的 json
    if not game_path:
        return ""
    try:
        mods_dir = get_mods_dir(game_path)
    except Exception:
        return ""
    if not os.path.isdir(mods_dir):
        return ""

    target = normalize_name(mod_name)
    dirs = []
    for base in (mods_dir, os.path.join(mods_dir, "Disabled")):
        if not os.path.isdir(base):
            continue
        try:
            for entry in os.listdir(base):
                p = os.path.join(base, entry)
                if os.path.isdir(p) and normalize_name(entry) == target:
                    dirs.append(p)
        except OSError:
            continue

    named = (
        f"{mod_name}.GlobalSettings.json",
        f"{mod_name}.json",
        "GlobalSettings.json",
        "Settings.json",
        "settings.json",
        "Config.json",
        "config.json",
    )
    fallback = ""
    for d in dirs:
        for n in named:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
        # 仅当目录里恰好只有一个 .json 时才认它，避免打开无关资源文件
        try:
            jsons = [e for e in os.listdir(d)
                     if e.lower().endswith(".json") and not e.startswith(".")]
        except OSError:
            jsons = []
        if len(jsons) == 1:
            fallback = fallback or os.path.join(d, jsons[0])
    return fallback


# ============================================================
# 自定义详情卡片组件
# ============================================================

class DetailCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        # 与 _section_card_style() 里的 #DetailCard 选择器对应
        self.setObjectName("DetailCard")
        self.setStyleSheet(_section_card_style())
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 16, 20, 16)
        self._layout.setSpacing(10)

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
    def __init__(self, mod_name, display_name, enabled=True, has_update=False, parent=None, list_item=None):
        super().__init__(parent)

        self.mod_name = mod_name
        self.display_name = display_name
        self.enabled = enabled
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

        # 「待更新」按钮：本地 Mod 有可用更新时显示（点击切到在线页去更新）
        # 必须带 parent：_update_action_btn() 里会 setVisible(True)，而这一刻按钮
        # 还没被 addWidget——没有父控件的 QPushButton 一旦 setVisible(True)，Qt 会
        # 把它当成独立顶层窗口弹出来，表现就是切页时闪过一个空白小方块。
        self.action_btn = QPushButton(self)
        self.action_btn.setFixedSize(64, 28)
        self.action_btn.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        bg_layout.addWidget(self.action_btn)
        self._update_action_btn()   # 挂进布局后再定状态/可见性

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

    def _update_status_dot(self, enabled=None):
        if enabled is None:
            enabled = self.enabled
        else:
            self.enabled = enabled
        if self.has_update:
            color = "#ff9500"
        elif enabled:
            color = "#34c759"
        else:
            color = "#666666"
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
        """本地 Mod 有可用更新时显示「待更新」按钮（点击切到在线页更新）。"""
        if self.has_update:
            self.action_btn.setText("待更新")
            self.action_btn.setVisible(True)
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
        else:
            self.action_btn.setVisible(False)
            self.action_btn.setText("")

    def set_selected(self, selected):
        # 状态未变直接返回：拖拽/高频刷新会逐行调用，
        # 无条件重设 QSS 会触发整表样式重算，是明显的卡顿来源
        if getattr(self, "is_selected", None) == selected:
            return
        self.is_selected = selected
        self._update_bg_style()

    def update_status(self, enabled):
        """切换启用/禁用后立即刷新状态文案与徽标，直接显示最终态
        （已启用 / 已禁用），避免先闪一下「已开启 / 已关闭」中间态。"""
        self.enabled = enabled
        self._update_status_dot(enabled)
        self._clear_status_badges()
        if enabled:
            self.status_label.setText("✅ 模组已启用")
            self.status_label.setStyleSheet(
                "color: #34c759; background: transparent; border: none;")
            self._add_status_badge("已启用", "#ffffff", "#34c759")
        else:
            self.status_label.setText("⛔ 模组已禁用")
            self.status_label.setStyleSheet(
                "color: #ff6b6b; background: transparent; border: none;")
            self._add_status_badge("已禁用", "#ffffff", "#888888")


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

        # 同上：带 parent 创建 + 先挂布局再定可见性，避免按钮以顶层窗口身份闪现
        self.action_btn = QPushButton(self)
        self.action_btn.setFixedSize(64, 28)
        self.action_btn.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        bg_layout.addWidget(self.action_btn)
        self._update_action_btn()

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

    def set_downloading(self, pct=None):
        """下载中状态：按钮转成进度显示并禁用，避免重复触发"""
        if pct is None:
            self.action_btn.setText("下载中…")
        else:
            self.action_btn.setText(f"{pct}%")
        self.action_btn.setCursor(Qt.BusyCursor)
        self.action_btn.setEnabled(False)
        self.action_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a5276;
                color: #85d3ff;
                border: none;
                border-radius: 14px;
                font-size: 11px;
                font-weight: 700;
                padding: 0px;
            }
        """)

    def set_installing(self):
        """安装中状态：下载完成后校验/解压期间展示，禁用按钮避免误触"""
        self.action_btn.setText("安装中…")
        self.action_btn.setCursor(Qt.BusyCursor)
        self.action_btn.setEnabled(False)
        self.action_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a3f14;
                color: #ffd166;
                border: none;
                border-radius: 14px;
                font-size: 11px;
                font-weight: 700;
                padding: 0px;
            }
        """)

    def set_done(self, status):
        """完成态：恢复按钮可用，并简短展示结果（已安装 / 已最新 / 失败）"""
        self.action_btn.setCursor(Qt.PointingHandCursor)
        self.action_btn.setEnabled(True)
        if status in ("installed", "updated"):
            text, bg, fg = "✓ 已安装", "#1e5631", "#7CFC9B"
        elif status == "skipped":
            text, bg, fg = "已最新", "#333333", "#bbbbbb"
        else:
            text, bg, fg = "✘ 失败", "#5b1f1f", "#ff9b9b"
        self.action_btn.setText(text)
        self.action_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: none;
                border-radius: 14px;
                font-size: 11px;
                font-weight: 700;
                padding: 0px;
            }}
        """)

    def set_selected(self, selected):
        # 同上：状态未变化时跳过样式重算
        if getattr(self, "is_selected", None) == selected:
            return
        self.is_selected = selected
        self._update_bg_style()


# ============================================================
# 在线 Mod 下载线程（夸克下载 + 智能安装）
# ============================================================
class OnlineDownloadWorker(QThread):
    """后台线程：下载阶段把任务闭包（前置们 + 目标本体）并发下载，安装阶段串行。

    并行支持：每个目标 Mod 一个 Worker / 一批（batch_id）；批内 zip 由
    core.online_install 的线程池并发下载（共享依赖全局只下一次），
    事件按「任务名」精确对应到弹窗各自的行。
    """
    log = Signal(str, str)
    task_started = Signal(str, str)             # (batch_id, Mod 名) 该任务下载开始/入队
    progress = Signal(str, str, int)            # (batch_id, Mod 名, 下载百分比)
    installing = Signal(str, str)               # (batch_id, Mod 名) 进入校验/安装阶段
    task_done = Signal(str, str, str)           # (batch_id, Mod 名, installed/updated/skipped)
    stage = Signal(str)                         # 夸克实时阶段消息（解析/转存/取地址…）
    finished = Signal(str, bool, str, str)      # (batch_id, 是否成功, 目标 Mod 名, 摘要/错误)

    def __init__(self, game_path, batch_id, target_name, tasks, parallel=None, parent=None):
        super().__init__(parent)
        self.game_path = game_path
        self.batch_id = batch_id
        self.target_name = target_name
        self.tasks = tasks
        self.parallel = parallel         # 同批同时下载的路数（设置里可调，None 用默认）
        self._last_emit = 0.0          # 上次真正发出进度信号的时间（节流）
        self._emit_interval = 0.08     # 最小发信号间隔（秒），避免高频刷爆 UI 事件队列

    def run(self):
        try:
            from core.online_install import run_install_batch
            res = run_install_batch(
                self.game_path, self.tasks,
                log=lambda m, l: self.log.emit(m, l),
                task_progress=lambda name, done, total: self._emit_pct(name, done, total),
                on_task_started=lambda name: self.task_started.emit(self.batch_id, name),
                on_installing=lambda name: self.installing.emit(self.batch_id, name),
                task_done=lambda name, status: self.task_done.emit(self.batch_id, name, status),
                on_status=lambda msg: self.stage.emit(msg),
                parallel=self.parallel,
            )
            statuses = res.get("statuses", {})
            labels = {"installed": "全新安装", "updated": "已更新", "skipped": "已是最新跳过"}
            detail = "、".join(f"{n}（{labels.get(st, st)}）" for n, st in statuses.items())
            self.log.emit(f"✅ 全部完成：{detail or '无任务'}", "success")
            # 弹窗/悬浮面板只报整体结果，不逐个点名；细节留在日志里看
            self.finished.emit(self.batch_id, True, self.target_name, "")
        except Exception as e:
            self.log.emit(f"❌ 下载安装中止：{e}", "error")
            self.finished.emit(self.batch_id, False, self.target_name, str(e))

    def _emit_pct(self, task_name, done, total):
        if not total:
            return
        pct = max(0, min(100, int(done * 100 / total)))
        now = time.monotonic()
        # 节流：下载线程每收一小块就回调一次，若全量转发会以每秒上百次的速度
        # 刷爆 UI 事件队列，导致界面（含进度条）一卡一跳。限频后仅 100% 强制补发。
        if pct != 100 and (now - self._last_emit) < self._emit_interval:
            return
        self._last_emit = now
        self.progress.emit(self.batch_id, task_name, pct)


def _github_owner_repo(url):
    """从 GitHub 仓库地址里提取 owner/repo（去掉 .git、查询串与末尾斜杠）。"""
    if not url:
        return ""
    m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s#?]+)", url)
    if not m:
        return ""
    owner, repo = m.group(1).strip(), m.group(2).strip()
    if repo.lower().endswith(".git"):
        repo = repo[:-4]
    return f"{owner}/{repo}" if owner and repo else ""


def fetch_readme(repo_url, timeout=8, total_budget=20, ssl_warn_callback=None):
    """
    拉取 Mod 仓库的 README.md，返回 (markdown 原文, base_url)。

    国内可达性实测（本机「强制直连」、不走系统代理）：
      cdn.jsdelivr.net          200  ✅  主用
      gcore.jsdelivr.net        200  ✅  jsDelivr 备用域名
      fastly.jsdelivr.net       失败（仅代理可用）
      raw.githubusercontent.com 失败（证书拦截；verify=False 亦读超时）

    所以把 jsDelivr 系域名全部排前面，raw.githubusercontent 仅作最后兜底
    （对开了代理/VPN 的用户仍有效）；并用 total_budget 限制总耗时，
    避免在国内网络下逐个超时把界面拖住。

    base_url 为 README 所在目录，用于解析其中的相对图片/链接。
    """
    owner_repo = _github_owner_repo(repo_url)
    fallback_base = f"https://cdn.jsdelivr.net/gh/{owner_repo}/" if owner_repo else ""
    if not owner_repo:
        return "", ""
    try:
        from utils.common import safe_requests_get
    except Exception:
        return "", fallback_base
    # jsDelivr 省略版本号即取默认分支；HEAD 同理，覆盖非 main/master 的仓库
    urls = (
        f"https://cdn.jsdelivr.net/gh/{owner_repo}/README.md",
        f"https://gcore.jsdelivr.net/gh/{owner_repo}/README.md",
        f"https://fastly.jsdelivr.net/gh/{owner_repo}/README.md",
        f"https://raw.githubusercontent.com/{owner_repo}/HEAD/README.md",
        f"https://raw.githubusercontent.com/{owner_repo}/main/README.md",
        f"https://raw.githubusercontent.com/{owner_repo}/master/README.md",
    )
    deadline = time.time() + total_budget
    for u in urls:
        if time.time() > deadline:
            break
        try:
            r = safe_requests_get(u, timeout=timeout, ssl_warn_callback=ssl_warn_callback)
            if r is not None and getattr(r, "status_code", 0) == 200:
                text = r.content.decode("utf-8", errors="replace")
                if text.strip():
                    return text, u.rsplit("/", 1)[0] + "/"
        except Exception:
            continue
    return "", fallback_base


# README 里两种图片写法：markdown ![](x) 与原生 HTML <img src="x">
_MD_IMG_RE = re.compile(r"!\[[^\]]*\]\(\s*<?([^)>\s]+)", re.I)
_HTML_IMG_RE = re.compile(r"""<img[^>]*\bsrc\s*=\s*["']([^"']+)["']""", re.I)
# 整行只有一个 <img> 标签
_IMG_LINE_RE = re.compile(r"<img\b[^>]*/?>", re.I)


def _isolate_image_lines(markdown):
    """
    让独占一行的 <img> 单独成段。

    README 里整行写 <img> 时，markdown 会把它并进上一段，图片便跟在正文后面、
    被顶到行尾；再叠加 README 里写死的 width="800"（如 ToggleableBindings），
    宽图就会被挤出可视区，只能看到（也只能点到）右半张。这里给它前后补空行，
    使其独占一段、从左边距开始排版。
    """
    if not markdown:
        return markdown
    out = []
    for line in markdown.splitlines():
        s = line.strip()
        if s and _IMG_LINE_RE.fullmatch(s):
            out.extend(("", s, ""))
        else:
            out.append(line)
    return "\n".join(out)


def _collect_remote_images(markdown, base_url):
    """收集 README 中的远程图片 URL（相对路径按 base_url 解析），去重保序。"""
    if not markdown:
        return []
    found = _MD_IMG_RE.findall(markdown) + _HTML_IMG_RE.findall(markdown)
    out, seen = [], set()
    for u in found:
        u = (u or "").strip().strip("<>")
        if not u or u.lower().startswith("data:"):
            continue
        abs_u = urljoin(base_url, u) if base_url else u
        if not abs_u.lower().startswith(("http://", "https://")):
            continue
        if abs_u not in seen:
            seen.add(abs_u)
            out.append(abs_u)
    return out


# 直连失败时的公共图片代理兜底：wsrv.nl 会把任意图片取回并转成 PNG。
# 用途：README 常把配图挂在 catbox.moe 等境外图床，国内直连会被 RST（连接重置），
# 而 README 正文能通过 jsDelivr 拿到 —— 正文有、图没有，就是这种情况。代理可达，
# 于是被墙的图也能显示出来；只有直连确实失败时才走它，不增加正常情况的开销。
_IMAGE_PROXY = "https://wsrv.nl/?url={}"
# SVG 走代理时要**主动要求更大的栅格**：README 常把一个自带尺寸只有 32px 的小 SVG
# 放大显示（HKMP 的 logo 写死 width="52"），而代理默认只按 SVG 自带尺寸出图，
# 拿到 32px 位图再放大 2~3 倍绘制就糊了。矢量放大无损，所以直接要 512px 的。
_SVG_PROXY = "https://wsrv.nl/?url={}&w=512&h=512&fit=inside"

# 很多图床/代理（含 wsrv.nl 背后的 Cloudflare）对没有 UA 的请求直接回 403，
# 带一个浏览器 UA 才正常返回图片。
_IMAGE_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}

# SVG 栅格化的上下限：至少 256px（图标会被放大显示），至多 1024px（别太吃内存）
_SVG_MIN_SIDE = 256
_SVG_MAX_SIDE = 1024


def _is_svg_url(url):
    return url.split("?", 1)[0].lower().endswith(".svg")


def _proxy_url(url):
    """公共图片代理地址；SVG 额外要求按矢量栅格成更大的位图。"""
    if _is_svg_url(url):
        return _SVG_PROXY.format(quote(url, safe=""))
    return _IMAGE_PROXY.format(quote(url, safe=""))


def _looks_like_svg(content):
    head = content[:512].lstrip().lower()
    return head.startswith(b"<") and b"<svg" in head


def _rasterize_svg(content):
    """把 SVG 字节按矢量栅格成足够大的位图；失败返回 None（调用方退回 Qt 解码）。"""
    if QSvgRenderer is None:
        return None
    try:
        renderer = QSvgRenderer(QByteArray(content))
        if not renderer.isValid():
            return None
        size = renderer.defaultSize()
        if size.isEmpty():
            size = QSize(_SVG_MIN_SIDE, _SVG_MIN_SIDE)
        side = max(size.width(), size.height(), 1)
        target = max(float(_SVG_MIN_SIDE), min(float(_SVG_MAX_SIDE), side * 8.0))
        scale = target / side
        img = QImage(max(1, int(round(size.width() * scale))),
                     max(1, int(round(size.height() * scale))),
                     QImage.Format_ARGB32)
        img.fill(0)
        painter = QPainter(img)
        renderer.render(painter)
        painter.end()
        return img
    except Exception:
        return None


def _decode_image(content):
    """图片字节 -> QImage。SVG 按矢量重新栅格（避免被放大显示时发虚），其余交 Qt 解码。"""
    if _looks_like_svg(content):
        img = _rasterize_svg(content)
        if img is not None:
            return img
    img = QImage()
    if img.loadFromData(content) and not img.isNull():
        return img
    return None


def _download_image(url, timeout=10, ssl_warn_callback=None):
    """下载并解码单张图片，失败返回 None。"""
    try:
        from utils.common import safe_requests_get
        r = safe_requests_get(url, timeout=timeout, ssl_warn_callback=ssl_warn_callback,
                              headers=_IMAGE_HEADERS)
        if r is None or getattr(r, "status_code", 0) != 200:
            return None
        return _decode_image(r.content)
    except Exception:
        return None


def fetch_readme_images(urls, timeout=10, ssl_warn_callback=None):
    """
    预下载 README 里的**原图**，返回 {url: QImage}（失败的跳过，不影响正文）。

    必须在后台线程调用。原因：Qt 的 QTextBrowser 自己**不会下载 http(s) 图片**，
    loadResource 对网络图片一律返回空，于是带 width 的 <img> 会预留出一大块空白/
    乱码区域。改为渲染前把图备好，交给 _ReadmeBrowser 从缓存直接取，
    既修好显示，也避免在绘制过程中联网卡住界面。

    这里保留原图不缩放：内联显示时的缩窄由 _ReadmeBrowser 懒处理，
    点击图片预览时才能看到真正的原始尺寸。
    """
    result = {}
    if not urls:
        return result
    try:
        from utils.common import safe_requests_get      # noqa: F401  探测依赖可用
    except Exception:
        return result
    for u in urls:
        img = _download_image(u, timeout, ssl_warn_callback)
        if img is None:
            # 直连失败（多为境外图床被重置）时经公共图片代理重取。
            # 结果仍以**原图 URL** 为 key，才能和 <img src> 对上。
            img = _download_image(_proxy_url(u), timeout, ssl_warn_callback)
        if img is not None:
            result[u] = img
    return result


def show_image_preview(parent, image):
    """以原尺寸展示图片（超出屏幕可视区时等比缩小以便完整查看），点击关闭。"""
    dlg = QDialog(parent)
    dlg.setWindowTitle("图片预览 — %d × %d" % (image.width(), image.height()))
    dlg.setStyleSheet("QDialog { background-color: #1a1a1a; }")

    pix = QPixmap.fromImage(image)
    screen = QApplication.primaryScreen()
    if screen is not None:
        avail = screen.availableGeometry()
        max_w, max_h = int(avail.width() * 0.92), int(avail.height() * 0.92)
        if pix.width() > max_w or pix.height() > max_h:
            pix = pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel()
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet("background: #1a1a1a;")
    lbl.setPixmap(pix)
    lbl.setCursor(QCursor(Qt.PointingHandCursor))
    lbl.mousePressEvent = lambda e: dlg.close()
    layout.addWidget(lbl)

    dlg.resize(pix.size())
    dlg.exec()


class _ReadmeBrowser(MarkdownBrowser):
    """
    能显示网络图片的 Markdown 浏览器：
      - 排版与样式走 MarkdownBrowser（markdown-it + 暗色样式表）；
      - QTextBrowser 自带的 loadResource 只认 qrc/本地文件，对 http(s) 一律返回空，
        README 里的网络图片会渲染成空白/乱块，所以改用预下载好的缓存；
      - 点击图片会以原尺寸弹出预览（图片被链接包裹时仍走原链接）；
      - 内联显示按需缩窄并缓存，避免每次重绘都重新缩放。
    """

    # README 的图全走本地缓存，缓存里没有的（下载失败/被墙）就没有渲染出来的可能，
    # 直接删掉，免得 Qt 画一个裂图占位方块。
    drop_unavailable_images = True

    # 视口左右留点余量，别让图片顶到边框/滚动条上
    _SIDE_PAD = 24
    _MIN_WIDTH = 200

    def __init__(self, images=None, parent=None):
        super().__init__(parent)
        self._images = images or {}   # 原图（点击预览用）
        self._scaled = {}             # 内联用的位图（懒缓存，按「显示宽度 + DPR」失效）
        self._requested = {}          # 作者在 <img width="N"> 里写死的显示宽度

    def available_image_urls(self):
        # 交给 render_markdown：判断哪些图真能加载出来，加载不出来的直接删掉
        return set(self._images.keys())

    def set_markdown(self, text):
        # 尺寸属性在渲染时会被统一剥掉（见 md_render._process_images），
        # 这里先把作者想要的宽度读回来，出图时按它复现。
        self._requested = collect_image_widths(text)
        self._scaled.clear()
        super().set_markdown(text)

    def _display_width(self, key):
        """这张图该显示多宽（逻辑像素）：作者写死的宽度优先，但不超出视口。"""
        limit = max(self._MIN_WIDTH, self.viewport().width() - self._SIDE_PAD)
        natural = self._images[key].width() or limit
        want = lookup_url(self._requested, key) or natural
        return max(1, min(int(want), limit))

    def loadResource(self, type_, url):
        if url.isValid():
            key = url.toString()
            if key in self._images:
                return self._image_for(key)
        return super().loadResource(type_, url)

    def _image_for(self, key):
        """
        按「显示宽度 × 设备像素比」出图，并把 DPR 标注在图上。

        两处都要照顾，少一个都会糊（在 150% 缩放的屏幕上实测过）：
          - 像素数：Qt 在缩放屏上按 DPR 放大绘制，只给逻辑像素的位图就会被拉伸发虚；
            给足「显示宽度 × DPR」个像素，绘制才能 1:1。
          - devicePixelRatio：Qt 的富文本布局认这个值，按「像素数 ÷ DPR」当逻辑尺寸
            排版；不标注的话图片会按像素数占位，缩略图会撑成两倍大。

        缓存按 (显示宽度, DPR) 失效，窗口缩放或换屏后会自动重出。
        """
        dpr = self.devicePixelRatioF() or 1.0
        logical = self._display_width(key)
        cached = self._scaled.get(key)
        if cached is not None and cached[0] == (logical, dpr):
            return cached[1]
        img = self._images[key]
        px = max(1, int(round(logical * dpr)))
        if img.width() == px:
            out = QImage(img)      # 浅拷贝：下面要标注 DPR，不能污染原图（点击预览要用）
        else:
            out = img.scaledToWidth(px, Qt.SmoothTransformation)
        out.setDevicePixelRatio(dpr)
        self._scaled[key] = ((logical, dpr), out)
        return out

    def _image_at(self, pos):
        """
        返回该位置下的图片 URL；不在图片上、或图片被链接包裹时返回 ''。

        用 documentLayout().hitTest() 而不是 cursorForPosition()：后者在大图上
        吸附行为不准，实测只能命中图片右半边，左半边点不中。
        """
        try:
            if self.anchorAt(pos):
                return ""
            # 视口坐标 -> 文档坐标
            p = pos + QPoint(self.horizontalScrollBar().value(),
                             self.verticalScrollBar().value())
            charpos = self.document().documentLayout().hitTest(p, Qt.ExactHit)
            if charpos < 0:
                return ""
            cur = QTextCursor(self.document())
            cur.setPosition(charpos + 1)
            fmt = cur.charFormat()
            if fmt.isImageFormat():
                return fmt.toImageFormat().name()
        except Exception:
            pass
        return ""

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint() if hasattr(e, "position") else e.pos()
        if self._image_at(pos):
            self.viewport().setCursor(QCursor(Qt.PointingHandCursor))
        else:
            self.viewport().unsetCursor()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        pos = e.position().toPoint() if hasattr(e, "position") else e.pos()
        url = self._image_at(pos) if e.button() == Qt.LeftButton else ""
        if url:
            img = self._images.get(url)
            if img is not None and not img.isNull():
                show_image_preview(self, img)
                e.accept()
                return
        super().mouseReleaseEvent(e)


class _ReadmeWorker(QThread):
    """后台拉取 README 及其配图：网络请求不能卡住 UI 主线程。"""

    done = Signal(str, object, str, str)  # (markdown, {url: QImage}, base_url, 错误信息)

    def __init__(self, repo_url, parent=None):
        super().__init__(parent)
        self.repo_url = repo_url or ""

    def run(self):
        try:
            text, base = fetch_readme(self.repo_url)
        except Exception as e:
            self.done.emit("", {}, "", f"获取 README 失败：{e}")
            return
        if not text:
            self.done.emit(
                "", {}, base,
                "未能获取 README：该仓库可能没有 README.md，或当前网络无法访问 GitHub。")
            return
        try:
            images = fetch_readme_images(_collect_remote_images(text, base))
        except Exception:
            images = {}
        self.done.emit(text, images, base, "")


class _TranslateWorker(QThread):
    """后台翻译 README：长文本要走多次网络请求，不能卡住 UI 主线程。"""

    done = Signal(str, str)  # (译文, 错误信息)

    def __init__(self, markdown, parent=None):
        super().__init__(parent)
        self._markdown = markdown or ""

    def run(self):
        try:
            from utils.translator import translate_markdown
            text = translate_markdown(self._markdown)
        except Exception as e:      # noqa: BLE001 网络类异常统一转成提示
            self.done.emit("", str(e))
            return
        self.done.emit(text or "", "")


def show_readme_dialog(parent, title, markdown, images=None, base_url=""):
    """展示 README 弹窗（markdown 渲染；配图走预下载缓存）。内容由调用方提前取好。"""
    dlg = QDialog(parent)
    dlg.setWindowTitle(f"README — {title}")
    dlg.resize(800, 600)
    dlg.setStyleSheet("QDialog { background-color: #1a1a1a; }")

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(10)

    browser = _ReadmeBrowser(images)
    browser.setStyleSheet("""
        QTextBrowser {
            background-color: #1c1c20;
            border: 1px solid #33333c;
            border-radius: 8px;
            padding: 16px 18px;
        }
    """)
    def _apply(md):
        browser.set_markdown(_isolate_image_lines(md))
        if base_url:
            # 让 README 里的相对图片/链接能解析到仓库目录（需在 setMarkdown 之后设置）
            browser.document().setBaseUrl(QUrl(base_url))
        browser.moveCursor(QTextCursor.Start)

    _apply(markdown)
    layout.addWidget(browser, stretch=1)

    # 翻译状态：译文只在首次点击时取一次，之后在原文/译文间来回切换
    original_md = markdown
    cache = {"translated": None}
    showing = {"translated": False}

    btn_row = QHBoxLayout()

    trans_btn = QPushButton("🌐 一键翻译")
    trans_btn.setFixedSize(120, 34)
    trans_btn.setCursor(QCursor(Qt.PointingHandCursor))
    trans_btn.setStyleSheet("""
        QPushButton {
            background: #2a2a32; color: #7ab8ff;
            border: 1px solid #3a3a44; border-radius: 8px;
            font-size: 13px; font-weight: bold;
        }
        QPushButton:hover { background: #34343e; }
        QPushButton:disabled {
            color: #4f4f5c; border-color: #33333c; background: transparent;
        }
    """)

    def _on_translate():
        if showing["translated"]:
            # 当前是译文 -> 切回原文
            showing["translated"] = False
            _apply(original_md)
            trans_btn.setText("🌐 一键翻译")
            return
        if cache["translated"] is not None:
            # 已翻过 -> 直接复用，不再发请求
            showing["translated"] = True
            _apply(cache["translated"])
            trans_btn.setText("📄 显示原文")
            return

        trans_btn.setEnabled(False)
        trans_btn.setText("🌐 翻译中…")
        QToolTip.showText(QCursor.pos(), "正在调用微软翻译…", trans_btn)

        def _done(text, err):
            QToolTip.hideText()
            trans_btn.setEnabled(True)
            if text:
                cache["translated"] = text
                showing["translated"] = True
                _apply(text)
                trans_btn.setText("📄 显示原文")
            else:
                trans_btn.setText("🌐 一键翻译")
                QMessageBox.information(
                    dlg, "翻译失败",
                    f"未能完成翻译：{err or '未知错误'}\n请检查网络后重试。")

        worker = _TranslateWorker(original_md, dlg)
        worker.done.connect(_done)
        # 持有引用，否则线程还在跑就被 GC 回收，信号永远等不到
        dlg._translate_worker = worker
        worker.start()

    trans_btn.clicked.connect(_on_translate)
    btn_row.addWidget(trans_btn)
    btn_row.addStretch()
    close_btn = QPushButton("关闭")
    close_btn.setFixedSize(100, 34)
    close_btn.setCursor(QCursor(Qt.PointingHandCursor))
    close_btn.setStyleSheet("""
        QPushButton {
            background: #2a2a32; color: #d8d8e0;
            border: 1px solid #3a3a44; border-radius: 8px;
            font-size: 13px; font-weight: bold;
        }
        QPushButton:hover { background: #34343e; }
    """)
    close_btn.clicked.connect(dlg.accept)
    btn_row.addWidget(close_btn)
    layout.addLayout(btn_row)

    dlg.exec()


# ============================================================
# 详情面板
# ============================================================

class ModDetailPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(16)

        # Mod 名右下角的动作图标（打开文件夹 / 编辑配置 / 复制夸克链接）
        self._game_path = ""
        self._config_path = ""
        self._mod_dir = ""
        self._qlink = ""
        self._deps = []
        self._mod_name = ""
        self._readme_text = ""
        self._readme_worker = None
        self._link_provider: Optional[Callable[[str], str]] = None

        # 标题卡片
        self.title_card = QFrame()
        # 同上：必须用 objectName 限定，否则卡片内的标题 QLabel 也会被套上边框
        self.title_card.setObjectName("DetailTitleCard")
        self.title_card.setStyleSheet("""
            #DetailTitleCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #242a3d, stop:1 #1a1b26);
                border: 1px solid #353a4d;
                border-radius: 16px;
            }
        """)
        title_layout = QVBoxLayout(self.title_card)
        title_layout.setContentsMargins(24, 20, 24, 20)
        title_layout.setSpacing(8)

        title_top_row = QHBoxLayout()
        title_top_row.setSpacing(12)
        title_top_row.setContentsMargins(0, 0, 0, 0)

        self.title_en = QLabel("")
        self.title_en.setFont(QFont("Microsoft YaHei", 24, QFont.Bold))
        self.title_en.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background: transparent;
                border: none;
                padding: 0px;
                font-size: 24px;
                font-weight: bold;
            }
        """)
        self.title_en.setWordWrap(True)
        self.title_en.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        title_top_row.addWidget(self.title_en)

        self.version_badge = QLabel("")
        self.version_badge.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        self.version_badge.setStyleSheet(
            _version_badge_style("#7ab8ff", "rgba(0,122,255,0.16)", "rgba(0,122,255,0.38)"))
        self.version_badge.setFixedHeight(26)
        self.version_badge.setAlignment(Qt.AlignCenter)
        title_top_row.addWidget(self.version_badge, 0, Qt.AlignTop)

        title_layout.addLayout(title_top_row)

        # 中文名：作为大标题之下的次要信息
        self.title_cn = QLabel("")
        self.title_cn.setFont(QFont("Microsoft YaHei", 14))
        self.title_cn.setStyleSheet("""
            QLabel {
                color: #a8b0c4;
                background: transparent;
                border: none;
                padding: 0px;
                font-size: 14px;
            }
        """)
        self.title_cn.setWordWrap(True)

        # 中文名同行右侧放三个动作图标（即 Mod 名的右下角）
        title_bottom_row = QHBoxLayout()
        title_bottom_row.setSpacing(10)
        title_bottom_row.setContentsMargins(0, 0, 0, 0)
        title_bottom_row.addWidget(self.title_cn, stretch=1)
        self.folder_lbl = self._make_action_icon(self._on_folder_icon_clicked)
        self.config_edit_lbl = self._make_action_icon(self._on_config_icon_clicked)
        self.share_lbl = self._make_action_icon(self._on_share_icon_clicked)
        title_bottom_row.addWidget(self.folder_lbl, 0, Qt.AlignBottom)
        title_bottom_row.addWidget(self.config_edit_lbl, 0, Qt.AlignBottom)
        title_bottom_row.addWidget(self.share_lbl, 0, Qt.AlignBottom)
        title_layout.addLayout(title_bottom_row)

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

        # 原仓库卡片（GitHub 图标 + 可点击跳转，XML <Repository> 为空时隐藏）
        self.repo_card = DetailCard()
        repo_header = QHBoxLayout()
        repo_header.setContentsMargins(0, 0, 0, 0)
        repo_header.setSpacing(8)
        self.repo_icon_lbl = QLabel()
        self.repo_icon_lbl.setFixedSize(18, 18)
        self.repo_icon_lbl.setAlignment(Qt.AlignCenter)
        gh_pix = _render_svg_icon("github", 16, "#c8c8d0")
        if gh_pix is not None:
            self.repo_icon_lbl.setPixmap(gh_pix)
        else:
            self.repo_icon_lbl.setText("GitHub")
            self.repo_icon_lbl.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
            self.repo_icon_lbl.setStyleSheet("color:#c8c8d0; background:transparent; border:none;")
        repo_header.addWidget(self.repo_icon_lbl)
        repo_title = QLabel("原仓库")
        repo_title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        repo_title.setStyleSheet(
            "color:#a0a0a8; background:transparent; border:none; font-size:13px; font-weight:bold;")
        repo_header.addWidget(repo_title)
        repo_header.addStretch()

        # README 按钮：拉取该仓库的 README.md 并在弹窗中展示
        self.readme_btn = QPushButton("📖 README")
        self.readme_btn.setFixedHeight(24)
        self.readme_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.readme_btn.setStyleSheet("""
            QPushButton {
                background: rgba(122,184,255,0.12);
                color: #7ab8ff;
                border: 1px solid rgba(122,184,255,0.35);
                border-radius: 6px;
                padding: 0px 10px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background: rgba(122,184,255,0.24); }
            QPushButton:disabled {
                color: #4f4f5c; border-color: #33333c; background: transparent;
            }
        """)
        self.readme_btn.clicked.connect(self._on_readme_clicked)
        repo_header.addWidget(self.readme_btn)

        self.repo_card.add_widget(self._wrap_in_layout_widget(repo_header))
        self.repo_card.add_divider()
        self._repo_url = ""
        self.repo_link_lbl = QLabel("")
        self.repo_link_lbl.setFont(QFont("Microsoft YaHei", 12))
        self.repo_link_lbl.setStyleSheet(
            "QLabel { color:#5aa9ff; background:transparent; border:none; padding:0px; }")
        self.repo_link_lbl.setCursor(QCursor(Qt.PointingHandCursor))
        self.repo_link_lbl.setWordWrap(True)
        self.repo_link_lbl.mousePressEvent = self._on_repo_link_clicked
        self.repo_card.add_widget(self.repo_link_lbl)
        self.main_layout.addWidget(self.repo_card)

        # 描述卡片
        self.desc_card = DetailCard()
        self.desc_card.add_header("📝", "描  述")
        self.desc_card.add_divider()

        self.desc_cn_lbl = QLabel("")
        self.desc_cn_lbl.setFont(QFont("Microsoft YaHei", 15))
        self.desc_cn_lbl.setStyleSheet("""
            QLabel {
                color: #ececf2;
                background: transparent;
                border: none;
                padding: 0px;
                font-size: 15px;
            }
        """)
        self.desc_cn_lbl.setWordWrap(True)
        self.desc_cn_lbl.setTextFormat(Qt.RichText)
        self.desc_card.add_widget(self.desc_cn_lbl)

        self.desc_en_lbl = QLabel("")
        self.desc_en_lbl.setFont(QFont("Microsoft YaHei", 14))
        self.desc_en_lbl.setStyleSheet("""
            QLabel {
                color: #9ea3b5;
                background: transparent;
                border: none;
                padding: 0px;
                font-size: 14px;
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

        self._dep_checker: Optional[Callable[[str], bool]] = None
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
        self.title_cn.setText("")
        self.title_cn.setVisible(False)
        self._config_path = ""
        self._mod_dir = ""
        self._qlink = ""
        self._deps = []
        self.config_edit_lbl.setVisible(False)
        self.folder_lbl.setVisible(False)
        self.share_lbl.setVisible(False)
        self.version_badge.setText("")
        self.version_badge.setVisible(False)
        self.status_card.setVisible(True)
        self.status_label.setText("👈 点击左侧列表查看详情")
        self.status_label.setStyleSheet("color: #666666; background: transparent; border: none;")
        self._clear_status_badges()
        self.desc_card.setVisible(False)
        self.deps_card.setVisible(False)
        self.integ_card.setVisible(False)
        self.repo_card.setVisible(False)
        self._repo_url = ""

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
        repository="",
        readme="",
        qlink="",
        game_path="",
        is_online_page=False,
        local_version="",
    ):
        self.title_en.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background: transparent;
                border: none;
                padding: 0px;
                font-size: 24px;
                font-weight: bold;
            }
        """)
        self._mod_name = mod_name
        self.title_en.setText(mod_name)
        self.title_cn.setText(chinese_name)
        self.title_cn.setVisible(bool(chinese_name.strip()))

        # 右下角动作图标：各自按可用性置灰（配置 / 本地目录 / 夸克链接）
        self._game_path = game_path or getattr(self, "_game_path", "")
        self._mod_dir = find_mod_dir(self._game_path, mod_name)
        self._config_path = find_mod_config_file(self._game_path, mod_name)
        self._qlink = (qlink or "").strip()
        self._deps = dependencies or []
        self._refresh_action_icons()

        # 版本徽章：待更新时显示「v旧版本 → v新版本」并转为橙色，其它情况只显示当前版本
        if version:
            if has_update and local_version:
                self.version_badge.setText(f"v{local_version} → v{version}")
                self.version_badge.setStyleSheet(
                    _version_badge_style("#ffb454", "rgba(255,149,0,0.18)", "rgba(255,149,0,0.42)"))
            else:
                self.version_badge.setText(f"v{version}")
                self.version_badge.setStyleSheet(
                    _version_badge_style("#7ab8ff", "rgba(0,122,255,0.16)", "rgba(0,122,255,0.38)"))
            self.version_badge.setVisible(True)
        else:
            self.version_badge.setText("")
            self.version_badge.setVisible(False)

        self._clear_status_badges()

        # 在线页：「尚未安装 / 已安装到本地」在列表里已体现，整栏隐藏不再重复展示；
        # 本地页保留「已启用 / 已禁用」状态（可据此操作启停）
        self.status_card.setVisible(not is_online_page)
        if not is_online_page:
            if enabled:
                self.status_label.setText("✅ 模组已启用")
                self.status_label.setStyleSheet(
                    "color: #34c759; background: transparent; border: none; font-size: 14px; font-weight: bold;")
                self._add_status_badge("已启用", "#ffffff", "#34c759")
            else:
                self.status_label.setText("⛔ 模组已禁用")
                self.status_label.setStyleSheet(
                    "color: #ff6b6b; background: transparent; border: none; font-size: 14px; font-weight: bold;")
                self._add_status_badge("已禁用", "#ffffff", "#888888")

        has_desc = bool(desc_cn.strip() or desc_en.strip())
        self.desc_card.setVisible(has_desc)

        self.desc_cn_lbl.setText(desc_cn if desc_cn.strip() else "")
        self.desc_cn_lbl.setVisible(bool(desc_cn.strip()))

        self.desc_en_lbl.setText(desc_en if desc_en.strip() else "")
        self.desc_en_lbl.setVisible(bool(desc_en.strip()))

        # README：XML 自带的优先；为空时按钮会退而去仓库拉 README.md
        self._readme_text = readme or ""

        # 原仓库：有 <Repository> 才显示，点击图标/链接跳转浏览器
        self._repo_url = repository.strip()
        has_repo = bool(self._repo_url)
        self.repo_card.setVisible(has_repo)
        self.repo_link_lbl.setText(self._repo_url if has_repo else "")
        self.repo_link_lbl.setVisible(has_repo)

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

    def _on_repo_link_clicked(self, event):
        url = getattr(self, "_repo_url", "")
        if url:
            QDesktopServices.openUrl(QUrl(url))
        event.accept()

    def _make_action_icon(self, slot):
        """
        统一的动作图标：20x20、透明底、默认隐藏、点击走 slot。

        悬浮提示自己控制：进入后等 _TOOLTIP_WAKE_DELAY_MS 就弹出，离开立即收起。
        """
        # 带 parent 创建：这个标签稍后会被 setVisible(True)，要是那一刻还没挂进
        # 布局，无父控件的它就会以独立顶层窗口闪一下（跟 action_btn 同一个坑）。
        lbl = QLabel(self)
        lbl.setFixedSize(20, 20)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("background: transparent; border: none;")
        lbl.setVisible(False)
        lbl.mousePressEvent = slot
        lbl._tip_text = ""
        lbl._tip_timer = QTimer(lbl)
        lbl._tip_timer.setSingleShot(True)
        lbl._tip_timer.setInterval(_TOOLTIP_WAKE_DELAY_MS)
        lbl._tip_timer.timeout.connect(lambda: self._show_icon_tip(lbl))
        lbl.enterEvent = lambda e: lbl._tip_timer.start()
        lbl.leaveEvent = lambda e: (lbl._tip_timer.stop(), QToolTip.hideText())
        return lbl

    def _show_icon_tip(self, lbl):
        """定时器到点：在鼠标位置弹出该图标的说明。"""
        text = getattr(lbl, "_tip_text", "")
        if text:
            QToolTip.showText(QCursor.pos(), text, lbl)

    def _set_action_icon(self, lbl, icon_name, enabled, tooltip):
        """设置一个动作图标的状态：可用=蓝色+手型光标，不可用=灰色+箭头光标。"""
        pix = _render_svg_icon(icon_name, 16, "#7ab8ff" if enabled else "#4f4f5c")
        if pix is not None:
            lbl.setPixmap(pix)
        else:  # 无 QtSvg 时退化为文字
            lbl.setText(_ICON_FALLBACK_TEXT.get(icon_name, "•"))
            lbl.setStyleSheet(
                f"color: {'#7ab8ff' if enabled else '#4f4f5c'};"
                "background: transparent; border: none;")
        lbl.setVisible(True)
        lbl.setCursor(QCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor))
        lbl._tip_text = tooltip   # 由 _make_action_icon 的定时器弹出，不用原生 setToolTip

    def _refresh_action_icons(self):
        """刷新右下角三个动作图标：编辑配置 / 打开文件夹 / 复制夸克链接。"""
        has_cfg = bool(self._config_path)
        self._set_action_icon(
            self.config_edit_lbl, "edit", has_cfg,
            f"编辑配置文件\n{self._config_path}" if has_cfg
            else "该 Mod 没有配置文件（GlobalSettings）")

        has_dir = bool(self._mod_dir) and os.path.isdir(self._mod_dir)
        self._set_action_icon(
            self.folder_lbl, "folder", has_dir,
            f"打开该 Mod 的本地文件夹\n{self._mod_dir}" if has_dir
            else "该 Mod 未安装到本地")

        has_link = bool(self._qlink)
        dep_n = len(self._deps)
        if has_link:
            extra = f"（本 Mod + {dep_n} 个前置依赖）" if dep_n else ""
            share_tip = f"复制夸克分享链接{extra}"
        else:
            share_tip = "该 Mod 没有配置夸克链接"
        self._set_action_icon(self.share_lbl, "share", has_link, share_tip)

    def _on_config_icon_clicked(self, event):
        path = getattr(self, "_config_path", "")
        if path and os.path.isfile(path):
            # 用系统默认程序打开；没有关联程序时退化为打开所在目录
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))
        event.accept()

    def _on_folder_icon_clicked(self, event):
        d = getattr(self, "_mod_dir", "")
        if d and os.path.isdir(d):
            QDesktopServices.openUrl(QUrl.fromLocalFile(d))
        event.accept()

    def _on_readme_clicked(self, _checked=False):
        """README：优先用 XML 自带的 <Readme>；没有则后台去仓库拉 README.md。"""
        if self._readme_worker is not None:
            return
        text = getattr(self, "_readme_text", "")
        if text:
            show_readme_dialog(self, self._mod_name, text)
            return
        # 注：走网络时下面会用 _ReadmeWorker 预下载配图后再弹窗
        url = getattr(self, "_repo_url", "")
        if not url:
            QMessageBox.information(self, "README", "该 Mod 没有 README，也未配置仓库地址")
            return
        self.readme_btn.setEnabled(False)
        QToolTip.showText(QCursor.pos(), "正在加载 README…", self.readme_btn)
        self._readme_worker = _ReadmeWorker(url, self)
        self._readme_worker.done.connect(self._on_readme_loaded)
        self._readme_worker.start()

    def _on_readme_loaded(self, text, images, base_url, err):
        """README 拉取完成：恢复按钮并弹窗展示（或提示失败原因）。"""
        worker = self._readme_worker
        self._readme_worker = None
        try:
            self.readme_btn.setEnabled(True)
            QToolTip.hideText()
            if text:
                show_readme_dialog(self, self._mod_name, text, images, base_url)
            else:
                QMessageBox.information(self, "README", err or "未能获取该 Mod 的 README")
        finally:
            if worker is not None:
                try:
                    worker.deleteLater()
                except RuntimeError:
                    pass

    def _on_share_icon_clicked(self, event):
        """复制「本 Mod + 全部前置依赖」的夸克链接，每行一条。"""
        links = []
        own = getattr(self, "_qlink", "")
        if own:
            links.append(own)
        provider = getattr(self, "_link_provider", None)
        if provider:
            for dep in (getattr(self, "_deps", None) or []):
                try:
                    l = (provider(dep) or "").strip()
                except Exception:
                    l = ""
                if l and l not in links:
                    links.append(l)
        if links:
            QApplication.clipboard().setText("\n".join(links))
            n = len(links)
            QToolTip.showText(
                QCursor.pos(),
                f"已复制 {n} 条夸克链接" + ("（含前置依赖）" if n > 1 else ""),
                self.share_lbl)
        event.accept()

    def set_local_mod_info(self, mod_name, enabled, version="", mod_info=None, game_path=""):
        chinese_name = desc_cn = desc_en = repository = qlink = readme = ""
        deps = integ = []
        if mod_info:
            chinese_name = mod_info.get('chinese_name', '')
            desc_cn = mod_info.get('desc_cn', '')
            desc_en = mod_info.get('desc_en', '')
            deps = mod_info.get('dependencies', [])
            integ = mod_info.get('integrations', [])
            repository = mod_info.get('repository', '')
            readme = mod_info.get('readme', '')
            qlink = _first_link(mod_info)

        self.set_mod_info(
            mod_name=mod_name,
            chinese_name=chinese_name,
            version=version,
            enabled=enabled,
            desc_cn=desc_cn,
            desc_en=desc_en,
            dependencies=deps,
            integrations=integ,
            repository=repository,
            readme=readme,
            qlink=qlink,
            game_path=game_path,
            is_online_page=False,
        )

    def set_online_mod_info(self, mod_name, is_installed, has_update, mod_info=None,
                            local_version="", game_path=""):
        chinese_name = version = desc_cn = desc_en = repository = qlink = readme = ""
        deps = integ = []
        if mod_info:
            chinese_name = mod_info.get('chinese_name', '')
            version = mod_info.get('version', '')
            desc_cn = mod_info.get('desc_cn', '')
            desc_en = mod_info.get('desc_en', '')
            deps = mod_info.get('dependencies', [])
            integ = mod_info.get('integrations', [])
            repository = mod_info.get('repository', '')
            readme = mod_info.get('readme', '')
            qlink = _first_link(mod_info)

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
            repository=repository,
            readme=readme,
            qlink=qlink,
            is_online_page=True,
            local_version=local_version,
            game_path=game_path,
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
        self._rendered = False  # 首次渲染标记：切换标签页时避免重复重建列表
        self._game_path = ""    # 当前游戏路径（文件监听用，刷新时同步）
        # 自定义拖拽区间选择状态（替代 Qt 自带框选，修复自绘行+自动滚动下漏选/丢尾行）
        self._sel_press_row = -1          # 按下时所在行（-1 表示未在拖拽选择中）
        self._sel_press_pos = QPoint()    # 按下位置（viewport 坐标）
        self._sel_last_row = -1           # 兼容旧字段（当前鼠标所在行）
        self._sel_click_anchor = -1       # Shift 扩展用的锚点行（上次单击的行）
        self._sel_anchor_row = -1         # 框选起点行
        self._sel_anchor_off = 0          # 起点在该行内的 y 偏移（可 <0 或 >行高）
        self._sel_end_row = -1            # 框选终点行
        self._sel_end_off = 0             # 终点在该行内的 y 偏移
        self._sel_dragging = False        # 是否已进入拖拽框选
        self._sel_pending_blank = False   # 按下点落在间隙/空白：未拖动则视为“点空白取消选中”
        self._sel_ctrl = False            # 按下瞬间是否按住 Ctrl
        self._sel_shift = False           # 按下瞬间是否按住 Shift
        self._sel_base = set()            # 拖拽开始前已选中的行集合（Ctrl 加选时作基线）
        self._sel_autoscroll = None       # 拖拽到边缘时的自动滚动 QTimer

        # widget 树延迟到首次真正展示本页时才构建（见 _ensure_ui）。
        # 原因：_setup_ui() 要建几百个控件，实测约 0.8s；MainWindow 启动时会一次性
        # 构造全部 4 个页面，用户在首页根本看不到本页，不该让首屏白等这 0.8s。
        self._ui_ready = False
        self._fs_watcher = None
        self._mods_sig = None

    def _ensure_ui(self):
        """首次需要展示本页时才构建 widget 树（并把文件监听挂上去）。"""
        if self._ui_ready:
            return
        self._ui_ready = True
        self._setup_ui()

        # 文件系统监听：Mods 文件夹（含 Disabled 子目录）变动时自动刷新本地列表，
        # 玩家无需手动点刷新。目录变化事件较密集（安装/增删会连续触发），用 400ms
        # 防抖合并为一次刷新。
        self._fs_watcher = QFileSystemWatcher(self)
        self._fs_watcher.directoryChanged.connect(self._on_mods_dir_changed)
        self._fs_watch_timer = QTimer(self)
        self._fs_watch_timer.setSingleShot(True)
        self._fs_watch_timer.setInterval(400)
        self._fs_watch_timer.timeout.connect(
            lambda: self.refresh_mod_list(self._game_path))

        # 兜底轮询：QFileSystemWatcher 在个别 Windows 环境/特定删除操作下可能漏事件，
        # 这里每秒比对一次 Mods 目录快照（文件夹名+修改时间），有变化就刷新。
        # 不依赖 watcher，保证「文件夹变动必刷新」一定成立。
        self._fs_poll_timer = QTimer(self)
        self._fs_poll_timer.setInterval(1000)
        self._fs_poll_timer.timeout.connect(self._poll_mods_dir)
        self._fs_poll_timer.start()

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

        self.multi_select_hint = QLabel("按住 Ctrl 或 Shift 可进行多选，右键单击模组可以快速启用或禁用")
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
        self.search_input.textChanged.connect(self._on_search_text_changed)
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
            self.filter_combo.addItems(["全部模组", "已启用", "已禁用", "待更新"])
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
        self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
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
        self.mod_list.viewport().installEventFilter(self)
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

    # ---------- 鼠标选择：点击 / Shift / Ctrl / 拖拽区间（自实现，替代 Qt marquee） ----------
    def eventFilter(self, obj, event):
        if obj == self.mod_list.viewport():
            t = event.type()
            if t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._on_list_press(event)
                return True
            if t == QEvent.MouseButtonPress and event.button() == Qt.RightButton:
                self._on_list_right_click(event)
                return True
            if t == QEvent.MouseMove and (event.buttons() & Qt.LeftButton) and self._sel_press_row >= 0:
                self._on_list_move(event)
                return True
            if t == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton and self._sel_press_row >= 0:
                self._on_list_release(event)
                return True
        return super().eventFilter(obj, event)

    def _row_at(self, pos):
        """viewport 坐标 -> 行号；不在任何行上返回 -1"""
        item = self.mod_list.itemAt(pos)
        return self.mod_list.row(item) if item is not None else -1

    def _nearest_row(self, pos):
        """把坐标（可能落在行间隙/边缘外）吸附到最近的可视行"""
        vp = self.mod_list.viewport()
        x = pos.x()
        y = pos.y()
        if y < 0:
            y = 0
        elif y >= vp.height():
            y = vp.height() - 1
        row = self._row_at(QPoint(x, y))
        if row >= 0:
            return row
        best, best_d = -1, 10 ** 9
        for i in range(self.mod_list.count()):
            item = self.mod_list.item(i)
            if item is None or item.isHidden():
                continue
            rect = self.mod_list.visualItemRect(item)
            d = 0
            if y < rect.top():
                d = rect.top() - y
            elif y > rect.bottom():
                d = y - rect.bottom()
            if d < best_d:
                best, best_d = i, d
                if d == 0:
                    break
        return best

    def _selected_row_set(self):
        """当前可见且被选中的行号集合（不含“暂无已安装模组”）"""
        rows = set()
        for i in range(self.mod_list.count()):
            item = self.mod_list.item(i)
            if item is None or item.isHidden():
                continue
            if item.data(Qt.UserRole) in (None, "", "暂无已安装模组"):
                continue
            if item.isSelected():
                rows.add(i)
        return rows

    def _apply_selection_rows(self, rows):
        """整段替换当前选择为指定行集合"""
        if not rows:
            self.mod_list.clearSelection()
            return
        sm = self.mod_list.selectionModel()
        if sm is None:
            return
        model = sm.model()
        selection = QItemSelection()
        for r in rows:
            idx = model.index(r, 0)
            selection.select(idx, idx)
        sm.select(selection, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)

    def _range_visible_rows(self, lo, hi):
        """区间 [lo, hi] 内的所有可见行号"""
        result = []
        for r in range(lo, hi + 1):
            item = self.mod_list.item(r)
            if item is None or item.isHidden():
                continue
            result.append(r)
        return result

    def _row_and_offset(self, pos):
        """坐标 -> (行号, 该行内的 y 偏移)。
        偏移可能 <0（落在该行上方）或 >行高（落在该行下方/间隙/空白区），
        矩形框选靠它判断边界行是否真的被框到"""
        row = self._row_at(pos)
        if row < 0:
            row = self._nearest_row(pos)
            if row < 0:
                return -1, 0
        item = self.mod_list.item(row)
        if item is None:
            return -1, 0
        rect = self.mod_list.visualItemRect(item)
        return row, pos.y() - rect.top()

    def _band_rows(self):
        """按“矩形相交”计算被框住的行：
        起点/终点各落在某一行的某个偏移上，只有在矩形纵向范围内的行才选中，
        因此从空白处、行间隙起笔或收笔都能得到和原生框选一致的结果"""
        lst = self.mod_list
        a_row, a_off = self._sel_anchor_row, self._sel_anchor_off
        b_row, b_off = self._sel_end_row, self._sel_end_off
        if a_row < 0 or b_row < 0:
            return []
        if a_row < b_row or (a_row == b_row and a_off <= b_off):
            lo, lo_off, hi, hi_off = a_row, a_off, b_row, b_off
        else:
            lo, lo_off, hi, hi_off = b_row, b_off, a_row, a_off

        rows = []
        for r in range(lo, hi + 1):
            item = lst.item(r)
            if item is None or item.isHidden():
                continue
            rect = lst.visualItemRect(item)
            h = rect.height() or 58
            if lo == hi:
                # 同一行内的拖动：矩形与该行有重叠才选中
                if max(lo_off, hi_off) < 0 or min(lo_off, hi_off) > h:
                    continue
            else:
                if r == lo and lo_off > h:
                    continue          # 起点在该行下方（间隙/空白）
                if r == hi and hi_off < 0:
                    continue          # 终点在该行上方
            rows.append(r)
        return rows

    def _on_list_press(self, event):
        """左键按下：先落点确定本次点击语义（单击/Shift 区间/Ctrl 反选），
        并记录矩形起点（行 + 行内偏移），后续位移足够时进入自定义框选"""
        pos = event.position().toPoint()
        row, off = self._row_and_offset(pos)
        self._stop_autoscroll()
        self._sel_dragging = False
        self._sel_pending_blank = False
        self._sel_press_row = row
        self._sel_press_pos = pos
        self._sel_anchor_row = row      # 矩形起点（框选用）
        self._sel_anchor_off = off
        self._sel_end_row = row
        self._sel_end_off = off
        if row < 0:
            self._clear_selection()
            return
        if self._row_at(pos) < 0:
            # 落在行间隙/空白：先不改动选择，若之后拖动则以该位置为矩形起点；
            # 松手时若没有拖动，再按“点空白取消选中”处理
            self._sel_ctrl = False
            self._sel_shift = False
            self._sel_base = self._selected_row_set()
            self._sel_pending_blank = True
            return
        mods = event.modifiers()
        self._sel_ctrl = bool(mods & Qt.ControlModifier)
        self._sel_shift = bool(mods & Qt.ShiftModifier)
        self._sel_base = self._selected_row_set()
        with QSignalBlocker(self.mod_list):
            if self._sel_ctrl:
                new_rows = self._sel_base ^ {row}
            elif self._sel_shift:
                anchor = self._sel_click_anchor if self._sel_click_anchor >= 0 else row
                lo, hi = min(anchor, row), max(anchor, row)
                new_rows = set(self._range_visible_rows(lo, hi))
            else:
                # 无修饰键单击：
                # - 点未选中的行 -> 只选中它（标准列表行为，收敛选择）
                # - 点多选中的某一行 -> 同样收敛为只选中它。绝不能把该行从
                #   多选集合里摘掉：那是 Ctrl 点击的语义，否则选了 4 个再点
                #   其中一个会莫名少一个。
                # - 点「唯一」已选中的行 -> 取消选中（单击开关，省去按 Ctrl）
                if self._sel_base == {row}:
                    new_rows = set()
                else:
                    new_rows = {row}
            self._apply_selection_rows(sorted(new_rows))
        if not self._sel_shift:
            # 反选掉的行不能再当 Shift 区间锚点，否则下次 Shift 点击会错的连一片
            self._sel_click_anchor = row if row in new_rows else -1
        # 只同步 current（便于键盘上下导航），不要动选择集：
        # setCurrentRow() 会清空并只选中该行，会把刚算好的多选/加选结果打回单行
        sm = self.mod_list.selectionModel()
        if sm is not None:
            sm.setCurrentIndex(sm.model().index(row, 0), QItemSelectionModel.NoUpdate)
        # 先做轻量同步（不打开详情），松手或进入框选时再统一刷新详情
        self._on_selection_changed(update_detail=False)

    def _on_list_move(self, event):
        """按住左键移动：位移足够后进入自定义矩形框选"""
        pos = event.position().toPoint()
        row, off = self._row_and_offset(pos)
        if not self._sel_dragging:
            moved = (pos - self._sel_press_pos).manhattanLength()
            if row == self._sel_press_row and moved < QApplication.startDragDistance():
                return
            self._sel_dragging = True
        if row >= 0:
            self._sel_end_row = row
            self._sel_end_off = off
        self._update_drag_selection()
        vp = self.mod_list.viewport()
        h = vp.height()
        if pos.y() <= 18 or pos.y() >= h - 18:
            self._ensure_autoscroll()
        else:
            self._stop_autoscroll()

    def _update_drag_selection(self):
        """按当前矩形范围更新选择；
        无 Ctrl = 替换为矩形内可见行，Ctrl = 在“按下前已选”基线上叠加这些行"""
        rows = self._band_rows()
        if self._sel_ctrl:
            final = set(self._sel_base) | set(rows)
        else:
            final = set(rows)
        with QSignalBlocker(self.mod_list):
            self._apply_selection_rows(sorted(final))
        self._on_selection_changed(update_detail=False)

    def _on_list_release(self, event):
        """松手：若在框选，补一次最终区间计算，再统一刷新详情与按钮状态"""
        self._stop_autoscroll()
        if self._sel_dragging:
            row, off = self._row_and_offset(event.position().toPoint())
            if row >= 0:
                self._sel_end_row = row
                self._sel_end_off = off
                self._update_drag_selection()
        elif self._sel_pending_blank:
            # 只是点了一下空白/间隙：取消选中（保持原有交互）
            self._clear_selection()
        self._sel_press_row = -1
        self._sel_dragging = False
        self._sel_pending_blank = False
        self._on_selection_changed(update_detail=True)

    def _on_list_right_click(self, event):
        """右键单击：启用/禁用光标所在行的 Mod（原为双击，避免与“单击切换
        选中”打架）。只作用于右键那一行，不动当前选择集——多选时另有批量按钮。"""
        pos = event.position().toPoint()
        row = self._row_at(pos)
        self._stop_autoscroll()
        self._sel_press_row = -1
        self._sel_dragging = False
        if row < 0:
            return
        item = self.mod_list.item(row)
        if item is not None:
            self._on_item_toggle_enabled(item)

    def _ensure_autoscroll(self):
        if self._sel_autoscroll is None:
            timer = QTimer(self.mod_list)
            timer.setInterval(16)
            timer.timeout.connect(self._autoscroll_tick)
            timer.start()
            self._sel_autoscroll = timer

    def _autoscroll_tick(self):
        """拖到列表上/下边缘时自动滚动并持续扩展选择"""
        if self._sel_press_row < 0:
            self._stop_autoscroll()
            return
        vp = self.mod_list.viewport()
        pos = vp.mapFromGlobal(QCursor.pos())
        h = vp.height()
        sb = self.mod_list.verticalScrollBar()
        step = 22
        if pos.y() <= 18:
            new_val = max(sb.minimum(), sb.value() - step)
        elif pos.y() >= h - 18:
            new_val = min(sb.maximum(), sb.value() + step)
        else:
            self._stop_autoscroll()
            return
        if new_val == sb.value():
            self._stop_autoscroll()
            return
        sb.setValue(new_val)
        row, off = self._row_and_offset(pos)
        if row >= 0:
            self._sel_end_row = row
            self._sel_end_off = off
            self._update_drag_selection()

    def _stop_autoscroll(self):
        if self._sel_autoscroll is not None:
            try:
                self._sel_autoscroll.stop()
            except RuntimeError:
                pass
            self._sel_autoscroll = None

    # ---------- 原有业务逻辑 ----------
    def _on_item_toggle_enabled(self, item):
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
        """全选 / 取消全选。

        - 只作用于真实模组行：跳过「暂无已安装模组」占位行，否则占位行也会被打
          上选中态，但它在统计里不算数，按钮文字会和实际状态对不上。
        - 状态不靠按钮文字判断（筛选或程序改选后文字会失真），而是实时比对
          「已选真实行数 vs 可见真实行数」来决定这次是全选还是取消。
        """
        valid_rows = []
        for i in range(self.mod_list.count()):
            item = self.mod_list.item(i)
            if item is None or item.isHidden():
                continue
            if item.data(Qt.UserRole) in (None, "", "暂无已安装模组"):
                continue
            valid_rows.append(i)
        if not valid_rows:
            return

        all_selected = all(self.mod_list.item(i).isSelected() for i in valid_rows)
        # 屏蔽信号，避免逐行 setSelected 触发 N 次 itemSelectionChanged
        with QSignalBlocker(self.mod_list):
            for i in valid_rows:
                self.mod_list.item(i).setSelected(not all_selected)
        self._on_selection_changed()

    def _on_selection_changed(self, update_detail=True):
        """选择变化同步。拖拽过程中以 update_detail=False 高频轻量调用，
        避免每次移动都重读 ModLog / 详情；松手后 update_detail=True 一次性刷新详情"""
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

        if update_detail:
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
                self.detail_scroll.detail_panel._show_empty_state()

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
                self.detail_scroll.detail_panel._show_empty_state()

            self.refresh_mod_list(game_path)
        except Exception:
            pass

    def refresh_mod_list(self, game_path):
        self._ensure_ui()
        try:
            self._game_path = game_path or ""
            self._update_fs_watch()  # 同步监听的 Mods 目录（含 Disabled）
            selected_mod = self._current_mod
            saved_filter_index = self.filter_combo.currentIndex()
            saved_search_text = self.search_input.text()

            self.mod_list.clear()
            self._current_mod = None
            self._current_widget = None
            self._current_row = -1
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

            try:
                if os.path.exists(mods_dir):
                    for item in os.listdir(mods_dir):
                        if item == "Disabled":
                            continue
                        item_path = os.path.join(mods_dir, item)
                        if os.path.isdir(item_path):
                            try:
                                sub_items = os.listdir(item_path)
                            except OSError:
                                sub_items = []
                            if any(f.endswith('.dll') for f in sub_items):
                                found_mods.append((item, True))
                        elif os.path.isfile(item_path) and item.endswith('.dll'):
                            found_mods.append((os.path.splitext(item)[0], True))

                if os.path.exists(disabled_dir):
                    for item in os.listdir(disabled_dir):
                        item_path = os.path.join(disabled_dir, item)
                        if os.path.isdir(item_path):
                            try:
                                sub_items = os.listdir(item_path)
                            except OSError:
                                sub_items = []
                            if any(f.endswith('.dll') for f in sub_items):
                                found_mods.append((item, False))
                        elif os.path.isfile(item_path) and item.endswith('.dll'):
                            found_mods.append((os.path.splitext(item)[0], False))
            except OSError:
                # 目录被删除/无权限等异常，按"没有已安装模组"处理
                found_mods = []

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

            # 建立「归一化名 -> 在线 Mod」映射，用于判断本地 Mod 是否有更新
            online_by_norm = {}
            if resolver and hasattr(resolver, 'mod_data'):
                for info in resolver.mod_data:
                    nm = info.get('name', '')
                    if nm:
                        online_by_norm[normalize_name(nm)] = info

            from core.online_install import local_package_sha

            # 批量插入期间禁用重绘/重排，结束后一次性布局（大幅提速）
            self.mod_list.setUpdatesEnabled(False)
            for mod_name, enabled in found_mods:
                chinese_name = ""
                if resolver and hasattr(resolver, 'mod_data_by_name'):
                    chinese_name = resolver.mod_data_by_name.get(mod_name, {}).get('chinese_name', '')

                display_name = f"{mod_name}（{chinese_name}）" if chinese_name else mod_name

                # 是否有可用更新：本地安装包 sha 与在线发布 sha 不一致
                has_update = False
                online_info = online_by_norm.get(normalize_name(mod_name))
                if online_info:
                    online_sha = (online_info.get('sha256') or '').strip().upper()
                    if online_sha:
                        local_sha = local_package_sha(game_path, mod_name)
                        # 无 metadata（旧版装的）无法判定版本，不当作有更新，避免误报
                        has_update = bool(local_sha) and local_sha != online_sha

                item = QListWidgetItem()
                item.setData(Qt.UserRole, mod_name)
                item.setData(Qt.UserRole + 1, enabled)
                item.setData(Qt.UserRole + 2, has_update)

                widget = ModListItemWidget(
                    mod_name=mod_name,
                    display_name=display_name,
                    enabled=enabled,
                    has_update=has_update,
                    parent=self.mod_list,
                    list_item=item
                )
                item.setSizeHint(widget.sizeHint())
                self.mod_list.addItem(item)
                self.mod_list.setItemWidget(item, widget)
                # 本地 Mod 有更新：点「待更新」切到在线页选中该 Mod 去升级
                if has_update:
                    widget.action_btn.clicked.connect(
                        lambda checked=False, mn=mod_name: self._on_local_update_clicked(mn)
                    )

            self._update_count()
            self.search_input.setText(saved_search_text)
            with QSignalBlocker(self.filter_combo):
                self.filter_combo.setCurrentIndex(saved_filter_index)
            # 恢复 UI 更新，一次性完成重排
            self.mod_list.setUpdatesEnabled(True)

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

            self._rendered = True
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
                elif filter_index == 3 and not widget.has_update:
                    visible = False
                item.setHidden(not visible)

        visible_count = sum(1 for i in range(self.mod_list.count()) if not self.mod_list.item(i).isHidden())
        self.count_label.setText(f"共 {visible_count} 个模组")
        self._on_selection_changed()

    def _manual_refresh(self):
        if self.parent and hasattr(self.parent, 'game_path'):
            self.refresh_mod_list(self.parent.game_path)

    def _update_fs_watch(self):
        """根据当前 game_path 重新设置要监听的 Mods 目录。

        只监听 Mods 根目录，不监听 Disabled 子目录：启用/禁用 mod 是文件夹在
        Mods 与 Disabled 之间移动，Mods 根目录的变动已能覆盖（禁用=从 Mods 移走、
        启用=进入 Mods）；另外 Disabled 在某些环境 ACL 受限，QFileSystemWatcher
        对其取监视句柄会报「FindNextChangeNotification failed ... 拒绝访问」。
        Disabled 内的直接增删由兜底轮询覆盖，无需 watcher。
        """
        if self._fs_watcher is None:
            return
        watched = set(self._fs_watcher.directories())
        if not self._game_path:
            for p in watched:
                self._fs_watcher.removePath(p)
            return
        mods_dir = get_mods_dir(self._game_path)
        want = {mods_dir} if os.path.isdir(mods_dir) else set()
        # 只增删差异项，避免对同一个目录反复 remove/add 导致 watch 丢失
        for p in watched - want:
            self._fs_watcher.removePath(p)
        for p in want - watched:
            self._fs_watcher.addPath(p)

    def _compute_mods_signature(self, game_path):
        """计算 Mods 目录快照签名（文件夹名 + 修改时间），用于轮询比对。"""
        mods_dir = get_mods_dir(game_path)
        parts = []
        for base in (mods_dir, os.path.join(mods_dir, "Disabled")):
            try:
                names = sorted(e.name for e in os.scandir(base) if e.is_dir())
            except OSError:
                names = []
            for n in names:
                try:
                    m = int(os.path.getmtime(os.path.join(base, n)))
                except OSError:
                    m = 0
                parts.append(f"{n}:{m}")
        return tuple(parts)

    def _poll_mods_dir(self):
        """兜底轮询：每秒比对 Mods 目录快照，有变化就刷新列表。"""
        # 页面还没构建过 = 用户从没看过本地页，没必要为它干活（也就不会在启动后
        # 一秒偷偷把那 0.8s 的构建费付掉）
        if not self._ui_ready:
            return
        gp = self.parent.game_path if (self.parent
                                       and hasattr(self.parent, 'game_path')) else None
        if not gp:
            return
        try:
            sig = self._compute_mods_signature(gp)
        except Exception:
            return
        if sig != self._mods_sig:
            self._mods_sig = sig
            self.refresh_mod_list(gp)

    def _on_mods_dir_changed(self, path):
        # 目录变动（增删 mod / 启用禁用切换 / metadata 写入）触发防抖刷新
        timer = getattr(self, '_fs_watch_timer', None)
        if timer:
            timer.start()

    def _on_local_update_clicked(self, mod_name):
        """本地 Mod 有更新：点「待更新」切到在线页并选中该 Mod 去升级。"""
        mw = self.parent
        if not (mw and hasattr(mw, '_switch_tab')):
            return
        mw._switch_tab(2)  # 在线模组页
        page = mw.page_online

        def _select():
            try:
                if not getattr(page, '_rendered', False):
                    page.refresh_mod_list(mw.game_path or '')
                page.select_mod_by_name(mod_name)
            except Exception:
                pass

        # 等在线页渲染完成（_switch_tab 内用 QTimer(50) 触发渲染）后再选中
        QTimer.singleShot(200, _select)

    def _clear_selection(self):
        if self.mod_list.selectedItems():
            self.mod_list.clearSelection()
        # Shift 锚点是行号：筛选/搜索会重排行号，不重置的话下次 Shift 点击
        # 会拿旧行号当起点，框出一段完全不相干的区间
        self._sel_click_anchor = -1
        if self._current_widget:
            self._current_widget.set_selected(False)
            self._current_widget = None
        self._current_mod = None
        self.detail_scroll.detail_panel._show_empty_state()

    def _on_search_text_changed(self, text):
        self._clear_selection()
        self._filter_mods()

    def _on_filter_changed(self, index):
        self._clear_selection()
        self._filter_mods()

    def _select_and_show_item(self, item):
        if not item:
            return
        self.mod_list.clearSelection()
        item.setSelected(True)
        self.mod_list.setCurrentItem(item)
        self._on_item_clicked(item)

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

            # 本地已装模组的版本来自 .metadata.json（不再依赖 ModLog）
            version_from_modlog = ""
            game_path = getattr(self.parent, 'game_path', '') if self.parent else ''
            if game_path:
                from core.installer import get_mod_version_from_metadata
                version_from_modlog = get_mod_version_from_metadata(game_path, mod_name) or ""

            mod_info = None
            resolver = getattr(self.parent, 'resolver', None) if self.parent else None
            if resolver and hasattr(resolver, 'mod_data_by_name'):
                mod_info = resolver.mod_data_by_name.get(mod_name)

            _panel = self.detail_scroll.detail_panel
            _panel._dep_checker = lambda n: self._is_mod_installed(n)
            _mdb = getattr(resolver, 'mod_data_by_name', None) or {}
            _panel._link_provider = lambda n: _first_link(_mdb.get(n) or {})
            _panel.set_local_mod_info(
                mod_name=mod_name,
                enabled=enabled,
                version=version_from_modlog,
                mod_info=mod_info,
                game_path=game_path,
            )

        except RuntimeError:
            pass

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
        self._rendered = False  # 首次渲染标记：切换标签页时避免重复重建列表
        self._game_path = ""
        self._batch_seq = 0         # 下载批次自增 id（多任务并行，每批一个 Worker）
        self._workers = []          # 持有 QThread 引用，防止被 GC
        self._batch_results = {}    # batch_id -> (目标Mod名, 是否成功, 结果摘要)，全部结束后汇总提示
        self._active_batch_targets = set()  # 正在下载/安装中的目标 Mod 名（防重复开批）
        # 行 widget 懒构建：只给“可见 + 少量缓冲”的行创建 widget，
        # 其余行先以轻量 item 占位，随滚动/筛选动态补齐（显著降低启动/整体卡顿）
        self._row_transient = {}    # mod_name -> ('downloading', pct) / ('installing',) / ('done', status)
        self._prog = {}             # (batch_id, name) -> 该任务整体进度 0..1
        self._prog_active = set()   # 仍在进行（未完成）的任务键集合
        self._setup_ui()
        self._refresh_quark_status()

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

        nav_layout.addWidget(title)
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
        self.search_input.textChanged.connect(self._on_search_text_changed)
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
        self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_combo)

        # 夸克账号状态显示（登录/切换入口在顶部「设置」页）
        self.quark_chip = QLabel("夸克：未配置")
        self.quark_chip.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        self.quark_chip.setToolTip("夸克网盘账号状态。登录 / 切换 / 退出请在顶部「设置」页操作。")
        self.quark_chip.setStyleSheet("color: #ff6b6b; background: transparent; padding-left: 12px;")
        filter_layout.addWidget(self.quark_chip)
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
        self.mod_list.viewport().installEventFilter(self)
        # 滚动时按需为进入视野的行创建自绘 widget（懒构建，避免整表一次性建 600+ widget）
        self.mod_list.verticalScrollBar().valueChanged.connect(self._on_list_scrolled)
        left_layout.addWidget(self.mod_list, stretch=3)

        # ---- 下方：整体进度（汇总所有并行下载 + 安装的总进度，替代原日志区） ----
        self._prog_card = QFrame()
        self._prog_card.setStyleSheet("QFrame{background:#191919;border:none;border-radius:10px;}")
        prog_layout = QVBoxLayout(self._prog_card)
        prog_layout.setContentsMargins(14, 12, 14, 12)
        prog_layout.setSpacing(8)
        self._prog_label = QLabel("整体进度 0%")
        self._prog_label.setStyleSheet("color:#d5d5d5;font-size:12px;font-weight:600;")
        prog_layout.addWidget(self._prog_label)
        self._prog_bar = QProgressBar()
        self._prog_bar.setRange(0, 100)
        self._prog_bar.setValue(0)
        self._prog_bar.setTextVisible(True)
        self._prog_bar.setFormat("%p%")
        self._prog_bar.setStyleSheet(
            "QProgressBar{background:#2a2a2a;border:none;border-radius:7px;"
            "height:14px;text-align:center;color:#ffffff;font-size:11px;font-weight:700;}"
            "QProgressBar::chunk{background:#34c759;border-radius:7px;}")
        prog_layout.addWidget(self._prog_bar)
        self._prog_card.setVisible(False)   # 空闲（无进行中任务）时隐藏
        left_layout.addWidget(self._prog_card, stretch=0)

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

        # ---- 右下角悬浮提示（夸克登录 / 下载安装结果） ----
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

    # ---------- 右下角悬浮提示相关 ----------
    def eventFilter(self, obj, event):
        if hasattr(self, 'detail_scroll') and obj == self.detail_scroll.parent() and event.type() == event.Type.Resize:
            self._reposition_copy_tip()
            return True
        if obj == self.mod_list.viewport() and event.type() == QEvent.MouseButtonPress:
            item = self.mod_list.itemAt(event.pos())
            if item is None:
                self._clear_selection()
                return True
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
            self._game_path = game_path or ""
            if not self.isVisible():
                # 页面不可见（后台数据刷新 / 下载批量完成时用户正停在其它页）：
                # 跳过昂贵的整表构建，仅标记“未渲染”，切回本页时再真正渲染，
                # 避免在用户操作其它页面时被卡顿
                self._rendered = False
                return
            selected_mod = self._current_mod
            saved_filter_index = self.filter_combo.currentIndex()
            saved_search_text = self.search_input.text()

            self.mod_list.clear()
            self._row_transient.clear()
            self._current_mod = None
            self._current_widget = None
            self._current_row = -1
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

            from core.online_install import installed_mod_set, local_package_sha
            installed = installed_mod_set(self._game_path) if self._game_path else set()
            found_mods = []

            for mod_info in mod_data:
                mod_name = mod_info.get('name', '')
                if not mod_name:
                    continue

                chinese_name = mod_info.get('chinese_name', '')
                online_sha = (mod_info.get('sha256') or '').strip().upper()
                normalized_online = normalize_name(mod_name)

                # 「已安装」只看游戏 Mods / Disabled 目录里是否真实存在该 Mod。
                # 「待更新」仅按线上包 sha 与本地安装记录比对；无 sha 时不参考 ModLog，
                # 直接视为已是最新（保持“已安装”）。
                in_folder = normalized_online in installed
                is_installed = in_folder
                has_update = False

                if is_installed and online_sha:
                    # 有远程 sha：本地安装包校验值与线上不一致 => 待更新
                    has_update = local_package_sha(self._game_path, mod_name) != online_sha

                found_mods.append((mod_name, chinese_name, is_installed, has_update))

            self._refresh_quark_status()

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

            # 第一遍只插入“轻量 item 外壳”（不含自绘 widget，非常快）。
            # 行 widget 交给 _ensure_visible_row_widgets 按需懒构建，
            # 避免一次性创建 600+ 个 widget（约 1.9s 的主线程卡顿）。
            self.mod_list.setUpdatesEnabled(False)
            for mod_name, chinese_name, is_installed, has_update in found_mods:
                display_name = f"{mod_name}（{chinese_name}）" if chinese_name else mod_name

                item = QListWidgetItem()
                item.setData(Qt.UserRole, mod_name)
                item.setData(Qt.UserRole + 1, is_installed)
                item.setData(Qt.UserRole + 2, has_update)
                item.setData(Qt.UserRole + 3, chinese_name or "")
                item.setData(Qt.UserRole + 4, display_name)
                item.setSizeHint(QSize(0, 58))
                self.mod_list.addItem(item)

            self._update_count()
            self.search_input.setText(saved_search_text)
            with QSignalBlocker(self.filter_combo):
                self.filter_combo.setCurrentIndex(saved_filter_index)
            # 恢复 UI 更新，一次性完成重排
            self.mod_list.setUpdatesEnabled(True)
            self.mod_list.viewport().update()

            if selected_mod:
                for i in range(self.mod_list.count()):
                    if self.mod_list.item(i).data(Qt.UserRole) == selected_mod:
                        self.mod_list.setCurrentRow(i)
                        self._on_item_clicked(self.mod_list.item(i), allow_toggle=False)
                        break

            self._filter_mods()

            if not selected_mod or self.mod_list.currentRow() < 0:
                self.detail_scroll.detail_panel.title_en.setText(f"共 {len(found_mods)} 个在线模组")
                self.detail_scroll.detail_panel.title_en.setStyleSheet(
                    "color: #888888; background: transparent; border: none;")
                self.detail_scroll.detail_panel.status_label.setText("👈 点击左侧列表查看详情")
                self.detail_scroll.detail_panel.status_label.setStyleSheet(
                    "color: #666666; background: transparent; border: none;")

            # 页面可见：只给当前视野内的行建 widget，其余延后。
            # 布局尚未完成时 visualItemRect 可能无效，故延迟一帧再补一次
            self._ensure_visible_row_widgets()
            QTimer.singleShot(0, self._ensure_visible_row_widgets)

            self._rendered = True
        except Exception:
            pass

    def _update_count(self):
        self.count_label.setText(f"共 {self.mod_list.count()} 个模组")

    def _filter_mods(self):
        # 筛选基于 item 数据角色完成，不依赖行 widget 是否已懒构建
        search_text = self.search_input.text().lower()
        filter_index = self.filter_combo.currentIndex()

        for i in range(self.mod_list.count()):
            item = self.mod_list.item(i)
            mod_name = item.data(Qt.UserRole) or ""
            if not mod_name or mod_name.startswith(("暂无", "⏳")):
                item.setHidden(False)
                continue
            chinese_name = item.data(Qt.UserRole + 3) or ""
            is_installed = bool(item.data(Qt.UserRole + 1))
            has_update = bool(item.data(Qt.UserRole + 2))

            visible = True
            if search_text and search_text not in mod_name.lower() and search_text not in chinese_name.lower():
                visible = False
            if filter_index == 1 and not is_installed:
                visible = False
            elif filter_index == 2 and not has_update:
                visible = False
            elif filter_index == 3 and is_installed:
                visible = False
            item.setHidden(not visible)

        visible_count = sum(1 for i in range(self.mod_list.count()) if not self.mod_list.item(i).isHidden())
        self.count_label.setText(f"共 {visible_count} 个模组")
        # 筛选变化可能让尚未建 widget 的行进入视野：补建当前可见范围
        self._ensure_visible_row_widgets()
        QTimer.singleShot(0, self._ensure_visible_row_widgets)

    # ---------- 在线行 widget 懒构建（按可见区域动态补齐） ----------
    def _create_online_row_widget(self, item, row):
        """为单个 item 创建自绘行 widget（仅当 item 尚未有 widget 时）"""
        try:
            if self.mod_list.itemWidget(item) is not None:
                return
            mod_name = item.data(Qt.UserRole) or ""
            if not mod_name or mod_name.startswith(("暂无", "⏳")):
                return
            widget = OnlineModListItemWidget(
                mod_name=mod_name,
                display_name=item.data(Qt.UserRole + 4) or mod_name,
                is_installed=bool(item.data(Qt.UserRole + 1)),
                has_update=bool(item.data(Qt.UserRole + 2)),
                parent=self.mod_list,
                list_item=item,
            )
            self.mod_list.setItemWidget(item, widget)
            widget.action_btn.clicked.connect(
                lambda checked=False, mn=mod_name, w=widget: self._on_action_clicked(mn, w)
            )
            state = self._row_transient.get(mod_name)
            if state:
                if state[0] == "downloading":
                    widget.set_downloading(state[1])
                elif state[0] == "installing":
                    widget.set_installing()
                elif state[0] == "done":
                    widget.set_done(state[1])
            # 若该行就是当前详情行，懒构建完成后补绑高亮，避免状态丢失
            if self._current_mod == mod_name:
                if self._current_widget is not widget:
                    self._current_widget = widget
                    widget.set_selected(True)
            elif item.isSelected():
                widget.set_selected(True)
        except RuntimeError:
            pass

    def _on_list_scrolled(self, value):
        # 滚动时值可能高频变化，构建本身廉价且有 widget 去重；直接同步补齐可见行即可
        self._ensure_visible_row_widgets()

    def _ensure_visible_row_widgets(self):
        """只对“当前可见(+上下缓冲)”且尚无 widget 的行执行懒构建；
        一次性创建几十个 widget（毫秒级），避免整表 600+ 全量创建卡顿"""
        if getattr(self, "_ensuring_visible", False):
            return
        lst = self.mod_list
        if lst.count() == 0 or not self.isVisible():
            return
        self._ensuring_visible = True
        try:
            # 先定位“首/末可见行”，只在附近补建，避免每次滚动都全表扫描
            vp = lst.viewport()
            h = vp.height()
            first = lst.itemAt(QPoint(2, 2))
            last = lst.itemAt(QPoint(2, max(0, h - 2)))
            if first is None and last is None:
                return
            start = lst.row(first) if first is not None else 0
            end = lst.row(last) if last is not None else lst.count() - 1
            if start < 0:
                start = 0
            if end < 0:
                end = lst.count() - 1
            start = max(0, start - 2)          # 上下各多建 2 行做缓冲
            end = min(lst.count() - 1, end + 2)

            top = -80
            bottom = h + 80
            built = 0
            for i in range(start, end + 1):
                item = lst.item(i)
                if item is None or item.isHidden():
                    continue
                if lst.itemWidget(item) is not None:
                    continue
                rect = lst.visualItemRect(item)
                if rect.isEmpty():
                    continue
                if rect.bottom() < top or rect.top() > bottom:
                    continue
                self._create_online_row_widget(item, i)
                built += 1
                if built >= 60:
                    break
        finally:
            self._ensuring_visible = False

    def _clear_selection(self):
        if self.mod_list.selectedItems():
            self.mod_list.clearSelection()
        if self._current_widget:
            self._current_widget.set_selected(False)
            self._current_widget = None
        self._current_mod = None
        self.detail_scroll.detail_panel._show_empty_state()

    def _on_search_text_changed(self, text):
        self._clear_selection()
        self._filter_mods()

    def _on_filter_changed(self, index):
        self._clear_selection()
        self._filter_mods()

    def _select_and_show_item(self, item):
        if not item:
            return
        self.mod_list.clearSelection()
        item.setSelected(True)
        self.mod_list.setCurrentItem(item)
        self._on_item_clicked(item, allow_toggle=False)

    def _manual_refresh(self):
        if self.parent and hasattr(self.parent, 'game_path'):
            self.refresh_mod_list(self.parent.game_path)

    def _on_item_clicked(self, item, allow_toggle=True):
        mod_name = item.data(Qt.UserRole)
        if not mod_name or mod_name == "暂无在线模组":
            return

        current_widget = self.mod_list.itemWidget(item)
        # 行 widget 可能是懒构建的（点击的那一瞬间可能尚未建出来），
        # 因此以“同一行 + 同一 widget”为重复点击判断。
        # 用户再次点击已选中的 Mod = 取消选中；但程序内部选中（刷新后恢复、
        # 按名跳转等）不能触发反选，否则会把自己刚选中的项又清掉，故用
        # allow_toggle 区分。
        if current_widget is self._current_widget and current_widget is not None and self._current_mod == mod_name:
            if allow_toggle:
                self._clear_selection()
            return

        if self._current_widget and self._current_widget is not current_widget:
            self._current_widget.set_selected(False)

        if current_widget:
            current_widget.set_selected(True)
            self._current_widget = current_widget

        self._current_mod = mod_name
        self._show_mod_detail(mod_name)

    def select_mod_by_name(self, mod_name):
        """按（归一化）名称在在线列表中选中并展开某 Mod 的详情，找不到返回 False。"""
        target = normalize_name(mod_name)
        for i in range(self.mod_list.count()):
            item = self.mod_list.item(i)
            mn = item.data(Qt.UserRole)
            if mn and normalize_name(mn) == target:
                self.mod_list.setCurrentRow(i)
                self._on_item_clicked(item, allow_toggle=False)
                return True
        return False

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
            resolver = getattr(self.parent, 'resolver', None) if self.parent else None
            if resolver and hasattr(resolver, 'mod_data_by_name'):
                mod_info = resolver.mod_data_by_name.get(mod_name)

            # 在线页读取本地已安装版本（用于显示 v旧→v新 格式）。
            # 来源改为 .metadata.json 的 version 字段，不再依赖 ModLog。
            local_version = ""
            game_path = getattr(self.parent, 'game_path', '') if self.parent else ''
            if is_installed and game_path:
                from core.installer import get_mod_version_from_metadata
                local_version = get_mod_version_from_metadata(game_path, mod_name) or ""

            _panel = self.detail_scroll.detail_panel
            _panel._dep_checker = lambda n: self._is_mod_installed(n)
            _mdb = getattr(resolver, 'mod_data_by_name', None) or {}
            _panel._link_provider = lambda n: _first_link(_mdb.get(n) or {})
            _panel.set_online_mod_info(
                mod_name=mod_name,
                is_installed=is_installed,
                has_update=has_update,
                mod_info=mod_info,
                local_version=local_version,
                game_path=game_path,
            )

        except RuntimeError:
            pass

    def _on_action_clicked(self, mod_name, widget):
        # 未安装 / 待更新的行按钮 = 一键下载安装入口；已是最新时按钮禁用不会走到这里
        if widget.is_installed and not widget.has_update:
            return
        if not self.parent or not hasattr(self.parent, 'resolver'):
            return
        for i in range(self.mod_list.count()):
            item = self.mod_list.item(i)
            if item.data(Qt.UserRole) == mod_name:
                self._select_and_show_item(item)
                break
        # 待更新 -> 强制重装（忽略"已安装"状态），并安装前清掉 downloads 里的旧包
        self._start_download(mod_name, force=bool(getattr(widget, "has_update", False)))

    # ---------- M2 在线一键下载安装 ----------
    def _refresh_quark_status(self):
        """按 config.json 是否有 Cookie 刷新筛选栏状态色（不做网络请求）"""
        try:
            from utils.common import load_quark_cookie
            has = bool(load_quark_cookie())
            self.quark_chip.setText("夸克：已配置" if has else "夸克：未配置")
            self.quark_chip.setStyleSheet(
                ("color: #66bb6a; background: transparent; padding-left: 12px;")
                if has else
                ("color: #ff6b6b; background: transparent; padding-left: 12px;")
            )
        except Exception:
            pass

    def _open_quark_setting(self):
        """打开夸克内嵌登录窗口（扫码 / 账密 / 手机号）；保存成功后同步状态"""
        try:
            from ui.quark_login_dialog import show_quark_login_dialog
        except ImportError:
            from quark_login_dialog import show_quark_login_dialog
        saved = show_quark_login_dialog(self)
        if saved:
            self._refresh_quark_status()
            self._show_copy_tip("夸克账号已保存")
            if self.parent and hasattr(self.parent, '_log'):
                self.parent._log("夸克账号已配置并保存", "success")
        return saved

    def _start_download(self, mod_name, force=False):
        """一键下载并安装：算依赖计划时自动检测 downloads 是否已有安装包备份，
        有则直接走本地安装（不再从夸克下载），缺的才在线补齐；全程无确认弹窗。

        :param force: True 表示这是「待更新」触发的更新安装：即使已装也重新下载，
                      并先清掉 downloads 里属于该 Mod 的旧安装包（只留最新一份）。
        """
        if not mod_name:
            return
        # 多任务并行：每批一个独立后台线程。批内 zip 由 core.online_install 并发下载
        # （本体 + 缺失前置同时下，同名共享依赖全局只下一次）。下载过的安装包 zip 会
        # 留在 downloads 里，卸载/重装时直接命中本地缓存安装，不再重新从夸克下载。

        parent = self.parent
        game_path = getattr(parent, 'game_path', '') if parent else ''
        if not game_path:
            QMessageBox.warning(self, "尚未选择游戏", "请先在「首页」指定空洞骑士游戏根目录（含 hollow_knight.exe）后再下载安装。")
            return

        resolver = getattr(parent, 'resolver', None) if parent else None
        if not resolver or not hasattr(resolver, 'mod_data_by_name') or mod_name not in resolver.mod_data_by_name:
            QMessageBox.warning(self, "无法下载", f"未找到模组「{mod_name}」的下载信息，请确认在线列表已加载完成。")
            return

        from utils.common import load_quark_cookie
        from core.online_install import (collect_install_plan, local_ready_result,
                                         purge_local_packages)
        plan = collect_install_plan(game_path, mod_name, resolver, force=force)
        tasks = plan.get('tasks') or []
        if not tasks:
            self._show_copy_tip("该 Mod 及其依赖均已是本地最新，无需操作")
            return

        # 同一个 Mod 正在下载/安装时不再开新批：否则弹窗会出现「xxx ·2」重复行，
        # 且两批并行装同一个 Mod 也没有意义
        if mod_name in getattr(self, "_active_batch_targets", set()):
            self._show_copy_tip(f"「{mod_name}」正在下载/安装中，请等待当前批次完成")
            return

        # 更新安装：先清掉 downloads 里该 Mod 的旧包（必须在缓存预判之前，
        # 否则会把旧包当成"本地缓存命中"又装回去）
        if force:
            purged = purge_local_packages(mod_name)
            if purged and parent and hasattr(parent, '_log'):
                parent._log(f"🧹 已清理旧安装包：{'、'.join(purged)}", "info")

        # 本地就绪预判（一次算好，下面复用）：
        #   None                 -> 需要联网下载
        #   {"skip": 目录}        -> 已安装同版本，会静默跳过
        #   {"zip": 路径}         -> 本地缓存直接安装
        ready_map = {t.get('name', ''): local_ready_result(game_path, t) for t in tasks}

        # 本批是否真的需要联网下载：只有存在 downloads 里也没有的安装包时，
        # 才需要夸克账号；全部命中本地缓存则完全离线、直接安装。
        need_net = any(v is None for v in ready_map.values())

        # 弹窗只显示"真正要做事"的任务：已安装同版本（会静默 skip）的不占一行，
        # 重复名兜底去重；过滤掉的任务仍会传给 Worker，由安装阶段正常跳过
        names = []
        _seen_names = set()
        for t in tasks:
            n = t.get('name', '')
            if not n or n in _seen_names:
                continue
            _seen_names.add(n)
            res = ready_map.get(n)
            # 强制更新时目标 Mod 一定显示（即使预判为 skip 也要走一遍重新安装）
            if res and "skip" in res and not (force and n == mod_name):
                continue
            names.append(n)
        if not names:
            self._show_copy_tip("该 Mod 及其依赖均已是本地最新，无需操作")
            return
        # 真正需要留意的异常（依赖不在在线列表 / 未配置下载链接）以非阻塞方式
        # 写入日志窗口，不打断下载。
        if plan.get('offline_deps'):
            if parent and hasattr(parent, '_log'):
                parent._log("⚠️ 以下依赖不在在线列表，请自行处理：" + "、".join(plan['offline_deps']), "warn")
        if plan.get('no_link'):
            if parent and hasattr(parent, '_log'):
                parent._log("⚠️ 以下条目未配置下载链接，需手动下载：" + "、".join(plan['no_link']), "warn")

        if not need_net:
            tip = "downloads 已有所需安装包，直接本地安装，无需从夸克下载"
            self._show_copy_tip(tip)
            if parent and hasattr(parent, '_log'):
                parent._log("✔ " + tip, "success")
        elif not load_quark_cookie():
            # 真有要下的包才设夸克登录门槛；纯本地安装不拦。
            ret = QMessageBox.question(
                self, "需要夸克账号",
                "下载 Mod 需要登录夸克网盘。是否现在打开夸克登录窗口（扫码即可）？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes or not self._open_quark_setting():
                return

        # 目标行切到「下载中 / 安装中」态（写入 transient，
        # 保证懒构建尚未出现的行在补建 widget 时也能带上正确状态）
        self._row_transient[mod_name] = ('downloading', None) if need_net else ('installing',)
        for i in range(self.mod_list.count()):
            item = self.mod_list.item(i)
            if item.data(Qt.UserRole) == mod_name:
                w = self.mod_list.itemWidget(item)
                if w:
                    if need_net:
                        w.set_downloading(None)
                    else:
                        w.set_installing()
                break

        # 弹出悬浮进度面板：登记本批计划（目标 + 缺失依赖）。
        # 可并行：重复点击会新增一批，各批独立线程同时下载，互不阻塞。
        from utils.common import load_parallel_downloads
        parallel = load_parallel_downloads()
        self._batch_seq += 1
        batch_id = f"dl{self._batch_seq}"
        self._batch_results[batch_id] = (mod_name, True, "")
        self._active_batch_targets.add(mod_name)
        # 登记本批所有任务，整体进度条据此聚合并行下载 + 安装的总进度
        for _n in {t.get("name", "") for t in tasks if t.get("name")}:
            _k = (batch_id, _n)
            self._prog[_k] = 0.0
            self._prog_active.add(_k)
        self._update_overall_progress()
        worker = OnlineDownloadWorker(game_path, batch_id, mod_name, tasks,
                                      parallel=max(1, min(16, parallel)), parent=self)
        worker.log.connect(self._on_worker_log)
        worker.progress.connect(self._on_download_progress)
        worker.task_started.connect(self._on_task_started)
        worker.installing.connect(self._on_installing)
        worker.task_done.connect(self._on_task_done)
        worker.stage.connect(self._on_worker_stage)
        worker.finished.connect(self._on_download_finished)
        self._workers.append(worker)
        worker.start()

    # ---------- 整体进度聚合（替代原日志区） ----------
    def _update_overall_progress(self):
        """汇总所有并行下载 + 安装任务的整体进度，刷新底部进度条。
        每个任务权重相同：下载占 0~0.9，安装占 0.95，完成记 1.0。"""
        if not self._prog_active:
            self._prog_card.setVisible(False)
            self._prog_bar.setValue(100)
            self._prog_label.setText("整体进度 100%")
            return
        self._prog_card.setVisible(True)
        total = sum(self._prog.get(k, 0.0) for k in self._prog_active)
        pct = int(total / len(self._prog_active) * 100)
        self._prog_bar.setValue(pct)
        self._prog_label.setText(f"整体进度 {pct}%  ·  进行中 {len(self._prog_active)} 项")

    def _on_worker_log(self, message, level):
        # 日志区已移除：仅把警告/错误转给主窗口全局日志，确保失败可见
        lvl = (level or "").lower()
        if lvl in ("warn", "warning", "error", "fail") \
                and self.parent and hasattr(self.parent, '_log'):
            self.parent._log(message, level)

    def _on_task_started(self, batch_id, name):
        key = (batch_id, name)
        self._prog.setdefault(key, 0.0)
        self._prog_active.add(key)
        self._update_overall_progress()

    def _on_worker_stage(self, message):
        # 阶段细节不再展示（日志区已移除，整体进度条足够反映进度）
        pass

    def _on_download_progress(self, batch_id, name, pct):
        if not name:
            return
        key = (batch_id, name)
        if key in self._prog_active:
            # 下载占整体任务的 0~0.9，安装另占 0.95，完成记 1.0
            self._prog[key] = max(self._prog.get(key, 0.0), (pct / 100.0) * 0.9)
            self._update_overall_progress()
        self._row_transient[name] = ('downloading', pct)
        for i in range(self.mod_list.count()):
            item = self.mod_list.item(i)
            if item.data(Qt.UserRole) == name:
                w = self.mod_list.itemWidget(item)
                if w:
                    w.set_downloading(pct)
                break

    def _on_task_done(self, batch_id, name, status):
        key = (batch_id, name)
        self._prog[key] = 1.0
        self._prog_active.discard(key)
        self._update_overall_progress()
        self._row_transient[name] = ('done', status)
        for i in range(self.mod_list.count()):
            item = self.mod_list.item(i)
            if item.data(Qt.UserRole) == name:
                w = self.mod_list.itemWidget(item)
                if w:
                    w.set_done(status)
                break

    def _on_installing(self, batch_id, task):
        key = (batch_id, task)
        self._prog[key] = 0.95
        self._prog_active.add(key)
        self._update_overall_progress()
        self._row_transient[task] = ('installing',)
        for i in range(self.mod_list.count()):
            item = self.mod_list.item(i)
            if item.data(Qt.UserRole) == task:
                w = self.mod_list.itemWidget(item)
                if w:
                    w.set_installing()
                break

    def _on_download_finished(self, batch_id, ok, mod_name, message):
        self._workers = [w for w in self._workers if w is not self.sender()]
        self._active_batch_targets.discard(mod_name)
        self._batch_results[batch_id] = (mod_name, ok, message)
        # 本批结束：清理其进度登记，让整体进度条回落到其余在跑批次 / 无任务时隐藏
        for _k in [k for k in self._prog if k[0] == batch_id]:
            self._prog.pop(_k, None)
        self._prog_active = {k for k in self._prog_active if k[0] != batch_id}
        self._update_overall_progress()
        if self._workers:
            return
        try:
            if self.parent and hasattr(self.parent, 'game_path'):
                self.refresh_mod_list(self.parent.game_path or '')
        except RuntimeError:
            pass
        results = list(self._batch_results.values())
        self._batch_results.clear()
        if all(ok for _label, ok, _msg in results):
            self._show_copy_tip("安装完成")
            QMessageBox.information(self, "下载安装完成", "全部 Mod 安装完成")
        else:
            fails = [f"· {label}：{msg}" for label, ok, msg in results if not ok]
            QMessageBox.critical(self, "下载安装失败", "存在失败项：\n" + "\n".join(fails))

    def _is_mod_installed(self, mod_name):
        """在线详情页「前置依赖」判定：以游戏 Mods/Disabled 目录真实文件为准（与列表页一致，不依赖 ModLog）"""
        try:
            if not self._game_path:
                return False
            from core.online_install import installed_mod_set
            return normalize_name(mod_name) in installed_mod_set(self._game_path)
        except Exception:
            return False