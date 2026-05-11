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
    html = _read("index.html")

    assert "English QR menus for restaurants in Japan" in text
    assert "Guests scan a QR code, read your menu in English" in text
    assert "English QR Menu + Show Staff List" in text
    assert "free trial" in text.lower()
    assert 'href="pricing.html"' in html


def test_ja_homepage_is_qr_first_single_product():
    html = _read("ja/index.html")
    text = _visible_text(html)

    assert "日本の飲食店向け English QR Menu" in text
    assert "英語でメニューを確認" in text
    assert "English QR Menu + Show Staff List" in text
    assert "1週間の無料トライアル" in text
    assert 'href="pricing.html"' in html


def test_pricing_page_has_one_product_and_owner_confirmation_rules():
    text = _visible_text(_read("pricing.html"))

    assert "65,000 yen" in text
    assert "Hosted English QR menu page" in text
    assert "QR code" in text
    assert "Printable QR sign" in text
    assert "Hosting included" in text
    assert "One pre-launch revision" in text
    assert "Owner confirmation is required before publishing prices" in text
    assert "Updates after launch are available on request and quoted separately" in text
    assert "Free 1-week trial" in text
    assert "Show Staff List" in text
    assert "Tax excluded" in text
    assert "No monthly fees" in text
    assert "used only to create and operate your QR menu" in text
    assert "12 months" not in text


def test_ja_pricing_page_has_one_product_and_owner_confirmation_rules():
    text = _visible_text(_read("ja/pricing.html"))

    assert "65,000円" in text
    assert "英語QRメニューのトライアルページ" in text
    assert "QRコード" in text
    assert "印刷用QRサイン" in text
    assert "ホスティング込み" in text
    assert "公開前修正1回" in text
    assert "価格はオーナー確認後のみ公開します" in text
    assert "1週間の無料トライアル" in text
    assert "税別" in text
    assert "月額料金はありません" in text
    assert "QRメニューの制作と運用のみに使用します" in text
    assert "12ヶ月" not in text


def test_homepage_keeps_mobile_demo_accessible():
    html = _read("index.html")
    ja_html = _read("ja/index.html")

    assert 'class="mobile-demo"' in html
    assert 'href="demo/ramen.html"' in html
    assert ".phone-wrap { display: flex; }" in html
    assert 'class="mobile-demo"' in ja_html
    assert 'href="../demo/ramen.html"' in ja_html
    assert ".phone-wrap { display: flex; }" in ja_html


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


def test_public_pages_have_seo_foundation():
    expected = {
        "index.html": "https://webrefurb.com/",
        "ja/index.html": "https://webrefurb.com/ja/",
        "pricing.html": "https://webrefurb.com/pricing.html",
        "ja/pricing.html": "https://webrefurb.com/ja/pricing.html",
        "demo/index.html": "https://webrefurb.com/demo/",
        "demo/ramen.html": "https://webrefurb.com/demo/ramen.html",
        "demo/sushi.html": "https://webrefurb.com/demo/sushi.html",
    }
    for name, canonical in expected.items():
        html = _read(name)
        assert f'<link rel="canonical" href="{canonical}">' in html
        assert '<meta property="og:title"' in html
        assert '<meta property="og:description"' in html
        assert '<meta property="og:image" content="https://webrefurb.com/logo.svg">' in html

    sitemap = _read("sitemap.xml")
    for canonical in expected.values():
        assert f"<loc>{canonical}</loc>" in sitemap
    assert "Sitemap: https://webrefurb.com/sitemap.xml" in _read("robots.txt")


def test_root_public_files_mirror_docs_pages_source():
    # GitHub Pages currently serves the repository root for the custom domain.
    # Keep these mirrored until Pages is explicitly configured to use /docs.
    mirrored = (
        "CNAME",
        "email-logo.svg",
        "index.html",
        "logo.svg",
        "pricing.html",
        "robots.txt",
        "sitemap.xml",
        "ja/index.html",
        "ja/pricing.html",
        "demo/index.html",
        "demo/ramen.html",
        "demo/sushi.html",
    )
    for name in mirrored:
        assert (PROJECT_ROOT / name).read_bytes() == (DOCS_ROOT / name).read_bytes()

    assert (PROJECT_ROOT / "assets" / "previews" / "qr-mobile-menu.png").exists()
    assert (PROJECT_ROOT / "demo" / "_demo_images" / "ramen" / "shoyu_ramen.png").exists()


def test_generic_demo_has_add_to_list_and_show_staff_flow():
    # Demo hub page references the flow and links to interactive demos
    html = _read("demo/index.html")
    text = _visible_text(html)

    assert "add items to a list" in text.lower()
    assert "Japanese-first staff screen" in text or "Show Staff List" in text
    assert "checkout" not in html.lower()
    assert "submit order" not in html.lower()
    assert "place order" not in html.lower()
    assert "ordering system" not in html.lower()

    # Interactive ramen demo has the full Add to list / Show staff flow + CJK
    ramen_html = _read("demo/ramen.html")
    assert "Add to list" in ramen_html
    assert "Show this list to staff" in ramen_html
    assert "お客様のリスト" in ramen_html
    assert any("\u4e00" <= c <= "\u9fff" for c in ramen_html)


def test_dashboard_single_active_package_option():
    html = (PROJECT_ROOT / "dashboard" / "templates" / "index.html").read_text(encoding="utf-8")

    # New SPA dashboard references the product via API, not form values
    assert "QR Menu Studio" in html
    assert "ramen" in html.lower()
    assert "izakaya" in html.lower()
    # No old package references
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
