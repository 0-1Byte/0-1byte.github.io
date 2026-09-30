"""阶段 3 验证：信息架构重组后，URL 兼容性与导航一致性。

检查项：
  A. 旧 URL 全部仍然 200（/music/ /book/ /works/ /docu/ /film/ /tv/）
  B. 新增页面 200（/ 和 /now/）
  C. 导航来源一致：Hugo 页面服务端渲染的 .hnav 与 data/nav.yaml 内容吻合
  D. 不含死链：导航里出现的每个 href 都能取到
  E. 首页不再是文章列表
  F. 主题切换 / 回到顶部等既有资源未被破坏
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
OLD = ["/music/", "/book/", "/works/", "/docu/", "/film/", "/tv/"]
for p in OLD:
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
# 从 yaml 里抽出未 pending 的分组 key/label
groups = re.findall(r"^  - key: (\w+)\n    label: (\w+)(\n    pending: true)?", NAV, re.M)
expected_live = [(k, lbl) for k, lbl, pend in groups if not pend]
expected_pending = [(k, lbl) for k, lbl, pend in groups if pend]
expected_keys = [k for k, _ in expected_live]
print(f"  yaml 中应渲染的分组: {expected_keys}")
print(f"  yaml 中标记 pending : {[k for k, _ in expected_pending]}（不应出现在任何导航里）")

# --- C1. Hugo 页面：服务端渲染的 .hnav ---
# 注意：hugo --minify / dev server 会把属性引号从 " 换成 '，
# 所以匹配时两种引号都要接受。
st, body = get("/")
server_keys = re.findall(r"data-group=[\"'](\w+)[\"']", body)
ok = server_keys == expected_keys
if not ok:
    problems.append(f"Hugo 页面导航分组 {server_keys}，期望 {expected_keys}")
print(f"  {'OK ' if ok else 'FAIL'} /          [服务端渲染] data-group={server_keys}")

# --- C2. 合集页：读取 /nav.json（static/ 页面不经过 Hugo 模板，运行时 fetch） ---
st, navjson = get("/nav.json")
if st != 200:
    problems.append(f"/nav.json -> {st}")
    print(f"  FAIL /nav.json  {st}")
else:
    try:
        data = json.loads(navjson)
        keys = [g["key"] for g in data["groups"]]
        ok = keys == expected_keys
        if not ok:
            problems.append(f"/nav.json 分组 {keys}，期望 {expected_keys}")
        print(f"  {'OK ' if ok else 'FAIL'} /nav.json   [运行时数据] groups={keys}")
    except Exception as e:  # noqa: BLE001
        problems.append(f"/nav.json 解析失败: {e}")
        print(f"  FAIL /nav.json 解析失败: {e}")

# --- C3. 合集页确实引入了导航脚本与样式 ---
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
print("D. 死链检查：导航里出现的每个页面 URL 是否都能取到")
print("=" * 88)
hrefs = sorted(set(re.findall(r'href="(/[a-z]+/)"', NAV)))
for h in hrefs:
    st, _ = get(h)
    ok = st == 200
    if not ok:
        problems.append(f"导航死链 {h} -> {st}")
    print(f"  {'OK ' if ok else 'FAIL'} {h:12} {st}")

print()
print("=" * 88)
print("E. 首页不再是文章列表")
print("=" * 88)
st, home = get("/")
checks = [
    ("使用 .home 结构", 'class="home"' in home),
    ("含 focus 文案", "home-focus" in home),
    ("含 currently", "home-currently" in home),
    ("不含文章卡片 .post-entry", "post-entry" not in home),
    ("不含文章链接 .entry-link", "entry-link" not in home),
    ("含 Now 入口", 'href="' in home and "/now/" in home),
]
for name, ok in checks:
    if not ok:
        problems.append(f"首页检查失败: {name}")
    print(f"  {'OK ' if ok else 'FAIL'} {name}")

print()
print("=" * 88)
print("F. 既有资源未被破坏")
print("=" * 88)
for p in ["/theme.css?v=1", "/site-nav.css?v=1", "/site-nav.js?v=1",
          "/pages.css?v=1", "/back-to-top.js?v=1", "/collection-common.js?v=1"]:
    st, _ = get(p)
    ok = st == 200
    if not ok:
        problems.append(f"{p} -> {st}")
    print(f"  {'OK ' if ok else 'FAIL'} {p:34} {st}")

print()
print("=" * 88)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 全部通过")
print("=" * 88)
