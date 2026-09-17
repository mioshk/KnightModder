# -*- coding: utf-8 -*-
"""
夸克网盘登录（系统浏览器内核版）。

实现方式：
  1. 点击登录后弹出一个独立的浏览器窗口，打开 https://pan.quark.cn/ 官方登录页，
     用户扫码（夸克 App）或用手机号/账密登录，全程不需要离开本软件；
  2. 登录成功后从窗口里读回 Cookie（走 WebView2 官方的 Cookie 管理器，
     HttpOnly 的登录令牌 __pus / __puus 也读得到），自动用 account/info 接口
     联网验证，通过后写入 config.json 并关闭窗口；
  3. 若当前系统没有可用的浏览器内核，或用户中途关闭窗口，回退到「手动粘贴 Cookie」。

为什么不再用 QtWebEngine：
  QtWebEngine 等于把一整个 Chromium 塞进安装包（195 MB），占了软件体积的七成。
  改用系统自带的 Edge 内核（WebView2）后体验完全一样，体积却能从 ~305 MB 降到
  ~95 MB。实测 WebView2 的 CookieManager 能读回 HttpOnly 的登录令牌，所以登录
  功能不受影响。
"""
import time

from PySide6.QtWidgets import QMessageBox

# 样式常量（与 dialogs.py 深色系保持一致）
_COLOR_BG = "#1e1e1e"
_COLOR_TEXT = "#ffffff"
_COLOR_TEXT_SUB = "#bbbbbb"
_COLOR_TEXT_DIM = "#999999"
_COLOR_ACCENT = "#34c759"
_COLOR_RED = "#ff6b6b"
_COLOR_WARN = "#ff9800"

QUARK_HOME_URL = "https://pan.quark.cn/"

# 登录窗口最长等待时间（秒）；超时或用户关闭窗口都算未完成
_LOGIN_TIMEOUT = 900
# 轮询间隔（秒）
_POLL_INTERVAL = 1.2


def webview_available() -> bool:
    """系统是否具备可用的浏览器内核（延迟导入，启动阶段不加载）"""
    try:
        import webview  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _cookies_to_header(cookies) -> str:
    """把 WebView2 读回的 Cookie 拼成 Cookie 请求头。

    pywebview 的 get_cookies() 返回一串 http.cookies.SimpleCookie（每个内含一条
    Set-Cookie 的完整结构），这里只挑夸克域下的 name=value。
    """
    from core.quark import is_quark_cookie_domain

    pairs = {}
    for cookie in cookies or []:
        try:
            items = dict(cookie).items()
        except Exception:  # noqa: BLE001
            continue
        for name, morsel in items:
            # 注意：Morsel 是 dict 子类，domain 是"字典项"而不是属性，
            # 用 getattr 永远取不到（会静默让域名过滤失效），必须走 .get()
            try:
                domain = str(morsel.get("domain", "") or "")
            except Exception:  # noqa: BLE001
                domain = ""
            if not is_quark_cookie_domain(domain):
                continue
            value = getattr(morsel, "value", None)
            if value is None:
                value = getattr(morsel, "coded_value", "")
            value = str(value).strip('"')
            if name and value:
                pairs[str(name)] = value
    return "; ".join(f"{k}={v}" for k, v in pairs.items())


def _has_key_cookies(header: str) -> bool:
    """登录态的两个关键令牌都在，才算登录完成"""
    return "__pus=" in header and "__puus=" in header


def is_same_saved_account(header: str) -> bool:
    """当前读到的登录态是否就是 config.json 里已经保存的那个号。

    只比对账号标识 __pus：__puus/ctoken 是每次访问网盘都会被服务端轮换的会话
    令牌（下载前必须主动换新，否则直链全是 412），不能用来判身份。
    """
    try:
        from core.quark import same_login_account
        from utils.common import load_quark_cookie
        saved = load_quark_cookie()
    except Exception:  # noqa: BLE001
        return False
    if not saved:
        return False
    return same_login_account(header, saved)


def _verify(header: str):
    """联网验证一段 Cookie 头是否有效 -> (是否成功, 昵称或原因)"""
    try:
        from core.online_install import verify_cookie
        ok, msg = verify_cookie(header)
        return bool(ok), str(msg or "")
    except Exception as e:  # noqa: BLE001
        return False, f"验证失败：{e}"


