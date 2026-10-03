import urllib.request

cands = {
    "gcore": "https://gcore.jsdelivr.net/gh/mioshk/KnightModder@main/ModLinksCN.xml",
    "gitmirror": "https://raw.gitmirror.com/mioshk/KnightModder/main/ModLinksCN.xml",
    "ghproxy": "https://ghproxy.net/https://raw.githubusercontent.com/mioshk/KnightModder/refs/heads/main/ModLinksCN.xml",
}
for name, u in cands.items():
    req = urllib.request.Request(u, headers={"User-Agent": "kmbg"})
    try:
        r = urllib.request.urlopen(req, timeout=20)
        h = r.headers
        etag = h.get("etag", "-")
        age = h.get("age", "-")
        xc = h.get("x-cache", h.get("x-jsd-cache", "-"))
        print(f"{name:10} OK  status={r.status} etag={etag[:20]} age={age} xcache={xc} len={h.get('content-length', '-')}")
    except Exception as e:
        print(f"{name:10} FAIL {type(e).__name__}: {str(e)[:90]}")
