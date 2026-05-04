from __future__ import annotations

import json

from pipeline.constants import PACKAGE_2_KEY
from pipeline.lead_dossier import (
    READINESS_DISQUALIFIED,
    READINESS_MANUAL,
    READINESS_READY,
    build_lead_evidence_dossier,
    migrate_lead_record,
    migrate_state_leads,
    safe_customer_snippets,
)
from pipeline.operator_state import OPERATOR_DONE, OPERATOR_READY, OPERATOR_REVIEW, OPERATOR_SKIP


def _ready_record(**overrides):
    record = {
        "lead_id": "wrm-ready",
        "lead": True,
        "business_name": "Independent Ramen",
        "primary_category_v1": "ramen",
        "english_availability": "missing",
        "english_menu_issue": True,
        "menu_evidence_found": True,
        "machine_evidence_found": True,
        "address": "東京都渋谷区1-1-1",
        "evidence_urls": ["https://example.test/menu"],
        "evidence_snippets": ["醤油ラーメン 味玉 トッピング メニュー"],
        "contacts": [{"type": "email", "value": "owner@independent-ramen.jp", "actionable": True}],
        "recommended_primary_package": "package_2_printed_delivered_45k",
        "package_recommendation_reason": "Ticket machine shop needs a counter-ready English ordering kit.",
        "outreach_status": "new",
    }
    record.update(overrides)
    return record


def test_dossier_derives_required_states_for_ramen_ticket_machine():
    dossier = build_lead_evidence_dossier(_ready_record())

    assert dossier["ticket_machine_state"] == "present"
    assert dossier["english_menu_state"] == "missing"
    assert dossier["menu_complexity_state"] == "simple"
    assert dossier["izakaya_rules_state"] == "none_found"
    assert dossier["proof_items"][0]["customer_preview_eligible"] is True


def test_dossier_marks_ramen_ticket_machine_absent_when_explicitly_proven():
    dossier = build_lead_evidence_dossier(_ready_record(
        machine_evidence_found=False,
        evidence_classes=["official_html_menu", "ticket_machine_absence_evidence"],
        evidence_snippets=["醤油ラーメン 味玉 メニュー 券売機なし 席で注文"],
    ))

    assert dossier["ticket_machine_state"] == "absent"


def test_bad_snippets_are_not_customer_safe():
    snippets = [
        "Calendar check TEL_String 店舗検索",
        "醤油ラーメン 味玉 トッピング メニュー",
        "塚田農場 Calendar check",
    ]

    assert safe_customer_snippets(snippets) == ["醤油ラーメン 味玉 トッピング メニュー"]


def test_migration_maps_legacy_package_and_marks_ready():
    migrated, changes = migrate_lead_record(_ready_record(recommended_primary_package="package_A_in_person_48k"))

    assert migrated["recommended_primary_package"] == PACKAGE_2_KEY
    assert migrated["legacy_recommended_primary_package"] == "package_A_in_person_48k"
    assert migrated["launch_readiness_status"] == READINESS_READY
    assert "recommended_primary_package" in changes


def test_migration_sets_ready_operator_state_for_clean_supported_lead():
    migrated, changes = migrate_lead_record(_ready_record())

    assert migrated["operator_state"] == OPERATOR_READY
    assert migrated["operator_reason"] == "Ready for email outreach."
    assert migrated["contact_policy_evidence"]["usable_route_count"] == 1
    assert migrated["contact_policy_evidence"]["routes"][0]["decision"] == "usable"
    assert "operator_state" in changes
    assert "operator_reason" in changes
    assert "contact_policy_evidence" in changes


def test_public_business_email_source_evidence_is_preserved():
    migrated, _ = migrate_lead_record(_ready_record(
        contacts=[{
            "type": "email",
            "value": "owner@independent-ramen.jp",
            "actionable": True,
            "source": "official_site",
            "source_url": "https://independent-ramen.jp/contact",
        }],
    ))

    route = migrated["contact_policy_evidence"]["routes"][0]
    assert migrated["operator_state"] == OPERATOR_READY
    assert route["decision"] == "usable"
    assert route["source"] == "official_site"
    assert route["source_url"] == "https://independent-ramen.jp/contact"


def test_public_personal_domain_email_can_be_ready_when_listed_for_business():
    migrated, _ = migrate_lead_record(_ready_record(
        contacts=[{
            "type": "email",
            "value": "tanaka@tanaka-family.jp",
            "actionable": True,
            "source": "official_site",
            "source_url": "https://independent-ramen.jp/contact",
        }],
    ))

    assert migrated["operator_state"] == OPERATOR_READY
    assert migrated["contact_policy_evidence"]["routes"][0]["decision"] == "usable"


