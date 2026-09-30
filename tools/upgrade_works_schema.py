"""Works 升级（阶段 6）：给数据补上状态机与详情字段。

原则：只搬运已有事实，不编造内容。
  · status 规范化为阶段 6 的统一词表（Idea / Building / Paused / Shipped / Abandoned）
    原来的中文取值「已上线」「使用中」在词表里都有对应，因此归类是确定的；
    同时保留原始中文到 statusLabel，页面上仍显示你写的那个词。
  · 新增字段 started / problem / learned / demo 一律留空字符串 —— 我没有这些信息，
    不会替你编。字段存在（schema 就位），有值时才在详情里显示。
  · demo 与 url 等价（spec 里叫 Demo），保留 url 以免破坏既有字段名。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
F = ROOT / "static" / "works" / "works.json"

# 阶段 6 的状态词表；同时接受 spec 里的写法（大小写不敏感）
VOCAB = ["Idea", "Building", "Paused", "Shipped", "Abandoned", "Ongoing"]

# 已有中文取值 -> 词表。这是确定性的映射，不是猜测：
#   已上线 = 已经发布并可用 -> Shipped
#   使用中 = 我自己在持续用、且仍在演进 -> Ongoing
LEGACY = {
    "已上线": "Shipped",
    "已发布": "Shipped",
    "使用中": "Ongoing",
    "进行中": "Building",
    "暂停": "Paused",
    "废弃": "Abandoned",
    "想法": "Idea",
}

items = json.loads(F.read_text(encoding="utf-8"))
for it in items:
    raw = str(it.get("status", "")).strip()
    canon = ""
    if raw:
        # 先看是否已经是词表里的值（大小写不敏感）
        for v in VOCAB:
            if raw.lower() == v.lower():
                canon = v
                break
        if not canon:
            canon = LEGACY.get(raw, "")

    it["status"] = canon
    it["statusLabel"] = raw          # 保留原始文字，页面优先显示它

    # 新字段：无信息则留空，不编造
    for key in ("started", "problem", "learned", "demo"):
        it.setdefault(key, "")

    # 保持字段顺序稳定，方便日后手工编辑
    order = ["title", "tagline", "summary", "type", "status", "statusLabel",
             "started", "period", "year", "role", "tech", "cover",
             "problem", "highlights", "learned", "url", "demo", "repo", "note"]
    ordered = {k: it[k] for k in order if k in it}
    for k in it:
        if k not in ordered:
            ordered[k] = it[k]
    it.clear()
    it.update(ordered)

F.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(f"已更新 {len(items)} 条")
for it in items:
    print(f"  {it['title']:14} status={it['status'] or '（空）':10} statusLabel={it['statusLabel']}")
    print(f"      新字段: " + "  ".join(f"{k}={it[k]!r}" for k in ("started", "problem", "learned", "demo")))
