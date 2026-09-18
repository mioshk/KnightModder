# -*- coding: utf-8 -*-
"""下载缓存目录的单元测试。

覆盖设置页「更改路径」背后的逻辑：自定义路径优先、没设置时回退到软件目录下的
downloads、以及"选回默认目录要清掉自定义项"这条容易写错的规则。
"""
import os
import unittest
from unittest import mock


class DownloadDirTests(unittest.TestCase):
    @staticmethod
    def _common():
        from utils import common
        return common

    def test_custom_dir_takes_priority(self):
        common = self._common()
        with mock.patch.object(common, "load_app_setting",
                               return_value=r"D:\Mods\cache"):
            self.assertEqual(common.get_download_dir(),
                             os.path.normpath(r"D:\Mods\cache"))

    def test_falls_back_to_bundled_downloads(self):
        common = self._common()
        with mock.patch.object(common, "load_app_setting", return_value=""):
            expect = os.path.join(common.get_base_dir(), common.DOWNLOAD_DIR_NAME)
            self.assertEqual(common.get_download_dir(), expect)

    def test_blank_setting_falls_back(self):
        common = self._common()
        for blank in (None, "", "   "):
            with mock.patch.object(common, "load_app_setting", return_value=blank):
                expect = os.path.join(common.get_base_dir(),
                                      common.DOWNLOAD_DIR_NAME)
                self.assertEqual(common.get_download_dir(), expect)

    def test_set_custom_dir_writes_value(self):
        common = self._common()
        saved = {}
        with mock.patch.object(
                common, "save_app_setting",
                side_effect=lambda k, v: saved.update({k: v}) or True):
            self.assertTrue(common.set_download_dir(r"E:\Games\KMCache"))
        self.assertEqual(saved.get("download_dir"), r"E:\Games\KMCache")

    def test_setting_default_dir_clears_override(self):
        """选回默认目录时必须清掉自定义项，而不是把绝对路径写死。

        否则软件以后换位置（绿色版挪文件夹 / 重装到别的盘），这个记录下来的
        旧绝对路径还会一直生效，用户会发现缓存莫名其妙写到了老地方。
        """
        common = self._common()
        default = os.path.join(common.get_base_dir(), common.DOWNLOAD_DIR_NAME)
        saved = {}
        with mock.patch.object(
                common, "save_app_setting",
                side_effect=lambda k, v: saved.update({k: v}) or True):
            common.set_download_dir(default)
        self.assertEqual(saved.get("download_dir"), "")

    def test_set_empty_resets(self):
        common = self._common()
        saved = {}
        with mock.patch.object(
                common, "save_app_setting",
                side_effect=lambda k, v: saved.update({k: v}) or True):
            common.set_download_dir("")
        self.assertEqual(saved.get("download_dir"), "")


if __name__ == "__main__":
    unittest.main()
