"""最终画质校验：模拟浏览器的 object-fit:cover 中心裁切，比较优化前后真正显示出来的像素。

页面结构：.cover-wrap 是 aspect-ratio:1 的正方形，.cover 用 object-fit:cover 填满，
所以浏览器实际展示的是「图片按比例放大到覆盖正方形 → 中心裁切」的结果。
这里对优化前后的图各自复现这条路径，再算 PSNR。
包含非正方形封面（宽高比 1.121 / 0.705 等），用来确认没有被拉伸变形。
"""
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import unquote

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MUSIC = ROOT / "static" / "music"
ASSETS = MUSIC / "assets"
SONGS = MUSIC / "songs.json"

DISPLAY = 235          # 桌面端 CSS 实际显示边长
DPR = 2                # 取 2x 屏，对应 srcset 会选中的档位
TARGET = DISPLAY * DPR


def browser_render(im: Image.Image, target: int) -> Image.Image:
    """复现 object-fit:cover 到正方形：等比缩放到覆盖 target²，再中心裁切。"""
    im = im.convert("RGB")
    w, h = im.size
    scale = max(target / w, target / h)
    nw, nh = max(target, round(w * scale)), max(target, round(h * scale))
    im = im.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - target) // 2, (nh - target) // 2
    return im.crop((left, top, left + target, top + target))


def psnr(a: Image.Image, b: Image.Image) -> float:
    pa, pb = a.load(), b.load()
    w, h = a.size
    total = 0
    for y in range(h):
        for x in range(w):
            va, vb = pa[x, y], pb[x, y]
            for c in range(3):
                d = va[c] - vb[c]
                total += d * d
    mse = total / (w * h * 3)
    return 99.0 if mse == 0 else 10 * math.log10(255 * 255 / mse)


songs = json.loads(SONGS.read_text(encoding="utf-8"))

# 按内容去重，保证每个不同封面只测一次
unique = {}
for s in songs:
    p = ASSETS / unquote(s["cover"].replace("/music/assets/", ""))
    unique.setdefault(hashlib.sha256(p.read_bytes()).hexdigest(), (p, s["img"]))

print(f"唯一封面: {len(unique)} 张   模拟显示尺寸: {TARGET}px (桌面 {DISPLAY}px @2x)")
print("=" * 92)

results = []
for h, (jpg, base) in unique.items():
    webp = ASSETS / f"{base}-480.webp"
    if not webp.exists():
        continue
    with Image.open(jpg) as a, Image.open(webp) as b:
        orig_ar = a.size[0] / a.size[1]
        rendered_a = browser_render(a, TARGET)
        rendered_b = browser_render(b, TARGET)
        # 衍生图是否等比（宽/高 与源一致）
        ar_kept = abs((b.size[0] / b.size[1]) - orig_ar) < 0.01
        p = psnr(rendered_a, rendered_b)
    results.append((p, jpg.name, base, orig_ar, jpg.stat().st_size, webp.stat().st_size, ar_kept))

results.sort()
print(f"\n最差的 6 张（PSNR 最低）:")
print(f"  {'PSNR':>6}  {'宽高比':>7}  {'等比':>4}  {'原图':>8} {'480webp':>8}  文件")
for p, name, base, ar, js, ws, kept in results[:6]:
    print(f"  {p:6.1f}  {ar:7.3f}  {'是' if kept else '否 !!':>4}  {js/1024:6.1f}K {ws/1024:7.1f}K  {base}")

print(f"\n最好的 3 张:")
for p, name, base, ar, js, ws, kept in results[-3:]:
    print(f"  {p:6.1f}  {ar:7.3f}  {'是' if kept else '否 !!':>4}  {js/1024:6.1f}K {ws/1024:7.1f}K  {base}")

vals = [r[0] for r in results]
non_square = [r for r in results if abs(r[3] - 1.0) > 0.01]
print("\n" + "=" * 92)
print(f"  测试张数            : {len(vals)}")
print(f"  平均 PSNR           : {sum(vals)/len(vals):.1f} dB")
print(f"  最低 PSNR           : {min(vals):.1f} dB")
print(f"  PSNR > 35dB 的张数  : {sum(1 for v in vals if v > 35)}/{len(vals)}")
print(f"  非正方形封面        : {len(non_square)} 张，全部等比保留: {all(r[6] for r in non_square)}")
print(f"  非正方形中最低 PSNR : {min((r[0] for r in non_square), default=0):.1f} dB")
print("\n  参考: >40dB 几乎无法分辨 / >35dB 视觉基本一致 / >30dB 良好 / <28dB 可察觉劣化")
