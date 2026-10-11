#!/usr/bin/env python3
"""Safely verify GitHub-to-Worker credential bindings without syncing data."""
import argparse
import os
import re
import sys
import tomllib
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)


ROOT = Path(__file__).resolve().parents[1]
WORKER_CONFIG = ROOT / "worker" / "weread-sync" / "wrangler.toml"
ENDPOINTS = {
    "upload": ("/internal/upload/start", "WEREAD_UPLOAD_SECRET"),
    "report": ("/internal/report", "WEREAD_SYNC_REPORT_SECRET"),
}
WORKER_HOST_PATTERN = re.compile(
    r"^weread-sync-console\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.workers\.dev$",
    re.IGNORECASE,
)


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def open_without_redirects(request, timeout):
    return build_opener(RejectRedirects()).open(request, timeout=timeout)


def configured_worker_origin():
    with WORKER_CONFIG.open("rb") as source:
        config = tomllib.load(source)
    origin = config.get("vars", {}).get("WORKER_ORIGIN", "")
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.port
            or parsed.username or parsed.password or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment
            or not WORKER_HOST_PATTERN.fullmatch(parsed.hostname)):
        raise ValueError("invalid configured Worker origin")
    return origin.rstrip("/")


def check_endpoint(name, secret, origin, opener=open_without_redirects):
    path, _ = ENDPOINTS[name]
    if not secret:
        return None
    request = Request(
        origin + path,
        data=b"{}",
        method="POST",
        headers={
            "Authorization": "Bearer " + secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with opener(request, timeout=15) as response:
            return response.status
    except HTTPError as error:
        error.close()
        return error.code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("interface", choices=ENDPOINTS)
    name = parser.parse_args().interface
    _, secret_name = ENDPOINTS[name]
    secret = os.environ.get(secret_name, "")
    try:
        origin = configured_worker_origin()
        status = check_endpoint(name, secret, origin)
    except Exception:
        status = None

    passed = status == 400
    rendered_status = str(status) if status is not None else "N/A"
    print("{} HTTP {} {}".format(name, rendered_status, "PASS" if passed else "FAIL"))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
