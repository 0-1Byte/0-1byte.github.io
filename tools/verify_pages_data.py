"""六个合集页的数据与渲染前置条件核对。

在「主题按钮被误删导致脚本崩溃」这次事故之后新增：
除了看数据条数，还要确认每个页面脚本在调用加载函数之前
没有任何会在 null 上抛错的操作。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUB = ROOT / "public"
SRC = ROOT / "static"
problems = []

PAGES = [
    ("music", "music/songs.json", "歌曲"),
    ("book", "book/books.json", "书籍"),
    ("film", "film/films.json", "电影"),
    ("tv", "tv/tvs.json", "剧集"),
    ("docu", "docu/docus.json", "纪录片"),
    ("works", "works/works.json", "作品"),
]

print("=" * 80)
print("1. 数据条数")
print("=" * 80)
for page, rel, label in PAGES:
    p = PUB / rel
    if not p.exists():
        problems.append(f"{rel} 产物缺失")
        print(f"  FAIL {page:6} {rel} 缺失")
        continue
    items = json.loads(p.read_text(encoding="utf-8"))
    ok = isinstance(items, list) and len(items) > 0
    if not ok:
        problems.append(f"{rel} 不是非空数组")
    print(f"  {'OK ' if ok else 'FAIL'} {page:6} {label:5} {len(items):4} 条")

print()
print("=" * 80)
print("2. 页面脚本的崩溃风险（这次事故的直接原因）")
print("=" * 80)
# 形如 getElementById("x").addEventListener(...) 的链式调用：
# 元素不存在时会在 null 上抛错，并中断同一轮脚本里后面的加载调用。
RISKY = re.compile(r'getElementById\(\s*["\']([^"\']+)["\']\s*\)\s*\.\s*\w+')
for page, _, _ in PAGES:
    f = SRC / page / "script.js"
    src = f.read_text(encoding="utf-8")
    hits = RISKY.findall(src)
    ok = not hits
    if not ok:
        problems.append(f"{page}/script.js 有链式调用 {hits}")
    print(f"  {'OK ' if ok else 'FAIL'} {page:6} 链式 getElementById 调用 = {len(hits)}"
          + (f"  -> {hits}" if hits else ""))

print()
print("=" * 80)
print("3. 加载调用必须存在（脚本尾部的那句）")
print("=" * 80)
LOADCALL = re.compile(r"^\s*(?:load\w*|boot|init)\s*\(\s*\)\s*;", re.M)
for page, _, _ in PAGES:
    src = (SRC / page / "script.js").read_text(encoding="utf-8")
    hits = LOADCALL.findall(src)
    ok = bool(hits)
    if not ok:
        problems.append(f"{page}/script.js 缺少加载调用")
    print(f"  {'OK ' if ok else 'FAIL'} {page:6} 找到 {len(hits)} 处加载调用")

print()
print("=" * 80)
print("4. 页面 HTML 里的关键元素必须在（脚本会去找它们）")
print("=" * 80)
NEED = {
    "music": ["song-grid", "song-count", "error"],
    "book": ["book-grid", "book-count", "error"],
    "film": ["film-grid", "film-count", "error"],
    "tv": ["tv-grid", "tv-count", "error"],
    "docu": ["docu-grid", "docu-count", "error"],
    "works": ["works-grid", "works-count", "toolbar", "search", "drawer", "error"],
}
for page, ids in NEED.items():
    html = (PUB / page / "index.html").read_text(encoding="utf-8")
    missing = [i for i in ids if f'id="{i}"' not in html and f"id={i}" not in html]
    ok = not missing
    if not ok:
        problems.append(f"{page}/index.html 缺少元素 {missing}")
    print(f"  {'OK ' if ok else 'FAIL'} {page:6} 缺少 {missing or '无'}")

print()
print("=" * 80)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 数据完整、无崩溃风险、加载调用与关键元素都在")
print("=" * 80)
sys.exit(1 if problems else 0)
