"""Batch-add or remove TV series with locally cached covers from public metadata."""

from __future__ import print_function

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen


DATA_FILE = Path(__file__).resolve().parents[1] / "static" / "tv" / "tvs.json"
COVERS_DIR = DATA_FILE.parent / "covers"
DEFAULT_LIST = Path(__file__).resolve().parents[1] / "tv-list.txt"
DOUBAN_SEARCH_URL = "https://search.douban.com/movie/subject_search?search_text={}"
IMDB_SEARCH_URL = "https://v3.sg.media-imdb.com/suggestion/x/{}.json"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36"
)
DOUBAN_IMAGE_HOSTS = [
    "img1.doubanio.com",
    "img2.doubanio.com",
    "img3.doubanio.com",
    "img4.doubanio.com",
    "img5.doubanio.com",
    "img6.doubanio.com",
    "img7.doubanio.com",
    "img8.doubanio.com",
    "img9.doubanio.com",
]
# 已核对的豆瓣条目，优先使用，避免搜索结果张冠李戴。
DOUBAN_URLS = {
    "漫长的季节": "https://movie.douban.com/subject/35588177/",
    "请回答1988": "https://movie.douban.com/subject/26302614/",
    "人生切割术": "https://movie.douban.com/subject/34885342/",
    "暗黑": "https://movie.douban.com/subject/26992330/",
    "黑镜": "https://movie.douban.com/subject/7054120/",
    "爱，死亡和机器人": "https://movie.douban.com/subject/30424374/",
    "后翼弃兵": "https://movie.douban.com/subject/32579283/",
    "去有风的地方": "https://movie.douban.com/subject/35662223/",
    "隐秘的角落": "https://movie.douban.com/subject/33404425/",
    "我们与恶的距离": "https://movie.douban.com/subject/30181230/",
    "我的大叔": "https://movie.douban.com/subject/27602137/",
    # HBO《切尔诺贝利》豆瓣页曾被下架，改用 IMDb
    "切尔诺贝利": "https://www.imdb.com/title/tt7366338/",
}
IMDB_ALIASES = {
    "人生切割术": ["Severance"],
    "漫长的季节": ["The Long Season"],
    "请回答1988": ["Reply 1988"],
    "黑镜": ["Black Mirror"],
    "爱，死亡和机器人": ["Love, Death & Robots", "Love Death and Robots"],
    "后翼弃兵": ["The Queen's Gambit"],
    "切尔诺贝利": ["Chernobyl"],
    "去有风的地方": ["Meet Yourself"],
    "隐秘的角落": ["The Bad Kids"],
    "我们与恶的距离": ["The World Between Us"],
    "暗黑": ["Dark"],
    "我的大叔": ["My Mister"],
}
TV_MARKERS = ("电视剧", "剧集", "tv series", "tv mini", "web系列", "网剧")
IMDB_TV_TYPES = ("tv series", "tv mini-series", "tv mini series")


# --- 封面衍生图钩子 ---
# 加完数据后自动补齐封面下载尺寸的 WebP（增量，通常 1~2 秒）。
# 逻辑见 cover_opt.run_after_add；失败只打警告，不影响加数据本身。
# 同目录导入：以 `python tools/add_xxx.py` 方式运行时脚本目录已在 sys.path 上。
from cover_opt import run_after_add as _run_after_add

def normalize(value):
    return " ".join(str(value or "").casefold().split())


def slug(title):
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title.casefold()).strip("-")
    return value or "show"


def fetch(url, accept="*/*", referer=""):
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    if referer:
        headers["Referer"] = referer
    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        return response.read()


def extract_year(text):
    match = re.search(r"\b((?:18|19|20)\d{2})\b", text or "")
    return int(match.group(1)) if match else ""


def looks_like_tv(item):
    blob = " ".join([
        str(item.get("title") or ""),
        str(item.get("abstract") or ""),
        str(item.get("sub_title") or ""),
    ]).casefold()
    return any(marker in blob for marker in TV_MARKERS)


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
    tv_items = [item for item in items if looks_like_tv(item)]
    pool = tv_items or items
    exact = [
        item for item in pool
        if wanted == normalize(item.get("title"))
        or wanted in normalize(item.get("title"))
        or wanted in normalize(item.get("abstract"))
    ]
    return (exact or pool or [None])[0]


def imdb_result(title):
    queries = [title] + IMDB_ALIASES.get(title, [])
    for query in queries:
        data = json.loads(fetch(
            IMDB_SEARCH_URL.format(quote(query)),
            accept="application/json",
        ).decode("utf-8"))
        items = data.get("d") or []
        wanted = normalize(query)
        tv_items = [
            item for item in items
            if str(item.get("q") or "").casefold() in IMDB_TV_TYPES
        ]
        for pool in (tv_items, items):
            for item in pool:
                image = item.get("i") or {}
                if normalize(item.get("l")) == wanted and image.get("imageUrl"):
                    return item
            for item in pool:
                if (item.get("i") or {}).get("imageUrl"):
                    return item
    return None


