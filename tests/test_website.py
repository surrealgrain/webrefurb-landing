from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path


DOCS_ROOT = Path(__file__).resolve().parents[1] / "docs"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.parts))


def _read(name: str) -> str:
    return (DOCS_ROOT / name).read_text(encoding="utf-8")


def _visible_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text


def test_homepage_titles_and_language_links():
    en = _read("index.html")
    ja = _read("ja/index.html")

    assert "<title>WebRefurb | English Menus &amp; Ordering Guides for Restaurants</title>" in en
    assert "<title>WebRefurb | 飲食店向け英語メニュー・注文ガイド制作</title>" in ja
    assert 'href="/ja"' in en
    assert 'href="/"' in ja
    assert 'href="/pricing.html"' in en
    assert 'href="/ja/pricing.html"' in ja


def test_homepages_include_pricing_content():
    en_text = _visible_text(_read("index.html"))
    ja_text = _visible_text(_read("ja/index.html"))

    for expected in (
        "Online Delivery",
        "¥30,000",
        "Printed and Delivered",
        "¥45,000",
        "QR Menu System",
        "¥65,000",
        "sized compactly for your menu and shop",
        "hosted English menu page",
        "Scan for English Menu",
        "quoted separately",
    ):
        assert expected in en_text

    for expected in (
        "オンライン納品",
        "30,000円",
        "印刷・お届け",
        "45,000円",
        "QRメニューシステム",
        "65,000円",
        "内容量と店舗で扱いやすいサイズ",
        "Scan for English Menu",
        "別途お見積もり",
    ):
        assert expected in ja_text


def test_website_visible_copy_has_no_em_dashes():
    for name in ("index.html", "ja/index.html", "pricing.html", "ja/pricing.html"):
        text = _visible_text(_read(name))
        assert "—" not in text
        assert "–" not in text
