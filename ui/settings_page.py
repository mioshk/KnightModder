# -*- coding: utf-8 -*-
"""
设置页（主窗口顶部导航第 4 个页面）

集中管理在线下载所需的配置：
  1. 夸克网盘账号：登录（软件内嵌官方登录页，扫码 / 手机号 / 账密）、
     在线验证状态、退出登录；
  2. 下载缓存目录：显示 / 打开本地 downloads 目录；
  3. 关于与版本信息。

所有下载所需的夸克登录入口统一收口到这里（在线模组页不再放登录按钮）。
"""
import json
import os

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QFont, QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from utils.common import (
    get_base_dir,
    get_download_dir,
    load_app_setting,
    load_quark_cookie,
    save_app_setting,
    save_quark_cookie,
)

_COLOR_BG = "#1b1b1f"
_COLOR_TEXT = "#ffffff"
_COLOR_SUB = "#bbbbbb"
_COLOR_DIM = "#888888"
_COLOR_GREEN = "#34c759"
_COLOR_GREEN_BG = "rgba(52, 199, 89, 0.12)"
_COLOR_RED = "#ff6b6b"
_COLOR_RED_BG = "rgba(255, 107, 107, 0.12)"
_COLOR_ORANGE = "#ff9500"
_COLOR_CARD_BG = "#222227"


class _QuarkStatusWorker(QThread):
    """后台线程：联网校验 config.json 里保存的夸克 Cookie 是否仍有效"""

    done = Signal(bool, str)  # (是否有效, 昵称或失败原因)

    def __init__(self, cookie: str, parent=None):
        super().__init__(parent)
        self.cookie = cookie or ""

    def run(self):
        try:
            from core.online_install import verify_cookie
            ok, msg = verify_cookie(self.cookie)
            self.done.emit(bool(ok), str(msg or ""))
        except Exception as e:  # noqa: BLE001
            self.done.emit(False, f"验证出错：{e}")


