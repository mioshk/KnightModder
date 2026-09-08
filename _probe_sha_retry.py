# -*- coding: utf-8 -*-
"""临时：验证 sha 不符自动强制重转存重试 + .part 防护（用完即删）"""
import os
import sys
import hashlib
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core.online_install as oi
from core.quark import QuarkClient

dl = tempfile.mkdtemp()
oi.get_download_dir = lambda: dl
LOGS = []

OLD, NEW = b"OLD-PACKAGE", b"NEW-PACKAGE"
SHA_NEW = hashlib.sha256(NEW).hexdigest().upper()


class DlStub:
    """第一次（普通）产出旧包；force_transfer=True 时产出新包"""

    def __init__(self, **kw):
        self.ft_flags = []
        self.is_logged_in = True

    def download_share(self, url, local_dir, remote_dir_name="", passcode="",
                       select_file=None, return_files=False, force_transfer=False):
        self.ft_flags.append(force_transfer)
        p = os.path.join(local_dir, "A.zip")
        with open(p, "wb") as f:
            f.write(NEW if force_transfer else OLD)
        return local_dir, [p]


orig_client = oi.QuarkClient
oi.QuarkClient = DlStub

try:
    res = oi._download_and_verify(
        cookie="x", game_path=tempfile.mkdtemp(),
        mod_info={"name": "A", "link": "https://pan.quark.cn/s/x", "sha256": SHA_NEW},
        log=lambda m, l="info": LOGS.append((l, m)),
    )
    print(f"1. sha 不符自愈重试: force_transfer 序列={DlStub.__init__ and res and 'ok'}")
    print(f"   最终内容={open(res['zip'], 'rb').read()}（应为 {NEW}）")
finally:
    oi.QuarkClient = orig_client
LOGS.clear()

# 2) 校验失败且重试仍不符 -> 必须报错中止
class AlwaysOld(DlStub):
    def download_share(self, *a, **k):
        p = os.path.join(k.get("local_dir") or a[1], "A.zip")
        with open(p, "wb") as f:
            f.write(OLD)
        return (k.get("local_dir") or a[1]), [p]


oi.QuarkClient = AlwaysOld
try:
    oi._download_and_verify(
        cookie="x", game_path=tempfile.mkdtemp(),
        mod_info={"name": "A", "link": "https://pan.quark.cn/s/x", "sha256": SHA_NEW},
        log=lambda m, l="info": LOGS.append((l, m)),
    )
    print("2. 重试仍不符: >>> 没有报错（不符合预期）")
except Exception as e:
    print(f"2. 重试仍不符: 正确中止 -> {e}")
finally:
    oi.QuarkClient = orig_client
LOGS.clear()

# 3) 残留 .part 比新版本大 -> 丢弃重下，不追加
qp = QuarkClient.__new__(QuarkClient)
part = os.path.join(dl, "B.zip.part")
open(part, "wb").write(b"X" * 500)
seen = {}


class Resp:
    status_code = 200
    headers = {"content-length": "3"}
    def iter_content(self, chunk_size=1):
        yield b"abc"


class Session:
    def get(self, url, headers=None, stream=False, timeout=None):
        seen["range"] = (headers or {}).get("range")
        return Resp()


qp.session = Session()
qp.timeout = 5
qp.progress_callback = lambda *a: None
out = qp.download_file("http://x/B.zip", os.path.join(dl, "B.zip"), expect_size=3)
size = os.path.getsize(out)
print(f"3. .part 防护: 残留丢弃={not os.path.exists(part)}, 内容={open(out,'rb').read()}, "
      f"最终大小={size}（应为 3 而不是 503）")

print("PROBE_DONE")
