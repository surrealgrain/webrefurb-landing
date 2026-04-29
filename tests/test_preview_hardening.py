from __future__ import annotations

from pipeline.models import EvidenceAssessment
from pipeline.preview import build_preview_html, build_preview_menu, build_shop_preview_from_record


def _assessment():
    return EvidenceAssessment(
        is_ramen_candidate=True,
        is_izakaya_candidate=False,
        evidence_classes=["official_html_menu"],
        menu_evidence_found=True,
        machine_evidence_found=False,
        course_or_drink_plan_evidence_found=False,
        score=8,
        evidence_urls=["https://example.test/menu"],
        best_evidence_url="https://example.test/menu",
        best_evidence_reason="Menu evidence is strongest.",
        false_positive_risk="low",
    )


def test_preview_filters_bad_snippets_and_hides_unconfirmed_prices():
    preview = build_preview_menu(
        assessment=_assessment(),
        snippets=[
            "Calendar check TEL_String 店舗検索",
            "醤油ラーメン 900円 味玉 トッピング メニュー",
        ],
        business_name="Safe Ramen",
    )
    html = build_preview_html(preview_menu=preview, ticket_machine_hint=None, business_name="Safe Ramen")

    assert "Calendar" not in html
    assert "900円" not in html
    assert "[" not in html
    assert "醤油ラーメン" in html


def test_shop_preview_returns_none_when_no_safe_customer_proof():
    html = build_shop_preview_from_record(record={
        "business_name": "Unsafe Lead",
        "establishment_profile": "ramen_only",
        "evidence_snippets": ["Calendar check TEL_String 店舗検索"],
        "evidence_classes": ["official_html_menu"],
        "menu_evidence_found": True,
        "machine_evidence_found": False,
    })

    assert html is None
