# -*- coding: utf-8 -*-
"""API 安装清单（api_manifest.json）的解析与三级兜底测试。

清单取代了原先写死在 config.py 里的 API 下载地址，所以"读不到清单时还能装
API"这件事必须有测试兜着：线上挂了要用程序自带的，自带的也没有才用内置配置。
"""
import json
import os
import tempfile
import unittest
from unittest import mock


SAMPLE = {
    "version": 78,
    "updated": "2026-10-01",
    "packages": {
        "Windows": {
            "file": "moddingapi.v78.windows.zip",
            "direct_links": ["https://example.com/api78.zip"],
            "quark_links": ["https://pan.quark.cn/s/aaa"],
            "sha256": "ABC123",
            "size": 1234,
        },
        # 单数写法（quark / url）也要能认，方便手写清单
        "Linux": {"file": "moddingapi.v78.linux.zip",
                  "quark": "https://pan.quark.cn/s/bbb"},
        # 缺 file 的平台应被跳过，而不是塞个空包进来
        "Broken": {"quark_links": ["https://pan.quark.cn/s/ccc"]},
    },
}


class ApiManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _local(self, data):
        p = os.path.join(self.tmp, "api_manifest.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return p

    def _remote(self, data=None, src="cdn"):
        """返回一个把 fetch_remote_content 打桩的上下文"""
        content = None if data is None else json.dumps(data).encode("utf-8")
        return mock.patch("core.api_manifest.fetch_remote_content",
                          return_value=(content, src))

    def test_remote_manifest_wins(self):
        from core import api_manifest as am
        with self._remote(SAMPLE):
            m = am.load_manifest()
        self.assertEqual(m["source"], "github:cdn")
        self.assertEqual(m["version"], 78)
        pkg = m["packages"]["Windows"]
        self.assertEqual(pkg.file_name, "moddingapi.v78.windows.zip")
        # 直链排前面：不用登录夸克、也不用转存
        self.assertEqual(pkg.all_links[0], "https://example.com/api78.zip")
        self.assertEqual(pkg.all_links[1], "https://pan.quark.cn/s/aaa")
        self.assertEqual(pkg.sha256, "abc123")  # 统一小写，便于比对
        self.assertEqual(pkg.size, 1234)

    def test_singular_field_compat(self):
        from core import api_manifest as am
        with self._remote(SAMPLE):
            pkg = am.load_manifest()["packages"]["Linux"]
        self.assertEqual(pkg.quark_links, ["https://pan.quark.cn/s/bbb"])
        self.assertEqual(pkg.direct_links, [])

    def test_platform_without_file_is_skipped(self):
        from core import api_manifest as am
        with self._remote(SAMPLE):
            m = am.load_manifest()
        self.assertNotIn("Broken", m["packages"])

    def test_falls_back_to_local_file(self):
        from core import api_manifest as am
        with self._remote(None), \
                mock.patch.object(am, "_local_manifest_path",
                                  return_value=self._local(SAMPLE)):
            m = am.load_manifest()
        self.assertEqual(m["source"], "local")
        self.assertIn("Windows", m["packages"])

    def test_broken_remote_json_falls_back(self):
        """线上清单被改坏（比如手抖写错 JSON）时不能让安装直接崩掉"""
        from core import api_manifest as am
        with mock.patch("core.api_manifest.fetch_remote_content",
                        return_value=(b"{not json at all", "cdn")), \
                mock.patch.object(am, "_local_manifest_path",
                                  return_value=self._local(SAMPLE)):
            m = am.load_manifest()
        self.assertEqual(m["source"], "local")

    def test_falls_back_to_builtin(self):
        from config import API_ZIP_MAP
        from core import api_manifest as am
        with self._remote(None), \
                mock.patch.object(am, "_local_manifest_path",
                                  return_value=os.path.join(self.tmp, "nope.json")):
            m = am.load_manifest()
        self.assertEqual(m["source"], "builtin")
        self.assertEqual(set(m["packages"]), set(API_ZIP_MAP))

    def test_get_package_unknown_platform(self):
        from core import api_manifest as am
        with self._remote(SAMPLE):
            self.assertIsNotNone(am.get_package("Windows"))
            self.assertIsNone(am.get_package("Solaris"))

    def test_repo_manifest_is_valid(self):
        """仓库里那份 api_manifest.json 必须是合法且可用的，别推上去才发现"""
        from config import API_MANIFEST_FILE, get_base_dir
        path = os.path.join(get_base_dir(), API_MANIFEST_FILE)
        self.assertTrue(os.path.isfile(path), f"缺少 {API_MANIFEST_FILE}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        packages = data.get("packages") or {}
        self.assertTrue(packages, "清单里没有任何平台")
        for system, item in packages.items():
            self.assertTrue(item.get("file"), f"{system} 缺少 file 字段")
            self.assertTrue(item.get("quark_links") or item.get("direct_links"),
                            f"{system} 至少要有一个下载链接")


class ResolveApiPackageTests(unittest.TestCase):
    """_resolve_api_package 的链接分派与失败重试"""

    @staticmethod
    def _pkg(file_name="api.zip", direct=None, quark=None):
        from core.api_manifest import ApiPackage
        return ApiPackage("Windows", file_name,
                          quark_links=quark or [], direct_links=direct or [])

    def test_cached_file_skips_download(self):
        """downloads 里已经有了就直接用，不要再去联网"""
        from core import installer
        with tempfile.TemporaryDirectory() as d:
            cached = os.path.join(d, "api.zip")
            with open(cached, "wb") as f:
                f.write(b"zip")
            with mock.patch.object(installer, "get_download_dir", return_value=d), \
                    mock.patch.object(installer, "get_package",
                                      return_value=self._pkg(quark=["https://pan.quark.cn/s/x"])), \
                    mock.patch.object(installer, "_download_from_quark",
                                      side_effect=AssertionError("不应触发下载")):
                self.assertEqual(
                    os.path.abspath(installer._resolve_api_package(lambda *a: None, None)),
                    os.path.abspath(cached))

    def test_direct_link_preferred_over_quark(self):
        from core import installer
        pkg = self._pkg(direct=["https://example.com/a.zip"],
                        quark=["https://pan.quark.cn/s/x"])
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(installer, "get_download_dir", return_value=d), \
                mock.patch.object(installer, "get_package", return_value=pkg), \
                mock.patch.object(installer, "_download_direct",
                                  return_value="via-direct") as dmock:
            self.assertEqual(installer._resolve_api_package(lambda *a: None, None),
                             "via-direct")
        self.assertEqual(dmock.call_count, 1)

    def test_quark_link_routes_to_quark(self):
        from core import installer
        pkg = self._pkg(quark=["https://pan.quark.cn/s/x"])
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(installer, "get_download_dir", return_value=d), \
                mock.patch.object(installer, "get_package", return_value=pkg), \
                mock.patch.object(installer, "_download_from_quark",
                                  return_value="via-quark") as qmock:
            self.assertEqual(installer._resolve_api_package(lambda *a: None, None),
                             "via-quark")
        self.assertEqual(qmock.call_count, 1)

    def test_falls_through_to_next_link(self):
        """第一个链接挂了要换下一个，而不是直接放弃"""
        from core import installer
        pkg = self._pkg(direct=["https://bad/a.zip"],
                        quark=["https://pan.quark.cn/s/ok"])
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(installer, "get_download_dir", return_value=d), \
                mock.patch.object(installer, "get_package", return_value=pkg), \
                mock.patch.object(installer, "_download_direct",
                                  side_effect=RuntimeError("HTTP 404")), \
                mock.patch.object(installer, "_download_from_quark",
                                  return_value="via-quark"):
            self.assertEqual(installer._resolve_api_package(lambda *a: None, None),
                             "via-quark")

    def test_all_links_fail_raises(self):
        from core import installer
        pkg = self._pkg(direct=["https://bad/a.zip"],
                        quark=["https://pan.quark.cn/s/bad"])
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(installer, "get_download_dir", return_value=d), \
                mock.patch.object(installer, "get_package", return_value=pkg), \
                mock.patch.object(installer, "_download_direct",
                                  side_effect=RuntimeError("HTTP 404")), \
                mock.patch.object(installer, "_download_from_quark",
                                  side_effect=RuntimeError("夸克已失效")):
            with self.assertRaises(RuntimeError) as ctx:
                installer._resolve_api_package(lambda *a: None, None)
        self.assertIn("均不可用", str(ctx.exception))

    def test_no_links_configured_raises(self):
        from core import installer
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(installer, "get_download_dir", return_value=d), \
                mock.patch.object(installer, "get_package", return_value=self._pkg()):
            with self.assertRaises(RuntimeError) as ctx:
                installer._resolve_api_package(lambda *a: None, None)
        self.assertIn("没有配置", str(ctx.exception))

    def test_unknown_platform_raises(self):
        from core import installer
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(installer, "get_download_dir", return_value=d), \
                mock.patch.object(installer, "get_package", return_value=None):
            with self.assertRaises(RuntimeError):
                installer._resolve_api_package(lambda *a: None, None)


if __name__ == "__main__":
    unittest.main()
