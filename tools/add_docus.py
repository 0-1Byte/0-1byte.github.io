"""Batch-add documentaries from Douban public movie search metadata."""

from __future__ import print_function

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


DATA_FILE = Path(__file__).resolve().parents[1] / "static" / "docu" / "docus.json"
COVERS_DIR = DATA_FILE.parent / "covers"

SEARCH_URL = (
    "https://search.douban.com/movie/subject_search?search_text={}"
)

IMDB_SEARCH_URL = (
    "https://v3.sg.media-imdb.com/suggestion/x/{}.json"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36"
)

# 豆瓣图片 CDN 有多个域名。
# 某一个域名被限制时，换另一个继续尝试。
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

# 某些中文纪录片在 IMDb 上没有中文标题，补充常见英文名。
IMDB_ALIASES = {
    "罗斯托夫的14秒": [
        "14 Seconds of Rostov",
        "14 Seconds in Rostov",
        "Rostov 14 Seconds",
    ],
}


def normalize(value):
    return " ".join(str(value or "").casefold().split())


def slug(title):
    value = re.sub(
        r"[^\w\u4e00-\u9fff]+",
        "-",
        title.casefold()
    ).strip("-")

    if value:
        return value

    # 极端情况下，给一个稳定的 ASCII 文件名
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:10]
    return "documentary-{}".format(digest)


def is_douban_image(url):
    try:
        host = urlsplit(url).hostname or ""
        return host.endswith(".doubanio.com")
    except Exception:
        return False


def build_cover_candidates(url):
    """
    给一个豆瓣图片 URL，生成多个 CDN 域名候选。
    """
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
        candidate = urlunsplit(
            (
                "https",
                image_host,
                parsed.path,
                parsed.query,
                parsed.fragment,
            )
        )

        if candidate not in candidates:
            candidates.append(candidate)

    return candidates


def download_cover(url, name, referer=None):
    """
    下载封面到 static/docu/covers。
    对豆瓣图片自动轮询 img1～img9。
    成功后返回站点内部路径，例如：

        covers/罗斯托夫的14秒.jpg
    """
    if not url:
        raise OSError("封面 URL 为空")

    COVERS_DIR.mkdir(parents=True, exist_ok=True)

    path = COVERS_DIR / "{}.jpg".format(slug(name))

    candidates = build_cover_candidates(url)

    # 非豆瓣图片直接使用原地址
    if not candidates:
        candidates = [url]

    errors = []

    for candidate in candidates:
        request_headers = {
            "User-Agent": USER_AGENT,
            "Accept": (
                "image/avif,image/webp,image/apng,"
                "image/svg+xml,image/*,*/*;q=0.8"
            ),
        }

        # 对豆瓣图片使用实际电影页面作为 Referer
        if referer:
            request_headers["Referer"] = referer
        else:
            request_headers["Referer"] = "https://movie.douban.com/"

        request = Request(
            candidate,
            headers=request_headers,
        )

        try:
            with urlopen(request, timeout=30) as response:
                content = response.read()

                if not content:
                    raise OSError("封面内容为空")

                # 防止拿到 HTML 错误页却被保存成 jpg
                content_type = (
                    response.headers.get("Content-Type", "")
                    .lower()
                )

                if "text/html" in content_type:
                    raise OSError(
                        "返回的是 HTML，而不是图片"
                    )

                path.write_bytes(content)

            print(
                "✓ 封面已保存：{} ← {}".format(
                    path.name,
                    candidate,
                )
            )

            return "covers/{}".format(path.name)

        except (
            OSError,
            HTTPError,
            URLError,
        ) as error:
            errors.append(
                "{} -> {}".format(candidate, error)
            )

    raise OSError(
        "所有封面来源均下载失败：\n" + "\n".join(errors)
    )


def find_imdb_cover(titles):
    """
    对多个标题尝试 IMDb suggestion API。
    例如：
        ["罗斯托夫的14秒", "14 Seconds of Rostov"]
    """
    if isinstance(titles, str):
        titles = [titles]

    wanted = {
        normalize(title)
        for title in titles
        if title
    }

    for query_title in titles:
        if not query_title:
            continue

        request = Request(
            IMDB_SEARCH_URL.format(
                quote(query_title)
            ),
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
        )

        try:
            with urlopen(request, timeout=20) as response:
                data = json.loads(
                    response.read().decode("utf-8")
                )
        except (
            OSError,
            ValueError,
            KeyError,
        ):
            continue

        for item in data.get("d", []):
            image = item.get("i", {})

            imdb_title = normalize(item.get("l"))

            if (
                imdb_title in wanted
                and image.get("imageUrl")
            ):
                return image["imageUrl"]

    return ""


def fetch_search_page(title):
    request = Request(
        SEARCH_URL.format(
            quote(title)
        ),
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )

    with urlopen(request, timeout=30) as response:
        return response.read().decode(
            "utf-8",
            errors="replace",
        )


def find_result(title):
    source = fetch_search_page(title)

    match = re.search(
        r"window\.__DATA__\s*=\s*(\{.*?\});",
        source,
        re.S,
    )

    if not match:
        return None

    data = json.loads(match.group(1))

    wanted = normalize(title)

    candidates = [
        item
        for item in data.get("items", [])
        if "纪录片" in normalize(
            item.get("abstract")
        )
    ]

    if not candidates:
        return None

    matches = [
        item
        for item in candidates
        if (
            wanted in normalize(item.get("title"))
            or wanted in normalize(item.get("abstract"))
        )
    ]

    return matches[0] if matches else None


