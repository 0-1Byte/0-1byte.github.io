import json
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import music_moments


class MusicMomentsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="music-moments-test-")
        self.root = Path(self.temporary.name)
        self.music_dir = self.root / "static" / "music"
        self.moments_dir = self.music_dir / "moments"
        self.moments_dir.mkdir(parents=True)
        self.songs_file = self.music_dir / "songs.json"
        self.moments_file = self.music_dir / "moments.json"
        self.songs_file.write_text(
            json.dumps([{"id": "test-track", "title": "Track", "artist": "Artist"}]),
            encoding="utf-8",
        )
        self.moments_file.write_text("[]", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_empty_array_is_valid_and_object_is_rejected(self):
        self.assertEqual(self.moments_file.read_text(encoding="utf-8"), "[]")
        self.assertEqual(music_moments.validate_moments(self.root), [])

        self.moments_file.write_text(json.dumps({
            "songId": "test-track",
            "source": "/music/moments/test.mp3",
        }), encoding="utf-8")
        errors = music_moments.validate_moments(self.root)
        self.assertTrue(any("顶层数据必须是 JSON 数组" in error for error in errors), errors)

    def test_validate_accepts_valid_moment_and_rejects_duplicates(self):
        audio = self.moments_dir / "test-track-live.mp3"
        audio.write_bytes(b"test mp3")
        moments = [{
            "songId": "test-track",
            "source": "/music/moments/test-track-live.mp3",
            "title": "Live moment",
            "sourceInfo": "Authorized test recording",
            "duration": 12.0,
        }]
        self.moments_file.write_text(json.dumps(moments), encoding="utf-8")
        with unittest.mock.patch.object(
            music_moments,
            "ffprobe_media",
            return_value={"duration": 12.0, "codec_name": "mp3", "channels": 1},
        ):
            self.assertEqual(music_moments.validate_moments(self.root), [])

        moments.append(dict(moments[0]))
        self.moments_file.write_text(json.dumps(moments), encoding="utf-8")
        errors = music_moments.validate_moments(self.root)
        self.assertTrue(any("重复" in error for error in errors), errors)

    def test_validate_rejects_unknown_song_and_missing_audio(self):
        self.moments_file.write_text(json.dumps([{
            "songId": "missing-song",
            "source": "/music/moments/missing.mp3",
            "title": "Missing",
        }]), encoding="utf-8")
        errors = music_moments.validate_moments(self.root)
        self.assertTrue(any("不存在于 songs.json" in error for error in errors), errors)
        self.assertTrue(any("音频文件不存在" in error for error in errors), errors)

    def test_add_reports_missing_ffmpeg_without_processing(self):
        source = self.root / "authorized.mp3"
        source.write_bytes(b"authorized source")
        with unittest.mock.patch.object(music_moments.shutil, "which", return_value=None):
            with self.assertRaisesRegex(music_moments.MomentError, "未找到 FFmpeg"):
                music_moments.add_moment(
                    source, "test-track", "Live", "0", "10", "Authorized recording"
                )

    def test_add_reports_missing_ffprobe_when_ffmpeg_exists(self):
        source = self.root / "authorized.mp3"
        source.write_bytes(b"authorized source")

        def available(tool):
            return "/tools/ffmpeg.exe" if tool == "ffmpeg" else None

        with unittest.mock.patch.object(music_moments.shutil, "which", side_effect=available):
            with self.assertRaisesRegex(music_moments.MomentError, "未找到 FFmpeg 或 FFprobe"):
                music_moments.add_moment(
                    source, "test-track", "Live", "0", "10", "Authorized recording"
                )

    def test_parse_time_accepts_seconds_and_clock_and_rejects_invalid_values(self):
        self.assertEqual(music_moments.parse_time("12.5"), 12.5)
        self.assertEqual(music_moments.parse_time("1:02.5"), 62.5)
        self.assertEqual(music_moments.parse_time("1:02:03"), 3723.0)
        with self.assertRaises(ValueError):
            music_moments.parse_time("not-a-time")

    def test_mp4_uses_input_seek_and_creates_stereo_160k_mp3(self):
        source = self.root / "authorized.mp4"
        source.write_bytes(b"authorized video")
        captured_commands = []

        def run_command(command, **kwargs):
            captured_commands.append(command)
            if command[0] == "/tools/ffmpeg.exe":
                Path(command[-1]).write_bytes(b"generated mp3")
            return subprocess.CompletedProcess(command, 0, "", "")

        with unittest.mock.patch.object(music_moments.shutil, "which", side_effect=lambda tool:
                                   "/tools/ffmpeg.exe" if tool == "ffmpeg" else "/tools/ffprobe.exe"):
            with unittest.mock.patch.object(music_moments, "SONGS_FILE", self.songs_file), \
                 unittest.mock.patch.object(music_moments, "MOMENTS_FILE", self.moments_file), \
                 unittest.mock.patch.object(music_moments, "MOMENTS_DIR", self.moments_dir), \
                 unittest.mock.patch.object(music_moments.subprocess, "run", side_effect=run_command), \
                 unittest.mock.patch.object(
                     music_moments, "ffprobe_media",
                     return_value={"duration": 80.0, "codec_name": "mp3", "channels": 2},
                 ):
                moment = music_moments.add_moment(
                    source, "test-track", "Munich Backing Vocals",
                    "03:50", "05:10", "Authorized Munich recording",
                    "adele-hello-munich.mp3",
                )

        command = music_moments.subprocess.run.call_args if False else None
        self.assertEqual(moment["songId"], "test-track")
        self.assertEqual(moment["duration"], 80.0)
        self.assertEqual(moment["source"], "/music/moments/adele-hello-munich.mp3")
        destination = self.moments_dir / "adele-hello-munich.mp3"
        self.assertTrue(destination.is_file())
        ffmpeg_command = next(command for command in captured_commands if command[0] == "/tools/ffmpeg.exe")
        ss_index = ffmpeg_command.index("-ss")
        input_index = ffmpeg_command.index("-i")
        self.assertLess(ss_index, input_index)
        self.assertEqual(ffmpeg_command[ss_index + 1], "230.000")
        self.assertIn("160k", ffmpeg_command)
        self.assertIn("-ac", ffmpeg_command)
        self.assertEqual(ffmpeg_command[ffmpeg_command.index("-ac") + 1], "2")

    def test_adele_hello_song_id_exists_in_library(self):
        songs = json.loads(music_moments.SONGS_FILE.read_text(encoding="utf-8-sig"))
        ids = {song.get("id") for song in songs if isinstance(song, dict)}
        self.assertIn("adele-hello", ids)

    def test_existing_destination_is_never_overwritten(self):
        source = self.root / "authorized.mov"
        source.write_bytes(b"authorized video")
        existing = self.moments_dir / "existing.mp3"
        existing.write_bytes(b"keep me")
        with unittest.mock.patch.object(music_moments.shutil, "which", return_value="/tools/tool.exe"):
            with unittest.mock.patch.object(music_moments, "SONGS_FILE", self.songs_file), \
                 unittest.mock.patch.object(music_moments, "MOMENTS_FILE", self.moments_file), \
                 unittest.mock.patch.object(music_moments, "MOMENTS_DIR", self.moments_dir):
                with self.assertRaisesRegex(music_moments.MomentError, "不会覆盖"):
                    music_moments.add_moment(
                        source, "test-track", "Live", "0", "10",
                        "Authorized recording", "existing.mp3",
                    )
        self.assertEqual(existing.read_bytes(), b"keep me")


if __name__ == "__main__":
    unittest.main()
