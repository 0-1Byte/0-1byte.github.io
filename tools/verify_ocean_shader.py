"""用 Python 复刻 /ocean/ 的片元着色器数学，验证：
   A. 颜色是否落在「深蓝、低饱和」的目标区间
   B. 海平线的雾气带是否自然（不是硬边）
   C. 相同输入是否稳定（无 NaN / 越界）
   D. 动画在 10 秒内是否「几乎看不出在动」

这不能替代真实 GPU 渲染，但能验证配色与数值是否合理 ——
比「写完就说完成了」可靠。
"""
import math

HORIZON = 0.58


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(e0, e1, x):
    if e0 == e1:
        return 0.0 if x < e0 else 1.0
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def rgb_to_hsl(r, g, b):
    mx, mn = max(r, g, b), min(r, g, b)
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


def shade(uvx, uvy, t=0.0, nx_off=0.0):
    """复刻着色器主函数（噪声用确定性伪随机近似，只关心配色走向）。"""
    aspect = 16 / 9
    nx = (uvx - 0.5) * aspect + nx_off
    d = uvy - HORIZON
    sea = smoothstep(-0.0035, 0.0035, d)

    depth = (uvy - HORIZON) / (1.0 - HORIZON)
    depth = max(0.0, min(1.0, depth))
    persp = 1.0 / (depth * 7.0 + 0.06)
    wp_x = nx * persp * 0.85
    wp_y = persp * 0.5

    def noise(x, y):
        return 0.5 + 0.5 * math.sin(x * 1.7 + y * 2.3 + t * 0.1)

    n1, n2, n3 = noise(wp_x * 0.5, wp_y * 0.5), noise(wp_x * 1.7, wp_y * 1.7), noise(wp_x * 4.2, wp_y * 4.2)
    ripple = (n1 * 0.58 + n2 * 0.27 + n3 * 0.15) * 2.0 - 1.0

    # 修正后：偏移量在 shader 内用 hash 求得，这里用 n1 近似（只影响形状，不影响配色）
    wave = (math.sin((nx * 3.2 + (n1 - 0.5) * 1.6) * 0.9 + t * 0.21) * 0.62
            + math.sin((nx * 3.2 + (n1 - 0.5) * 1.6) * 2.3 - t * 0.37 + 1.7) * 0.38) * 0.16
    crest = (math.sin((nx * 7.5 + 2.1) * 0.9 + t * 0.21 * 1.4) * 0.62
             + math.sin((nx * 7.5 + 2.1) * 2.3 - t * 0.37 * 1.4 + 1.7) * 0.38) * 0.07

    far = 1.0 - smoothstep(0.0, 0.42, depth)
    amp = lerp(0.35, 1.0, far)
    hl = (wave + crest) * amp

    sea_far = (0.400, 0.478, 0.545)
    sea_mid = (0.100, 0.170, 0.238)
    sea_near = (0.032, 0.062, 0.098)
    col = [lerp(sea_far[i], sea_mid[i], smoothstep(0.0, 0.30, depth)) for i in range(3)]
    col = [lerp(col[i], sea_near[i], smoothstep(0.26, 1.0, depth)) for i in range(3)]
    col = [c + ripple * 0.030 * lerp(0.45, 1.0, depth) for c in col]
    col = [c + max(hl, 0.0) * 0.30 * math.exp(-depth * 3.4) for c in col]

    sky_t = max(0.0, min(1.0, -d / HORIZON))
    sky_high = (0.026, 0.056, 0.090)
    sky_mid = (0.066, 0.108, 0.158)
    sky_low = (0.300, 0.360, 0.430)
    sky = [lerp(sky_low[i], sky_mid[i], smoothstep(0.0, 0.42, sky_t)) for i in range(3)]
    sky = [lerp(sky[i], sky_high[i], smoothstep(0.34, 1.0, sky_t)) for i in range(3)]
    cloud = 0.5 + 0.5 * math.sin(nx * 1.5 + sky_t * 3.4 + t * 0.0016)
    sky = [s + (cloud - 0.5) * 0.035 * smoothstep(0.05, 0.8, sky_t) for s in sky]

    out = [lerp(sky[i], col[i], sea) for i in range(3)]
    band = math.exp(-abs(d) * 34.0)
    out = [lerp(out[i], (0.455, 0.520, 0.575)[i], band * 0.55) for i in range(3)]

    vig = smoothstep(1.15, 0.25, math.hypot((uvx - 0.5), (uvy - 0.46) * 1.1))
    out = [c * lerp(0.86, 1.0, vig) for c in out]

    lum = 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]
    out = [lerp(lum, out[i], 0.88) for i in range(3)]
    return out