def test_third_party_restaurant_listing_email_can_be_ready_when_not_placeholder():
    migrated, _ = migrate_lead_record(_ready_record(
        contacts=[{
            "type": "email",
            "value": "shop@listing-restaurant.jp",
            "actionable": True,
            "source": "tabelog",
            "source_url": "https://tabelog.com/tokyo/A1303/A130301/example/",
        }],
    ))

    assert migrated["operator_state"] == OPERATOR_READY
    assert migrated["contact_policy_evidence"]["routes"][0]["source"] == "tabelog"


def test_supported_contact_form_can_be_operator_ready_without_email():
    migrated, _ = migrate_lead_record(_ready_record(
        email="",
        contacts=[{
            "type": "contact_form",
            "value": "https://independent-ramen.jp/contact",
            "actionable": True,
            "status": "discovered",
            "contact_form_profile": "supported_inquiry",
            "required_fields": ["お名前", "メールアドレス", "お問い合わせ内容"],
        }],
    ))

    assert migrated["operator_state"] == OPERATOR_READY
    assert migrated["operator_reason"] == "Ready for contact-form outreach review."
    assert migrated["contact_policy_evidence"]["routes"][0]["decision"] == "usable"


def test_email_refusal_text_blocks_operator_outreach():
    migrated, _ = migrate_lead_record(_ready_record(
        contacts=[{
            "type": "email",
            "value": "info@independent-ramen.jp",
            "actionable": True,
            "source": "official_site",
            "source_url": "https://independent-ramen.jp/contact",
            "page_text_hint": "営業メール・広告メールはお断りします",
        }],
    ))

    assert migrated["operator_state"] == OPERATOR_SKIP
    assert migrated["operator_reason"] == "Skipped because the listed email route blocks sales or advertising contact."
    assert migrated["contact_policy_evidence"]["routes"][0]["reason"] == "email_sales_or_ad_refusal"


def test_migration_omits_phone_and_social_routes_but_keeps_supported_form():
    migrated, changes = migrate_lead_record(_ready_record(
        primary_contact={"type": "phone", "value": "03-0000-0000", "actionable": True, "status": "discovered"},
        contacts=[
            {"type": "phone", "value": "03-0000-0000", "actionable": True, "status": "discovered"},
            {"type": "instagram", "value": "shop_account", "actionable": True, "status": "discovered"},
            {"type": "line", "value": "https://line.me/shop", "actionable": True, "status": "discovered"},
            {"type": "walk_in", "value": "東京都渋谷区1-1", "actionable": True, "status": "discovered"},
            {"type": "contact_form", "value": "https://example.test/contact", "actionable": True, "status": "discovered"},
        ],
    ))

    assert not any(contact["type"] in {"phone", "instagram", "line"} for contact in migrated["contacts"])
    walk_in = [contact for contact in migrated["contacts"] if contact["type"] == "walk_in"]
    assert walk_in
    assert walk_in[0]["actionable"] is False
    assert walk_in[0]["status"] == "reference_only"
    assert migrated["primary_contact"]["type"] == "contact_form"
    assert migrated["has_supported_contact_route"] is True
    assert "contacts" in changes
    assert "primary_contact" in changes


def test_phone_only_record_cannot_remain_launch_ready():
    migrated, changes = migrate_lead_record(_ready_record(
        contacts=[{"type": "phone", "value": "03-0000-0000", "actionable": True, "status": "discovered"}],
    ))

    assert migrated["contacts"] == []
    assert migrated["launch_readiness_status"] == READINESS_MANUAL
    assert migrated["operator_state"] == OPERATOR_REVIEW
    assert migrated["operator_reason"] == "Add a usable business email or real contact form."
    assert "no_supported_contact_route" in migrated["launch_readiness_reasons"]
    assert "contacts" in changes


def test_phone_required_contact_form_is_not_supported_route():
    migrated, changes = migrate_lead_record(_ready_record(
        primary_contact={
            "type": "contact_form",
            "value": "https://example.test/contact",
            "actionable": True,
            "status": "discovered",
            "required_fields": ["お名前", "電話番号", "メールアドレス"],
        },
        contacts=[{
            "type": "contact_form",
            "value": "https://example.test/contact",
            "actionable": True,
            "status": "discovered",
            "required_fields": ["お名前", "電話番号", "メールアドレス"],
        }],
    ))

    assert migrated["contacts"] == []
    assert migrated["has_supported_contact_route"] is False
    assert migrated["launch_readiness_status"] == READINESS_MANUAL
    assert "no_supported_contact_route" in migrated["launch_readiness_reasons"]
    assert "contacts" in changes


