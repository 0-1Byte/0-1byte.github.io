"""阶段 6 验证：Now / Fragments / Works。

Fragments 的渲染需要至少一条内容才能验证列表与 JSON。
按照「不生成假数据」的要求，这里临时写入一条测试用 fragment，
验证完立刻删除并重建，仓库不会留下任何编造内容。
"""
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUB = ROOT / "public"
HUGO = ROOT / "hugo.exe"
BASE = "http://127.0.0.1:1364"

TMP_FRAGMENTS = [
    ROOT / "content" / "fragments" / "_tmp_verify_a.md",
    ROOT / "content" / "fragments" / "_tmp_verify_b.md",
]

problems = []


def build():
    r = subprocess.run([str(HUGO), "--logLevel", "warn"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def check(label, ok, detail=""):
    """detail 只在失败时打印 —— 成功时打印会让人误以为检查没过。"""
    if not ok:
        problems.append(f"{label} {detail}".strip())
        print(f"  FAIL {label}" + (f"  ← {detail}" if detail else ""))
    else:
        print(f"  OK   {label}")


# =========================================================================
print("=" * 90)
print("A. Now —— 数据来自 data/now.yaml，改数据不改模板")
print("=" * 90)
st, now = get("/now/")
check("/now/ 可访问", st == 200, f"HTTP {st}")

yaml = (ROOT / "data" / "now.yaml").read_text(encoding="utf-8")
for section in ["reading", "listening", "watching", "building", "thinking", "obsessed"]:
    in_yaml = re.search(rf"^{section}:", yaml, re.M) is not None
    check(f"data/now.yaml 有 {section} 分区", in_yaml)

# 有值的分区必须渲染
for section, item in [("reading", "李飞飞"), ("listening", "方大同"),
                      ("watching", "The Thinking Game"), ("building", "信息架构")]:
    check(f"渲染 {section} 的内容", item in now, f"找不到 {item!r}")

# 空分区不应渲染标题（空列表）
for section in ["thinking", "obsessed"]:
    rendered = re.search(rf'class="home-label">{section}<', now) is not None
    check(f"空分区 {section} 不渲染标题", not rendered)

check("updated 显示在底部", "2026-09" in now)
check("内容不再来自 front matter（模板改用 site.Data.now）",
      "site.Data.now" in (ROOT / "layouts" / "now" / "single.html").read_text(encoding="utf-8"))

# =========================================================================
print()
print("=" * 90)
print("B. Fragments —— 临时写入内容以验证渲染，之后删除")
print("=" * 90)

TMP_FRAGMENTS[0].write_text(
    "---\ndate: 2026-09-30\ntags:\n  - agent\n  - life\n---\n"
    "「知道」和「做到」之间，可能隔着比知识更多的东西。\n", encoding="utf-8")
TMP_FRAGMENTS[1].write_text(
    "---\ndate: 2026-09-23\ntags:\n  - build\n---\n"
    "一个只有一句话的碎片。\n", encoding="utf-8")

try:
    out = build()
    if "ERROR" in out:
        problems.append(f"构建报错：{out[:200]}")

    st, frag = get("/fragments/")
    check("/fragments/ 可访问", st == 200, f"HTTP {st}")
    check("标题为 Fragments", "Fragments" in frag)
    check("使用归档列表 .frag-list", "frag-list" in frag)
    check("不是博客卡片（无 post-entry）", "post-entry" not in frag)
    check("不是博客卡片（无 entry-cover）", "entry-cover" not in frag)

    dates = re.findall(r'class="frag-date"[^>]*>([^<]+)<', frag)
    check("日期格式 2026.09.30", dates and dates[0] == "2026.09.30", f"实际 {dates}")
    check("按时间倒序", dates == ["2026.09.30", "2026.09.23"], f"实际 {dates}")
    check("两条都渲染", len(dates) == 2)
    check("短句正文渲染", "比知识更多的东西" in frag)
    check("标签渲染", "agent" in frag and "life" in frag)
    check("条数统计显示", "2 条记录" in frag)
    check("引入 pages.css", "pages.css" in frag)

    # 只有 front matter、没有正文的条目不应渲染
    (ROOT / "content" / "fragments" / "_tmp_verify_c.md").write_text(
        "---\ndate: 2026-09-20\n---\n", encoding="utf-8")
    build()
    st, frag2 = get("/fragments/")
    dates2 = re.findall(r'class="frag-date"[^>]*>([^<]+)<', frag2)
    check("无正文的条目不显示", dates2 == ["2026.09.30", "2026.09.23"], f"实际 {dates2}")
    (ROOT / "content" / "fragments" / "_tmp_verify_c.md").unlink()

    # JSON 输出（供 Random 抽取）
    st, fragjson = get("/fragments/fragments.json")
    check("/fragments/fragments.json 可访问", st == 200, f"HTTP {st}")
    if st == 200:
        arr = json.loads(fragjson)
        check("JSON 是数组且 2 条", isinstance(arr, list) and len(arr) == 2, f"实际 {len(arr)}")
        first = arr[0]
        for key in ["title", "subtitle", "body", "date", "url", "tags"]:
            check(f"JSON 含字段 {key}", key in first)
        check("JSON 按日期倒序", arr[0]["date"] == "2026.09.30", f"实际 {arr[0]['date']}")
        check("body 为纯文本", "<" not in first["body"], first["body"][:60])
    build()

finally:
    for f in TMP_FRAGMENTS + [ROOT / "content" / "fragments" / "_tmp_verify_c.md"]:
        if f.exists():
            f.unlink()
    build()
    print("  （临时 fragment 已删除并重建）")

# 空状态
print()
st, empty = get("/fragments/")
check("空状态下 /fragments/ 仍可访问", st == 200, f"HTTP {st}")
check("空状态有明确说明", "还没有记录" in empty, "")
st, emptyjson = get("/fragments/fragments.json")
check("空状态下 JSON 为 []", st == 200 and emptyjson.strip() == "[]", f"HTTP {st} {emptyjson[:40]!r}")

# =========================================================================
print()
print("=" * 90)
print("C. Works —— 状态词表与新字段")
print("=" * 90)
works = json.loads((ROOT / "static" / "works" / "works.json").read_text(encoding="utf-8"))
VOCAB = ["Idea", "Building", "Paused", "Shipped", "Abandoned", "Ongoing"]
for w in works:
    check(f"{w['title']}: status 在词表内", w.get("status") in VOCAB, f"status={w.get('status')!r}")
    check(f"{w['title']}: 保留原始 statusLabel", "statusLabel" in w, f"{w.get('statusLabel')!r}")
    for key in ["started", "problem", "learned", "demo"]:
        check(f"{w['title']}: 有 {key} 字段", key in w)

abandoned_supported = (ROOT / "static" / "works" / "style.css").read_text(encoding="utf-8")
check("Abandoned 有独立样式（失败也是记录）", '[data-status="abandoned"]' in abandoned_supported)
for s in VOCAB:
    check(f"状态样式 {s}", f'[data-status="{s.lower()}"]' in abandoned_supported)
check("未识别状态有兜底样式", '[data-status="unknown"]' in abandoned_supported)

js = (ROOT / "static" / "works" / "script.js").read_text(encoding="utf-8")
check("卡片渲染状态圆点", "status-dot" in js)
check("详情渲染「要解决的问题」", "要解决的问题" in js)
check("详情渲染「学到什么」", "学到什么" in js)
check("demo 与 url 等价", 'text(work.url) || text(work.demo)' in js)
check("详情里有状态", "detail-status" in js)

print()
print("=" * 90)
print("D. 导航")
print("=" * 90)
st, navtext = get("/nav.json")
nav = json.loads(navtext)
labels = [g["label"] for g in nav["groups"]]
check("导航含 think", "think" in labels, f"实际 {labels}")
check("think 不再是 pending", all(not g.get("pending") for g in nav["groups"]))
check("think 指向 /fragments/",
      any(c["href"] == "/fragments/" for g in nav["groups"] for c in g["children"]))

print()
print("=" * 90)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 全部通过")
print("=" * 90)
sys.exit(1 if problems else 0)
