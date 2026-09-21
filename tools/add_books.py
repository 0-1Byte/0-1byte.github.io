"""Batch-add books with covers from Douban book search."""

from __future__ import print_function

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


DATA_FILE = Path(__file__).resolve().parents[1] / "static" / "book" / "books.json"
PUBLIC_DATA_FILE = Path(__file__).resolve().parents[1] / "public" / "book" / "books.json"
COVERS_DIR = DATA_FILE.parent / "covers"
OPEN_LIBRARY_URL = "https://openlibrary.org/search.json?title={}&limit=10"
GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes?q=intitle:{}&maxResults=10"
DOUBAN_SEARCH_URL = "https://search.douban.com/book/subject_search?search_text={}"
USER_AGENT = "0-1byte.github.io book importer/2.0"
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


def clean_title(value):
    return str(value or "").replace("\ufeff", "").replace("\u200b", "").strip()


def normalize(value):
    return " ".join(clean_title(value).casefold().split())


def slug(title):
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title.casefold()).strip("-")
    return value or "book"


def cache_cover(url, title):
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    path = COVERS_DIR / "{}.jpg".format(slug(title))
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": "https://book.douban.com/",
        },
    )
    with urlopen(request, timeout=30) as response:
        content = response.read()
    if not content:
        raise OSError("封面内容为空")
    path.write_bytes(content)
    return "covers/{}".format(path.name)


def from_douban(title):
    request = Request(
        DOUBAN_SEARCH_URL.format(quote(title)),
        headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"},
    )
    with urlopen(request, timeout=30) as response:
        source = response.read().decode("utf-8", errors="replace")
    match = re.search(r"window\.__DATA__\s*=\s*(\{.*?\});", source, re.S)
    if not match:
        return None
    data = json.loads(match.group(1))
    wanted = normalize(title)
    candidates = [
        item for item in data.get("items", [])
        if item.get("cover_url")
        and "book-default" not in item.get("cover_url", "")
    ]
    if not candidates:
        return None
    book = next(
        (
            item for item in candidates
            if wanted == normalize(item.get("title"))
            or wanted in normalize(item.get("title"))
        ),
        candidates[0],
    )
    abstract = book.get("abstract", "")
    author = abstract.split(" / ")[0] if abstract else ""
    return {
        "title": title,
        "author": author,
        "cover": book["cover_url"],
        "status": "",
        "note": "",
        "url": book.get("url", ""),
    }


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
        try:
            book = from_douban(candidate)
            if book:
                try:
                    book["cover"] = cache_cover(book["cover"], title)
                except OSError as error:
                    print(
                        "豆瓣封面无法缓存，将保留远程地址：{} ({})".format(title, error),
                        file=sys.stderr,
                    )
                return book
        except (OSError, ValueError, KeyError) as error:
            errors.append(str(error))
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
        description="Batch-add books by title using Douban book search."
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
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh existing books from Douban instead of skipping them.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    titles = list(args.titles)
    if args.file:
        titles.extend(
            clean_title(line)
            for line in args.file.read_text(encoding="utf-8").splitlines()
            if clean_title(line) and not clean_title(line).lstrip().startswith("#")
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
        title = clean_title(title)
        normalized_title = normalize(title)
        existing_index = next(
            (
                index for index, item in enumerate(books)
                if normalize(item.get("title")) == normalized_title
            ),
            None,
        )
        if existing_index is not None and not args.refresh:
            print("跳过（已存在）：{}".format(title))
            continue
        book = find_book(title)
        if not book:
            print("未找到封面：{}".format(title), file=sys.stderr)
            continue
        book["id"] = slug(book["title"])
        if existing_index is None:
            books.append(book)
            added += 1
            print("已添加：{} — {}".format(book["title"], book["author"]))
        else:
            books[existing_index] = dict(books[existing_index], **book)
            print("已刷新：{} — {}".format(book["title"], book["author"]))
        existing.add(normalized_title)

    if added or args.refresh:
        DATA_FILE.write_text(
            json.dumps(books, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if PUBLIC_DATA_FILE.parent.exists():
        PUBLIC_DATA_FILE.write_text(
            json.dumps(books, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print("完成：新增 {} 本，当前共 {} 本。".format(added, len(books)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
