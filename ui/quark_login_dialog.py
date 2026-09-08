# -*- coding: utf-8 -*-
"""
夸克网盘内嵌登录对话框。

实现方式：
  1. 用 QtWebEngine 在软件内打开 https://pan.quark.cn/（夸克官方登录页），
     用户可直接扫码登录（夸克App扫二维码）或使用手机号/账号密码登录，全程在软件内完成；
  2. 登录成功后 WebEngine 的 CookieStore 会捕获到 __pus / __puus 等关键 Cookie，
     对话框自动用 account/info 接口联网验证有效性，通过后保存到 config.json 并自动关闭；
  3. 验证未自动触发成功时，可点「完成登录」手动提交当前已捕获的 Cookie；
  4. 若当前环境缺少 QtWebEngine，或用户希望沿用旧方式，对话框内保留
     「手动粘贴 Cookie」作为回退入口。
"""
import time

from PySide6.QtCore import Qt, QTimer, Signal, QThread, QUrl
from PySide6.QtGui import QFont
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)

# 样式常量（与 dialogs.py 深色系保持一致）
_COLOR_BG = "#1e1e1e"
_COLOR_TEXT = "#ffffff"
_COLOR_TEXT_SUB = "#bbbbbb"
_COLOR_TEXT_DIM = "#999999"
_COLOR_ACCENT = "#34c759"
_COLOR_RED = "#ff6b6b"
_COLOR_WARN = "#ff9800"

QUARK_HOME_URL = "https://pan.quark.cn/"

try:
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView

    _WEBENGINE_AVAILABLE = True
except Exception:  # noqa: BLE001 —— 个别精简安装缺 QtWebEngine
    _WEBENGINE_AVAILABLE = False


