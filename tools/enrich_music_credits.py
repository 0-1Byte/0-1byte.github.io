"""Fill missing music credits from MusicBrainz without guessing."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


DATA_FILE = Path(__file__).resolve().parents[1] / "static" / "music" / "songs.json"
API_ROOT = "https://musicbrainz.org/ws/2"
USER_AGENT = "0-1byte.github.io music credits/1.0 (https://0-1byte.github.io/)"
LAST_REQUEST_AT = 0.0


def fetch_json(url: str) -> dict:
    global LAST_REQUEST_AT
    wait = 1.1 - (time.monotonic() - LAST_REQUEST_AT)
    if wait > 0:
        time.sleep(wait)
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urlopen(request, timeout=20) as response:
        result = json.load(response)
    LAST_REQUEST_AT = time.monotonic()
    return result


def normalized(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def recording_score(recording: dict, song: dict) -> int:
    title = normalized(song.get("title"))
    album = normalized(song.get("album"))
    year = str(song.get("year", "")).strip()
    score = 0

    if normalized(recording.get("title")) == title:
        score += 100
    elif title and title in normalized(recording.get("title")):
        score += 25

    if recording.get("video") is False:
        score += 10
    if "live" not in normalized(recording.get("disambiguation")):
        score += 10

    release_titles = {
        normalized(release.get("title"))
        for release in recording.get("releases", [])
        if release.get("title")
    }
    if album and album in release_titles:
        score += 60
    elif album and any(album in release_title for release_title in release_titles):
        score += 30

    if any(
        release.get("status") == "Official"
        for release in recording.get("releases", [])
    ):
        score += 20

    first_release_date = str(recording.get("first-release-date", ""))
    if year and first_release_date.startswith(year):
        score += 20

    return score


def find_recording(song: dict) -> dict | None:
    title = str(song.get("title", "")).strip()
    artist = str(song.get("artist", "")).strip()
    if not title or not artist:
        return None

    query = quote(f'recording:"{title}" AND artist:"{artist}"')
    result = fetch_json(f"{API_ROOT}/recording/?query={query}&fmt=json&limit=100")
    recordings = result.get("recordings", [])
    if not recordings:
        return None

    return max(recordings, key=lambda recording: recording_score(recording, song))


def extract_credits(recording_id: str) -> tuple[str, str]:
    recording = fetch_json(
        f"{API_ROOT}/recording/{recording_id}?inc=work-rels+artist-rels&fmt=json"
    )
    lyricists: set[str] = set()
    composers: set[str] = set()

    work_ids = {
        relation.get("work", {}).get("id")
        for relation in recording.get("relations", [])
        if relation.get("target-type") == "work"
        and relation.get("work", {}).get("id")
    }

    for work_id in work_ids:
        work = fetch_json(f"{API_ROOT}/work/{work_id}?inc=artist-rels&fmt=json")
        for relation in work.get("relations", []):
            artist = relation.get("artist", {})
            name = artist.get("name")
            if not name:
                continue
            relation_type = normalized(relation.get("type"))
            if relation_type in {"lyricist", "lyrics", "words"}:
                lyricists.add(name)
            elif relation_type in {"composer", "music", "writer"}:
                composers.add(name)

    # Some MusicBrainz entries expose work relations in a compact form.
    for relation in recording.get("relations", []):
        if relation.get("target-type") != "artist":
            continue
        name = relation.get("artist", {}).get("name")
        relation_type = normalized(relation.get("type"))
        if name:
            if relation_type in {"lyricist", "lyrics", "words"}:
                lyricists.add(name)
            elif relation_type in {"composer", "music", "writer"}:
                composers.add(name)

    return ", ".join(sorted(lyricists)), ", ".join(sorted(composers))


def main() -> int:
    try:
        songs = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"::error::Unable to read {DATA_FILE}: {error}")
        return 1

    if not isinstance(songs, list):
        print("::error::songs.json must contain an array")
        return 1

    missing: list[str] = []
    changed = False
    updated_count = 0

    for index, song in enumerate(songs):
        if not isinstance(song, dict):
            print(f"::warning::Song at index {index} is not an object; skipped")
            continue

        if "lyricist" not in song:
            song["lyricist"] = ""
            changed = True
        if "composer" not in song:
            song["composer"] = ""
            changed = True
        if song["lyricist"] and song["composer"]:
            continue

        label = f'{song.get("title", "Untitled")} — {song.get("artist", "Unknown artist")}'
        try:
            recording = find_recording(song)
            if recording:
                lyricist, composer = extract_credits(recording["id"])
                if not song["lyricist"] and lyricist:
                    song["lyricist"] = lyricist
                    changed = True
                if not song["composer"] and composer:
                    song["composer"] = composer
                    changed = True
                if lyricist or composer:
                    updated_count += 1
        except (OSError, ValueError, KeyError) as error:
            print(f"::warning::{label}: MusicBrainz lookup failed: {error}")

        if not song["lyricist"] or not song["composer"]:
            missing.append(label)
            print(f"::warning::{label}: lyricist/composer not found; left blank")

    if changed:
        DATA_FILE.write_text(
            json.dumps(songs, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if missing:
        print(f"::notice::{len(missing)} song(s) still have missing credits")
    print(f"Checked {len(songs)} song(s); updated {updated_count} song(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
