"""Batch-add or remove games, using Steam Store metadata and locally cached artwork."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "static" / "game" / "games.json"
COVERS_DIR = DATA_FILE.parent / "covers"
SEARCH_URL = "https://store.steampowered.com/api/storesearch/?term={}&l=schinese&cc=cn"
DETAILS_URL = "https://store.steampowered.com/api/appdetails/?appids={}&l=schinese&cc=cn"
USER_AGENT = "0-1byte.github.io game importer/1.0"

from cover_opt import run_after_add as _run_after_add


def normalize(value):
    return " ".join(str(value or "").casefold().split())


def slug(title):
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title.casefold()).strip("-")
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:8]
    return "{}-{}".format(value or "game", digest)


def fetch(url, accept="*/*"):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urlopen(request, timeout=30) as response:
        return response.read(), response.headers.get("Content-Type", "")


def json_request(url):
    content, _ = fetch(url, "application/json")
    return json.loads(content.decode("utf-8"))


def find_game(title):
    search = json_request(SEARCH_URL.format(quote(title)))
    wanted = normalize(title)
    result = next(
        (item for item in search.get("items", []) if normalize(item.get("name")) == wanted),
        None,
    )
    if not result:
        return None

    app_id = result.get("id")
    if not app_id:
        raise ValueError("Steam 搜索结果缺少游戏 ID")
    response = json_request(DETAILS_URL.format(app_id))
    detail = response.get(str(app_id), {})
    if not detail.get("success") or not isinstance(detail.get("data"), dict):
        raise ValueError("无法读取 Steam 游戏详情")
    data = detail["data"]
    platforms = data.get("platforms") or {}
    available_platforms = [
        name for key, name in (("windows", "Windows"), ("mac", "macOS"), ("linux", "Linux"))
        if platforms.get(key)
    ]
    release_date = (data.get("release_date") or {}).get("date", "")
    year_match = re.search(r"\b(?:18|19|20)\d{2}\b", release_date)
    return {
        "title": result["name"],
        "appid": app_id,
        "year": int(year_match.group()) if year_match else "",
        "platform": " / ".join(available_platforms) or "Steam",
        "url": "https://store.steampowered.com/app/{}/".format(app_id),
        "cover_url": data.get("header_image", ""),
    }


def image_extension(content, content_type):
    content_type = content_type.split(";", 1)[0].strip().lower()
    extensions = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    if content_type in extensions:
        return extensions[content_type]
    signatures = (
        (b"\xff\xd8\xff", ".jpg"),
        (b"\x89PNG\r\n\x1a\n", ".png"),
        (b"RIFF", ".webp"),
        (b"GIF87a", ".gif"),
        (b"GIF89a", ".gif"),
    )
    for signature, extension in signatures:
        if content.startswith(signature):
            return extension
    raise ValueError("封面响应不是支持的图片格式")


def download_cover(url, title):
    if not url:
        raise ValueError("Steam 没有提供官方封面 URL")
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        host == "steamstatic.com" or host.endswith(".steamstatic.com")
    ):
        raise ValueError("封面地址不是 Steam 官方 CDN：{}".format(host or "(无主机名)"))
    content, content_type = fetch(url, "image/*")
    extension = image_extension(content, content_type)
    if not content:
        raise ValueError("Steam 封面内容为空")
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    path = COVERS_DIR / (slug(title) + extension)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return "covers/{}".format(path.name)


def read_titles(args):
    titles = list(args.titles)
    if args.file:
        try:
            titles.extend(
                line.strip()
                for line in args.file.read_text(encoding="utf-8-sig").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
        except OSError as error:
            raise ValueError("无法读取清单 {}: {}".format(args.file, error)) from error
    if not titles:
        print("请输入游戏名，每行一款；输入空行结束：")
        while True:
            title = input().strip()
            if not title:
                break
            titles.append(title)
    unique = []
    seen = set()
    for title in titles:
        title = title.strip()
        key = normalize(title)
        if key and key not in seen:
            unique.append(title)
            seen.add(key)
    return unique


def load_games():
    try:
        games = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("无法读取 {}: {}".format(DATA_FILE, error)) from error
    if not isinstance(games, list):
        raise ValueError("games.json 顶层必须是数组")
    return games


def write_games(games):
    temporary = DATA_FILE.with_suffix(".json.tmp")
    try:
        temporary.write_text(
            json.dumps(games, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(DATA_FILE)
    finally:
        if temporary.exists():
            temporary.unlink()


def has_value(game, key):
    return key in game and game[key] not in (None, "")


def local_cover_path(cover):
    if not cover or cover.startswith(("http://", "https://")):
        return None
    relative = cover.replace("\\", "/")
    if relative.startswith("covers/"):
        relative = relative[len("covers/"):]
    return COVERS_DIR / relative


def find_existing(games, title):
    wanted = normalize(title)
    for game in games:
        if isinstance(game, dict) and normalize(game.get("title")) == wanted:
            return game
    return None


def find_existing_by_app_id(games, app_id):
    expected = str(app_id)
    for game in games:
        if not isinstance(game, dict):
            continue
        url = game.get("url")
        if not isinstance(url, str):
            continue
        match = re.search(r"/app/(\d+)(?:/|$)", urlsplit(url).path)
        if match and match.group(1) == expected:
            return game
    return None


def verify_optimized_games(games, titles):
    wanted = {normalize(title) for title in titles}
    selected = [
        game for game in games
        if isinstance(game, dict) and normalize(game.get("title")) in wanted
    ]
    errors = []
    found = {normalize(game.get("title")) for game in selected}
    for missing in sorted(wanted - found):
        errors.append("{}：games.json 中找不到该游戏".format(missing))
    for game in selected:
        title = game.get("title") or "(无标题)"
        cover = game.get("cover")
        image_base = game.get("img")
        if not cover or not image_base:
            errors.append("{}：缺少 cover 或 img 字段".format(title))
            continue
        cover_path = local_cover_path(cover)
        if not cover_path or not cover_path.is_file():
            errors.append("{}：本地封面文件不存在 ({})".format(title, cover_path))
            continue
        for width in (240, 320, 480):
            derivative = COVERS_DIR / "opt" / "{}-{}.webp".format(image_base, width)
            if not derivative.is_file() or derivative.stat().st_size == 0:
                errors.append("{}：缺少 {} WebP ({})".format(title, width, derivative))
    return errors


def parse_args():
    parser = argparse.ArgumentParser(
        description="批量添加或删除游戏；添加时从 Steam 匹配名称、平台、年份和封面。"
    )
    parser.add_argument("titles", nargs="*", help="游戏名称，可一次输入多个")
    parser.add_argument("--file", type=Path, help="从文本文件读取游戏名（每行一个）")
    parser.add_argument("--remove", action="store_true", help="删除这些游戏")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        titles = read_titles(args)
        if not titles:
            print("没有提供游戏名称。", file=sys.stderr)
            return 1
        games = load_games()
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1

    if args.remove:
        wanted = {normalize(title) for title in titles}
        remaining = [
            game for game in games
            if not isinstance(game, dict) or normalize(game.get("title")) not in wanted
        ]
        removed = len(games) - len(remaining)
        if removed:
            try:
                write_games(remaining)
            except OSError as error:
                print("无法保存游戏数据：{}".format(error), file=sys.stderr)
                return 1
        print("已删除 {} 款；当前共 {} 款。".format(removed, len(remaining)))
        if removed:
            print("未自动删除封面文件；确认没有其他条目引用后可手动清理。")
        return 0

    changed = False
    optimize_titles = []
    added = 0
    repaired = 0
    failures = []
    for title in titles:
        game = find_existing(games, title)
        if game and has_value(game, "cover") and has_value(game, "img"):
            print("跳过（已有 cover 和 img）：{}".format(title))
            continue
        existing_cover = local_cover_path(game.get("cover")) if game else None
        cover_is_available = existing_cover is not None and existing_cover.is_file()
        if game and cover_is_available:
            optimize_titles.append(game["title"])
            repaired += 1
            print("已找到本地封面，将补生成 img 和 WebP：{}".format(game["title"]))
            continue
        try:
            metadata = find_game(title)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as error:
            reason = "Steam 查询失败：{}".format(error)
            print("{}：{}".format(title, reason), file=sys.stderr)
            failures.append("{}：{}".format(title, reason))
            continue

        if not metadata:
            reason = "Steam 商店没有精确匹配，未新增或修改数据"
            print("{}：{}".format(title, reason), file=sys.stderr)
            failures.append("{}：{}".format(title, reason))
            continue

        if game is None:
            game = find_existing(games, metadata["title"])
            if game is None:
                game = find_existing_by_app_id(games, metadata["appid"])
            if game and has_value(game, "cover") and has_value(game, "img"):
                print("跳过（Steam 对应游戏已有 cover 和 img）：{}".format(metadata["title"]))
                continue
            existing_cover = local_cover_path(game.get("cover")) if game else None
            cover_is_available = existing_cover is not None and existing_cover.is_file()
            if game and cover_is_available and has_value(game, "img"):
                print("跳过（Steam 对应游戏已有 cover 和 img）：{}".format(metadata["title"]))
                continue
            if game and cover_is_available:
                optimize_titles.append(game["title"])
                repaired += 1
                print("已找到本地封面，将补生成 img 和 WebP：{}".format(game["title"]))
                continue

        if not cover_is_available:
            try:
                cover = download_cover(metadata.get("cover_url"), metadata["title"])
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
                reason = "Steam 官方封面下载失败：{}".format(error)
                print("{}：{}".format(title, reason), file=sys.stderr)
                failures.append("{}：{}".format(title, reason))
                continue
        else:
            cover = None

        was_new = game is None
        if was_new:
            game = {"title": metadata["title"], "note": ""}
            games.append(game)
            added += 1

        if cover:
            game["cover"] = cover
            changed = True
        for field in ("year", "platform", "url"):
            if not has_value(game, field) and has_value(metadata, field):
                game[field] = metadata[field]
                changed = True

        if not was_new and (cover or not has_value(game, "img")):
            repaired += 1
        optimize_titles.append(game["title"])
        print(
            "{}：{}".format(
                "已新增" if was_new else "已补全",
                game["title"],
            )
        )

    if changed:
        try:
            write_games(games)
        except OSError as error:
            print("无法保存游戏数据：{}".format(error), file=sys.stderr)
            return 1

    if optimize_titles:
        print("正在优化并验证游戏封面...")
        _run_after_add("game")
        try:
            optimized_games = load_games()
        except ValueError as error:
            print("无法验证封面优化结果：{}".format(error), file=sys.stderr)
            return 1
        optimization_errors = verify_optimized_games(optimized_games, optimize_titles)
        if optimization_errors:
            print("封面优化未完成：", file=sys.stderr)
            for error in optimization_errors:
                print("  - {}".format(error), file=sys.stderr)
            return 1

    if failures:
        print(
            "未全部完成：新增 {} 款、补全 {} 款，失败 {} 项；当前共 {} 款。".format(
                added, repaired, len(failures), len(games)
            ),
            file=sys.stderr,
        )
        return 1
    print(
        "完成：新增 {} 款，补全 {} 款，当前共 {} 款。".format(
            added, repaired, len(games)
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
