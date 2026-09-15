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
