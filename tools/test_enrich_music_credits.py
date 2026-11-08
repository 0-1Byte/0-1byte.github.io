import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import enrich_music_credits as enrich


class EnrichMusicCreditsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="music-credit-test-")
        self.data_file = Path(self.temporary.name) / "songs.json"
        self.original_data_file = enrich.DATA_FILE
        enrich.DATA_FILE = self.data_file

    def tearDown(self):
        enrich.DATA_FILE = self.original_data_file
        self.temporary.cleanup()

    def run_main(self, songs):
        self.data_file.write_text(json.dumps(songs), encoding="utf-8")
        return enrich.main()

    def test_instrumental_with_composer_skips_lookup_and_warning(self):
        song = {
            "title": "Esperanza",
            "artist": "Hermanos Gutiérrez",
            "tags": ["Instrumental"],
            "lyricist": "",
            "composer": "Daniel Alejandro Hotz, Stephan Ricardo Hotz",
        }
        with patch.object(enrich, "find_recording") as lookup:
            with patch("builtins.print") as output:
                result = self.run_main([song])
        self.assertEqual(result, 0)
        lookup.assert_not_called()
        warnings = " ".join(str(call.args[0]) for call in output.call_args_list if call.args)
        self.assertNotIn("Esperanza", warnings)

    def test_instrumental_without_composer_still_requires_composer(self):
        song = {
            "title": "Pure Instrumental",
            "artist": "Test Artist",
            "tags": ["Instrumental"],
            "lyricist": "",
            "composer": "",
        }
        with patch.object(enrich, "find_recording", return_value=None):
            result = self.run_main([song])
        self.assertEqual(result, 0)

    def test_find_recording_rejects_partial_title_match(self):
        song = {"title": "Esperanza", "artist": "Hermanos Gutiérrez"}
        with patch.object(
            enrich,
            "fetch_json",
            return_value={"recordings": [{"title": "Esperanza (Live)", "id": "wrong"}]},
        ):
            self.assertIsNone(enrich.find_recording(song))

    def test_existing_credits_are_not_overwritten(self):
        song = {
            "title": "Test Song",
            "artist": "Test Artist",
            "tags": ["Pop"],
            "lyricist": "Human Lyricist",
            "composer": "Human Composer",
        }
        with patch.object(enrich, "find_recording") as lookup:
            result = self.run_main([song])
        self.assertEqual(result, 0)
        lookup.assert_not_called()
        saved = json.loads(self.data_file.read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["lyricist"], "Human Lyricist")
        self.assertEqual(saved[0]["composer"], "Human Composer")


if __name__ == "__main__":
    unittest.main()
