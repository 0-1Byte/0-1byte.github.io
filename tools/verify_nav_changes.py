"""验证本轮两项导航改动，并确认没有连带破坏。

1. think 分组已从导航消失，但 /fragments/ 与 fragments.json 仍可用
2. watch 的三项不再有 desc（可见小字与悬停提示都没了）
   同时 listen / read / make 的 desc 未受影响
3. 其余东西一律没动：random/ocean 仍隐藏、writing 仍在、六个页面数据仍在
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUB = ROOT / "public"
SRC = ROOT / "static"
problems = []


def check(label, ok, detail=""):
    if ok:
        print(f"  OK   {label}")
    else:
        problems.append(label)
        print(f"  FAIL {label}" + (f"  ← {detail}" if detail else ""))


nav = json.loads((PUB / "nav.json").read_text(encoding="utf-8"))
labels = [g["label"] for g in nav["groups"]]

print("=" * 82)
print("1. think 已隐藏，内容与 URL 保留")
print("=" * 82)
check("导航分组不含 think", "think" not in labels, f"实际 {labels}")
check("导航分组仍是 listen/read/watch/make",
      labels == ["listen", "read", "watch", "make"], f"实际 {labels}")
check("/fragments/ 页面仍存在", (PUB / "fragments" / "index.html").exists())
check("/fragments/fragments.json 端点仍存在",
      (PUB / "fragments" / "fragments.json").exists())
frag = (PUB / "fragments" / "index.html").read_text(encoding="utf-8")
check("/fragments/ 仍有标题与空状态", "Fragments" in frag and "还没有记录" in frag)
check("content/fragments/ 内容目录未动",
      (ROOT / "content" / "fragments" / "_index.md").exists())
check("布局模板未动（fragments 列表与 JSON 模板都在）",
      (ROOT / "layouts" / "fragments" / "list.html").exists()
      and (ROOT / "layouts" / "fragments" / "list.json").exists())

print()
print("=" * 82)
print("2. watch 三项的中文已去掉（可见小字 + 悬停提示）")
print("=" * 82)
watch = next(g for g in nav["groups"] if g["key"] == "watch")
for c in watch["children"]:
    check(f"{c['name']} 的 desc 为空", c["desc"] == "", f"desc={c['desc']!r}")
check("watch 仍有三项", [c["name"] for c in watch["children"]] == ["Film", "TV", "Docu"])

# 产物里不应再出现那三句中文
home = (PUB / "index.html").read_text(encoding="utf-8")
for zh in ["看过的电影", "看过的剧集", "看过的纪录片"]:
    check(f"首页产物不含「{zh}」", zh not in home)
# nav.json 里也不该有
raw = (PUB / "nav.json").read_text(encoding="utf-8")
for zh in ["看过的电影", "看过的剧集", "看过的纪录片"]:
    check(f"nav.json 不含「{zh}」", zh not in raw)

print()
print("=" * 82)
print("3. 其它分组的 desc 未受影响（我不该顺手改它们）")
print("=" * 82)
expect = {"listen": ("Music", "在听的歌"), "read": ("Book", "在读的书"),
          "make": ("Works", "做出来的东西")}
for key, (name, desc) in expect.items():
    g = next(x for x in nav["groups"] if x["key"] == key)
    c = g["children"][0]
    check(f"{key} 的 {name} desc 保持「{desc}」",
          c["name"] == name and c["desc"] == desc, f"实际 {c}")

standalone = [s["name"] for s in nav.get("standalone", [])]
check("standalone 仍只有 writing", standalone == ["writing"], f"实际 {standalone}")
check("writing 的 desc 未动",
      next(s for s in nav["standalone"] if s["name"] == "writing")["desc"] == "写下来的东西")
check("random 仍隐藏", "random" not in raw)
check("ocean 仍隐藏", "ocean" not in raw)

print()
print("=" * 82)
print("4. 六个合集页数据未受影响（上次事故的回归）")
print("=" * 82)
for page, rel, n_min in [("music", "music/songs.json", 200), ("book", "book/books.json", 5),
                         ("film", "film/films.json", 10), ("tv", "tv/tvs.json", 3),
                         ("docu", "docu/docus.json", 5), ("works", "works/works.json", 2)]:
    items = json.loads((PUB / rel).read_text(encoding="utf-8"))
    ok = len(items) >= n_min
    check(f"{page} 数据 {len(items)} 条（>= {n_min}）", ok)

RISKY = re.compile(r'getElementById\(\s*["\']([^"\']+)["\']\s*\)\s*\.\s*\w+')
for page in ["music", "book", "film", "tv", "docu", "works"]:
    src = (SRC / page / "script.js").read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    code = re.sub(r"//[^\n]*", "", code)
    hits = RISKY.findall(code)
    check(f"{page}/script.js 无链式 getElementById", not hits, f"{hits}")

print()
print("=" * 82)
print("5. 导航脚本与样式未被改动")
print("=" * 82)
import subprocess
r = subprocess.run(["git", "status", "--porcelain", "--ignore-submodules=all"],
                   cwd=ROOT, capture_output=True, text=True)
changed = [x[3:].strip() for x in r.stdout.split("\n") if x.strip()]
print(f"  本次工作区改动：{changed or '（无）'}")
# 改用「禁止清单」而不是白名单。
# 白名单每次改动都要维护，容易变成橡皮图章；禁止清单表达的是真正的底线：
# 这些文件是共用设计系统或其它页面的实现，任何导航/首页的改动都不该碰它们。
FORBIDDEN = [
    "static/theme.css",           # 全站设计变量
    "hugo.toml",                  # 站点配置
    "static/collection-common.js",
    "static/covers.js",
    "static/site-nav.js",         # 导航脚本：只有明确要改下拉时才会动
]
# 六个合集页各自的实现也属于「别的页面」
for _p in ("music", "book", "works", "docu", "film", "tv"):
    FORBIDDEN += [f"static/{_p}/script.js", f"static/{_p}/style.css"]

violated = [c for c in changed if c in FORBIDDEN]
check("没有碰共用设计系统 / 其它页面的实现", not violated, f"违规改了 {violated}")
print(f"       本次源码改动：{[c for c in changed if not c.startswith('public/')]}")

print()
print("=" * 82)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 两项改动完成，其它一切未动")
print("=" * 82)
sys.exit(1 if problems else 0)
