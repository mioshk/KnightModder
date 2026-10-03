import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as c

fresh = list(c.MODLINKS_FRESH_URLS)
rest = [u for u in c.MODLINKS_URLS if u not in fresh]
order = fresh + rest

print("=== load_from_url 统一尝试顺序（启动 = 更新链接按钮，完全一致）===")
for i, u in enumerate(order):
    tag = "实时源" if u in fresh else "jsDelivr/CDN 兜底"
    print(f"  {i+1}. [{tag}] {u}")

jd_pos = [order.index(u) + 1 for u in order if "jsdelivr.net" in u]
fresh_pos = [order.index(u) + 1 for u in order if u in fresh]
print(f"\n实时源位置: {fresh_pos}  (1..{len(fresh)})")
print(f"jsDelivr 兜底位置: {jd_pos}  (全部 > {len(fresh)} => 仅当实时源全失败时尝试) ✓" if all(p > len(fresh) for p in jd_pos) else "✗ jsDelivr 不在兜底位")
