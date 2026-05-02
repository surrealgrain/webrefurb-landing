from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from pipeline.constants import PACKAGE_1_KEY, PACKAGE_2_KEY, PACKAGE_3_KEY
from pipeline.quote import generate_quote


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
        "Ticket Machine Guides",
        "QR Signs",
        "Customer Flow",
        "Scan for English Menu",
        "Owner approval and one correction window",
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
        "注文ガイド",
        "QR案内サイン",
        "スムーズな注文の流れ",
        "内容量と店舗で扱いやすいサイズ",
        "Scan for English Menu",
        "納品前の店舗確認と修正1回",
        "別途お見積もり",
    ):
        assert expected in ja_text


def test_pricing_pages_include_risk_reversal_and_custom_quote_limits():
    en_text = _visible_text(_read("pricing.html"))
    ja_text = _visible_text(_read("ja/pricing.html"))

    for expected in (
        "Owner approval and one correction window are included before delivery",
        "Prices and ingredient/allergen claims are only published after restaurant confirmation",
        "Larger menus, extra pages, additional copies, frequent updates, or combined packages can be quoted separately",
    ):
        assert expected in en_text

    for expected in (
        "納品前の店舗確認と修正1回を含みます",
        "価格・アレルギー表記は店舗確認後のみ掲載します",
        "別途お見積もり",
    ):
        assert expected in ja_text


def test_public_copy_avoids_forbidden_positioning_terms_and_hvac():
    forbidden = (
        "translation service",
        "generic translation",
        "HVAC",
        "hvac",
    )
    for name in ("index.html", "ja/index.html", "pricing.html", "ja/pricing.html"):
        text = _visible_text(_read(name))
        for term in forbidden:
            assert term not in text


def test_quote_copy_has_package_labels_prices_and_risk_reversal():
    expected = {
        PACKAGE_1_KEY: ("English Ordering Files", 30000),
        PACKAGE_2_KEY: ("Counter-Ready Ordering Kit", 45000),
        PACKAGE_3_KEY: ("Live QR English Menu", 65000),
    }

    for package_key, (label, price) in expected.items():
        quote = generate_quote(business_name="Audit Ramen", package_key=package_key)
        combined = " ".join([
            quote.package_label,
            quote.scope_description,
            quote.delivery_terms,
            quote.update_terms,
        ])
        assert quote.package_label == label
        assert quote.price_yen == price
        assert "owner approval" in combined.lower() or "owner confirmation" in combined.lower()
        assert "prices, ingredients, and allergens are only shown when confirmed by the restaurant" in combined.lower()
        assert "correction window" in combined or "bundled update round" in combined


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


def test_dashboard_template_has_no_visible_jinja_when_opened_directly():
    html = (DOCS_ROOT.parent / "dashboard" / "templates" / "index.html").read_text(encoding="utf-8")
    visible_markup = re.sub(r"(?is)<script\b[^>]*>.*?</script>", "", html)

    assert "{%" not in visible_markup
    assert "{{" not in visible_markup
    assert "initial-leads-data" in html


def test_dashboard_review_filters_include_route_and_profile():
    html = (DOCS_ROOT.parent / "dashboard" / "templates" / "index.html").read_text(encoding="utf-8")

    assert 'id="sidebar-route"' in html
    assert 'value="contact_form">Contact Form' in html
    assert 'id="sidebar-profile"' in html
    assert 'value="izakaya_yakitori_kushiyaki">Yakitori / Kushiyaki' in html
    assert "card.dataset.establishmentProfile === profile" in html
    assert 'data-establishment-profile="' in html


def test_dashboard_review_lanes_make_manual_work_queue_visible():
    html = (DOCS_ROOT.parent / "dashboard" / "templates" / "index.html").read_text(encoding="utf-8")

    assert 'id="lead-review-lanes"' in html
    assert "function reviewLaneCounts(leads)" in html
    assert "Email Route Review" in html
    assert "Contact Form Review" in html
    assert "Unreviewed Cards" in html
    assert "Name Review" in html
    assert "Scope Review" in html
    assert "function applyReviewLane(lane)" in html
    assert "function currentReviewLaneFromFilters()" in html
    assert "function updateReviewLaneSelection(activeLane)" in html
    assert "data-review-lane" in html
    assert 'aria-pressed="false"' in html
    assert ".review-lane.is-active" in html


def test_dashboard_keeps_internal_plan_and_filters_out_of_primary_sidebar():
    html = (DOCS_ROOT.parent / "dashboard" / "templates" / "index.html").read_text(encoding="utf-8")

    assert "Phase Plan" not in html
    assert "Queue Filters" not in html
    assert 'id="advanced-filter-toggle"' in html
    assert 'id="advanced-filters"' in html
    assert "function toggleAdvancedFilters()" in html
    assert 'id="nav-builds"' not in html


def test_dashboard_has_no_send_review_outcome_controls():
    html = (DOCS_ROOT.parent / "dashboard" / "templates" / "index.html").read_text(encoding="utf-8")

    assert 'id="review-outcome-panel"' in html
    assert 'id="sidebar-review-outcome"' in html
    assert 'id="review-outcome-select"' in html
    assert 'value="not_reviewed">Not Reviewed' in html
    assert 'value="hold">Hold' in html
    assert 'value="needs_more_info">Needs More Info' in html
    assert 'value="reject">Reject' in html
    assert 'id="save-review-next-btn"' in html
    assert 'id="next-review-card-btn"' in html
    assert 'data-review-outcome="' in html
    assert "reviewOutcomeValue(lead)" in html
    assert "visibleReviewCardIds" in html
    assert "nextReviewLeadIdAfterSave" in html
    assert "openNextReviewCard" in html
    assert "loadDashboardLeads(true)" in html
    assert "saveLeadReviewOutcome" in html
    assert "/review-outcome" in html
