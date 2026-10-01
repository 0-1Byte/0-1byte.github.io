"""检查构建后的 pages.css：取值是否保留、::before 是否还在、没被压缩破坏。"""
import re
from pathlib import Path

css = Path("public/pages.css").read_text(encoding="utf-8")
problems = []


def check(label, ok, detail=""):
    if ok:
        print(f"  OK   {label}")
    else:
        problems.append(label)
        print(f"  FAIL {label}" + (f"  ← {detail}" if detail else ""))


print("=" * 78)
print("产物 pages.css 里的首页规则")
print("=" * 78)
for m in re.finditer(r"([^\n{}]*hero--quote[^\n{}]*)\{([^{}]*)\}", css):
    sel = m.group(1).strip()
    body = " ".join(m.group(2).split())
    print(f"  {sel}")
    print(f"      {body}")

print()
print("=" * 78)
print("关键校验")
print("=" * 78)
check("大括号配平", css.count("{") == css.count("}"))
check("含 34px（桌面字号）", "34px" in css)
check("含 680px（阅读宽度）", "680px" in css)
check("含 clamp(72px,16vh,150px) 或等价",
      re.search(r"clamp\(72px,\s*16vh,\s*150px\)", css) is not None)
check("含 25px（移动字号）", "25px" in css)
check("含 .82em（光标高）", ".82em" in css)
check("含 ::before 破折号规则", "::before" in css and "— " in css)
check("含 data-has-dash 抑制条件", "data-has-dash" in css)
check("不含 min-height（首页句子）",
      re.search(r"hero--quote[^{]*\{[^}]*min-height", css) is None)
check(".home-focus 基础规则也不含 min-height",
      re.search(r"\.home-focus\s*\{[^}]*min-height", css) is None)

print()
print("=" * 78)
print("未越界：theme.css 与 site-nav.css 不应被本次改动碰到")
print("=" * 78)
import subprocess
r = subprocess.run(["git", "status", "--porcelain", "--ignore-submodules=all"],
                   capture_output=True, text=True)
changed = [x[3:].strip() for x in r.stdout.split("\n") if x.strip()]
for f in ["static/theme.css", "static/site-nav.css", "static/site-nav.js"]:
    check(f"{f} 未被改动", f not in changed, "被改了")
print(f"       本次工作区改动：{[c for c in changed if not c.startswith('public/')]}")

print()
print("=" * 78)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 产物 CSS 正常")
print("=" * 78)
