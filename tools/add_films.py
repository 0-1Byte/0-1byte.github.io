"""Batch-add films with locally cached covers from public movie metadata."""

from __future__ import print_function

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


DATA_FILE = Path(__file__).resolve().parents[1] / "static" / "film" / "films.json"
COVERS_DIR = DATA_FILE.parent / "covers"
DOUBAN_SEARCH_URL = "https://search.douban.com/movie/subject_search?search_text={}"
IMDB_SEARCH_URL = "https://v3.sg.media-imdb.com/suggestion/x/{}.json"
USER_AGENT = "0-1byte.github.io film importer/1.0"


def normalize(value):
    return " ".join(str(value or "").casefold().split())


def slug(title):
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title.casefold()).strip("-")
    return value or "film"


def fetch(url, accept="*/*", referer=""):
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    if referer:
        headers["Referer"] = referer
    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        return response.read()


def download_cover(url, title):
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    path = COVERS_DIR / "{}.jpg".format(slug(title))
    content = fetch(url, referer="https://movie.douban.com/")
    if not content:
        raise OSError("封面内容为空")
    path.write_bytes(content)
    return "covers/{}".format(path.name)


def extract_year(text):
    match = re.search(r"\b((?:18|19|20)\d{2})\b", text or "")
    return int(match.group(1)) if match else ""


def douban_result(title):
    source = fetch(
        DOUBAN_SEARCH_URL.format(quote(title)),
        accept="text/html",
    ).decode("utf-8", errors="replace")
    match = re.search(r"window\.__DATA__\s*=\s*(\{.*?\});", source, re.S)
    if not match:
        return None
    data = json.loads(match.group(1))
    wanted = normalize(title)
    items = [item for item in data.get("items", []) if item.get("cover_url")]
    exact = [
        item for item in items
        if wanted == normalize(item.get("title"))
        or wanted in normalize(item.get("title"))
        or wanted in normalize(item.get("abstract"))
    ]
    return (exact or items or [None])[0]


def imdb_result(title):
    data = json.loads(fetch(
        IMDB_SEARCH_URL.format(quote(title)),
        accept="application/json",
    ).decode("utf-8"))
    wanted = normalize(title)
    for item in data.get("d", []):
        image = item.get("i", {})
        if normalize(item.get("l")) == wanted and image.get("imageUrl"):
            return item
    for item in data.get("d", []):
        if item.get("i", {}).get("imageUrl"):
            return item
    return None


def find_film(title):
    try:
        result = douban_result(title)
    except (OSError, ValueError, KeyError):
        result = None
    if result:
        cover = result.get("cover_url", "")
        data = {
            "title": title,
            "cover": cover,
            "year": extract_year(result.get("title", "") + " " + result.get("abstract", "")),
            "note": "",
            "url": result.get("url", ""),
        }
        try:
            data["cover"] = download_cover(cover, title)
        except OSError:
            pass
        return data

    result = imdb_result(title)
    if not result:
        return None
    data = {
        "title": title,
        "cover": result["i"]["imageUrl"],
        "year": result.get("y", ""),
        "note": "",
        "url": "",
    }
    try:
        data["cover"] = download_cover(data["cover"], title)
    except OSError:
        pass
    return data


def parse_args():
    parser = argparse.ArgumentParser(
        description="Batch-add films by title and cache their covers locally."
    )
    parser.add_argument("titles", nargs="*", help="Film titles.")
    parser.add_argument("--file", type=Path, help="Read one film title per line.")
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
        print("请输入电影名，每行一部；输入空行结束：")
        while True:
            title = input().strip()
            if not title:
                break
            titles.append(title)

    try:
        films = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print("无法读取 {}: {}".format(DATA_FILE, error), file=sys.stderr)
        return 1
    if not isinstance(films, list):
        print("films.json 必须是数组", file=sys.stderr)
        return 1

    existing = {normalize(film.get("title")) for film in films if isinstance(film, dict)}
    added = 0
    for title in titles:
        if normalize(title) in existing:
            print("跳过（已存在）：{}".format(title))
            continue
        try:
            film = find_film(title)
        except (OSError, ValueError, KeyError) as error:
            print("查询失败：{} ({})".format(title, error), file=sys.stderr)
            continue
        if not film or not film.get("cover"):
            print("未找到封面：{}".format(title), file=sys.stderr)
            continue
        film["id"] = slug(title)
        films.append(film)
        existing.add(normalize(title))
        added += 1
        print("已添加：{} — {}".format(title, film["year"] or "年份未找到"))

    if added:
        DATA_FILE.write_text(
            json.dumps(films, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print("完成：新增 {} 部，当前共 {} 部。".format(added, len(films)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
