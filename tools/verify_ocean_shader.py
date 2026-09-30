"""用 Python 复刻 /ocean/ 的片元着色器数学，验证重做后的目标：

  A. 三套色板确实是「白天亮 / 黄昏金 / 夜晚深蓝」
  B. 权重混合在一天中连续（不会硬切）
  C. 任意时刻的最终画面都落在可接受的明度与低饱和范围内
  D. 10 秒内的动态幅度几乎察觉不到
  E. 数值稳定（无 NaN / 越界）

颜色现在由 uniform 传入，所以这里直接读 script.js 里的 PALETTES 定义，
保证验证对象与实际使用的数值是同一份。
"""
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "static" / "ocean" / "script.js").read_text(encoding="utf-8")

problems = []

# ---- 从 script.js 里读出真实的 PALETTES ----
block = re.search(r"const PALETTES = \{(.*?)\n  \};", JS, re.S)
if not block:
    print("✗ 无法从 script.js 解析 PALETTES")
    raise SystemExit(1)


def parse_palettes(text):
    out = {}
    for m in re.finditer(r"(\w+): \{(.*?)\}", text, re.S):
        name, body = m.group(1), m.group(2)
        fields = {}
        for f in re.finditer(r"(\w+): \[([^\]]+)\]", body):
            fields[f.group(1)] = [float(x) for x in f.group(2).split(",")]
        sw = re.search(r"sway: ([\d.]+)", body)
        if sw:
            fields["sway"] = float(sw.group(1))
        out[name] = fields
    return out


P = parse_palettes(block.group(1))
print("=" * 84)
print("A. 三套色板")
print("=" * 84)
for name in ("day", "dusk", "night"):
    if name not in P:
        problems.append(f"缺少色板 {name}")
        continue
    p = P[name]


    def lum(c):
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


    def hsl(c):
        r, g, b = c
        mx, mn = max(c), min(c)
        light = (mx + mn) / 2
        if mx == mn:
            return 0.0, 0.0, light
        d = mx - mn
        sat = d / (2 - mx - mn) if light > 0.5 else d / (mx + mn)
        if mx == r:
            h = ((g - b) / d) % 6
        elif mx == g:
            h = (b - r) / d + 2
        else:
            h = (r - g) / d + 4
        return h * 60, sat, light

    h, s, light = hsl(p["seaMid"])
    warm = p["skyLow"][0] - p["skyLow"][2]
    print(f"  {name:6} 天空明度 {lum(p['skyMid']):.2f}  海面色相 {h:5.0f}° 饱和 {s:.2f}  "
          f"地平线暖度 {warm:+.2f}  sway {p['sway']}")
    if not (195 <= h <= 240 or name == "dusk"):
        problems.append(f"{name} 海面色相 {h:.0f}° 偏离深蓝区间")
    if s > 0.70:
        problems.append(f"{name} 海面饱和 {s:.2f} 偏高")

dayL = 0.2126 * P["day"]["skyMid"][0] + 0.7152 * P["day"]["skyMid"][1] + 0.0722 * P["day"]["skyMid"][2]
duskL = 0.2126 * P["dusk"]["skyMid"][0] + 0.7152 * P["dusk"]["skyMid"][1] + 0.0722 * P["dusk"]["skyMid"][2]
nightL = 0.2126 * P["night"]["skyMid"][0] + 0.7152 * P["night"]["skyMid"][1] + 0.0722 * P["night"]["skyMid"][2]
if not (dayL > duskL > nightL):
    problems.append("明度排序应为 白天 > 黄昏 > 夜晚")
print(f"  明度排序 白天({dayL:.2f}) > 黄昏({duskL:.2f}) > 夜晚({nightL:.2f})  "
      f"{'✓' if dayL > duskL > nightL else '✗'}")

print()
print("=" * 84)
print("B. 权重混合连续性（每 15 分钟采一次）")
print("=" * 84)


