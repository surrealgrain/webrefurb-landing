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


def test_bracketed_preview_forces_manual_review():
    migrated, _ = migrate_lead_record(_ready_record(
        pitch_draft={"native": {"body": "醤油ラーメン -> [醤油ラーメン]"}},
    ))

    assert migrated["launch_readiness_status"] == READINESS_MANUAL
    assert "saved_preview_or_pitch_contains_blocked_content" in migrated["launch_readiness_reasons"]


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
