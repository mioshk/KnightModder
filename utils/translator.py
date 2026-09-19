# -*- coding: utf-8 -*-
"""README / 长文本翻译：走微软 Edge 的翻译端点。

为什么不用 Azure Translator：那要订阅密钥 + 区域，用户手上没有，也不该把
密钥塞进客户端。Edge 浏览器自用端点免鉴权，语种覆盖与 Azure 一致，实测能
原样保留 Markdown 的 #、>、列表等**行首**语法，但会把行内的强调标记（* _）
吞掉或挪位，所以这类片段仍要先抽取保护（见 _protect）。

注意：这是 Edge 前端内部使用的非公开端点，没有 SLA，路径和风控策略可能随时
调整。因此所有调用都带重试 + SSL/代理降级，失败时抛异常交给上层降级提示，
绝不影响 README 原本的展示。若哪天端点失效，只需替换本文件的 _post_batch。
"""
import json
import re

_TRANSLATE_URL = "https://edge.microsoft.com/translate/translatetext"
# 单次请求的字符上限（官方 Translator 是 50000，这里取保守值，
# README 单行很长时也能安全切分）
_MAX_CHARS = 4000
# 单批元素上限
_MAX_BATCH = 20

DEFAULT_TARGET = "zh-Hans"


def _post_json(url, payload, timeout=20):
    """POST JSON，带 SSL 验证降级与代理降级（与 utils.common 的取数策略一致）。

    个别精简版 Windows 缺根证书会导致 SSLError；本机代理（如 Clash）没开时
    requests 读系统代理会抛 ProxyError。两种情况都要能自动重试。
    """
    import requests

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    kwargs = {
        "data": body,
        "headers": {"Content-Type": "application/json"},
        "timeout": timeout,
    }
    try:
        return requests.post(url, **kwargs)
    except requests.exceptions.SSLError:
        kwargs["verify"] = False
    except requests.exceptions.ProxyError:
        kwargs["proxies"] = {"http": None, "https": None}
    try:
        return requests.post(url, **kwargs)
    except requests.exceptions.SSLError:
        kwargs["verify"] = False
        return requests.post(url, **kwargs)


def _post_batch(texts, target, timeout=20):
    """翻译一批文本，返回等长译文列表；失败抛 RuntimeError。"""
    url = f"{_TRANSLATE_URL}?from=&to={target}&isEnterpriseClient=false"
    last_err = None
    for _ in range(3):
        try:
            resp = _post_json(url, texts, timeout=timeout)
        except Exception as e:          # noqa: BLE001 网络类异常统一兜底
            last_err = str(e)
            continue
        if resp.status_code != 200:
            last_err = f"HTTP {resp.status_code}"
            continue
        try:
            data = resp.json()
        except Exception:               # noqa: BLE001 返回不是 JSON
            last_err = "返回内容不是 JSON"
            continue
        if not isinstance(data, list) or len(data) != len(texts):
            last_err = "返回结构与请求不一致"
            continue
        out = []
        for item in data:
            tr = (item or {}).get("translations") or [{}]
            out.append((tr[0] or {}).get("text", "") or "")
        return out
    raise RuntimeError(last_err or "翻译失败")


# 成对的强调标记：* ** *** / _ __ ___（最多切 4 个连续字符，够用）
_EMPH_RUN_RE = re.compile(r"\*{1,4}|_{1,4}")

# 整行被强调标记包起来：***粗斜体*** / **粗体** / _斜体_。
# 内层限定 [^*_] 是为了排除 "**a** and **b**"（一行里有多组标记）——那属于行内
# 标记，交给 _protect_emphasis；只有「标记里再也没有别的标记」才当成整行包裹。
_WRAPPED_LINE_RE = re.compile(
    r"^(?P<mark>\*{1,3}|_{1,3})(?=\S)(?P<inner>[^*_]+?)(?<=\S)(?P=mark)$")


def _is_bullet(line, run):
    """这个 * 是不是列表项符号（行首、且后面紧跟空白）。"""
    if run.group(0) != "*":
        return False
    if line[:run.start()].strip():
        return False
    return line[run.end():run.end() + 1] in (" ", "\t")


def _clearly_emphasis(line, opener, closer):
    """这对标记是不是「明确在强调」，而不是标识符里的下划线。

    判据是两侧都被空白/标点隔开（"binding _and_ when"）。词内的 "some_file_name"
    不算：CommonMark 本来就不把它当强调，换了反而凭空多出斜体。
    """
    before = line[opener.start() - 1] if opener.start() else " "
    after = line[closer.end():closer.end() + 1] or " "
    return not before.isalnum() and not after.isalnum()