def weights(hour):
    stops = [0, 4.5, 7, 12, 17, 19.5, 22, 24]
    keys = ["night", "night", "dusk", "day", "dusk", "dusk", "night", "night"]
    i = 0
    while i < len(stops) - 1 and hour >= stops[i + 1]:
        i += 1
    t = (hour - stops[i]) / max(stops[i + 1] - stops[i], 1e-6)
    a, b = keys[i], keys[min(i + 1, len(keys) - 1)]
    w = {"day": 0.0, "dusk": 0.0, "night": 0.0}
    if a == b:
        w[a] = 1.0
        return w
    w[a] = 1 - t
    w[b] += t
    return w


def blend(w):
    out = {}
    for f in ["skyHigh", "skyMid", "skyLow", "seaFar", "seaMid", "seaNear", "horizon"]:
        out[f] = [P["day"][f][c] * w["day"] + P["dusk"][f][c] * w["dusk"] + P["night"][f][c] * w["night"]
                  for c in range(3)]
    return out


prev = None
max_jump = 0.0
for i in range(0, 96):
    hour = i * 0.25
    pal = blend(weights(hour))
    lum = sum(pal["skyMid"][c] * [0.2126, 0.7152, 0.0722][c] for c in range(3))
    if prev is not None:
        max_jump = max(max_jump, abs(lum - prev))
    prev = lum
print(f"  每 15 分钟的天空明度最大跳变 = {max_jump:.4f}")
if max_jump > 0.06:
    problems.append(f"明度跳变 {max_jump:.4f} 偏大，可能看出硬切")
print(f"  {'OK ' if max_jump <= 0.06 else 'FAIL'} 过渡连续（阈值 0.06）")

print()
print("=" * 84)
print("C. 全天采样的最终画面（复刻着色器合成）")
print("=" * 84)
HORIZON = 0.58


def smoothstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0))) if e1 != e0 else (0.0 if x < e0 else 1.0)
    return t * t * (3 - 2 * t)


def shade(uvx, uvy, pal, t=0.0):
    d = uvy - HORIZON
    sea = smoothstep(-0.0035, 0.0035, d)
    depth = max(0.0, min(1.0, (uvy - HORIZON) / (1 - HORIZON)))
    col = [P["day"]["seaFar"][c] * 0 for c in range(3)]
    col = [pal["seaFar"][c] + (pal["seaMid"][c] - pal["seaFar"][c]) * smoothstep(0, 0.30, depth) for c in range(3)]
    col = [col[c] + (pal["seaNear"][c] - col[c]) * smoothstep(0.26, 1.0, depth) for c in range(3)]
    skyT = max(0.0, min(1.0, -d / HORIZON))
    sky = [pal["skyLow"][c] + (pal["skyMid"][c] - pal["skyLow"][c]) * smoothstep(0, 0.42, skyT) for c in range(3)]
    sky = [sky[c] + (pal["skyHigh"][c] - sky[c]) * smoothstep(0.34, 1.0, skyT) for c in range(3)]
    out = [sky[c] + (col[c] - sky[c]) * sea for c in range(3)]
    band = math.exp(-abs(d) * 34.0)
    out = [out[c] + (pal["horizon"][c] - out[c]) * band * 0.55 for c in range(3)]
    lum = sum(out[c] * [0.2126, 0.7152, 0.0722][c] for c in range(3))
    out = [lum + (out[c] - lum) * 0.88 for c in range(3)]
    return out


def hsl2(c):
    mx, mn = max(c), min(c)
    light = (mx + mn) / 2
    if mx == mn:
        return 0.0, 0.0, light
    dd = mx - mn
    sat = dd / (2 - mx - mn) if light > 0.5 else dd / (mx + mn)
    if mx == c[0]:
        h = ((c[1] - c[2]) / dd) % 6
    elif mx == c[1]:
        h = (c[2] - c[0]) / dd + 2
    else:
        h = (c[0] - c[1]) / dd + 4
    return h * 60, sat, light


