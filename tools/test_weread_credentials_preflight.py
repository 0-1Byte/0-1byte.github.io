#!/usr/bin/env python3
"""Offline tests for the credential preflight request shape and status checks."""
import unittest
from urllib.error import HTTPError
from pathlib import Path

from weread_credentials_preflight import USER_AGENT, check_endpoint

ROOT = Path(__file__).resolve().parents[1]


class Response:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class CredentialPreflightTests(unittest.TestCase):
    def test_upload_preflight_sends_only_empty_authenticated_manifest(self):
        captured = {}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["method"] = request.method
            captured["body"] = request.data
            captured["authorization"] = request.get_header("Authorization")
            captured["content_type"] = request.get_header("Content-type")
            captured["user_agent"] = request.get_header("User-agent")
            captured["timeout"] = timeout
            return Response(400)

        status = check_endpoint("upload", "synthetic-secret", "https://worker.example", opener)
        self.assertEqual(status, 400)
        self.assertEqual(captured["url"], "https://worker.example/internal/upload/start")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["body"], b"{}")
        self.assertEqual(captured["authorization"], "Bearer synthetic-secret")
        self.assertEqual(captured["content_type"], "application/json")
        self.assertEqual(captured["user_agent"], USER_AGENT)
        self.assertEqual(captured["timeout"], 15)

    def test_report_preflight_recognizes_http_error_status_without_reading_body(self):
        def opener(_request, timeout):
            raise HTTPError(
                "https://worker.example/internal/report",
                401,
                "unauthorized",
                None,
                None,
            )

        self.assertEqual(
            check_endpoint("report", "synthetic-secret", "https://worker.example", opener),
            401,
        )

    def test_report_preflight_sends_authenticated_empty_report(self):
        captured = {}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["method"] = request.method
            captured["body"] = request.data
            captured["authorization"] = request.get_header("Authorization")
            captured["user_agent"] = request.get_header("User-agent")
            return Response(400)

        self.assertEqual(
            check_endpoint("report", "synthetic-secret", "https://worker.example", opener),
            400,
        )
        self.assertEqual(captured["url"], "https://worker.example/internal/report")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["body"], b"{}")
        self.assertTrue(captured["authorization"].startswith("Bearer "))
        self.assertEqual(captured["user_agent"], USER_AGENT)

    def test_only_expected_authenticated_invalid_body_status_passes(self):
        def response_with(status):
            return lambda _request, timeout: Response(status)

        self.assertEqual(
            check_endpoint("upload", "synthetic-secret", "https://worker.example",
                           response_with(400)),
            400,
        )
        self.assertEqual(
            check_endpoint("upload", "synthetic-secret", "https://worker.example",
                           response_with(200)),
            200,
        )

    def test_sync_report_callback_logs_http_status_without_reading_response(self):
        workflow = (ROOT / ".github" / "workflows" / "sync-weread.yml").read_text(
            encoding="utf-8",
        )
        self.assertIn("except urllib.error.HTTPError as error:", workflow)
        self.assertIn(
            'print("Console summary callback failed: HTTP {}".format(error.code))',
            workflow,
        )
        self.assertIn(
            '"User-Agent": "0-1byte-weread-sync/1.0 (+https://0-1byte.github.io/)"',
            workflow,
        )
        self.assertNotIn("error.read()", workflow)


if __name__ == "__main__":
    unittest.main()
