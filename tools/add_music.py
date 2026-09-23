"""Batch-add songs from a UTF-8 text file using the iTunes Search API."""

from __future__ import print_function

import argparse
import http.client
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "static" / "music" / "songs.json"
COVERS_DIR = DATA_FILE.parent / "assets"
SEARCH_URL = "https://itunes.apple.com/search?term={}&entity=song&limit=50"
MUSICBRAINZ_SEARCH_URL = (
    "https://musicbrainz.org/ws/2/recording/?query=recording:%22{}%22"
    "%20AND%20artist:%22{}%22&fmt=json&limit=5"
)
MUSICBRAINZ_LOOKUP_URL = (
    "https://musicbrainz.org/ws/2/recording/{}"
    "?inc=artist-rels+work-rels&fmt=json"
)
MUSICBRAINZ_WORK_URL = (
    "https://musicbrainz.org/ws/2/work/{}"
    "?inc=artist-rels&fmt=json"
)
MUSICBRAINZ_WORK_SEARCH_URL = (
    "https://musicbrainz.org/ws/2/work/?query=work:%22{}%22"
    "%20AND%20artist:%22{}%22&fmt=json&limit=5"
)
USER_AGENT = "0-1byte.github.io music importer/1.0"
ARTIST_ALIASES = {
    "khalilfong": {"khalil fong", "方大同"},
    "jaychou": {"jay chou", "周杰伦"},
    "simpleplan": {"simple plan"},
    "celinedion": {"celine dion", "céline dion"},
}
KNOWN_CREDITS = {
    ("celinedion", "to love you more"): (
        "David Foster, Junior Miles",
        "David Foster, Junior Miles",
    ),
    ("khalilfong", "love song"): (
        "方大同",
        "方大同",
    ),
    ("khalilfong", "手拖手"): (
        "方大同",
        "方大同",
    ),
    ("khalilfong", "take me"): (
        "方大同",
        "方大同",
    ),
    ("khalilfong", "好不容易"): (
        "方大同",
        "方大同",
    ),
    ("khalilfong", "romeo"): (
        "方大同",
        "方大同",
    ),
    ("khalilfong", "bb88"): (
        "方大同",
        "方大同",
    ),
    ("khalilfong", "悟空"): (
        "方大同",
        "方大同",
    ),
    ("khalilfong", "gf"): (
        "方大同",
        "方大同",
    ),
    ("khalilfong", "tango"): (
        "方大同",
        "方大同",
    ),
    ("simpleplan", "astronaut"): (
        "Pierre Bouvier, Chuck Comeau, David Desrosiers, Sébastien Lefebvre, Jeff Stinco",
        "Pierre Bouvier, Chuck Comeau, David Desrosiers, Sébastien Lefebvre, Jeff Stinco",
    ),
    ("hermanosgutierrez", "esperanza"): (
        "",
        "Daniel Alejandro Hotz, Stephan Ricardo Hotz",
    ),
    ("linkinpark", "numb"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("linkinpark", "in the end"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("linkinpark", "what i've done"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("linkinpark", "crawling"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("linkinpark", "one step closer"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("linkinpark", "breaking the habit"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("linkinpark", "faint"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("linkinpark", "shadow of the day"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("linkinpark", "leave out all the rest"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("linkinpark", "new divide"): (
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
        "Chester Bennington, Mike Shinoda, Brad Delson, Dave Farrell, Joe Hahn, Rob Bourdon",
    ),
    ("jaychou", "断了的弦"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "完美主义"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "反方向的钟"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "开不了口"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "安静"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "半岛铁盒"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "暗号"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "分裂"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "最后的战役"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "以父之名"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "晴天"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "三年二班"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "东风破"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "你听得到"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "她的睫毛"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "梯田"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "七里香"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "借口"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "外婆"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "搁浅"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "园游会"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "止战之殇"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "夜曲"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "发如雪"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "黑色毛衣"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "枫"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "浪漫手机"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "珊瑚海"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "漂移"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "一路向北"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "夜的第七章"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "听妈妈的话"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "退后"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "菊花台"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "牛仔很忙"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "彩虹"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "我不配"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "最长的电影"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "给我一首歌的时间"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "花海"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "说好的幸福呢"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "兰亭序"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "流浪诗人"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "时光机"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "稻香"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "说了再见"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "烟花易冷"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "我落泪情绪零碎"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "红尘客栈"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "哪里都是你"): (
        "方文山",
        "周杰伦",
    ),
    ("jaychou", "美人鱼"): (
        "方文山",
        "周杰伦",
    ),
    ("linjiaqian", "某种老朋友"): (
        "林家谦",
        "林家谦",
    ),
    ("adele", "chasing pavements"): (
        "Adele",
        "Adele, Eg White",
    ),
    ("adele", "rolling in the deep"): (
        "Adele, Paul Epworth",
        "Adele, Paul Epworth",
    ),
    ("adele", "don't you remember"): (
        "Adele, Dan Wilson",
        "Adele, Dan Wilson",
    ),
    ("adele", "take it all"): (
        "Adele, Francis White",
        "Adele, Francis White",
    ),
    ("adele", "one and only"): (
        "Adele, Greg Wells, Dan Wilson",
        "Adele, Greg Wells, Dan Wilson",
    ),
    ("adele", "river lea"): (
        "Adele, Brian Burton",
        "Adele, Brian Burton",
    ),
    ("adele", "love in the dark"): (
        "Adele, Samuel Dixon",
        "Adele, Samuel Dixon",
    ),
    ("adele", "million years ago"): (
        "Adele, Greg Kurstin",
        "Adele, Greg Kurstin",
    ),
    ("adele", "all i ask"): (
        "Adele, Brody Brown, Philip Lawrence, Bruno Mars",
        "Adele, Brody Brown, Philip Lawrence, Bruno Mars",
    ),
    ("adele", "easy on me"): (
        "Adele, Greg Kurstin",
        "Adele, Greg Kurstin",
    ),
    ("adele", "i drink wine"): (
        "Adele, Greg Kurstin",
        "Adele, Greg Kurstin",
    ),
}


def clean_title(value):
    return str(value or "").replace("\ufeff", "").replace("\u200b", "").strip()


def normalize(value):
    return " ".join(clean_title(value).casefold().split())


def normalize_artist(value):
    value = unicodedata.normalize("NFKD", normalize(value))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE)


def artist_matches(actual, expected):
    expected_normalized = normalize_artist(expected)
    names = ARTIST_ALIASES.get(expected_normalized, {expected_normalized})
    actual_normalized = normalize_artist(actual)
    return any(
        normalize_artist(name) == actual_normalized
        or normalize_artist(name) in actual_normalized
        for name in names
    )


def parse_song_reference(value):
    value = clean_title(value)
    if "|" in value:
        artist, title = value.split("|", 1)
        return clean_title(title), clean_title(artist)
    if " - " in value:
        artist, title = value.split(" - ", 1)
        return clean_title(title), clean_title(artist)
    return value, ""


def slug(title, artist):
    value = re.sub(
        r"[^\w\u4e00-\u9fff]+",
        "-",
        "{}-{}".format(artist, title).casefold(),
    ).strip("-")
    return value or "song"


def fetch_json(url):
    last_error = None
    for attempt in range(3):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "User-Agent": USER_AGENT + " (contact: site-maintainer)",
                },
            )
            with urlopen(request, timeout=30) as response:
                content = response.read()
            return json.loads(content.decode("utf-8"))
        except (OSError, http.client.HTTPException, ValueError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(1)
    raise OSError("接口响应不完整或无效：{}".format(last_error))


def collect_credit_names(relationships, credit_type):
    names = []
    for relation in relationships:
        if relation.get("type") != credit_type:
            continue
        artist = relation.get("artist") or relation.get("target", {})
        name = artist.get("name") if isinstance(artist, dict) else ""
        if name and name not in names:
            names.append(name)
    return names


def collect_work_credits(relationships):
    writers = collect_credit_names(relationships, "writer")
    composers = collect_credit_names(relationships, "composer")
    lyricists = collect_credit_names(relationships, "lyricist")
    if writers:
        if not composers:
            composers = writers
        if not lyricists:
            lyricists = writers
    return lyricists, composers


def find_credits(title, artist):
    if not artist:
        return "", ""
    known = KNOWN_CREDITS.get((normalize_artist(artist), normalize(title)))
    if known:
        return known
    time.sleep(1)
    search_url = MUSICBRAINZ_SEARCH_URL.format(quote(title), quote(artist))
    data = fetch_json(search_url)
    recordings = data.get("recordings", [])
    wanted_title = normalize(title)
    wanted_artist = normalize_artist(artist)
    candidates = [
        item for item in recordings
        if (
            normalize(item.get("title")) == wanted_title
            or wanted_title in normalize(item.get("title"))
        )
        and any(
            wanted_artist == normalize_artist(credit.get("name", ""))
            or wanted_artist in normalize_artist(credit.get("name", ""))
            for credit in item.get("artist-credit", [])
            if isinstance(credit, dict)
        )
    ]
    for recording in candidates or recordings:
        recording_id = recording.get("id")
        if not recording_id:
            continue
        details = fetch_json(MUSICBRAINZ_LOOKUP_URL.format(recording_id))
        lyricists, composers = collect_work_credits(details.get("relations", []))
        work_ids = [
            relation.get("work", {}).get("id")
            for relation in details.get("relations", [])
            if relation.get("work", {}).get("id")
        ]
        for work_id in work_ids:
            time.sleep(1)
            work = fetch_json(MUSICBRAINZ_WORK_URL.format(work_id))
            work_lyricists, work_composers = collect_work_credits(
                work.get("relations", [])
            )
            lyricists = work_lyricists or lyricists
            composers = work_composers or composers
        if lyricists or composers:
            return ", ".join(lyricists), ", ".join(composers)
    work_data = fetch_json(
        MUSICBRAINZ_WORK_SEARCH_URL.format(quote(title), quote(artist))
    )
    for work in work_data.get("works", []):
        work_id = work.get("id")
        if not work_id:
            continue
        time.sleep(1)
        details = fetch_json(MUSICBRAINZ_WORK_URL.format(work_id))
        lyricists, composers = collect_work_credits(
            details.get("relations", [])
        )
        if lyricists or composers:
            return ", ".join(lyricists), ", ".join(composers)
    return "", ""


def enrich_missing_credits(songs):
    changed = False
    for song in songs:
        if not isinstance(song, dict) or (
            song.get("lyricist") and song.get("composer")
        ):
            continue
        try:
            lyricist, composer = find_credits(
                song.get("title", ""),
                song.get("artist", ""),
            )
        except (OSError, ValueError, KeyError) as error:
            print(
                "词曲信息查询失败，将保留现有数据：{} ({})".format(
                    song.get("title", ""), error
                ),
                file=sys.stderr,
            )
            continue
        if lyricist and not song.get("lyricist"):
            song["lyricist"] = lyricist
            changed = True
        if composer and not song.get("composer"):
            song["composer"] = composer
            changed = True
        if lyricist or composer:
            print(
                "已补充词曲：{} — 词：{}；曲：{}".format(
                    song.get("title", ""),
                    lyricist or "未找到",
                    composer or "未找到",
                )
            )
    return changed


def cache_cover(url, title, artist):
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    path = COVERS_DIR / "{}.jpg".format(slug(title, artist))
    last_error = None
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=30) as response:
                content = response.read()
            if not content:
                raise OSError("封面内容为空")
            path.write_bytes(content)
            return "/music/assets/{}".format(quote(path.name))
        except (OSError, http.client.HTTPException) as error:
            last_error = error
            if attempt < 2:
                time.sleep(1)
    raise OSError("封面下载失败：{}".format(last_error))


def find_song(title, artist_hint=""):
    query = "{} {}".format(artist_hint, title).strip()
    data = fetch_json(SEARCH_URL.format(quote(query)))
    wanted = normalize(title)
    songs = [
        item for item in data.get("results", [])
        if item.get("trackName") and item.get("artworkUrl100")
    ]
    if not songs:
        return None
    exact_title = [
        item for item in songs
        if (
            normalize(item.get("trackName")) == wanted
            or wanted in normalize(item.get("trackName"))
        )
    ]
    if artist_hint:
        wanted_artist = normalize(artist_hint)
        exact_artist = [
            item for item in exact_title
            if wanted_artist == normalize(item.get("artistName"))
            or artist_matches(item.get("artistName", ""), artist_hint)
        ]
        if not exact_artist:
            title_data = fetch_json(SEARCH_URL.format(quote(title)))
            title_songs = [
                item for item in title_data.get("results", [])
                if item.get("trackName") and item.get("artworkUrl100")
            ]
            exact_artist = [
                item for item in title_songs
                if (
                    normalize(item.get("trackName")) == wanted
                    or wanted in normalize(item.get("trackName"))
                )
                and artist_matches(item.get("artistName", ""), artist_hint)
            ]
            if not exact_artist:
                return None
        result = exact_artist[0]
    else:
        if len({normalize(item.get("artistName")) for item in exact_title}) > 1:
            return None
        result = exact_title[0] if exact_title else songs[0]
    artist = result.get("artistName", "")
    lyricist = ""
    composer = ""
    try:
        lyricist, composer = find_credits(title, artist)
    except (OSError, ValueError, KeyError) as error:
        print("词曲信息查询失败，将继续添加歌曲：{} ({})".format(title, error), file=sys.stderr)
    cover_url = result["artworkUrl100"].replace("100x100", "600x600")
    song = {
        "id": slug(result.get("trackName") or title, artist),
        "title": result.get("trackName") or title,
        "artist": artist,
        "lyricist": lyricist,
        "composer": composer,
        "cover": cover_url,
        "album": result.get("collectionName", ""),
        "year": (result.get("releaseDate") or "")[:4],
        "tags": [result["primaryGenreName"]] if result.get("primaryGenreName") else [],
        "url": result.get("trackViewUrl", ""),
    }
    try:
        song["cover"] = cache_cover(cover_url, song["title"], artist)
    except OSError as error:
        print(
            "封面无法缓存，将保留远程地址：{} ({})".format(title, error),
            file=sys.stderr,
        )
    return song


def parse_args():
    parser = argparse.ArgumentParser(
        description="Batch-add songs from a UTF-8 text file."
    )
    parser.add_argument(
        "titles",
        nargs="*",
        help="Song titles; quote titles containing spaces.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Read one song title per line (default: music-list.txt).",
    )
    parser.add_argument(
        "--remove",
        nargs="+",
        metavar="SONG",
        help="Remove songs by title, or by 'artist | title'.",
    )
    parser.add_argument(
        "--remove-file",
        type=Path,
        help="Read songs to remove, one per line.",
    )
    return parser.parse_args()


def read_titles(args):
    titles = [clean_title(title) for title in args.titles if clean_title(title)]
    input_file = args.file or ROOT / "music-list.txt"
    if input_file:
        try:
            lines = input_file.read_text(encoding="utf-8-sig").splitlines()
        except OSError as error:
            print("无法读取 {}: {}".format(input_file, error), file=sys.stderr)
            return titles, False
        titles.extend(
            clean_title(line)
            for line in lines
            if clean_title(line) and not clean_title(line).lstrip().startswith("#")
        )
    return titles, True


def remove_references(args):
    references = [clean_title(value) for value in (args.remove or [])]
    if args.remove_file:
        try:
            lines = args.remove_file.read_text(encoding="utf-8-sig").splitlines()
        except OSError as error:
            print("无法读取 {}: {}".format(args.remove_file, error), file=sys.stderr)
            return references, False
        references.extend(
            clean_title(line)
            for line in lines
            if clean_title(line) and not clean_title(line).lstrip().startswith("#")
        )
    return references, True


def remove_songs(songs, references):
    removed = []
    kept = []
    for song in songs:
        matched = False
        song_title = normalize(song.get("title"))
        song_artist = normalize(song.get("artist"))
        for reference in references:
            title, artist = parse_song_reference(reference)
            if song_title == normalize(title) and (
                not artist
                or song_artist == normalize(artist)
                or normalize(artist) in song_artist
            ):
                matched = True
                break
        if matched:
            removed.append(song)
        else:
            kept.append(song)
    return kept, removed


def remove_unused_covers(removed, remaining):
    used_covers = {
        normalize(song.get("cover"))
        for song in remaining
        if isinstance(song, dict)
    }
    for song in removed:
        cover = song.get("cover", "")
        if not cover.startswith("/music/assets/"):
            continue
        if normalize(cover) in used_covers:
            continue
        cover_path = ROOT / "static" / cover.lstrip("/")
        try:
            cover_path.unlink()
            print("已删除本地封面：{}".format(cover_path.name))
        except FileNotFoundError:
            pass
        except OSError as error:
            print("本地封面删除失败：{} ({})".format(cover_path, error), file=sys.stderr)


def main():
    args = parse_args()
    remove_references_list, readable = remove_references(args)
    if not readable:
        return 1
    if remove_references_list and (args.titles or args.file):
        print("删除模式不能同时处理新增歌曲，请分开执行。", file=sys.stderr)
        return 2
    try:
        songs = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print("无法读取 {}: {}".format(DATA_FILE, error), file=sys.stderr)
        return 1
    if not isinstance(songs, list):
        print("songs.json 必须是数组", file=sys.stderr)
        return 1

    if remove_references_list:
        songs, removed = remove_songs(songs, remove_references_list)
        if not removed:
            print("没有找到要删除的歌曲。", file=sys.stderr)
            return 1
        DATA_FILE.write_text(
            json.dumps(songs, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        remove_unused_covers(removed, songs)
        for song in removed:
            print("已删除：{} — {}".format(
                song.get("title", ""),
                song.get("artist", ""),
            ))
        print("完成：删除 {} 首，当前共 {} 首。".format(len(removed), len(songs)))
        return 0

    credits_changed = enrich_missing_credits(songs)

    titles, readable = read_titles(args)
    if not readable:
        return 1
    if not titles:
        print("没有可导入的歌曲。请把歌曲名逐行写入 music-list.txt。")
        return 0

    existing = {
        (normalize(song.get("title")), normalize(song.get("artist")))
        for song in songs
        if isinstance(song, dict)
    }
    added = 0
    for reference in titles:
        title, artist_hint = parse_song_reference(reference)
        try:
            song = find_song(title, artist_hint)
        except (OSError, ValueError, KeyError, http.client.HTTPException) as error:
            print("查询失败：{} ({})".format(reference, error), file=sys.stderr)
            continue
        if not song or not song.get("cover"):
            print(
                "未找到匹配歌曲：{}{}".format(
                    artist_hint + " — " if artist_hint else "",
                    title,
                ),
                file=sys.stderr,
            )
            continue
        key = (normalize(song["title"]), normalize(song["artist"]))
        if key in existing:
            print("跳过（已存在）：{} — {}".format(
                song["title"], song["artist"]
            ))
            continue
        songs.append(song)
        existing.add(key)
        added += 1
        print("已添加：{} — {}".format(song["title"], song["artist"]))

    if added or credits_changed:
        DATA_FILE.write_text(
            json.dumps(songs, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print("完成：新增 {} 首，当前共 {} 首。".format(added, len(songs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
