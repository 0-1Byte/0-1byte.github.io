"""微信读书网关探针 —— 用官方文档里的两个接口直接验证连通性。

在你自己电脑上运行：

    python tools/weread_probe.py

它依次调用官方文档明确的接口，确认 Key 与网关都可用：

  1. /user/notebooks    笔记本概览：所有有笔记的书（bookId、书名、作者、
                        划线数 noteCount、想法数 reviewCount）
  2. /book/bookmarklist 单本书的划线内容（markText），拿第一本的 bookId 试

这两个接口都来自 Tencent/WeChatReading 官方 skill 文档
（skills/notes.md），不是猜的。

如果返回 -2013「鉴权失败」，改用：
    python tools/weread_diag.py
它会逐项定位是 Key 文本问题、鉴权头问题，还是 Key 本身未被接受。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weread_secret import KeyError_, load_key, redact  # noqa: E402
from weread_gateway import (  # noqa: E402
    API_BOOKMARKLIST, API_NOTEBOOKS, SKILL_VERSION, WereadError, call,
)

problems = []


def check(label, ok, detail=""):
    if ok:
        print(f"  OK   {label}")
    else:
        problems.append(label)
        print(f"  FAIL {label}" + (f"  ← {detail}" if detail else ""))


def main():
    print("=" * 80)
    print("微信读书网关探针")
    print("=" * 80)

    try:
        api_key, endpoint = load_key()
    except KeyError_ as e:
        print(str(e))
        return 2

    print(f"  Key          : {redact(api_key)}")
    print(f"  网关         : {endpoint}")
    print(f"  skill_version: {SKILL_VERSION}")
    print()

    # ---------- 1. 笔记本概览 ----------
    print("1) /user/notebooks —— 笔记本概览")
    print()
    try:
        nb = call(endpoint, api_key, API_NOTEBOOKS, {"count": 20})
    except WereadError as e:
        print(f"  {e}")
        print()
        print("  如果上面是 -2013 鉴权失败，跑这个逐项定位：")
        print("      python tools/weread_diag.py")
        print("  如果是网络失败，先设代理：")
        print("      set HTTPS_PROXY=http://127.0.0.1:7897")
        return 3

    print(f"  顶层字段: {list(nb.keys())[:12]}")
    total_books = nb.get("totalBookCount")
    total_notes = nb.get("totalNoteCount")
    print(f"  有笔记的书: {total_books}    笔记总数: {total_notes}")

    books = nb.get("books")
    if not isinstance(books, list) or not books:
        print()
        print("  没有取到 books 列表。回包内容（字段名可能变了）：")
        print(f"    {json.dumps(nb, ensure_ascii=False)[:400]}")
        print("  把这一行贴回来，我据此调整解析。")
        return 4

    print(f"  本页 {len(books)} 本：")
    for b in books[:10]:
        if not isinstance(b, dict):
            continue
        title = (b.get("book") or {}).get("title") or b.get("bookTitle") or "?"
        author = (b.get("book") or {}).get("author") or b.get("author") or ""
        nc = b.get("noteCount", 0)
        rc = b.get("reviewCount", 0)
        bm = b.get("bookmarkCount", 0)
        print(f"    {title}  —— {author}   划线 {nc} · 想法 {rc} · 书签 {bm}")
    print()
    check("笔记本概览可用", True)

    # ---------- 2. 单本划线内容 ----------
    print()
    print("2) /book/bookmarklist —— 取第一本书的划线内容")
    print()
    first = books[0] if isinstance(books[0], dict) else {}
    book_id = first.get("bookId") or first.get("book_id") or ""
    title = (first.get("book") or {}).get("title") or first.get("bookTitle") or "?"

    if not book_id:
        print("  第一本没有 bookId，跳过。")
        return 0

    try:
        bm = call(endpoint, api_key, API_BOOKMARKLIST, {"bookId": book_id})
    except WereadError as e:
        print(f"  {e}")
        return 5

    print(f"  《{title}》顶层字段: {list(bm.keys())[:10]}")
    updated = bm.get("updated")
    if isinstance(updated, list):
        print(f"  划线条数: {len(updated)}")
        for it in updated[:5]:
            if isinstance(it, dict):
                text = it.get("markText") or ""
                print(f"    · {text[:60]}")
    else:
        print(f"  没有 updated 数组。回包：{json.dumps(bm, ensure_ascii=False)[:300]}")
    check("单本划线可用", isinstance(updated, list))

    print()
    print("=" * 80)
    if problems:
        print(f"问题: {problems}")
    else:
        print("两个接口都可用 —— 可以直接导出：")
        print("    python tools/weread_export.py")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
