import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import music_library


class MusicLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="music-library-test-")
        self.root = Path(self.temporary.name)
        self.music_dir = self.root / "static" / "music"
        self.assets = self.music_dir / "assets"
        self.assets.mkdir(parents=True)
        self.data_file = self.music_dir / "songs.json"
        self.page_script = self.music_dir / "script.js"
        self.page_script.write_text(
            'fetchCollectionJson("/music/songs.json"); '
            "songs.filter(song => song && song.title && song.cover);",
            encoding="utf-8",
        )
        self.data_file.write_text("[]\n", encoding="utf-8")
        self.source_cover = self.root / "test-cover.jpg"
        self.source_cover.write_bytes(b"isolated test image")

    def tearDown(self):
        self.temporary.cleanup()

    def test_add_and_reject_duplicate_without_overwrite(self):
        record = music_library.add_song(
            self.root, "Test Track", "Test Artist", self.source_cover
        )
        self.assertEqual(record["id"], "test-artist-test-track")
        self.assertEqual(record["cover"], "/music/assets/test-artist-test-track.jpg")
        copied_cover = self.assets / "test-artist-test-track.jpg"
        self.assertEqual(copied_cover.read_bytes(), self.source_cover.read_bytes())
        self.assertEqual(len(json.loads(self.data_file.read_text(encoding="utf-8"))), 1)

        with self.assertRaisesRegex(music_library.LibraryError, "ID 已存在"):
            music_library.add_song(
                self.root, "Test Track", "Test Artist", self.source_cover
            )
        self.assertTrue(copied_cover.is_file())
        self.assertEqual(len(json.loads(self.data_file.read_text(encoding="utf-8"))), 1)

    def test_reject_missing_cover_and_duplicate_record(self):
        with self.assertRaisesRegex(music_library.LibraryError, "封面图片不存在"):
            music_library.add_song(
                self.root, "Missing Cover", "Test Artist", self.root / "missing.jpg"
            )
        record = music_library.add_song(
            self.root, "Test Track", "Test Artist", self.source_cover
        )
        record["id"] = "different-id"
        songs = json.loads(self.data_file.read_text(encoding="utf-8"))
        songs.append(record)
        self.data_file.write_text(json.dumps(songs), encoding="utf-8")
        errors = music_library.validate_library(self.root, build=False)
        self.assertTrue(any("歌手与歌曲名" in error for error in errors), errors)

    def test_credit_field_validation(self):
        base_cover = "/music/assets/test-cover.jpg"
        (self.assets / "test-cover.jpg").write_bytes(b"test image")
        cases = [
            (
                "ordinary_missing_lyricist",
                {"id": "ordinary-missing-lyricist", "title": "普通缺词", "artist": "Artist", "cover": base_cover, "composer": "Composer"},
                "lyricist",
            ),
            (
                "ordinary_missing_composer",
                {"id": "ordinary-missing-composer", "title": "普通缺曲", "artist": "Artist", "cover": base_cover, "lyricist": "Lyricist"},
                "composer",
            ),
            (
                "ordinary_complete",
                {"id": "ordinary-complete", "title": "普通完整", "artist": "Artist", "cover": base_cover, "lyricist": "Lyricist", "composer": "Composer"},
                None,
            ),
            (
                "instrumental_empty_lyricist",
                {"id": "instrumental-empty", "title": "Esperanza", "artist": "Hermanos Gutiérrez", "cover": base_cover, "lyricist": "", "composer": "Daniel Alejandro Hotz, Stephan Ricardo Hotz", "tags": ["Instrumental"]},
                None,
            ),
            (
                "instrumental_missing_composer",
                {"id": "instrumental-missing-composer", "title": "纯器乐缺曲", "artist": "Artist", "cover": base_cover, "lyricist": "", "composer": "", "tags": ["Instrumental"]},
                "composer",
            ),
        ]
        for _name, song, expected_field in cases:
            self.data_file.write_text(json.dumps([song]), encoding="utf-8")
            errors = music_library.validate_library(self.root, build=False)
            if expected_field is None:
                self.assertFalse(
                    any("lyricist" in error or "composer" in error for error in errors),
                    errors,
                )
            else:
                self.assertTrue(
                    any(song["title"] in error and expected_field in error for error in errors),
                    errors,
                )

    def test_validate_reports_duplicate_id_missing_field_and_bad_cover(self):
        songs = [
            {"id": "same", "title": "First", "artist": "Artist", "cover": "/outside.jpg"},
            {"id": "same", "title": "Second", "cover": "/music/assets/missing.jpg"},
        ]
        self.data_file.write_text(json.dumps(songs), encoding="utf-8")
        errors = music_library.validate_library(self.root, build=False)
        self.assertTrue(any("ID 'same' 与第 1 条重复" in error for error in errors), errors)
        self.assertTrue(any("缺少有效的 artist 字段" in error for error in errors), errors)
        self.assertTrue(any("封面路径必须是 /music/assets/" in error for error in errors), errors)
        self.assertTrue(any("封面文件不存在" in error for error in errors), errors)

    def test_delete_keeps_cover_by_default_and_allows_explicit_cleanup(self):
        record = music_library.add_song(
            self.root, "Test Track", "Test Artist", self.source_cover
        )
        cover = self.assets / "test-artist-test-track.jpg"
        removed, shared = music_library.delete_song(self.root, 0)
        self.assertEqual(removed, record)
        self.assertFalse(shared)
        self.assertTrue(cover.is_file())
        self.assertTrue(music_library.delete_unreferenced_cover(self.root, removed))
        self.assertFalse(cover.exists())
        self.assertEqual(json.loads(self.data_file.read_text(encoding="utf-8")), [])

    def test_shared_cover_is_never_deleted(self):
        record = music_library.add_song(
            self.root, "Test Track", "Test Artist", self.source_cover
        )
        songs = json.loads(self.data_file.read_text(encoding="utf-8"))
        second = dict(record, id="second-record", title="Alternate Title")
        songs.append(second)
        self.data_file.write_text(json.dumps(songs), encoding="utf-8")

        removed, shared = music_library.delete_song(self.root, 0)
        self.assertTrue(shared)
        self.assertFalse(music_library.delete_unreferenced_cover(self.root, removed))
        self.assertTrue((self.assets / "test-artist-test-track.jpg").is_file())

    def test_preview_identifies_only_current_project_hugo(self):
        hugo = self.root / "hugo.exe"
        config = self.root / "hugo.toml"
        command = (
            '"{}" server --source "{}" --config "{}" '
            "--baseURL http://localhost:1313/ --port 1313"
        ).format(hugo, self.root, config)
        process = {
            "pid": 42,
            "executable": str(hugo),
            "command": command,
        }
        self.assertTrue(
            music_library._is_current_project_hugo(
                process, self.root, hugo, config
            )
        )
        foreign = dict(
            process,
            executable=str(self.root / "other" / "hugo.exe"),
            command=command.replace(str(self.root), str(self.root / "other")),
        )
        self.assertFalse(
            music_library._is_current_project_hugo(
                foreign, self.root, hugo, config
            )
        )
        conflicting_arguments = dict(
            process,
            command=command.replace(
                "--source \"{}\"".format(self.root),
                "--source \"{}\"".format(self.root / "other"),
            ),
        )
        self.assertFalse(
            music_library._is_current_project_hugo(
                conflicting_arguments, self.root, hugo, config
            )
        )
        wrong_port = dict(process, command=command.replace("--port 1313", "--port 1317"))
        self.assertFalse(
            music_library._is_current_project_hugo(
                wrong_port, self.root, hugo, config
            )
        )

    def test_preview_stop_refuses_foreign_process(self):
        (self.root / "hugo.exe").write_bytes(b"isolated test executable")
        config = self.root / "hugo.toml"
        config.write_text("", encoding="utf-8")
        process = {
            "pid": 457,
            "executable": "C:\\other\\hugo.exe",
            "command": "hugo.exe server --source C:\\other --port 1313",
        }
        with patch.object(music_library, "_get_port_listeners", return_value=[process]), \
                patch.object(music_library.os, "kill") as kill:
            with self.assertRaisesRegex(music_library.LibraryError, "拒绝停止"):
                music_library._stop_preview(
                    self.root, self.root / "hugo.exe", config
                )
        kill.assert_not_called()

    def test_preview_stop_refuses_hugo_without_explicit_project_path(self):
        (self.root / "hugo.exe").write_bytes(b"isolated test executable")
        config = self.root / "hugo.toml"
        config.write_text("", encoding="utf-8")
        process = {
            "pid": 458,
            "executable": str(self.root / "hugo.exe"),
            "command": '"{}" server --port 1313'.format(self.root / "hugo.exe"),
        }
        with patch.object(music_library, "_get_port_listeners", return_value=[process]), \
                patch.object(music_library.os, "kill") as kill:
            with self.assertRaisesRegex(music_library.LibraryError, "拒绝停止"):
                music_library._stop_preview(
                    self.root, self.root / "hugo.exe", config
                )
        kill.assert_not_called()

    def test_preview_reports_foreign_port_owner_without_starting_hugo(self):
        (self.root / "hugo.exe").write_bytes(b"isolated test executable")
        (self.root / "hugo.toml").write_text("", encoding="utf-8")
        process = {
            "pid": 456,
            "executable": "C:\\other\\python.exe",
            "command": "python -m http.server 1313 --directory C:\\other\\public",
        }
        with patch.object(music_library, "_get_port_listeners", return_value=[process]), \
                patch.object(music_library.subprocess, "call") as call:
            with self.assertRaisesRegex(music_library.LibraryError, "PID: 456"):
                music_library.run_preview(self.root)
        call.assert_not_called()

    def test_preview_stop_flag_is_explicit(self):
        with patch.object(music_library, "run_preview", return_value=0) as preview:
            self.assertEqual(music_library.main(["preview", "--stop"]), 0)
        preview.assert_called_once_with(music_library.ROOT, stop=True)

    def test_isolated_add_build_delete_flow(self):
        project_parent = music_library.ROOT / "tools" / "_probe_out"
        project_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="music-library-site-",
            dir=str(project_parent),
        ) as directory:
            root = Path(directory)
            music_dir = root / "static" / "music"
            assets = music_dir / "assets"
            assets.mkdir(parents=True)
            (root / "tools" / "_probe_out").mkdir(parents=True)
            (root / "hugo.toml").write_text(
                'baseURL = "https://example.test/"\n'
                'title = "Music manager isolated test"\n'
                'disableKinds = ["taxonomy", "term", "RSS", "sitemap"]\n',
                encoding="utf-8",
            )
            (music_dir / "index.html").write_text(
                '<main><div id="song-grid"></div></main>', encoding="utf-8"
            )
            (music_dir / "script.js").write_text(
                'fetchCollectionJson("/music/songs.json"); '
                "songs.filter(song => song && song.title && song.cover);",
                encoding="utf-8",
            )
            (music_dir / "songs.json").write_text("[]\n", encoding="utf-8")
            source = root / "isolated-cover.jpg"
            source.write_bytes(b"isolated test image")

            record = music_library.add_song(
                root,
                "Preview Track",
                "Preview Artist",
                source,
                extra={"lyricist": "Test Lyricist", "composer": "Test Composer"},
            )
            hugo_path = music_library.ROOT / "hugo.exe"
            self.assertEqual(
                music_library.validate_library(root, build=True, hugo_path=hugo_path),
                [],
            )

            removed, shared = music_library.delete_song(root, 0)
            self.assertEqual(removed, record)
            self.assertFalse(shared)
            cover = assets / "preview-artist-preview-track.jpg"
            self.assertTrue(cover.is_file())
            self.assertTrue(music_library.delete_unreferenced_cover(root, removed))
            self.assertFalse(cover.exists())
            self.assertEqual(
                music_library.validate_library(root, build=True, hugo_path=hugo_path),
                [],
            )


if __name__ == "__main__":
    unittest.main()
