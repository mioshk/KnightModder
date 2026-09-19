# -*- coding: utf-8 -*-
"""README 翻译的离线单元测试。

只覆盖不联网的部分：Markdown 保护/还原、分块。这两块是最容易写错、
一旦错了就会静默破坏 README 排版的地方——翻译器会把半角 () 改成全角 （）
导致链接失效，把反引号改成中文引号导致行内代码失效，所以必须锁住。
真正发请求的 _post_batch 不在单测里跑（避免依赖网络）。
"""
import re
import unittest
from unittest import mock


class ProtectRestoreTests(unittest.TestCase):
    @staticmethod
    def _mod():
        from utils import translator
        return translator

    def test_link_urls_survive_roundtrip(self):
        """链接的 (...) 必须原样还原，且 [文字] 仍留在外面参与翻译"""
        t = self._mod()
        md = "See the [wiki](https://example.com/wiki) for details."
        protected, store = t._protect(md)
        restored = t._restore(protected, store)
        self.assertEqual(restored, md)
        # 只护住 url，链接文字没被吞进占位符
        self.assertIn("[wiki]", protected)
        self.assertNotIn("https://", protected)
        self.assertEqual(store, ["(https://example.com/wiki)"])

    def test_inline_code_keeps_backticks(self):
        t = self._mod()
        md = "Edit `ExampleMod.GlobalSettings.json` first."
        protected, store = t._protect(md)
        self.assertNotIn("`", protected)
        self.assertEqual(t._restore(protected, store), md)

    def test_fenced_code_block_is_wholly_protected(self):
        t = self._mod()
        md = '```csharp\npublic void Init() { Log("hi"); }\n```'
        protected, store = t._protect(md)
        # 整块被换成单行占位符，语言标记不会流出去被翻
        self.assertEqual(len(protected.split("\n")), 1)
        self.assertNotIn("csharp", protected)
        self.assertEqual(t._restore(protected, store), md)

    def test_bare_url_and_html_tag_protected(self):
        t = self._mod()
        md = "Visit https://example.com/a_b or <br> for more."
        protected, store = t._protect(md)
        self.assertNotIn("https://", protected)
        self.assertNotIn("<br>", protected)
        self.assertEqual(t._restore(protected, store), md)

    def test_html_img_tag_is_protected_wholly(self):
        """<img> 整块保护：不能只护住 src，否则标签占位符里套着 URL 占位符"""
        t = self._mod()
        md = '<img src="https://example.com/a.png" width="800">'
        protected, store = t._protect(md)
        # 整条标签应被换成单个占位符，src 不再以明文或嵌套形式出现
        self.assertNotIn("https://", protected)
        self.assertEqual(t._restore(protected, store), md)
        # 关键：标签文本里不能再残留占位符（嵌套一旦发生就会留成死串）
        self.assertIsNone(re.search(r"ZX\d+ZX", store[-1]))

    def test_html_tag_rule_runs_before_bare_url(self):
        """HTML 标签规则必须早于裸 URL 规则，否则会产出嵌套占位符"""
        t = self._mod()
        md = '<img src="https://example.com/a.png" width="800">'
        protected, store = t._protect(md)
        for s in store:
            self.assertIsNone(re.search(r"ZX\d+ZX", s), f"片段里出现嵌套占位符: {s}")

    def test_markdown_image_url_preserved(self):
        t = self._mod()
        md = "![Preview](https://example.com/p.png)\n\nText here.\n"
        protected, store = t._protect(md)
        self.assertEqual(t._restore(protected, store), md)
        self.assertIn("https://example.com/p.png", "".join(store))

    def test_markdown_image_is_protected_wholly(self):
        """整张 ![alt](url) 一起护住，避免翻译器在 ! 与 [ 间插空格导致图消失"""
        t = self._mod()
        md = "![Preview](https://a.com/x.png)"
        protected, store = t._protect(md)
        self.assertNotIn("![", protected)
        self.assertEqual(t._restore(protected, store), md)

    def test_repair_removes_space_between_bracket_and_paren(self):
        t = self._mod()
        self.assertEqual(t._repair("[wiki] (https://a.com)"), "[wiki](https://a.com)")
        self.assertEqual(t._repair("![a] (https://a.com/x.png)"),
                         "![a](https://a.com/x.png)")

    def test_repair_leaves_normal_text_alone(self):
        """不要把正常文本里的 ! 或 ] 误伤"""
        t = self._mod()
        md = "Wow ! What a mod.\n\nUse [1, 2, 3] (ordered) here.\n"
        self.assertEqual(t._repair(md), md)

    def test_restore_resolves_nested_placeholder(self):
        """万一真出现嵌套，多轮还原也要能解开，不能留死字符串"""
        t = self._mod()
        # store[0] 里故意再嵌一个占位符
        text = t._restore("ZX1ZX", ["(https://a.com/x)", "<img src=\"ZX0ZX\">"])
        self.assertNotIn("ZX", text)

    def test_restore_tolerates_unknown_index(self):
        """占位符索引越界时原样保留，不能抛异常把整个 README 弄挂"""
        t = self._mod()
        self.assertEqual(t._restore("a ZX9ZX b", []), "a ZX9ZX b")


