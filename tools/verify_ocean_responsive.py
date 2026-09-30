"""阶段 5 响应式：/ocean/ 在 6 个视口下的关键几何关系。

无法在沙箱里真正渲染，因此按 CSS 里的实际取值做几何核对：
  · 海平线位置（≤600px 时为 0.50，否则 0.58）
  · 光点位置应紧贴海平线下方
  · 底部入口不应与光点重叠
  · header 不应压住光点

另外核对导航宽度预算（standalone 已增至 3 个：writing / random / ocean）。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "ocean" / "style.css").read_text(encoding="utf-8")

problems = []

# 从 CSS 里读出真实取值，避免脚本里硬编码与样式漂移
horizon_desktop = float(re.search(r"--ocean-horizon:\s*([\d.]+);", CSS).group(1))
mobile_block = re.search(r"@media \(max-width: 600px\)\s*\{(.*?)\n\}", CSS, re.S)
horizon_mobile = float(re.search(r"--ocean-horizon:\s*([\d.]+);", mobile_block.group(1)).group(1))
light_offset = float(re.search(r"top:\s*calc\(var\(--ocean-horizon\)\s*\+\s*([\d.]+)%\)", CSS).group(1))

print("=" * 84)
print("CSS 取值")
print("=" * 84)
print(f"  海平线（桌面）: {horizon_desktop}")
print(f"  海平线（≤600）: {horizon_mobile}")
print(f"  光点相对海平线下移: {light_offset}%")

VIEWPORTS = [
    ("1920", 1920, 1080), ("1440", 1440, 900), ("1366", 1366, 768),
    ("600", 600, 900), ("430", 430, 932), ("375", 375, 667),
]

print()
print("=" * 84)
print("A. 光点与海平线的几何关系")
print("=" * 84)
print(f"  {'视口':>6} {'高':>5} {'海平线y':>8} {'光点y':>7} {'底部入口区':>10}  结论")
for label, vw, vh in VIEWPORTS:
    mobile = vw <= 600
    h = horizon_mobile if mobile else horizon_desktop
    horizon_y = vh * h
    light_y = vh * (h + light_offset / 100)
    bottom = 28 if mobile else 40
    links_reserve = bottom + 22 + 20   # padding + 入口高度
    gap = vh - links_reserve - light_y
    ok = gap > 40
    if not ok:
        problems.append(f"{label}: 光点与底部入口只差 {gap:.0f}px，可能重叠")
    print(f"  {label:>6} {vh:>5} {horizon_y:>8.0f} {light_y:>7.0f} {vh-links_reserve:>10.0f}  "
          f"{'OK（间距 %.0fpx）' % gap if ok else '★ 过近 %.0fpx' % gap}")

print()
print("=" * 84)
print("B. header 与光点不应重叠")
print("=" * 84)
HEADER_H = 68
for label, vw, vh in VIEWPORTS:
    mobile = vw <= 600
    h = horizon_mobile if mobile else horizon_desktop
    light_y = vh * (h + light_offset / 100)
    ok = light_y > HEADER_H + 20
    if not ok:
        problems.append(f"{label}: 光点 y={light_y:.0f} 太靠近 header({HEADER_H})")
    print(f"  {'OK ' if ok else 'FAIL'} {label:>6}  光点 y={light_y:>6.0f}  header 高={HEADER_H}")

print()
print("=" * 84)
print("C. 导航宽度预算（standalone 已增至 writing/random/ocean）")
print("=" * 84)
GUTTER_D = 48
GUTTER_M = 28
GROUPS = ["listen", "read", "watch", "make"]
STANDALONE = ["writing", "random", "ocean"]


def text_w(s, size):
    return sum(size * (1.0 if ord(c) > 0x2000 else 0.55) for c in s)


print(f"  {'视口':>6} {'可用宽':>7} {'需要宽':>7}  结论")
for label, vw, vh in VIEWPORTS:
    mobile = vw <= 600
    gutter = GUTTER_M if mobile else GUTTER_D
    avail = vw - gutter * 2
    size = 17 if mobile else 22
    gap = 16 if mobile else 26
    logo = 48 if mobile else 62
    toggle = 38 if mobile else 44
    items = GROUPS + STANDALONE
    need = logo + gap + sum(text_w(t, size) for t in items) + gap * (len(items) - 1) + toggle
    ok = need <= avail
    scrollable = vw <= 600
    verdict = "放得下" if ok else ("横向滚动（已启用 overflow-x）" if scrollable else "★ 溢出")
    if not ok and not scrollable:
        problems.append(f"{label}: 导航需要 {need:.0f} 超出可用 {avail}")
    print(f"  {label:>6} {avail:>7} {need:>7.0f}  {verdict}")

print()
print("=" * 84)
print(f"硬性问题: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 无溢出 / 无重叠")
print("=" * 84)
