"""阶段 4 验证：/random/ 页面与它引用的所有资源。

检查：
  A. 页面与静态资源 200
  B. 七个数据源 URL 可达（fragments 预期 404，属已知未启用）
  C. adapter 生成的封面 URL 全部真实存在（抽样 + 全量）
  D. 导航里出现 random 入口，且链接可达
  E. 页面没有引用不存在的资源
"""
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:1360"
ROOT = Path(__file__).resolve().parents[1]
PUB = ROOT / "public"

problems = []


def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=15) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return None, str(e)


print("=" * 90)
print("A. 页面与静态资源")
print("=" * 90)
for p in ["/random/", "/random/style.css", "/random/script.js", "/random/random-favicon.svg",
          "/site-nav.js", "/theme.css", "/collection-common.js"]:
    st, _ = get(p)
    ok = st == 200
    if not ok:
        problems.append(f"{p} -> {st}")
    print(f"  {'OK ' if ok else 'FAIL'} {p:34} {st}")

print()
print("=" * 90)
print("B. 数据源可达性")
print("=" * 90)
SRC = {
    "Music": "/music/songs.json?v=2",
    "Books": "/book/books.json?v=2",
    "Films": "/film/films.json?v=2",
    "TV": "/tv/tvs.json?v=2",
    "Docu": "/docu/docus.json?v=2",
    "Works": "/works/works.json?v=2",
    "Fragments": "/fragments/fragments.json?v=2",
}
for name, p in SRC.items():
    st, body = get(p)
    note = ""
    if name == "Fragments" and st == 404:
        note = "（阶段 3 定为 pending，尚无数据 —— 页面会跳过并保留 console.warn）"
        ok = True
    else:
        ok = st == 200
        if ok:
            try:
                n = len(json.loads(body))
                note = f"{n} 条"
            except Exception:  # noqa: BLE001
                ok = False
                note = "JSON 解析失败"
    if not ok:
        problems.append(f"{name} {p} -> {st}")
    print(f"  {'OK ' if ok else 'FAIL'} {name:10} {st}  {note}")

print()
print("=" * 90)
print("C. adapter 生成的封面 URL 是否真实存在（全量校验）")
print("=" * 90)

# 复刻 adapter 的图片规则。要点（与 static/random/script.js 的 assetFor 一致）：
#   1. 完整 URL 或根路径 → 原样返回；否则拼上该源自己的目录
#      （works 的 cover 形如 assets/x.svg，必须补 /works/；
#        book 有一条 cover 本身就是 douban 远程 URL，不能补前缀）
#   2. 部分 cover 值本身是百分号编码（如 /music/assets/Adele%20-%20Hello.jpg），
#      浏览器请求时会再编码，实际文件名带空格 —— 校验时要 unquote
#   3. 少数条目没有 img 字段，adapter 会回退到 cover
from urllib.parse import unquote  # noqa: E402


def resolve(base_dir, path):
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://") or path.startswith("//") or path.startswith("/"):
        return path
    return f"{base_dir}/{path}"


def exists(url):
    if not url or url.startswith("http"):
        return True          # 远程资源不在本地校验范围
    # 三件事都要做，缺一个就会误报「文件不存在」：
    #   1. 去掉查询串（如 ?v=2）
    #   2. unquote —— 数据里可能带 %20，而磁盘上的文件名是空格
    #   3. lstrip("/") —— 否则 PUB / "/music/…" 会被当成绝对路径
    path = unquote(url.split("?")[0]).lstrip("/")
    return (PUB / path).exists()


CHECKS = [
    ("music", "music/songs.json", "/music",
     lambda it: f"/music/assets/{it['img']}-480.webp" if it.get("img") else resolve("/music", it["cover"]),
     lambda it: resolve("/music", it["cover"])),
    ("books", "book/books.json", "/book",
     lambda it: f"/book/covers/opt/{it['img']}-320.webp" if it.get("img") else resolve("/book", it["cover"]),
     lambda it: resolve("/book", it["cover"])),
    ("films", "film/films.json", "/film",
     lambda it: f"/film/covers/opt/{it['img']}-320.webp" if it.get("img") else resolve("/film", it["cover"]),
     lambda it: resolve("/film", it["cover"])),
    ("tv", "tv/tvs.json", "/tv",
     lambda it: f"/tv/covers/opt/{it['img']}-320.webp" if it.get("img") else resolve("/tv", it["cover"]),
     lambda it: resolve("/tv", it["cover"])),
    ("docu", "docu/docus.json", "/docu",
     lambda it: f"/docu/covers/opt/{it['img']}-320.webp" if it.get("img") else resolve("/docu", it["cover"]),
     lambda it: resolve("/docu", it["cover"])),
    ("works", "works/works.json", "/works",
     lambda it: resolve("/works", it["cover"]),
     lambda it: ""),
]

total = remote = 0
for name, rel, _base, main_fn, fb_fn in CHECKS:
    items = json.loads((PUB / rel).read_text(encoding="utf-8"))
    m = 0
    for it in items:
        url = main_fn(it)
        total += 1
        if url.startswith("http"):
            remote += 1
            continue
        if not exists(url):
            m += 1
            if m <= 3:
                print(f"      ✗ {name}: 缺少 {url}")
    if m:
        problems.append(f"{name} 有 {m} 个封面文件不存在")
    fb_missing = sum(1 for it in items
                     if fb_fn(it) and not fb_fn(it).startswith("http") and not exists(fb_fn(it)))
    print(f"  {'OK ' if m == 0 else 'FAIL'} {name:8} 条目 {len(items):3}  主图缺失 {m}  兜底图缺失 {fb_missing}")
print(f"  合计校验 {total} 个主图 URL（其中 {remote} 个为远程，不本地校验）")

print()
print("=" * 90)
print("D. 导航入口")
print("=" * 90)
st, navjson = get("/nav.json")
nav = json.loads(navjson)
names = [s["name"] for s in nav.get("standalone", [])]
ok = "random" in names
if not ok:
    problems.append("导航缺少 random 入口")
print(f"  {'OK ' if ok else 'FAIL'} standalone = {names}")
st, home = get("/")
ok = "random" in home and "/random/" in home
if not ok:
    problems.append("首页导航未出现 random")
print(f"  {'OK ' if ok else 'FAIL'} 首页含 random 链接 = {ok}")

print()
print("=" * 90)
print("E. /random/ 页面自身引用的资源是否都可取")
print("=" * 90)
st, page = get("/random/")
refs = set()
for m in re.findall(r'(?:href|src)="([^"]+)"', page):
    if m.startswith(("http://", "https://", "//", "#", "mailto:")):
        continue
    refs.add(m.split("?")[0])
bad = []
for r in sorted(refs):
    if r.startswith("/") and not r.endswith(".json"):
        st2, _ = get(r)
        if st2 != 200:
            bad.append(f"{r} -> {st2}")
if bad:
    problems.extend(bad)
print(f"  引用 {len(refs)} 个资源，失败 {len(bad)}")
for b in bad:
    print("      ✗", b)

print()
print("=" * 90)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 全部通过")
print("=" * 90)
