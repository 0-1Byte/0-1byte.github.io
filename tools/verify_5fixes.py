"""五个问题的修复验证。针对生产产物（hugo --minify 的结果）检查。"""
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:1356"
ROOT = Path(__file__).resolve().parents[1]
PAGES = ["music", "book", "works", "docu", "film", "tv"]

problems = []


def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=15) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def header_of(html):
    m = re.search(r"<header[^>]*class=[\"']?header[\"']?[^>]*>(.*?)</header>", html, re.S)
    return m.group(1) if m else ""


print("=" * 92)
print("问题 1：合集页能否回主页")
print("=" * 92)
for p in PAGES:
    st, html = get(f"/{p}/")
    h = header_of(html)
    has_logo = bool(re.search(r"class=[\"']?logo[\"']?", h))
    home_link = bool(re.search(r"<a href=[\"']?/(?:index\.html)?[\"'\s>]", h))
    ok = has_logo and home_link
    if not ok:
        problems.append(f"{p} 缺少回主页入口 logo={has_logo} link={home_link}")
    print(f"  {'OK ' if ok else 'FAIL'} /{p+'/':10} logo={has_logo}  指向 / 的链接={home_link}")

print()
print("=" * 92)
print("问题 2（阶段 7 已改）：主题切换按钮应已从全站移除，且固定深色")
print("=" * 92)
for path in ["/"] + [f"/{p}/" for p in PAGES]:
    st, html = get(path)
    h = header_of(html)
    has_btn = re.search(r"<button[^>]*id=[\"']?theme-toggle", h) is not None
    has_bind = re.search(r"getElementById\([\"']theme-toggle[\"']\)\s*\.\s*addEventListener", html) is not None
    fixed_dark = re.search(r"dataset\.theme\s*=\s*[\"']dark[\"']", html) is not None
    ok = (not has_btn) and (not has_bind) and fixed_dark
    if not ok:
        problems.append(f"{path} 按钮={has_btn} 绑定={has_bind} 固定深色={fixed_dark}")
    print(f"  {'OK ' if ok else 'FAIL'} {path:10} 无按钮={not has_btn} 无绑定={not has_bind} 固定深色={fixed_dark}")

css_st, nav_css = get("/site-nav.css")
# 断言前先去掉 CSS 注释：文件里刻意写了「原先这里是 padding-right: 44px…」
# 这类说明，直接匹配会命中自己的注释，产生假失败。
nav_css_code = re.sub(r"/\*.*?\*/", "", nav_css, flags=re.S)
checks = [
    (".header 有 position:relative（布局仍需要）", re.search(r"\.header\s*\{[^}]*position:\s*relative", nav_css_code, re.S) is not None),
    (".hnav 有 z-index（下拉层级仍需要）", re.search(r"\.hnav\s*\{[^}]*z-index", nav_css_code, re.S) is not None),
    ("site-nav.css 已无 .theme-toggle 规则（按钮删了就是死代码）",
     re.search(r"^\.theme-toggle\s*\{", nav_css_code, re.M) is None),
    (".header-nav 已不再为按钮留白",
     re.search(r"\.header-nav\s*\{[^}]*padding-right", nav_css_code, re.S) is None),
]
for name, ok in checks:
    if not ok:
        problems.append(f"CSS 检查失败: {name}")
    print(f"  {'OK ' if ok else 'FAIL'} {name}")

for p in PAGES:
    st, css = get(f"/{p}/style.css")
    leftover = re.search(r"\.theme-toggle\s*\{", css)
    ok = leftover is None
    if not ok:
        problems.append(f"{p}/style.css 仍有自己的 .theme-toggle 规则")
    print(f"  {'OK ' if ok else 'FAIL'} {p}/style.css 无重复 .theme-toggle={ok}")

print()
print("=" * 92)
print("问题 3：文章入口")
print("=" * 92)
st, home = get("/")
posts_ok = "/posts/" in home
print(f"  {'OK ' if posts_ok else 'FAIL'} 首页含 /posts/ 链接={posts_ok}")
if not posts_ok:
    problems.append("首页没有文章入口")

titles = re.findall(r"home-post-title[^>]*>([^<]+)<", home)
print(f"  首页展示最近文章 {len(titles)} 篇: {titles}")

