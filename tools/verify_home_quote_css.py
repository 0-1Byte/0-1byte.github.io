"""校验 pages.css 的结构与实际生效范围（只读）。

1. 语法结构：大括号配平、每条声明以 ; 结尾、没有把规则嵌错地方
2. 生效范围：新增的 .hero--quote 规则不应命中 /now/ 与 /fragments/
3. 关键取值是否与要求一致
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "pages.css").read_text(encoding="utf-8")
problems = []


def check(label, ok, detail=""):
    if ok:
        print(f"  OK   {label}")
    else:
        problems.append(label)
        print(f"  FAIL {label}" + (f"  ← {detail}" if detail else ""))


print("=" * 80)
print("1. 语法结构")
print("=" * 80)
check("大括号配平", CSS.count("{") == CSS.count("}"),
      f"{{ {CSS.count('{')} vs }} {CSS.count('}')}")

# 去掉注释后，逐块检查声明是否以 ; 或 } 收尾
no_comment = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
depth_issues = []
i, depth = 0, 0
line_no = 1
for ch in no_comment:
    if ch == "\n":
        line_no += 1
    elif ch == "{":
        depth += 1
        if depth > 2:
            depth_issues.append(f"行 {line_no}: 嵌套超过两层（depth={depth}）")
    elif ch == "}":
        depth -= 1
        if depth < 0:
            depth_issues.append(f"行 {line_no}: 多余的 }}")
            depth = 0
check("没有多余/过深的嵌套", not depth_issues, "; ".join(depth_issues[:3]))

# 声明行必须以 ; 结尾（自定义属性值里可能含分号，粗查足够）
bad_decl = []
for m in re.finditer(r"\{([^{}]*)\}", no_comment, re.S):
    body = m.group(1)
    for raw in body.split("\n"):
        t = raw.strip()
        if not t or t.startswith("/*"):
            continue
        if not t.endswith((";", "{", "}", ",")):
            bad_decl.append(t[:60])
check("块内声明都以 ; 结尾", not bad_decl, f"{bad_decl[:3]}")

print()
print("=" * 80)
print("2. 生效范围：只命中首页")
print("=" * 80)
quote_rules = re.findall(r"^([^\n{]*hero--quote[^\n{]*)\{", CSS, re.M)
print(f"  带 .hero--quote 的选择器 {len(quote_rules)} 条：")
for sel in quote_rules:
    print(f"    {sel.strip()}")
check("存在 hero--quote 作用域规则", len(quote_rules) >= 4)

# /now/ 与 /fragments/ 的模板里没有 hero--quote
for rel in ["layouts/now/single.html", "layouts/fragments/list.html"]:
    src = (ROOT / rel).read_text(encoding="utf-8")
    check(f"{rel} 不含 hero--quote（不会被影响）", "hero--quote" not in src)

idx = (ROOT / "layouts/index.html").read_text(encoding="utf-8")
check("layouts/index.html 含 hero--quote", "hero--quote" in idx)

print()
print("=" * 80)
print("3. 关键取值")
print("=" * 80)
expect = [
    ("首屏留白 clamp(72px, 16vh, 150px)", r"padding-top:\s*clamp\(72px,\s*16vh,\s*150px\)"),
    ("桌面字号 34px", r"font-size:\s*34px"),
    ("桌面行高 1.45", r"line-height:\s*1\.45"),
    ("字距 .008em", r"letter-spacing:\s*\.008em"),
    ("阅读宽度 680px", r"max-width:\s*680px"),
    ("移动字号 25px", r"font-size:\s*25px"),
    ("移动行高 1.55", r"line-height:\s*1\.55"),
    ("移动留白 clamp(56px, 10vh, 96px)", r"padding-top:\s*clamp\(56px,\s*10vh,\s*96px\)"),
    ("出处 margin-top 18px", r"margin:\s*18px\s+0\s+0"),
    ("出处字号 11px", r"font-size:\s*11px"),
    ("出处 opacity .55", r"opacity:\s*\.55"),
    ("光标宽 1px", r"width:\s*1px"),
    ("光标高 .82em", r"height:\s*\.82em"),
    ("光标 margin-left 3px", r"margin-left:\s*3px"),
    ("光标 vertical-align -.02em", r"vertical-align:\s*-\.02em"),
    ("出处破折号用 ::before", r"::before"),
]
for label, pat in expect:
    check(label, re.search(pat, CSS) is not None)

print()
print("=" * 80)
print("4. 被禁止的做法")
print("=" * 80)
qcss = ""
# 收集 hero--quote 相关的块内容
for m in re.finditer(r"([^\n{]*hero--quote[^\n{]*)\{([^{}]*)\}", CSS):
    qcss += m.group(2)
for bad, label in [
    (r"font-weight:\s*(600|700|bold)", "粗体"),
    (r"text-shadow", "text-shadow"),
    (r"background-clip:\s*text", "渐变文字"),
    (r"-webkit-text-stroke", "文字描边"),
    (r"text-align:\s*center", "居中"),
    (r"box-shadow", "阴影"),
    (r"linear-gradient|radial-gradient", "渐变"),
    (r"filter:|drop-shadow", "滤镜/发光"),
    (r"border-radius", "圆角卡片感"),
]:
    check(f"首页句子未使用「{label}」", re.search(bad, qcss) is None)

print()
print("=" * 80)
print("5. min-height 已移除（避免超短句下方空洞）")
print("=" * 80)
check("首页句子的规则里没有 min-height",
      re.search(r"hero--quote[^{]*\{[^}]*min-height", CSS) is None)
check(".home-focus 基础规则也没有 min-height",
      re.search(r"\.home-focus\s*\{[^}]*min-height", CSS) is None)

print()
print("=" * 80)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ CSS 结构正常、只作用于首页、取值符合要求、未用禁止做法")
print("=" * 80)
sys.exit(1 if problems else 0)
