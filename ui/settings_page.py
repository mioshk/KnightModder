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
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from utils.common import (
    get_base_dir,
    get_download_dir,
    load_parallel_downloads,
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
_COLOR_BORDER = "rgba(255, 255, 255, 0.07)"

# 按钮统一高度；宽度靠内容自适应（见 _mk_btn），不再被布局拉满卡片
_BTN_H = 36
_FONT = "Microsoft YaHei"


def _btn_style(kind: str) -> str:
    """三种按钮样式：primary 主操作 / ghost 次要 / danger 危险操作"""
    base = ("font-family: '%s'; border-radius: 10px; padding: 0 15px;" % _FONT)
    if kind == "primary":
        return f"""
            QPushButton {{ {base} background: #34c759; color: white; border: none;
                font-size: 12px; font-weight: 700; }}
            QPushButton:hover {{ background: #2eb750; }}
            QPushButton:pressed {{ background: #28a745; }}
            QPushButton:disabled {{ background: #2a2a30; color: #6a6a6a; }}
        """
    if kind == "danger":
        return f"""
            QPushButton {{ {base} background: transparent; color: #ff6b6b;
                border: 1px solid rgba(255, 107, 107, 0.45);
                font-size: 11px; font-weight: 700; }}
            QPushButton:hover {{ background: rgba(255, 107, 107, 0.12); }}
            QPushButton:disabled {{ color: #555555; border-color: #333338; }}
        """
    return f"""
        QPushButton {{ {base} background: rgba(255, 255, 255, 0.04); color: #c8c8c8;
            border: 1px solid rgba(255, 255, 255, 0.10);
            font-size: 11px; font-weight: 600; }}
        QPushButton:hover {{ background: rgba(255, 255, 255, 0.09); color: #ffffff; }}
    """


def _mk_btn(text: str, kind: str = "ghost", min_width: int = 0) -> QPushButton:
    """按内容宽度排布的按钮。

    关键点：QSizePolicy.Maximum 让按钮最多只占自身所需宽度。之前用 stretch=3/2
    或直接 addWidget，按钮会被布局拉到整张卡片那么宽，看起来很笨重。
    """
    btn = QPushButton(text)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setFixedHeight(_BTN_H)
    btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    if min_width:
        btn.setMinimumWidth(min_width)
    btn.setStyleSheet(_btn_style(kind))
    return btn


def _badge(text: str, color: str, bg: str) -> QLabel:
    """状态徽章（带底色的小标签），比纯文字更容易一眼看清状态"""
    lbl = QLabel(text)
    lbl.setFont(QFont(_FONT, 11, QFont.Bold))
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    lbl.setStyleSheet(
        f"color: {color}; background: {bg}; border-radius: 9px; padding: 5px 12px;")
    return lbl


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
        # 必须用 objectName 限定选择器：裸写 "QFrame { ... }" 会命中卡片内所有后代
        # QFrame，而 QLabel 正是 QFrame 的子类 —— 那样每个文字标签都会被套上
        # 一条 1px 边框，看起来就是"每行字都有个很浅的灰框"。
        self.setObjectName("SettingsCard")
        self.setStyleSheet(
            f"#SettingsCard {{ background-color: {_COLOR_CARD_BG};"
            f" border: 1px solid {_COLOR_BORDER}; border-radius: 14px; }}")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 18, 20, 18)
        self._layout.setSpacing(9)

    def add_title(self, text: str, side=None):
        """标题行；side 可传一个靠右的小部件（如状态徽章）"""
        row = QHBoxLayout()
        row.setSpacing(10)
        title = QLabel(text)
        title.setFont(QFont(_FONT, 13, QFont.Bold))
        title.setStyleSheet("color: #ffffff; background: transparent;")
        row.addWidget(title)
        row.addStretch()
        if side is not None:
            row.addWidget(side, alignment=Qt.AlignRight)
        self._layout.addLayout(row)

    def add_text(self, text: str, color=_COLOR_SUB, size: int = 10):
        label = QLabel(text)
        label.setFont(QFont(_FONT, size))
        label.setStyleSheet(f"color: {color}; background: transparent;")
        label.setWordWrap(True)
        self._layout.addWidget(label)

    def add_row(self, *widgets, stretch_last=False):
        """一行控件：默认靠左排布，末尾补 stretch 防止被拉宽"""
        row = QHBoxLayout()
        row.setSpacing(10)
        for w in widgets:
            row.addWidget(w, 1 if stretch_last else 0)
        if not stretch_last:
            row.addStretch()
        self._layout.addLayout(row)

    def add_divider(self):
        line = QFrame()
        line.setObjectName("SettingsDivider")
        line.setFixedHeight(1)
        line.setStyleSheet(
            f"#SettingsDivider {{ background: {_COLOR_BORDER}; border: none; }}")
        self._layout.addWidget(line)

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
        nav_bar.setObjectName("SettingsNavBar")
        nav_bar.setFixedHeight(64)
        # 同样用 objectName：否则标题 QLabel 也会被套上下边框
        nav_bar.setStyleSheet(
            "#SettingsNavBar { background: transparent; border: none;"
            " border-bottom: 1px solid #333333; }")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(24, 0, 24, 0)

        title = QLabel("⚙️ 设置")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        title.setStyleSheet("color: #ffffff; background: transparent;")
        nav_layout.addWidget(title)

        nav_layout.addStretch()
        layout.addWidget(nav_bar)

        # 内容区：限宽居中，避免卡片在宽屏上被拉得很长
        scroll = QWidget()
        outer = QHBoxLayout(scroll)
        outer.setContentsMargins(24, 18, 24, 24)
        outer.setSpacing(0)

        center = QWidget()
        center.setMaximumWidth(880)
        body = QVBoxLayout(center)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(14)
        body.setAlignment(Qt.AlignTop)
        outer.addStretch(1)
        outer.addWidget(center, 4)
        outer.addStretch(1)

        # ---------------- 卡 1：夸克网盘账号 ----------------
        quark_card = _Card()
        self.quark_state_label = _badge("尚未登录", _COLOR_RED, _COLOR_RED_BG)
        quark_card.add_title("🔑 夸克网盘账号", side=self.quark_state_label)
        quark_card.add_text(
            "在线模组下载需要登录夸克网盘。可直接在软件内扫码 / 手机号 / 账密登录，"
            "Cookie 仅保存在本机 config.json 中。", size=10)
        quark_card.add_spacer(2)

        self.login_btn = _mk_btn("🔑  登录夸克账号", "primary", min_width=150)
        self.login_btn.clicked.connect(self._do_login)
        self.verify_btn = _mk_btn("🔄  验证状态", "ghost")
        self.verify_btn.clicked.connect(self.refresh_login_status)
        self.logout_btn = _mk_btn("退出登录", "danger")
        self.logout_btn.clicked.connect(self._do_logout)
        quark_card.add_row(self.login_btn, self.verify_btn, self.logout_btn)

        quark_card.add_text(
            "下载时会转存到您网盘固定目录「KnightModder」中（不建子文件夹），"
            "下载完成后保留不删除，可随时到网盘里自行清理。", color=_COLOR_DIM, size=9)
        body.addWidget(quark_card)

        # ---------------- 卡 2：下载设置与缓存 ----------------
        dl_card = _Card()
        dl_card.add_title("📥 下载设置与缓存")
        dl_card.add_text("Mod 安装包先下载到软件目录的 downloads 文件夹，安装完成可自行清理。",
                         size=10)

        self.dl_path_label = QLabel(get_download_dir())
        self.dl_path_label.setFont(QFont("Consolas", 10))
        self.dl_path_label.setStyleSheet(
            "color: #9ecbff; background: #1a1a1e; border: 1px solid #2c2c34;"
            " border-radius: 8px; padding: 8px 12px;")
        self.dl_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        open_dir_btn = _mk_btn("📂 打开", "ghost")
        open_dir_btn.clicked.connect(self._open_download_dir)
        # 路径占满剩余宽度，按钮按自身宽度靠右
        dl_card.add_row(self.dl_path_label, open_dir_btn, stretch_last=False)

        dl_card.add_divider()
        dl_card.add_spacer(4)

        # 同时下载的安装包路数（本体 + 前置在下载阶段全并行）
        p_lbl = QLabel("⚡ 下载并行数")
        p_lbl.setFont(QFont(_FONT, 12, QFont.Bold))
        p_lbl.setStyleSheet("color: #ffffff; background: transparent;")
        self.parallel_box = QSpinBox()
        self.parallel_box.setRange(1, 16)
        self.parallel_box.setSuffix(" 路")
        self.parallel_box.setFixedWidth(110)
        self.parallel_box.setFixedHeight(_BTN_H)
        self.parallel_box.setAlignment(Qt.AlignCenter)
        self.parallel_box.setFont(QFont("Consolas", 11))
        self.parallel_box.setStyleSheet(
            "QSpinBox { background: #1a1a1e; color: #9ecbff; border: 1px solid #2c2c34;"
            " border-radius: 8px; padding: 4px 6px; }"
            "QSpinBox::up-button, QSpinBox::down-button { width: 18px; }")
        self.parallel_box.setValue(load_parallel_downloads())
        self.parallel_box.valueChanged.connect(self._on_parallel_changed)
        dl_card.add_row(p_lbl, self.parallel_box)
        dl_card.add_text(
            "默认 1 路。调高能提速，但更容易触发风控；被风控时退出账号重新登录即可。",
            color=_COLOR_DIM, size=9)
        body.addWidget(dl_card)

        # ---------------- 卡 3：关于 ----------------
        about_card = _Card()
        self.about_label = QLabel()
        self.about_label.setFont(QFont(_FONT, 10))
        self.about_label.setStyleSheet(f"color: {_COLOR_SUB}; background: transparent;")
        self.about_label.setWordWrap(True)
        self.about_label.setText(self._about_text())
        about_card.add_title("ℹ️ 关于")
        about_card.add_row(self.about_label, stretch_last=True)
        body.addWidget(about_card)

        body.addStretch()
        layout.addWidget(scroll, stretch=1)

    @staticmethod
    def _load_version_text() -> str:
        """从 version.json 读取版本信息（保留给外部调用）"""
        try:
            path = os.path.join(get_base_dir(), "version.json")
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return (data.get("version", ""),
                        data.get("release_date", ""),
                        data.get("changelog", "") or "")
        except Exception:
            pass
        return "", "", ""

    @staticmethod
    def _about_text() -> str:
        """关于卡片正文：版本号 + 发布日期 + 更新内容"""
        ver, date, changelog = SettingsPage._load_version_text()
        if not ver:
            try:
                from config import APP_VERSION
                ver = APP_VERSION
            except Exception:
                ver = ""
        head = f"版本 {ver}" + (f"　·　{date}" if date else "")
        if changelog:
            return f"{head}\n\n{changelog}"
        return head

    def _set_quark_state(self, text: str, color: str, bg: str):
        """更新状态徽章（setText + 保持徽章的底色/圆角样式）"""
        self.quark_state_label.setText(text)
        self.quark_state_label.setStyleSheet(
            f"color: {color}; background: {bg}; border-radius: 9px; padding: 5px 12px;")

    # ---------------------------------------------------------- 业务逻辑
    def refresh_login_status(self):
        """刷新夸克登录状态：先本地判断有没有 Cookie，再起线程联网验证"""
        cookie = load_quark_cookie()
        if not cookie:
            self._busy = False
            self._set_quark_state("尚未登录", _COLOR_RED, _COLOR_RED_BG)
            self.login_btn.setText("🔑  登录夸克账号")
            self.login_btn.setVisible(True)
            self.logout_btn.setEnabled(False)
            return

        self._busy = True
        self._set_quark_state("正在验证…", _COLOR_DIM, "rgba(255, 255, 255, 0.06)")
        self.logout_btn.setEnabled(True)
        self._start_status_worker(cookie)

    def _start_status_worker(self, cookie: str):
        """起一条新的状态校验线程；旧线程的结果一律丢弃，避免切号后被旧结果盖回去。"""
        old = getattr(self, "_status_worker", None)
        if old is not None:
            try:
                old.done.disconnect(self._on_status_done)
            except Exception:
                pass
        worker = _QuarkStatusWorker(cookie, self)
        self._status_worker = worker
        worker.done.connect(self._on_status_done)
        worker.start()

    def _on_status_done(self, ok: bool, msg: str):
        if self.sender() is not self._status_worker:
            return
        self._busy = False
        if ok:
            self._set_quark_state(f"✅ 已登录 · {msg or '夸克用户'}",
                                  _COLOR_GREEN, _COLOR_GREEN_BG)
            # 已登录就不再显示登录按钮：要换账号直接「退出登录」再登即可，
            # 单独留一个"切换账号"入口没有意义。
            self.login_btn.setVisible(False)
        else:
            self._set_quark_state(f"⚠ 登录已失效 · {msg or 'Cookie 过期'}",
                                  _COLOR_ORANGE, "rgba(255, 149, 0, 0.14)")
            self.login_btn.setText("🔑  重新登录")
            self.login_btn.setVisible(True)

    def _do_login(self):
        """打开软件内嵌夸克登录页（扫码 / 手机号 / 账密）"""
        try:
            from ui.quark_login_dialog import show_quark_login_dialog
        except ImportError:
            from quark_login_dialog import show_quark_login_dialog
        saved = show_quark_login_dialog(self)
        if saved:
            self._busy = False
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
        save_app_setting("parallel_downloads_user_set", True)
