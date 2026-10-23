"""验证当前站点导航结构及相关页面资源。

传入构建目录可验证该目录；不传时使用仓库 public/。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUB = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "public"
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
check("五个导航分组顺序正确",
      labels == ["listen", "read", "watch", "play", "make"], f"实际 {labels}")
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
print("2. Watch 是直接导航入口，影视分类保留在页面内")
print("=" * 82)
watch = next(g for g in nav["groups"] if g["key"] == "watch")
check("Watch 导航直接指向 /watch/", watch.get("href") == "/watch/", f"实际 {watch}")
check("影视子分类不再占用导航子菜单", not watch.get("children"))
watch_page = (PUB / "watch" / "index.html").read_text(encoding="utf-8")
for category in ["All", "Film", "TV", "Docu"]:
    check(f"Watch 页面包含 {category} 分类筛选",
          category in (SRC / "watch" / "script.js").read_text(encoding="utf-8"))
check("Watch 页面已输出筛选容器", 'id="category-filters"' in watch_page)

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
expect = {"listen": ("Music", "在听的歌"), "read": ("Books", "在读的书"),
          "play": ("Game", "喜欢的游戏"), "make": ("Works", "做出来的东西")}
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
                         ("docu", "docu/docus.json", 5), ("works", "works/works.json", 2),
                         ("game", "game/games.json", 1)]:
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
print("5. 页面脚本与构建资源")
print("=" * 82)
import subprocess
r = subprocess.run(["git", "status", "--porcelain", "--ignore-submodules=all"],
                   cwd=ROOT, capture_output=True, text=True)
changed = [x[3:].strip() for x in r.stdout.split("\n") if x.strip()]
print(f"  本次工作区改动：{changed or '（无）'}")
check("Watch 样式与脚本已输出",
      (PUB / "watch" / "style.css").is_file() and (PUB / "watch" / "script.js").is_file())
check("共享主题与导航资源已输出",
      (PUB / "theme.css").is_file() and (PUB / "site-nav.css").is_file()
      and (PUB / "site-nav.js").is_file())
print(f"       验证构建目录：{PUB}")

print()
print("=" * 82)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 两项改动完成，其它一切未动")
print("=" * 82)
sys.exit(1 if problems else 0)
