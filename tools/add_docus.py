"""Batch-add documentaries from Douban's public movie search metadata."""

from __future__ import print_function

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


DATA_FILE = Path(__file__).resolve().parents[1] / "static" / "docu" / "docus.json"
COVERS_DIR = DATA_FILE.parent / "covers"
SEARCH_URL = "https://search.douban.com/movie/subject_search?search_text={}"
IMDB_SEARCH_URL = "https://v3.sg.media-imdb.com/suggestion/x/{}.json"
USER_AGENT = "0-1byte.github.io documentary importer/2.0"


def normalize(value):
    return " ".join(str(value or "").casefold().split())


def slug(title):
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title.casefold()).strip("-")
    return value or "documentary"


def download_cover(url, name):
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    path = COVERS_DIR / "{}.jpg".format(slug(name))
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": "https://movie.douban.com/",
        },
    )
    with urlopen(request, timeout=30) as response:
        content = response.read()
    if not content:
        raise OSError("封面内容为空")
    path.write_bytes(content)
    return "covers/{}".format(path.name)


def find_imdb_cover(title):
    request = Request(
        IMDB_SEARCH_URL.format(quote(title)),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    wanted = normalize(title)
    for item in data.get("d", []):
        image = item.get("i", {})
        if normalize(item.get("l")) == wanted and image.get("imageUrl"):
            return image["imageUrl"]
    return ""


def fetch_search_page(title):
    request = Request(
        SEARCH_URL.format(quote(title)),
        headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"},
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def find_result(title):
    source = fetch_search_page(title)
    match = re.search(r"window\.__DATA__\s*=\s*(\{.*?\});", source, re.S)
    if not match:
        return None
    data = json.loads(match.group(1))
    wanted = normalize(title)
    candidates = [
        item for item in data.get("items", [])
        if "纪录片" in normalize(item.get("abstract"))
    ]
    if not candidates:
        return None
    matches = [
        item for item in candidates
        if wanted in normalize(item.get("title"))
        or wanted in normalize(item.get("abstract"))
    ]
    return matches[0] if matches else None


def extract_year(text):
    match = re.search(r"\b((?:18|19|20)\d{2})\b", text or "")
    return int(match.group(1)) if match else ""


def find_docu(title):
    result = find_result(title)
    if not result or not result.get("cover_url"):
        return None
    abstract = result.get("abstract", "")
    data = {
        "title": title,
        "cover": result["cover_url"],
        "year": extract_year(result.get("title", "") + " " + abstract),
        "note": "",
        "url": result.get("url", ""),
    }
    try:
        data["cover"] = download_cover(data["cover"], title)
    except OSError as error:
        try:
            alternative = find_imdb_cover(title)
            data["cover"] = download_cover(alternative, title) if alternative else data["cover"]
        except (OSError, ValueError, KeyError):
            pass
        if data["cover"] == result["cover_url"]:
            print("封面下载失败，将由页面尝试备用来源：{} ({})".format(title, error), file=sys.stderr)
    return data


def parse_args():
    parser = argparse.ArgumentParser(
        description="Batch-add documentaries from Douban movie search."
    )
    parser.add_argument(
        "titles",
        nargs="*",
        help="Documentary titles; quote titles containing spaces.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Read one documentary title per line from a UTF-8 file.",
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
        print("请输入纪录片名，每行一部；输入空行结束：")
        while True:
            title = input().strip()
            if not title:
                break
            titles.append(title)

    try:
        docus = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print("无法读取 {}: {}".format(DATA_FILE, error), file=sys.stderr)
        return 1
    if not isinstance(docus, list):
        print("docus.json 必须是数组", file=sys.stderr)
        return 1

    existing = {
        normalize(docu.get("title"))
        for docu in docus
        if isinstance(docu, dict)
    }
    added = 0
    for title in titles:
        if normalize(title) in existing:
            print("跳过（已存在）：{}".format(title))
            continue
        try:
            docu = find_docu(title)
        except (OSError, ValueError, KeyError) as error:
            print("查询失败：{} ({})".format(title, error), file=sys.stderr)
            continue
        if not docu:
            print("未找到带封面的纪录片：{}".format(title), file=sys.stderr)
            continue
        docu["id"] = slug(docu["title"])
        docus.append(docu)
        existing.add(normalize(docu["title"]))
        added += 1
        print("已添加：{} — {}".format(
            docu["title"],
            docu["year"] or "年份未找到",
        ))

    if added:
        DATA_FILE.write_text(
            json.dumps(docus, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print("完成：新增 {} 部，当前共 {} 部。".format(added, len(docus)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
