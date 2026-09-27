# -*- coding: utf-8 -*-
"""版本门禁：只认 globalgamemanagers（位于 hollow_knight_Data/ 下）。

Modding API 注入**只改** Assembly-CSharp.dll、绝不碰 globalgamemanagers，所以后者是
「随游戏版本变化、又不被任何 Mod 改动」的最稳指纹。装了 Mod/API 的游戏必须照常放行，
只有游戏本体不是 1.5.78 时才拦。Assembly-CSharp.dll 的哈希不再参与判定（它装完 API
后就不是原版哈希了），也不再写任何 .v/.m 备份。
"""
import hashlib
import os
import shutil
import tempfile
import unittest
from unittest import mock

from core import game_version as gv


# 用作「1.5.78」的次级文件内容（测试时用 mock 把它的哈希塞进已知表）
SECONDARY_OK = b"real 1.5.78 globalgamemanagers"
SECONDARY_WRONG = b"this is some other version's globalgamemanagers"


class GameVersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.managed = os.path.join(self.tmp, "Managed")
        os.makedirs(self.managed)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self):
        return mock.patch.object(gv, "get_managed_dir", return_value=self.managed)

    def _write_secondary(self, data):
        p = os.path.join(self.tmp, gv.SECONDARY_FILE)
        with open(p, "wb") as f:
            f.write(data)
        return hashlib.sha256(data).hexdigest()

    def test_secondary_ok_passes(self):
        sec_hash = self._write_secondary(SECONDARY_OK)
        with self._ctx(), mock.patch.dict(gv.KNOWN_SECONDARY_SHA256, {sec_hash: "1.5.78.11833"}):
            r = gv.check_game_version(self.tmp)
        self.assertTrue(r["ok"], r["message"])
        self.assertEqual(r["version"], "1.5.78.11833")

    def test_secondary_absent_rejected(self):
        with self._ctx():
            r = gv.check_game_version(self.tmp)
        self.assertFalse(r["ok"])
        self.assertIn("globalgamemanagers", r["detail"])

    def test_secondary_mismatch_rejected(self):
        self._write_secondary(SECONDARY_WRONG)
        with self._ctx(), mock.patch.dict(gv.KNOWN_SECONDARY_SHA256, {}):
            r = gv.check_game_version(self.tmp)
        self.assertFalse(r["ok"])
        self.assertIn("校验不通过", r["message"])
        self.assertIn("1.5.78.11833", r["message"])

    def test_modded_dll_ignored_still_passes(self):
        """装了 API 后 dll 变成模组版，但只要 globalgamemanagers 命中 1.5.78 就放行。"""
        with open(os.path.join(self.managed, "Assembly-CSharp.dll"), "wb") as f:
            f.write(b"ModHooks-injected")
        sec_hash = self._write_secondary(SECONDARY_OK)
        with self._ctx(), mock.patch.dict(gv.KNOWN_SECONDARY_SHA256, {sec_hash: "1.5.78.11833"}):
            r = gv.check_game_version(self.tmp)
        self.assertTrue(r["ok"], "装了 Mod 的 1.5.78 必须放行（Mod 不改版本）")

    def test_result_has_expected_keys(self):
        sec_hash = self._write_secondary(SECONDARY_OK)
        with self._ctx(), mock.patch.dict(gv.KNOWN_SECONDARY_SHA256, {sec_hash: "1.5.78.11833"}):
            r = gv.check_game_version(self.tmp)
        for k in ("ok", "version", "sha256", "message", "detail"):
            self.assertIn(k, r)
        # 不再携带 no_vanilla_backup 字段（备份机制已移除）
        self.assertNotIn("no_vanilla_backup", r)


class SecondaryFileSanity(unittest.TestCase):
    def setUp(self):
        self.gv = gv

    def test_secondary_is_globalgamemanagers_not_assets(self):
        self.assertEqual(self.gv.SECONDARY_FILE, "globalgamemanagers")
        self.assertNotIn("assets", self.gv.SECONDARY_FILE)

    def test_secondary_hash_points_to_1_5_78(self):
        self.assertTrue(self.gv.KNOWN_SECONDARY_SHA256, "必须填入 1.5.78 的实测哈希")
        for ver in self.gv.KNOWN_SECONDARY_SHA256.values():
            self.assertEqual(ver, "1.5.78.11833")


if __name__ == "__main__":
    unittest.main()
