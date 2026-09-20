"""Batch-add books with covers from public book metadata APIs."""

from __future__ import print_function

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


DATA_FILE = Path(__file__).resolve().parents[1] / "static" / "book" / "books.json"
OPEN_LIBRARY_URL = "https://openlibrary.org/search.json?title={}&limit=10"
GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes?q=intitle:{}&maxResults=10"
USER_AGENT = "0-1byte.github.io book importer/1.1"
TITLE_ALIASES = {
    "有限与无限的游戏": "Finite and Infinite Games",
    "平面国": "Flatland",
    "我看见的世界": "The Worlds I See",
    "鱼不存在": "The Fish Does Not Exist",
}


def fetch_json(url):
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize(value):
    return " ".join(str(value or "").casefold().split())


def slug(title):
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title.casefold()).strip("-")
    return value or "book"


def from_open_library(title):
    data = fetch_json(OPEN_LIBRARY_URL.format(quote(title)))
    docs = data.get("docs", [])
    if not docs:
        return None
    wanted = normalize(title)
    book = next(
        (item for item in docs if normalize(item.get("title")) == wanted),
        docs[0],
    )
    cover_id = book.get("cover_i")
    if not cover_id:
        return None
    authors = book.get("author_name") or []
    return {
        "title": book.get("title") or title,
        "author": ", ".join(authors),
        "cover": "https://covers.openlibrary.org/b/id/{}-L.jpg".format(cover_id),
        "status": "",
        "note": "",
    }


def from_google_books(title):
    data = fetch_json(GOOGLE_BOOKS_URL.format(quote(title)))
    for item in data.get("items", []):
        info = item.get("volumeInfo", {})
        image_links = info.get("imageLinks", {})
        cover = image_links.get("thumbnail") or image_links.get("smallThumbnail")
        if not cover:
            continue
        found_title = info.get("title") or title
        return {
            "title": found_title,
            "author": ", ".join(info.get("authors") or []),
            "cover": cover.replace("http://", "https://"),
            "status": "",
            "note": "",
        }
    return None


def find_book(title):
    errors = []
    candidates = [title]
    alias = TITLE_ALIASES.get(title)
    if alias:
        candidates.append(alias)
    for candidate in candidates:
        for provider in (from_open_library, from_google_books):
            try:
                book = provider(candidate)
                if book:
                    book["title"] = title
                    return book
            except (OSError, ValueError, KeyError) as error:
                errors.append(str(error))
    if errors:
        print(
            "查询来源暂时不可用：{} ({})".format(title, "; ".join(errors)),
            file=sys.stderr,
        )
    return None


def parse_args():
    parser = argparse.ArgumentParser(
        description="Batch-add books by title using Open Library and Google Books."
    )
    parser.add_argument(
        "titles",
        nargs="*",
        help="Book titles; quote titles containing spaces.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Read one book title per line from a UTF-8 text file.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    titles = list(args.titles)
    if args.file:
        titles.extend(
            line.strip()
            for line in args.file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    if not titles:
        print("请输入书名，每行一本；输入空行结束：")
        while True:
            title = input().strip()
            if not title:
                break
            titles.append(title)

    try:
        books = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print("无法读取 {}: {}".format(DATA_FILE, error), file=sys.stderr)
        return 1
    if not isinstance(books, list):
        print("books.json 必须是数组", file=sys.stderr)
        return 1

    existing = {
        normalize(book.get("title"))
        for book in books
        if isinstance(book, dict)
    }
    added = 0
    for title in titles:
        if normalize(title) in existing:
            print("跳过（已存在）：{}".format(title))
            continue
        book = find_book(title)
        if not book:
            print("未找到封面：{}".format(title), file=sys.stderr)
            continue
        book["id"] = slug(book["title"])
        books.append(book)
        existing.add(normalize(book["title"]))
        added += 1
        print("已添加：{} — {}".format(book["title"], book["author"]))

    if added:
        DATA_FILE.write_text(
            json.dumps(books, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print("完成：新增 {} 本，当前共 {} 本。".format(added, len(books)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
