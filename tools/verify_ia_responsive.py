"""阶段 3 响应式：导航与首页 / Now 页在指定视口下的排布。

导航的 CSS 事实（来自 static/site-nav.css）：
  桌面  .hnav-list gap:26px，.hnav-link font-size:22px
  ≤600px  .hnav 横向滚动，gap:16px，font-size:17px
首页 .home-focus 30px / ≤600px 26px；.home-index a 24px / ≤600px 21px
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAV_CSS = (ROOT / "static" / "site-nav.css").read_text(encoding="utf-8")
PAGES_CSS = (ROOT / "static" / "pages.css").read_text(encoding="utf-8")

GROUPS = ["listen", "read", "watch", "make"]   # think 为 pending，不渲染

VIEWPORTS = [
    ("桌面 1920", 1920, 26, 22),
    ("桌面 1440", 1440, 26, 22),
    ("桌面 1366", 1366, 26, 22),
    ("移动 430", 430, 16, 17),
    ("移动 375", 375, 16, 17),
]

# 粗略估算 label 宽度：Dancing Script 偏窄，约 0.42em/字符
CHAR_W = 0.42

print("=" * 92)
print("导航在指定视口下是否放得下（放不下时 ≤600px 允许横向滚动）")
print("=" * 92)
problems = []
for label, vw, gap, size in VIEWPORTS:
    mobile = vw <= 600
    # 容器：与 .page 一致（min(1040, 100%-48)），移动端 100%-28
    container = min(1040, vw - (28 if mobile else 48))
    # logo 占位（Chen，约 36px 字号）+ 主题按钮留白
    logo_w = 36 * 5 * CHAR_W + 20
    toggle_w = 40
    avail = container - logo_w - toggle_w - (16 if mobile else 26)

    total = 0
    for g in GROUPS:
        w = len(g) * size * CHAR_W
        if g == "watch":
            w += 14          # 下拉箭头
        total += w
    total += gap * (len(GROUPS) - 1)

    fits = total <= avail
    note = "放得下" if fits else ("横向滚动（已启用 overflow-x）" if mobile else "放不下且无滚动！")
    ok = fits or mobile
    if not ok:
        problems.append(f"{label} 导航需 {total:.0f}px，可用 {avail:.0f}px")
    print(f"  {label:9} 容器 {container:4.0f}  可用 {avail:4.0f}  导航需 {total:4.0f}  {note}  {'OK' if ok else 'FAIL'}")

print()
print("=" * 92)
print("首页 / Now 文案与入口")
print("=" * 92)
for label, vw, _, _ in VIEWPORTS:
    mobile = vw <= 600
    container = min(1040, vw - (28 if mobile else 48))
    cols = 1 if mobile else 1
    focus = 26 if mobile else 30
    idx = 21 if mobile else 24
    # 最长一行 "thinking about large things." 长度
    longest = len("thinking about large things.")
    line_px = longest * focus * 0.42
    fits = line_px <= container
    if not fits:
        problems.append(f"{label} focus 文案一行需 {line_px:.0f}px，容器 {container:.0f}px（会换行，可接受但需知悉）")
    print(f"  {label:9} 容器 {container:4.0f}  focus {focus}px  最长行约 {line_px:4.0f}px  "
          f"{'单行' if fits else '会折行'}")

print()
print("=" * 92)
print(f"硬性问题: {len(problems)}")
for p in problems:
    print("  ·", p)
if not problems:
    print("  ✓ 无溢出 / 无不可访问内容")
print("=" * 92)
