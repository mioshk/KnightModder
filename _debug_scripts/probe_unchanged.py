import sys, os
sys.path.insert(0, ".")

import core.installer as inst

FAKE = b'<?xml version="1.0"?><ModLinks><Mod name="A"/></ModLinks>'

class FakeResp:
    def __init__(self, status, content=b"", etag=None):
        self.status_code = status
        self.content = content
        self.headers = {"ETag": etag} if etag else {}
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

resolver = inst.DependencyResolver()
cf = resolver._cache_file()
for p in (cf, resolver._etag_file()):
    if os.path.isfile(p):
        os.remove(p)

# 基线：先写入一份缓存（模拟首次成功拉取）
resolver.save_cache(FAKE)
print("基线: cache 已写入")

scenarios = {
    "304未变更":       lambda u, **kw: FakeResp(304, etag='"v1"'),
    "内容相同(无304)":  lambda u, **kw: FakeResp(200, FAKE, etag='"v1"'),
    "内容变了":        lambda u, **kw: FakeResp(200, FAKE + b"<!--x-->", etag='"v2"'),
}
for name, fn in scenarios.items():
    inst.safe_requests_get = fn
    ok = resolver.load_from_url(progress_callback=None, bust_cache=True)
    # 读取缓存内容以确认是否被覆盖
    with open(cf, "rb") as f:
        cached = f.read()
    print(f"{name:14} -> ok={ok} changed={resolver._last_fetch_changed} cache_is_FAKE={cached==FAKE}")
