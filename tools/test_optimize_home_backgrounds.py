import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import optimize_home_backgrounds as optimizer


class OptimizeHomepageBackgroundsTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.sources = self.root / "backgrounds"
        self.outputs = self.root / "optimized"
        self.sources.mkdir()

        Image.new("RGBA", (1200, 800), (30, 70, 110, 180)).save(self.sources / "海边.png")
        Image.new("RGB", (1600, 900), (50, 90, 120)).save(self.sources / "mountain.jpg")
        (self.sources / "broken.jpg").write_bytes(b"not an image")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_build_is_incremental_and_refreshes_changed_or_removed_sources(self):
        first = optimizer.optimize_backgrounds(self.sources, self.outputs)
        self.assertEqual(first["generated"], 4)
        self.assertEqual(first["reused"], 0)
        self.assertEqual(len(list(self.outputs.glob("*.webp"))), 4)

        with mock.patch.object(optimizer, "create_variant", wraps=optimizer.create_variant) as convert:
            second = optimizer.optimize_backgrounds(self.sources, self.outputs)
        self.assertEqual(convert.call_count, 0)
        self.assertEqual(second["generated"], 0)
        self.assertEqual(second["reused"], 4)

        before = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.outputs.glob("*.webp")
        }
        Image.new("RGB", (1600, 900), (90, 40, 80)).save(self.sources / "mountain.jpg")
        with mock.patch.object(optimizer, "create_variant", wraps=optimizer.create_variant) as convert:
            changed = optimizer.optimize_backgrounds(self.sources, self.outputs)
        self.assertEqual(convert.call_count, 2)
        self.assertEqual(changed["generated"], 2)
        self.assertEqual(changed["reused"], 2)
        for name in ("mountain--jpg--mobile.webp", "mountain--jpg--desktop.webp"):
            self.assertNotEqual(hashlib.sha256((self.outputs / name).read_bytes()).hexdigest(), before[name])
        for name in ("海边--png--mobile.webp", "海边--png--desktop.webp"):
            self.assertEqual(hashlib.sha256((self.outputs / name).read_bytes()).hexdigest(), before[name])

        before_rename = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.outputs.glob("*.webp")
        }
        (self.sources / "海边.png").rename(self.sources / "海岸.png")
        with mock.patch.object(optimizer, "create_variant", wraps=optimizer.create_variant) as convert:
            renamed = optimizer.optimize_backgrounds(self.sources, self.outputs)
        self.assertEqual(convert.call_count, 2)
        self.assertEqual(renamed["generated"], 2)
        self.assertEqual(renamed["reused"], 2)
        self.assertFalse((self.outputs / "海边--png--mobile.webp").exists())
        self.assertTrue((self.outputs / "海岸--png--mobile.webp").exists())
        for name in ("mountain--jpg--mobile.webp", "mountain--jpg--desktop.webp"):
            self.assertEqual(hashlib.sha256((self.outputs / name).read_bytes()).hexdigest(), before_rename[name])
        manifest = json.loads((self.outputs / ".manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(set(manifest["sources"]), {"mountain.jpg", "海岸.png"})

        (self.sources / "海岸.png").unlink()
        with mock.patch.object(optimizer, "create_variant", wraps=optimizer.create_variant) as convert:
            deleted = optimizer.optimize_backgrounds(self.sources, self.outputs)
        self.assertEqual(convert.call_count, 0)
        self.assertEqual(deleted["generated"], 0)
        self.assertEqual(deleted["reused"], 2)
        self.assertFalse((self.outputs / "海岸--png--mobile.webp").exists())
        manifest = json.loads((self.outputs / ".manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(set(manifest["sources"]), {"mountain.jpg"})

    def test_conversion_setting_change_invalidates_cached_variants(self):
        optimizer.optimize_backgrounds(self.sources, self.outputs)
        with mock.patch.object(optimizer, "CONVERSION_VERSION", optimizer.CONVERSION_VERSION + 1):
            with mock.patch.object(optimizer, "create_variant", wraps=optimizer.create_variant) as convert:
                refreshed = optimizer.optimize_backgrounds(self.sources, self.outputs)
        self.assertEqual(convert.call_count, 4)
        self.assertEqual(refreshed["generated"], 4)

    def test_transparent_png_and_corrupt_image_are_handled(self):
        with self.assertWarns(RuntimeWarning):
            result = optimizer.optimize_backgrounds(self.sources, self.outputs)
        self.assertEqual(len(result["failures"]), 1)
        mobile_png = self.outputs / "海边--png--mobile.webp"
        with Image.open(mobile_png) as image:
            self.assertIn("A", image.getbands())
        self.assertFalse((self.outputs / "broken--jpg--mobile.webp").exists())

    def test_manifest_can_live_outside_the_publish_directory(self):
        manifest = self.root / ".cache" / "homepage-backgrounds" / ".manifest.json"
        with self.assertWarns(RuntimeWarning):
            optimizer.optimize_backgrounds(self.sources, self.outputs, manifest)
        self.assertTrue(manifest.is_file())
        self.assertFalse((self.outputs / ".manifest.json").exists())
        self.assertEqual(len(list(self.outputs.glob("*.webp"))), 4)


if __name__ == "__main__":
    unittest.main()
