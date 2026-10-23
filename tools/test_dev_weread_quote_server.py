#!/usr/bin/env python3
"""Offline tests for the loopback-only WeRead preview endpoint."""
import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import dev_weread_quote_server as dev_server


def synthetic_quote(index):
    return {
        "text": "synthetic quote {}".format(index),
        "source_type": "weread",
        "source": "Synthetic Book",
        "author": "Synthetic Author",
        "chapter": "Synthetic Chapter",
        "book_id": "book-{}".format(index),
        "chapter_uid": "chapter-{}".format(index),
        "bookmark_id": "bookmark-{}".format(index),
        "also_sources": [],
    }


class LocalQuoteServerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_path = Path(self.temp_dir.name) / "quotes.json"
        self.data_path.write_text(
            json.dumps([synthetic_quote(1), synthetic_quote(2)]),
            encoding="utf-8",
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), dev_server.QuoteHandler)
        self.server.quotes = dev_server.load_quotes(self.data_path)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = "http://127.0.0.1:{}".format(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def test_server_binds_to_loopback_and_defines_loopback_default(self):
        self.assertEqual(dev_server.HOST, "127.0.0.1")
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_each_selection_validates_and_draws_from_the_full_dataset(self):
        with mock.patch.object(
            dev_server.secrets,
            "choice",
            side_effect=lambda records: records[-1],
        ) as choose:
            first = dev_server.random_quote(self.server.quotes)
            second = dev_server.random_quote(self.server.quotes)
        self.assertEqual(choose.call_count, 2)
        self.assertEqual(len(choose.call_args_list[0].args[0]), 2)
        self.assertEqual(first["text"], "synthetic quote 2")
        self.assertEqual(second["text"], "synthetic quote 2")

    def test_selection_does_not_revalidate_or_reload_dataset_each_request(self):
        with mock.patch.object(dev_server, "validate", side_effect=AssertionError):
            with mock.patch.object(dev_server.secrets, "choice", return_value=self.server.quotes[0]):
                result = dev_server.random_quote(self.server.quotes)
        self.assertEqual(result["text"], "synthetic quote 1")

    def test_get_returns_one_quote_with_only_public_fields(self):
        request = Request(
            self.base_url + "/public/quote",
            headers={"Origin": "http://localhost:1313"},
        )
        with urlopen(request, timeout=2) as response:
            result = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get("Cache-Control"), "no-store")
            self.assertEqual(
                response.headers.get("Access-Control-Allow-Origin"),
                "http://localhost:1313",
            )
        self.assertEqual(
            set(result),
            {"source_type", "text", "source", "author", "chapter"},
        )
        self.assertEqual(result["source_type"], "weread")
        self.assertTrue(result["text"].startswith("synthetic quote "))
        self.assertNotIn("book_id", result)
        self.assertNotIn("bookmark_id", result)
        self.assertNotIn("also_sources", result)
        self.assertNotIn("records", result)

    def test_only_allowed_preview_origins_receive_cors_access(self):
        request = Request(
            self.base_url + "/public/quote",
            headers={"Origin": "https://attacker.example"},
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 403)
        self.assertEqual(raised.exception.headers.get("Access-Control-Allow-Origin"), None)

    def test_invalid_or_empty_dataset_fails_without_data_in_response(self):
        self.server.quotes = ()
        with self.assertRaises(HTTPError) as raised:
            urlopen(self.base_url + "/public/quote", timeout=2)
        self.assertEqual(raised.exception.code, 503)
        self.assertEqual(raised.exception.read(), b'{"error":"quote_unavailable"}')

    def test_unknown_paths_and_mutating_methods_are_rejected(self):
        with self.assertRaises(HTTPError) as raised:
            urlopen(self.base_url + "/", timeout=2)
        self.assertEqual(raised.exception.code, 404)
        request = Request(self.base_url + "/public/quote", data=b"{}", method="POST")
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 405)


if __name__ == "__main__":
    unittest.main()
