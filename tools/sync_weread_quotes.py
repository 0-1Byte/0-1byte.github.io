#!/usr/bin/env python3
"""Fetch personal WeRead highlights and atomically publish sanitized quotes."""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weread_gateway import API_BOOKMARKLIST, API_NOTEBOOKS, WereadError, call
from weread_secret import assert_no_key_leak, load_key

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "weread_quotes.json"
TEMP_PATH = OUT_PATH.with_suffix(".json.tmp")
REQUEST_INTERVAL = 1.0


class SyncError(RuntimeError):
    def __init__(self, message, stage, request_path=None):
        RuntimeError.__init__(self, message)
        self.stage = stage
        self.request_path = request_path


def pick_value(node, *keys):
    if not isinstance(node, dict):
        return ""
    for key in keys:
        value = node.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
    return ""


def normalize_text(value):
    if not isinstance(value, str):
        return ""
    text = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def source_record(mark):
    return {
        "source": mark.get("source", ""),
        "author": mark.get("author", ""),
        "chapter": mark.get("chapter", ""),
        "book_id": mark.get("book_id", ""),
        "chapter_uid": mark.get("chapter_uid", ""),
        "bookmark_id": mark.get("bookmark_id", ""),
    }


def book_metadata(book, detail=None):
    title = ""
    author = ""
    for source in (book, detail):
        if not isinstance(source, dict):
            continue
        title = title or pick_value(source, "title", "bookTitle", "bookName")
        author = author or pick_value(source, "author", "bookAuthor")
        nested = source.get("book") if isinstance(source.get("book"), dict) else {}
        title = title or pick_value(nested, "title", "bookTitle", "bookName")
        author = author or pick_value(nested, "author", "bookAuthor")
    return title, author


def chapter_title_map(detail):
    chapters = detail.get("chapters")
    if chapters is None:
        return {}, set()
    if not isinstance(chapters, list):
        raise SyncError("章节列表结构无效", "bookmarks_parse", API_BOOKMARKLIST)
    candidates = {}
    for chapter in chapters:
        if not isinstance(chapter, dict):
            raise SyncError("章节记录不是对象", "bookmarks_parse", API_BOOKMARKLIST)
        uid = pick_value(chapter, "chapterUid", "chapter_uid")
        title = pick_value(chapter, "title", "chapterTitle", "chapterName")
        if uid and title:
            candidates.setdefault(uid, set()).add(title)
    ambiguous = {uid for uid, titles in candidates.items() if len(titles) > 1}
    return {
        uid: next(iter(titles))
        for uid, titles in candidates.items()
        if len(titles) == 1
    }, ambiguous


def as_quote_item(mark, book=None, chapters=None, detail=None):
    if not isinstance(mark, dict) or mark.get("type") == 0:
        return None
    text = normalize_text(pick_value(mark, "markText", "markedText", "text"))
    if not text:
        return None
    book = book if isinstance(book, dict) else {}
    title, author = book_metadata(book, detail)
    book_id = pick_value(mark, "bookId", "book_id") or pick_value(
        book, "bookId", "book_id", "id"
    )
    chapter_uid = pick_value(mark, "chapterUid", "chapter_uid")
    bookmark_id = pick_value(mark, "bookmarkId", "bookmark_id")
    chapter = (chapters or {}).get(chapter_uid, "")
    scope = book_id or ""
    if bookmark_id:
        dedupe_key = "id:{}:{}".format(scope, bookmark_id)
    else:
        dedupe_key = "fallback:{}:{}:{}".format(scope, chapter_uid, text)
    return {
        "text": text,
        "source_type": "weread",
        "source": title,
        "author": author,
        "chapter": chapter,
        "book_id": book_id,
        "chapter_uid": chapter_uid,
        "bookmark_id": bookmark_id,
        "also_sources": [],
        "_key": dedupe_key,
    }


