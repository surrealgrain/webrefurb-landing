"""Tests for WebRefurbMenu pipeline modules."""

from __future__ import annotations

import pytest
from pipeline.qualification import qualify_candidate
from pipeline.evidence import (
    assess_evidence, is_chain_business, is_excluded_business,
    is_invalid_page, classify_primary_category, has_public_website,
    looks_high_quality_english,
)
from pipeline.scoring import (
    compute_tourist_exposure_score, compute_lead_score_v1,
    detect_english_menu_issue, recommend_package,
)
from pipeline.models import QualificationResult
from pipeline.constants import (
    PACKAGE_A_KEY, PACKAGE_B_KEY,
    LEAD_CATEGORY_RAMEN_MENU_TRANSLATION,
    LEAD_CATEGORY_RAMEN_MACHINE_MAPPING,
    LEAD_CATEGORY_RAMEN_MENU_AND_MACHINE,
    LEAD_CATEGORY_IZAKAYA_MENU_TRANSLATION,
)
from pipeline.html_parser import extract_page_payload
from pipeline.utils import slugify, sha256_text, utc_now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ramen_page(html: str = "", url: str = "https://example.ramen.jp") -> dict:
    return {"url": url, "html": html or _ramen_html()}


def _ramen_html() -> str:
    return """
    <html><body>
    <h1>テストラーメン</h1>
    <div class="menu">
        <h2>メニュー</h2>
        <ul>
            <li>醤油ラーメン ¥850</li>
            <li>味噌ラーメン ¥900</li>
            <li>塩ラーメン ¥800</li>
            <li>唐揚げ ¥480</li>
            <li>餃子 ¥350</li>
        </ul>
    </div>
    <p>券売機でご注文ください。</p>
    <p>住所：東京都渋谷区神南1-2-3</p>
    <p>電話：03-1234-5678</p>
    </body></html>
    """


def _izakaya_html() -> str:
    return """
    <html><body>
    <h1>テスト居酒屋</h1>
    <div class="menu">
        <h2>メニュー</h2>
        <ul>
            <li>刺身盛り合わせ ¥980</li>
            <li>焼き鳥 ¥380</li>
            <li>唐揚げ ¥480</li>
            <li>飲み放題 ¥1,500</li>
        </ul>
    </div>
    <p>コース料理もございます。</p>
    <p>住所：東京都新宿区歌舞伎町1-2-3</p>
    </body></html>
    """