problems = []

print("=" * 88)
print("A. 配色检查（深蓝 / 低饱和）")
print("=" * 88)
SAMPLES = [
    ("天空顶部", 0.5, 0.02),
    ("天空中部", 0.5, 0.30),
    ("海平线正上", 0.5, 0.55),
    ("海平线正下", 0.5, 0.61),
    ("海面中部", 0.5, 0.78),
    ("海面近处", 0.5, 0.97),
    ("左下角", 0.05, 0.9),
    ("右下角", 0.95, 0.9),
]
for label, x, y in SAMPLES:
    r, g, b = shade(x, y)
    h, s, light = rgb_to_hsl(r, g, b)
    blueish = 195 <= h <= 235
    lowsat = s <= 0.65
    ok = blueish and lowsat
    if not ok:
        problems.append(f"{label} 色相 {h:.0f}° 饱和 {s:.2f} 不在目标区间")
    print(f"  {'OK ' if ok else 'FAIL'} {label:8} "
          f"RGB({r*255:3.0f},{g*255:3.0f},{b*255:3.0f})  "
          f"色相 {h:5.0f}°  饱和 {s:.2f}  明度 {light:.2f}")

print()
print("=" * 88)
print("B. 海平线过渡是否柔和（不应是硬边）")
print("=" * 88)
prev = None
max_jump = 0.0
for i in range(101):
    y = 0.53 + i * 0.0010
    r, g, b = shade(0.5, y)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    if prev is not None:
        max_jump = max(max_jump, abs(lum - prev))
    prev = lum
print(f"  海平线 ±5% 范围内，逐行最大亮度跳变 = {max_jump:.4f}")
ok = max_jump < 0.02
if not ok:
    problems.append(f"海平线跳变过大 {max_jump:.4f}，可能呈硬边")
print(f"  {'OK ' if ok else 'FAIL'} 过渡柔和（阈值 0.02）")

print()
print("=" * 88)
print("C. 数值稳定性")
print("=" * 88)
bad = 0
for i in range(60):
    for j in range(60):
        r, g, b = shade(i / 59, j / 59)
        for c in (r, g, b):
            if math.isnan(c) or math.isinf(c) or c < -1e-6 or c > 1.0 + 1e-6:
                bad += 1
print(f"  {'OK ' if bad == 0 else 'FAIL'} 3600 个采样点，越界/NaN = {bad}")
if bad:
    problems.append(f"有 {bad} 个采样点越界")

print()
print("=" * 88)
print("D. 10 秒内的动态幅度（应几乎察觉不到）")
print("=" * 88)
probe = (0.5, 0.70)
base = shade(*probe, t=0.0)
max_delta = 0.0
for step in range(1, 21):
    t = step * 0.5   # 0.5 秒一帧，共 10 秒
    cur = shade(*probe, t=t)
    max_delta = max(max_delta, max(abs(cur[i] - base[i]) for i in range(3)))
print(f"  海面中部取样点，10 秒内最大通道变化 = {max_delta*255:.2f}/255")
ok = max_delta * 255 < 3.0
if not ok:
    problems.append(f"10 秒内变化 {max_delta*255:.2f}/255 偏大，可能被察觉")
print(f"  {'OK ' if ok else 'FAIL'} 变化极小（阈值 3/255）")

print()
print("=" * 88)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 配色 / 过渡 / 稳定性 / 动态幅度 全部符合目标")
print("=" * 88)
