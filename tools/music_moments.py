"""Manage optional audio Moments for the static Music page."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
MUSIC_DIR = ROOT / "static" / "music"
SONGS_FILE = MUSIC_DIR / "songs.json"
MOMENTS_FILE = MUSIC_DIR / "moments.json"
MOMENTS_DIR = MUSIC_DIR / "moments"


class MomentError(Exception):
    pass


def load_json(path: Path, default=None):
    if not path.exists():
        if default is not None:
            return default
        raise MomentError("文件不存在：{}".format(path))
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise MomentError("无法读取 JSON {}：{}".format(path, error)) from error
    return value


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=str(path.parent),
            prefix=path.name + ".", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(str(temporary), str(path))
    except OSError as error:
        if temporary and temporary.exists():
            temporary.unlink()
        raise MomentError("无法安全写入 {}：{}".format(path, error)) from error


def slug(value: str) -> str:
    text = value.strip().casefold()
    text = re.sub(r"[^a-z0-9\u3400-\u9fff]+", "-", text, flags=re.UNICODE)
    return text.strip("-") or "moment"


def parse_time(value: str) -> float:
    value = value.strip()
    if ":" in value:
        parts = value.split(":")
        if len(parts) > 3:
            raise MomentError("时间格式无效：{}".format(value))
        total = 0.0
        for part in parts:
            total = total * 60 + float(part)
        return total
    return float(value)


def ffprobe_duration(ffprobe: str, path: Path) -> float:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise MomentError("ffprobe无法读取音频：{}".format(result.stderr.strip()))
    try:
        return float(result.stdout.strip())
    except ValueError as error:
        raise MomentError("无法解析音频时长：{}".format(path)) from error


def ffprobe_media(ffprobe: str, path: Path) -> dict:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries",
         "format=duration:stream=codec_name,codec_type,channels,sample_rate",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise MomentError("ffprobe无法读取媒体文件：{}".format(result.stderr.strip()))
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise MomentError("无法解析ffprobe媒体信息：{}".format(path)) from error
    streams = [stream for stream in data.get("streams", []) if stream.get("codec_type") == "audio"]
    if not streams:
        raise MomentError("文件中没有可用音轨：{}".format(path))
    try:
        duration = float(data["format"]["duration"])
    except (KeyError, TypeError, ValueError) as error:
        raise MomentError("无法解析媒体时长：{}".format(path)) from error
    return {
        "duration": duration,
        "codec_name": streams[0].get("codec_name"),
        "channels": streams[0].get("channels"),
        "sample_rate": streams[0].get("sample_rate"),
    }


def validate_output_audio(ffprobe: str, path: Path, expected_duration: float) -> float:
    if path.suffix.lower() != ".mp3":
        raise MomentError("生成的Moment必须是MP3：{}".format(path))
    info = ffprobe_media(ffprobe, path)
    if info["codec_name"] != "mp3":
        raise MomentError("生成的编码不是MP3：{}".format(info["codec_name"]))
    if info["channels"] != 2:
        raise MomentError("生成的音频不是Stereo（2声道）：{}".format(info["channels"]))
    duration = info["duration"]
    if expected_duration > 0 and abs(duration - expected_duration) > 1.0:
        raise MomentError(
            "生成时长异常：预期 {:.3f} 秒，实际 {:.3f} 秒".format(expected_duration, duration)
        )
    return duration


def source_path(source: str, moments_dir: Path = MOMENTS_DIR) -> Path | None:
    if not isinstance(source, str) or not source.strip():
        return None
    parsed = urlsplit(source)
    decoded = unquote(parsed.path)
    prefix = "/music/moments/"
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or not decoded.startswith(prefix):
        return None
    relative = Path(decoded[len(prefix):])
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        return None
    return (moments_dir / relative).resolve()


def validate_moments(root: Path = ROOT) -> list[str]:
    music_dir = root / "static" / "music"
    songs_file = music_dir / "songs.json"
    moments_file = music_dir / "moments.json"
    moments_dir = music_dir / "moments"
    errors: list[str] = []
    try:
        songs = load_json(songs_file)
    except MomentError as error:
        return [str(error)]
    if not isinstance(songs, list):
        return ["{} 的顶层数据必须是 JSON 数组".format(songs_file)]
    song_ids = {
        song.get("id") for song in songs
        if isinstance(song, dict) and isinstance(song.get("id"), str)
    }
    try:
        moments = load_json(moments_file, default=[])
    except MomentError as error:
        return [str(error)]
    if not isinstance(moments, list):
        return ["{} 的顶层数据必须是 JSON 数组".format(moments_file)]

    seen: dict[str, int] = {}
    for index, moment in enumerate(moments, 1):
        label = "{} 第 {} 条".format(moments_file, index)
        if not isinstance(moment, dict):
            errors.append("{}：Moment 记录必须是对象".format(label))
            continue
        song_id = moment.get("songId")
        if not isinstance(song_id, str) or not song_id.strip():
            errors.append("{}：缺少有效的 songId".format(label))
        elif song_id in seen:
            errors.append("{}：songId {!r} 与第 {} 条重复".format(label, song_id, seen[song_id]))
        else:
            seen[song_id] = index
            if song_id not in song_ids:
                errors.append("{}：songId {!r} 不存在于 songs.json".format(label, song_id))
        for field in ("source", "title"):
            if not isinstance(moment.get(field), str) or not moment[field].strip():
                errors.append("{}：缺少有效的 {} 字段".format(label, field))
        if not isinstance(moment.get("sourceInfo"), str) or not moment["sourceInfo"].strip():
            errors.append("{}：缺少有效的 sourceInfo".format(label))
        duration = moment.get("duration")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
            errors.append("{}：duration 必须是大于 0 的数字".format(label))
        path = source_path(moment.get("source"), moments_dir)
        if path is None:
            errors.append("{}：source 必须是 /music/moments/ 下的本地 MP3 路径".format(label))
        elif not path.is_file():
            errors.append("{}：Moment 音频文件不存在：{}".format(label, path))
        elif path.suffix.lower() != ".mp3":
            errors.append("{}：Moment 音频必须是 MP3：{}".format(label, path))
        elif shutil.which("ffprobe"):
            try:
                info = ffprobe_media(shutil.which("ffprobe"), path)
                duration = info["duration"]
                if duration <= 0:
                    errors.append("{}：Moment 音频时长无效：{}".format(label, path))
                elif info["codec_name"] != "mp3":
                    errors.append("{}：Moment 音频编码必须是 MP3".format(label))
            except MomentError as error:
                errors.append("{}：{}".format(label, error))
    return errors


def add_moment(
    input_path: Path,
    song_id: str,
    title: str,
    start_time: str,
    end_time: str | None,
    source_info: str,
    output_name: str | None = None,
) -> dict:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise MomentError(
            "未找到 FFmpeg 或 FFprobe。请先安装 FFmpeg，并确保 ffmpeg.exe 和 ffprobe.exe 都加入 PATH；"
            "也可手动将授权素材 MP3 放入 static/music/moments/，再编辑 static/music/moments.json。"
        )
    source = input_path.expanduser().resolve()
    if not source.is_file():
        raise MomentError("原始音频或视频不存在：{}".format(source))
    allowed_input_suffixes = {
        ".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus",
        ".mp4", ".mov", ".m4v",
    }
    if source.suffix.lower() not in allowed_input_suffixes:
        raise MomentError(
            "不支持的输入格式：{}；支持 MP3/WAV 等音频及 MP4/MOV 等视频".format(source.suffix)
        )
    start = parse_time(start_time)
    end = parse_time(end_time) if end_time else None
    if start < 0 or (end is not None and end <= start):
        raise MomentError("开始/结束时间无效")
    if not source_info.strip():
        raise MomentError("sourceInfo（演出或录制来源）不能为空")

    songs = load_json(SONGS_FILE)
    if not isinstance(songs, list) or not any(
        isinstance(song, dict) and song.get("id") == song_id for song in songs
    ):
        raise MomentError("songId 不存在于 songs.json：{}".format(song_id))
    moments = load_json(MOMENTS_FILE, default=[])
    if not isinstance(moments, list):
        raise MomentError("{} 的顶层数据必须是数组".format(MOMENTS_FILE))
    if any(isinstance(moment, dict) and moment.get("songId") == song_id for moment in moments):
        raise MomentError("该歌曲已配置 Moment，请先手动删除或替换现有配置")
    if not title.strip():
        raise MomentError("Moment 名称不能为空")

    MOMENTS_DIR.mkdir(parents=True, exist_ok=True)
    if output_name:
        filename = Path(output_name.strip()).name
        if not filename.lower().endswith(".mp3"):
            raise MomentError("输出文件名必须以 .mp3 结尾：{}".format(filename))
        if Path(output_name.strip()).name != output_name.strip():
            raise MomentError("输出文件名不能包含目录：{}".format(output_name))
    else:
        filename = "{}-{}.mp3".format(slug(song_id), slug(title))
    destination = MOMENTS_DIR / filename
    if destination.exists():
        raise MomentError("目标文件已存在，不会覆盖：{}".format(destination))
    try:
        ffprobe_media(ffprobe, source)
    except MomentError as error:
        raise MomentError("原始素材没有可读取的音轨：{} ({})".format(source, error)) from error

    length = end - start if end is not None else None
    command = [
        ffmpeg, "-v", "error", "-y",
        "-ss", "{:.3f}".format(start),
        "-i", str(source),
        *(["-t", "{:.3f}".format(length)] if length is not None else []),
        "-map", "0:a:0",
        "-vn", "-c:a", "libmp3lame", "-b:a", "160k",
        "-ar", "48000", "-ac", "2",
        "-map_metadata", "-1", str(destination),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise MomentError("FFmpeg 截取失败：{}".format(result.stderr.strip()))
        duration = validate_output_audio(ffprobe, destination, length if length is not None else 0.0)
        if duration <= 0:
            raise MomentError("生成的音频时长无效：{}".format(destination))
        moment = {
            "songId": song_id,
            "source": "/music/moments/{}".format(destination.name),
            "title": title.strip(),
            "sourceInfo": source_info.strip(),
            "duration": round(duration, 3),
            "startTime": round(start, 3),
        }
        if end is not None:
            moment["endTime"] = round(end, 3)
        moments.append(moment)
        write_json(MOMENTS_FILE, moments)
        return moment
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="管理 Music 页面 Moments 音频片段")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_parser = subparsers.add_parser("add", help="从授权音频或视频截取并生成 Moment")
    add_parser.add_argument("input", help="原始 MP3/WAV/MP4/MOV 等本地素材路径")
    add_parser.add_argument("--song-id", required=True)
    add_parser.add_argument("--title", required=True)
    add_parser.add_argument("--start", default="0", help="开始时间（秒或 HH:MM:SS）")
    add_parser.add_argument("--end", help="结束时间（秒或 HH:MM:SS，可选）")
    add_parser.add_argument("--source-info", required=True, help="演出或录制来源")
    add_parser.add_argument("--output-name", help="可选 MP3 文件名，例如 adele-hello-munich.mp3")
    subparsers.add_parser("validate", help="检查 moments.json 与 MP3 资源")
    args = parser.parse_args()

    try:
        if args.command == "validate":
            errors = validate_moments()
            if errors:
                for error in errors:
                    print(error, file=sys.stderr)
                return 1
            print("Moments validation passed: moments.json and audio resources are valid.")
            return 0
        moment = add_moment(
            Path(args.input), args.song_id, args.title, args.start, args.end,
            args.source_info, args.output_name,
        )
        print(json.dumps(moment, ensure_ascii=False, indent=2))
        return 0
    except (MomentError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