def _as_str(value) -> str:
    """把 bytes/QByteArray/str 统一成 str（QNetworkCookie 属性返回 QByteArray）"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    # QByteArray 包装对象 -> bytes -> str
    try:
        raw = bytes(value)
    except Exception:  # noqa: BLE001
        return ""
    return raw.decode("utf-8", errors="ignore")


class _CookieVerifyWorker(QThread):
    """后台线程：用 account/info 接口验证一段夸克 Cookie 头是否有效"""

    done = Signal(bool, str)

    def __init__(self, cookie_header: str, parent=None):
        super().__init__(parent)
        self.cookie_header = cookie_header

    def run(self):
        try:
            from core.online_install import verify_cookie
            ok, msg = verify_cookie(self.cookie_header)
            self.done.emit(bool(ok), str(msg or ""))
        except Exception as e:  # noqa: BLE001
            self.done.emit(False, f"验证失败：{e}")


class QuarkLoginDialog(QDialog):
    """内嵌夸克官方登录页；登录成功后自动保存 Cookie 并关闭"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("夸克网盘登录")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFixedSize(780, 700)
        self.setStyleSheet(f"background-color: {_COLOR_BG};")

        # ---------- 捕获到的 Cookie（name -> value） ----------
        self._cookies: dict = {}
        self._profile = None
        self._view = None
        self._checking = False
        self._last_checked_header = ""
        self._verify_worker = None

        self._build_ui()
        self._start_webview()

        # 轮询：关键 Cookie 出现即自动联网验证
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(700)

    # ---------- UI ----------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        title = QLabel("🔑 登录夸克网盘")
        title.setFont(QFont("Microsoft YaHei", 15, QFont.Bold))
        title.setStyleSheet(f"color: {_COLOR_TEXT}; background: transparent;")
        layout.addWidget(title)

        tip = QLabel(
            "在下方官方登录页中完成登录：推荐用夸克App「扫一扫」扫码，也可切换手机号/账密登录。\n"
            "登录成功后本窗口会自动保存并关闭（无需手动复制任何内容）。"
        )
        tip.setFont(QFont("Microsoft YaHei", 10))
        tip.setStyleSheet(f"color: {_COLOR_TEXT_SUB}; background: transparent;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        # 状态提示条（验证中 / 成功 / 失败原因）
        self._state_label = QLabel("等待登录...")
        self._state_label.setFixedHeight(20)
        self._state_label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        self._state_label.setStyleSheet(
            f"color: {_COLOR_TEXT_DIM}; background: transparent;")
        layout.addWidget(self._state_label)

        # 内嵌浏览器
        self._browser_container = QVBoxLayout()
        self._browser_container.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._browser_container, stretch=1)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        manual_btn = QPushButton("手动粘贴 Cookie（备选）")
        manual_btn.setStyleSheet(self._btn_style(primary=False))
        manual_btn.clicked.connect(self._open_manual_dialog)
        btn_row.addWidget(manual_btn)

        reload_btn = QPushButton("刷新登录页")
        reload_btn.setStyleSheet(self._btn_style(primary=False))
        reload_btn.clicked.connect(lambda: self._load_home())
        btn_row.addWidget(reload_btn)

        btn_row.addStretch()

        self._finish_btn = QPushButton("✅ 完成登录")
        self._finish_btn.setStyleSheet(self._btn_style(primary=True))
        self._finish_btn.setEnabled(False)
        self._finish_btn.clicked.connect(self._manual_finish)
        btn_row.addWidget(self._finish_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(self._btn_style(primary=False))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)

    @staticmethod
    def _btn_style(primary: bool) -> str:
        if primary:
            return """
                QPushButton {
                    background-color: #34c759; color: white; border: none;
                    border-radius: 15px; padding: 7px 18px; font-weight: 700;
                }
                QPushButton:hover { background-color: #28a745; }
                QPushButton:disabled {
                    background-color: #2c2c2c; color: #666666;
                }
            """
        return """
            QPushButton {
                background-color: #2e2e2e; color: #cccccc;
                border: 1px solid #555555; border-radius: 15px;
                padding: 7px 14px; font-weight: 700;
            }
            QPushButton:hover { background-color: #3a3a3a; color: #ffffff; }
        """

    # ---------- WebEngine ----------
    def _start_webview(self):
        if not _WEBENGINE_AVAILABLE:
            self._set_state("当前环境缺少 QtWebEngine，请使用「手动粘贴 Cookie」登录。",
                            _COLOR_WARN)
            return
        # 无参构造即离屏会话（不落盘，每次登录都是全新会话，避免旧 Cookie 干扰判定）
        self._profile = QWebEngineProfile(self)
        self._profile.cookieStore().cookieAdded.connect(self._on_cookie_added)

        self._view = QWebEngineView(self)
        page = QWebEnginePage(self._profile, self._view)
        self._view.setPage(page)
        self._browser_container.addWidget(self._view)
        self._load_home()

    def _load_home(self):
        if self._view:
            self._view.load(QUrl(QUARK_HOME_URL))

    # ---------- Cookie 捕获 ----------
    def _on_cookie_added(self, cookie: QNetworkCookie):
        try:
            domain = _as_str(cookie.domain())
            name = _as_str(cookie.name())
            value = _as_str(cookie.value())
            if not name or not value:
                return
            # 只收夸克域下的 Cookie，避免混入无关第三方
            if "quark.cn" not in domain.lower():
                return
            self._cookies[name] = value
            if len(self._cookies) > 80:  # 防御性上限
                self._cookies = dict(list(self._cookies.items())[-80:])
            if "__pus" in self._cookies and "__puus" in self._cookies:
                if not self._finish_btn.isEnabled():
                    self._finish_btn.setEnabled(True)
        except Exception:
            pass

    def _cookie_header(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self._cookies.items())

    def _has_key_cookies(self) -> bool:
        return bool(self._cookies.get("__pus")) and bool(self._cookies.get("__puus"))

    # ---------- 状态 ----------
    def _set_state(self, text, color=_COLOR_TEXT_DIM):
        self._state_label.setText(text)
        self._state_label.setStyleSheet(
            f"color: {color}; background: transparent;")

    # ---------- 自动 / 手动验证 ----------
    def _tick(self):
        """轮询：检测到关键 Cookie 且内容有变化时自动发起验证（失败会冷却重试）"""
        if not self._has_key_cookies():
            return
        if self._checking:
            return
        header = self._cookie_header()
        if header == self._last_checked_header:
            return  # 内容没变说明还没真正登录成功，等登录页刷新 Cookie
        self._start_verify(header, auto=True)

    def _manual_finish(self):
        if not self._has_key_cookies():
            self._set_state("还没捕获到有效登录态，请在页面里完成登录后再点这里。",
                            _COLOR_WARN)
            return
        self._start_verify(self._cookie_header(), auto=False)

    def _start_verify(self, header: str, auto: bool):
        self._checking = True
        self._last_checked_header = header
        self._set_state("正在验证登录状态，请稍候...", _COLOR_TEXT_DIM)
        self._finish_btn.setEnabled(False)

        self._verify_worker = _CookieVerifyWorker(header, self)
        self._verify_worker.done.connect(
            lambda ok, msg, h=header: self._on_verify_done(ok, msg, h))
        self._verify_worker.start()

    def _on_verify_done(self, ok: bool, msg: str, header: str):
        self._checking = False
        if ok:
            # 验证通过 -> 保存并自动关闭
            try:
                from utils.common import save_quark_cookie
                save_quark_cookie(header)
            except Exception as e:  # noqa: BLE001
                self._set_state(f"验证通过但保存失败：{e}", _COLOR_RED)
                self._finish_btn.setEnabled(True)
                return
            self._set_state(f"✅ 登录成功（{msg}），Cookie 已保存", _COLOR_ACCENT)
            QTimer.singleShot(400, self.accept)
            return

        # 失败：可能是登录流程还没走完 / 账号异常 / 网络问题
        self._set_state(
            f"❌ 登录未通过：{msg or 'Cookie 无效'}。\n"
            "如果页面尚未登录成功，请继续在页面中完成登录，本窗口会自动重试；"
            "也可以稍后点「完成登录」。",
            _COLOR_RED,
        )
        # 内容不变时不再自动轰炸；用户重新登录产生新 Cookie 后会自动再验
        if self._has_key_cookies():
            self._finish_btn.setEnabled(True)

    # ---------- 手动回退 ----------
    def _open_manual_dialog(self):
        """沿用旧的手动粘贴对话框（保留作备选路径）"""
        try:
            from ui.dialogs import show_quark_cookie_dialog
        except ImportError:
            from dialogs import show_quark_cookie_dialog
        saved = show_quark_cookie_dialog(self)
        if saved:
            self._set_state("✅ 手动粘贴的 Cookie 已保存", _COLOR_ACCENT)
            QTimer.singleShot(300, self.accept)

    # ---------- 收尾 ----------
    def closeEvent(self, event):
        try:
            self._timer.stop()
        except Exception:
            pass
        try:
            if self._verify_worker is not None:
                self._verify_worker.wait(1500)
        except Exception:
            pass
        # 释放 WebEngine，避免关闭后残留 GPU/渲染进程
        try:
            if self._view is not None:
                layout = self._view.parentWidget()
                if layout is not None:
                    self._browser_container.removeWidget(self._view)
                self._view.setPage(None)
                self._view.deleteLater()
                self._view = None
        except Exception:
            pass
        try:
            if self._profile is not None:
                self._profile.deleteLater()
                self._profile = None
        except Exception:
            pass
        super().closeEvent(event)


def show_quark_login_dialog(parent=None) -> bool:
    """
    打开夸克内嵌登录对话框（扫码 / 账密 / 手机号）。
    :return: True=已获得并保存有效 Cookie；False=用户取消或失败
    """
    if not _WEBENGINE_AVAILABLE:
        try:
            from ui.dialogs import show_quark_cookie_dialog
        except ImportError:
            from dialogs import show_quark_cookie_dialog
        return show_quark_cookie_dialog(parent)
    dlg = QuarkLoginDialog(parent)
    return dlg.exec() == QDialog.Accepted
