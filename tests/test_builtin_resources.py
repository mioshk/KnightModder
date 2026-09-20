# -*- coding: utf-8 -*-
"""内置离线资源（1.5.78 原版 dll / Modding API 包）的测试：

安装 / 还原优先使用随软件打包的内置文件，无需联网、也不走夸克网盘下载。
"""
import hashlib
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import installer
from core.game_version import KNOWN_VANILLA_DLL
from utils.common import get_builtin_path


class BuiltinApiPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake_zip(self, name="api.zip"):
        path = os.path.join(self.tmp, name)
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("Assembly-CSharp.dll", b"ModHooks-injected")
        return path

    def test_resolve_prefers_builtin_and_skips_network(self):
        """内置包存在时直接返回它，且不触发线上清单（get_package）"""
        fake_zip = self._fake_zip()
        with mock.patch.object(installer, "get_builtin_path", return_value=fake_zip), \
             mock.patch.object(installer, "get_package") as m_pkg:
            got = installer._resolve_api_package(lambda *a: None, None)
        self.assertEqual(got, fake_zip)
        m_pkg.assert_not_called()

    def test_resolve_falls_back_when_builtin_absent(self):
        """内置包缺失时退回清单/下载流程（此处只验证确实去调了 get_package）"""
        with mock.patch.object(installer, "get_builtin_path", return_value=""), \
             mock.patch.object(installer, "get_package", return_value=None) as m_pkg:
            with self.assertRaises(RuntimeError):
                installer._resolve_api_package(lambda *a: None, None)
        m_pkg.assert_called_once()


class BuiltinVanillaBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.managed = os.path.join(self.tmp, "Managed")
        os.makedirs(self.managed)
        self.cur, self.van, self.mod = installer._api_paths(self.managed)
        # 让 install_api / restore_vanilla 把 game_path 映射到我们的临时 Managed
        self._mgmt = mock.patch.object(installer, "get_managed_dir",
                                       return_value=self.managed)
        self._mgmt.start()
        self.addCleanup(self._mgmt.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _patch_version(self, ok):
        return mock.patch(
            "core.game_version.check_game_version",
            return_value={"ok": ok, "version": "1.5.78.11833" if ok else "",
                          "message": "ok" if ok else "版本不符"})

    def test_restore_uses_builtin_when_vanilla_missing(self):
        """当前是模组版且缺 .v：应用内置 1.5.78 原版 dll 离线还原"""
        with open(self.cur, "wb") as f:
            f.write(b"ModHooks-injected")  # 模组版
        fake_vanilla = os.path.join(self.tmp, "vanilla.dll")
        with open(fake_vanilla, "wb") as f:
            f.write(b"vanilla-original")

        with self._patch_version(True), \
             mock.patch.object(installer, "get_builtin_path", return_value=fake_vanilla):
            result = installer.restore_vanilla(self.tmp)

        self.assertTrue(result["ok"])
        self.assertTrue(os.path.isfile(self.van), "内置原版应被补为 .v")
        with open(self.van, "rb") as f:
            self.assertEqual(f.read(), b"vanilla-original")
        self.assertFalse(installer._is_modded_dll(self.cur), "还原后当前 dll 必须是原版")

    def test_restore_rejects_non_1_5_78_even_with_builtin(self):
        """非 1.5.78：即便内置原版存在也不能用（内置只针对 1.5.78）"""
        with open(self.cur, "wb") as f:
            f.write(b"ModHooks-injected")
        fake_vanilla = os.path.join(self.tmp, "vanilla.dll")
        with open(fake_vanilla, "wb") as f:
            f.write(b"vanilla-original")

        with self._patch_version(False), \
             mock.patch.object(installer, "get_builtin_path", return_value=fake_vanilla):
            result = installer.restore_vanilla(self.tmp)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "no_vanilla_backup")
        self.assertFalse(os.path.isfile(self.van), "非 1.5.78 不应写入内置原版")


class BuiltinResourcesCommittedTests(unittest.TestCase):
    """锁定随仓库提交的内置资源：必须存在、且原版 dll 确实就是 1.5.78 指纹。"""

    def test_builtin_files_present_and_vanilla_is_genuine(self):
        base = os.path.join(ROOT, "assets", "builtin")
        api_zip = os.path.join(base, installer.BUILTIN_API_ZIP)
        vanilla = os.path.join(base, installer.BUILTIN_VANILLA_DLL)

        self.assertTrue(os.path.isfile(api_zip), "内置 API 包必须随仓库提交")
        self.assertTrue(zipfile.is_zipfile(api_zip), "内置 API 包必须是合法 zip")
        self.assertTrue(os.path.isfile(vanilla), "内置 1.5.78 原版 dll 必须随仓库提交")

        h = hashlib.sha256(open(vanilla, "rb").read()).hexdigest()
        self.assertIn(h, KNOWN_VANILLA_DLL,
                      "内置原版 dll 必须与游戏版本指纹表里的 1.5.78 一致")


if __name__ == "__main__":
    unittest.main()
