# -*- coding: utf-8 -*-
"""Markdown 渲染的回归测试。

重点锁两类「图片下方留出大块空白」的问题（用户实际截图反馈过）：
  1. 图片和正文同处一块时，Qt 的比例行距会把整行按图高放大：200px 的图配 1.75
     行距，这一行变成 350px，图下方凭空多出 150px；
  2. 图片没下载成功时，Qt 会按 <img> 上的 width 预留一块 width×width 的正方形，
     width="800" 就是 800px 高的大白块，比图本身还显眼。
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _qapp():
    """拿到（或建出）QApplication；建不出来就跳过，不让测试整体挂掉。"""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class ProcessImagesTests(unittest.TestCase):
    def test_removes_width_and_height(self):
        from ui.md_render import _process_images
        self.assertEqual(
            _process_images('<img src="a.png" width="800" height="200">'),
            '<img src="a.png">')

    def test_keeps_src_and_other_attrs(self):
        from ui.md_render import _process_images
        out = _process_images('<img alt="x" src="a.png" width="100">')
        self.assertIn('src="a.png"', out)
        self.assertIn('alt="x"', out)
        self.assertNotIn("width", out)

    def test_single_quoted_and_bare_attrs(self):
        from ui.md_render import _process_images
        self.assertEqual(
            _process_images("<img src='a.png' width='800'>"), "<img src='a.png'>")
        self.assertEqual(
            _process_images("<img src=a.png width=800>"), "<img src=a.png>")

    def test_leaves_other_tags_alone(self):
        from ui.md_render import _process_images
        src = '<a href="x" width="1">t</a><br>'
        self.assertEqual(_process_images(src), src)

    def test_available_image_keeps_tag_but_drops_size(self):
        """能加载的图保留标签，但 width/height 要剥掉。

        出图尺寸改由 MarkdownBrowser 按「视口宽 × 设备像素比」统一决定；留着作者
        写死的 width 会让位图被 Qt 拉伸（放大 1.x 倍就又糊了，见过 HKMP 的案例）。
        作者想要的宽度由 collect_image_widths 读回复现。
        """
        from ui.md_render import _process_images
        out = _process_images('<img src="https://a.com/logo.svg" width="52">',
                              {"https://a.com/logo.svg"})
        self.assertIn("<img", out)
        self.assertNotIn("width", out)
        self.assertIn('src="https://a.com/logo.svg"', out)

    def test_drops_unavailable_image_when_asked(self):
        """drop_unavailable=True 时，加载不到的 <img> 应整段删掉（不留裂图占位）"""
        from ui.md_render import _process_images
        out = _process_images(
            '<img src="https://x.invalid/m.png" width="800">正文', set(),
            drop_unavailable=True)
        self.assertNotIn("<img", out)
        self.assertIn("正文", out)

    def test_render_markdown_strips_img_size(self):
        from ui.md_render import render_markdown
        html = render_markdown('<img src="https://a.com/b.png" width="800">')
        if html is None:                    # markdown-it 没装，跳过
            self.skipTest("markdown-it 不可用")
        self.assertNotIn("width", html)
        self.assertIn("https://a.com/b.png", html)

    def test_render_markdown_drops_unavailable(self):
        from ui.md_render import render_markdown
        html = render_markdown(
            '<img src="https://x.invalid/m.png">\n\n正文', set(),
            drop_unavailable=True)
        if html is None:                    # markdown-it 没装，跳过
            self.skipTest("markdown-it 不可用")
        self.assertNotIn("<img", html)
        self.assertIn("正文", html)


class CollectImageWidthsTests(unittest.TestCase):
    """作者写死的 <img width="N"> 要能被读回来（渲染时尺寸被剥掉了）。"""

    def test_reads_width(self):
        from ui.md_render import collect_image_widths
        md = ('# HKMP <img src="https://files.catbox.moe/x2wnhc.svg" width="52" '
              'align="right">\n\n<img src="b.png" width=800>')
        self.assertEqual(collect_image_widths(md), {
            "https://files.catbox.moe/x2wnhc.svg": 52,
            "b.png": 800,
        })

    def test_ignores_img_without_width(self):
        from ui.md_render import collect_image_widths
        self.assertEqual(
            collect_image_widths('<img src="a.png" align="right">'), {})

    def test_does_not_confuse_height_with_width(self):
        from ui.md_render import collect_image_widths
        self.assertEqual(collect_image_widths('<img src="a.png" height="99">'), {})

    def test_empty(self):
        from ui.md_render import collect_image_widths
        self.assertEqual(collect_image_widths(""), {})
        self.assertEqual(collect_image_widths(None), {})


class LookupUrlTests(unittest.TestCase):
    """文档里的 src 可能被 Qt 解析成绝对地址，查表要能按文件名兜底。"""

    def test_exact_first(self):
        from ui.md_render import lookup_url
        m = {"https://a.com/x.png": 1}
        self.assertEqual(lookup_url(m, "https://a.com/x.png"), 1)

    def test_falls_back_to_basename(self):
        from ui.md_render import lookup_url
        m = {"images/logo.svg": 52}
        self.assertEqual(lookup_url(m, "https://cdn.example.com/repo/main/logo.svg"), 52)

    def test_missing(self):
        from ui.md_render import lookup_url
        self.assertIsNone(lookup_url({}, "https://a.com/x.png"))
        self.assertIsNone(lookup_url({"a.png": 1}, "https://a.com/b.png"))


class ImageGapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            _qapp()
        except Exception as e:              # noqa: BLE001 无 GUI 环境
            raise unittest.SkipTest(f"无 Qt 环境: {e}")

    @staticmethod
    def _image(h, w):
        from PySide6.QtGui import QImage
        img = QImage(w, h, QImage.Format_RGB32)
        img.fill(0)
        return img

    def _browser_with_image(self, url, img, markdown):
        from ui.md_render import MarkdownBrowser

        class B(MarkdownBrowser):
            def loadResource(self, type_, u):
                if u.toString() == url:
                    return img
                return super().loadResource(type_, u)

        br = B()
        br.set_markdown(markdown)
        br.resize(900, 600)
        doc = br.document()
        doc.adjustSize()
        return br, doc

    def test_image_block_not_inflated_by_line_height(self):
        """图与正文同块时不该被行距放大（1.75 行距会让 200px 的图占 350px）"""
        url = "https://example.com/banner.png"
        br, doc = self._browser_with_image(
            url, self._image(200, 400),
            '<img src="%s" width="800"><br>正文文字。' % url)
        h = doc.documentLayout().blockBoundingRect(doc.begin()).height()
        self.assertLess(h, 260, f"图片所在块被行距撑高了: {h}")

    def test_missing_image_does_not_reserve_huge_blank(self):
        """加载失败的图不能按 width 预留 width×width 的空白"""
        from ui.md_render import MarkdownBrowser
        br = MarkdownBrowser()
        br.set_markdown('<img src="https://x.invalid/m.png" width="800">\n\n正文')
        br.resize(900, 600)
        doc = br.document()
        doc.adjustSize()
        total = doc.documentLayout().documentSize().height()
        self.assertLess(total, 200, f"缺失图片仍占了大块空白: {total}")

    def test_plain_text_still_gets_line_height(self):
        """不含图的段落行距要保留，否则本次优化就白做了"""
        from ui.md_render import MarkdownBrowser
        br = MarkdownBrowser()
        br.set_markdown("正文段落。\n")
        block = br.document().begin()
        self.assertGreater(block.blockFormat().lineHeight(), 100)


if __name__ == "__main__":
    unittest.main()