def test_reservation_contact_form_is_not_supported_route():
    migrated, changes = migrate_lead_record(_ready_record(
        primary_contact={
            "type": "contact_form",
            "value": "https://example.test/reservation",
            "actionable": True,
            "status": "discovered",
            "form_actions": ["/booking/confirm"],
        },
        contacts=[{
            "type": "contact_form",
            "value": "https://example.test/reservation",
            "actionable": True,
            "status": "discovered",
            "form_actions": ["/booking/confirm"],
        }],
    ))

    assert migrated["contacts"] == []
    assert migrated["contact_policy_evidence"]["routes"][0]["reason"] == "contact_form_not_real_inquiry"
    assert migrated["launch_readiness_status"] == READINESS_MANUAL
    assert migrated["operator_state"] == OPERATOR_SKIP
    assert migrated["operator_reason"] == "Skipped because the saved contact form is not a real inquiry form."
    assert "no_supported_contact_route" in migrated["launch_readiness_reasons"]
    assert "contacts" in changes


def test_social_url_mislabeled_as_contact_form_is_not_supported_route():
    migrated, changes = migrate_lead_record(_ready_record(
        primary_contact={
            "type": "contact_form",
            "value": "https://twitter.com/shop_account",
            "actionable": True,
            "status": "discovered",
        },
        contacts=[{
            "type": "contact_form",
            "value": "https://twitter.com/shop_account",
            "actionable": True,
            "status": "discovered",
        }],
    ))

    assert migrated["contacts"] == []
    assert migrated["has_supported_contact_route"] is False
    assert migrated["launch_readiness_status"] == READINESS_MANUAL
    assert "contacts" in changes


def test_chain_like_record_cannot_remain_launch_ready():
    migrated, _ = migrate_lead_record(_ready_record(business_name="Tsukada Nojo Shibuya Miyamasuzaka"))

    assert migrated["launch_readiness_status"] == READINESS_DISQUALIFIED
    assert migrated["outreach_status"] == "do_not_contact"
    assert migrated["operator_state"] == OPERATOR_SKIP
    assert "chain" in migrated["operator_reason"]
    assert "chain_or_franchise_like_business" in migrated["launch_readiness_reasons"]


def test_chain_infrastructure_snippet_cannot_remain_launch_ready():
    migrated, _ = migrate_lead_record(_ready_record(
        business_name="居酒屋みらい",
        primary_category_v1="izakaya",
        evidence_snippets=["飲み放題 コース 焼き鳥 メニュー 全国に35店舗を展開"],
    ))

    assert migrated["launch_readiness_status"] == READINESS_DISQUALIFIED
    assert migrated["outreach_status"] == "do_not_contact"
    assert "chain_or_franchise_like_business" in migrated["launch_readiness_reasons"]


def test_bracketed_preview_forces_manual_review():
    migrated, _ = migrate_lead_record(_ready_record(
        pitch_draft={"native": {"body": "醤油ラーメン -> [醤油ラーメン]"}},
        pitch_available=True,
        preview_available=True,
    ))

    assert migrated["launch_readiness_status"] == READINESS_MANUAL
    assert "saved_preview_or_pitch_contains_blocked_content" in migrated["launch_readiness_reasons"]
    assert migrated["pitch_draft"] is None
    assert migrated["legacy_pitch_draft"]["native"]["body"] == "醤油ラーメン -> [醤油ラーメン]"
    assert migrated["pitch_available"] is False
    assert migrated["preview_available"] is False
    assert migrated["preview_blocked_reason"] == "legacy_pitch_contains_bracketed_fallback"


def test_already_solved_english_record_cannot_remain_launch_ready():
    migrated, _ = migrate_lead_record(_ready_record(
        english_availability="usable_complete",
        english_menu_issue=False,
    ))

    assert migrated["launch_readiness_status"] == READINESS_DISQUALIFIED
    assert migrated["operator_state"] == OPERATOR_SKIP
    assert "usable English" in migrated["operator_reason"]
    assert "already_has_usable_english_solution" in migrated["launch_readiness_reasons"]


def test_multilingual_qr_record_cannot_remain_launch_ready():
    migrated, _ = migrate_lead_record(_ready_record(
        evidence_snippets=["Multilingual QR mobile order English support available ラーメン メニュー"],
    ))

    assert migrated["launch_readiness_status"] == READINESS_DISQUALIFIED
    assert migrated["operator_state"] == OPERATOR_SKIP
    assert "multilingual" in migrated["operator_reason"]
    assert "multilingual_qr_or_ordering_solution_present" in migrated["launch_readiness_reasons"]


