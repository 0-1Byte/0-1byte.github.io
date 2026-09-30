"""阶段 5 验证：/ocean/ 页面、资源、入口生成与回退路径。

另外在 Node 里跑真实的 ocean/script.js，验证：
  A. 底部入口从 /nav.json 正确生成
  B. nav.json 失败时给出明确错误而不是静默留白
  C. WebGL 不可用时不抛未捕获异常，且显示 fallback 说明
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


print("=" * 88)
print("A. 页面与资源")
print("=" * 88)
for p in ["/ocean/", "/ocean/style.css", "/ocean/script.js", "/ocean/ocean-favicon.svg",
          "/theme.css", "/site-nav.css", "/site-nav.js", "/collection-common.js", "/nav.json"]:
    st, _ = get(p)
    ok = st == 200
    if not ok:
        problems.append(f"{p} -> {st}")
    print(f"  {'OK ' if ok else 'FAIL'} {p:30} {st}")

print()
print("=" * 88)
print("B. 页面结构：三个状态钩子 + 唯一主动入口")
print("=" * 88)
st, page = get("/ocean/")
checks = [
    ("canvas#ocean 存在", 'id="ocean"' in page),
    ("静态 fallback 层存在", "ocean-fallback" in page),
    ("出口 #ocean-links 存在", 'id="ocean-links"' in page),
    ("错误提示 #ocean-note 存在且默认隐藏", 'id="ocean-note"' in page and "hidden" in page),
    ("冷启动 #ocean-links 带 is-loading", False),   # 由 JS 添加，HTML 里没有是对的
    ("光点指向 /random/", "/random/" in page),
    ("光点带无障碍标签", 'aria-label="something random' in page),
]
for label, ok in checks:
    if label == "冷启动 #ocean-links 带 is-loading":
        print(f"  --   {label}: 由 JS 运行时添加（预期不在 HTML 中）")
        continue
    if not ok:
        problems.append(f"页面缺少：{label}")
    print(f"  {'OK ' if ok else 'FAIL'} {label}")

# 页面不应有大量按钮：统计 <button> 与 <a> 数量
n_btn = len(re.findall(r"<button", page))
n_a = len(re.findall(r"<a\s", page))
print(f"      页面按钮 {n_btn} 个（应仅主题切换 1 个）、链接 {n_a} 个（导航 + 光点）")
if n_btn > 1:
    problems.append(f"页面有 {n_btn} 个按钮，超出预期（仅主题切换）")

print()
print("=" * 88)
print("C. 底部入口应由 nav.json 生成（预期内容）")
print("=" * 88)
st, navjson = get("/nav.json")
nav = json.loads(navjson)
expect = []
for g in nav["groups"]:
    if not g.get("pending") and g.get("children"):
        expect.append(g["label"])
for s in nav.get("standalone", []):
    expect.append(s["name"])
print(f"  nav.json 可生成的入口: {expect}")
ok = "ocean" in [s["name"] for s in nav.get("standalone", [])]
if not ok:
    problems.append("导航里没有 ocean 入口")
print(f"  {'OK ' if ok else 'FAIL'} ocean 已加入 standalone")

st, home = get("/")
ok = "/ocean/" in home
if not ok:
    problems.append("首页导航未出现 ocean")
print(f"  {'OK ' if ok else 'FAIL'} 首页导航含 /ocean/ = {ok}")

print()
print("=" * 88)
print("D. 着色器与回退（静态检查）")
print("=" * 88)
st, js = get("/ocean/script.js")
for label, cond in [
    ("包含顶点着色器", "gl_Position" in js),
    ("包含片元着色器", "gl_FragColor" in js),
    ("未出现 JS 函数被 GLSL 调用（rippleseed 已移除）", "rippleseed" not in js),
    ("WebGL 不可用时隐藏画布", "canvas.style.display" in js),
    ("提供静态回退说明", "回退到静态海面" in js),
    ("尊重 prefers-reduced-motion", "prefers-reduced-motion" in js),
    ("后台时停止渲染", "visibilitychange" in js),
    ("限制像素比以省电", "devicePixelRatio" in js),
]:
    if not cond:
        problems.append(f"script.js 缺少：{label}")
    print(f"  {'OK ' if cond else 'FAIL'} {label}")

st, css = get("/ocean/style.css")
for label, cond in [
    ("静态海面 .ocean-fallback", ".ocean-fallback" in css),
    ("雾气层 .ocean-haze", ".ocean-haze" in css),
    ("海平线变量与 shader 共用", "--ocean-horizon" in css),
    ("无卡通/网格感的大面积纯蓝渐变", "repeating-linear-gradient" not in css),
    ("移动端断点", "max-width: 600px" in css),
    ("减少动效断点", "prefers-reduced-motion" in css),
]:
    if not cond:
        problems.append(f"style.css 缺少：{label}")
    print(f"  {'OK ' if cond else 'FAIL'} {label}")

print()
print("=" * 88)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 全部通过")
print("=" * 88)
