#!/usr/bin/env python3
"""Validate the sanitized public WeRead quote dataset without printing its text."""
import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "weread_quotes.json"
QUOTE_FIELDS = {
    "text", "source_type", "source", "author", "chapter",
    "book_id", "chapter_uid", "bookmark_id", "also_sources",
}
SOURCE_FIELDS = {
    "source", "author", "chapter", "book_id", "chapter_uid", "bookmark_id",
}


def validate(path):
    with path.open("r", encoding="utf-8") as source:
        items = json.load(source)
    if not isinstance(items, list):
        raise ValueError("dataset root must be a JSON array")

    seen_texts = set()
    stats = {
        "quotes": len(items),
        "missing_author": 0,
        "missing_chapter": 0,
        "additional_attributions": 0,
    }
    if not items:
        raise ValueError("dataset must contain at least one quote")
    for index, item in enumerate(items):
        if not isinstance(item, dict) or set(item) != QUOTE_FIELDS:
            raise ValueError("invalid quote schema at item {}".format(index + 1))
        if item["source_type"] != "weread":
            raise ValueError("invalid source_type at item {}".format(index + 1))
        if (not isinstance(item["text"], str) or not item["text"].strip()
                or len(item["text"]) > 20000
                or any(ord(char) < 32 and char not in "\n\t\r" for char in item["text"])):
            raise ValueError("empty quote text at item {}".format(index + 1))
        if item["text"] in seen_texts:
            raise ValueError("duplicate public quote text")
        seen_texts.add(item["text"])
        for field in ("source", "author", "chapter", "book_id",
                      "chapter_uid", "bookmark_id"):
            if not isinstance(item[field], str) or len(item[field]) > 2000:
                raise ValueError("invalid metadata type at item {}".format(index + 1))
        if (not item["source"] or item["source"].lower() == "weread"
                or len(item["book_id"]) > 512
                or len(item["chapter_uid"]) > 512
                or len(item["bookmark_id"]) > 512):
            raise ValueError("missing real book title at item {}".format(index + 1))
        if not item["book_id"]:
            raise ValueError("missing book identifier at item {}".format(index + 1))
        if not isinstance(item["also_sources"], list) or len(item["also_sources"]) > 100:
            raise ValueError("invalid also_sources at item {}".format(index + 1))
        stats["missing_author"] += not bool(item["author"])
        stats["missing_chapter"] += not bool(item["chapter"])
        stats["additional_attributions"] += len(item["also_sources"])
        attribution_ids = {(item["book_id"], item["chapter_uid"], item["bookmark_id"])}
        for attribution in item["also_sources"]:
            if not isinstance(attribution, dict) or set(attribution) != SOURCE_FIELDS:
                raise ValueError("invalid additional attribution at item {}".format(index + 1))
            if not attribution["source"] or attribution["source"].lower() == "weread":
                raise ValueError("missing additional book title at item {}".format(index + 1))
            if not all(isinstance(attribution[field], str)
                       and len(attribution[field]) <= 2000 for field in SOURCE_FIELDS):
                raise ValueError("invalid additional attribution metadata type")
            identity = (
                attribution["book_id"], attribution["chapter_uid"],
                attribution["bookmark_id"],
            )
            if not identity[0] or identity in attribution_ids:
                raise ValueError("invalid or duplicate additional attribution identity")
            attribution_ids.add(identity)

    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=DATA_FILE)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    try:
        stats = validate(args.file)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("WeRead dataset validation failed: {}".format(type(exc).__name__))
        return 1

    print("WeRead dataset validated: quotes={} missing_author={} missing_chapter={} additional_attributions={}".format(
        stats["quotes"], stats["missing_author"], stats["missing_chapter"],
        stats["additional_attributions"]))
    output_path = args.github_output
    if output_path is None and os.environ.get("GITHUB_OUTPUT"):
        output_path = Path(os.environ["GITHUB_OUTPUT"])
    if output_path:
        with output_path.open("a", encoding="utf-8") as output:
            for key, value in stats.items():
                output.write("{}={}\n".format(key, value))
    return 0


if __name__ == "__main__":
    sys.exit(main())
