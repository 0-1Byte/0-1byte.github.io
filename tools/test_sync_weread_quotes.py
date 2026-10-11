#!/usr/bin/env python3
"""Offline tests for the WeRead quote synchronizer (Python 3.7 compatible)."""
import json
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_weread_quotes as sync
import weread_gateway
from weread_gateway import WereadError


class FakeResponse(object):
    def __init__(self, status_code=200, content=b'{"errcode":0,"books":[],"hasMore":0}'):
        self.status_code = status_code
        self.content = content
        self.closed = False

    def close(self):
        self.closed = True


class FakeSession(object):
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.trust_env = True

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class SyncTests(unittest.TestCase):
    def test_text_normalization_and_empty_filter(self):
        item = sync.as_quote_item({"bookmarkId": "id", "markText": "  中文，标点。\r\n第二行  "})
        self.assertEqual(item["text"], "中文，标点。\n第二行")
        self.assertIsNone(sync.as_quote_item({"markText": " \n\t "}))

    def test_dedupe_prefers_stable_id_and_falls_back_to_text(self):
        items = [
            sync.as_quote_item({"bookmarkId": "same", "markText": "重复句"}),
            sync.as_quote_item({"bookmarkId": "same", "markText": "另一句"}),
            sync.as_quote_item({"markText": "文本去重"}),
            sync.as_quote_item({"markText": "文本去重"}),
        ]
        result = sync.dedupe(items)
        self.assertEqual([item["text"] for item in result], ["重复句", "文本去重"])
        self.assertTrue(all(
            item["source_type"] == "weread"
            and set(item.keys()) == {
                "text", "source_type", "source", "author", "chapter",
                "book_id", "chapter_uid", "bookmark_id", "also_sources",
            }
            for item in result
        ))

    def test_book_and_chapter_metadata_are_mapped_without_guessing(self):
        book = {
            "bookId": "book-a",
            "book": {"title": "真实书名", "author": "真实作者"},
        }
        detail = {"chapters": [
            {"chapterUid": "chapter-1", "title": "第一章"},
            {"chapterUid": "chapter-2", "title": "第二章"},
        ]}
        chapters, ambiguous = sync.chapter_title_map(detail)
        item = sync.as_quote_item({
            "bookId": "book-a",
            "bookmarkId": "mark-a",
            "chapterUid": "chapter-2",
            "markText": "章节映射测试",
        }, book, chapters)
        self.assertEqual(item["source_type"], "weread")
        self.assertEqual(item["source"], "真实书名")
        self.assertEqual(item["author"], "真实作者")
        self.assertEqual(item["chapter"], "第二章")
        self.assertEqual(item["book_id"], "book-a")
        self.assertEqual(item["chapter_uid"], "chapter-2")
        self.assertEqual(item["bookmark_id"], "mark-a")
        self.assertEqual(ambiguous, set())

        missing = sync.as_quote_item({
            "bookId": "book-a",
            "bookmarkId": "mark-b",
            "chapterUid": "missing-chapter",
            "markText": "缺失章节不编造",
        }, book, chapters)
        self.assertEqual(missing["chapter"], "")

    def test_duplicate_text_keeps_other_book_sources(self):
        first = sync.as_quote_item({
            "bookId": "book-a", "bookmarkId": "mark-a",
            "chapterUid": "chapter-a", "markText": "同一句",
        }, {"bookId": "book-a", "book": {"title": "书甲", "author": "作者甲"}},
            {"chapter-a": "甲章"})
        second = sync.as_quote_item({
            "bookId": "book-b", "bookmarkId": "mark-b",
            "chapterUid": "chapter-b", "markText": "同一句",
        }, {"bookId": "book-b", "book": {"title": "书乙", "author": "作者乙"}},
            {"chapter-b": "乙章"})
        result = sync.dedupe([first, second])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source"], "书甲")
        self.assertEqual(result[0]["also_sources"], [{
            "source": "书乙", "author": "作者乙", "chapter": "乙章",
            "book_id": "book-b", "chapter_uid": "chapter-b",
            "bookmark_id": "mark-b",
        }])

    def test_duplicate_chapter_ids_with_conflicting_titles_are_unmapped(self):
        chapters, ambiguous = sync.chapter_title_map({"chapters": [
            {"chapterUid": "dup", "title": "标题甲"},
            {"chapterUid": "dup", "title": "标题乙"},
        ]})
        self.assertNotIn("dup", chapters)
        self.assertEqual(ambiguous, {"dup"})

    def test_notebook_pagination_uses_last_sort_until_has_more_false(self):
        pages = [
            {"books": [{"sort": 10, "bookId": "private-id"}], "hasMore": 1},
            {"books": [{"sort": 5, "bookId": "private-id-2"}], "hasMore": 0},
        ]
        calls = []

        def fake_call(endpoint, key, api_name, params, **kwargs):
            calls.append((api_name, dict(params)))
            return pages.pop(0)

        with mock.patch.object(sync, "call", side_effect=fake_call):
            books = list(sync.iter_notebooks("key", "endpoint", count=1))
        self.assertEqual(len(books), 2)
        self.assertEqual(calls[0][1], {"count": 1})
        self.assertEqual(calls[1][1], {"count": 1, "lastSort": 10})

    def test_non_advancing_cursor_is_an_error(self):
        page = {"books": [{"sort": 10}], "hasMore": 1}
        with mock.patch.object(sync, "call", return_value=page):
            iterator = sync.iter_notebooks("key", "endpoint", count=1)
            next(iterator)
            with self.assertRaises(sync.SyncError):
                next(iterator)

    def test_multi_book_merge_and_missing_or_empty_mark_text(self):
        responses = [
            {"books": [
                {"sort": 10, "bookId": "a", "noteCount": 2,
                 "book": {"title": "书甲", "author": "作者甲"}},
                {"sort": 9, "bookId": "b", "noteCount": 1,
                 "book": {"title": "书乙", "author": "作者乙"}},
            ], "hasMore": 0},
            {"updated": [
                {"bookmarkId": "1", "markText": "甲\n乙"},
                {"bookmarkId": "2", "markText": "   "},
            ], "chapters": [{"chapterUid": "u1", "title": "第一章"}]},
            {"updated": [
                {"bookmarkId": "3", "markText": "甲\n乙"},
                {"bookmarkId": "4", "markText": "第二句"},
            ], "chapters": [{"chapterUid": "u2", "title": "第二章"}]},
        ]
        calls = []

        def fake_call(endpoint, key, api_name, params, **kwargs):
            calls.append(api_name)
            return responses.pop(0)

        with mock.patch.object(sync, "call", side_effect=fake_call), \
                mock.patch.object(sync.time, "sleep"):
            items, stats = sync.fetch_all("key", "endpoint", count=10)
        self.assertEqual([item["text"] for item in items], ["甲\n乙", "第二句"])
        self.assertEqual(stats["notebooks"], 2)
        self.assertEqual(stats["eligible_books"], 2)
        self.assertEqual(stats["read_books"], 2)
        self.assertEqual(calls.count("/book/bookmarklist"), 2)
        self.assertEqual(items[0]["also_sources"][0]["source"], "书乙")

    def test_failed_api_and_bad_response_fail_closed(self):
        with mock.patch.object(sync, "call", side_effect=WereadError("no details")):
            with self.assertRaises(sync.SyncError) as raised:
                list(sync.iter_notebooks("key", "endpoint", count=1))
        self.assertEqual(raised.exception.stage, "notebooks")

        with mock.patch.object(sync, "call", return_value={"books": [], "hasMore": 1}):
            with self.assertRaises(sync.SyncError) as raised:
                list(sync.iter_notebooks("key", "endpoint", count=1))
        self.assertEqual(raised.exception.stage, "notebooks_pagination")

    def test_gateway_rejects_nonzero_errcode_without_retry(self):
        session = FakeSession([
            FakeResponse(content=b'{"errcode":-2013,"errmsg":"private message"}')
        ])
        with mock.patch.object(weread_gateway, "_SESSION", session):
            with self.assertRaises(WereadError) as raised:
                weread_gateway.call(
                    weread_gateway.DEFAULT_ENDPOINT,
                    "wrk-test-key",
                    "/user/notebooks",
                    {"count": 1},
                )
        self.assertEqual(raised.exception.kind, "api_error")
        self.assertEqual(raised.exception.errcode, -2013)
        self.assertEqual(len(session.calls), 1)
        self.assertTrue(session.calls[0][1]["verify"])

    def test_gateway_preserves_http_error_status_and_does_not_retry(self):
        session = FakeSession([
            FakeResponse(401, b'{"errcode":-2013,"errmsg":"sensitive"}')
        ])
        diagnostics = []
        with mock.patch.object(weread_gateway, "_SESSION", session):
            with self.assertRaises(WereadError) as raised:
                weread_gateway.call(
                    weread_gateway.DEFAULT_ENDPOINT,
                    "wrk-test-key",
                    "/user/notebooks",
                    {"count": 1},
                    diagnostics=diagnostics.append,
                )
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(raised.exception.kind, "http")
        self.assertEqual(raised.exception.http_status, 401)
        self.assertEqual(raised.exception.errcode, -2013)
        self.assertEqual(diagnostics[0]["http_status"], 401)
        self.assertEqual(diagnostics[0]["exception_type"], "HTTPError")
        self.assertNotIn("sensitive", str(raised.exception))

    def test_gateway_retries_transient_network_failure_a_bounded_number_of_times(self):
        session = FakeSession([
            weread_gateway.requests.exceptions.ConnectionError("offline"),
            FakeResponse(),
        ])
        diagnostics = []
        with mock.patch.object(weread_gateway, "_SESSION", session), \
                mock.patch.object(weread_gateway.time, "sleep"):
            result = weread_gateway.call(
                weread_gateway.DEFAULT_ENDPOINT,
                "wrk-test-key",
                "/user/notebooks",
                {"count": 1},
                diagnostics=diagnostics.append,
            )
        self.assertEqual(result["errcode"], 0)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual([entry["attempt"] for entry in diagnostics], [1, 2])
        self.assertIsNone(diagnostics[0]["http_status"])
        self.assertEqual(diagnostics[0]["exception_type"], "ConnectionError")
        self.assertEqual(diagnostics[1]["http_status"], 200)

    def test_gateway_retries_http_protocol_transport_errors_and_reports_attempts(self):
        session = FakeSession([
            weread_gateway.requests.exceptions.ConnectionError("disconnected"),
            FakeResponse(),
        ])
        with mock.patch.object(weread_gateway, "_SESSION", session), \
                mock.patch.object(weread_gateway.time, "sleep"):
            result = weread_gateway.call(
                weread_gateway.DEFAULT_ENDPOINT,
                "wrk-test-key",
                "/user/notebooks",
                {"count": 1},
            )
        self.assertEqual(result["errcode"], 0)
        self.assertEqual(len(session.calls), 2)

    def test_gateway_reports_exhausted_timeout_without_sensitive_message(self):
        session = FakeSession([
            weread_gateway.requests.exceptions.Timeout("private network details"),
            weread_gateway.requests.exceptions.Timeout("private network details"),
        ])
        with mock.patch.object(weread_gateway, "_SESSION", session), \
                mock.patch.object(weread_gateway.time, "sleep"):
            with self.assertRaises(WereadError) as raised:
                weread_gateway.call(
                    weread_gateway.DEFAULT_ENDPOINT,
                    "wrk-test-key",
                    "/user/notebooks",
                    {"count": 1},
                    retries=1,
                )
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(raised.exception.kind, "network")
        self.assertEqual(raised.exception.attempts, 2)
        self.assertEqual(raised.exception.transport_type, "Timeout")
        self.assertGreaterEqual(raised.exception.elapsed_seconds, 0)
        self.assertNotIn("private network details", str(raised.exception))

    def test_file_not_found_is_not_retried_or_classified_as_network(self):
        diagnostics = []
        failure = FileNotFoundError(
            2, "missing file", "Bearer secret-token wrk-test-key https://private.example/path"
        )
        session = FakeSession([failure])
        with mock.patch.object(weread_gateway, "_SESSION", session):
            with self.assertRaises(WereadError) as raised:
                weread_gateway.call(
                    weread_gateway.DEFAULT_ENDPOINT,
                    "wrk-test-key",
                    "/book/bookmarklist",
                    {"bookId": "synthetic"},
                    diagnostics=diagnostics.append,
                )
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(raised.exception.kind, "transport_unclassified")
        self.assertEqual(raised.exception.exception_errno, 2)
        self.assertEqual(diagnostics[0]["exception_type"], "FileNotFoundError")
        self.assertNotIn("secret-token", diagnostics[0]["exception_message"])
        self.assertNotIn("wrk-test-key", diagnostics[0]["exception_message"])
        self.assertNotIn("private.example", diagnostics[0]["exception_message"])
        self.assertTrue(diagnostics[0]["file"])
        self.assertIsNotNone(diagnostics[0]["line"])

    def test_tls_certificate_error_is_not_retried(self):
        session = FakeSession([
            weread_gateway.requests.exceptions.SSLError(
                "certificate verify failed: self signed certificate"
            )
        ])
        with mock.patch.object(weread_gateway, "_SESSION", session):
            with self.assertRaises(WereadError) as raised:
                weread_gateway.call(
                    weread_gateway.DEFAULT_ENDPOINT,
                    "wrk-test-key",
                    "/user/notebooks",
                    {"count": 1},
                )
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(raised.exception.kind, "tls_certificate")

    def test_tls_eof_is_bounded_retryable_connection_error(self):
        session = FakeSession([
            weread_gateway.requests.exceptions.SSLError(
                "EOF occurred in violation of protocol"
            ),
            FakeResponse(),
        ])
        with mock.patch.object(weread_gateway, "_SESSION", session), \
                mock.patch.object(weread_gateway.time, "sleep"):
            result = weread_gateway.call(
                weread_gateway.DEFAULT_ENDPOINT,
                "wrk-test-key",
                "/user/notebooks",
                {"count": 1},
            )
        self.assertEqual(result["errcode"], 0)
        self.assertEqual(len(session.calls), 2)

    def test_duplicate_notebook_ids_fail_before_bookmark_requests(self):
        pages = [
            {"books": [
                {"sort": 10, "bookId": "private-book", "noteCount": 1},
            ], "hasMore": 1},
            {"books": [
                {"sort": 9, "bookId": "private-book", "noteCount": 1},
            ], "hasMore": 0},
        ]
        calls = []

        def fake_call(endpoint, key, api_name, params, **kwargs):
            calls.append(api_name)
            return pages.pop(0)

        with mock.patch.object(sync, "call", side_effect=fake_call), \
                mock.patch.object(sync.time, "sleep"):
            with self.assertRaises(sync.SyncError) as raised:
                sync.fetch_all("key", "endpoint", count=1)
        self.assertEqual(raised.exception.stage, "notebooks_pagination")
        self.assertEqual(calls.count("/book/bookmarklist"), 0)

    def test_failure_report_contains_safe_request_diagnostics(self):
        failure = WereadError(
            "sanitized",
            kind="network",
            attempts=3,
            elapsed_seconds=12.5,
        )
        failure.transport_type = "TimeoutError"
        failure.safe_exception_message = "timed out at [URL]"
        failure.exception_errno = 110
        failure.exception_winerror = 10060
        failure.exception_function = "urlopen"
        failure.exception_file = "request.py"
        failure.exception_line = 123

        def fail_fetch(*args, **kwargs):
            try:
                raise failure
            except WereadError as exc:
                raise sync.SyncError(
                    "request failed",
                    "notebooks",
                    "/user/notebooks",
                ) from exc

        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["sync_weread_quotes.py", "--dry-run"]), \
                mock.patch.object(sync, "load_key", return_value=("wrk-test-key", "endpoint")), \
                mock.patch.object(sync, "fetch_all", side_effect=fail_fetch), \
                redirect_stdout(output):
            self.assertEqual(sync.main(), 3)
        report = output.getvalue()
        self.assertIn("阶段=notebooks", report)
        self.assertIn("请求路径=/user/notebooks", report)
        self.assertIn("尝试次数=3", report)
        self.assertIn("异常类型=TimeoutError", report)
        self.assertIn("耗时秒=12.500", report)
        self.assertIn("异常消息=timed out at [URL]", report)
        self.assertIn("errno=110 winerror=10060", report)
        self.assertIn("出错位置=request.py:urlopen:123", report)
        self.assertNotIn("wrk-test-key", report)

    def test_dry_run_never_writes_formal_file(self):
        stats = {
            "notebooks": 2,
            "eligible_books": 1,
            "read_books": 1,
            "nonempty_highlights": 1,
            "quotes": 1,
            "unmapped_chapters": 0,
            "ambiguous_chapter_ids": 0,
        }
        with mock.patch.object(sys, "argv", ["sync_weread_quotes.py", "--dry-run"]), \
                mock.patch.object(sync, "load_key", return_value=("wrk-test-key", "endpoint")), \
                mock.patch.object(
                    sync,
                    "fetch_all",
                    return_value=([{
                        "text": "合成测试", "source_type": "weread", "source": "书名",
                        "author": "", "chapter": "", "book_id": "", "chapter_uid": "",
                        "bookmark_id": "", "also_sources": [],
                    }], stats),
                ), \
                mock.patch.object(sync, "write_json") as write_json, \
                redirect_stdout(io.StringIO()):
            self.assertEqual(sync.main(), 0)
        write_json.assert_not_called()

    def test_atomic_replace_failure_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "quotes.json"
            temporary = Path(directory) / "quotes.json.tmp"
            output.write_text('[{"text":"old","source_type":"weread"}]\n', encoding="utf-8")
            with mock.patch.object(sync, "OUT_PATH", output), \
                    mock.patch.object(sync, "TEMP_PATH", temporary), \
                    mock.patch.object(sync.os, "replace", side_effect=OSError("blocked")):
                with self.assertRaises(OSError):
                    sync.write_json([{
                        "text": "new", "source_type": "weread", "source": "书名",
                        "author": "", "chapter": "", "book_id": "", "chapter_uid": "",
                        "bookmark_id": "", "also_sources": [],
                    }])
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))[0]["text"], "old")
            self.assertFalse(temporary.exists())


if __name__ == "__main__":
    unittest.main()