def test_weak_source_coverage_forces_manual_review():
    migrated, _ = migrate_lead_record(_ready_record(
        source_count=1,
        source_coverage_score=32,
        coverage_signals={
            "source_count": 1,
            "has_official_site": False,
            "has_portal_menu": False,
            "has_english_menu_signal": False,
            "operator_found": False,
            "contact_found": True,
            "portal_only": False,
            "matching_phone_or_address": False,
        },
    ))

    assert migrated["launch_readiness_status"] == READINESS_MANUAL
    assert "weak_source_coverage" in migrated["launch_readiness_reasons"]
    assert "no_official_site_confirmed" in migrated["launch_readiness_reasons"]
    assert "weak_entity_resolution" in migrated["launch_readiness_reasons"]
    assert "low_source_coverage_score" in migrated["launch_readiness_reasons"]


def test_strong_source_coverage_can_remain_ready():
    migrated, _ = migrate_lead_record(_ready_record(
        source_count=3,
        source_coverage_score=74,
        coverage_signals={
            "source_count": 3,
            "has_official_site": True,
            "has_portal_menu": True,
            "has_english_menu_signal": False,
            "operator_found": False,
            "contact_found": True,
            "portal_only": False,
            "matching_phone_or_address": True,
        },
    ))

    assert migrated["launch_readiness_status"] == READINESS_READY
    assert migrated["launch_readiness_reasons"] == ["qualified_with_safe_proof_and_contact_route"]


def test_non_japan_record_cannot_remain_launch_ready():
    migrated, _ = migrate_lead_record(_ready_record(
        address="71-28 Roosevelt Ave, Jackson Heights, NY 11372",
    ))

    assert migrated["launch_readiness_status"] == READINESS_DISQUALIFIED
    assert migrated["outreach_status"] == "do_not_contact"
    assert migrated["operator_state"] == OPERATOR_SKIP
    assert "Japan shop location" in migrated["operator_reason"]
    assert "not_in_japan" in migrated["launch_readiness_reasons"]


def test_non_v1_category_is_operator_skip():
    migrated, _ = migrate_lead_record(_ready_record(
        business_name="Quiet Cafe",
        primary_category_v1="cafe",
        category="cafe",
        evidence_snippets=["コーヒー ケーキ メニュー"],
    ))

    assert migrated["launch_readiness_status"] == READINESS_DISQUALIFIED
    assert migrated["operator_state"] == OPERATOR_SKIP
    assert "outside ramen or izakaya" in migrated["operator_reason"]


def test_closed_business_evidence_is_operator_skip():
    migrated, _ = migrate_lead_record(_ready_record(
        evidence_snippets=["閉店しました ラーメン メニュー"],
    ))

    assert migrated["operator_state"] == OPERATOR_SKIP
    assert migrated["operator_reason"] == "Skipped because the shop appears to be closed."


def test_operator_state_marks_sent_records_done():
    migrated, _ = migrate_lead_record(_ready_record(outreach_status="sent"))

    assert migrated["operator_state"] == OPERATOR_DONE
    assert migrated["operator_reason"] == "Done because the first outreach was sent."


def test_operator_state_skips_placeholder_email_route():
    migrated, _ = migrate_lead_record(_ready_record(
        email="test@example.com",
        contacts=[{"type": "email", "value": "test@example.com", "actionable": True}],
    ))

    assert migrated["operator_state"] == OPERATOR_SKIP
    assert migrated["operator_reason"] == "Skipped because the saved email route is a placeholder or invalid."
    assert migrated["contact_policy_evidence"]["routes"][0]["reason"] == "email_placeholder"


def test_operator_state_reviews_missing_package_reason():
    migrated, _ = migrate_lead_record(_ready_record(package_recommendation_reason=""))

    assert migrated["launch_readiness_status"] == READINESS_READY
    assert migrated["operator_state"] == OPERATOR_REVIEW
    assert migrated["operator_reason"] == "Choose a recommended package before outreach."


def test_operator_state_reviews_missing_japan_location():
    migrated, _ = migrate_lead_record(_ready_record(address="", phone="", city=""))

    assert migrated["launch_readiness_status"] == READINESS_READY
    assert migrated["operator_state"] == OPERATOR_REVIEW
    assert migrated["operator_reason"] == "Confirm this shop has a physical location in Japan."


def test_state_migration_persists_changed_leads(tmp_path):
    leads = tmp_path / "leads"
    leads.mkdir()
    path = leads / "wrm-ready.json"
    path.write_text(json.dumps(_ready_record(recommended_primary_package="package_A_in_person_48k")), encoding="utf-8")

    result = migrate_state_leads(state_root=tmp_path)
    stored = json.loads(path.read_text(encoding="utf-8"))

    assert result["changed"][0]["lead_id"] == "wrm-ready"
    assert stored["recommended_primary_package"] == PACKAGE_2_KEY
    assert stored["launch_readiness_status"] == READINESS_READY
