import urllib.request

# 用几个公开 Gitee 仓库的 raw 文件探连通性，确认国内直连 + 返回真实内容（非登录页）
tests = [
    "https://gitee.com/mirror/gh_mirror/raw/master/README.md",
    "https://gitee.com/ant-design/ant-design/raw/master/README.md",
    "https://gitee.com/lenovo-kernel-ci/linux/raw/master/README",
]
for u in tests:
    req = urllib.request.Request(u, headers={"User-Agent": "kmbg", "Referer": "https://gitee.com/"})
    try:
        r = urllib.request.urlopen(req, timeout=20)
        data = r.read(200)
        ct = r.headers.get("content-type", "-")
        print(f"OK  {r.status} ct={ct} first={data[:40]!r}  <- {u.split('/raw/')[0]}")
    except Exception as e:
        print(f"FAIL {type(e).__name__}: {str(e)[:90]}  <- {u}")
