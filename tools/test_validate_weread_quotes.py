#!/usr/bin/env python3
"""Offline schema tests using synthetic, non-private quote data."""
import json
import tempfile
import unittest
from pathlib import Path

from validate_weread_quotes import validate
from validate_weread_quotes import MAX_RECORDS


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
        with self.assertRaisesRegex(ValueError, r"record 2 field text: duplicate quote text"):
            self.validate_items([item(), item()])

    def test_empty_dataset_is_rejected_without_becoming_a_valid_publication(self):
        with self.assertRaisesRegex(ValueError, "at least one quote"):
            self.validate_items([])

    def test_oversized_text_is_rejected(self):
        with self.assertRaisesRegex(ValueError, r"record 1 field text"):
            self.validate_items([item("x" * 20001)])

    def test_worker_utf16_length_limit_is_enforced(self):
        with self.assertRaisesRegex(ValueError, r"record 1 field text"):
            self.validate_items([item("😀" * 10001)])

    def test_missing_real_title_is_rejected(self):
        quote = item()
        quote["source"] = "weread"
        with self.assertRaisesRegex(ValueError, "missing real book title"):
            self.validate_items([quote])

    def test_whitespace_only_book_title_is_rejected_without_echoing_value(self):
        quote = item()
        quote["source"] = " \ufeff "
        with self.assertRaisesRegex(ValueError, r"record 1 field source"):
            self.validate_items([quote])

    def test_incorrect_source_type_is_rejected(self):
        quote = item()
        quote["source_type"] = "manual"
        with self.assertRaisesRegex(ValueError, r"record 1 field source_type"):
            self.validate_items([quote])

    def test_invalid_additional_source_is_rejected_by_field_name_only(self):
        quote = item()
        quote["also_sources"] = [{
            "source": "   ",
            "author": "private-author-value",
            "chapter": "",
            "book_id": "book-2",
            "chapter_uid": "",
            "bookmark_id": "mark-2",
        }]
        with self.assertRaises(ValueError) as raised:
            self.validate_items([quote])
        self.assertIn("record 1 field also_sources.source", str(raised.exception))
        self.assertNotIn("private-author-value", str(raised.exception))

    def test_duplicate_additional_source_identity_is_rejected(self):
        quote = item()
        quote["also_sources"] = [{
            "source": "Second Synthetic Book",
            "author": "",
            "chapter": "",
            "book_id": quote["book_id"],
            "chapter_uid": quote["chapter_uid"],
            "bookmark_id": quote["bookmark_id"],
        }]
        with self.assertRaisesRegex(
                ValueError, r"record 1 field also_sources: duplicate source identity"):
            self.validate_items([quote])

    def test_dataset_record_limit_is_enforced(self):
        records = [item("synthetic-{}".format(index))
                   for index in range(MAX_RECORDS + 1)]
        with self.assertRaisesRegex(
                ValueError, r"record {} field records".format(MAX_RECORDS + 1)):
            self.validate_items(records)

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
        with self.assertRaisesRegex(
                ValueError, r"record 1 field also_sources\.source"):
            self.validate_items([quote])


if __name__ == "__main__":
    unittest.main()
