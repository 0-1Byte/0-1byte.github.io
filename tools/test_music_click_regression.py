import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = (ROOT / "static" / "music" / "style.css").read_text(encoding="utf-8")
JS = (ROOT / "static" / "music" / "script.js").read_text(encoding="utf-8")
HTML = (ROOT / "static" / "music" / "index.html").read_text(encoding="utf-8")


class MusicClickRegressionTest(unittest.TestCase):
    def test_click_targets_are_not_blocked_by_hidden_edge_links(self):
        self.assertIn(".song-card.is-wall-visible", CSS)
        self.assertIn("pointer-events: auto;", CSS)
        self.assertIn("pointer-events: none;", CSS)
        self.assertIn("visibility: hidden;", CSS)
        self.assertIn(".cover-select", CSS)
        self.assertIn(".external", CSS)
        self.assertIn("grid.addEventListener(\"click\"", JS)
        self.assertIn(".cover-select", JS)
        self.assertIn("const layer = 100 - Math.abs(offset) + (offset === 0 ? 10 : 0);", JS)

    def test_all_cards_use_button_based_selection(self):
        self.assertIn('class="cover-select"', JS)
        self.assertIn('data-index="${index}"', JS)
        self.assertIn('aria-label="选择唱片：${escapeHtml(title)}"', JS)


if __name__ == "__main__":
    unittest.main()
