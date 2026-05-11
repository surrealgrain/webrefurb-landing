#!/usr/bin/env python3
"""Check WebRefurb public-site deployment health.

Static mode checks a local site root. Live mode checks deployed URLs. The
checks intentionally stay small and deterministic so they can run as a release
gate without browser automation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


PUBLIC_PAGES = {
    "/": "en",
    "/ja/": "ja",
    "/pricing.html": "en",
    "/ja/pricing.html": "ja",
    "/demo/": "en",
    "/demo/ramen.html": "ja",
    "/demo/sushi.html": "ja",
}

BANNED_PUBLIC_TERMS = (
    "ordering system",
    "qr ordering system",
    "online ordering",
    "pos",
    "checkout",
    "place order",
    "submit order",
    "package_1_remote_30k",
    "package_2_printed_delivered_45k",
    "package_3_qr_menu_65k",
    "english ordering files",
    "counter-ready ordering kit",
    "live qr english menu",
    "lamination",
    "automation",
    "scraping",
)


class _HTMLAuditParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.html_lang = ""
        self.title = ""
        self._in_title = False
        self.canonical = ""
        self.og_title = False
        self.og_description = False
        self.images: list[str] = []
        self.links: list[str] = []
        self.visible_parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs):
        data = dict(attrs)
        if tag == "html":
            self.html_lang = str(data.get("lang") or "")
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style"}:
            self._skip += 1
        if tag == "link" and data.get("rel") == "canonical":
            self.canonical = str(data.get("href") or "")
        if tag == "meta" and data.get("property") == "og:title":
            self.og_title = True
        if tag == "meta" and data.get("property") == "og:description":
            self.og_description = True
        if tag == "img":
            src = str(data.get("src") or "")
            if src:
                self.images.append(src)
        if tag == "a":
            href = str(data.get("href") or "")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str):
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str):
        if self._in_title:
            self.title += data
        if not self._skip:
            self.visible_parts.append(data)

    @property
    def visible_text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.visible_parts)).strip()


def check_static(root: Path) -> dict:
    findings: list[dict] = []
    if _contains_underscore_public_paths(root) and not (root / ".nojekyll").exists():
        findings.append(_finding("/", "nojekyll_missing", "underscore asset paths require .nojekyll on GitHub Pages"))
    for path, expected_lang in PUBLIC_PAGES.items():
        html_path = _static_path(root, path)
        if not html_path.exists():
            findings.append(_finding(path, "missing_page", str(html_path)))
            continue
        html = html_path.read_text(encoding="utf-8")
        findings.extend(_audit_html(path, html, expected_lang=expected_lang))
        findings.extend(_audit_local_assets(root, html_path, html))
    return {"ok": not findings, "mode": "static", "root": str(root), "findings": findings}


def check_live(base_url: str, *, timeout: int = 15) -> dict:
    findings: list[dict] = []
    base = base_url.rstrip("/")
    for path, expected_lang in PUBLIC_PAGES.items():
        url = base + path
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                status = response.status
                html = response.read().decode("utf-8", errors="replace")
                final_url = response.geturl()
        except Exception as exc:
            findings.append(_finding(path, "request_failed", str(exc)))
            continue
        if status != 200:
            findings.append(_finding(path, "bad_status", str(status)))
        findings.extend(_audit_html(path, html, expected_lang=expected_lang))
        parser = _parse(html)
        for src in parser.images[:50]:
            if src.startswith("data:"):
                continue
            asset_url = urllib.parse.urljoin(final_url, src)
            try:
                request = urllib.request.Request(asset_url, method="HEAD")
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    if response.status >= 400:
                        findings.append(_finding(path, "image_bad_status", f"{src}:{response.status}"))
            except Exception as exc:
                findings.append(_finding(path, "image_request_failed", f"{src}:{exc}"))
    return {"ok": not findings, "mode": "live", "base_url": base_url, "findings": findings}


def _audit_html(path: str, html: str, *, expected_lang: str) -> list[dict]:
    parser = _parse(html)
    findings: list[dict] = []
    if parser.html_lang != expected_lang:
        findings.append(_finding(path, "lang_mismatch", f"{parser.html_lang} != {expected_lang}"))
    if not parser.title.strip():
        findings.append(_finding(path, "title_missing", ""))
    if not parser.canonical:
        findings.append(_finding(path, "canonical_missing", ""))
    if not parser.og_title:
        findings.append(_finding(path, "og_title_missing", ""))
    if not parser.og_description:
        findings.append(_finding(path, "og_description_missing", ""))
    text = parser.visible_text.lower()
    for term in BANNED_PUBLIC_TERMS:
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text):
            findings.append(_finding(path, "banned_term", term))
    return findings


def _audit_local_assets(root: Path, html_path: Path, html: str) -> list[dict]:
    parser = _parse(html)
    findings: list[dict] = []
    for value in [*parser.images, *parser.links]:
        if _skip_asset(value):
            continue
        parsed = urllib.parse.urlparse(value)
        if parsed.scheme or value.startswith("#"):
            continue
        target = (html_path.parent / parsed.path).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            findings.append(_finding(str(html_path.relative_to(root)), "asset_outside_root", value))
            continue
        if not target.exists():
            if target.with_name("index.html").exists():
                continue
            findings.append(_finding(str(html_path.relative_to(root)), "asset_missing", value))
    return findings


def _parse(html: str) -> _HTMLAuditParser:
    parser = _HTMLAuditParser()
    parser.feed(html)
    return parser


def _static_path(root: Path, path: str) -> Path:
    if path.endswith("/"):
        return root / path.lstrip("/") / "index.html"
    return root / path.lstrip("/")


def _skip_asset(value: str) -> bool:
    return (
        not value
        or value.startswith(("mailto:", "tel:", "javascript:", "data:"))
        or value.startswith("http://")
        or value.startswith("https://")
    )


def _contains_underscore_public_paths(root: Path) -> bool:
    for html_path in root.rglob("*.html"):
        try:
            html = html_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "/_" in html or '"_' in html or "'_" in html:
            return True
    return False


def _finding(path: str, code: str, detail: str) -> dict:
    return {"path": path, "code": code, "detail": detail}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check WebRefurb public site health.")
    parser.add_argument("--mode", choices=("static", "live"), default="static")
    parser.add_argument("--root", default="docs", help="Static site root for --mode static")
    parser.add_argument("--base-url", default="https://webrefurb.com", help="Base URL for --mode live")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args(argv)

    result = check_static(Path(args.root)) if args.mode == "static" else check_live(args.base_url)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"ok: {result['mode']} health check passed")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
