"""Local manager for the Music page's static/music/songs.json library."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from urllib.parse import quote, unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
MUSIC_DIR = ROOT / "static" / "music"
DATA_FILE = MUSIC_DIR / "songs.json"
ASSETS_DIR = MUSIC_DIR / "assets"
REQUIRED_FIELDS = ("id", "title", "artist", "cover")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
DERIVATIVE_WIDTHS = (240, 320, 480)
PREVIEW_HOST = "127.0.0.1"
PREVIEW_PUBLIC_HOST = "localhost"
PREVIEW_PORT = 1313


class LibraryError(Exception):
    """An actionable Music library validation or operation error."""


def load_songs(data_file: Path = DATA_FILE) -> list[dict]:
    try:
        songs = json.loads(data_file.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise LibraryError("无法读取歌曲数据 {}：{}".format(data_file, error)) from error
    if not isinstance(songs, list):
        raise LibraryError("{} 的顶层数据必须是 JSON 数组".format(data_file))
    return songs


def write_songs(songs: list[dict], data_file: Path = DATA_FILE) -> None:
    data_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=str(data_file.parent),
            prefix=data_file.name + ".",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(songs, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(str(temporary), str(data_file))
    except OSError as error:
        if temporary and temporary.exists():
            temporary.unlink()
        raise LibraryError("无法安全写入歌曲数据 {}：{}".format(data_file, error)) from error


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in text if char.isalnum())


def make_slug(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).casefold()
    text = "".join(
        char if char.isascii() and char.isalnum() or "\u3400" <= char <= "\u9fff" else "-"
        for char in text
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9\u3400-\u9fff]+", "-", text)).strip("-")


def cover_path_for(song: dict, assets_dir: Path) -> Path:
    cover = song.get("cover")
    if not isinstance(cover, str):
        raise LibraryError("封面字段必须是 /music/assets/ 下的本地路径")
    parsed = urlsplit(cover)
    decoded = unquote(parsed.path)
    prefix = "/music/assets/"
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or not decoded.startswith(prefix):
        raise LibraryError("封面路径必须是 /music/assets/ 下的本地路径：{}".format(cover))
    relative = Path(decoded[len(prefix):])
    if not relative.parts or relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
        raise LibraryError("封面路径包含非法目录：{}".format(cover))
    root = assets_dir.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise LibraryError("封面路径超出管理目录：{}".format(cover)) from error
    return path


def validate_library(
    root: Path = ROOT,
    build: bool = True,
    hugo_path: Path | None = None,
) -> list[str]:
    data_file = root / "static" / "music" / "songs.json"
    assets_dir = root / "static" / "music" / "assets"
    errors: list[str] = []
    try:
        songs = load_songs(data_file)
    except LibraryError as error:
        return [str(error)]

    ids: dict[str, int] = {}
    titles: dict[tuple[str, str], int] = {}
    referenced: set[Path] = set()
    img_names: set[str] = set()
    referenced_derivatives: set[Path] = set()

    for index, song in enumerate(songs, 1):
        location = "{} 第 {} 条".format(data_file, index)
        if not isinstance(song, dict):
            errors.append("{}：歌曲记录必须是对象".format(location))
            continue
        title = song.get("title") if isinstance(song.get("title"), str) else "（未知歌曲）"
        label = "{}「{}」".format(location, title)
        for field in REQUIRED_FIELDS:
            if not isinstance(song.get(field), str) or not song[field].strip():
                errors.append("{}：缺少有效的 {} 字段".format(label, field))
        tags = song.get("tags")
        is_instrumental = isinstance(tags, list) and any(
            isinstance(tag, str) and tag.strip().casefold() == "instrumental"
            for tag in tags
        )
        for field in ("lyricist", "composer"):
            if field not in song:
                errors.append("{}：缺少有效的 {} 字段".format(label, field))
                continue
            value = song[field]
            if not isinstance(value, str):
                errors.append("{}：{} 字段类型错误，必须是字符串".format(label, field))
                continue
            if field == "lyricist" and is_instrumental and not value.strip():
                continue
            if not value.strip():
                errors.append("{}：缺少有效的 {} 字段".format(label, field))
        song_id = song.get("id")
        if isinstance(song_id, str) and song_id:
            if song_id in ids:
                errors.append("{}：ID {!r} 与第 {} 条重复".format(label, song_id, ids[song_id]))
            else:
                ids[song_id] = index
        artist = song.get("artist")
        if isinstance(title, str) and isinstance(artist, str) and title != "（未知歌曲）":
            title_key = (normalize(artist), normalize(title))
            if title_key in titles:
                errors.append("{}：歌手与歌曲名和第 {} 条重复".format(label, titles[title_key]))
            else:
                titles[title_key] = index
        try:
            cover_path = cover_path_for(song, assets_dir)
            referenced.add(cover_path)
            if not cover_path.is_file():
                errors.append("{}：封面文件不存在：{}".format(label, cover_path))
            elif cover_path.suffix.lower() not in IMAGE_SUFFIXES:
                errors.append("{}：不支持的封面格式：{}".format(label, cover_path.suffix))
        except LibraryError as error:
            errors.append("{}：{}".format(label, error))
        img = song.get("img")
        if img:
            if not isinstance(img, str) or Path(img).name != img:
                errors.append("{}：img 必须是封面衍生图文件名".format(label))
            else:
                img_names.add(img)
                for width in DERIVATIVE_WIDTHS:
                    derivative = assets_dir / "{}-{}.webp".format(img, width)
                    referenced_derivatives.add(derivative.resolve())
                    if not derivative.is_file():
                        errors.append("{}：缺少页面引用的封面资源：{}".format(label, derivative))

    page_script = root / "static" / "music" / "script.js"
    try:
        script = page_script.read_text(encoding="utf-8")
        if "songs.json" not in script or "fetchCollectionJson" not in script:
            errors.append("{}：页面没有从 songs.json 读取歌曲数据".format(page_script))
        if not re.search(r"song\s*&&\s*song\.title\s*&&\s*song\.cover", script):
            errors.append("{}：页面歌曲过滤条件已变化，请复核管理器校验逻辑".format(page_script))
    except OSError as error:
        errors.append("无法读取页面脚本 {}：{}".format(page_script, error))

    if assets_dir.is_dir():
        for path in assets_dir.iterdir():
            if (
                path.is_file()
                and path.suffix.lower() in IMAGE_SUFFIXES
                and path.resolve() not in referenced
                and path.resolve() not in referenced_derivatives
            ):
                errors.append("孤立封面文件（没有歌曲记录引用）：{}".format(path))
    else:
        errors.append("封面目录不存在：{}".format(assets_dir))

    if errors or not build:
        return errors

    hugo = hugo_path or root / "hugo.exe"
    if not hugo.is_file() and hugo_path is None:
        hugo = Path(shutil.which("hugo") or "")
    if not hugo.is_file():
        return ["找不到 Hugo 可执行文件，无法验证页面构建"]

    try:
        build_parent = root / "tools" / "_probe_out"
        build_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="music-library-build-",
            dir=str(build_parent),
        ) as destination:
            result = subprocess.run(
                [
                    str(hugo),
                    "--minify",
                    "--cleanDestinationDir",
                    "--destination",
                    destination,
                ],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode:
                detail = (result.stderr or result.stdout).strip()
                errors.append("Hugo 构建失败：{}".format(detail[-2000:]))
                return errors
            output = Path(destination)
            built_data = output / "music" / "songs.json"
            built_page = output / "music" / "index.html"
            try:
                built_songs = load_songs(built_data)
            except LibraryError as error:
                errors.append(str(error))
                return errors
            if built_songs != songs:
                errors.append("Hugo 产物 songs.json 与权威数据源不一致：{}".format(built_data))
            if not built_page.is_file() or "song-grid" not in built_page.read_text(encoding="utf-8"):
                errors.append("Hugo 产物中缺少 Music 页面或唱片列表容器：{}".format(built_page))
            for path in referenced:
                try:
                    relative = path.resolve().relative_to(assets_dir.resolve())
                except ValueError:
                    continue
                if not (output / "music" / "assets" / relative).is_file():
                    errors.append("Hugo 产物缺少引用的封面资源：{}".format(relative))
            for img in img_names:
                for width in DERIVATIVE_WIDTHS:
                    name = "{}-{}.webp".format(img, width)
                    if not (output / "music" / "assets" / name).is_file():
                        errors.append("Hugo 产物缺少响应式封面：{}".format(name))
    except OSError as error:
        errors.append("无法执行隔离的 Hugo 构建：{}".format(error))
    return errors


def list_songs(songs: list[dict], keyword: str = "") -> None:
    term = normalize(keyword)
    matches = [
        song for song in songs
        if not term or term in normalize("{} {} {}".format(
            song.get("title", ""), song.get("artist", ""), song.get("id", "")
        ))
    ]
    print("歌曲总数：{}（匹配：{}）".format(len(songs), len(matches)))
    for index, song in enumerate(matches, 1):
        print("{:>3}. {} — {} | ID: {} | 封面: {}".format(
            index,
            song.get("title", "（无标题）"),
            song.get("artist", "（无歌手）"),
            song.get("id", "（无 ID）"),
            song.get("cover", "（无封面）"),
        ))


def add_song(
    root: Path,
    title: str,
    artist: str,
    cover_source: Path,
    extra: dict | None = None,
) -> dict:
    title = title.strip()
    artist = artist.strip()
    source = cover_source.expanduser().resolve()
    if not title or not artist:
        raise LibraryError("歌曲名称和歌手均为必填项")
    if not source.is_file():
        raise LibraryError("封面图片不存在或不是文件：{}".format(source))
    if source.suffix.lower() not in IMAGE_SUFFIXES:
        raise LibraryError("不支持的封面格式：{}".format(source.suffix))

    data_file = root / "static" / "music" / "songs.json"
    assets_dir = root / "static" / "music" / "assets"
    songs = load_songs(data_file)
    song_id = make_slug("{}-{}".format(artist, title))
    if not song_id:
        raise LibraryError("无法从歌手和歌曲名称生成唯一 ID")
    if any(song.get("id") == song_id for song in songs if isinstance(song, dict)):
        raise LibraryError("歌曲 ID 已存在：{}".format(song_id))
    if any(
        normalize(song.get("artist", "")) == normalize(artist)
        and normalize(song.get("title", "")) == normalize(title)
        for song in songs
        if isinstance(song, dict)
    ):
        raise LibraryError("相同歌手和歌曲名称已存在：{} — {}".format(artist, title))

    assets_dir.mkdir(parents=True, exist_ok=True)
    filename = song_id + source.suffix.lower()
    destination = assets_dir / filename
    if destination.exists():
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:8]
        destination = assets_dir / "{}-{}{}".format(song_id, digest, source.suffix.lower())
        if destination.exists():
            raise LibraryError("封面目标文件已存在，不会覆盖：{}".format(destination))

    copied = False
    try:
        with source.open("rb") as input_stream, destination.open("xb") as output_stream:
            copied = True
            shutil.copyfileobj(input_stream, output_stream)
        record = {
            "id": song_id,
            "title": title,
            "artist": artist,
            "cover": "/music/assets/{}".format(quote(destination.name, safe="-._~")),
        }
        for key, value in (extra or {}).items():
            if value not in (None, "", []):
                record[key] = value
        songs.append(record)
        write_songs(songs, data_file)
    except (OSError, LibraryError) as error:
        if copied:
            destination.unlink(missing_ok=True)
        if isinstance(error, LibraryError):
            raise
        raise LibraryError("新增歌曲失败：{}".format(error)) from error
    return record


def delete_song(root: Path, index: int) -> tuple[dict, bool]:
    data_file = root / "static" / "music" / "songs.json"
    assets_dir = root / "static" / "music" / "assets"
    songs = load_songs(data_file)
    if index < 0 or index >= len(songs):
        raise LibraryError("歌曲编号超出范围")
    song = songs[index]
    cover = cover_path_for(song, assets_dir)
    remaining = songs[:index] + songs[index + 1:]
    shared = any(
        isinstance(other, dict)
        and cover_path_for(other, assets_dir) == cover
        for other in remaining
    )
    write_songs(remaining, data_file)
    return song, shared


def delete_unreferenced_cover(root: Path, song: dict) -> bool:
    assets_dir = root / "static" / "music" / "assets"
    cover = cover_path_for(song, assets_dir)
    songs = load_songs(root / "static" / "music" / "songs.json")
    if any(
        isinstance(other, dict) and cover_path_for(other, assets_dir) == cover
        for other in songs
    ):
        return False
    if cover.is_file():
        cover.unlink()
        return True
    return False


def prompt_add(root: Path) -> None:
    title = input("歌曲名称：").strip()
    artist = input("歌手：").strip()
    if not title or not artist:
        raise LibraryError("歌曲名称和歌手均为必填项")
    cover_text = input("封面图片路径：").strip().strip("\"'")
    extra: dict = {}
    for field, label in (
        ("album", "专辑"),
        ("year", "发行年份"),
        ("lyricist", "作词"),
        ("composer", "作曲"),
    ):
        value = input("{}（可留空）：".format(label)).strip()
        if value:
            extra[field] = int(value) if field == "year" and value.isdigit() else value
    tags = input("标签（逗号分隔，可留空）：").strip()
    if tags:
        extra["tags"] = [part.strip() for part in tags.split(",") if part.strip()]
    url = input("歌曲链接（可留空）：").strip()
    if url:
        extra["url"] = url
    song = add_song(root, title, artist, Path(cover_text), extra)
    print("新增成功：{} — {}".format(song["artist"], song["title"]))
    print("唯一 ID：{}".format(song["id"]))
    print("封面：{}".format(song["cover"]))


def prompt_delete(root: Path, keyword: str = "") -> None:
    songs = load_songs(root / "static" / "music" / "songs.json")
    term = normalize(keyword)
    matches = [
        (index, song) for index, song in enumerate(songs)
        if not term or term in normalize("{} {} {}".format(
            song.get("title", ""), song.get("artist", ""), song.get("id", "")
        ))
    ]
    list_songs([song for _, song in matches], keyword)
    if not matches:
        return
    selection = input("输入上方编号以精确选择要删除的歌曲（直接回车取消）：").strip()
    if not selection:
        print("已取消，没有修改。")
        return
    if not selection.isdigit() or not 1 <= int(selection) <= len(matches):
        raise LibraryError("无效编号，没有修改。")
    actual_index, song = matches[int(selection) - 1]
    cover = song.get("cover", "（无封面）")
    print("将删除歌曲记录：{} — {}".format(song.get("artist"), song.get("title")))
    print("封面：{}".format(cover))
    if input("确认删除歌曲记录？[y/N] ").strip().casefold() != "y":
        print("已取消，没有修改。")
        return
    removed, shared = delete_song(root, actual_index)
    print("已删除歌曲记录：{} — {}".format(removed.get("artist"), removed.get("title")))
    try:
        cover_file = cover_path_for(removed, root / "static" / "music" / "assets")
        if shared:
            print("此封面仍被其他歌曲引用，已保留：{}".format(cover_file))
        elif cover_file.is_file():
            print("封面当前未被其他歌曲引用，默认保留：{}".format(cover_file))
            if input("是否同时删除此封面文件？[y/N] ").strip().casefold() == "y":
                if delete_unreferenced_cover(root, removed):
                    print("已删除未被引用的封面文件：{}".format(cover_file))
                else:
                    print("该封面仍被其他歌曲引用或文件已不存在，未删除。")
        else:
            print("封面文件已不存在：{}".format(cover_file))
    except LibraryError as error:
        print("封面资源未删除：{}".format(error))


def interactive(root: Path) -> int:
    while True:
        print("\nMusic Library Manager")
        print("1. 查看歌曲    2. 搜索歌曲    3. 添加歌曲")
        print("4. 删除歌曲    5. 检查数据    6. 本地预览    0. 退出")
        choice = input("选择操作：").strip()
        try:
            if choice == "0":
                return 0
            if choice == "1":
                list_songs(load_songs(root / "static" / "music" / "songs.json"))
            elif choice == "2":
                list_songs(load_songs(root / "static" / "music" / "songs.json"), input("关键词："))
            elif choice == "3":
                prompt_add(root)
            elif choice == "4":
                prompt_delete(root, input("删除关键词（可留空列出全部）："))
            elif choice == "5":
                return run_validate(root, build=True)
            elif choice == "6":
                return run_preview(root)
            else:
                print("无效选项，请重新选择。")
        except (LibraryError, OSError, ValueError) as error:
            print("操作失败：{}".format(error), file=sys.stderr)


def run_validate(root: Path, build: bool) -> int:
    errors = validate_library(root, build=build)
    if errors:
        print("歌曲数据检查失败（{} 项）：".format(len(errors)), file=sys.stderr)
        for error in errors:
            print("- {}".format(error), file=sys.stderr)
        return 1
    songs = load_songs(root / "static" / "music" / "songs.json")
    print("检查通过：{} 首歌曲，记录字段、重复项、封面引用和页面数据链路正常。".format(len(songs)))
    if build:
        print("Hugo 隔离构建通过：Music 页面、songs.json 与引用封面均已生成。")
    return 0


def _process_option(command: str, option: str) -> str:
    match = re.search(
        r"(?:^|\s)--{}(?:=|\s+)(?:\"([^\"]+)\"|'([^']+)'|([^\s]+))".format(
            re.escape(option)
        ),
        command,
        re.IGNORECASE,
    )
    return next((value for value in match.groups() if value), "") if match else ""


def _resolve_path(value: str) -> Path | None:
    if not value:
        return None
    try:
        return Path(value.strip("\"'")).resolve()
    except OSError:
        return None


def _get_port_listeners(port: int) -> list[dict]:
    if os.name != "nt":
        raise LibraryError("预览进程识别目前仅支持 Windows")
    shell = shutil.which("pwsh") or shutil.which("powershell.exe") or shutil.which("powershell")
    if not shell:
        raise LibraryError("无法检查端口占用：找不到 PowerShell")
    script = (
        "$ErrorActionPreference='Stop'; "
        "$rows=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue "
        "| Where-Object {{ $_.LocalPort -eq {port} }} "
        "| Select-Object -ExpandProperty OwningProcess "
        "-Unique | ForEach-Object {{ "
        "$p=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $_); "
        "if ($p) {{ $parent=Get-CimInstance Win32_Process "
        "-Filter ('ProcessId=' + $p.ParentProcessId) -ErrorAction SilentlyContinue; "
        "[pscustomobject]@{{ pid=[int]$p.ProcessId; executable=$p.ExecutablePath; "
        "command=$p.CommandLine; parentExecutable=$parent.ExecutablePath; "
        "parentCommand=$parent.CommandLine }} }} "
        "}}); if ($rows.Count) {{ $rows | ConvertTo-Json -Compress }}".format(port=port)
    )
    try:
        result = subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise LibraryError("无法检查端口 {} 的监听进程：{}".format(port, error)) from error
    if result.returncode:
        raise LibraryError(
            "无法检查端口 {} 的监听进程：{}".format(port, result.stderr.strip())
        )
    output = result.stdout.strip()
    if not output:
        return []
    try:
        rows = json.loads(output)
    except json.JSONDecodeError as error:
        raise LibraryError("PowerShell 返回了无法解析的进程信息") from error
    if isinstance(rows, dict):
        rows = [rows]
    return rows


def _process_project_path(process: dict) -> str:
    command = process.get("command") or ""
    source = _resolve_path(_process_option(command, "source"))
    if source:
        return str(source)
    for option in ("directory", "root"):
        path = _resolve_path(_process_option(command, option))
        if path:
            return str(path)
    config = _resolve_path(_process_option(command, "config"))
    if config:
        return str(config.parent)
    executable = _resolve_path(process.get("executable") or "")
    if (
        executable
        and executable.name.casefold() == "hugo.exe"
        and not _process_option(command, "source")
        and not _process_option(command, "config")
    ):
        return str(executable.parent)
    parent_executable = _resolve_path(process.get("parentExecutable") or "")
    if parent_executable:
        parts = [part.casefold() for part in parent_executable.parts]
        if ".venv" in parts:
            return str(Path(*parent_executable.parts[:parts.index(".venv")]))
    return "无法从该进程命令行确定项目目录"


def _is_current_project_hugo(
    process: dict,
    root: Path,
    hugo: Path,
    config: Path,
    require_explicit_project: bool = False,
) -> bool:
    command = process.get("command") or ""
    executable = _resolve_path(process.get("executable") or "")
    source = _resolve_path(_process_option(command, "source"))
    configured = _resolve_path(_process_option(command, "config"))
    has_project_arguments = source is not None or configured is not None
    explicit_project = has_project_arguments and (
        (source is None or source == root)
        and (configured is None or configured == config)
    )
    project_executable = not has_project_arguments and executable == hugo
    if require_explicit_project and not has_project_arguments:
        return False
    if not (explicit_project or project_executable):
        return False
    if not re.search(r"(?:^|\s)server(?:\s|$)", command, re.IGNORECASE):
        return False
    requested_port = _process_option(command, "port")
    return not requested_port or requested_port == str(PREVIEW_PORT)


def _describe_listeners(listeners: list[dict]) -> str:
    return "\n".join(
        "  PID: {pid}\n  命令: {command}\n  可执行文件: {executable}\n  项目路径: {project}".format(
            pid=process.get("pid", "未知"),
            command=process.get("command") or "不可用",
            executable=process.get("executable") or "不可用",
            project=_process_project_path(process),
        )
        for process in listeners
    )


def _verify_preview(root: Path) -> None:
    data_file = root / "static" / "music" / "songs.json"
    base = "http://{}:{}".format(PREVIEW_PUBLIC_HOST, PREVIEW_PORT)
    try:
        with urlopen(base + "/music/", timeout=8) as response:
            page = response.read().decode("utf-8", errors="replace")
            if response.status != 200 or "song-grid" not in page:
                raise LibraryError("当前项目预览的 Music 页面内容不正确")
        with urlopen(base + "/music/songs.json", timeout=8) as response:
            served_data = response.read()
            if response.status != 200:
                raise LibraryError("当前项目预览歌曲 JSON 返回 HTTP {}".format(response.status))
        if served_data != data_file.read_bytes():
            raise LibraryError(
                "1313 上的 JSON 与当前项目权威数据不一致；为避免复用旧预览，未连接该服务。"
            )
    except (OSError, URLError) as error:
        raise LibraryError("无法验证 1313 上的当前项目预览：{}".format(error)) from error


def _stop_preview(root: Path, hugo: Path, config: Path) -> int:
    listeners = _get_port_listeners(PREVIEW_PORT)
    if not listeners:
        print("Music 预览当前未运行（端口 1313 无监听进程）。")
        return 0
    foreign = [
        process for process in listeners
        if not _is_current_project_hugo(
            process, root, hugo, config, require_explicit_project=True
        )
    ]
    if foreign:
        raise LibraryError(
            "端口 1313 存在不属于当前项目的进程，拒绝停止：\n{}".format(
                _describe_listeners(foreign)
            )
        )
    pids = sorted({int(process["pid"]) for process in listeners})
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as error:
            raise LibraryError("停止已验证的 Hugo 进程 PID {} 失败：{}".format(pid, error)) from error
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        remaining = _get_port_listeners(PREVIEW_PORT)
        if not remaining:
            print("已停止当前项目 Music 预览，PID：{}".format(", ".join(map(str, pids))))
            return 0
        if any(
            not _is_current_project_hugo(
                process, root, hugo, config, require_explicit_project=True
            )
            for process in remaining
        ):
            raise LibraryError("停止预览时端口 1313 出现了其他进程；未对其执行操作。")
        time.sleep(0.25)
    raise LibraryError("Hugo 进程仍在运行；未强制结束。PID：{}".format(", ".join(map(str, pids))))


def run_preview(root: Path, stop: bool = False) -> int:
    root = root.resolve()
    hugo = root / "hugo.exe"
    if not hugo.is_file():
        found = shutil.which("hugo")
        if not found:
            raise LibraryError("找不到 Hugo 可执行文件")
        hugo = Path(found).resolve()
    config = root / "hugo.toml"
    if not config.is_file():
        raise LibraryError("找不到 Hugo 配置文件：{}".format(config))

    if stop:
        return _stop_preview(root, hugo, config)

    host = PREVIEW_HOST
    port = PREVIEW_PORT
    listeners = _get_port_listeners(port)
    if listeners:
        if all(
            _is_current_project_hugo(process, root, hugo, config)
            for process in listeners
        ):
            _verify_preview(root)
            print(
                "复用当前项目已运行的 Hugo 预览：http://{}:{}/music/".format(
                    PREVIEW_PUBLIC_HOST, port
                )
            )
            print(
                "歌曲数据：http://{}:{}/music/songs.json".format(
                    PREVIEW_PUBLIC_HOST, port
                )
            )
            return 0
        raise LibraryError(
            "端口 {} 已被其他进程占用，未连接、停止或更换端口：\n{}".format(
                port, _describe_listeners(listeners)
            )
        )

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind((host, port))
    except OSError as error:
        raced_listeners = _get_port_listeners(port)
        raise LibraryError(
            "端口 {} 刚被占用，未自动更换端口：\n{}\n{}".format(
                port,
                _describe_listeners(raced_listeners) if raced_listeners else "无法取得监听进程信息。",
                error,
            )
        ) from error

    command = [
        str(hugo),
        "server",
        "--source",
        str(root),
        "--config",
        str(config),
        "--baseURL",
        "http://{}:{}/".format(PREVIEW_PUBLIC_HOST, port),
        "--bind",
        host,
        "--port",
        str(port),
        "--disableFastRender",
    ]
    print("启动命令：{}".format(subprocess.list2cmdline(command)))
    print("Music 页面：http://{}:{}/music/".format(PREVIEW_PUBLIC_HOST, port))
    print("歌曲数据：http://{}:{}/music/songs.json".format(PREVIEW_PUBLIC_HOST, port))
    print("此预览保持运行，直到用户在该终端按 Ctrl+C 或主动执行 preview --stop。")
    try:
        return subprocess.call(command, cwd=str(root))
    except KeyboardInterrupt:
        print("\n本地预览已停止。")
        return 0
    except OSError as error:
        raise LibraryError("无法启动 Hugo 预览：{}".format(error)) from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="管理 Music 页面唯一歌曲数据源及封面")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("list", help="列出全部歌曲")
    search_parser = subparsers.add_parser("search", help="按关键词搜索歌曲")
    search_parser.add_argument("keyword")
    subparsers.add_parser("add", help="交互式添加歌曲")
    delete_parser = subparsers.add_parser("delete", help="选择并删除歌曲")
    delete_parser.add_argument("keyword", nargs="?", default="")
    validate_parser = subparsers.add_parser("validate", help="检查数据并隔离构建 Hugo 页面")
    validate_parser.add_argument("--no-build", action="store_true", help="只检查数据和资源，不执行 Hugo")
    preview_parser = subparsers.add_parser("preview", help="启动或停止 Hugo 本地预览")
    preview_parser.add_argument(
        "--stop", action="store_true", help="仅停止已验证属于当前项目的 1313 预览"
    )
    args = parser.parse_args(argv)
    try:
        if args.command is None:
            return interactive(ROOT)
        if args.command == "list":
            list_songs(load_songs(DATA_FILE))
            return 0
        if args.command == "search":
            list_songs(load_songs(DATA_FILE), args.keyword)
            return 0
        if args.command == "add":
            prompt_add(ROOT)
            return 0
        if args.command == "delete":
            prompt_delete(ROOT, args.keyword)
            return 0
        if args.command == "validate":
            return run_validate(ROOT, build=not args.no_build)
        if args.command == "preview":
            return run_preview(ROOT, stop=args.stop)
        parser.error("未知操作")
    except (LibraryError, OSError, ValueError) as error:
        print("操作失败：{}".format(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
