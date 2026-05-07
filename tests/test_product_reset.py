from __future__ import annotations

from pathlib import Path

from pipeline.constants import ENGLISH_QR_MENU_KEY, GENERIC_DEMO_URL, PACKAGE_1_KEY, PACKAGE_REGISTRY
from pipeline.models import QualificationResult
from pipeline.scoring import recommend_package_details_for_record
from pipeline.search import _qr_first_pitch_draft, _recover_codex_review_qualification


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _qualified(category: str) -> dict:
    return {
        "lead": True,
        "country": "Japan",
        "category": category,
        "primary_category_v1": category,
        "contacts": [{"type": "email", "value": "owner@example.jp", "actionable": True}],
        "email": "owner@example.jp",
        "english_menu_state": "missing",
        "launch_readiness_status": "ready_for_outreach",
    }


def test_only_english_qr_menu_is_public_package():
    assert list(PACKAGE_REGISTRY) == [ENGLISH_QR_MENU_KEY]
    product = PACKAGE_REGISTRY[ENGLISH_QR_MENU_KEY]

    assert product["label"] == "English QR Menu"
    assert product["price_yen"] == 65000
    assert "Show Staff List feature" in product["includes"]


def test_qualified_ramen_and_izakaya_recommend_english_qr_menu():
    for category in ("ramen", "izakaya"):
        recommendation = recommend_package_details_for_record(_qualified(category))
        assert recommendation["package_key"] == ENGLISH_QR_MENU_KEY
        assert recommendation["package_key"] != PACKAGE_1_KEY
        assert recommendation["custom_quote_reason"] == ""


def test_unknown_category_is_not_an_active_recommendation():
    recommendation = recommend_package_details_for_record(_qualified("sushi"))

    assert recommendation["package_key"] == "skip"
    assert recommendation["recommendation_reason"] == "unsupported_restaurant_category_outside_active_scope"


def test_legacy_package_ids_are_not_active_registry_keys():
    assert "package_1_remote_30k" not in PACKAGE_REGISTRY
    assert "package_2_printed_delivered_45k" not in PACKAGE_REGISTRY
    assert "package_3_qr_menu_65k" not in PACKAGE_REGISTRY


def test_recovered_search_review_lead_does_not_fall_back_to_old_package():
    recovered = _recover_codex_review_qualification(
        qualification=QualificationResult(
            lead=False,
            rejection_reason="no_verified_business_email_route",
            business_name="Audit Ramen",
            primary_category_v1="ramen",
            recommended_primary_package="",
        ),
        canonical="ramen",
        source_name="Audit Ramen",
        source_website="https://example.jp",
        source_address="Tokyo, Japan",
        source_url="https://example.jp/contact",
        rejection_reason="no_verified_business_email_route",
    )

    assert recovered.launch_readiness_status == "manual_review"
    assert recovered.recommended_primary_package == ENGLISH_QR_MENU_KEY
    assert recovered.recommended_primary_package != PACKAGE_1_KEY


def test_active_search_generation_does_not_import_legacy_pitch_builder():
    source = (PROJECT_ROOT / "pipeline" / "search.py").read_text(encoding="utf-8")

    assert "from .pitch import build_pitch" not in source
    assert "build_pitch(" not in source


def test_search_compatibility_pitch_is_qr_first_and_generic():
    draft = _qr_first_pitch_draft(
        business_name="Audit Ramen",
        establishment_profile="ramen",
    )
    combined = "\n".join(part for section in draft.values() for part in section.values())

    assert "英語QRメニュー" in combined
    assert "Show Staff List" in combined
    assert GENERIC_DEMO_URL in combined
    assert "公開されているメニュー情報" not in combined
    assert "確認用サンプル" not in combined
    assert "menu photos" not in combined.lower()
    assert "package_1_remote_30k" not in combined


def test_no_stale_sample_or_old_package_language_in_active_outbound_paths():
    paths = [
        PROJECT_ROOT / "pipeline" / "search.py",
        PROJECT_ROOT / "pipeline" / "outreach.py",
        PROJECT_ROOT / "pipeline" / "email_templates.py",
        PROJECT_ROOT / "pipeline" / "pitch.py",
        PROJECT_ROOT / "pipeline" / "hosted_sample.py",
        PROJECT_ROOT / "dashboard" / "templates" / "index.html",
        PROJECT_ROOT / "docs" / "index.html",
        PROJECT_ROOT / "docs" / "pricing.html",
        PROJECT_ROOT / "docs" / "ja" / "index.html",
        PROJECT_ROOT / "docs" / "ja" / "pricing.html",
        PROJECT_ROOT / "docs" / "demo" / "index.html",
    ]
    banned = (
        "package_1_remote_30k",
        "package_2_printed_delivered_45k",
        "package_3_qr_menu_65k",
        "sample from public menu",
        "based on your public menu",
        "made from your menu",
        "send menu photos",
        "公開されているメニュー情報",
        "確認用サンプル",
        "ordering system",
        "qr ordering system",
        "checkout",
        "place order",
        "submit order",
        "lamination",
    )

    for path in paths:
        lowered = path.read_text(encoding="utf-8").lower()
        for term in banned:
            assert term.lower() not in lowered, f"{term} leaked in {path}"