bad = 0
for hour in (3, 8, 13, 18, 20, 23):
    pal = blend(weights(hour))
    for (label, ux, uy) in [("天空", 0.5, 0.30), ("海平线", 0.5, 0.60), ("海面", 0.5, 0.85)]:
        c = shade(ux, uy, pal)
        h, s, light = hsl2(c)
        if s > 0.80:
            bad += 1
            print(f"      ✗ {hour}:00 {label} 饱和 {s:.2f} 过高")
        if any(math.isnan(v) or v < -1e-6 or v > 1 + 1e-6 for v in c):
            bad += 1
            print(f"      ✗ {hour}:00 {label} 数值越界 {c}")
    c = shade(0.5, 0.60, pal)
    h, s, light = hsl2(c)
    print(f"  {hour:>5}:00  海平线 RGB({c[0]*255:3.0f},{c[1]*255:3.0f},{c[2]*255:3.0f})  "
          f"色相 {h:5.0f}° 饱和 {s:.2f} 明度 {light:.2f}")
if bad:
    problems.append(f"{bad} 个采样点饱和/数值异常")
print(f"  {'OK ' if bad == 0 else 'FAIL'} 全天画面低饱和、数值稳定")

print()
print("=" * 84)
print("D. 10 秒内的动态幅度（逐帧读数，不用上界估算）")
print("=" * 84)


def _hash2(x, y):
    s = math.sin(x * 127.1 + y * 311.7) * 43758.5453123
    return s - math.floor(s)


def _noise(x, y):
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    ux = fx * fx * (3 - 2 * fx)
    uy = fy * fy * (3 - 2 * fy)
    a = _hash2(ix, iy)
    b = _hash2(ix + 1, iy)
    c = _hash2(ix, iy + 1)
    d = _hash2(ix + 1, iy + 1)
    top = a + (b - a) * ux
    bot = c + (d - c) * ux
    return top + (bot - top) * uy


def _swell(x, t):
    return math.sin(x * 0.90 + t * 0.21) * 0.62 + math.sin(x * 2.30 - t * 0.37 + 1.7) * 0.38


def motion(uvx, uvy, t, aspect=16 / 9):
    """shader 里随时间变化的那两项：ripple 与高位 swell 的高光。"""
    nx = (uvx - 0.5) * aspect
    depth = max(0.0, min(1.0, (uvy - HORIZON) / (1 - HORIZON)))
    persp = 1.0 / (depth * 7.0 + 0.06)
    wx, wy = nx * persp * 0.85, persp * 0.5
    n1 = _noise(wx * 0.50 + t * 0.008, wy * 0.50 - t * 0.005)
    n2 = _noise(wx * 1.70 - t * 0.014, wy * 1.70 + t * 0.019)
    n3 = _noise(wx * 4.20 + t * 0.026, wy * 4.20 - t * 0.031)
    ripple = (n1 * 0.58 + n2 * 0.27 + n3 * 0.15) * 2.0 - 1.0
    phase_a = nx * 3.2 + (_hash2(math.floor(wx * 64.0), math.floor(wy * 64.0)) - 0.5) * 1.6
    hl = (_swell(phase_a, t) * 0.16 + _swell(nx * 7.5 + 2.1, t * 1.4) * 0.07) \
        * (0.35 + 0.65 * (1 - smoothstep(0, 0.42, depth)))
    return ripple * 0.030 * (0.45 + 0.55 * depth) + max(hl, 0.0) * 0.30 * math.exp(-depth * 3.4)


worst = 0.0
worst_at = None
for (ux, uy) in [(0.5, 0.62), (0.5, 0.72), (0.5, 0.85), (0.25, 0.70), (0.75, 0.70), (0.5, 0.95)]:
    base = motion(ux, uy, 0.0)
    mx = max(abs(motion(ux, uy, k * 0.1) - base) for k in range(1, 101))
    print(f"  uv=({ux}, {uy})  最大通道变化 {mx*255:5.2f}/255")
    if mx > worst:
        worst, worst_at = mx, (ux, uy)
print(f"  最坏 {worst*255:.2f}/255（uv={worst_at}）")
if worst * 255 > 4:
    problems.append(f"10 秒内变化 {worst*255:.2f}/255 偏大")
print(f"  {'OK ' if worst * 255 <= 4 else 'FAIL'} 几乎察觉不到（阈值 4/255；8 位 1 级 = 1/255）")

print()
print("=" * 84)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 色板 / 过渡 / 画面 / 动态幅度 全部符合目标")
print("=" * 84)
