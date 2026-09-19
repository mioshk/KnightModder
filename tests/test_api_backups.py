# -*- coding: utf-8 -*-
"""API 两份备份（.v 原版 / .m 模组版）必须常驻。

早先实现是"互换"（shutil.move）：启用后 .m 被移走、还原后 .v 被移走，任何时刻
都只剩一份备份，用户误删一个文件就得重新下载 API。现在切换一律走复制，两份必须
始终都在。
"""
import contextlib
import os
import shutil
import tempfile
import unittest
import zipfile
from unittest import mock


class ApiBackupPersistenceTests(unittest.TestCase):
    def setUp(self):
        from core import installer
        self.installer = installer
        self.tmp = tempfile.mkdtemp()
        self.managed = os.path.join(self.tmp, "Managed")
        os.makedirs(self.managed)
        self.cur, self.van, self.mod = installer._api_paths(self.managed)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _put(self, path, modded):
        with open(path, "wb") as f:
            f.write(b"ModHooks-injected" if modded else b"vanilla-original")
        return path

    def _ctx(self):
        """切到临时 Managed 目录，并放行游戏版本校验。

        本文件的用例只关心 .v / .m 两份备份的行为；版本门禁（原版 dll 哈希）
        交给 tests/test_game_version.py 单独覆盖，这里直接放行，免得每次都要
        在临时目录里造一份哈希登记过的 dll。
        """
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(self.installer, "get_managed_dir",
                                              return_value=self.managed))
        stack.enter_context(mock.patch(
            "core.game_version.check_game_version",
            return_value={"ok": True, "version": "1.5.78.11833",
                          "sha256": "fake", "message": "ok"}))
        return stack

    def test_fresh_install_creates_both(self):
        self._put(self.cur, modded=False)
        zip_path = os.path.join(self.tmp, "api.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(os.path.basename(self.cur), b"ModHooks-injected")
        with self._ctx(), mock.patch.object(self.installer, "_resolve_api_package",
                                            return_value=zip_path):
            self.installer.install_api(self.tmp)
        self.assertTrue(os.path.isfile(self.van), "全新安装后 .v 必须存在")
        self.assertTrue(os.path.isfile(self.mod), "全新安装后 .m 必须存在")
        self.assertTrue(self.installer._is_modded_dll(self.cur))

    def test_enable_keeps_mod_backup(self):
        """已装被关 → 启用：.m 不能被 move 掉"""
        self._put(self.cur, modded=False)
        self._put(self.mod, modded=True)
        with self._ctx():
            state = self.installer.install_api(self.tmp)
        self.assertTrue(state["enabled"])
        self.assertTrue(os.path.isfile(self.van), "启用后 .v 必须存在")
        self.assertTrue(os.path.isfile(self.mod), "启用后 .m 必须保留")

    def test_restore_keeps_vanilla_backup(self):
        """启用 → 还原：.v 不能被 move 掉"""
        self._put(self.cur, modded=True)
        self._put(self.van, modded=False)
        with self._ctx():
            result = self.installer.restore_vanilla(self.tmp)
        self.assertTrue(result["ok"])
        self.assertTrue(os.path.isfile(self.van), "还原后 .v 必须保留")
        self.assertTrue(os.path.isfile(self.mod), "还原后 .m 必须存在")
        self.assertFalse(self.installer._is_modded_dll(self.cur))

    def test_toggling_repeatedly_keeps_both(self):
        """来回切换多轮，两份备份始终都在"""
        self._put(self.cur, modded=False)
        self._put(self.mod, modded=True)
        with self._ctx():
            for _ in range(3):
                self.installer.install_api(self.tmp)
                self.assertTrue(os.path.isfile(self.van), "启用后 .v 丢了")
                self.assertTrue(os.path.isfile(self.mod), "启用后 .m 丢了")
                self.installer.restore_vanilla(self.tmp)
                self.assertTrue(os.path.isfile(self.van), "还原后 .v 丢了")
                self.assertTrue(os.path.isfile(self.mod), "还原后 .m 丢了")


if __name__ == "__main__":
    unittest.main()