class ChunkTests(unittest.TestCase):
    @staticmethod
    def _mod():
        from utils import translator
        return translator

    def test_chunk_respects_char_limit(self):
        t = self._mod()
        lines = ["x" * 100] * 100
        chunks = t._chunk_lines(lines)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(sum(len(x) + 1 for x in c), t._MAX_CHARS)
            self.assertLessEqual(len(c), t._MAX_BATCH)

    def test_chunk_keeps_all_lines_in_order(self):
        t = self._mod()
        lines = [f"line{i}" for i in range(50)]
        flat = [l for c in t._chunk_lines(lines) for l in c]
        self.assertEqual(flat, lines)

    def test_blank_only_chunk_not_sent(self):
        """连续空行不该发请求，应原样保留"""
        t = self._mod()
        md = "Para one.\n\n\n\nPara two.\n"
        with mock.patch.object(t, "_post_batch",
                               side_effect=lambda texts, *a, **k: ["译:" + x for x in texts]) as m:
            out = t.translate_markdown(md)
        # 只对含内容的行发了请求
        sent = [x for call in m.call_args_list for x in call.args[0]]
        self.assertTrue(all(s.strip() for s in sent), f"发了空白块: {sent}")
        # 空行数量不变
        self.assertEqual(out.count("\n"), md.count("\n"))

    def test_translation_result_is_used(self):
        t = self._mod()
        with mock.patch.object(t, "_post_batch", side_effect=lambda texts, *a, **k: texts):
            md = "# Title\n\nBody text.\n"
            self.assertEqual(t.translate_markdown(md), md)


class EmphasisProtectionTests(unittest.TestCase):
    """行内强调标记必须护住——翻译器会吞掉/挪动它们（真实 README 实测过）。"""

    @staticmethod
    def _mod():
        from utils import translator
        return translator

    def test_bold_markers_are_protected(self):
        """行内 **粗体** 的标记要换成占位符；否则译者会吞掉开头那个、把结尾的
        留成正文，屏幕上就出现「…文本编辑器。***」（用户报的就是这个）。"""
        t = self._mod()
        md = "This is **really** important."
        protected, store = t._protect(md)
        self.assertNotIn("*", protected)
        self.assertEqual(t._restore(protected, store), md)

    def test_wrapped_line_markers_are_left_for_line_handler(self):
        """整行包裹的标记要留给 translate_markdown 处理：它得先认出「整行包裹」
        才能剥掉标记送译。这里换成占位符就认不出来了。"""
        t = self._mod()
        md = "***A robust text editor is highly recommended.***"
        protected, store = t._protect(md)
        self.assertIn("***", protected)
        self.assertEqual(t._restore(protected, store), md)

    def test_underscore_emphasis_becomes_asterisk(self):
        """空格分隔的下划线强调换成星号：CommonMark 不允许词内的 _ 强调，
        翻成中文后没空格（「绑定_和_时」）斜体就丢了，星号则没问题。"""
        t = self._mod()
        protected, store = t._protect("the binding _and_ when saved")
        self.assertNotIn("_", protected)
        self.assertEqual(store.count("*"), 2)
        self.assertEqual(t._restore(protected, store), "the binding *and* when saved")

    def test_intraword_underscore_is_not_emphasis(self):
        """some_file_name 是标识符不是强调，换成星号会凭空多出斜体。"""
        t = self._mod()
        md = "a path like some_file_name here"
        protected, store = t._protect(md)
        self.assertNotIn("*", protected)
        self.assertEqual(t._restore(protected, store), md)

    def test_list_bullet_is_left_alone(self):
        """行首落单的 * 是列表项符号，不能换成占位符（一旦被译者丢掉，列表就塌成段落）"""
        t = self._mod()
        protected, _ = t._protect("* Jump\n* Left, Right\n")
        self.assertIn("* Jump", protected)
        self.assertIn("* Left", protected)

    def test_multi_marker_line_is_not_a_wrapped_line(self):
        """一行里有多组标记（**a** and **b**）属于行内强调，不该当成整行包裹处理"""
        t = self._mod()
        self.assertIsNone(t._WRAPPED_LINE_RE.match("**a** and **b**"))
        self.assertIsNotNone(t._WRAPPED_LINE_RE.match("**Bold statement here.**"))

    def test_structure_only_line_is_protected_wholly(self):
        """没有可译文字的行整行护住：实测译者会把 "#### " 的空格吃掉，
        变成 "####**`A.B`**"，H4 标题塌成普通段落。"""
        t = self._mod()
        md = "#### **`A.B`**\n\nBody text.\n"
        protected, store = t._protect(md)
        self.assertNotIn("####", protected)
        self.assertIn("Body text.", protected)
        self.assertEqual(t._restore(protected, store), md)


class WrappedLineTests(unittest.TestCase):
    """整行被标记包裹的行：剥掉标记送译，译完按原文把标记套回。"""

    @staticmethod
    def _mod():
        from utils import translator
        return translator

    def test_markers_are_reapplied_around_translation(self):
        t = self._mod()
        with mock.patch.object(t, "_post_batch",
                               side_effect=lambda texts, *a, **k: ["请保持格式完整。"]):
            out = t.translate_markdown("***Make sure to keep the format intact.***")
        self.assertEqual(out, "***请保持格式完整。***")

    def test_markers_are_stripped_before_sending(self):
        t = self._mod()
        sent = []

        def fake(texts, *a, **k):
            sent.extend(texts)
            return ["译文" for _ in texts]

        with mock.patch.object(t, "_post_batch", side_effect=fake):
            t.translate_markdown("_Settings are stored in `X.json`._")
        self.assertTrue(sent)
        self.assertFalse(any(s.startswith("_") for s in sent),
                         f"标记没剥掉就送译了: {sent}")

    def test_extra_markers_from_translator_are_cleaned(self):
        """译者偶尔会把标记吐回来（实测出现过「…文本编辑器***A。***」）"""
        t = self._mod()
        with mock.patch.object(t, "_post_batch",
                               side_effect=lambda texts, *a, **k: ["***文本编辑器***A***"]):
            out = t.translate_markdown("***A text editor.***")
        self.assertEqual(out, "***文本编辑器A***")


if __name__ == "__main__":
    unittest.main()
