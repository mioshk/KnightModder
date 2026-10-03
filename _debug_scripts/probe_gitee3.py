import urllib.request

def head(u, ref=None):
    h = {"User-Agent": "Mozilla/5.0", "Referer": ref or "https://gitee.com/"}
    req = urllib.request.Request(u, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=20)
        return f"OK {r.status} ct={r.headers.get('content-type','-')} len={r.headers.get('content-length','-')}"
    except Exception as e:
        return f"FAIL {type(e).__name__}: {str(e)[:100]}"

print("仓库主页        :", head("https://gitee.com/MioAmore/KnightModder"))
print("raw master       :", head("https://gitee.com/MioAmore/KnightModder/raw/master/ModLinksCN.xml"))
print("raw main         :", head("https://gitee.com/MioAmore/KnightModder/raw/main/ModLinksCN.xml"))
print("blob master 页面 :", head("https://gitee.com/MioAmore/KnightModder/blob/master/ModLinksCN.xml"))
