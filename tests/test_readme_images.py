# -*- coding: utf-8 -*-
"""README 配图下载的回归测试。

用户实际反馈过：README 正文能显示，但配图空白（HKMP 的 logo）。根因是图片挂在
catbox.moe 等境外图床，国内直连被 RST；而正文走 jsDelivr 能拿到。修复是直连失败
时改走公共图片代理 wsrv.nl 兜底，并且结果仍以**原图 URL** 为 key 缓存。
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _fake_download_factory(calls, succeed):
    """造一个假的 _download_image：记录调用 URL，只对 succeed(url) 为真的返回图片。"""
    def _fake(url, timeout=10, ssl_warn_callback=None):
        calls.append(url)
        return "IMG" if succeed(url) else None
    return _fake


class FetchReadmeImagesTests(unittest.TestCase):
    def setUp(self):
        import ui.mod_page as mp
        self.mp = mp
        self._orig = mp._download_image

    def tearDown(self):
        self.mp._download_image = self._orig

    def test_direct_success_skips_proxy(self):
        """直连成功时不应再走代理（不增加正常情况的开销）"""
        calls = []
        self.mp._download_image = _fake_download_factory(calls, lambda u: True)
        res = self.mp.fetch_readme_images(["https://a.com/x.png"])
        self.assertEqual(res, {"https://a.com/x.png": "IMG"})
        self.assertEqual(len(calls), 1)
        self.assertNotIn("wsrv.nl", calls[0])

    def test_falls_back_to_proxy_and_keeps_original_key(self):
        """直连失败时走代理兜底，缓存 key 仍是原图 URL（才能和 <img src> 对上）"""
        calls = []
        self.mp._download_image = _fake_download_factory(
            calls, lambda u: "wsrv.nl" in u)
        url = "https://files.catbox.moe/x2wnhc.svg"
        res = self.mp.fetch_readme_images([url])
        self.assertEqual(list(res.keys()), [url])
        self.assertEqual(res[url], "IMG")
        self.assertEqual(len(calls), 2)          # 先直连，后代理
        self.assertIn("wsrv.nl", calls[1])
        self.assertIn("files.catbox.moe", calls[1])   # 原图 URL 被带上

    def test_skips_image_when_both_fail(self):
        calls = []
        self.mp._download_image = _fake_download_factory(calls, lambda u: False)
        res = self.mp.fetch_readme_images(["https://x.invalid/a.png"])
        self.assertEqual(res, {})
        self.assertEqual(len(calls), 2)

    def test_falls_back_to_bigger_svg_raster(self):
        """SVG 走代理时要求更大的栅格：README 会把它放大显示，32px 的源图必糊。"""
        calls = []
        self.mp._download_image = _fake_download_factory(
            calls, lambda u: "wsrv.nl" in u)
        self.mp.fetch_readme_images(["https://files.catbox.moe/x2wnhc.svg"])
        self.assertIn("w=512", calls[1])

    def test_empty_urls(self):
        self.assertEqual(self.mp.fetch_readme_images([]), {})


def _qapp():
    """拿到（或建出）QApplication；建不出来就跳过，不让测试整体挂掉。"""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class SvgTests(unittest.TestCase):
    """SVG 源图要按矢量栅格成大图，否则被 README 放大显示时发虚。"""

    @classmethod
    def setUpClass(cls):
        try:
            _qapp()
        except Exception as e:              # noqa: BLE001 无 GUI 环境
            raise unittest.SkipTest(f"无 Qt 环境: {e}")

    def test_is_svg_url(self):
        from ui.mod_page import _is_svg_url
        self.assertTrue(_is_svg_url("https://files.catbox.moe/x2wnhc.svg"))
        self.assertTrue(_is_svg_url("https://a.com/Logo.SVG?raw=1"))
        self.assertFalse(_is_svg_url("https://a.com/logo.png"))
        self.assertFalse(_is_svg_url("https://a.com/svg/logo.png"))

    def test_proxy_url_asks_for_big_raster_only_for_svg(self):
        from ui.mod_page import _proxy_url
        svg = _proxy_url("https://files.catbox.moe/x2wnhc.svg")
        self.assertIn("wsrv.nl", svg)
        self.assertIn("w=512", svg)
        self.assertIn("x2wnhc.svg", svg)        # 原图 URL 必须带上
        png = _proxy_url("https://a.com/a.png")
        self.assertIn("wsrv.nl", png)
        self.assertNotIn("w=", png)             # 位图不能要求放大

    def test_decode_svg_rasters_above_intrinsic_size(self):
        from ui.mod_page import _decode_image, _SVG_MIN_SIDE
        svg = (b'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32">'
               b'<rect width="32" height="32" fill="red"/></svg>')
        img = _decode_image(svg)
        self.assertIsNotNone(img)
        self.assertGreaterEqual(img.width(), _SVG_MIN_SIDE)
        self.assertEqual(img.width(), img.height())
        self.assertEqual(img.devicePixelRatio(), 1.0)   # 源图不带 DPR，由浏览器标注

    def test_decode_svg_failure_returns_none(self):
        from ui.mod_page import _decode_image
        self.assertIsNone(_decode_image(b"<svg"))

    def test_decode_rejects_garbage(self):
        from ui.mod_page import _decode_image
        self.assertIsNone(_decode_image(b"not an image at all"))


class ImageSizingTests(unittest.TestCase):
    """出图尺寸 = 显示宽度 × 设备像素比，并标注 DPR（缩放屏上才能 1:1 绘制）。"""

    URL = "https://a.com/logo.svg"

    @classmethod
    def setUpClass(cls):
        try:
            _qapp()
        except Exception as e:              # noqa: BLE001 无 GUI 环境
            raise unittest.SkipTest(f"无 Qt 环境: {e}")

    def _browser(self, natural_w, natural_h, dpr):
        from ui.mod_page import _ReadmeBrowser

        class B(_ReadmeBrowser):
            def devicePixelRatioF(self):    # 模拟 150%/200% 缩放屏
                return dpr

        from PySide6.QtGui import QImage
        self.original = QImage(natural_w, natural_h, QImage.Format_ARGB32)
        self.original.fill(0xFF223344)
        br = B({self.URL: self.original})
        br.resize(760, 500)
        return br

    def _limit(self, br):
        from ui.mod_page import _ReadmeBrowser
        return max(_ReadmeBrowser._MIN_WIDTH,
                   br.viewport().width() - _ReadmeBrowser._SIDE_PAD)

    def test_author_width_wins_over_natural_size(self):
        """作者写 width="52" 的小图标不该按原图铺满，且要按 DPR 出够像素。"""
        br = self._browser(1600, 900, 2.0)
        br.set_markdown('<img src="%s" width="52">' % self.URL)
        out = br._image_for(self.URL)
        self.assertEqual(out.deviceIndependentSize().width(), 52)
        self.assertEqual(out.width(), 104)              # 52 × 2.0
        self.assertEqual(out.devicePixelRatio(), 2.0)

    def test_no_author_width_clamps_to_viewport(self):
        """没写 width 时按原图宽度显示，但不能超出视口。"""
        br = self._browser(1600, 900, 2.0)
        br.set_markdown('<img src="%s">' % self.URL)
        logical = self._limit(br)
        out = br._image_for(self.URL)
        self.assertEqual(out.deviceIndependentSize().width(), logical)
        self.assertEqual(out.width(), int(round(logical * 2.0)))

    def test_huge_author_width_is_clamped(self):
        br = self._browser(1600, 900, 1.0)
        br.set_markdown('<img src="%s" width="9999">' % self.URL)
        out = br._image_for(self.URL)
        self.assertEqual(out.deviceIndependentSize().width(), self._limit(br))

    def test_dpr_one_keeps_logical_pixels(self):
        br = self._browser(1600, 900, 1.0)
        br.set_markdown('<img src="%s" width="300">' % self.URL)
        out = br._image_for(self.URL)
        self.assertEqual(out.width(), 300)
        self.assertEqual(out.devicePixelRatio(), 1.0)

    def test_small_source_is_upscaled_to_requested_size(self):
        """源图比要显示的还小时（旧版 SVG 只有 32px）也要出够像素，尽量不失真。"""
        br = self._browser(32, 32, 2.0)
        br.set_markdown('<img src="%s" width="52">' % self.URL)
        out = br._image_for(self.URL)
        self.assertEqual(out.width(), 104)

    def test_does_not_mutate_cached_original(self):
        """标注 DPR 不能污染缓存的原图 —— 点击预览要用带原始尺寸的图。"""
        dpr = 2.0
        br = self._browser(1600, 900, dpr)
        limit = self._limit(br)
        from PySide6.QtGui import QImage
        natural = int(round(limit * dpr))
        self.original = QImage(natural, 100, QImage.Format_ARGB32)
        br._images[self.URL] = self.original
        br.set_markdown('<img src="%s">' % self.URL)
        out = br._image_for(self.URL)                    # 走浅拷贝分支
        self.assertEqual(out.devicePixelRatio(), dpr)
        self.assertEqual(self.original.devicePixelRatio(), 1.0)


if __name__ == "__main__":
    unittest.main()
