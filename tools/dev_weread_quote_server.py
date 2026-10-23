#!/usr/bin/env python3
"""Loopback-only single-quote API for local Hugo preview."""
import json
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from validate_weread_quotes import validate


ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "weread_quotes.json"
HOST = "127.0.0.1"
PORT = 8765
ALLOWED_ORIGINS = {
    "http://localhost:1313",
    "http://127.0.0.1:1313",
}
RESPONSE_FIELDS = ("source_type", "text", "source", "author", "chapter")


def load_quotes(path):
    validate(path)
    with path.open("r", encoding="utf-8") as source:
        records = json.load(source)
    return tuple(
        {field: record[field] for field in RESPONSE_FIELDS}
        for record in records
    )


def random_quote(records):
    if not records:
        raise ValueError("dataset_unavailable")
    return secrets.choice(records)


class QuoteHandler(BaseHTTPRequestHandler):
    server_version = "WeReadLocalQuote/1"
    sys_version = ""

    def log_message(self, _format, *_args):
        return

    def send_json(self, status, payload, origin=None):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        origin = self.headers.get("Origin", "")
        if origin not in ALLOWED_ORIGINS:
            self.send_json(403, {"error": "origin_not_allowed"})
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Accept")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Vary", "Origin")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self):
        if self.path.split("?", 1)[0] != "/public/quote":
            self.send_json(404, {"error": "not_found"})
            return
        origin = self.headers.get("Origin", "")
        if origin and origin not in ALLOWED_ORIGINS:
            self.send_json(403, {"error": "origin_not_allowed"})
            return
        try:
            quote = random_quote(self.server.quotes)
        except ValueError:
            self.send_json(503, {"error": "quote_unavailable"}, origin if origin else None)
            return
        self.send_json(200, quote, origin if origin else None)

    def do_POST(self):
        self.send_json(405, {"error": "method_not_allowed"})


def main():
    try:
        quotes = load_quotes(DATA_FILE)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        quotes = ()
        print("本地 WeRead 数据不可用: {}".format(type(exc).__name__), file=sys.stderr)
    server = ThreadingHTTPServer((HOST, PORT), QuoteHandler)
    server.daemon_threads = True
    server.quotes = quotes
    print("本地 WeRead 单条句子服务已启动: http://{}:{}/public/quote".format(HOST, PORT))
    if quotes:
        print("已加载并校验 {} 条候选记录。".format(len(quotes)))
    print("只监听回环地址；按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n本地 WeRead 单条句子服务已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
