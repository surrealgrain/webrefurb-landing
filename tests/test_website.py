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
    assert "<title>WebRefurb | 飲食店向け英語注文システム制作</title>" in ja
    assert 'href="/ja"' in en
    assert 'href="/"' in ja
    assert 'href="/pricing.html"' in en
    assert 'href="/ja/pricing.html"' in ja


def test_homepages_include_pricing_content():
    en_text = _visible_text(_read("index.html"))
    ja_text = _visible_text(_read("ja/index.html"))

    for expected in (
        "English Ordering Files",
        "¥30,000",
        "Counter-Ready Ordering Kit",
        "¥45,000",
        "Live QR English Menu",
        "¥65,000",
        "sized compactly for your menu and shop",
        "hosted English ordering menu",
        "Scan for English Menu",
        "quoted separately",
    ):
        assert expected in en_text

    for expected in (
        "英語注文ファイル",
        "30,000円",
        "店頭用注文キット",
        "45,000円",
        "ライブQR英語メニュー",
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


def test_public_menu_samples_do_not_expose_unsafe_placeholders():
    docs_menu_root = DOCS_ROOT / "menus"
    unsafe_patterns = (
        "[[",
        "OCR required",
        "menu image detected",
        r"\[[^\]]*[\u3040-\u30ff\u3400-\u9fff][^\]]*\]",
    )

    for path in docs_menu_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".html", ".json"}:
            content = path.read_text(encoding="utf-8")
            for pattern in unsafe_patterns:
                if pattern.startswith("\\["):
                    assert re.search(pattern, content) is None, f"Unsafe placeholder in {path}"
                else:
                    assert pattern not in content, f"Unsafe placeholder in {path}"
