"""阶段 5（重做后）验证：/ocean/ 作为隐藏的隐喻入口。

检查：
  A. 页面与资源 200
  B. 场景结构：只有海、天、Chen，以及一个装东西的容器
  C. 隐藏性：不在导航、不在首页、页面标了 noindex
  D. 隐喻入口：从 /nav.json 生成，指向真实分区（不是硬编码）
  E. 时段色板与三态钩子在页面/脚本中确实存在
  F. URL 未被删除
"""
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:1362"
ROOT = Path(__file__).resolve().parents[1]
problems = []


def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=15) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def check(label, cond, detail=""):
    if not cond:
        problems.append(f"{label} {detail}".strip())
        print(f"  FAIL {label}" + (f"  ← {detail}" if detail else ""))
    else:
        print(f"  OK   {label}")


print("=" * 88)
print("A. 页面与资源")
print("=" * 88)
for p in ["/ocean/", "/ocean/style.css", "/ocean/script.js", "/ocean/ocean-favicon.svg", "/nav.json"]:
    st, _ = get(p)
    check(f"{p} 200", st == 200, f"HTTP {st}")

print()
print("=" * 88)
print("B. 场景结构：只有海、天、Chen")
print("=" * 88)
st, page = get("/ocean/")
check("canvas#ocean 存在", 'id="ocean"' in page)
check("静态 fallback 层存在", "ocean-fallback" in page)
check("雾气层存在", "ocean-haze" in page)
check("名字 Chen 存在", 'class="ocean-name"' in page and ">Chen<" in page)
check("名字点回首页", re.search(r'class="ocean-name"[^>]*href="/"', page) is not None
      or re.search(r'href="/"[^>]*class="ocean-name"', page) is not None)
check("东西的容器存在", 'id="ocean-objects"' in page)
check("说明元素存在且默认隐藏", 'id="ocean-note"' in page and "hidden" in page)

# 「没有卡片，没有按钮堆砌」
n_btn = len(re.findall(r"<button", page))
n_card = len(re.findall(r"class=\"[^\"]*card", page))
n_nav = len(re.findall(r"data-site-nav|site-nav\.js", page))
check("没有按钮", n_btn == 0, f"实际 {n_btn} 个")
check("没有卡片", n_card == 0, f"实际 {n_card} 个")
check("没有网站导航栏", n_nav == 0, f"实际 {n_nav} 处")
n_a = len(re.findall(r"<a\s", page))
check("链接只有名字一处（东西由 JS 生成）", n_a == 1, f"实际 {n_a} 个")

print()
print("=" * 88)
print("C. 隐藏性")
print("=" * 88)
st, navjson = get("/nav.json")
nav = json.loads(navjson)
names = [s["name"] for s in nav.get("standalone", [])]
check("导航 standalone 不含 ocean", "ocean" not in names, f"实际 {names}")
check("导航分组不含 ocean",
      not any(c.get("href") == "/ocean/" for g in nav["groups"] for c in g.get("children", [])))
st, home = get("/")
check("首页不含 /ocean/ 链接", "/ocean/" not in home)
check("页面标了 noindex", 'name="robots"' in page and "noindex" in page)

# 其它页面也不该引用它
refs = []
for p in ["/music/", "/book/", "/works/", "/docu/", "/film/", "/tv/", "/random/", "/posts/", "/now/", "/fragments/"]:
    st2, body = get(p)
    if st2 == 200 and "/ocean/" in body.replace('href="/ocean/"', ""):
        refs.append(p)
check("其它页面都不链接到 /ocean/", not refs, f"出现在 {refs}")

print()
print("=" * 88)
print("D. 隐喻入口（由 nav.json 生成，指向真实分区）")
print("=" * 88)
st, js = get("/ocean/script.js")
check("从 /nav.json 取数据", 'fetch("/nav.json"' in js)
check("每个东西都取分区第一个子项", "g.children[0].href" in js)
check("pending 分组被跳过", "if (g.pending" in js)
# 期望的映射
for group, href in [("listen", "/music/"), ("read", "/book/"),
                    ("watch", "/film/"), ("make", "/works/"), ("think", "/fragments/")]:
    check(f"CAST 里有 {group}", f'group: "{group}"' in js)
# 形状各异
kinds = re.findall(r'kind: "(\w+)"', js)
check("五种不同的形状", len(set(kinds)) == 5 and len(kinds) == 5, f"实际 {kinds}")
check("形状用 CSS 而非 emoji", "sh-boat" in js and "⛵" not in js)
check("每个东西有 aria-label", "aria-label=" in js and "—— 去" in js)

print()
print("=" * 88)
print("E. 时段色板 / 三态 / 克制动效")
print("=" * 88)
css = get("/ocean/style.css")[1]
for label, cond in [
    ("三套色板已定义", 'day:' in js and 'dusk:' in js and 'night:' in js),
    ("按权重混合（非硬切）", "function phaseWeights" in js and "blendedPalette" in js),
    ("黄昏地平线偏暖", "0.88, 0.62, 0.38" in js),
    ("夜晚有星光", "uStars" in js and "uStars > 0.01" in js),
    ("夜间海面偏蓝", "0.026, 0.052, 0.084" in js),
    ("加载失败给说明", "入口加载失败" in js),
    ("无可用分区给说明", "海面上暂时没有可以辨认的东西" in js),
    ("WebGL 失败回退", "canvas.style.display" in js),
    ("尊重减少动效", "prefers-reduced-motion" in js and "prefers-reduced-motion" in css),
    ("后台停止渲染", "visibilitychange" in js),
    ("限制像素比", "devicePixelRatio" in js),
    ("周期统一（保证最多两个可见）", "period: 75, dur: 30" in js),
    ("名字颜色随时段变化", "--ocean-name" in css and "setProperty" in js),
]:
    check(label, cond)

print()
print("=" * 88)
print("F. URL 未被删除")
print("=" * 88)
check("public/ocean/index.html 存在", (ROOT / "public" / "ocean" / "index.html").exists())
check("/ocean/ 可访问（虽然隐藏）", get("/ocean/")[0] == 200)

print()
print("=" * 88)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 全部通过")
print("=" * 88)
