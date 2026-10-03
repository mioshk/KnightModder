import urllib.request

u = "https://gitee.com/MioAmore/KnightModder/raw/master/ModLinksCN.xml"
req = urllib.request.Request(u, headers={"User-Agent": "kmbg", "Referer": "https://gitee.com/"})
try:
    r = urllib.request.urlopen(req, timeout=20)
    data = r.read()
    ct = r.headers.get("content-type", "-")
    head = data[:60]
    print(f"OK  {r.status} ct={ct} len={len(data)}")
    print(f"first bytes: {head!r}")
    # 粗略判断是不是 XML（不是登录页 HTML）
    txt = data[:200].decode("utf-8", "ignore")
    if "<ModLinks" in txt or "<?xml" in txt:
        print("看起来是合法 XML ✅")
    else:
        print("⚠️ 可能不是 XML（疑似登录页/HTML），需排查")
except Exception as e:
    print(f"FAIL {type(e).__name__}: {str(e)[:120]}")