st, navjson = get("/nav.json")
nav = json.loads(navjson)
standalone = [s["name"] for s in nav.get("standalone", [])]
ok = "writing" in standalone
if not ok:
    problems.append("导航缺少 writing 入口")
print(f"  {'OK ' if ok else 'FAIL'} 导航独立入口: {standalone}")

st, posts_page = get("/posts/")
ok = st == 200
if not ok:
    problems.append(f"/posts/ -> {st}")
print(f"  {'OK ' if ok else 'FAIL'} /posts/ 可访问 {st}")
for slug in ["/posts/reload-from-here/", "/posts/my-second-post/"]:
    st, _ = get(slug)
    ok = st == 200
    if not ok:
        problems.append(f"{slug} -> {st}")
    print(f"  {'OK ' if ok else 'FAIL'} {slug:32} {st}")

print()
print("=" * 92)
print("问题 4：首页 elsewhere 是否已移除")
print("=" * 92)
# 阶段 7：currently / writing 两块已按反馈从首页移除。
# 这里断言它们**不在**首页，同时确认句子与导航仍在。
for kw, expect in [("elsewhere", False), ("home-index", False),
                   ("home-posts", False), ("home-currently", False),
                   ("home-focus", True)]:
    found = kw in home
    ok = found == expect
    if not ok:
        problems.append(f"首页 {kw} 存在={found}，期望={expect}")
    print(f"  {'OK ' if ok else 'FAIL'} {kw:16} 存在={found}  期望={expect}")

print()
print("=" * 92)
print("问题 4b：/posts/ 标题改为 Writing，且保留封面图卡片")
print("=" * 92)
st, posts_html = get("/posts/")
# 标题里的 "Posts" 应换成 "Writing"
title_m = re.search(r"<title>([^<]*)</title>", posts_html)
title_txt = title_m.group(1) if title_m else ""
ok = "Posts" not in title_txt and "Writing" in title_txt
if not ok:
    problems.append(f"/posts/ 标题仍是 {title_txt!r}，期望含 Writing 且不含 Posts")
print(f"  {'OK ' if ok else 'FAIL'} <title> = {title_txt!r}（不应含 Posts）")

# 列表仍用主题的封面图卡片（这是列表页该有的样子，不能被去掉）
for kw, expect in [("post-entry", True), ("entry-cover", True), ("entry-link", True)]:
    found = kw in posts_html
    ok = found == expect
    if not ok:
        problems.append(f"/posts/ {kw} 存在={found}，期望={expect}")
    print(f"  {'OK ' if ok else 'FAIL'} {kw:14} 存在={found}  期望={expect}")

n_cards = len(re.findall(r"post-entry", posts_html))
ok = n_cards == 2
if not ok:
    problems.append(f"/posts/ 卡片数 {n_cards}，期望 2")
print(f"  {'OK ' if ok else 'FAIL'} 卡片数={n_cards}（期望 2）")

print()
print("=" * 92)
print("问题 5：下拉字体统一")
print("=" * 92)
name_rule = re.search(r"\.hnav-menu-name,\s*\.hnav-menu-desc\s*\{([^}]*)\}", nav_css, re.S)
has_family = name_rule and "font-family" in name_rule.group(1)
if not has_family:
    problems.append("下拉项未显式指定 font-family")
print(f"  {'OK ' if has_family else 'FAIL'} .hnav-menu-name/-desc 显式指定字体族={bool(has_family)}")
if has_family:
    fam = " ".join(name_rule.group(1).split())
    print(f"      {fam}")
ok = has_family and "Dancing Script" in name_rule.group(1)
if not ok:
    problems.append("下拉项字体族未包含 Dancing Script")
print(f"  {'OK ' if ok else 'FAIL'} 与顶层同样含 Dancing Script={ok}")
# 字号不再过小
size = re.search(r"\.hnav-menu-name\s*\{[^}]*font-size:\s*([\d.]+)px", nav_css, re.S)
print(f"      下拉项字号: {size.group(1) + 'px' if size else '未找到'}（原为 13px）")

print()
print("=" * 92)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 五项修复全部验证通过")
print("=" * 92)
