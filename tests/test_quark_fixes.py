# -*- coding: utf-8 -*-
"""夸克切号 / 412 相关修复的回归测试（不触网、不弹 UI）。"""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class CookieIdentityTests(unittest.TestCase):
    def test_pan_quark_cn_is_accepted(self):
        from core.quark import is_quark_cookie_domain
        self.assertTrue(is_quark_cookie_domain("pan.quark.cn"))
        self.assertTrue(is_quark_cookie_domain(".quark.cn"))
        self.assertTrue(is_quark_cookie_domain("quark.cn"))
        self.assertTrue(is_quark_cookie_domain(""))
        self.assertFalse(is_quark_cookie_domain("example.com"))

    def test_identity_distinguishes_accounts(self):
        from core.quark import cookie_login_identity
        a = "__pus=aaa; __puus=bbb; other=1"
        b = "__pus=ccc; __puus=ddd; other=1"
        self.assertEqual(cookie_login_identity(a), ("aaa", "bbb"))
        self.assertNotEqual(cookie_login_identity(a), cookie_login_identity(b))


    def test_identity_ignores_rotating_session_token(self):
        """__puus/ctoken 会被服务端轮换，换完仍是同一个账号。"""
        from core.quark import same_login_account
        a = "__pus=aaa; __puus=bbb; ctoken=111"
        a_rotated = "__pus=aaa; __puus=zzz; ctoken=999"
        other = "__pus=ccc; __puus=bbb"
        self.assertTrue(same_login_account(a, a_rotated))
        self.assertFalse(same_login_account(a, other))
        self.assertFalse(same_login_account("", a))
        self.assertFalse(same_login_account("__puus=bbb", "__puus=bbb"))


class SessionRefreshTests(unittest.TestCase):
    def test_refresh_merges_set_cookie_and_updates_header(self):
        from core.quark import QuarkClient

        class _RawHeaders:
            @staticmethod
            def getlist(name):  # noqa: ARG004
                return ["__puus=NEWVALUE; Max-Age=604800; Domain=.quark.cn; Path=/",
                        "ctoken=NEWCT; Path=/",
                        "deleted=; Max-Age=0; Path=/"]

        class _Resp:
            raw = type("R", (), {"headers": _RawHeaders})()

        client = QuarkClient(cookie_str="__pus=a; __puus=OLD; ctoken=OLDC",
                             verify_login=False)
        client._session_refreshed = False
        with mock.patch.object(client.session, "get", return_value=_Resp()):
            changed = client.refresh_session_cookie(persist=False)

        self.assertTrue(changed)
        self.assertIn("__puus=NEWVALUE", client.cookies)
        self.assertNotIn("__puus=OLD", client.cookies)
        self.assertIn("ctoken=NEWCT", client.cookies)
        self.assertIn("__pus=a", client.cookies)
        # 空值 = 删除指令，不能写进来
        self.assertNotIn("deleted", client.cookies)
        # base_headers 必须同步，否则后续请求还在用旧令牌
        self.assertEqual(client.base_headers["cookie"], client.cookies)

    def test_refresh_noop_when_nothing_new(self):
        from core.quark import QuarkClient

        class _RawHeaders:
            @staticmethod
            def getlist(name):  # noqa: ARG004
                return []

        class _Resp:
            raw = type("R", (), {"headers": _RawHeaders})()

        client = QuarkClient(cookie_str="__pus=a; __puus=OLD", verify_login=False)
        with mock.patch.object(client.session, "get", return_value=_Resp()):
            self.assertFalse(client.refresh_session_cookie(persist=False))

    def test_ensure_fresh_session_only_once(self):
        from core.quark import QuarkClient
        client = QuarkClient(cookie_str="__pus=a; __puus=OLD", verify_login=False)
        # __init__ 里对 verify_login=True 的客户端已刷过一次，这里重置模拟未刷新
        client._session_refreshed = False
        calls = []
        with mock.patch.object(client, "refresh_session_cookie",
                               side_effect=lambda **kw: calls.append(kw) or True):
            self.assertTrue(client._ensure_fresh_session())
            self.assertFalse(client._ensure_fresh_session())   # 第二次直接跳过
            self.assertTrue(client._ensure_fresh_session(force=True))
        self.assertEqual(len(calls), 2)

    def test_cdn_rejection_is_typed(self):
        from core.quark import QuarkCDNRejected, QuarkError
        e = QuarkCDNRejected(412)
        self.assertIsInstance(e, QuarkError)
        self.assertEqual(e.status, 412)
        self.assertIn("412", str(e))


