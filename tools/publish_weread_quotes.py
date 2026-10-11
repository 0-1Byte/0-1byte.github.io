#!/usr/bin/env python3
"""Upload a validated private WeRead dataset to the fixed Worker API."""
import argparse
import json
import os
import re
import sys
import tomllib
import uuid
from pathlib import Path
from urllib.parse import urlparse

import requests

from validate_weread_quotes import validate

MAX_CHUNK_BYTES = 64 * 1024
MAX_RECORDS = 20000
MAX_DATASET_BYTES = 32 * 1024 * 1024
WORKER_CONFIG = Path(__file__).resolve().parents[1] / "worker" / "weread-sync" / "wrangler.toml"
WORKER_HOST_PATTERN = r"^weread-sync-console\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.workers\.dev$"


def encode_records(records):
    return json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def make_chunks(items):
    chunks = []
    current = []
    for item in items:
        candidate = current + [item]
        if len(encode_records(candidate)) > MAX_CHUNK_BYTES:
            if not current:
                raise ValueError("single record exceeds upload chunk limit")
            chunks.append(current)
            current = [item]
            if len(encode_records(current)) > MAX_CHUNK_BYTES:
                raise ValueError("single record exceeds upload chunk limit")
        else:
            current = candidate
    if current:
        chunks.append(current)
    if len(chunks) > 300:
        raise ValueError("dataset exceeds upload chunk limit")
    return chunks


def configured_worker_origin():
    with WORKER_CONFIG.open("rb") as config_file:
        config = tomllib.load(config_file)
    return config.get("vars", {}).get("WORKER_ORIGIN", "")


def api_base(value, expected_origin):
    parsed = urlparse(value)
    expected = urlparse(expected_origin)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.port
            or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment
            or expected.scheme != "https" or not expected.hostname or expected.port
            or expected.username or expected.password
            or expected.path not in ("", "/") or expected.query or expected.fragment
            or not re.fullmatch(WORKER_HOST_PATTERN, expected.hostname, re.IGNORECASE)
            or parsed.hostname.lower() != expected.hostname.lower()
            or value.rstrip("/") != expected_origin.rstrip("/")):
        raise ValueError("WEREAD_SYNC_API_BASE does not match the pinned workers.dev origin")
    return expected_origin.rstrip("/")


def safe_error(response):
    try:
        value = response.json().get("error", "")
    except (ValueError, AttributeError):
        return "http_error"
    if isinstance(value, str) and value.replace("_", "").isalnum():
        return value[:64]
    return "http_error"


def request(session, base, path, secret, body):
    try:
        response = session.post(
            base + path,
            data=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + secret,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=(8, 45),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise RuntimeError("transport_{}".format(type(exc).__name__)) from None
    if response.status_code not in (200, 201, 202):
        raise RuntimeError("http_{}_{}".format(response.status_code, safe_error(response)))
    try:
        result = response.json()
    except ValueError:
        raise RuntimeError("invalid_json_response") from None
    if not isinstance(result, dict) or result.get("accepted") is not True:
        raise RuntimeError("invalid_response")
    return result


def publish(path):
    api = api_base(
        os.environ.get("WEREAD_SYNC_API_BASE", ""),
        configured_worker_origin(),
    )
    secret = os.environ.get("WEREAD_UPLOAD_SECRET", "")
    if not secret:
        raise ValueError("WEREAD_UPLOAD_SECRET is not configured")
    stats = validate(path)
    if not 1 <= stats["quotes"] <= MAX_RECORDS:
        raise ValueError("dataset record count is outside the allowed range")
    if path.stat().st_size > MAX_DATASET_BYTES:
        raise ValueError("dataset exceeds the upload size limit")
    with path.open("r", encoding="utf-8") as source:
        items = json.load(source)
    chunks = make_chunks(items)
    upload_id = str(uuid.uuid4())
    session = requests.Session()
    session.trust_env = True
    started = False
    try:
        request(session, api, "/internal/upload/start", secret, {
            "upload_id": upload_id,
            "record_count": len(items),
            "chunk_count": len(chunks),
        })
        started = True
        for index, records in enumerate(chunks):
            request(session, api, "/internal/upload/chunk", secret, {
                "upload_id": upload_id,
                "chunk_index": index,
                "records": records,
            })
            print("上传私有数据批次: {}/{}".format(index + 1, len(chunks)))
        request(session, api, "/internal/upload/complete", secret, {
            "upload_id": upload_id,
        })
    except Exception:
        if started:
            try:
                request(session, api, "/internal/upload/abort", secret, {
                    "upload_id": upload_id,
                })
            except Exception:
                pass
        raise
    finally:
        session.close()
    print("私有数据上传并激活成功: records={} chunks={}".format(len(items), len(chunks)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, type=Path)
    args = parser.parse_args()
    try:
        publish(args.file)
    except Exception as exc:
        message = str(exc)
        if not message.startswith(("http_", "transport_", "invalid_",
                                   "WEREAD_", "dataset ", "single ", "missing_")):
            message = type(exc).__name__
        print("私有数据上传失败: {}".format(message))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