def _protect_emphasis(md, store):
    """把成对的强调标记换成占位符（标记之间的正文照常翻译）。

    实测翻译器会吞掉/挪动 * 和 _ 这些标记，这是最容易被忽略的一类破坏：
      - "***Make sure ... recommended.***" 开头的 *** 直接消失、结尾的 *** 落进
        正文，屏幕上就成了「…文本编辑器。***」；
      - "*binding _and_ when ...*" 的两个下划线一起消失，斜体全丢；
      - "A glob like *.json and 2 * 3 math." 句中的 * 被当成标点，变成「2，3」。

    另外，明确是强调的**下划线标记一律换成星号**（_x_ -> *x*）：CommonMark 不允许
    词内的下划线强调，而翻译后中文没有空格，"_and_" 常变成「绑定_和_时」这种词内
    形态，斜体就没了；星号没有这个限制，渲染结果完全一样。

    只护**同一行内两两配对**的标记：落单的 * 多是列表项符号（"* Jump"）或句中
    乘号，一并换成占位符收益很小，却多担一份「占位符被译者丢掉、列表塌成段落」
    的风险。
    """
    out = []
    for line in md.split("\n"):
        if _WRAPPED_LINE_RE.match(line):
            # 整行包裹的标记要留给 translate_markdown 处理（剥掉再送译、译完套回），
            # 这里换成占位符它就认不出来了
            out.append(line)
            continue
        runs = [r for r in _EMPH_RUN_RE.finditer(line) if not _is_bullet(line, r)]
        if len(runs) < 2:
            out.append(line)
            continue
        buf, pos = [], 0
        for i in range(0, len(runs) - 1, 2):
            opener, closer = runs[i], runs[i + 1]
            mark = opener.group(0)
            if mark.startswith("_") and _clearly_emphasis(line, opener, closer):
                mark = "*" * len(mark)
            buf.append(line[pos:opener.start()])
            store.append(mark)
            buf.append("ZX%dZX" % (len(store) - 1))
            buf.append(line[opener.end():closer.start()])
            store.append(mark)
            buf.append("ZX%dZX" % (len(store) - 1))
            pos = closer.end()
        buf.append(line[pos:])
        out.append("".join(buf))
    return "\n".join(out)


def _protect(md):
    """把不该被改写/翻译的片段抽出来换成占位符，返回 (处理后文本, 原片段表)。

    实测翻译器会做两件破坏 Markdown 的事：
    - 把半角 () 改成全角 （），[文本](链接) 直接失效变成纯文本；
    - 把 ` 反引号改成中文引号，行内代码样式丢失，连围栏代码里的语言标记
      （```csharp）都会被当成词翻掉。
    所以先把这些片段原样存起来，翻译完再塞回去。链接/图片只护住 (...) 部分，
    外面的 [文本] 仍参与翻译。
    """
    store = []

    def _mk():
        # 用刚 append 进去的那个下标
        return f"ZX{len(store) - 1}ZX"

    def _apply(pattern, store_fn, repl_fn):
        nonlocal md

        def _r(m):
            store.append(store_fn(m))
            return repl_fn(_mk())

        md = pattern.sub(_r, md)

    # 顺序有讲究，两条都要守：
    # 1) 先整块护住围栏代码，里面的内容才不会被后面的规则误伤；
    # 2) HTML 标签必须排在裸 URL 之前。<img src="..."> 若先被裸 URL 规则把
    #    src 换成占位符，这个占位符就会嵌在标签占位符内部，形成嵌套——还原时
    #    外层换回文本后内层不会被再扫一遍，src 就变成一个死字符串，图片全丢。
    _apply(re.compile(r"```[\s\S]*?```"), lambda m: m.group(0), lambda t: t)
    _apply(re.compile(r"`[^`\n]+`"), lambda m: m.group(0), lambda t: t)
    # 整个 Markdown 图片一起护住。只护 URL 是不够的：实测翻译器会在 ! 和 [
    # 之间插空格（"![图示]" -> "! [图示]"），那就不再是图片语法，图片直接消失。
    # 代价是 alt 文字不翻译——图片标题本来也只在图挂掉时才显示，不值得为它冒
    # 整张图丢失的风险。
    _apply(re.compile(r"!\[[^\]]*\]\([^)]*\)"), lambda m: m.group(0), lambda t: t)
    # 链接只替换 ](...) 里的 (...)，保留 ] 让链接文字继续被翻译
    _apply(re.compile(r"\]\([^)]*\)"), lambda m: m.group(0)[1:], lambda t: "]" + t)
    _apply(re.compile(r"<[^>]+>"), lambda m: m.group(0), lambda t: t)
    _apply(re.compile(r"https?://[^\s)\]>]+"), lambda m: m.group(0), lambda t: t)
    # 强调标记排最后：上面的代码块、行内代码、链接地址、HTML 标签、裸 URL 都已
    # 整段换成占位符，这一步只会处理剩下的正文标记，不会误伤它们内部的 _ 和 *。
    md = _protect_emphasis(md, store)

    # 整行没有任何可译文字（只剩 ### 之类标记和占位符）时，译文本就用不上它，
    # 但译者会因为「没什么可翻的」而顺手做空白规整 —— 实测
    # "#### **`BindingManager.RegisteredBindings`**" 被改成
    # "####**`BindingManager.RegisteredBindings`**"：井号和内容之间的空格没了，
    # H4 标题直接塌成普通段落。这类行整行护起来，原文原样留到译文里。
    out_lines = []
    for line in md.split("\n"):
        bare = _TOKEN_RE.sub("", line)
        # bare.strip() 这一条是为了放行「整行本来就是个占位符」的行（例如独占一行的
        # <img>）：它们已经护好了，再套一层只会多出一层嵌套占位符
        if line.strip() and bare.strip() and not any(ch.isalpha() for ch in bare):
            store.append(line)
            out_lines.append("ZX%dZX" % (len(store) - 1))
        else:
            out_lines.append(line)
    md = "\n".join(out_lines)

    return md, store


