"""验证导出脚本的字段兼容层 —— 不联网，用构造的回包。

网关回包经过字段裁剪，字段名可能与我预设的不同。
这个测试确认：无论回包是哪种常见形状，都能正确取出划线，
且「只有书签没有正文」的条目不会变成空句子。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from weread_export import book_source, extract_marks, pick  # noqa: E402

problems = []


def check(label, ok, detail=""):
    if ok:
        print(f"  OK   {label}")
    else:
        problems.append(label)
        print(f"  FAIL {label}" + (f"  ← {detail}" if detail else ""))


print("=" * 78)
print("1. 出处拼接")
print("=" * 78)
check("书名 + 作者", book_source({"title": "书名", "author": "作者"}) == "《书名》· 作者")
check("只有书名", book_source({"title": "书名"}) == "《书名》")
check("都没有 -> 空", book_source({}) == "")
check("嵌套 book 对象",
      book_source({"book": {"title": "嵌套书", "author": "某人"}}) == "《嵌套书》· 某人")
check("划线节点自带书名",
      book_source(None, {"bookTitle": "直接书名", "author": "甲"}) == "《直接书名》· 甲")

print()
print("=" * 78)
print("2. 多种回包形状都能取出划线")
print("=" * 78)
shapes = [
    ("bookmarks + markedText", {"bookmarks": [
        {"bookId": "x", "bookTitle": "书名A", "author": "作者A",
         "markedText": "句子一", "createTime": 1748563200}]}, 1),
    ("updated + 嵌套 book + markText", {"updated": [
        {"book": {"title": "书名B", "author": "作者B"}, "markText": "句子二"}]}, 1),
    ("data.notes + content", {"data": {"notes": [
        {"content": "句子三", "bookName": "书名C"}]}}, 1),
    ("深层嵌套", {"a": {"b": {"c": [{"text": "句子四", "bookTitle": "书名D"}]}}}, 1),
]
for label, payload, expect in shapes:
    got = extract_marks(payload)
    check(f"{label} -> {expect} 条", len(got) == expect, f"实际 {len(got)}: {got}")

print()
print("=" * 78)
print("3. 只有书签、没有正文的条目不应产生空句子")
print("=" * 78)
check("纯书签 -> 0 条",
      extract_marks({"bookmarks": [{"bookId": "y", "bookmarkId": "z"}]}) == [])
check("空字符串正文被忽略",
      extract_marks({"bookmarks": [{"markedText": "   "}]}) == [])
check("null 正文被忽略",
      extract_marks({"bookmarks": [{"markedText": None}]}) == [])

print()
print("=" * 78)
print("4. 去重")
print("=" * 78)
dup = {"bookmarks": [{"markedText": "重复句"}, {"markedText": "重复句"}]}
check("同一句只保留一次", len(extract_marks(dup)) == 1)

print()
print("=" * 78)
print("5. pick 的取值优先级与类型处理")
print("=" * 78)
check("优先取第一个存在的字段", pick({"a": "x", "b": "y"}, "a", "b") == "x")
check("前面的字段为空则用后面的", pick({"a": "", "b": "y"}, "a", "b") == "y")
check("数字也能取到", pick({"n": 1748563200}, "n") == 1748563200)
check("布尔不应被当成数字", pick({"n": True}, "n") == "")
check("都没有 -> 默认空", pick({}, "a", "b") == "")

print()
print("=" * 78)
print(f"问题合计: {len(problems)}")
for p in problems:
    print("  ✗", p)
if not problems:
    print("  ✓ 字段兼容层可用：多种回包形状都能正确取出划线")
print("=" * 78)
sys.exit(1 if problems else 0)
