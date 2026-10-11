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
MAX_RECORDS = 20000
ECMASCRIPT_TRIM_CHARS = (
    "\u0009\u000a\u000b\u000c\u000d\u0020\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000\ufeff"
)


def worker_length(value):
    return len(value.encode("utf-16-le", errors="surrogatepass")) // 2


def valid_text(value, max_length):
    return (isinstance(value, str)
            and bool(value.strip(ECMASCRIPT_TRIM_CHARS))
            and worker_length(value) <= max_length
            and not any(
                ord(char) <= 8 or ord(char) in (11, 12) or 14 <= ord(char) <= 31
                for char in value
            ))


def fail(record, field, reason="invalid"):
    raise ValueError("record {} field {}: {}".format(record, field, reason))


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
    if len(items) > MAX_RECORDS:
        fail(MAX_RECORDS + 1, "records", "record limit exceeded")
    for index, item in enumerate(items):
        record = index + 1
        if not isinstance(item, dict) or set(item) != QUOTE_FIELDS:
            fail(record, "schema")
        if item["source_type"] != "weread":
            fail(record, "source_type")
        if not valid_text(item["text"], 20000):
            fail(record, "text")
        if item["text"] in seen_texts:
            fail(record, "text", "duplicate quote text")
        seen_texts.add(item["text"])
        if not valid_text(item["source"], 2000) or item["source"].lower() == "weread":
            fail(record, "source", "missing real book title")
        for field in ("author", "chapter"):
            if not isinstance(item[field], str) or worker_length(item[field]) > 2000:
                fail(record, field)
        if not valid_text(item["book_id"], 512):
            fail(record, "book_id", "missing book identifier")
        for field in ("chapter_uid", "bookmark_id"):
            if not isinstance(item[field], str) or worker_length(item[field]) > 512:
                fail(record, field)
        if not isinstance(item["also_sources"], list) or len(item["also_sources"]) > 100:
            fail(record, "also_sources")
        stats["missing_author"] += not bool(item["author"])
        stats["missing_chapter"] += not bool(item["chapter"])
        stats["additional_attributions"] += len(item["also_sources"])
        attribution_ids = {(item["book_id"], item["chapter_uid"], item["bookmark_id"])}
        for attribution in item["also_sources"]:
            if not isinstance(attribution, dict) or set(attribution) != SOURCE_FIELDS:
                fail(record, "also_sources.schema")
            if (not valid_text(attribution["source"], 2000)
                    or attribution["source"].lower() == "weread"):
                fail(record, "also_sources.source", "missing real book title")
            for field in ("author", "chapter"):
                if (not isinstance(attribution[field], str)
                        or worker_length(attribution[field]) > 2000):
                    fail(record, "also_sources." + field)
            if not valid_text(attribution["book_id"], 512):
                fail(record, "also_sources.book_id")
            for field in ("chapter_uid", "bookmark_id"):
                if (not isinstance(attribution[field], str)
                        or worker_length(attribution[field]) > 512):
                    fail(record, "also_sources." + field)
            identity = (
                attribution["book_id"], attribution["chapter_uid"],
                attribution["bookmark_id"],
            )
            if identity in attribution_ids:
                fail(record, "also_sources", "duplicate source identity")
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
        message = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print("WeRead dataset validation failed: {}".format(message))
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
