# -*- coding: utf-8 -*-
"""安装器「自动找到已安装位置」的单元测试。

这段逻辑踩过两次坑，必须有测试兜着：
  1. 只信注册表 InstallLocation —— 那条记录会被任意一次安装覆盖（包括装到
     临时目录做测试），指向的目录还可能已被删除，于是用户明明装过却每次都得
     手动再选一遍路径；
  2. 靠 GetLogicalDriveStrings 枚举盘符 —— 实测它在某些环境里只返回系统盘，
     装在 D 盘的程序就永远找不到。
"""
import os
import shutil
import tempfile
import unittest
from unittest import mock


def _mk_install(parent, exe_name="KnightModder.exe"):
    """造一个"装着 KnightModder"的目录"""
    d = tempfile.mkdtemp(dir=parent)
    with open(os.path.join(d, exe_name), "w") as f:
        f.write("fake")
    return d


class InstallDirDetectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_main_exe_prefers_plain_name(self):
        from installer import _main_exe_in
        d = _mk_install(self._tmp)
        with open(os.path.join(d, "KnightModder v1.4.2.exe"), "w") as f:
            f.write("fake")
        self.assertEqual(os.path.basename(_main_exe_in(d)), "KnightModder.exe")

    def test_empty_or_missing_dir_is_not_an_install(self):
        from installer import _looks_like_install
        self.assertFalse(_looks_like_install(""))
        self.assertFalse(_looks_like_install(None))
        self.assertFalse(_looks_like_install(tempfile.mkdtemp(dir=self._tmp)))
        self.assertFalse(_looks_like_install(
            os.path.join(self._tmp, "no", "such", "dir")))

    def test_skips_candidates_without_program(self):
        """注册表指向的目录早已被删掉时，必须跳过而不是直接采用"""
        from installer import last_install_dir
        real = _mk_install(self._tmp)
        gone = os.path.join(self._tmp, "deleted-install")
        with mock.patch("installer._install_candidates",
                        return_value=[gone, real]):
            self.assertEqual(last_install_dir(), os.path.normpath(real))

    def test_picks_newest_when_several_installed(self):
        """同时装着旧版和新版时，要选在用的那份（否则会"升级"到更老的版本）"""
        from installer import last_install_dir
        old = _mk_install(self._tmp, "KnightModder v1.4.2.exe")
        new = _mk_install(self._tmp)
        os.utime(os.path.join(old, "KnightModder v1.4.2.exe"), (1, 1))
        with mock.patch("installer._install_candidates",
                        return_value=[old, new]):
            self.assertEqual(last_install_dir(), os.path.normpath(new))
        with mock.patch("installer._install_candidates",
                        return_value=[new, old]):
            self.assertEqual(last_install_dir(), os.path.normpath(new))

    def test_falls_back_to_default(self):
        from installer import default_install_dir, last_install_dir
        with mock.patch("installer._install_candidates", return_value=[]):
            self.assertEqual(last_install_dir(), default_install_dir())

    def test_candidate_drives_excludes_a_and_b(self):
        """A/B 是软驱，试探它们会让安装向导白等"""
        from installer import _candidate_drives
        drives = [d.lower() for d in _candidate_drives()]
        self.assertNotIn("a:\\", drives)
        self.assertNotIn("b:\\", drives)
        self.assertTrue(all(len(d) == 3 and d.endswith(":\\") for d in drives))


if __name__ == "__main__":
    unittest.main()
