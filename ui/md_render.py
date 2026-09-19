# -*- coding: utf-8 -*-
"""Markdown → 暗色主题 HTML，供 QTextBrowser 显示。

为什么要绕开 QTextBrowser.setMarkdown()：
  - 原生解析器排版很弱：h1~h6 和正文一个字号（Qt 的 CSS 只认 pt 单位，写 px
    会整条失效）、行与行贴在一起、表格和删除线不支持；
  - 原生解析会直接丢掉 <img>，README 里用 HTML 写的图片永远显示不出来。
改用 markdown-it（CommonMark 完整实现）先转 HTML，再 setHtml 配一套样式表。

Qt 富文本 CSS 子集的几个坑（都实测过，改样式时别踩）：
  - font-size **必须**写 pt；px 和无单位一律无效（标题会跟正文一样大）；
  - line-height 要写在具体元素（p / li / td）上，写在 body 上不生效；
  - 支持 margin / padding / color / background-color / border；
  - border-radius、border-collapse 不支持，写了也不报错，别指望生效。
"""
import re

from PySide6.QtGui import QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import QTextBrowser

try:
    from markdown_it import MarkdownIt
except Exception:      # 没装就退化成 Qt 原生渲染，保证不崩
    MarkdownIt = None


# html=True：README 常直接用 <img> 写图，关掉的话会被转义成纯文本。
# 不开 linkify：它依赖 linkify-it-py，本项目没装。
def _make_parser():
    if MarkdownIt is None:
        return None
    return MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])


_PARSER = _make_parser()

# 内容来自远端（GitHub README），先去掉这几类标签。Qt 不执行 JS，本来就没有
# 脚本风险，主要是避免内容里的 <style> 顶掉我们的样式表。
_UNSAFE_RE = re.compile(
    r"<\s*(script|style|iframe|object|embed)\b.*?<\s*/\s*\1\s*>",
    re.I | re.S)

# <pre><code class="language-x"> 里那层 code 会套上行内代码的底色，
# 把 pre 的底色盖掉，所以直接剥掉内层标签
_PRE_CODE_RE = re.compile(r"(<pre>)\s*<code[^>]*>(.*?)</code>\s*(</pre>)", re.S)

