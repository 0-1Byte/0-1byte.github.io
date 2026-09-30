"""检查 /random/ 与含 random 的导航在 5 个视口下是否溢出。

按 tools/verify_ia_responsive.py 相同的算法估算：
  可用宽度 = 视口宽 - 页面两侧留白
  需要宽度 = logo + gap + 各分组文字宽 + 分组间 gap + 主题按钮占位
中文字宽按 字号 计，拉丁按 字号 * 0.55 计（与既有脚本一致）。
"""
from pathlib import Path

# 与 static/site-nav.css 的实际值保持一致
GUTTER_DESKTOP = 48
GUTTER_MOBILE = 28
LOGO_60 = 62          # "Chen" 手写体 36px 的近似宽度
LOGO_48 = 48          # 移动端 28px
TOGGLE_SPACE = 44     # .header-nav 的 padding-right
TOGGLE_SPACE_M = 38

GROUPS = ["listen", "read", "watch", "make"]
STANDALONE = ["writing", "random"]


def text_w(s, size):
    w = 0.0
    for ch in s:
        w += size * (1.0 if ord(ch) > 0x2000 else 0.55)
    return w


VIEWPORTS = [
    ("1920", 1920, False),
    ("1440", 1440, False),
    ("1366", 1366, False),
    ("600", 600, False),
    ("430", 430, True),
    ("375", 375, True),
]

print("=" * 82)
print("导航宽度预算（含新增的 random 入口）")
print("=" * 82)
print(f"  {'视口':>6}  {'可用宽':>7}  {'导航需要':>8}  {'logo':>5}  {'空余':>7}  结论")
problems = 0
for label, vw, mobile in VIEWPORTS:
    gutter = GUTTER_MOBILE if mobile else GUTTER_DESKTOP
    avail = vw - gutter * 2
    size = 17 if vw <= 600 else 22
    gap = 16 if vw <= 600 else 26
    logo = LOGO_48 if vw <= 600 else LOGO_60
    toggle = TOGGLE_SPACE_M if vw <= 600 else TOGGLE_SPACE

    items = GROUPS + STANDALONE
    need = sum(text_w(t, size) for t in items) + gap * (len(items) - 1)
    total = logo + gap + need + toggle
    free = avail - total
    ok = free >= 0
    # 移动端 ≤600px 时导航可横向滚动，允许紧张
    scrollable = vw <= 600
    verdict = "放得下" if ok else ("横向滚动（已启用 overflow-x）" if scrollable else "★ 溢出")
    if not ok and not scrollable:
        problems += 1
    print(f"  {label:>6}  {avail:>7}  {total:>8.0f}  {logo:>5}  {free:>7.0f}  {verdict}")

print()
print("=" * 82)
print("/random/ 页面的关键元素是否能在窄屏容纳")
print("=" * 82)
print("  说明：≤600px 时 .drawer-slot 改为纵向排列（缩略图在上、文字在下），")
print("        因此需要宽度 = max(缩略图, 文字最小可读宽度)，而不是两者相加。")
for label, vw, _ in VIEWPORTS:
    gutter = GUTTER_MOBILE if vw <= 600 else GUTTER_DESKTOP
    avail = vw - gutter * 2
    stacked = vw <= 600
    thumb = 132 if stacked else 172
    gap = 22 if stacked else 34
    body_min = 180          # 标题/副标题所需的最小可读宽度
    need = max(thumb, body_min) if stacked else thumb + gap + body_min
    ok = need <= avail
    if not ok:
        problems += 1
    mode = "纵向" if stacked else "横向"
    print(f"  {label:>6}  可用 {avail:>5}  需要 {need:>5}  ({mode})  {'OK' if ok else '★ 过窄'}")

print()
print("=" * 82)
print(f"硬性问题: {problems}")
print("=" * 82)