_TOKEN_RE = re.compile(r"ZX(\d+)ZX")


def _restore(text, store):
    """把占位符换回原始片段。

    多轮替换直到不再变化：re.sub 不会重新扫描替换进去的内容，万一某个片段
    里还嵌着另一个占位符（嵌套），单轮替换会把它留成死字符串。这里循环兜底，
    并用轮数上限防止片段自引用时无限展开。
    """
    def _r(m):
        i = int(m.group(1))
        return store[i] if 0 <= i < len(store) else m.group(0)

    for _ in range(5):
        new_text = _TOKEN_RE.sub(_r, text)
        if new_text == text:
            break
        text = new_text
    return text


def _repair(text):
    """收紧翻译器塞在 `]` 与 `(` 之间的空格。

    Markdown 要求 ] 和 ( 紧邻，中间一有空格链接/图片地址就失效。
    只修括号里像地址的内容（含 / 或 .），否则会把 "[1, 2, 3] (ordered)"
    这类正常文本误改成链接。
    """
    return re.sub(r"\]\s+\(([^\s)]*[/.][^\s)]*)\)", r"](\1)", text)


def _chunk_lines(lines):
    """把行序列切成若干块：每块累计字符不超过 _MAX_CHARS，行数不超过
    _MAX_BATCH。连续行放同一块，让译者能看到整段上下文，而不是逐行硬翻。"""
    chunks = []
    cur = []
    cur_len = 0
    for line in lines:
        add = len(line) + 1
        if cur and (cur_len + add > _MAX_CHARS or len(cur) >= _MAX_BATCH):
            chunks.append(cur)
            cur = []
            cur_len = 0
        cur.append(line)
        cur_len += add
    if cur:
        chunks.append(cur)
    return chunks


def translate_markdown(markdown, target=DEFAULT_TARGET, timeout=20):
    """翻译 Markdown 文本，尽量保留原有行结构与图片。

    代码块、行内代码、链接/图片地址、HTML 标签、行内强调标记会先被占位符保护起来
    再送译，翻完原样塞回——否则翻译器会把半角 () 改全角、把反引号改中文引号、
    把强调标记吞掉，轻则样式丢失，重则链接失效、图片地址被改成不存在的地址。

    整行被强调标记包起来的行（***粗斜体*** / **粗体** / _斜体_）另作处理：连同
    标记一起送译的话，译者会在标记之间挪动文字 —— 实测
    "***A robust text editor like ... is highly recommended.***" 会译成
    「…文本编辑器***A。***」（原文里的 "A" 被甩到句尾、还套进了标记里）。
    所以这类行剥掉标记单独送译，译完再按原文套回去。
    """
    if not markdown or not markdown.strip():
        return markdown

    protected, store = _protect(markdown)
    lines = protected.split("\n")

    # 整行被强调标记包起来的行：先把标记剥掉（标记本身不该参与翻译），译完再套回
    wraps = {}
    for i, line in enumerate(lines):
        m = _WRAPPED_LINE_RE.match(line)
        if m:
            wraps[i] = m.group("mark")
            lines[i] = m.group("inner")

    out_lines = []
    consumed = 0
    for chunk in _chunk_lines(lines):
        start = consumed          # 这一块第一行在 lines 里的下标
        consumed += len(chunk)
        # 纯空白块（连续空行）不值得发请求，原样保留
        if not any(s.strip() for s in chunk):
            out_lines.extend(chunk)
            continue
        translated = _post_batch(["\n".join(chunk)], target, timeout=timeout)[0]
        # 直接按译者产出的行拼回。早先这里在行数不一致时会把整块压成一行
        # （换行替换成空格），结果独占一行的 <img> 被并进段落里渲染不出来，
        # 列表/代码块也会被揉成一团。行数对不上不影响拼接，保留原样更安全。
        parts = translated.split("\n")
        if len(parts) == len(chunk):
            # 行数没变才敢按下标套回标记；变了就宁可少一处加粗，也不错位到别的行
            for j, text in enumerate(parts):
                mark = wraps.get(start + j)
                if not mark:
                    continue
                # 原文里这一行的内层不含 * 和 _（_WRAPPED_LINE_RE 限定了），
                # 所以译文里出现的星号/下划线只可能来自译者自己吐回来的标记，清掉
                inner = re.sub(r"[*_]", "", text).strip()
                if inner:
                    parts[j] = mark + inner + mark
        out_lines.extend(parts)

    return _repair(_restore("\n".join(out_lines), store))
