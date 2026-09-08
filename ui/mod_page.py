# -*- coding: utf-8 -*-
"""模组管理页面"""
import os
import re
import time
import webbrowser
from typing import Callable, Optional
from PySide6.QtCore import (
    Qt,
    QTimer,
    QSignalBlocker,
    QSize,
    QEvent,
    QThread,
    Signal,
    QItemSelection,
    QItemSelectionModel,
    QPoint,
    QPointF,
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
    QTextEdit,
    QScrollArea,
    QMessageBox,
    QSizePolicy,
    QLineEdit,
    QComboBox,
    QFrame,
    QSpacerItem,
    QCheckBox,
    QToolButton,
    QProgressBar,
)
from PySide6.QtGui import QFont, QColor, QPalette, QIcon, QPixmap, QPainter, QPaintEvent, QMouseEvent, QCursor, QTextCursor
from utils import get_mods_dir
from core import disable_mod, enable_mod, delete_mod, is_mod_enabled


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
        # 状态未变直接返回：拖拽/高频刷新会逐行调用，
        # 无条件重设 QSS 会触发整表样式重算，是明显的卡顿来源
        if getattr(self, "is_selected", None) == selected:
            return
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
        self._rendered = False  # 首次渲染标记：切换标签页时避免重复重建列表
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
        self.mod_list.itemDoubleClicked.connect(self._on_item_double_clicked)
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
            if t == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
                self._on_list_double_click(event)
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
                new_rows = {row}
            self._apply_selection_rows(sorted(new_rows))
        if not self._sel_shift:
            self._sel_click_anchor = row
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

    def _on_list_double_click(self, event):
        """双击：保持原有“双击启用/禁用”交互"""
        pos = event.position().toPoint()
        row = self._row_at(pos)
        self._stop_autoscroll()
        self._sel_press_row = -1
        self._sel_dragging = False
        if row < 0:
            return
        item = self.mod_list.item(row)
        if item is not None:
            self._on_item_double_clicked(item)

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
        try:
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

            # 批量插入期间禁用重绘/重排，结束后一次性布局（大幅提速）
            self.mod_list.setUpdatesEnabled(False)
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
                item.setHidden(not visible)

        visible_count = sum(1 for i in range(self.mod_list.count()) if not self.mod_list.item(i).isHidden())
        self.count_label.setText(f"共 {visible_count} 个模组")
        self._on_selection_changed()

    def _manual_refresh(self):
        if self.parent and hasattr(self.parent, 'game_path'):
            self.refresh_mod_list(self.parent.game_path)

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
        self._on_item_clicked(item)

    def _manual_refresh(self):
        if self.parent and hasattr(self.parent, 'game_path'):
            self.refresh_mod_list(self.parent.game_path)

    def _on_item_clicked(self, item):
        mod_name = item.data(Qt.UserRole)
        if not mod_name or mod_name == "暂无在线模组":
            return

        current_widget = self.mod_list.itemWidget(item)
        # 行 widget 可能是懒构建的（点击的那一瞬间可能尚未建出来），
        # 因此以“同一行 + 同一 widget”为重复点击判断，避免漏刷详情
        if current_widget is self._current_widget and current_widget is not None and self._current_mod == mod_name:
            return

        if self._current_widget and self._current_widget is not current_widget:
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
            return

        from utils.common import load_app_setting, load_quark_cookie
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
        parallel = int(load_app_setting("parallel_downloads", 8) or 8)
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