# <img> 上的 width / height
_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.I)
_IMG_SIZE_ATTR_RE = re.compile(
    r"\s+(?:width|height)\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
_IMG_SRC_ATTR_RE = re.compile(
    r"""\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
# <img> 上的 width（用来还原作者想要的显示宽度）
_IMG_WIDTH_ATTR_RE = re.compile(
    r"""\bwidth\s*=\s*["']?\s*(\d+(?:\.\d+)?)""", re.I)

# 独占一行的 <img>（markdown 里把图单独写一行时 markdown-it 会产出裸标签）
_STANDALONE_IMG_RE = re.compile(r"(?m)^[ \t]*(<img\b[^>]*>)[ \t]*$", re.I)


def _img_src(tag):
    m = _IMG_SRC_ATTR_RE.search(tag)
    if not m:
        return ""
    return (m.group(1) or m.group(2) or m.group(3) or "").strip()


def _img_available(src, available):
    """判断这张图是否真能加载出来（available 是缓存里的绝对地址集合）。

    缓存 key 是 urljoin(base_url, 相对路径) 得到的绝对地址，而这里只有原文里的
    src（可能是相对路径），所以按文件名兜底比对。
    """
    if not available or not src:
        return False
    if src in available:
        return True
    name = src.split("?")[0].split("#")[0].rstrip("/").split("/")[-1]
    if not name:
        return False
    for key in available:
        k = key.split("?")[0].split("#")[0]
        if k == src or k.endswith("/" + name):
            return True
    return False


def _url_basename(url):
    return (url or "").split("?")[0].split("#")[0].rstrip("/").split("/")[-1].lower()


def collect_image_widths(markdown):
    """取出 README 里 <img> 写死的 width：{src: 宽度}（像素，取整数部分）。

    渲染时尺寸属性会被统一剥掉（见 _process_images），改由渲染方按视口宽度和
    设备像素比重算；这里把作者原本想要的宽度读回来，好在重算时把它的意图当上限
    保留（例如 HKMP 的 logo 写死 width="52"，就不该按原图的原始尺寸铺满）。
    """
    out = {}
    for tag in _IMG_TAG_RE.findall(markdown or ""):
        src = _img_src(tag)
        m = _IMG_WIDTH_ATTR_RE.search(tag)
        if src and m:
            try:
                out[src] = int(float(m.group(1)))
            except ValueError:
                continue
    return out


def lookup_url(mapping, url):
    """按完整 URL 查表，查不到再按文件名兜底（相对路径会被 Qt 解析成绝对地址）。"""
    if not mapping or not url:
        return None
    if url in mapping:
        return mapping[url]
    name = _url_basename(url)
    if not name:
        return None
    for key, value in mapping.items():
        if _url_basename(key) == name:
            return value
    return None


def _process_images(html, available=None, drop_unavailable=False):
    """处理 <img>：一律去掉 width/height，加载不出来的图再按需整段删掉。

    为什么连「能加载的图」也要去掉 width/height：最终出图尺寸由 MarkdownBrowser
    按「视口宽度 × 设备像素比」决定（见 _ReadmeBrowser.loadResource），作者写死的
    width 会和它打架 —— 例如作者写 width="800"、我们按 736 出图，Qt 会把 736 的
    位图拉伸到 800 绘制，放大 1.09 倍就又糊了。作者想要的宽度由浏览器自己读回来
    复现（collect_image_widths）。

    加载不出来的图：
      - drop_unavailable=True：整段删掉。QTextBrowser 对取不到资源的 <img> 会画一个
        「裂图」占位方块，落在标题行里很难看；README 的图全走本地缓存，删掉不影响
        任何能显示的内容。
      - drop_unavailable=False：保留标签但去掉尺寸。Qt 拿不到图片真实尺寸时会按
        width 预留 width×width 的正方形空白（width="800" 就是 800px 高的大白块）。

    available 为空表示「没有图片缓存」（如「关于」弹窗），此时一律按加载不出来处理。
    """
    def _sub(m):
        tag = m.group(0)
        if not _img_available(_img_src(tag), available) and drop_unavailable:
            return ""
        return _IMG_SIZE_ATTR_RE.sub("", tag)
    return _IMG_TAG_RE.sub(_sub, html)


def _wrap_standalone_img(html):
    """给独占一行的 <img> 套上 <p>。

    markdown 里把 <img> 单独写一行时，markdown-it 会原样输出裸标签（不套 <p>）。
    Qt 会把这个裸 <img> 当成内联内容**并进上一段**，结果图片和它上面的文字挤在
    同一个块里：既没有段落之间的空隙，图片还会被上一段的行距残留影响。套上 <p>
    后它成为独立段落，自然获得段间距。
    """
    return _STANDALONE_IMG_RE.sub(lambda m: "<p>%s</p>" % m.group(1), html)


def render_markdown(text, available_images=None, drop_unavailable=False):
    """Markdown 文本 → HTML 片段；解析失败返回 None（调用方应退回 setMarkdown）。

    available_images：已经下载好、能真正渲染出来的图片绝对地址集合。能加载的
    保留作者指定的 width（维持小图标大小），加载不了的见 drop_unavailable。
    drop_unavailable：加载不到的 <img> 是否整段删除（否则只去掉 width/height）。
    """
    if not text or _PARSER is None:
        return None
    try:
        html = _PARSER.render(text)
    except Exception:
        return None
    html = _UNSAFE_RE.sub("", html)
    html = _PRE_CODE_RE.sub(lambda m: m.group(1) + m.group(2) + m.group(3), html)
    html = _process_images(html, available_images, drop_unavailable)
    html = _wrap_standalone_img(html)
    return html


# ---------------------------------------------------------------------------
# 暗色样式表
# 换算：1pt ≈ 1.33px，正文字号 14px ≈ 10.5pt
# ---------------------------------------------------------------------------
MD_CSS = """
p, li, td, th {
    font-size: 10.5pt;
    line-height: 1.75;
    color: #dcdce4;
}
h1 {
    font-size: 19pt; font-weight: bold; color: #ffffff;
    line-height: 1.4; margin: 16pt 0 8pt 0;
}
h2 {
    font-size: 15pt; font-weight: bold; color: #ffffff;
    line-height: 1.45; margin: 15pt 0 7pt 0;
}
h3 {
    font-size: 12.5pt; font-weight: bold; color: #f2f2f7;
    line-height: 1.5; margin: 13pt 0 6pt 0;
}
h4, h5, h6 {
    font-size: 11pt; font-weight: bold; color: #e8e8ee;
    line-height: 1.55; margin: 11pt 0 5pt 0;
}
a { color: #5aa9ff; }
code {
    font-family: "Cascadia Mono", "Consolas", "Courier New", monospace;
    font-size: 9.5pt; color: #e6e6f0;
    background-color: #2b2b34; padding: 0 3pt;
}
pre {
    font-family: "Cascadia Mono", "Consolas", "Courier New", monospace;
    font-size: 9.5pt; color: #cfcfdb; line-height: 1.55;
    background-color: #16161a;
    margin: 9pt 0 9pt 0; padding: 9pt 11pt;
    border: 1px solid #2b2b34;
}
blockquote {
    color: #9ea3b5; line-height: 1.7;
    margin: 9pt 0; padding-left: 11pt;
    border-left: 3pt solid #3a3a44;
}
ul, ol { margin: 6pt 0; }
table { margin: 9pt 0; }
th {
    background-color: #24242b; color: #ffffff; font-weight: bold;
    padding: 4pt 8pt; border: 1px solid #33333c;
}
td { padding: 4pt 8pt; border: 1px solid #33333c; }
hr { color: #33333c; }
"""


class MarkdownBrowser(QTextBrowser):
    """按暗色主题渲染 Markdown 的 QTextBrowser。

    set_markdown() 一次做完「转 HTML + 上样式 + 载入」；markdown-it 不可用时
    自动退回 Qt 原生 setMarkdown，保证功能不中断（只是排版朴素些）。
    """

    # 子类设为 True：把加载不到的 <img> 整段删掉（README 场景，避免 Qt 画裂图占位）
    drop_unavailable_images = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self.document().setDefaultStyleSheet(MD_CSS)

    def available_image_urls(self):
        """已缓存、能真正渲染的图片地址集合。子类（如 README 浏览器）可覆盖。"""
        return set()

    def set_markdown(self, text):
        html = render_markdown(text, self.available_image_urls(),
                               self.drop_unavailable_images)
        if html is None:
            self.setMarkdown(text or "")
        else:
            self.setHtml(html)
            self._reset_line_height_on_image_blocks()
        self.moveCursor(QTextCursor.Start)

    @staticmethod
    def _block_has_image(block):
        it = block.begin()
        while it != block.end():
            frag = it.fragment()
            if frag.isValid():
                cf = frag.charFormat()
                if cf.isImageFormat():
                    return True
            it += 1
        return False

    def _reset_line_height_on_image_blocks(self):
        """把「含图片的块」的行距还原成默认值。

        Qt 的比例行距是按**整行**放大的，那一行里只要有张图，就会按图高乘比例
        预留空间：200px 的图配 1.75 的行距，这一行会变成 350px，图下方凭空多出
        150px 空白（实测块高 364 vs 215）。

        README 常见写法是 <img ...><br>正文，图和正文同处一块，所以中招概率很高。
        CSS 没法只对「不含图片的段落」生效，只能在渲染后逐块修正：带图的行距在
        Qt 里是块级属性，改不了单行，这里整块退回默认行距——代价是该块里的文字
        行距变紧凑，但这类块通常只有一两行正文，换来的是不再有大白块。
        """
        doc = self.document()
        cursor = QTextCursor(doc)
        block = doc.begin()
        while block.isValid():
            if self._block_has_image(block):
                bf = block.blockFormat()
                bf.setLineHeight(0.0, QTextBlockFormat.SingleHeight.value)
                cursor.setPosition(block.position())
                cursor.setBlockFormat(bf)
            block = block.next()
