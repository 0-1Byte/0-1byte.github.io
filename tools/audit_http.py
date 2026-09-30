"""阶段 1 的 HTTP 层验证：逐页抓取，检查所有引用资源是否 200，无 404/网络错误。

模拟浏览器会发出的请求：页面本身 + 页面引用的 css/js/json/字体 + 数据里的封面图
（只抽一份样本，避免把 653 个资源全部请求一遍）。
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:1345"
ROOT = Path(__file__).resolve().parents[1]
PAGES = ["", "music", "book", "works", "docu", "film", "tv", "posts", "categories", "tags"]

results = []
checked = 0
missing = []


def fetch(path, method="GET"):
    url = BASE + path
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:  # noqa: BLE001
        return None, str(e).encode()


print("=" * 84)
print("1. 页面与页面内引用资源")
print("=" * 84)

for page in PAGES:
    path = f"/{page}/" if page else "/"
    status, body = fetch(path)
    checked += 1
    if status != 200:
        missing.append(f"{path} -> {status}")
        print(f"  {path:16} {status}")
        continue
    html = body.decode("utf-8", "replace")
    refs = set()
    for m in re.findall(r'(?:href|src)="([^"]+)"', html):
        if m.startswith(("http://", "https://", "//", "#", "mailto:")):
            continue
        if m.startswith("/"):
            refs.add(m.split("#")[0])
    bad = []
    for ref in sorted(refs):
        if ref.endswith(".xml"):
            continue
        st, _ = fetch(ref)
        checked += 1
        if st != 200:
            bad.append(f"{ref} -> {st}")
    print(f"  {path:16} 200  引用 {len(refs):2d}  失败 {len(bad)}")
    for b in bad:
        missing.append(f"{path} 内引用 {b}")

print()
print("=" * 84)
print("2. 六个合集页的数据与封面样本")
print("=" * 84)
DATASETS = {
    "music": ("songs.json", "cover"),
    "book": ("books.json", "cover"),
    "works": ("works.json", "cover"),
    "docu": ("docus.json", "cover"),
    "film": ("films.json", "cover"),
    "tv": ("tvs.json", "cover"),
}
for page, (jf, field) in DATASETS.items():
    st, body = fetch(f"/{page}/{jf}?v=2")
    checked += 1
    if st != 200:
        missing.append(f"/{page}/{jf} -> {st}")
        print(f"  {page:6} json {st}")
        continue
    items = json.loads(body)
    # 取前 3 条的封面（含 srcset 三档）
    sample_ok = sample_bad = 0
    for it in items[:3]:
        base = it.get("img")
        cover = it.get(field, "")
        urls = []
        if base:
            for w in (240, 320, 480):
                urls.append(f"/{page}/covers/opt/{base}-{w}.webp" if page != "music"
                            else f"/music/assets/{base}-{w}.webp")
        if cover and not cover.startswith("http"):
            # music 的 cover 已是站点绝对路径（/music/assets/xxx.jpg）；
            # 其余合集页是页面内相对路径（covers/xxx.jpg），前端用 BASE 拼前缀。
            urls.append(cover if cover.startswith("/") else f"/{page}/" + cover.lstrip("/"))
        for u in urls:
            st2, _ = fetch(urllib.parse.quote(u, safe="/:?=&%"))
            checked += 1
            if st2 == 200:
                sample_ok += 1
            else:
                sample_bad += 1
                missing.append(f"{u} -> {st2}")
    print(f"  {page:6} 条目 {len(items):3d}  封面样本 OK {sample_ok}  失败 {sample_bad}")

print()
print("=" * 84)
print("3. 新增共用资源")
print("=" * 84)
for path in ["/collection-common.js?v=1", "/collection-states.css?v=1", "/covers.js?v=1", "/back-to-top.js?v=1", "/back-to-top.css?v=1"]:
    st, body = fetch(path)
    checked += 1
    print(f"  {path:34} {st}  {len(body)} bytes")
    if st != 200:
        missing.append(f"{path} -> {st}")

print()
print("=" * 84)
print(f"共请求 {checked} 次，失败 {len(missing)} 项")
if missing:
    for m in missing[:20]:
        print("  ✗", m)
else:
    print("  ✓ 无 404 / 网络错误")
print("=" * 84)