def _evaluate_cookies(cookies, last_header):
    """检查一次读到的 Cookie，返回 (是否已登录成功, 当前 header, 昵称或原因)。

    单独抽成函数是便于测试：轮询里的任何异常都发生在 pywebview 的回调线程里，
    界面上完全看不到（表现就是"登录完了窗口却不关"），必须靠单测兜住。
    """
    header = _cookies_to_header(cookies)
    if not header or header == last_header:
        return False, (header or last_header), ""
    if not _has_key_cookies(header):
        return False, header, ""
    ok, msg = _verify(header)
    return bool(ok), header, msg


def run_webview_login(url: str = QUARK_HOME_URL, timeout: int = _LOGIN_TIMEOUT) -> dict:
    """弹出浏览器窗口让用户登录，返回 {"ok": bool, "header": str, "msg": str}。

    说明：webview.start() 会阻塞调用线程直到窗口关闭，所以本函数必须在主线程
    调用（此时 Qt 的登录对话框尚未弹出，界面不会被卡住）。
    """
    import webview

    state = {"ok": False, "header": "", "msg": "", "error": ""}
    win = webview.create_window(
        "登录夸克网盘 —— 登录成功后本窗口会自动关闭", url, width=1020, height=780)

    def _poll(w):
        # 注意：last_header 必须是本函数的局部变量。若放到外层作用域，
        # 这里的赋值会把它变成局部变量、而赋值前又被读取，抛 UnboundLocalError
        # ——异常发生在 pywebview 的回调线程里，界面上看不到任何提示，只会表现为
        # "登录成功了但窗口死活不关"。
        last = ""
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(_POLL_INTERVAL)
            try:
                cookies = w.get_cookies()
            except Exception:  # noqa: BLE001 窗口正在导航时可能取不到
                continue
            try:
                done, header, msg = _evaluate_cookies(cookies, last)
            except Exception as e:  # noqa: BLE001 单次检查失败不能中断整个轮询
                state["error"] = f"检查 Cookie 时出错：{e}"
                continue
            last = header
            if done:
                state.update({"ok": True, "header": header, "msg": msg})
                try:
                    w.destroy()
                except Exception:  # noqa: BLE001
                    pass
                return

    try:
        # private_mode=True：Cookie 不落盘，保证每次打开都是干净的登录页，
        # 不会出现「想切号却还停在旧账号」的情况
        webview.start(_poll, win, gui="edgechromium", private_mode=True)
    except Exception as e:  # noqa: BLE001 系统缺 WebView2 运行时等
        state["error"] = str(e)
    return state


def _open_manual_dialog(parent=None) -> bool:
    """回退路径：手动粘贴 Cookie"""
    try:
        from ui.dialogs import show_quark_cookie_dialog
    except ImportError:
        from dialogs import show_quark_cookie_dialog
    return bool(show_quark_cookie_dialog(parent))


def show_quark_login_dialog(parent=None) -> bool:
    """
    打开夸克登录窗口（扫码 / 手机号 / 账密）。
    :return: True=已获得并保存有效 Cookie；False=用户取消或失败
    """
    if not webview_available():
        return _open_manual_dialog(parent)

    state = run_webview_login()

    if state["ok"]:
        try:
            from utils.common import save_quark_cookie
            save_quark_cookie(state["header"])
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(
                parent, "登录失败", f"登录已通过验证，但保存 Cookie 失败：{e}")
            return False
        if parent is not None:
            QMessageBox.information(
                parent, "登录成功",
                f"已登录并保存夸克账号：{state['msg'] or '夸克用户'}")
        return True

    # 自动登录没走完：给出明确的回退入口，不让用户卡住
    detail = state.get("error") or "窗口已关闭或登录未完成"
    if parent is None:
        return False
    reply = QMessageBox.question(
        parent, "登录未完成",
        f"没能自动完成登录（{detail}）。\n\n"
        "要改用「手动粘贴 Cookie」的方式登录吗？",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
    if reply != QMessageBox.Yes:
        return False
    return _open_manual_dialog(parent)
