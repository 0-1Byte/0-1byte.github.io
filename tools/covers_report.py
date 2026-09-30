"""合集页封面优化的体积对比 + 未引用文件盘点。"""
import hashlib
import json
import subprocess
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    "book": ("books.json", "covers"),
    "docu": ("docus.json", "covers"),
    "film": ("films.json", "covers"),
    "tv": ("tvs.json", "covers"),
}
# 各页 CSS：2:3 竖版封面，桌面四列约 235x353
SIZES = ["桌面1x", "桌面2x", "手机3x"]
WIDTHS = {"桌面1x": 240, "桌面2x": 480, "手机3x": 320}


def mb(n):
    return n / 1048576


def kb(n):
    return n / 1024


print("=" * 78)
print("合集页封面：优化前后对比")
print("=" * 78)
grand_before = grand_after = 0

for page, (json_name, cover_dir_name) in PAGES.items():
    base = ROOT / "static" / page
    items = json.loads((base / json_name).read_text(encoding="utf-8"))
    cdir = base / cover_dir_name
    optdir = cdir / "opt"

    local = [it for it in items if it.get("cover") and not str(it["cover"]).startswith("http")]
    remote = [it for it in items if it.get("cover") and str(it["cover"]).startswith("http")]

    before = 0
    for it in local:
        rel = unquote(it["cover"])
        for p in ("covers/", "./covers/"):
            if rel.startswith(p):
                rel = rel[len(p):]
                break
        f = cdir / rel
        if f.exists():
            before += f.stat().st_size

    bases = sorted({it["img"] for it in items if it.get("img")})
    after = {w: 0 for w in WIDTHS}
    for b in bases:
        for label, w in WIDTHS.items():
            f = optdir / f"{b}-{w}.webp"
            if f.exists():
                after[label] += f.stat().st_size

    grand_before += before
    grand_after += after["桌面2x"]

    print(f"\n--- {page.upper()} --- 条目 {len(items)}（远程 {len(remote)}）  唯一封面 {len(bases)}")
    print(f"  优化前（原图）        : {mb(before):7.2f} MB")
    for label in SIZES:
        a = after[label]
        pct = (1 - a / before) * 100 if before else 0
        print(f"  优化后 {label:<8}({WIDTHS[label]}w): {mb(a):7.2f} MB   降幅 {pct:5.1f}%")
    if remote:
        print(f"  注：{len(remote)} 个远程封面无法本地优化，页面仍直接加载原图")

print()
print("=" * 78)
print(f"四个合集页合计：优化前 {mb(grand_before):.2f} MB  ->  桌面2x 口径 {mb(grand_after):.2f} MB"
      f"  （降幅 {(1-grand_after/grand_before)*100:.1f}%）")
print("=" * 78)

# ---------------- 未引用文件盘点 ----------------
print("\n未引用文件盘点（covers 目录中未被数据文件引用的图片）")
print("-" * 78)
for page, (json_name, cover_dir_name) in PAGES.items():
    base = ROOT / "static" / page
    items = json.loads((base / json_name).read_text(encoding="utf-8"))
    cdir = base / cover_dir_name
    used = set()
    for it in items:
        cover = it.get("cover")
        if not cover or str(cover).startswith("http"):
            continue
        rel = unquote(cover)
        for p in ("covers/", "./covers/"):
            if rel.startswith(p):
                rel = rel[len(p):]
                break
        used.add(rel)

    files = {p.name: p for p in cdir.iterdir() if p.is_file() and p.parent == cdir}
    unused = {n: p for n, p in files.items() if n not in used}
    if not unused:
        print(f"  {page:6} 无未引用文件")
        continue

    # 用内容哈希判断：哪些未引用文件其实和某个"在用"文件内容相同（纯重复，可安全删）
    hash_used = {}
    for n in used:
        if n in files:
            hash_used.setdefault(hashlib.sha256(files[n].read_bytes()).hexdigest(), n)
    pure_dup, orphan = [], []
    for n, p in sorted(unused.items()):
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        (pure_dup if h in hash_used else orphan).append((n, p.stat().st_size))
    print(f"  {page:6} 未引用 {len(unused)} 个，合计 {mb(sum(s for _, s in unused.values() if True) if False else sum(p.stat().st_size for p in unused.values())):.2f} MB")
    print(f"          其中内容重复(可安全删) {len(pure_dup)} 个 / {kb(sum(s for _, s in pure_dup)):.0f} KB")
    print(f"          内容独有(不是重复)     {len(orphan)} 个 / {kb(sum(s for _, s in orphan)):.0f} KB")
    for n, s in orphan[:6]:
        print(f"             · {n}  ({kb(s):.0f} KB)")
