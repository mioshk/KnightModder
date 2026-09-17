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
        self.assertIn("sess = requests.Session()", src)

    def test_login_dialog_refreshes_cookies_and_rejects_same_account(self):
        path = os.path.join(ROOT, "ui", "quark_login_dialog.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("loadAllCookies", src)
        self.assertIn("_is_same_saved_account", src)
        self.assertIn("cookieRemoved", src)
        self.assertIn("NoPersistentCookies", src)
        self.assertNotIn("quark.cn\" not in domain", src)


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
