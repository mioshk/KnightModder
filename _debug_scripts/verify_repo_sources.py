import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as c

for p in ("version.json", "README.md", "USAGE.md"):
    srcs = c.repo_file_sources(p)
    fresh = srcs[:3]
    jsd = srcs[3:]
    print(f"=== {p} ===")
    for i, u in enumerate(srcs, 1):
        tag = "实时" if i <= 3 else "兜底"
        print(f"  {i}. [{tag}] {u}")
    ok = all("jsdelivr.net" in u for u in jsd) and all("jsdelivr.net" not in u for u in fresh)
    print("  顺序正确(实时在前/jsDelivr 兜底):", ok, "\n")
