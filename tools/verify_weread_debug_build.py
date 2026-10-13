#!/usr/bin/env python3
"""Fail the Pages build if the standalone WeRead diagnostic output is incomplete."""
import argparse
from html.parser import HTMLParser
from pathlib import Path


class PageProbe(HTMLParser):
    def __init__(self):
        super().__init__()
        self.panel_hidden = None
        self.resources = []
        self.language = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "html":
            self.language = values.get("lang")
        if values.get("id") == "weread-debug":
            self.panel_hidden = "hidden" in values
        resource = values.get("src") or values.get("href")
        if resource:
            self.resources.append(resource)


def require(condition, message):
    if not condition:
        raise SystemExit("WeRead diagnostic build verification failed: " + message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-dir", type=Path, required=True)
    args = parser.parse_args()
    public_dir = args.public_dir.resolve()
    home_path = public_dir / "index.html"
    diagnostic_path = public_dir / "weread-debug" / "index.html"
    require(home_path.is_file(), "built homepage index.html is missing")
    require(diagnostic_path.is_file(), "built weread-debug/index.html is missing")

    home = home_path.read_text(encoding="utf-8")
    require('id="weread-debug"' in home or "id=weread-debug" in home,
            "homepage diagnostic panel is missing")
    require("quotes.js?v=12" in home, "homepage does not reference quotes.js?v=12")
    require("quotes-debug.css" in home, "homepage diagnostic CSS is missing")

    page = diagnostic_path.read_text(encoding="utf-8")
    probe = PageProbe()
    probe.feed(page)
    require(probe.language == "zh-CN", "standalone page language is not zh-CN")
    require(probe.panel_hidden is False,
            "standalone diagnostic panel is missing or initially hidden")
    require("诊断脚本尚未运行" in page,
            "static page does not expose the no-script initial state")
    require("/public/quote" not in page,
            "endpoint must be assembled from the shared Worker config")

    config_index = next(
        (index for index, resource in enumerate(probe.resources)
         if resource == "/admin/weread-sync/config.js"),
        None,
    )
    script_index = next(
        (index for index, resource in enumerate(probe.resources)
         if resource == "/weread-debug.js"),
        None,
    )
    require(config_index is not None and script_index is not None
            and config_index < script_index,
            "Worker config must load before the standalone diagnostic script")
    for resource in ("/weread-debug.js", "/weread-debug.css",
                     "/admin/weread-sync/config.js"):
        require((public_dir / resource.lstrip("/")).is_file(),
                "built resource is missing: " + resource)

    script = (public_dir / "weread-debug.js").read_text(encoding="utf-8")
    require("home-focus" not in script and "quotes.js" not in script,
            "standalone script must not depend on homepage quote code")
    require("/public/quote" in script,
            "standalone script does not request the public quote endpoint")
    print("WeRead diagnostic build verification passed.")


if __name__ == "__main__":
    main()
