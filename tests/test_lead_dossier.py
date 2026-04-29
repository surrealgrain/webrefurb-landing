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
        "evidence_urls": ["https://example.test/menu"],
        "evidence_snippets": ["醤油ラーメン 味玉 トッピング メニュー"],
        "contacts": [{"type": "email", "value": "owner@example.test", "actionable": True}],
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


def test_chain_like_record_cannot_remain_launch_ready():
    migrated, _ = migrate_lead_record(_ready_record(business_name="Tsukada Nojo Shibuya Miyamasuzaka"))

    assert migrated["launch_readiness_status"] == READINESS_DISQUALIFIED
    assert migrated["outreach_status"] == "do_not_contact"
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
    assert "already_has_usable_english_solution" in migrated["launch_readiness_reasons"]


def test_multilingual_qr_record_cannot_remain_launch_ready():
    migrated, _ = migrate_lead_record(_ready_record(
        evidence_snippets=["Multilingual QR mobile order English support available ラーメン メニュー"],
    ))

    assert migrated["launch_readiness_status"] == READINESS_DISQUALIFIED
    assert "multilingual_qr_or_ordering_solution_present" in migrated["launch_readiness_reasons"]


def test_non_japan_record_cannot_remain_launch_ready():
    migrated, _ = migrate_lead_record(_ready_record(
        address="71-28 Roosevelt Ave, Jackson Heights, NY 11372",
    ))

    assert migrated["launch_readiness_status"] == READINESS_DISQUALIFIED
    assert migrated["outreach_status"] == "do_not_contact"
    assert "not_in_japan" in migrated["launch_readiness_reasons"]


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