def dedupe(items):
    seen = set()
    by_text = {}
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = normalize_text(item.get("text"))
        if not text:
            continue
        source = source_record(item)
        key = item.get("_key") or "fallback:{}:{}:{}".format(
            source["book_id"], source["chapter_uid"], text
        )
        if key in seen:
            continue
        seen.add(key)
        existing = by_text.get(text)
        if existing is None:
            cleaned = {
                "text": text,
                "source_type": "weread",
                "source": source["source"],
                "author": source["author"],
                "chapter": source["chapter"],
                "book_id": source["book_id"],
                "chapter_uid": source["chapter_uid"],
                "bookmark_id": source["bookmark_id"],
                "also_sources": [],
            }
            by_text[text] = cleaned
            out.append(cleaned)
            continue
        primary = source_record(existing)
        signature = tuple(source[key] for key in (
            "source", "author", "chapter", "book_id", "chapter_uid", "bookmark_id"
        ))
        primary_signature = tuple(primary[key] for key in (
            "source", "author", "chapter", "book_id", "chapter_uid", "bookmark_id"
        ))
        alternatives = existing["also_sources"]
        alternative_signatures = {
            tuple(alternative.get(field, "") for field in (
                "source", "author", "chapter", "book_id", "chapter_uid", "bookmark_id"
            ))
            for alternative in alternatives
        }
        if signature != primary_signature and signature not in alternative_signatures:
            alternatives.append(source)
    return out


def iter_notebooks(api_key, endpoint, count=100, progress=None, diagnostics=None):
    last_sort = None
    seen_cursors = set()
    page = 0
    while True:
        params = {"count": count}
        if last_sort is not None:
            params["lastSort"] = last_sort
        try:
            obj = call(
                endpoint,
                api_key,
                API_NOTEBOOKS,
                params,
                diagnostics=diagnostics,
            )
        except WereadError as exc:
            raise SyncError("个人笔记本请求失败", "notebooks", API_NOTEBOOKS) from exc
        if not isinstance(obj.get("books"), list):
            raise SyncError("个人笔记本响应缺少 books 数组", "notebooks_parse", API_NOTEBOOKS)
        has_more = obj.get("hasMore")
        if has_more not in (0, 1, False, True, "0", "1"):
            raise SyncError(
                "个人笔记本响应缺少有效 hasMore 字段",
                "notebooks_parse",
                API_NOTEBOOKS,
            )

        books = obj["books"]
        page += 1
        if progress:
            progress("notebooks_page", page, len(books))
        if has_more in (0, False, "0", None):
            for book in books:
                if not isinstance(book, dict):
                    raise SyncError(
                        "个人笔记本包含非对象记录",
                        "notebooks_parse",
                        API_NOTEBOOKS,
                    )
                yield book
            break
        if not books:
            raise SyncError(
                "hasMore 为真但笔记本页为空",
                "notebooks_pagination",
                API_NOTEBOOKS,
            )

        next_sort = books[-1].get("sort")
        if next_sort is None:
            raise SyncError(
                "hasMore 为真但末项缺少 sort 游标",
                "notebooks_pagination",
                API_NOTEBOOKS,
            )
        cursor_key = str(next_sort)
        if cursor_key in seen_cursors or cursor_key == str(last_sort):
            raise SyncError(
                "笔记本分页游标未前进",
                "notebooks_pagination",
                API_NOTEBOOKS,
            )
        seen_cursors.add(cursor_key)
        for book in books:
            if not isinstance(book, dict):
                raise SyncError(
                    "个人笔记本包含非对象记录",
                    "notebooks_parse",
                    API_NOTEBOOKS,
                )
            yield book
        last_sort = next_sort
        time.sleep(REQUEST_INTERVAL)


def notebook_has_notes(book):
    value = book.get("noteCount")
    if value is None:
        value = book.get("bookmarkCount", 0)
    try:
        return int(value or 0) > 0
    except (TypeError, ValueError):
        raise SyncError("笔记本 noteCount 字段无效", "notebooks_parse", API_NOTEBOOKS)


