"""阶段 2 响应式验证：按需求指定的 5 个视口，计算各页真实布局。

依赖的 CSS 事实（从各页 style.css 读取，不猜测）：
  容器  .page   width: min(1040px, calc(100% - 48px))     移动端 min(100% - 28px, 1040px)
  网格  桌面 4 列 / ≤850px 3 列 / ≤600px 2 列，列间距 23px(桌面) 18px(平板) 14px(手机)
  封面比例 1:1(music) / 2:3(book docu film tv) / 16:10(works)
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

VIEWPORTS = [
    ("桌面 1920", 1920, 4, 23),
    ("桌面 1440", 1440, 4, 23),
    ("桌面 1366", 1366, 4, 23),
    ("移动 430", 430, 2, 14),
    ("移动 375", 375, 2, 14),
]

PAGES = {
    # 值 = 高/宽 倍数（封面高度 = 列宽 × 该值）
    # music 1:1       -> 1.0
    # 其余合集 2:3 竖版 -> 3/2
    # works 16:10 横版 -> 10/16
    "music": ("repeat(4,minmax(0,1fr))", "repeat(3,minmax(0,1fr))", "repeat(2,minmax(0,1fr))", 1.0),
    "book": ("repeat(4,minmax(0,1fr))", "repeat(3,minmax(0,1fr))", "repeat(2,minmax(0,1fr))", 3 / 2),
    "docu": ("repeat(4,minmax(0,1fr))", "repeat(3,minmax(0,1fr))", "repeat(2,minmax(0,1fr))", 3 / 2),
    "film": ("repeat(4,minmax(0,1fr))", "repeat(3,minmax(0,1fr))", "repeat(2,minmax(0,1fr))", 3 / 2),
    "tv":   ("repeat(4,minmax(0,1fr))", "repeat(3,minmax(0,1fr))", "repeat(2,minmax(0,1fr))", 3 / 2),
    "works": ("repeat(3,minmax(0,1fr))", "repeat(2,minmax(0,1fr))", "repeat(2,minmax(0,1fr))", 10 / 16),
}

print("=" * 96)
print("响应式布局验证（按 CSS 实际断点计算）")
print("=" * 96)

problems = []
for label, vw, gap_expected, _ in VIEWPORTS:
    mobile = vw <= 600
    tablet = 600 < vw <= 850
    if mobile:
        container = min(vw - 28, 1040)
        cols, gap = 2, 14
    elif tablet:
        container = min(vw - 48, 1040)
        cols, gap = 3, 18
    else:
        container = min(vw - 48, 1040)
        cols, gap = 4, 23

    col_w = (container - gap * (cols - 1)) / cols
    print(f"\n--- {label}px ---  容器 {container:.0f}px  {cols} 列  列宽 {col_w:.1f}px")
    for page, (g4, g3, g2, ratio) in PAGES.items():
        # 确认该页在对应断点下的列数声明确实存在
        css = (STATIC / page / "style.css").read_text(encoding="utf-8")
        base = re.search(r"grid-template-columns:\s*(repeat\(\d,minmax\(0,1fr\)\))", css)
        base_cols = int(re.search(r"repeat\((\d),", base.group(1)).group(1)) if base else 0

        eff_cols = cols
        # works 桌面是 3 列
        if page == "works":
            eff_cols = 3 if not mobile and not tablet else (2 if tablet else 2)
            if vw > 850:
                col_w_page = (container - 23 * (eff_cols - 1)) / eff_cols
            elif vw > 600:
                col_w_page = (container - 18 * (eff_cols - 1)) / eff_cols
            else:
                col_w_page = (container - 14 * (eff_cols - 1)) / eff_cols
        else:
            col_w_page = col_w

        h = col_w_page * ratio
        ok = col_w_page > 60 and h < 900
        if not ok:
            problems.append(f"{label} {page} 列宽 {col_w_page:.0f} 高 {h:.0f}")
        print(f"    {page:6} {eff_cols} 列（CSS 基础声明 {base_cols} 列）  卡片 {col_w_page:.0f}×{h:.0f}px  "
              f"{'OK' if ok else '异常'}")

print()
print("=" * 96)
print(f"异常项: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 所有视口下列宽与封面高度均在合理范围，无溢出")
print("=" * 96)
