import re
from pathlib import Path

def attr(html, tag, name):
    """容忍 minify 去掉引号的三种写法。"""
    m = re.search(rf"<{tag}\b[^>]*\b{name}=(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", html)
    if not m:
        return None
    return next(g for g in m.groups() if g is not None)

print("=== 三个页面的 hero / h1 与首页专属元素 ===")
for rel in ("index.html", "now/index.html", "fragments/index.html",
            "posts/index.html", "music/index.html"):
    p = Path("public") / rel
    if not p.exists():
        print(f"  {rel:22} （不存在）")
        continue
    h = p.read_text(encoding="utf-8")
    hero = attr(h, "header", "class")
    h1 = attr(h, "h1", "class")
    check = {
        "hero--quote": "hero--quote" in h,
        "data-quote-text": "data-quote-text" in h,
        "data-quote-source": "data-quote-source" in h,
        "caret": "home-focus-caret" in h,
    }
    flags = " ".join(f"{k}={'Y' if v else 'N'}" for k, v in check.items())
    print(f"  {rel:22} header={hero or '-':24} h1={h1 or '-':18} {flags}")

print()
print("=== 关键结论 ===")
idx = (Path("public/index.html")).read_text(encoding="utf-8")
now = (Path("public/now/index.html")).read_text(encoding="utf-8")
frag = (Path("public/fragments/index.html")).read_text(encoding="utf-8")
print(f"  首页有 hero--quote          : {'是 ✓' if 'hero--quote' in idx else '否 ✗'}")
print(f"  /now/ 无 hero--quote        : {'是 ✓' if 'hero--quote' not in now else '否 ✗'}")
print(f"  /fragments/ 无 hero--quote  : {'是 ✓' if 'hero--quote' not in frag else '否 ✗'}")
print(f"  /now/ 仍是 home-hero        : {'是 ✓' if 'home-hero' in now else '否 ✗'}")
print(f"  /fragments/ 仍是 home-hero  : {'是 ✓' if 'home-hero' in frag else '否 ✗'}")