def fetch_all(api_key, endpoint, count, limit=0, progress=None, diagnostics=None):
    all_items = []
    notebooks = list(iter_notebooks(
        api_key,
        endpoint,
        count=count,
        progress=progress,
        diagnostics=diagnostics,
    ))
    scanned_books = len(notebooks)
    eligible = []
    seen_book_ids = set()
    for book in notebooks:
        book_id = pick_value(book, "bookId", "book_id", "id")
        if book_id:
            if book_id in seen_book_ids:
                raise SyncError(
                    "分页结果重复包含同一笔记本",
                    "notebooks_pagination",
                    API_NOTEBOOKS,
                )
            seen_book_ids.add(book_id)
        if notebook_has_notes(book):
            if not book_id:
                raise SyncError(
                    "有个人划线的笔记本记录缺少 bookId",
                    "notebooks_parse",
                    API_NOTEBOOKS,
                )
            eligible.append((book, book_id))
    eligible_books = len(eligible)
    read_books = 0
    unmapped_chapters = 0
    ambiguous_chapter_ids = 0

    for eligible_index, (book, book_id) in enumerate(eligible, 1):
        if progress:
            progress("bookmarks", eligible_index, eligible_books)
        try:
            detail = call(
                endpoint,
                api_key,
                API_BOOKMARKLIST,
                {"bookId": book_id},
                diagnostics=diagnostics,
            )
        except WereadError as exc:
            raise SyncError(
                "单书个人划线请求失败",
                "bookmarks",
                API_BOOKMARKLIST,
            ) from exc
        if not isinstance(detail.get("updated"), list):
            raise SyncError(
                "单书划线响应缺少 updated 数组",
                "bookmarks_parse",
                API_BOOKMARKLIST,
            )
        read_books += 1
        chapters, ambiguous_chapters = chapter_title_map(detail)
        ambiguous_chapter_ids += len(ambiguous_chapters)
        for mark in detail["updated"]:
            item = as_quote_item(mark, book, chapters, detail)
            if item:
                if item["chapter_uid"] and not item["chapter"]:
                    unmapped_chapters += 1
                all_items.append(item)
        if limit and len(dedupe(all_items)) >= limit:
            break
        time.sleep(REQUEST_INTERVAL)

    items = dedupe(all_items)
    if limit:
        items = items[:limit]
    stats = {
        "notebooks": scanned_books,
        "eligible_books": eligible_books,
        "read_books": read_books,
        "nonempty_highlights": len(all_items),
        "quotes": len(items),
        "unmapped_chapters": unmapped_chapters,
        "ambiguous_chapter_ids": ambiguous_chapter_ids,
    }
    return items, stats


