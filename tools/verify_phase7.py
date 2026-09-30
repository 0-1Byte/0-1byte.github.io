"""阶段 7 验证：首页精简 / random 隐藏 / 主题按钮移除 + 固定深色。

针对构建产物（public/）检查，不依赖服务。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUB = ROOT / "public"
problems = []


def check(label, ok, detail=""):
    if ok:
        print(f"  OK   {label}")
    else:
        problems.append(label)
        print(f"  FAIL {label}" + (f"  ← {detail}" if detail else ""))


def read(rel):
    f = PUB / rel
    return f.read_text(encoding="utf-8", errors="ignore") if f.exists() else ""


COLLECTIONS = ["music", "book", "works", "docu", "film", "tv"]

print("=" * 80)
print("1. 首页只剩那句随机句子")
print("=" * 80)
home = read("index.html")
check("首屏句子容器仍在（home-focus）", "home-focus" in home)
check("打字机脚本仍加载（quotes.js）", "quotes.js" in home)
check("quotes 数据端点仍在", (PUB / "nav.json").exists()
      and '"quotes"' in read("nav.json"))
for gone in ["home-currently", "home-posts", "home-post-title"]:
    check(f"已移除 {gone}", gone not in home)
# 注意：>writing< 仍会出现在顶部导航里，那是导航项，属于预期
check("首页正文区不再有 currently 标题",
      not re.search(r'class="home-label">currently<', home))
check("首页正文区不再有 writing 标题",
      not re.search(r'class="home-label">writing<', home))
check("首页正文区不再有 now 区块",
      not re.search(r'class="home-label">now<', home))
check("顶部导航仍含 writing 入口（导航项，应保留）",
      re.search(r'class="hnav-link"[^>]*>\s*<span>writing</span>', home) is not None
      or ">writing<" in home)

print()
print("=" * 80)
print("2. random 已隐藏（URL 与功能都保留）")
print("=" * 80)
nav = read("nav.json")
check("导航里没有 random", '"name": "random"' not in nav and '"random"' not in nav)
check("首页不链接 /random/", "/random/" not in home)
check("/random/ 页面仍然存在（URL 未删）", (PUB / "random" / "index.html").exists())
check("/random/ 资源仍在", (PUB / "random" / "script.js").exists()
      and (PUB / "random" / "style.css").exists())
# 其它页面也不应有 random 入口
linked = []
for rel in ["now/index.html", "posts/index.html", "fragments/index.html"] + \
           [f"{c}/index.html" for c in COLLECTIONS]:
    if "/random/" in read(rel):
        linked.append(rel)
check("其它页面也不链接 /random/", not linked, f"出现在 {linked}")

print()
print("=" * 80)
print("3. 主题切换按钮已从全部页面移除")
print("=" * 80)
pages = ["index.html", "now/index.html", "posts/index.html", "fragments/index.html",
         "ocean/index.html"] + [f"{c}/index.html" for c in COLLECTIONS]
for rel in pages:
    body = read(rel)
    if not body:
        check(f"{rel} 存在", False, "文件不存在")
        continue
    # 只找真正的按钮元素与绑定脚本。
    # 不要用裸字符串 "theme-toggle"：PaperMod 的 <noscript> 回退里有一条
    # `#theme-toggle{display:none}` CSS 规则，那是给不存在元素的兜底样式，
    # 留着无害（浏览器会忽略不匹配的选择器），不算「还有按钮」。
    has_btn = re.search(r'<button[^>]*id=["\']?theme-toggle', body) is not None
    has_bind = ("toggleSiteTheme" in body
                or "bindThemeToggle" in body
                or re.search(r'getElementById\(["\']theme-toggle["\']\)\s*\.\s*addEventListener', body) is not None)
    check(f"{rel} 无按钮/无绑定", not has_btn and not has_bind,
          f"按钮={has_btn} 绑定={has_bind}")

print()
print("=" * 80)
print("4. 除 Ocean 外全部固定深色")
print("=" * 80)
for rel in ["index.html", "now/index.html", "posts/index.html", "fragments/index.html"] + \
           [f"{c}/index.html" for c in COLLECTIONS]:
    body = read(rel)
    fixed = re.search(r'dataset\.theme\s*=\s*["\']dark["\']', body) is not None
    check(f"{rel} 写死 dark", fixed)

# 不应再读取遗留偏好（会把深色改回浅色）
for rel in ["index.html"] + [f"{c}/index.html" for c in COLLECTIONS]:
    body = read(rel)
    reads_pref = "prefers-color-scheme" in body
    check(f"{rel} 不再读系统偏好", not reads_pref,
          "仍会因系统浅色而变浅，而按钮已不可用")

# PaperMod 的页脚绑定脚本必须被 suppress 掉，否则每个 Hugo 页面 console 报错
for rel in ["index.html", "now/index.html", "posts/index.html"]:
    body = read(rel)
    bad = re.search(r'getElementById\(["\']theme-toggle["\']\)\.addEventListener', body)
    check(f"{rel} 没有会抛错的页脚绑定", bad is None,
          "存在 getElementById(...).addEventListener，按钮不存在时会 TypeError")

print()
print("=" * 80)
print("5. Ocean 不受影响")
print("=" * 80)
ocean = read("ocean/index.html")
check("ocean 不使用固定深色", not re.search(r'dataset\.theme\s*=\s*["\']dark["\']', ocean))
check("ocean 保留自己的时段配色逻辑", "toggleSiteTheme" not in ocean)
check("ocean 无导航栏（隐藏入口）", "data-site-nav" not in ocean)

print()
print("=" * 80)
print("6. 数据未丢失")
print("=" * 80)
check("文章仍在（/posts/）", (PUB / "posts" / "index.html").exists())
check("currently 数据仍在 content/_index.md",
      "currently" in (ROOT / "content" / "_index.md").read_text(encoding="utf-8"))
check("句子库仍在（data/quotes.yaml）", (ROOT / "data" / "quotes.yaml").exists())
check("/now/ 仍存在", (PUB / "now" / "index.html").exists())

print()
print("=" * 80)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 三个任务全部完成，且未丢失数据或 URL")
print("=" * 80)
sys.exit(1 if problems else 0)
