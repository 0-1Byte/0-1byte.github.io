"""阶段 2 审计：收集所有页面现有的颜色 / 圆角 / 动效 / 变量取值。

只读，不改文件。目的是把「现状」变成可核对的清单，
据此建立统一设计系统，并保证重构后取值等价。
"""
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

CSS_FILES = [
    ROOT / "assets/css/extended/custom.css",
    STATIC / "collection-states.css",
    STATIC / "back-to-top.css",
] + [STATIC / p / "style.css" for p in ("music", "book", "works", "docu", "film", "tv")]

print("=" * 100)
print("1. 每个文件里声明的 CSS 变量（:root / [data-theme=dark]）")
print("=" * 100)
for f in CSS_FILES:
    if not f.exists():
        continue
    src = f.read_text(encoding="utf-8")
    blocks = re.findall(r"(:root(?:\[data-theme=\"dark\"\])?(?:,\s*html\[data-theme=\"dark\"\])?)\s*\{([^}]*)\}", src)
    rel = str(f.relative_to(ROOT)).replace("\\", "/")
    print(f"\n--- {rel} ---")
    if not blocks:
        print("    (无变量声明)")
    for sel, body in blocks:
        decls = re.findall(r"(--[\w-]+)\s*:\s*([^;]+)", body)
        print(f"    {sel.strip()}")
        for name, val in decls:
            print(f"        {name:22} {val.strip()}")

print()
print("=" * 100)
print("2. 所有硬编码颜色（去重统计，用于判断哪些需要收进变量）")
print("=" * 100)
color_re = re.compile(r"#(?:[0-9a-fA-F]{3,8})\b|rgba?\([^)]*\)")
per_file = {}
all_colors = defaultdict(int)
for f in CSS_FILES:
    if not f.exists():
        continue
    src = f.read_text(encoding="utf-8")
    found = color_re.findall(src)
    per_file[f] = found
    for c in found:
        all_colors[c] += 1

rel_name = lambda p: str(p.relative_to(ROOT)).replace("\\", "/")
for f, found in per_file.items():
    uniq = sorted(set(found))
    print(f"\n--- {rel_name(f)} --- 共 {len(found)} 处，去重 {len(uniq)}")
    for c in uniq:
        print(f"    {c:34} ×{found.count(c)}")

print()
print("=" * 100)
print("3. 圆角取值分布")
print("=" * 100)
radius = defaultdict(list)
for f in CSS_FILES:
    if not f.exists():
        continue
    src = f.read_text(encoding="utf-8")
    for m in re.finditer(r"border-radius\s*:\s*([^;]+)", src):
        radius[m.group(1).strip()].append(rel_name(f))
for val, files in sorted(radius.items(), key=lambda kv: -len(kv[1])):
    print(f"    {val:24} ×{len(files):2}   {sorted(set(files))}")

print()
print("=" * 100)
print("4. 过渡与动效取值")
print("=" * 100)
trans = defaultdict(int)
for f in CSS_FILES:
    if not f.exists():
        continue
    src = f.read_text(encoding="utf-8")
    for m in re.finditer(r"transition\s*:\s*([^;]+)", src):
        trans[m.group(1).strip()] += 1
for val, n in sorted(trans.items(), key=lambda kv: -kv[1]):
    print(f"    ×{n}  {val}")

print()
print("=" * 100)
print("5. 强调色 / 渐变使用情况（判断品牌色是否属于高饱和）")
print("=" * 100)
for f in CSS_FILES:
    if not f.exists():
        continue
    src = f.read_text(encoding="utf-8")
    for m in re.finditer(r"linear-gradient\([^;]+\)", src):
        print(f"    {rel_name(f):44} {m.group(0)[:78]}")
