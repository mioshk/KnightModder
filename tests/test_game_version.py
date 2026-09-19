# -*- coding: utf-8 -*-
"""游戏版本校验的测试：只放行 1.5.78（原版 Assembly-CSharp.dll 的哈希）。

判定必须用**原版**那份 dll：装上 Modding API 后当前 dll 会被注入版替换，
所以要优先看 .v 备份。
"""
import hashlib
import os
import shutil
import tempfile
import unittest
from unittest import mock

VANILLA = b"vanilla assembly bytes for 1.5.78"
MODDED = b"ModHooks injected " + VANILLA


class GameVersionTests(unittest.TestCase):
    def setUp(self):
        from core import game_version as gv
        self.gv = gv
        self.tmp = tempfile.mkdtemp()
        self.managed = os.path.join(self.tmp, "Managed")
        os.makedirs(self.managed)
        self.cur, self.van, self.mod = gv._api_paths(self.managed)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _write(path, data):
        with open(path, "wb") as f:
            f.write(data)

    def _ctx(self):
        return mock.patch.object(self.gv, "get_managed_dir", return_value=self.managed)

    def _known(self):
        return {hashlib.sha256(VANILLA).hexdigest(): "1.5.78.11833"}

    def test_known_vanilla_passes(self):
        self._write(self.cur, VANILLA)
        with self._ctx(), mock.patch.dict(self.gv.KNOWN_VANILLA_DLL, self._known()):
            r = self.gv.check_game_version(self.tmp)
        self.assertTrue(r["ok"], r["message"])
        self.assertEqual(r["version"], "1.5.78.11833")
        self.assertEqual(r["sha256"], hashlib.sha256(VANILLA).hexdigest())

    def test_unknown_hash_rejected(self):
        self._write(self.cur, b"some other version dll")
        with self._ctx(), mock.patch.dict(self.gv.KNOWN_VANILLA_DLL, self._known()):
            r = self.gv.check_game_version(self.tmp)
        self.assertFalse(r["ok"])
        self.assertIn("校验不通过", r["message"])
        self.assertIn("1.5.78.11833", r["message"], "要写清期望的完整版本号")
        self.assertTrue(r["sha256"], "指纹留在返回值里，方便登记新版本")

    def test_vanilla_backup_used_when_current_is_modded(self):
        """装了 API 后当前 dll 是模组版，应改用 .v 原版备份判定"""
        self._write(self.cur, MODDED)
        self._write(self.van, VANILLA)
        with self._ctx(), mock.patch.dict(self.gv.KNOWN_VANILLA_DLL, self._known()):
            r = self.gv.check_game_version(self.tmp)
        self.assertTrue(r["ok"], r["message"])

    def test_current_dll_wins_over_stale_backup(self):
        """游戏被升级后：当前 dll 已是新版原版，.v 还留着旧版 1.5.78。

        这是最容易搞反的一处——若优先看 .v，会把升级后的游戏误判成合规放行。
        """
        self._write(self.cur, b"upgraded game dll, not 1.5.78 anymore")
        self._write(self.van, VANILLA)   # 旧备份仍是 1.5.78
        with self._ctx(), mock.patch.dict(self.gv.KNOWN_VANILLA_DLL, self._known()):
            r = self.gv.check_game_version(self.tmp)
        self.assertFalse(r["ok"], "应以当前 dll 为准，不能被旧备份放行")

    def test_modded_without_backup_rejected(self):
        """模组版 + 没有 .v：无从判断原版是哪个版本，必须拒绝而不是放行"""
        self._write(self.cur, MODDED)
        with self._ctx(), mock.patch.dict(self.gv.KNOWN_VANILLA_DLL, self._known()):
            r = self.gv.check_game_version(self.tmp)
        self.assertFalse(r["ok"])
        self.assertIn("还原原版", r["message"])

    def test_missing_dll_rejected(self):
        with self._ctx():
            r = self.gv.check_game_version(self.tmp)
        self.assertFalse(r["ok"])
        self.assertIn("未找到", r["message"])


if __name__ == "__main__":
    unittest.main()