# ===========================================================================
# Qualification tests — binary lead semantics
# ===========================================================================
class TestBinaryLead:
    def test_ramen_shop_qualifies(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
            address="東京都渋谷区神南1-2-3",
            phone="03-1234-5678",
        )
        assert result.lead is True
        assert result.rejection_reason is None
        assert result.primary_category_v1 == "ramen"
        assert result.lead_score_v1 > 0
        assert result.recommended_primary_package != ""

    def test_izakaya_qualifies(self):
        result = qualify_candidate(
            business_name="テスト居酒屋",
            website="https://example.izakaya.jp",
            category="izakaya",
            pages=[{"url": "https://example.izakaya.jp", "html": _izakaya_html()}],
            address="東京都新宿区歌舞伎町1-2-3",
        )
        assert result.lead is True
        assert result.rejection_reason is None
        assert result.primary_category_v1 == "izakaya"

    def test_no_physical_location_rejected(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
        )
        assert result.lead is False
        assert result.rejection_reason == "no_physical_location_evidence"

    def test_chain_rejected(self):
        result = qualify_candidate(
            business_name="一蘭 渋谷店",
            website="https://ichiran.com",
            category="ramen",
            pages=[_ramen_page()],
            address="東京都渋谷区",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_business"

    def test_chain_ippudo_rejected(self):
        result = qualify_candidate(
            business_name="一風堂 新宿店",
            website="https://ippudo.com",
            category="ramen",
            pages=[_ramen_page()],
            address="東京都新宿区",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_business"

    def test_branch_store_rejected(self):
        result = qualify_candidate(
            business_name="テストラーメン 3号店",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
            address="東京都渋谷区",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_business"

    def test_non_ramen_izakaya_rejected(self):
        result = qualify_candidate(
            business_name="テスト寿司",
            website="https://example.sushi.jp",
            category="sushi",
            pages=[{"url": "https://example.sushi.jp", "html": "<html><body><h1>寿司</h1><p>にぎり ¥300</p></body></html>"}],
            address="東京都中央区",
        )
        assert result.lead is False
        assert result.rejection_reason == "non_ramen_izakaya_v1"

    def test_excluded_business_sushi_rejected(self):
        html = "<html><body><h1>寿司処</h1><p>寿司 メニュー</p></body></html>"
        result = qualify_candidate(
            business_name="寿司処 テスト",
            website="https://example.sushi.jp",
            category="ramen",
            pages=[{"url": "https://example.sushi.jp", "html": html}],
            address="東京都渋谷区",
        )
        assert result.lead is False
        assert result.rejection_reason == "excluded_business_type_v1"

    def test_excluded_business_yakiniku_rejected(self):
        html = "<html><body><h1>焼肉レストラン</h1><p>焼肉 メニュー</p></body></html>"
        result = qualify_candidate(
            business_name="焼肉レストラン",
            website="https://example.yakiniku.jp",
            category="izakaya",
            pages=[{"url": "https://example.yakiniku.jp", "html": html}],
            address="東京都渋谷区",
        )
        assert result.lead is False

    def test_negative_score_rejected(self):
        """Negative evidence score (food-only photos, storefront only) → rejected."""
        html = """
        <html><body>
        <h1>テストラーメン</h1>
        <img src="storefront.jpg" alt="storefront exterior">
        <img src="ramen.jpg" alt="ramen food bowl">
        </body></html>
        """
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp", "html": html}],
            address="東京都渋谷区",
        )
        assert result.lead is False

    def test_independent_business_not_rejected_by_chain_check(self):
        assert is_chain_business("商店街ラーメン") is False
        assert is_chain_business("小さな居酒屋 よいち") is False

    def test_place_id_counts_as_location(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
            place_id="ChIJ_test123",
        )
        # Should pass physical location gate
        assert result.rejection_reason != "no_physical_location_evidence"


class TestInvalidPageGuard:
    def test_captcha_page_no_evidence(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp", "html": "<html><body><p>please verify you are human captcha</p></body></html>"}],
            address="東京都渋谷区",
        )
        assert result.lead is False

    def test_js_empty_page_no_evidence(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp", "html": "<html><body><p>please enable javascript to view this page</p></body></html>"}],
            address="東京都渋谷区",
        )
        assert result.lead is False

    def test_invalid_page_mixed_with_valid(self):
        """When invalid pages are mixed with valid ones, valid evidence still counts."""
        pages = [
            {"url": "https://example.ramen.jp", "html": "<html><body><p>captcha bot protection</p></body></html>"},
            _ramen_page(url="https://example.ramen.jp/menu"),
        ]
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=pages,
            address="東京都渋谷区",
        )
        # Should still qualify from the valid page
        assert result.lead is True


class TestAlreadyGoodEnglish:
    def test_high_quality_english_rejected(self):
        html = """
        <html><body>
        <h1>Test Ramen Shop</h1>
        <div>
            <p>Our menu features Shoyu Ramen, Miso Ramen, and Tonkotsu Ramen.</p>
            <p>Allergen information is available. Ingredients listed for each dish.</p>
            <p>Reservations accepted. Order online for delivery.</p>
            <p>Open daily. Location: Shibuya, Tokyo.</p>
            <p>Hours: 11:00-22:00. Address: 1-2-3 Shibuya.</p>
        </div>
        </body></html>
        """
        # Need enough English text to trigger the high-quality English detection
        result = qualify_candidate(
            business_name="Test Ramen",
            website="https://example.ramen.jp/en",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp/en", "html": html}],
            address="東京都渋谷区",
        )
        assert result.lead is False


# ===========================================================================
# Scoring tests
# ===========================================================================
class TestScoring:
    def test_ramen_score_higher_than_izakaya(self):
        ramen = compute_lead_score_v1(
            category="ramen", english_menu_issue=True,
            tourist_exposure=0.5, rating=4.5, reviews=500,
        )
        izakaya = compute_lead_score_v1(
            category="izakaya", english_menu_issue=True,
            tourist_exposure=0.5, rating=4.5, reviews=500,
        )
        assert ramen > izakaya

    def test_no_english_issue_zero_bonus(self):
        with_issue = compute_lead_score_v1(
            category="ramen", english_menu_issue=True,
            tourist_exposure=0.5,
        )
        without_issue = compute_lead_score_v1(
            category="ramen", english_menu_issue=False,
            tourist_exposure=0.5,
        )
        assert with_issue > without_issue

    def test_tourist_exposure_tokyo(self):
        score = compute_tourist_exposure_score(address="Tokyo, Shibuya-ku", reviews=300)
        assert score >= 0.5

    def test_tourist_exposure_rural(self):
        score = compute_tourist_exposure_score(address="Inaka-mura, Fukushima")
        assert score < 0.3

    def test_package_recommendation_none(self):
        pkg = recommend_package(
            english_menu_issue=False,
            machine_evidence_found=True,
            tourist_exposure_score=0.8,
            lead_score_v1=80,
        )
        assert pkg == "none"

    def test_package_recommendation_a_for_machine(self):
        pkg = recommend_package(
            english_menu_issue=True,
            machine_evidence_found=True,
            tourist_exposure_score=0.3,
            lead_score_v1=50,
        )
        assert pkg == PACKAGE_A_KEY

    def test_package_recommendation_a_for_high_tourist(self):
        pkg = recommend_package(
            english_menu_issue=True,
            machine_evidence_found=False,
            tourist_exposure_score=0.7,
            lead_score_v1=50,
        )
        assert pkg == PACKAGE_A_KEY

    def test_package_recommendation_a_for_high_score(self):
        pkg = recommend_package(
            english_menu_issue=True,
            machine_evidence_found=False,
            tourist_exposure_score=0.3,
            lead_score_v1=75,
        )
        assert pkg == PACKAGE_A_KEY

    def test_package_recommendation_b_default(self):
        pkg = recommend_package(
            english_menu_issue=True,
            machine_evidence_found=False,
            tourist_exposure_score=0.3,
            lead_score_v1=40,
        )
        assert pkg == PACKAGE_B_KEY


# ===========================================================================
# Evidence tests
# ===========================================================================
class TestEvidence:
    def test_assess_ramen_menu(self):
        payload = extract_page_payload("https://example.ramen.jp", _ramen_html())
        assessment = assess_evidence(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            payloads=[payload],
        )
        assert assessment.is_ramen_candidate is True
        assert assessment.menu_evidence_found is True
        assert assessment.machine_evidence_found is True
        assert assessment.score > 0

    def test_chain_detection(self):
        assert is_chain_business("Ichiran Shibuya") is True
        assert is_chain_business("IPPUDO Shinjuku") is True
        assert is_chain_business("Afuri Ebisu") is True

    def test_excluded_business(self):
        assert is_excluded_business("寿司レストラン", "") is True
        assert is_excluded_business("焼肉酒場", "") is True
        assert is_excluded_business("カフェ テスト", "") is True
        assert is_excluded_business("テストラーメン", "") is False

    def test_classify_category(self):
        assert classify_primary_category("ラーメン メニュー") == "ramen"
        assert classify_primary_category("居酒屋 料理") == "izakaya"
        assert classify_primary_category("random stuff") == "other"


# ===========================================================================
# Utility tests
# ===========================================================================
class TestUtils:
    def test_slugify(self):
        assert slugify("Test Ramen Shop") == "test-ramen-shop"
        assert slugify("!!!") == "lead"

    def test_sha256_text(self):
        h1 = sha256_text("hello")
        h2 = sha256_text("hello")
        h3 = sha256_text("world")
        assert h1 == h2
        assert h1 != h3

    def test_utc_now(self):
        now = utc_now()
        assert "T" in now
        assert "+" in now or "Z" in now


# ===========================================================================
# HVAC isolation check
# ===========================================================================
class TestNoHVAC:
    def test_no_hvac_references(self):
        """Verify no HVAC-related terms appear in any pipeline source."""
        import pathlib
        root = pathlib.Path(__file__).resolve().parent.parent / "pipeline"
        hvac_terms = ("hvac", "HVAC", "heating", "cooling", "plumbing", "roofing")
        for py_file in root.rglob("*.py"):
            content = py_file.read_text()
            for term in hvac_terms:
                assert term not in content, f"Found '{term}' in {py_file.name}"
