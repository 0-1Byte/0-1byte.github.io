"""优化前后体积对比报告（软件渲染口径 + 首屏实际下载口径）。"""
import json
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
MUSIC = ROOT / "static" / "music"
ASSETS = MUSIC / "assets"
songs = json.loads((MUSIC / "songs.json").read_text(encoding="utf-8"))

def kb(n):
    return n / 1024


def mb(n):
    return n / 1048576

# ---------- 1. 全量口径 ----------
orig_all = sum((ASSETS / unquote(s["cover"].replace("/music/assets/", ""))).stat().st_size for s in songs)
unique_bases = sorted({s["img"] for s in songs})
orig_unique = 0
seen = set()
for s in songs:
    p = ASSETS / unquote(s["cover"].replace("/music/assets/", ""))
    if p.name not in seen:
        seen.add(p.name)
        orig_unique += p.stat().st_size
webp = {w: sum((ASSETS / f"{b}-{w}.webp").stat().st_size for b in unique_bases) for w in (240, 320, 480)}

print("=" * 78)
print("一、图片资源总量")
print("=" * 78)
print(f"  歌曲数                        : {len(songs)}")
print(f"  唯一封面图（内容去重后）      : {len(unique_bases)} 张  （原先 213 个文件里有 67 个是重复内容）")
print(f"  优化前 单张原图总大小         : {mb(orig_all):9.2f} MB   ({kb(orig_all)/1024:.2f} GB 的千分之一记法)")
print(f"  优化前 去重后原图总大小       : {mb(orig_unique):9.2f} MB")
print(f"  优化后 webp 三档合计(240/320/480): {mb(sum(webp.values())):9.2f} MB")
print(f"    其中 240w {len(unique_bases)} 个 : {mb(webp[240]):7.2f} MB  平均 {kb(webp[240])/len(unique_bases):5.1f} KB")
print(f"    其中 320w {len(unique_bases)} 个 : {mb(webp[320]):7.2f} MB  平均 {kb(webp[320])/len(unique_bases):5.1f} KB")
print(f"    其中 480w {len(unique_bases)} 个 : {mb(webp[480]):7.2f} MB  平均 {kb(webp[480])/len(unique_bases):5.1f} KB")
print(f"  清理的未引用重复 JPG          : 33 个 / 2.97 MB")

# ---------- 2. 浏览器实际下载口径 ----------
print()
print("=" * 78)
print("二、浏览器实际下载量（srcset 生效后，不再下载 600px 原图）")
print("=" * 78)
print(f"  {'屏型':<26}{'优化前':>12}{'优化后':>12}{'降幅':>10}")
print("  " + "-" * 58)

scenarios = [
    ("桌面 1x（选 240w 档）", 240, 2.0),
    ("桌面 2x（选 480w 档）", 480, 3.0),
    ("手机 2x（选 240w 档）", 240, 4.0),
    ("手机 3x（选 320w 档）", 320, 5.0),
]
for label, w, *rest in scenarios:
    after = sum((ASSETS / f"{b}-{w}.webp").stat().st_size for b in unique_bases)
    # 优化前：每首歌各下载一份原图（无 srcset，直接用 cover 指到的 JPG）
    before = orig_all
    print(f"  {label:<26}{mb(before):>10.2f}MB{mb(after):>10.2f}MB{(1-after/before)*100:>9.1f}%")

# ---------- 3. 首屏 ----------
print()
print("=" * 78)
print("三、首屏 4 张（eager + fetchpriority=high）")
print("=" * 78)
first4 = songs[:4]
for s in first4:
    jpg = (ASSETS / unquote(s["cover"].replace("/music/assets/", ""))).stat().st_size
    w240 = (ASSETS / f"{s['img']}-240.webp").stat().st_size
    w480 = (ASSETS / f"{s['img']}-480.webp").stat().st_size
    print(f"  {s['title'][:26]:<28} 原 {kb(jpg):6.1f}KB  ->  240w {kb(w240):5.1f}KB / 480w {kb(w480):5.1f}KB")
b = sum((ASSETS / unquote(s["cover"].replace("/music/assets/", ""))).stat().st_size for s in first4)
a1 = sum((ASSETS / f"{s['img']}-240.webp").stat().st_size for s in first4)
a2 = sum((ASSETS / f"{s['img']}-480.webp").stat().st_size for s in first4)
print("  " + "-" * 74)
print(f"  {'合计':<28} 原 {kb(b):6.1f}KB  ->  240w {kb(a1):5.1f}KB / 480w {kb(a2):5.1f}KB")
print(f"  首屏降幅: 1x 屏 {(1-a1/b)*100:.1f}%   2x 屏 {(1-a2/b)*100:.1f}%")

# ---------- 4. 滚动到底的总流量 ----------
print()
print("=" * 78)
print("四、全部 213 张滚完的总流量")
print("=" * 78)
print(f"  优化前（每首歌一份原图）    : {mb(orig_all):9.2f} MB")
for w in (240, 320, 480):
    total = sum((ASSETS / f"{s['img']}-{w}.webp").stat().st_size for s in songs)
    print(f"  优化后（同一张图多首歌复用）: {mb(total):9.2f} MB   (全部走 {w}w 档时)")
print(f"  说明：213 首歌映射到 {len(unique_bases)} 个不同 URL，")
print(f"        同一张封面被多首歌引用时浏览器只下载一次。")
