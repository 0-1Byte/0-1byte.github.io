"""阶段 3 验证：信息架构重组后，URL 兼容性与导航一致性。

检查项：
  A. 旧 URL 全部仍然 200（/music/ /book/ /works/ /docu/ /film/ /tv/）
  B. 新增页面 200（/ 和 /now/）
  C. 导航来源一致：Hugo 页面服务端渲染的 .hnav 与 data/nav.yaml 吻合；
     合集页通过 /nav.json + site-nav.js 渲染同一份数据
  D. 不含死链：导航里出现的每个页面 URL 都能取到
  E. 首页不再是文章列表
  F. 既有资源未被破坏

注意：hugo --minify 会去掉可省略的属性引号（class="home" -> class=home），
dev server 则把 " 换成 '。因此属性匹配必须容忍三种写法。
"""
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:1350"
ROOT = Path(__file__).resolve().parents[1]
NAV = (ROOT / "data" / "nav.yaml").read_text(encoding="utf-8")

problems = []


def has_class(html, name):
    """类名匹配：容忍 class="x" / class='x' / class=x。"""
    return re.search(rf"\bclass=(?:\"{name}\"|'{name}'|{name})(?=[\s>])", html) is not None


def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=15) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return None, str(e)


print("=" * 88)
print("A. 旧 URL 兼容性（阶段 3 的核心约束：不能破坏已有链接）")
print("=" * 88)
for p in ["/music/", "/book/", "/works/", "/docu/", "/film/", "/tv/"]:
    st, _ = get(p)
    ok = st == 200
    if not ok:
        problems.append(f"{p} -> {st}")
    print(f"  {'OK ' if ok else 'FAIL'} {p:12} {st}")

print()
print("=" * 88)
print("B. 新增页面")
print("=" * 88)
for p in ["/", "/now/"]:
    st, body = get(p)
    ok = st == 200
    if not ok:
        problems.append(f"{p} -> {st}")
    print(f"  {'OK ' if ok else 'FAIL'} {p:12} {st}  {len(body)} bytes")

print()
print("=" * 88)
print("C. 导航分组与 data/nav.yaml 是否吻合")
print("=" * 88)
groups = re.findall(r"^  - key: (\w+)\n    label: (\w+)(\n    pending: true)?", NAV, re.M)
expected_keys = [k for k, _, pend in groups if not pend]
pending_keys = [k for k, _, pend in groups if pend]
print(f"  yaml 应渲染分组: {expected_keys}")
print(f"  yaml pending   : {pending_keys}（不应出现在任何导航里）")

st, body = get("/")
server_keys = re.findall(r"data-group=[\"']?(\w+)", body)
ok = server_keys == expected_keys
if not ok:
    problems.append(f"Hugo 页面导航分组 {server_keys}，期望 {expected_keys}")
print(f"  {'OK ' if ok else 'FAIL'} /          [服务端渲染] data-group={server_keys}")

for pending in pending_keys:
    if re.search(rf"data-group=[\"']?{pending}[\"'\s>]", body):
        problems.append(f"pending 分组 {pending} 被渲染进导航")
        print(f"  FAIL pending 的 {pending} 出现在导航里")

st, navjson = get("/nav.json")
if st != 200:
    problems.append(f"/nav.json -> {st}")
    print(f"  FAIL /nav.json  {st}")
else:
    data = json.loads(navjson)
    keys = [g["key"] for g in data["groups"]]
    ok = keys == expected_keys
    if not ok:
        problems.append(f"/nav.json 分组 {keys}，期望 {expected_keys}")
    print(f"  {'OK ' if ok else 'FAIL'} /nav.json   [运行时数据] groups={keys}")

for page in ["/music/", "/book/", "/works/", "/docu/", "/film/", "/tv/"]:
    st, body = get(page)
    has_js = "/site-nav.js" in body
    has_css = "/site-nav.css" in body
    has_host = "data-site-nav" in body
    ok = has_js and has_css and has_host
    if not ok:
        problems.append(f"{page} 导航接入不全 js={has_js} css={has_css} host={has_host}")
    print(f"  {'OK ' if ok else 'FAIL'} {page:9} site-nav.js={has_js} css={has_css} 容器={has_host}")

print()
print("=" * 88)
print("D. 死链检查：实际渲染出来的导航链接是否都能取到")
print("=" * 88)
# 只检查「会出现在导航里」的链接 —— 即非 pending 分组下的子项。
# pending 分组（如 think→Fragments）本阶段不渲染，其 URL 尚不存在属预期。
live_hrefs, pending_hrefs = [], []
current_group_pending = False
for line in NAV.splitlines():
    m_key = re.match(r"^  - key: (\w+)", line)
    if m_key:
        current_group_pending = False
        continue
    if re.match(r"^    pending: true", line):
        current_group_pending = True
        continue
    m_href = re.match(r"^        href: (/\S+)", line)
    if m_href:
        (pending_hrefs if current_group_pending else live_hrefs).append(m_href.group(1))

for h in sorted(set(live_hrefs)):
    st, _ = get(h)
    ok = st == 200
    if not ok:
        problems.append(f"导航死链 {h} -> {st}")
    print(f"  {'OK ' if ok else 'FAIL'} {h:12} {st}")
for h in sorted(set(pending_hrefs)):
    print(f"  --   {h:12} （pending 分组，本阶段不渲染，不检查）")

print()
print("=" * 88)
print("E. 首页不再是文章列表")
print("=" * 88)
st, home = get("/")
checks = [
    ("使用 .home 结构", has_class(home, "home")),
    ("含 focus 文案", "home-focus" in home),
    ("含 currently", "home-currently" in home),
    ("含分组入口", "home-index" in home),
    ("不含文章卡片 .post-entry", "post-entry" not in home),
    ("不含文章链接 .entry-link", "entry-link" not in home),
    ("含 Now 入口", "/now/" in home),
]
for name, ok in checks:
    if not ok:
        problems.append(f"首页检查失败: {name}")
    print(f"  {'OK ' if ok else 'FAIL'} {name}")

print()
print("=" * 88)
print("F. 既有资源未被破坏")
print("=" * 88)
for p in ["/theme.css", "/site-nav.css", "/site-nav.js", "/pages.css",
          "/back-to-top.js", "/collection-common.js", "/covers.js"]:
    st, _ = get(p)
    ok = st == 200
    if not ok:
        problems.append(f"{p} -> {st}")
    print(f"  {'OK ' if ok else 'FAIL'} {p:26} {st}")

print()
print("=" * 88)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 全部通过")
print("=" * 88)
