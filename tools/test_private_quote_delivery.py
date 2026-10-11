#!/usr/bin/env python3
"""Offline privacy checks for homepage and private WeRead dataset delivery."""
import json
import unittest
from pathlib import Path

from publish_weread_quotes import MAX_CHUNK_BYTES, api_base, encode_records, make_chunks


ROOT = Path(__file__).resolve().parents[1]


class PrivateQuoteDeliveryTests(unittest.TestCase):
    def test_home_template_does_not_load_the_complete_weread_file(self):
        template = (ROOT / "layouts" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "quotes.js").read_text(encoding="utf-8")
        self.assertNotIn("site.Data.weread_quotes", template)
        self.assertNotIn("data/weread_quotes.json", template)
        self.assertNotIn("weread_quotes.json", script)
        self.assertNotIn("data/weread_quotes.json", script)
        self.assertIn('dict "manual" $manualQuotes | jsonify', template)
        self.assertNotIn('"weread" $wereadQuotes', template)

    def test_workflow_uploads_only_to_worker_and_never_commits_dataset(self):
        workflow = (ROOT / ".github" / "workflows" / "sync-weread.yml").read_text(encoding="utf-8")
        self.assertIn('output="$RUNNER_TEMP/weread_quotes.json"', workflow)
        self.assertIn('--output "$output"', workflow)
        self.assertIn("publish_weread_quotes.py", workflow)
        self.assertNotIn("git add", workflow)
        self.assertNotIn("git commit", workflow)
        self.assertNotIn("git push", workflow)
        self.assertNotIn("WEREAD_PUBLISH_TOKEN", workflow)
        self.assertIn("contents: read", workflow)
        self.assertNotIn("actions: read", workflow)
        self.assertNotIn("Verify required sync secrets", workflow)
        self.assertIn("REPORT_URL: ${{ vars.WEREAD_SYNC_REPORT_URL }}", workflow)

    def test_chunks_are_bounded_and_contain_only_synthetic_records(self):
        synthetic = [{
            "text": "合成测试内容" * 1500,
            "source_type": "weread",
            "source": "Synthetic Book",
            "author": "",
            "chapter": "",
            "book_id": "synthetic-id",
            "chapter_uid": "",
            "bookmark_id": "synthetic-mark-{}".format(index),
            "also_sources": [],
        } for index in range(8)]
        chunks = make_chunks(synthetic)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(sum(len(chunk) for chunk in chunks), len(synthetic))
        self.assertTrue(all(len(encode_records(chunk)) <= MAX_CHUNK_BYTES for chunk in chunks))
        self.assertTrue(all("synthetic" in json.dumps(chunk, ensure_ascii=False) for chunk in chunks))

    def test_worker_is_single_quote_read_only_api_and_d1_backed(self):
        worker = (ROOT / "worker" / "weread-sync" / "src" / "index.js").read_text(encoding="utf-8")
        self.assertIn('url.pathname === "/public/quote"', worker)
        self.assertIn("ORDER BY random() LIMIT 1", worker)
        self.assertIn("q.text, q.source, q.author, q.chapter", worker)
        public_section = worker[worker.index("async function publicQuote"):worker.index("async function uploadStart")]
        self.assertNotIn("private_json", public_section)
        self.assertNotIn("book_id", public_section)

    def test_private_database_migration_and_local_ignore_are_present(self):
        migration = (ROOT / "worker" / "weread-sync" / "migrations" / "0001_private_quotes.sql").read_text(encoding="utf-8")
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS weread_quotes", migration)
        self.assertIn("private_json TEXT NOT NULL", migration)
        self.assertIn("data/weread_quotes.json", ignore)

    def test_upload_origin_is_pinned_to_the_worker_configuration(self):
        publisher = (ROOT / "tools" / "publish_weread_quotes.py").read_text(encoding="utf-8")
        worker_config = (ROOT / "worker" / "weread-sync" / "wrangler.toml").read_text(encoding="utf-8")
        self.assertIn("configured_worker_origin()", publisher)
        self.assertIn("allow_redirects=False", publisher)
        self.assertIn("WORKER_ORIGIN =", worker_config)
        script = (ROOT / "static" / "quotes.js").read_text(encoding="utf-8")
        self.assertIn('wereadApiBase.includes("REPLACE_WITH_")', script)
        pinned = "https://weread-sync-console.account.workers.dev"
        self.assertEqual(api_base(pinned, pinned), pinned)
        for untrusted in (
            "https://attacker.workers.dev",
            "https://weread-sync-console.account.workers.dev.attacker.example",
            "http://weread-sync-console.account.workers.dev",
            "https://weread-sync-console.account.workers.dev:8443",
            "https://weread-sync-console.account.workers.dev/path",
        ):
            with self.subTest(origin=untrusted):
                with self.assertRaises(ValueError):
                    api_base(untrusted, pinned)

    def test_pages_workflow_rejects_private_dataset_before_and_after_build(self):
        workflow = (ROOT / ".github" / "workflows" / "hugo.yml").read_text(encoding="utf-8")
        self.assertIn("data/weread_quotes.json", workflow)
        self.assertIn("public/data/weread_quotes.json", workflow)


if __name__ == "__main__":
    unittest.main()
