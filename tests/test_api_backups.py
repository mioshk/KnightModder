# -*- coding: utf-8 -*-
"""安装 / 还原 API 的新模型：不再在 Managed 里写 .v/.m 备份。

安装 = 把内置 Modding API 包解压进 Managed；还原 = 把内置 1.5.78 原版 dll 复制回
Assembly-CSharp.dll。两者都只依赖随软件分发的内置资源，切换靠「重新解压 / 复制原版」，
不需要任何本地备份文件，来回切换多少次都不会消耗或误删备份。
"""
import contextlib
import os
import shutil
import tempfile
import unittest
import zipfile
from unittest import mock

from core import installer


class ApiNoBackupTests(unittest.TestCase):
    def setUp(self):
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
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(installer, "get_managed_dir",
                                              return_value=self.managed))
        stack.enter_context(mock.patch(
            "core.game_version.check_game_version",
            return_value={"ok": True, "version": "1.5.78.11833",
                          "sha256": "fake", "message": "ok"}))
        return stack

    def _fake_api_zip(self):
        path = os.path.join(self.tmp, "api.zip")
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("Assembly-CSharp.dll", b"ModHooks-injected")
            zf.writestr("MMHOOK_Assembly-CSharp.dll", b"hook")
        return path

    def test_install_creates_no_backup_files(self):
        self._put(self.cur, modded=False)
        zip_path = self._fake_api_zip()
        with self._ctx(), mock.patch.object(installer, "_resolve_api_package",
                                            return_value=zip_path):
            installer.install_api(self.tmp)
        self.assertTrue(installer._is_modded_dll(self.cur), "安装后应是模组版")
        self.assertFalse(os.path.isfile(self.van), "不应写 .v 备份")
        self.assertFalse(os.path.isfile(self.mod), "不应写 .m 备份")

    def test_restore_uses_builtin_vanilla_and_no_backup(self):
        self._put(self.cur, modded=True)
        # 还原直接用随软件分发的内置原版 dll（仓库里确有此文件）
        with self._ctx():
            result = installer.restore_vanilla(self.tmp)
        self.assertTrue(result["ok"])
        self.assertFalse(installer._is_modded_dll(self.cur), "还原后应是原版")
        self.assertFalse(os.path.isfile(self.van), "不应写 .v 备份")
        self.assertFalse(os.path.isfile(self.mod), "不应写 .m 备份")

    def test_toggling_repeatedly_without_backup(self):
        zip_path = self._fake_api_zip()
        with self._ctx(), \
             mock.patch.object(installer, "_resolve_api_package", return_value=zip_path):
            for _ in range(3):
                installer.install_api(self.tmp)
                self.assertTrue(installer._is_modded_dll(self.cur), "安装后应是模组版")
                r = installer.restore_vanilla(self.tmp)
                self.assertTrue(r["ok"], "还原应成功（无备份也不影响）")
                self.assertFalse(installer._is_modded_dll(self.cur), "还原后应是原版")

    def test_restore_already_vanilla_is_noop(self):
        self._put(self.cur, modded=False)
        with self._ctx():
            result = installer.restore_vanilla(self.tmp)
        self.assertTrue(result["ok"])
        self.assertTrue(result["already_vanilla"])


if __name__ == "__main__":
    unittest.main()
