"""从微信读书导出划线，合并进首页句子库。用官方 Agent API Gateway。

    python tools/weread_probe.py      # 先探一次，确认接口名与字段
    python tools/weread_export.py     # 导出 -> static/quotes/wechat.yaml
    python tools/import_wechat_quotes.py --dry-run
    python tools/import_wechat_quotes.py

接口事实（来自 Tencent/WeChatReading 官方 skill 文档，非猜测）：
  · 统一入口 POST i.weread.qq.com/api/agent/gateway
  · body 里用 `api_name` 指定接口，业务参数与它平铺在同一层
  · 每次请求必须带 skill_version
  · /_list 可列出全部接口；errvector=0 表示成功
  · 个人笔记总览是 /user/notebooks

导出流程分两步，因为划线必须先知道 bookId：
  1. /user/notebooks        取笔记本概览（每本书的 noteCount/bookId）
  2. 对每本书取划线明细

第 2 步的接口名由 --probe 确定后写进 .secrets/probe.json；
没有探测结果时脚本会明确提示，而不是乱试。

密钥安全见 tools/weread_secret.py 与 static/quotes/README.md。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weread_secret import KeyError_, assert_no_key_leak, load_key, redact  # noqa: E402
from weread_gateway import (  # noqa: E402
    API_NOTEBOOKS, WereadError, call, redact_error,
)

ROOT = Path(__file__).resolve().parents[1]
OUT_YAML = ROOT / "static" / "quotes" / "wechat.yaml"
CONF = ROOT / ".secrets" / "weread.json"


def load_conf():
    if CONF.exists():
        try:
            return json.loads(CONF.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save_conf(conf):
    CONF.parent.mkdir(parents=True, exist_ok=True)
    CONF.write_text(json.dumps(conf, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- 字段兼容层 ----------
# 网关回包经过字段裁剪，文档也说明字段名以官方说明为准。
# 这里对常见写法做兼容，取不到就跳过该条，而不是崩掉。

def pick(node, *names, default=""):
    for n in names:
        v = node.get(n)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return v
    return default


def book_source(book, mark=None):
    """拼出「《书名》· 作者」。"""
    title = ""
    author = ""
    for src in (mark or {}, book or {}):
        if not isinstance(src, dict):
            continue
        title = title or str(pick(src, "bookTitle", "title", "bookName"))
        author = author or str(pick(src, "author", "bookAuthor"))
        b = src.get("book")
        if isinstance(b, dict):
            title = title or str(pick(b, "title", "bookName"))
            author = author or str(pick(b, "author"))
    if title and author:
        return f"《{title}》· {author}"
    if title:
        return f"《{title}》"
    return ""


def extract_marks(obj):
    """从任意层级的回包里找出划线条目。

    返回 [{text, source}]。只认「有正文的」条目，
    没有正文的（如纯书签）不会变成空句子。
    """
    found = []

    def walk(node, book_ctx=None):
        if isinstance(node, dict):
            ctx = node if isinstance(node.get("book"), dict) or node.get("bookTitle") else book_ctx
            text = pick(node, "markedText", "markText", "text", "content", "abstract")
            if text:
                found.append({"text": text, "source": book_source(ctx, node)})
            for v in node.values():
                walk(v, ctx)
        elif isinstance(node, list):
            for v in node:
                walk(v, book_ctx)

    walk(obj)

    seen, out = set(), []
    for it in found:
        if it["text"] in seen:
            continue
        seen.add(it["text"])
        out.append(it)
    return out


def write_yaml(items, note=""):
    def q(value):
        if value == "":
            return '""'
        if any(c in value for c in ':#[]{}&*!|>\'"%@`') or value != value.strip():
            return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
        return value

    lines = [
        "# 由 tools/weread_export.py 生成 —— 请勿手工编辑（会被下次导出覆盖）",
        "# 这个文件被 .gitignore 忽略，不会提交、不会上线。",
        f"# 共 {len(items)} 条",
    ]
    if note:
        lines.append(f"# {note}")
    lines.append("")
    for it in items:
        lines.append(f"- text: {q(it['text'])}")
        if it.get("source"):
            lines.append(f"  source: {q(it['source'])}")
    body = "\n".join(lines) + "\n"

    # 落盘前的最后一道闸
    assert_no_key_leak(body, str(OUT_YAML.relative_to(ROOT)))

    OUT_YAML.parent.mkdir(parents=True, exist_ok=True)
    OUT_YAML.write_text(body, encoding="utf-8")
    return OUT_YAML


def main():
    ap = argparse.ArgumentParser(description="从微信读书导出划线")
    ap.add_argument("--limit", type=int, default=0, help="最多导出多少条（0=全部）")
    ap.add_argument("--books", type=int, default=0, help="最多处理多少本书（0=全部）")
    ap.add_argument("--verbose", action="store_true", help="打印每本书的处理情况")
    args = ap.parse_args()

    try:
        api_key, endpoint = load_key()
    except KeyError_ as e:
        print(str(e))
        return 2

    conf = load_conf()
    marks_api = conf.get("marks_api", "")

    # ---------- 1. 笔记本概览 ----------
    print("读取笔记本概览…")
    try:
        notebooks = call(endpoint, api_key, API_NOTEBOOKS, {"count": 100})
    except WereadError as e:
        print(f"失败：{redact_error(str(e))}")
        print()
        print("如果提示接口不存在或 404，先跑：python tools/weread_probe.py")
        return 3

    books = notebooks.get("books") if isinstance(notebooks, dict) else None
    if not isinstance(books, list) or not books:
        print("没有取到笔记本列表。回包顶层字段：")
        print(f"  {list(notebooks.keys())[:12] if isinstance(notebooks, dict) else type(notebooks)}")
        print("把这一行贴回来，我据此调整字段解析。")
        return 4

    print(f"  共 {len(books)} 本有笔记的书")
    if args.books:
        books = books[:args.books]

    # ---------- 2. 划线明细 ----------
    if not marks_api:
        # 没有探测结果：先把概览里能直接拿到的内容导出，并说明下一步
        print()
        print("还没有确定「划线明细」的接口名（.secrets/weread.json 里没有 marks_api）。")
        print("先跑一次探针，它会列出可用接口：")
        print("    python tools/weread_probe.py")
        print()
        # 有些回包在概览层就带了划线，先试着抽一遍
        items = extract_marks(notebooks)
        if items:
            path = write_yaml(items, "来自笔记本概览")
            print(f"不过概览回包里已经带了 {len(items)} 条可直接用的内容，已写入 {path.relative_to(ROOT)}")
            return 0
        return 5

    print(f"逐本取划线，接口：{marks_api}")
    all_items = []
    processed = 0
    for b in books:
        if not isinstance(b, dict):
            continue
        book_id = pick(b, "bookId", "book_id", "id")
        title = pick(b, "bookTitle", "title", "bookName")
        note_count = b.get("noteCount") or b.get("bookmarkCount") or 0
        if not book_id:
            continue
        try:
            detail = call(endpoint, api_key, marks_api, {"bookId": book_id})
        except WereadError as e:
            print(f"  [跳过] {title}: {redact_error(str(e))[:80]}")
            continue
        got = extract_marks(detail)
        processed += 1
        if args.verbose:
            print(f"  {title}: 笔记 {note_count} 条 -> 取到 {len(got)} 条")
        all_items.extend(got)
        if args.limit and len(all_items) >= args.limit:
            break

    # 去重
    seen, items = set(), []
    for it in all_items:
        if it["text"] in seen:
            continue
        seen.add(it["text"])
        items.append(it)

    if args.limit:
        items = items[:args.limit]

    print(f"  处理 {processed} 本，去重后 {len(items)} 条")
    if not items:
        print()
        print("没有取到任何划线。可能原因：")
        print("  · 接口名不对 -> 跑 python tools/weread_probe.py 重新确认")
        print("  · 回包字段名变了 -> 用 --verbose 看每本书取到多少条，把输出贴回来")
        return 6

    path = write_yaml(items)
    print(f"已写入 {path.relative_to(ROOT)}")
    print()
    print("接下来：")
    print("    python tools/import_wechat_quotes.py --dry-run")
    print("    python tools/import_wechat_quotes.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
