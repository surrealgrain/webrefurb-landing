from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from pipeline.constants import ENGLISH_QR_MENU_KEY
from pipeline.quote import generate_quote


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = PROJECT_ROOT / "docs"


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs):
        if tag in {"script", "style"}:
            self._skip += 1

    def handle_endtag(self, tag: str):
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str):
        if not self._skip:
            self.parts.append(data)


def _read(name: str) -> str:
    return (DOCS_ROOT / name).read_text(encoding="utf-8")


def _visible_text(html: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(html)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def test_homepage_is_qr_first_single_product():
    text = _visible_text(_read("index.html"))

    assert "English QR Menu for Japanese restaurants" in text
    assert "Customers scan, read in English, add items to a list, and show Japanese item names to staff" in text
    assert "English QR Menu + Show Staff List" in text
    assert "65,000 yen" in text


def test_pricing_page_has_one_product_and_owner_confirmation_rules():
    text = _visible_text(_read("pricing.html"))

    assert "English QR Menu + Show Staff List" in text
    assert "65,000 yen" in text
    assert "Hosted English QR menu page" in text
    assert "QR code" in text
    assert "Printable QR sign" in text
    assert "12 months hosting" in text
    assert "One pre-launch revision" in text
    assert "Owner confirmation is required before publishing prices" in text
    assert "Updates after launch are available on request and quoted separately" in text


def test_public_site_avoids_banned_customer_facing_terms():
    banned = (
        "ordering system",
        "QR ordering system",
        "online ordering",
        "POS",
        "checkout",
        "place order",
        "submit order",
        "package_1_remote_30k",
        "package_2_printed_delivered_45k",
        "package_3_qr_menu_65k",
        "English Ordering Files",
        "Counter-Ready Ordering Kit",
        "Live QR English Menu",
        "lamination",
        "print-ready",
        "AI",
        "automation",
        "scraping",
    )
    for name in ("index.html", "pricing.html", "ja/index.html", "ja/pricing.html", "demo/index.html"):
        text = _visible_text(_read(name))
        lowered = text.lower()
        for term in banned:
            if term in {"AI", "POS"}:
                assert re.search(rf"\b{re.escape(term.lower())}\b", lowered) is None, f"{term} leaked in {name}"
            else:
                assert term.lower() not in lowered, f"{term} leaked in {name}"


def test_generic_demo_has_add_to_list_and_show_staff_flow():
    html = _read("demo/index.html")
    text = _visible_text(html)

    assert "Generic demo - example content only" in text
    assert "Add to list" in html
    assert "Review list" in text
    assert "Show to staff" in text
    assert "Show Staff List" in text
    assert "Japanese item names are first" in text
    assert "醤油ラーメン" in html
    assert "若鶏の唐揚げ" in html
    assert "checkout" not in html.lower()
    assert "submit order" not in html.lower()


def test_dashboard_single_active_package_option():
    html = (PROJECT_ROOT / "dashboard" / "templates" / "index.html").read_text(encoding="utf-8")

    assert 'value="english_qr_menu_65k"' in html
    assert "English QR Menu - ¥65,000" in html
    assert 'value="package_1_remote_30k"' not in html
    assert 'value="package_2_printed_delivered_45k"' not in html
    assert 'value="package_3_qr_menu_65k"' not in html


def test_quote_copy_is_single_qr_product():
    quote = generate_quote(business_name="Audit Ramen", package_key=ENGLISH_QR_MENU_KEY)
    combined = " ".join([quote.package_label, quote.scope_description, quote.delivery_terms, quote.update_terms])

    assert quote.package_label == "English QR Menu"
    assert quote.price_yen == 65000
    assert "Show Staff List" in combined
    assert "owner confirmation" in combined.lower()
    assert "English Ordering Files" not in combined