def write_json(items, output_path=None):
    output_path = Path(output_path) if output_path else OUT_PATH
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    payload = json.dumps(items, ensure_ascii=False, indent=2) + "\n"
    assert_no_key_leak(payload, str(output_path))
    parsed = json.loads(payload)
    if not isinstance(parsed, list) or any(
        not isinstance(item, dict)
        or set(item.keys()) != {
            "text", "source_type", "source", "author", "chapter",
            "book_id", "chapter_uid", "bookmark_id", "also_sources",
        }
        or not item["text"].strip()
        or item["source_type"] != "weread"
        or any(not isinstance(item[field], str) for field in (
            "source", "author", "chapter", "book_id", "chapter_uid", "bookmark_id"
        ))
        or not isinstance(item["also_sources"], list)
        or any(
            not isinstance(source, dict)
            or set(source.keys()) != {
                "source", "author", "chapter", "book_id", "chapter_uid", "bookmark_id"
            }
            or any(not isinstance(source[field], str) for field in (
                "source", "author", "chapter", "book_id", "chapter_uid", "bookmark_id"
            ))
            for source in item["also_sources"]
        )
        for item in parsed
    ):
        raise ValueError("生成数据校验失败")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(str(temp_path), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        with open(str(temp_path), "r", encoding="utf-8") as handle:
            if json.load(handle) != parsed:
                raise ValueError("临时数据文件校验失败")
        os.replace(str(temp_path), str(output_path))
    finally:
        if temp_path.exists():
            temp_path.unlink()


def main():
    parser = argparse.ArgumentParser(description="同步微信读书个人划线并生成首页数据")
    parser.add_argument("--count", type=int, default=100, help="每页笔记本数量")
    parser.add_argument("--limit", type=int, default=0, help="受控测试用的句子上限")
    parser.add_argument("--dry-run", action="store_true", help="只同步并报告统计，不写正式文件")
    parser.add_argument("--quiet-progress", action="store_true", help="关闭脱敏进度")
    parser.add_argument(
        "--output",
        type=Path,
        default=OUT_PATH,
        help="输出路径；CI 应指定临时目录，避免把个人数据放进仓库工作区",
    )
    args = parser.parse_args()
    if args.count < 1 or args.limit < 0:
        parser.error("--count 必须大于 0，--limit 不得小于 0")

    try:
        api_key, endpoint = load_key()
    except Exception as exc:
        print("凭据加载失败：{}".format(type(exc).__name__))
        return 2

    def report_progress(stage, current, total):
        if args.quiet_progress:
            return
        if stage == "notebooks_page":
            print("阶段=笔记本分页 页码={} 本页数量={}".format(current, total))
        else:
            print("阶段=个人划线请求 书籍序号={}/{}".format(current, total))

    def report_request(info):
        if args.quiet_progress:
            return
        stage = {
            API_NOTEBOOKS: "笔记本分页",
            API_BOOKMARKLIST: "个人划线",
        }.get(info["api_name"], "网关请求")
        print(
            "请求诊断：阶段={} 请求路径={} 尝试={}/{} 异常类型={} 异常消息={} "
            "errno={} winerror={} 出错位置={}:{}:{} HTTP={} 耗时秒={:.3f}".format(
                stage,
                info["api_name"],
                info["attempt"],
                info["max_attempts"],
                info["exception_type"] or "-",
                info.get("exception_message", "-"),
                info.get("errno") if info.get("errno") is not None else "-",
                info.get("winerror") if info.get("winerror") is not None else "-",
                info.get("file") or "-",
                info.get("function") or "-",
                info.get("line") if info.get("line") is not None else "-",
                info["http_status"] if info["http_status"] is not None else "-",
                info["elapsed_seconds"],
            )
        )

    try:
        items, stats = fetch_all(
            api_key,
            endpoint,
            args.count,
            limit=args.limit,
            progress=report_progress,
            diagnostics=report_request,
        )
    except SyncError as exc:
        cause = exc.__cause__
        details = (
            " 请求路径={} 尝试次数=- 异常类型={} 类型={} 耗时秒=- HTTP=- errcode=-"
        ).format(
            exc.request_path or "-",
            type(cause).__name__ if cause else type(exc).__name__,
            exc.stage,
        )
        if isinstance(cause, WereadError):
            exception_type = cause.transport_type or (
                type(cause.__cause__).__name__ if cause.__cause__ is not None else cause.kind
            )
            location = "{}:{}:{}".format(
                cause.exception_file or "-",
                cause.exception_function or "-",
                cause.exception_line if cause.exception_line is not None else "-",
            )
            details = (
                " 请求路径={} 尝试次数={} 异常类型={} 异常消息={} errno={} winerror={}"
                " 出错位置={} 类型={} 耗时秒={:.3f}"
                " HTTP={} errcode={}"
            ).format(
                exc.request_path or "-",
                cause.attempts,
                exception_type,
                cause.safe_exception_message or "-",
                cause.exception_errno if cause.exception_errno is not None else "-",
                cause.exception_winerror if cause.exception_winerror is not None else "-",
                location,
                cause.kind,
                cause.elapsed_seconds,
                cause.http_status if cause.http_status is not None else "-",
                cause.errcode if cause.errcode is not None else "-",
            )
        print("同步失败：阶段={}{}".format(exc.stage, details))
        return 3
    except WereadError as exc:
        print("同步失败：阶段=网关 请求路径={} 尝试次数={} 异常类型={} 类型={} 耗时秒={:.3f} HTTP={} errcode={}".format(
            "-",
            exc.attempts,
            exc.transport_type or exc.kind,
            exc.kind,
            exc.elapsed_seconds,
            exc.http_status if exc.http_status is not None else "-",
            exc.errcode if exc.errcode is not None else "-",
        ))
        return 3
    except Exception as exc:
        print("同步失败：阶段=本地处理 类型={}".format(type(exc).__name__))
        return 4

    if not args.dry_run:
        try:
            write_json(items, args.output)
        except Exception as exc:
            print("同步失败：阶段=文件写入 类型={}".format(type(exc).__name__))
            return 4

    print("扫描笔记本总数: {}".format(stats["notebooks"]))
    print("有个人划线的书籍: {}".format(stats["eligible_books"]))
    print("成功读取划线的书籍: {}".format(stats["read_books"]))
    print("获取的非空划线数量: {}".format(stats["nonempty_highlights"]))
    print("去重后的句子数量: {}".format(stats["quotes"]))
    print("未映射章节划线数量: {}".format(stats["unmapped_chapters"]))
    print("章节 ID 标题冲突数量: {}".format(stats["ambiguous_chapter_ids"]))
    if args.dry_run:
        print("dry-run: 正式数据文件未改写")
    else:
        try:
            output_label = args.output.resolve().relative_to(ROOT.resolve())
        except ValueError:
            output_label = args.output
        print("结果文件: {}".format(output_label))
        print("数据校验: 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
