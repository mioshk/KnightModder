import sys
sys.path.insert(0, ".")
import config as cfg

print("=== 手动刷新(bust_cache) 实际尝试顺序 ===")
fresh = list(cfg.MODLINKS_FRESH_URLS)
rest = [u for u in cfg.MODLINKS_URLS if u not in fresh]
for i, u in enumerate(fresh + rest):
    tag = "实时源" if u in fresh else "CDN兜底"
    print(f"{i+1}. [{tag}] {u}")

print()
print("=== 自动加载 顺序 ===")
for i, u in enumerate(cfg.MODLINKS_URLS):
    print(f"{i+1}. {u}")
