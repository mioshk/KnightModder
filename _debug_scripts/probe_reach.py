import urllib.request, time

cands = {
    'raw.githubusercontent.com': 'https://raw.githubusercontent.com/mioshk/KnightModder/refs/heads/main/ModLinksCN.xml',
    'raw.gitmirror.com':         'https://raw.gitmirror.com/mioshk/KnightModder/main/ModLinksCN.xml',
    'ghproxy.net':               'https://ghproxy.net/https://raw.githubusercontent.com/mioshk/KnightModder/refs/heads/main/ModLinksCN.xml',
    'mirror.ghproxy.com':        'https://mirror.ghproxy.com/https://raw.githubusercontent.com/mioshk/KnightModder/refs/heads/main/ModLinksCN.xml',
    'fastly.jsdelivr.net (对照)': 'https://fastly.jsdelivr.net/gh/mioshk/KnightModder@main/ModLinksCN.xml',
}

for name, u in cands.items():
    req = urllib.request.Request(u, headers={'User-Agent': 'kmbg-probe'})
    t0 = time.time()
    try:
        r = urllib.request.urlopen(req, timeout=15)
        dt = (time.time() - t0) * 1000
        print(f'{name:26} OK  status={r.status} len={r.headers.get("content-length","-"):>8}  {dt:5.0f}ms  etag={r.headers.get("etag","-")[:20]}')
    except Exception as e:
        dt = (time.time() - t0) * 1000
        print(f'{name:26} FAIL ({dt:5.0f}ms) {type(e).__name__}: {str(e)[:70]}')