def build_cover_candidates(url):
    if not url:
        return []
    try:
        parsed = urlsplit(url)
    except ValueError:
        return [url]
    host = parsed.hostname or ""
    if not host.endswith(".doubanio.com"):
        return [url]
    candidates = []
    for image_host in DOUBAN_IMAGE_HOSTS:
        candidate = urlunsplit((
            "https",
            image_host,
            parsed.path,
            parsed.query,
            parsed.fragment,
        ))
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def download_cover(url, title, referer=""):
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    path = COVERS_DIR / "{}.jpg".format(slug(title))
    candidates = build_cover_candidates(url) or [url]
    errors = []
    for candidate in candidates:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Referer": referer or "https://movie.douban.com/",
        }
        try:
            request = Request(candidate, headers=headers)
            with urlopen(request, timeout=30) as response:
                content = response.read()
                content_type = (response.headers.get("Content-Type") or "").lower()
                if not content:
                    raise OSError("封面内容为空")
                if "text/html" in content_type:
                    raise OSError("返回的是 HTML，而不是图片")
                path.write_bytes(content)
            return "covers/{}".format(path.name)
        except (OSError, HTTPError, URLError) as error:
            errors.append("{} -> {}".format(candidate, error))
    raise OSError("; ".join(errors) or "封面下载失败")


def known_url(title):
    if title in DOUBAN_URLS:
        return DOUBAN_URLS[title]
    for key, value in DOUBAN_URLS.items():
        if normalize(key) == normalize(title):
            return value
    return ""


def find_show(title):
    preferred_url = known_url(title)
    try:
        result = douban_result(title)
    except (OSError, ValueError, KeyError, HTTPError, URLError):
        result = None
    if result:
        cover = result.get("cover_url", "")
        data = {
            "title": title,
            "cover": cover,
            "year": extract_year(
                " ".join([result.get("title", ""), result.get("abstract", "")])
            ),
            "note": "",
            "url": preferred_url or result.get("url", ""),
        }
        try:
            data["cover"] = download_cover(cover, title, result.get("url", ""))
        except OSError:
            pass
        if data.get("cover"):
            return data

    result = imdb_result(title)
    if not result:
        return None
    imdb_id = result.get("id") or ""
    imdb_url = (
        "https://www.imdb.com/title/{}/".format(imdb_id)
        if imdb_id.startswith("tt")
        else ""
    )
    data = {
        "title": title,
        "cover": result["i"]["imageUrl"],
        "year": result.get("y", ""),
        "note": "",
        "url": preferred_url or imdb_url,
    }
    try:
        data["cover"] = download_cover(data["cover"], title, "https://www.imdb.com/")
    except OSError:
        pass
    return data


def parse_args():
    parser = argparse.ArgumentParser(
        description="Batch-add or remove TV series by title and cache their covers locally."
    )
    parser.add_argument("titles", nargs="*", help="TV series titles.")
    parser.add_argument("--file", type=Path, help="Read one title per line.")
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove the given titles from tvs.json instead of adding them.",
    )
    return parser.parse_args()


def load_shows():
    try:
        shows = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print("无法读取 {}: {}".format(DATA_FILE, error), file=sys.stderr)
        return None
    if not isinstance(shows, list):
        print("tvs.json 必须是数组", file=sys.stderr)
        return None
    return shows


def read_titles_from_file(path):
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def remove_shows(shows, titles):
    to_remove = {normalize(title) for title in titles}
    keep = []
    removed = 0
    for show in shows:
        if not isinstance(show, dict):
            keep.append(show)
            continue
        if normalize(show.get("title")) in to_remove:
            removed += 1
            print("已删除：{}".format(show.get("title")))
        else:
            keep.append(show)
    if removed:
        DATA_FILE.write_text(
            json.dumps(keep, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print("完成：删除 {} 部，当前共 {} 部。".format(removed, len(keep)))
    _run_after_add("tv")
    return 0


def add_shows(shows, titles):
    existing = {
        normalize(show.get("title"))
        for show in shows
        if isinstance(show, dict)
    }
    added = 0
    for title in titles:
        if normalize(title) in existing:
            print("跳过（已存在）：{}".format(title))
            continue
        try:
            show = find_show(title)
        except (OSError, ValueError, KeyError) as error:
            print("查询失败：{} ({})".format(title, error), file=sys.stderr)
            continue
        if not show or not show.get("cover"):
            print("未找到封面：{}".format(title), file=sys.stderr)
            continue
        show["id"] = slug(title)
        shows.append(show)
        existing.add(normalize(title))
        added += 1
        print("已添加：{} — {}".format(title, show["year"] or "年份未找到"))

    if added:
        DATA_FILE.write_text(
            json.dumps(shows, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print("完成：新增 {} 部，当前共 {} 部。".format(added, len(shows)))
    _run_after_add("tv")
    return 0


def main():
    args = parse_args()
    titles = list(args.titles)
    if args.file:
        titles.extend(read_titles_from_file(args.file))

    # 无参数时默认读项目根目录的 tv-list.txt
    if not titles and not args.remove:
        if DEFAULT_LIST.exists():
            titles = read_titles_from_file(DEFAULT_LIST)
            print("从 {} 读取 {} 部剧名。".format(DEFAULT_LIST.name, len(titles)))
        else:
            print(
                "未找到 {}，请传入剧名或 --file。".format(DEFAULT_LIST.name),
                file=sys.stderr,
            )
            return 1

    if not titles:
        action = "删除" if args.remove else "添加"
        print("请输入要{}的剧名，每行一部；输入空行结束：".format(action))
        while True:
            title = input().strip()
            if not title:
                break
            titles.append(title)
    if not titles:
        print("没有指定剧名。", file=sys.stderr)
        return 1

    shows = load_shows()
    if shows is None:
        return 1

    if args.remove:
        return remove_shows(shows, titles)
    return add_shows(shows, titles)


if __name__ == "__main__":
    sys.exit(main())