def extract_year(text):
    match = re.search(
        r"\b((?:18|19|20)\d{2})\b",
        text or "",
    )

    return (
        int(match.group(1))
        if match
        else ""
    )


def find_docu(title):
    result = find_result(title)

    if not result:
        return None

    if not result.get("cover_url"):
        return None

    abstract = result.get("abstract", "")

    data = {
        "title": title,
        "cover": result["cover_url"],
        "year": extract_year(
            result.get("title", "") + " " + abstract
        ),
        "note": "",
        "url": result.get("url", ""),
    }

    # 第一优先：直接下载豆瓣封面
    try:
        data["cover"] = download_cover(
            data["cover"],
            title,
            referer=data["url"],
        )

        return data

    except OSError as error:
        print(
            "豆瓣封面下载失败：{} ({})".format(
                title,
                error,
            ),
            file=sys.stderr,
        )

    # 第二优先：IMDb
    imdb_titles = [title]

    imdb_titles.extend(
        IMDB_ALIASES.get(
            normalize(title),
            IMDB_ALIASES.get(title, []),
        )
    )

    try:
        alternative = find_imdb_cover(imdb_titles)

        if alternative:
            data["cover"] = download_cover(
                alternative,
                title,
                referer=data["url"],
            )

            return data

    except (
        OSError,
        ValueError,
        KeyError,
    ) as error:
        print(
            "IMDb 备用封面也失败：{} ({})".format(
                title,
                error,
            ),
            file=sys.stderr,
        )

    return None


def cover_exists(cover):
    """
    判断 JSON 中的 cover 是否对应一个存在的本地文件。
    """
    if not cover or not isinstance(cover, str):
        return False

    if cover.startswith("http://") or cover.startswith(
        "https://"
    ):
        return False

    path = DATA_FILE.parent / cover

    return path.exists()


def repair_existing_docu(docu):
    """
    如果已有纪录片的 cover 是远程 URL，
    自动把它转成本地封面。
    """
    if not isinstance(docu, dict):
        return False

    title = docu.get("title", "")
    cover = docu.get("cover", "")

    if not title or not cover:
        return False

    # 已经是本地封面，并且文件存在
    if cover_exists(cover):
        return False

    # 本来就是本地路径，但文件丢失
    if not cover.startswith(
        ("http://", "https://")
    ):
        return False

    old_cover = cover

    try:
        docu["cover"] = download_cover(
            old_cover,
            title,
            referer=docu.get("url", ""),
        )

        print(
            "已修复封面：{} → {}".format(
                title,
                docu["cover"],
            )
        )

        return True

    except OSError as error:
        print(
            "修复封面失败：{} ({})".format(
                title,
                error,
            ),
            file=sys.stderr,
        )

    return False


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Batch-add documentaries "
            "from Douban movie search."
        )
    )

    parser.add_argument(
        "titles",
        nargs="*",
        help=(
            "Documentary titles; "
            "quote titles containing spaces."
        ),
    )

    parser.add_argument(
        "--file",
        type=Path,
        help=(
            "Read one documentary title "
            "per line from a UTF-8 file."
        ),
    )

    return parser.parse_args()


def main():
    args = parse_args()

    titles = list(args.titles)

    if args.file:
        titles.extend(
            line.strip()
            for line in args.file.read_text(
                encoding="utf-8"
            ).splitlines()
            if (
                line.strip()
                and not line.lstrip().startswith("#")
            )
        )

    if not titles:
        print(
            "请输入纪录片名，每行一部；"
            "输入空行结束："
        )

        while True:
            title = input().strip()

            if not title:
                break

            titles.append(title)

    try:
        docus = json.loads(
            DATA_FILE.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        ValueError,
    ) as error:
        print(
            "无法读取 {}: {}".format(
                DATA_FILE,
                error,
            ),
            file=sys.stderr,
        )

        return 1

    if not isinstance(docus, list):
        print(
            "docus.json 必须是数组",
            file=sys.stderr,
        )

        return 1

    existing = {
        normalize(docu.get("title"))
        for docu in docus
        if isinstance(docu, dict)
    }

    changed = False
    added = 0

    # --------------------------------------------------
    # 第一阶段：
    # 自动修复已有纪录片的远程封面
    # --------------------------------------------------
    for docu in docus:
        if repair_existing_docu(docu):
            changed = True

    # --------------------------------------------------
    # 第二阶段：
    # 添加新的纪录片
    # --------------------------------------------------
    for title in titles:
        normalized_title = normalize(title)

        if normalized_title in existing:
            print(
                "跳过（已存在）：{}".format(title)
            )
            continue

        try:
            docu = find_docu(title)

        except (
            OSError,
            ValueError,
            KeyError,
        ) as error:
            print(
                "查询失败：{} ({})".format(
                    title,
                    error,
                ),
                file=sys.stderr,
            )
            continue

        if not docu:
            print(
                "未找到带本地封面的纪录片：{}".format(
                    title
                ),
                file=sys.stderr,
            )
            continue

        docu["id"] = slug(docu["title"])

        docus.append(docu)

        existing.add(
            normalize(docu["title"])
        )

        added += 1
        changed = True

        print(
            "已添加：{} — {}".format(
                docu["title"],
                docu["year"] or "年份未找到",
            )
        )

    if changed:
        DATA_FILE.write_text(
            json.dumps(
                docus,
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

    print(
        "完成：新增 {} 部，当前共 {} 部。".format(
            added,
            len(docus),
        )
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())