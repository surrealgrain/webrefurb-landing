from __future__ import annotations

from pipeline.models import EvidenceAssessment
from pipeline.preview import build_preview_html, build_preview_menu, build_shop_preview_from_record


def _assessment(**overrides):
    values = {
        "is_ramen_candidate": True,
        "is_izakaya_candidate": False,
        "evidence_classes": ["official_html_menu"],
        "menu_evidence_found": True,
        "machine_evidence_found": False,
        "course_or_drink_plan_evidence_found": False,
        "score": 8,
        "evidence_urls": ["https://example.test/menu"],
        "best_evidence_url": "https://example.test/menu",
        "best_evidence_reason": "Menu evidence is strongest.",
        "false_positive_risk": "low",
    }
    values.update(overrides)
    return EvidenceAssessment(
        **values,
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
    assert "English review sample" not in html


def test_preview_does_not_guess_unknown_translations():
    preview = build_preview_menu(
        assessment=_assessment(),
        snippets=["季節限定の特製創作麺 メニュー"],
        business_name="Safe Ramen",
    )
    html = build_preview_html(preview_menu=preview, ticket_machine_hint=None, business_name="Safe Ramen")

    assert "季節限定の特製創作麺" not in html
    assert "English review sample" not in html


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


def test_preview_blocks_bracketed_fallback_and_reservation_only_snippets():
    html = build_shop_preview_from_record(record={
        "business_name": "Unsafe Lead",
        "establishment_profile": "ramen_only",
        "evidence_snippets": [
            "醤油ラーメン -> [醤油ラーメン]",
            "公式サイトからのご予約 reservation calendar",
        ],
        "evidence_classes": ["official_html_menu"],
        "menu_evidence_found": True,
        "machine_evidence_found": False,
    })

    assert html is None


def test_preview_rejects_headers_footers_tel_search_and_chain_text():
    preview = build_preview_menu(
        assessment=_assessment(),
        snippets=[
            "Header 店舗情報 TEL 03-1234-5678 アクセス",
            "Tsukada Nojo 塚田農場 コース メニュー",
            "味噌ラーメン トッピング メニュー",
        ],
        business_name="Safe Ramen",
    )
    html = build_preview_html(preview_menu=preview, ticket_machine_hint=None, business_name="Safe Ramen")

    assert "店舗情報" not in html
    assert "03-1234-5678" not in html
    assert "Tsukada" not in html
    assert "味噌ラーメン" in html


def test_shop_preview_requires_customer_eligible_proof_item_when_proof_items_exist():
    html = build_shop_preview_from_record(record={
        "business_name": "Unsafe Proof Lead",
        "establishment_profile": "ramen_only",
        "evidence_snippets": ["醤油ラーメン 味玉 トッピング メニュー"],
        "evidence_classes": ["official_html_menu"],
        "menu_evidence_found": True,
        "machine_evidence_found": False,
        "proof_items": [{
            "source_type": "official_or_shop_site",
            "url": "https://unsafe-proof.test/menu",
            "snippet": "醤油ラーメン 味玉 トッピング メニュー",
            "operator_visible": True,
            "customer_preview_eligible": False,
            "rejection_reason": "operator_rejected_sample_asset",
        }],
    })

    assert html is None


def test_ramen_preview_shows_operational_clarity_when_proven():
    preview = build_preview_menu(
        assessment=_assessment(machine_evidence_found=True),
        snippets=["醤油ラーメン 味玉 トッピング セット 替玉 スープ 券売機 メニュー"],
        business_name="Ramen Ops",
    )
    html = build_preview_html(preview_menu=preview, ticket_machine_hint=None, business_name="Ramen Ops")

    assert "Toppings" in html
    assert "Sets" in html
    assert "Noodle / soup choices" in html
    assert "Add-ons" in html
    assert "Ticket-machine button mapping" in html


def test_izakaya_preview_shows_drinks_courses_nomihodai_and_shared_plates_when_proven():
    preview = build_preview_menu(
        assessment=_assessment(
            is_ramen_candidate=False,
            is_izakaya_candidate=True,
            course_or_drink_plan_evidence_found=True,
        ),
        snippets=["居酒屋 メニュー 生ビール ハイボール コース 飲み放題 刺身 唐揚げ 一品料理"],
        business_name="Izakaya Ops",
    )
    html = build_preview_html(preview_menu=preview, ticket_machine_hint=None, business_name="Izakaya Ops")

    assert "Drinks" in html
    assert "Courses" in html
    assert "Nomihodai rules" in html
    assert "Shared plates" in html