class DownloadRequestTests(unittest.TestCase):
    def test_cdn_download_has_no_range_and_uses_own_session(self):
        path = os.path.join(ROOT, "core", "quark.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("_CDN_LOCK", src)
        self.assertIn("class _BlockCookies", src)
        self.assertNotIn('headers["range"]', src)
        self.assertIn('os.remove(part_path)', src)
        self.assertIn('with open(part_path, "wb")', src)
        # requests 改为按需取用（_rq()），不能再写死 requests.Session()
        self.assertIn("sess = _rq().Session()", src)

    def test_requests_is_lazy_imported(self):
        """requests 必须延迟导入：它是启动阶段最大的一笔 import 成本。"""
        import subprocess

        path = os.path.join(ROOT, "core", "quark.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("\nimport requests\n", src)
        self.assertIn("def _rq()", src)

        # 真实校验：只 import core.quark，requests 不应被拖进来
        code = ("import sys; sys.path.insert(0, %r); "
                "import core.quark; print('requests' in sys.modules)" % ROOT)
        out = subprocess.run([sys.executable, "-c", code],
                             capture_output=True, text=True)
        self.assertIn("False", out.stdout)

    def test_login_uses_system_webview_not_qtwebengine(self):
        """登录必须用系统 WebView2：QtWebEngine 会给安装包加 210 MB。"""
        path = os.path.join(ROOT, "ui", "quark_login_dialog.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        # 文档里会解释"为什么不用 QtWebEngine"，所以只禁 import，不禁文本
        self.assertNotIn("from PySide6.QtWebEngine", src)
        self.assertNotIn("import QtWebEngine", src)
        self.assertNotIn("QWebEngineView", src)
        # WebView2 的 Cookie 管理器能读回 HttpOnly 的登录令牌，这是本方案的前提
        self.assertIn("get_cookies", src)
        # 身份判定只能按 __pus（__puus 是每次访问网盘都会被轮换的会话令牌）
        self.assertIn("same_login_account", src)

    def test_card_styles_use_object_name_selectors(self):
        """卡片样式必须用 #ObjectName 限定。

        裸写 "QFrame { ... }" 会命中卡片内**所有后代 QFrame**，而 QLabel 正是
        QFrame 的子类——卡片里每一行文字都会被套上一条 1px 边框，表现为
        "每行字都有个很浅的灰框"。同理 QWidget / QLabel 裸选择器也有此风险。
        """
        cases = [
            ("ui/settings_page.py", "#SettingsCard {"),
            ("ui/settings_page.py", "#SettingsNavBar {"),
            ("ui/mod_page.py", "#DetailCard {"),
            ("ui/mod_page.py", "#DetailTitleCard {"),
        ]
        for rel, expect in cases:
            with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as f:
                src = f.read()
            self.assertIn(expect, src, f"{rel} 里缺少 {expect} 选择器")

    def test_github_icon_renders(self):
        """详情页的 GitHub 图标：QSvgRenderer 可用且能真的画出东西。"""
        from PySide6.QtWidgets import QApplication

        from ui import mod_page

        app = QApplication.instance() or QApplication([])  # noqa: F841
        self.assertIsNotNone(mod_page.QSvgRenderer,
                             "PySide6.QtSvg 不可用，图标会退化成文字")
        pix = mod_page._render_svg_icon("github", 16)
        self.assertIsNotNone(pix)
        self.assertFalse(pix.isNull(), "GitHub 图标渲染出的是空图")
        self.assertGreater(pix.width(), 0)

    def test_slim_rules_keep_every_pyside6_module_in_use(self):
        """防止瘦身时把代码实际用到的 Qt 模块剔掉。

        曾误删 QtSvg：详情页的 GitHub 图标靠 QSvgRenderer 渲染，缺了它不会报错，
        只是静默退化成文字——这类"不崩但功能没了"的问题必须靠测试兜住。
        """
        import re

        spec = os.path.join(ROOT, "main.spec")
        with open(spec, "r", encoding="utf-8") as f:
            src = f.read()

        # ① main.spec 的白名单
        keep_block = re.search(r"_QT_BINDING_KEEP\s*=\s*\{(.*?)\}", src, re.S)
        self.assertIsNotNone(keep_block, "没找到 _QT_BINDING_KEEP")
        kept = set(re.findall(r"'([a-z0-9]+)'", keep_block.group(1)))

        # ② 项目里真正 import 了哪些 PySide6 模块
        used = set()
        for rel in ("main.py", os.path.join("ui", "mod_page.py"),
                    os.path.join("ui", "main_window.py"),
                    os.path.join("ui", "settings_page.py"),
                    os.path.join("ui", "dialogs.py"),
                    os.path.join("ui", "quark_login_dialog.py"),
                    os.path.join("core", "installer.py"),
                    os.path.join("core", "online_install.py")):
            path = os.path.join(ROOT, rel)
            if not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            used.update(m.lower() for m in
                        re.findall(r"from\s+PySide6\.(\w+)\s+import", text))

        self.assertTrue(used, "没解析到任何 PySide6 模块")
        missing = used - kept
        self.assertFalse(
            missing,
            f"代码用到了 {sorted(missing)}，但 main.spec 的 _QT_BINDING_KEEP 里没有，"
            f"这些模块会被瘦身规则剔除")

        # ③ 用到的模块对应的 Qt 运行时 DLL 也要在白名单里
        dll_block = re.search(r"_QT_DLL_KEEP\s*=\s*\{(.*?)\}", src, re.S)
        self.assertIsNotNone(dll_block)
        dlls = set(re.findall(r"'([a-z0-9]+\.dll)'", dll_block.group(1)))
        self.assertIn("qt6svg.dll", dlls,
                      "Qt6Svg 被剔除会让 GitHub 等矢量图标退化成文字")

    def test_cookies_to_header_keeps_only_quark_domain(self):
        import http.cookies

        from ui.quark_login_dialog import _cookies_to_header

        quark = http.cookies.SimpleCookie()
        quark.load("__pus=abc123; Domain=.quark.cn")
        other = http.cookies.SimpleCookie()
        other.load("tracker=zzz; Domain=.example.com")
        host_only = http.cookies.SimpleCookie()
        host_only.load("b-user-id=uid-1")

        header = _cookies_to_header([quark, other, host_only])
        self.assertIn("__pus=abc123", header)
        self.assertIn("b-user-id=uid-1", header)  # 无 Domain 属性也收
        self.assertNotIn("tracker=zzz", header)

    def test_key_cookie_detection(self):
        from ui.quark_login_dialog import _has_key_cookies
        self.assertTrue(_has_key_cookies("__pus=a; __puus=b; other=c"))
        self.assertFalse(_has_key_cookies("__pus=a; other=c"))
        self.assertFalse(_has_key_cookies(""))

    def test_evaluate_cookies_detects_login(self):
        """拿到 __pus+__puus 且验证通过 -> 判定登录完成"""
        import http.cookies

        from ui import quark_login_dialog as d

        ck = http.cookies.SimpleCookie()
        ck.load("__pus=aaa; Domain=.quark.cn")
        ck2 = http.cookies.SimpleCookie()
        ck2.load("__puus=bbb; Domain=.quark.cn")

        with mock.patch.object(d, "_verify", return_value=(True, "测试用户")):
            done, header, msg = d._evaluate_cookies([ck, ck2], "")
        self.assertTrue(done)
        self.assertIn("__pus=aaa", header)
        self.assertEqual(msg, "测试用户")

        # 同一份 header 不重复验证（避免每次轮询都打网络请求）
        with mock.patch.object(d, "_verify", return_value=(True, "x")) as v:
            done2, _, _ = d._evaluate_cookies([ck, ck2], header)
        self.assertFalse(done2)
        v.assert_not_called()

        # 没登录（缺 __puus）时不应判定成功
        with mock.patch.object(d, "_verify", return_value=(True, "x")) as v2:
            done3, _, _ = d._evaluate_cookies([ck], "")
        self.assertFalse(done3)
        v2.assert_not_called()

    def test_login_window_closes_itself_when_logged_in(self):
        """登录成功后必须自动关窗：轮询线程里任何异常都会让这一步静默失效。"""
        import http.cookies

        from ui import quark_login_dialog as d

        ck = http.cookies.SimpleCookie()
        ck.load("__pus=aaa; __puus=bbb; Domain=.quark.cn")

        class _FakeWindow:
            def __init__(self):
                self.destroyed = False

            def get_cookies(self):
                return [ck]

            def destroy(self):
                self.destroyed = True

        fake_win = _FakeWindow()

        class _FakeWebview:
            @staticmethod
            def create_window(*_a, **_kw):
                return fake_win

            @staticmethod
            def start(func, win, **_kw):
                func(win)          # 同步跑一次轮询，模拟"上来就已登录"

        with mock.patch.dict(sys.modules, {"webview": _FakeWebview}):
            with mock.patch.object(d, "_verify", return_value=(True, "测试用户")):
                with mock.patch.object(d, "_POLL_INTERVAL", 0):
                    state = d.run_webview_login()

        self.assertTrue(state["ok"], msg=f"轮询未检出登录：{state}")
        self.assertEqual(state["msg"], "测试用户")
        self.assertTrue(fake_win.destroyed, "登录成功后窗口没有被关闭")


class ParallelDefaultTests(unittest.TestCase):
    def test_legacy_default_8_migrates_to_1(self):
        from utils import common as common_mod

        cfg = {"parallel_downloads": 8}
        with mock.patch.object(common_mod, "_read_config", lambda: dict(cfg)):
            saved = {}

            def _write(data):
                saved.update(data)
                cfg.update(data)
                return True

            with mock.patch.object(common_mod, "_write_config", _write):
                self.assertEqual(common_mod.load_parallel_downloads(), 1)
                self.assertEqual(saved.get("parallel_downloads"), 1)

    def test_user_set_8_is_kept(self):
        from utils import common as common_mod

        cfg = {"parallel_downloads": 8, "parallel_downloads_user_set": True}
        with mock.patch.object(common_mod, "_read_config", lambda: dict(cfg)):
            self.assertEqual(common_mod.load_parallel_downloads(), 8)

    def test_default_without_key_is_1(self):
        from utils import common as common_mod

        with mock.patch.object(common_mod, "_read_config", lambda: {}):
            self.assertEqual(common_mod.load_parallel_downloads(), 1)


if __name__ == "__main__":
    unittest.main()
