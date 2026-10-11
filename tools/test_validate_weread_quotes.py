#!/usr/bin/env python3
"""Offline schema tests using synthetic, non-private quote data."""
import json
import tempfile
import unittest
from pathlib import Path

from validate_weread_quotes import validate


def item(text="synthetic quote"):
    return {
        "text": text,
        "source_type": "weread",
        "source": "Synthetic Book",
        "author": "",
        "chapter": "",
        "book_id": "book-1",
        "chapter_uid": "",
        "bookmark_id": "mark-1",
        "also_sources": [],
    }


class ValidateWereadQuotesTests(unittest.TestCase):
    def validate_items(self, items):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quotes.json"
            path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
            return validate(path)

    def test_valid_synthetic_data_and_missing_metadata_counts(self):
        stats = self.validate_items([item()])
        self.assertEqual(stats["quotes"], 1)
        self.assertEqual(stats["missing_author"], 1)
        self.assertEqual(stats["missing_chapter"], 1)

    def test_duplicate_public_text_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate public quote text"):
            self.validate_items([item(), item()])

    def test_empty_dataset_is_rejected_without_becoming_a_valid_publication(self):
        with self.assertRaisesRegex(ValueError, "at least one quote"):
            self.validate_items([])

    def test_oversized_text_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty quote text"):
            self.validate_items([item("x" * 20001)])

    def test_missing_real_title_is_rejected(self):
        quote = item()
        quote["source"] = "weread"
        with self.assertRaisesRegex(ValueError, "missing real book title"):
            self.validate_items([quote])

    def test_incorrect_source_type_is_rejected(self):
        quote = item()
        quote["source_type"] = "manual"
        with self.assertRaisesRegex(ValueError, "invalid source_type"):
            self.validate_items([quote])

    def test_additional_attribution_is_counted_and_validated(self):
        quote = item()
        quote["also_sources"] = [{
            "source": "Second Synthetic Book",
            "author": "Synthetic Author",
            "chapter": "Synthetic Chapter",
            "book_id": "book-2",
            "chapter_uid": "chapter-2",
            "bookmark_id": "mark-2",
        }]
        self.assertEqual(self.validate_items([quote])["additional_attributions"], 1)
        quote["also_sources"][0]["source"] = "weread"
        with self.assertRaisesRegex(ValueError, "missing additional book title"):
            self.validate_items([quote])


if __name__ == "__main__":
    unittest.main()