class _Card(QFrame):
    """设置页通用卡片容器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QFrame {{ background-color: {_COLOR_CARD_BG}; border-radius: 12px; }}")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 18, 20, 18)
        self._layout.setSpacing(10)

    def add_title(self, text: str):
        title = QLabel(text)
        title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        title.setStyleSheet("color: #ffffff; background: transparent;")
        self._layout.addWidget(title)

    def add_text(self, text: str, color=_COLOR_SUB, size: int = 10):
        label = QLabel(text)
        label.setFont(QFont("Microsoft YaHei", size))
        label.setStyleSheet(f"color: {color}; background: transparent;")
        label.setWordWrap(True)
        self._layout.addWidget(label)

    def add_row(self, widget):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(widget)
        self._layout.addLayout(row)

    def add_spacer(self, height: int = 2):
        self._layout.addSpacing(height)


class SettingsPage(QWidget):
    """设置页面：夸克账号 / 下载缓存 / 关于"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self._status_worker = None
        self._busy = False
        self._setup_ui()
        self.refresh_login_status()

    # ------------------------------------------------------------------ UI
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题栏
        nav_bar = QFrame()
        nav_bar.setFixedHeight(64)
        nav_bar.setStyleSheet(
            "QFrame { background: transparent; border: none;"
            " border-bottom: 1px solid #333333; }")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(24, 0, 24, 0)

        title = QLabel("⚙️ 设置")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        title.setStyleSheet("color: #ffffff; background: transparent;")
        nav_layout.addWidget(title)

        nav_layout.addStretch()
        layout.addWidget(nav_bar)

        # 内容滚动区（小窗口可滚动）
        scroll = QWidget()
        body = QVBoxLayout(scroll)
        body.setContentsMargins(24, 18, 24, 24)
        body.setSpacing(16)
        body.setAlignment(Qt.AlignTop)

        # ---------------- 卡 1：夸克网盘账号 ----------------
        quark_card = _Card()
        quark_card.add_title("🔑 夸克网盘账号")
        quark_card.add_text(
            "在线模组下载需要登录夸克网盘。可在软件内直接扫码 / 手机号 / 账密登录，"
            "Cookie 仅保存在本机 config.json 中。", size=10)

        # 状态大字
        self.quark_state_label = QLabel("尚未登录")
        self.quark_state_label.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        self.quark_state_label.setStyleSheet(
            f"color: {_COLOR_RED}; background: transparent;")
        quark_card.add_row(self.quark_state_label)

        # 登录主按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.login_btn = QPushButton("🔑  登录夸克账号")
        self.login_btn.setMinimumHeight(42)
        self.login_btn.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.clicked.connect(self._do_login)
        btn_row.addWidget(self.login_btn, stretch=3)

        self.verify_btn = QPushButton("🔄 验证登录状态")
        self.verify_btn.setMinimumHeight(42)
        self.verify_btn.setCursor(Qt.PointingHandCursor)
        self.verify_btn.clicked.connect(self.refresh_login_status)
        btn_row.addWidget(self.verify_btn, stretch=2)
        quark_card._layout.addLayout(btn_row)

        self.logout_btn = QPushButton("退出登录")
        self.logout_btn.setFixedHeight(34)
        self.logout_btn.setCursor(Qt.PointingHandCursor)
        self.logout_btn.clicked.connect(self._do_logout)
        quark_card.add_row(self.logout_btn)
        quark_card.add_spacer(4)

        quark_card.add_text(
            "说明：下载时会转存到您网盘固定目录「KnightModder」中（不建子文件夹），"
            "下载完成后会保留不删除，您可随时到网盘里自行清理。", color=_COLOR_DIM, size=9)
        body.addWidget(quark_card)

        # ---------------- 卡 2：下载设置与缓存 ----------------
        dl_card = _Card()
        dl_card.add_title("📥 下载设置与缓存")
        dl_card.add_text("Mod 安装包会先下载到软件目录的 downloads 文件夹中，安装完成可自行清理。",
                         size=10)
        self.dl_path_label = QLabel(get_download_dir())
        self.dl_path_label.setFont(QFont("Consolas", 10))
        self.dl_path_label.setStyleSheet(
            f"color: #9ecbff; background: #1a1a1e; border-radius: 6px; padding: 8px 12px;")
        self.dl_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        dl_card.add_row(self.dl_path_label)

        open_dir_btn = QPushButton("📂 打开下载目录")
        open_dir_btn.setFixedHeight(36)
        open_dir_btn.setCursor(Qt.PointingHandCursor)
        open_dir_btn.clicked.connect(self._open_download_dir)
        dl_card.add_row(open_dir_btn)
        dl_card.add_spacer(6)

        # 同时下载的安装包路数（本体 + 前置在下载阶段全并行）
        dl_card.add_title("⚡ 下载并行数")
        dl_card.add_text(
            "同一批中「目标 Mod + 缺失前置」的安装包同时下载的数量。Mod 大多是很小的文件，"
            "并发拉取能明显加快整批下载；调高占用更多带宽。", size=10)
        p_row = QHBoxLayout()
        p_row.setSpacing(10)
        p_lbl = QLabel("同时下载")
        p_lbl.setFont(QFont("Microsoft YaHei", 11))
        p_lbl.setStyleSheet(f"color: {_COLOR_SUB}; background: transparent;")
        self.parallel_box = QSpinBox()
        self.parallel_box.setRange(1, 16)
        self.parallel_box.setValue(8)
        self.parallel_box.setSuffix(" 路")
        self.parallel_box.setFixedWidth(120)
        self.parallel_box.setAlignment(Qt.AlignCenter)
        self.parallel_box.setFont(QFont("Consolas", 11))
        self.parallel_box.setStyleSheet(
            "QSpinBox { background: #1a1a1e; color: #9ecbff; border: 1px solid #33333c;"
            " border-radius: 6px; padding: 5px 6px; }"
            "QSpinBox::up-button, QSpinBox::down-button { width: 18px; }")
        try:
            val = int(load_app_setting("parallel_downloads", 8) or 8)
        except Exception:
            val = 8
        self.parallel_box.setValue(max(1, min(16, val)))
        self.parallel_box.valueChanged.connect(self._on_parallel_changed)
        p_row.addWidget(p_lbl)
        p_row.addWidget(self.parallel_box)
        p_row.addStretch()
        dl_card._layout.addLayout(p_row)
        dl_card.add_text(
            "实际生效数不会超过本次任务需要的安装包个数；调得过高若触发夸克限流，请适当调低。",
            color=_COLOR_DIM, size=9)
        body.addWidget(dl_card)

        # ---------------- 卡 3：关于 ----------------
        about_card = _Card()
        about_card.add_title("ℹ️ 关于")
        self.about_label = QLabel(self._load_version_text())
        self.about_label.setFont(QFont("Microsoft YaHei", 10))
        self.about_label.setStyleSheet(f"color: {_COLOR_SUB}; background: transparent;")
        self.about_label.setWordWrap(True)
        about_card.add_row(self.about_label)
        body.addWidget(about_card)

        body.addStretch()
        layout.addWidget(scroll, stretch=1)

    @staticmethod
    def _load_version_text() -> str:
        """从 version.json 读取版本信息"""
        try:
            path = os.path.join(get_base_dir(), "version.json")
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                ver = data.get("version", "")
                date = data.get("release_date", "")
                return f"版本：{ver}（{date}）\n{data.get('changelog', '') or ''}"
        except Exception:
            pass
        return ""

    # ---------------------------------------------------------- 业务逻辑
    def refresh_login_status(self):
        """刷新夸克登录状态：先本地判断有没有 Cookie，再起线程联网验证"""
        if self._busy:
            return
        cookie = load_quark_cookie()
        if not cookie:
            self.quark_state_label.setText("尚未登录")
            self.quark_state_label.setStyleSheet(
                f"color: {_COLOR_RED}; background: transparent;")
            self.login_btn.setText("🔑  登录夸克账号")
            self.logout_btn.setEnabled(False)
            return

        self._busy = True
        self.quark_state_label.setText("正在验证登录状态…")
        self.quark_state_label.setStyleSheet(f"color: {_COLOR_DIM}; background: transparent;")
        self.logout_btn.setEnabled(True)

        self._status_worker = _QuarkStatusWorker(cookie, self)
        self._status_worker.done.connect(self._on_status_done)
        self._status_worker.start()

    def _on_status_done(self, ok: bool, msg: str):
        self._busy = False
        if ok:
            self.quark_state_label.setText(f"✅ 已登录：{msg or '夸克用户'}")
            self.quark_state_label.setStyleSheet(
                f"color: {_COLOR_GREEN}; background: transparent;")
            self.login_btn.setText("🔑  切换夸克账号")
        else:
            self.quark_state_label.setText(f"⚠ 登录已失效：{msg or 'Cookie 过期'}")
            self.quark_state_label.setStyleSheet(
                f"color: {_COLOR_ORANGE}; background: transparent;")
            self.login_btn.setText("🔑  重新登录夸克账号")

    def _do_login(self):
        """打开软件内嵌夸克登录页（扫码 / 手机号 / 账密）"""
        try:
            from ui.quark_login_dialog import show_quark_login_dialog
        except ImportError:
            from quark_login_dialog import show_quark_login_dialog
        saved = show_quark_login_dialog(self)
        if saved:
            self._sync_status_after_change("夸克账号已登录并保存")
        return saved

    def _do_logout(self):
        """清除本地保存的夸克 Cookie"""
        ret = QMessageBox.question(
            self, "退出登录",
            "确定要退出夸克网盘账号吗？已保存的 Cookie 将从本机清除。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        save_quark_cookie("")
        self._sync_status_after_change("已退出夸克账号")

    def _sync_status_after_change(self, tip: str):
        """登录/退出后：刷新本页状态，并同步在线模组页与日志"""
        self.refresh_login_status()
        parent = self.parent
        if parent is not None:
            page_online = getattr(parent, "page_online", None)
            if page_online is not None:
                page_online._refresh_quark_status()
            if hasattr(parent, "_log"):
                parent._log(tip, "success")

    @staticmethod
    def _open_download_dir():
        path = get_download_dir()
        if not os.path.isdir(path):
            os.makedirs(path, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _on_parallel_changed(self, value):
        """下载并行数变化 -> 立即写入 config.json（下次下载即生效）"""
        save_app_setting("parallel_downloads", int(value))
