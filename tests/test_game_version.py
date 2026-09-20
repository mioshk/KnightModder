# -*- coding: utf-8 -*-
"""游戏版本校验的测试：只放行 1.5.78（原版 Assembly-CSharp.dll 的哈希）。

判定必须用**原版**那份 dll：装上 Modding API 后当前 dll 会被注入版替换，
所以要优先看 .v 备份。

唯一例外：用户**手动覆盖** Assembly-CSharp.dll 装了 API（没用本工具），
此时当前 dll 已是注入版、且无 .v 原版备份。但被注入的 dll 只能来自 1.5.78
（Modding API 只针对这一版发布），所以仍放行，只是标记缺原版备份。

另用**第二判定文件**（Unity 内部元数据 globalgamemanagers）交叉确认版本：它和游戏内容
（sharedassets*/resources.assets/level*）是两码事，资源替换类 Mod 和 Modding API 注入
都绝不碰它，所以是最稳的「随版本变化、又不被 Mod 改动」的确认源。它只作确认、不匹配
也不拦截，退回 dll 自身的判断。
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

    def test_modded_without_backup_passes(self):
        """模组版 + 没有 .v：手动覆盖装 API 的用户。

        被注入 Modding API 的 dll 只能来自 1.5.78（API 只针对这一版发布），
        所以应放行；但必须标记缺原版备份（离线还原需要它）。
        """
        self._write(self.cur, MODDED)
        with self._ctx(), mock.patch.dict(self.gv.KNOWN_VANILLA_DLL, self._known()):
            r = self.gv.check_game_version(self.tmp)
        self.assertTrue(r["ok"], r["message"])
        self.assertTrue(r["no_vanilla_backup"], "应标记缺原版备份")
        self.assertIn("Modding API", r["message"])
        self.assertIn("1.5.78.11833", r["message"])
        self.assertTrue(r["detail"], "放行也要给出完整说明（tooltip/日志）")

    def test_missing_dll_rejected(self):
        with self._ctx():
            r = self.gv.check_game_version(self.tmp)
        self.assertFalse(r["ok"])
        self.assertIn("未找到", r["message"])

    # ---- 第二判定文件（资源包）交叉验证 ----

    def _write_secondary(self, data):
        p = os.path.join(self.tmp, self.gv.SECONDARY_FILE)
        with open(p, "wb") as f:
            f.write(data)
        return hashlib.sha256(data).hexdigest()

    def test_secondary_confirms_uncataloged_vanilla(self):
        """资源包命中 1.5.78，且 dll 是原版但不在已知表 -> 应放行。

        覆盖「确属 1.5.78 但 dll 哈希没被收录」的发行版。
        """
        self._write(self.cur, b"uncataloged but genuinely 1.5.78 vanilla")
        sec_hash = self._write_secondary(b"real 1.5.78 asset bundle")
        with self._ctx(), \
             mock.patch.dict(self.gv.KNOWN_VANILLA_DLL, {}), \
             mock.patch.dict(self.gv.KNOWN_SECONDARY_SHA256, {sec_hash: "1.5.78.11833"}):
            r = self.gv.check_game_version(self.tmp)
        self.assertTrue(r["ok"], r["message"])
        self.assertEqual(r["version"], "1.5.78.11833")
        self.assertIn("1.5.78.11833", r["message"])

    def test_secondary_confirms_modded_without_backup(self):
        """资源包命中 1.5.78，且当前 dll 是 Mod 版（手动覆盖装 API）-> 应放行。"""
        self._write(self.cur, MODDED)
        sec_hash = self._write_secondary(b"real 1.5.78 asset bundle")
        with self._ctx(), \
             mock.patch.dict(self.gv.KNOWN_VANILLA_DLL, self._known()), \
             mock.patch.dict(self.gv.KNOWN_SECONDARY_SHA256, {sec_hash: "1.5.78.11833"}):
            r = self.gv.check_game_version(self.tmp)
        self.assertTrue(r["ok"], r["message"])
        self.assertTrue(r["no_vanilla_backup"], "应标记缺原版备份")
        self.assertIn("Modding API", r["message"])

    def test_secondary_mismatch_rejects_wrong_version(self):
        """资源包不符 1.5.78：即便 dll 是原版且不在已知表，也应拒绝。

        覆盖「Steam 升级到别的版本」这类情况，不能靠 dll 推断放行。
        """
        self._write(self.cur, b"some other version dll")
        self._write_secondary(b"wrong version asset bundle")
        with self._ctx(), \
             mock.patch.dict(self.gv.KNOWN_VANILLA_DLL, {}), \
             mock.patch.dict(self.gv.KNOWN_SECONDARY_SHA256, {}):
            r = self.gv.check_game_version(self.tmp)
        self.assertFalse(r["ok"], "资源包不符必须拒绝")
        self.assertIn("校验不通过", r["message"])

    def test_modded_dll_accepted_regardless_of_secondary(self):
        """当前 dll 是 Mod 版（装了 API / 手动覆盖装 API）：无论资源包如何都应放行。

        装 Mod 不改游戏版本，门禁绝不会因「装了 Mod」而拦截。资源包哪怕缺失或不匹配，
        只要 dll 是 Modding API 注入版（只针对 1.5.78 发布）就确认是 1.5.78。
        """
        self._write(self.cur, MODDED)
        self._write_secondary(b"totally different game asset bundle")  # 资源包不匹配
        with self._ctx(), \
             mock.patch.dict(self.gv.KNOWN_VANILLA_DLL, {}), \
             mock.patch.dict(self.gv.KNOWN_SECONDARY_SHA256, {}):
            r = self.gv.check_game_version(self.tmp)
        self.assertTrue(r["ok"], "装了 Mod 的 1.5.78 必须放行（Mod 不改版本）")
        self.assertTrue(r["no_vanilla_backup"], "应标记缺原版备份")
        self.assertIn("Modding API", r["message"])


class SecondaryFileSanity(unittest.TestCase):
    """锁定第二判定文件必须是「不被任何 Mod 改动」的 Unity 内部文件，而非游戏内容资源包。"""

    def setUp(self):
        import core.game_version as gv
        self.gv = gv

    def test_secondary_is_globalgamemanagers_not_assets(self):
        # 资源替换类 Mod 会改 sharedassets*/resources.assets，绝不能用来做版本指纹
        self.assertEqual(self.gv.SECONDARY_FILE, "globalgamemanagers")
        self.assertNotIn("assets", self.gv.SECONDARY_FILE)

    def test_secondary_hash_points_to_1_5_78(self):
        self.assertTrue(self.gv.KNOWN_SECONDARY_SHA256, "必须填入 1.5.78 的实测哈希")
        for ver in self.gv.KNOWN_SECONDARY_SHA256.values():
            self.assertEqual(ver, "1.5.78.11833")


if __name__ == "__main__":
    unittest.main()
