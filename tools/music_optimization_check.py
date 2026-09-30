"""最终完整性校验：确认歌曲数据未被改动、页面结构未变、优化按要求落地。"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUSIC = ROOT / "static" / "music"
ASSETS = MUSIC / "assets"
ok = []
bad = []


def check(label, cond, detail=""):
    (ok if cond else bad).append(f"{label}{(' — ' + detail) if detail else ''}")
    print(f"  [{'✓' if cond else '✗'}] {label}{(' — ' + detail) if detail else ''}")


# ---------- 1. songs.json 数据完整性（与优化前的 git 版本逐字段比对）----------
print("1. songs.json 数据未丢失")
old_raw = subprocess.run(
    ["git", "show", "HEAD:static/music/songs.json"],
    cwd=ROOT, capture_output=True, text=True, encoding="utf-8"
).stdout
old = json.loads(old_raw)
new = json.loads((MUSIC / "songs.json").read_text(encoding="utf-8"))

check("条目数一致", len(old) == len(new), f"{len(old)} -> {len(new)}")
fields = ["id", "title", "artist", "lyricist", "composer", "cover", "album", "year", "tags", "url"]
diffs = []
for a, b in zip(old, new):
    for f in fields:
        if a.get(f) != b.get(f):
            diffs.append(f"{a.get('id')}.{f}: {a.get(f)!r} -> {b.get(f)!r}")
check("所有原有字段逐条一致", not diffs, f"{len(diffs)} 处差异" + ("" if not diffs else ": " + str(diffs[:3])))
check("新增字段仅为 img", all(set(b) - set(a) <= {"img"} for a, b in zip(old, new)))
check("cover 字段原样保留（JPG 兜底可用）", all(b["cover"] == a["cover"] for a, b in zip(old, new)))

# ---------- 2. 图片资源 ----------
print("\n2. 图片资源")
bases = sorted({s["img"] for s in new})
missing = [f"{b}-{w}.webp" for b in bases for w in (240, 320, 480) if not (ASSETS / f"{b}-{w}.webp").exists()]
check("每个 img 主干都有 240/320/480 三档", not missing, f"缺失 {len(missing)}")
check("唯一封面去重生效", len(bases) == 146, f"{len(bases)} 个主干对应 {len(new)} 首歌")
check("img 命名 URL 安全（无空格/无百分号编码）",
      all(" " not in b and "%" not in b for b in bases))

# 无引用的 JPG 是否已清干净
referenced = {s["cover"].replace("/music/assets/", "") for s in new}
from urllib.parse import unquote
unused_jpg = [p.name for p in ASSETS.glob("*.jpg") if p.name not in {unquote(r) for r in referenced}]
check("未引用的重复 JPG 已清理", not unused_jpg, f"剩余 {len(unused_jpg)}: {unused_jpg[:3]}")

# ---------- 3. script.js 关键逻辑 ----------
print("\n3. script.js")
js = (MUSIC / "script.js").read_text(encoding="utf-8")
check("不再使用 Date.now() 破缓存", "Date.now()" not in js)
check("不再使用 cache: \"no-store\"", 'cache: "no-store"' not in js)
check('使用固定版本号 songs.json?v=', "songs.json?v=${DATA_VERSION}" in js)
check("生成 srcset", "srcset=" in js)
check("生成 sizes", "sizes=" in js)
check("首屏 eager + fetchpriority=high", 'loading="eager" fetchpriority="high"' in js)
check("首屏之外 lazy", 'loading="lazy"' in js)
check("decoding=async", 'decoding="async"' in js)
check("JPG 加载失败兜底", "data-fallback" in js and "bindCoverFallback" in js)
check("保留词曲作者 overlay", "credit-overlay" in js)
check("保留 Apple Music 外链", "rel=\"noopener noreferrer\"" in js)
check("保留主题切换", "pref-theme" in js)
check("EAGER_COUNT 在 4~8 之间", 4 <= int(re.search(r"EAGER_COUNT = (\d+)", js).group(1)) <= 8)

# ---------- 4. CSS 布局未变 ----------
# 注意：阶段 2 起调色板与圆角取值统一收敛到 static/theme.css，
# 本文件只消费变量。所以这两项改为检查「变量是否存在且被引用」，
# 以及「theme.css 里的取值是否仍是原来的 7px」。
print("\n4. style.css 布局")
css = (MUSIC / "style.css").read_text(encoding="utf-8")
theme_css = (ROOT / "static" / "theme.css").read_text(encoding="utf-8")


def has_grid_cols(text, n):
    """匹配 grid-template-columns: repeat(n, minmax(0,1fr))，容忍空格差异。"""
    return re.search(r"repeat\(\s*%d\s*,\s*minmax\(\s*0\s*,\s*1fr\s*\)\s*\)" % n, text) is not None


check("桌面四列", has_grid_cols(css, 4))
check("平板三列", has_grid_cols(css, 3))
check("手机两列", has_grid_cols(css, 2))
check("封面 1:1 比例", re.search(r"aspect-ratio\s*:\s*1\b", css) is not None)
check("圆角走统一变量且取值为 7px",
      "border-radius: var(--radius)" in css and "--radius: 7px" in theme_css)
check("hover 缩放/透明效果", "scale(1.025)" in css and "opacity: .72" in css)
check("深浅色变量齐全（已收敛到 theme.css）",
      ':root[data-theme="dark"]' in theme_css and "--muted" in theme_css and "--surface" in theme_css)

# ---------- 5. index.html ----------
print("\n5. index.html")
html = (MUSIC / "index.html").read_text(encoding="utf-8")
check("preload songs.json（并行预取）", 'rel="preload" href="/music/songs.json?v=2" as="fetch"' in html)
check("preload 与 fetch 的 MIME/模式匹配", 'type="application/json"' in html and 'crossorigin="anonymous"' in html)
check("script.js 版本号已更新", re.search(r"script\.js\?v=\d+", html) is not None)
check("页面标题未变", "Things I like to hear." in html)
check("导航未变", 'class="site-nav"' in html)

print("\n" + "=" * 70)
print(f"通过 {len(ok)} 项，失败 {len(bad)} 项")
if bad:
    print("失败项:")
    for b in bad:
        print("  ✗", b)
