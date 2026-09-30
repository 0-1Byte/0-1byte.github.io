"""合集页优化后的数据完整性核对：原有字段零改动，只新增 img。"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    "book": "books.json",
    "docu": "docus.json",
    "film": "films.json",
    "tv": "tvs.json",
}
BASE_COMMIT = "e447829"   # Music 优化之前、也是这些合集页最后一次改动的状态

ok = bad = 0


def check(label, cond, detail=""):
    global ok, bad
    if cond:
        ok += 1
    else:
        bad += 1
    print(f"  [{'✓' if cond else '✗'}] {label}{(' — ' + detail) if detail else ''}")


for page, name in PAGES.items():
    rel = f"static/{page}/{name}"
    old_raw = subprocess.run(["git", "show", f"{BASE_COMMIT}:{rel}"],
                             cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout
    old = json.loads(old_raw)
    new = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    print(f"\n--- {page} / {name} ---")

    check("条目数一致", len(old) == len(new), f"{len(old)} -> {len(new)}")
    diffs = []
    for a, b in zip(old, new):
        for k in a:
            if a.get(k) != b.get(k):
                diffs.append(f"{a.get('id')}.{k}")
    check("所有原有字段零改动", not diffs, f"{len(diffs)} 处" + ("" if not diffs else f": {diffs[:3]}"))
    check("新增字段仅为 img", all(set(b) - set(a) <= {"img"} for a, b in zip(old, new)))
    imgs = [it.get("img") for it in new if it.get("img")]
    check("img 已写入", len(imgs) > 0, f"{len(imgs)} 条")
    check("img 命名 URL 安全", all(" " not in i and "%" not in i for i in imgs))
    check("cover 字段原样保留", all(a.get("cover") == b.get("cover") for a, b in zip(old, new)))

# 封面文件完整性
print("\n--- 衍生图档位完整性 ---")
for page, name in PAGES.items():
    base = ROOT / "static" / page
    items = json.loads((base / name).read_text(encoding="utf-8"))
    optdir = base / "covers" / "opt"
    missing = []
    for it in items:
        b = it.get("img")
        if not b:
            continue
        for w in (240, 320, 480):
            if not (optdir / f"{b}-{w}.webp").exists():
                missing.append(f"{b}-{w}.webp")
    check(f"{page} 每个主干三档齐全", not missing, f"缺失 {len(missing)}")

print("\n--- 页面脚本接入情况 ---")
for page, _ in PAGES.items():
    html = (ROOT / "static" / page / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / page / "script.js").read_text(encoding="utf-8")
    check(f"{page} 引入 covers.js", "/covers.js" in html)
    check(f"{page} covers.js 在页面脚本之前",
          html.find("/covers.js") < html.find(f"/{page}/script.js"))
    check(f"{page} preload 数据文件", f'rel="preload"' in html and f'{page}/' in html and "as=\"fetch\"" in html)
    check(f"{page} 不再用 Date.now 破缓存", "Date.now()" not in js)
    check(f"{page} 不再用 no-store", 'no-store' not in js)
    check(f"{page} 使用 buildCoverImg", "buildCoverImg" in js)
    check(f"{page} 接上 JPG 兜底", "bindCoverJpgFallback" in js)

print("\n" + "=" * 70)
print(f"通过 {ok} 项，失败 {bad} 项")
