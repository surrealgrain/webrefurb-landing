"""Tests for persisted state drift audits."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.constants import PROJECT_ROOT
from pipeline.state_audit import audit_state_leads, expected_dark_assets, repair_state_leads


def _write_lead(tmp_path: Path, **overrides):
    leads = tmp_path / "leads"
    leads.mkdir(exist_ok=True)
    lead = {
        "lead_id": "wrm-audit",
        "business_name": "監査ラーメン",
        "lead": True,
        "outreach_status": "draft",
        "launch_readiness_status": "ready_for_outreach",
        "launch_readiness_reasons": ["qualified_with_safe_proof_and_contact_route"],
        "primary_category_v1": "ramen",
        "establishment_profile": "ramen_ticket_machine",
        "outreach_classification": "menu_and_machine",
        "machine_evidence_found": True,
        "evidence_urls": ["https://audit.example.jp/menu"],
        "evidence_snippets": ["醤油ラーメン 味玉 トッピング メニュー"],
        "contacts": [{"type": "email", "value": "owner@audit.example.jp", "actionable": True}],
        "outreach_assets_selected": [
            str(PROJECT_ROOT / "assets" / "templates" / "ramen_food_menu.html"),
            str(PROJECT_ROOT / "assets" / "templates" / "ticket_machine_guide.html"),
        ],
    }
    lead.update(overrides)
    path = leads / f"{lead['lead_id']}.json"
    path.write_text(json.dumps(lead, ensure_ascii=False), encoding="utf-8")
    return lead


def _codes(result):
    return {finding["code"] for finding in result["findings"]}


def test_state_audit_accepts_correct_dark_assets(tmp_path):
    _write_lead(tmp_path)
    result = audit_state_leads(state_root=tmp_path)
    assert result["ok"] is True
    assert result["checked"] == 1


def test_state_audit_rejects_ready_non_japan_lead(tmp_path):
    _write_lead(
        tmp_path,
        address="245 W 51st St, New York, NY 10019",
    )

    result = audit_state_leads(state_root=tmp_path)

    assert result["ok"] is False
    assert "ready_lead_not_in_japan" in _codes(result)


def test_repair_state_leads_disqualifies_non_japan_lead(tmp_path):
    _write_lead(
        tmp_path,
        address="71-28 Roosevelt Ave, Jackson Heights, NY 11372",
    )

    result = repair_state_leads(state_root=tmp_path)
    stored = json.loads((tmp_path / "leads" / "wrm-audit.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert stored["launch_readiness_status"] == "disqualified"
    assert stored["outreach_status"] == "do_not_contact"
    assert "not_in_japan" in stored["launch_readiness_reasons"]


def test_state_audit_rejects_stale_ready_branch_chain_lead(tmp_path):
    _write_lead(
        tmp_path,
        business_name="Ramen Maru Shinjuku Ten",
    )

    result = audit_state_leads(state_root=tmp_path)

    assert result["ok"] is False
    assert "launch_readiness_drift" in _codes(result)
    assert result["readiness_report"] == [{
        "lead_id": "wrm-audit",
        "from_status": "ready_for_outreach",
        "from_reasons": ["qualified_with_safe_proof_and_contact_route"],
        "to_status": "disqualified",
        "to_reasons": ["chain_or_franchise_like_business"],
        "summary": "ready_for_outreach -> disqualified: chain_or_franchise_like_business",
    }]


def test_repair_state_leads_migrates_stale_ready_branch_and_clears_samples(tmp_path):
    lead = _write_lead(
        tmp_path,
        business_name="Ramen Maru Shinjuku Ten",
        outreach_draft_subject="英語注文ガイド制作のご提案",
        outreach_draft_body="添付のサンプルをご覧ください。",
        outreach_draft_english_body="Please review the attached sample.",
    )

    result = repair_state_leads(state_root=tmp_path)
    repaired = json.loads((tmp_path / "leads" / f"{lead['lead_id']}.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert repaired["launch_readiness_status"] == "disqualified"
    assert repaired["outreach_status"] == "do_not_contact"
    assert repaired["outreach_assets_selected"] == []
    assert repaired["outreach_draft_subject"] is None
    assert repaired["outreach_draft_body"] is None
    assert repaired["outreach_draft_english_body"] is None
    assert result["repaired"][0]["readiness_change"]["summary"] == (
        "ready_for_outreach -> disqualified: chain_or_franchise_like_business"
    )


def test_state_audit_rejects_legacy_cream_assets(tmp_path):
    _write_lead(
        tmp_path,
        outreach_assets_selected=[
            str(PROJECT_ROOT / "state" / "builds" / "p1-single-section-layout" / "food_menu_print_ready.pdf")
        ],
    )

    result = audit_state_leads(state_root=tmp_path)

    assert result["ok"] is False
    assert "legacy_or_cream_asset_reference" in _codes(result)
    assert "outreach_assets_do_not_match_dark_profile" in _codes(result)


def test_state_audit_rejects_wrong_profile_template(tmp_path):
    _write_lead(
        tmp_path,
        primary_category_v1="izakaya",
        establishment_profile="izakaya_drink_heavy",
        outreach_classification="menu_only",
        machine_evidence_found=False,
        outreach_assets_selected=[str(PROJECT_ROOT / "assets" / "templates" / "ramen_food_menu.html")],
    )

    result = audit_state_leads(state_root=tmp_path)

    assert result["ok"] is False
    assert "outreach_assets_do_not_match_dark_profile" in _codes(result)


def test_state_audit_rejects_dnc_records_with_assets(tmp_path):
    _write_lead(
        tmp_path,
        outreach_status="do_not_contact",
        launch_readiness_status="disqualified",
        outreach_assets_selected=[str(PROJECT_ROOT / "assets" / "templates" / "ramen_food_menu.html")],
    )

    result = audit_state_leads(state_root=tmp_path)

    assert result["ok"] is False
    assert "outreach_assets_do_not_match_dark_profile" in _codes(result)


def test_state_audit_rejects_poisoned_name_when_locked_name_exists(tmp_path):
    _write_lead(
        tmp_path,
        business_name="QA Phase10 Ramen",
        locked_business_name="青空ラーメン",
        business_name_locked=True,
        outreach_draft_body="QA Phase10 Ramen ご担当者様\n\n本文",
    )

    result = audit_state_leads(state_root=tmp_path)

    assert result["ok"] is False
    assert "business_name_diverges_from_locked_name" in _codes(result)
    assert "poisoned_name_in_customer_text" in _codes(result)


def test_expected_dark_assets_maps_profiles():
    assert expected_dark_assets({
        "lead": True,
        "outreach_status": "draft",
        "primary_category_v1": "izakaya",
        "establishment_profile": "izakaya_course_heavy",
        "outreach_classification": "menu_only",
    }) == [str(PROJECT_ROOT / "assets" / "templates" / "izakaya_food_drinks_menu.html")]
    assert expected_dark_assets({
        "lead": True,
        "outreach_status": "draft",
        "primary_category_v1": "ramen",
        "establishment_profile": "ramen_ticket_machine",
        "outreach_classification": "menu_and_machine",
    }) == [
        str(PROJECT_ROOT / "assets" / "templates" / "ramen_food_menu.html"),
        str(PROJECT_ROOT / "assets" / "templates" / "ticket_machine_guide.html"),
    ]


def test_izakaya_dark_template_does_not_show_ramen_menu_items():
    html = (PROJECT_ROOT / "assets" / "templates" / "izakaya_food_menu.html").read_text(encoding="utf-8")

    assert "Signature Dishes" in html
    assert "名物料理" in html
    assert "Soy Sauce Ramen" not in html
    assert "Creamy Chicken Broth Ramen" not in html
    assert "醤油ラーメン" not in html


def test_izakaya_food_drinks_template_contains_drinks_and_rules():
    html = (PROJECT_ROOT / "assets" / "templates" / "izakaya_food_drinks_menu.html").read_text(encoding="utf-8")

    assert "Food Menu" in html
    assert "Drinks Menu" in html
    assert "Nomihodai" in html
    assert "Course Flow" in html
    assert "data-slot=\"seal-text\"" in html
    assert "Creamy Chicken Broth Ramen" not in html


def test_state_audit_rejects_izakaya_food_only_template_when_claiming_food_drinks(tmp_path):
    _write_lead(
        tmp_path,
        primary_category_v1="izakaya",
        establishment_profile="izakaya_drink_heavy",
        outreach_classification="menu_only",
        machine_evidence_found=False,
        outreach_assets_selected=[str(PROJECT_ROOT / "assets" / "templates" / "izakaya_food_menu.html")],
    )

    result = audit_state_leads(state_root=tmp_path)

    assert result["ok"] is False
    assert "outreach_assets_do_not_match_dark_profile" in _codes(result)
    assert "izakaya_food_drinks_claim_uses_food_only_template" in _codes(result)


def test_state_audit_rejects_saved_draft_claiming_attachment_without_assets(tmp_path):
    _write_lead(
        tmp_path,
        contacts=[{"type": "contact_form", "actionable": True}],
        outreach_assets_selected=[],
        outreach_draft_body="添付のサンプルをご覧ください。",
        outreach_draft_english_body="Please review the attached sample.",
    )

    result = audit_state_leads(state_root=tmp_path)

    assert result["ok"] is False
    assert "draft_mentions_attachment_without_assets" in _codes(result)


def test_repair_state_leads_clears_attachment_claim_draft_when_route_has_no_assets(tmp_path):
    lead = _write_lead(
        tmp_path,
        contacts=[{"type": "contact_form", "actionable": True}],
        outreach_assets_selected=[],
        outreach_draft_body="添付のサンプルをご覧ください。",
        outreach_draft_english_body="Please review the attached sample.",
        outreach_draft_subject="英語メニュー制作のご提案",
    )

    result = repair_state_leads(state_root=tmp_path)
    repaired = json.loads((tmp_path / "leads" / f"{lead['lead_id']}.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert repaired["outreach_draft_body"] is None
    assert repaired["outreach_draft_english_body"] is None
    assert repaired["outreach_draft_subject"] is None


def test_repair_state_leads_normalizes_assets_and_locked_name(tmp_path):
    lead = _write_lead(
        tmp_path,
        business_name="QA Phase10 Ramen",
        locked_business_name="青空ラーメン",
        business_name_locked=True,
        outreach_draft_body="QA Phase10 Ramen ご担当者様\n\n本文",
        outreach_assets_selected=[
            str(PROJECT_ROOT / "state" / "builds" / "p1-single-section-layout" / "food_menu_print_ready.pdf")
        ],
    )

    result = repair_state_leads(state_root=tmp_path)
    repaired = json.loads((tmp_path / "leads" / f"{lead['lead_id']}.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["repaired"][0]["lead_id"] == "wrm-audit"
    assert repaired["business_name"] == "青空ラーメン"
    assert "青空ラーメン ご担当者様" in repaired["outreach_draft_body"]
    assert repaired["outreach_assets_selected"] == expected_dark_assets(repaired)


def test_state_audit_rejects_legacy_launch_smoke_proof_asset(tmp_path):
    lead = _write_lead(tmp_path)
    smoke_dir = tmp_path / "launch_smoke_tests"
    smoke_dir.mkdir()
    (smoke_dir / "smoke-test.json").write_text(json.dumps({
        "smoke_test_id": "smoke-test",
        "leads": [{
            "lead_id": lead["lead_id"],
            "proof_asset": str(PROJECT_ROOT / "state" / "qa-screenshots" / "phase10-sample-ramen-preview-desktop.png"),
        }],
    }), encoding="utf-8")

    result = audit_state_leads(state_root=tmp_path)

    assert result["ok"] is False
    assert "launch_proof_asset_does_not_match_dark_profile" in _codes(result)
    assert "legacy_or_cream_asset_reference" in _codes(result)


def test_repair_state_leads_updates_launch_smoke_proof_asset(tmp_path):
    lead = _write_lead(tmp_path)
    smoke_dir = tmp_path / "launch_smoke_tests"
    smoke_dir.mkdir()
    smoke_path = smoke_dir / "smoke-test.json"
    smoke_path.write_text(json.dumps({
        "smoke_test_id": "smoke-test",
        "leads": [{
            "lead_id": lead["lead_id"],
            "proof_asset": str(PROJECT_ROOT / "state" / "qa-screenshots" / "phase10-sample-ramen-preview-desktop.png"),
        }],
    }), encoding="utf-8")

    result = repair_state_leads(state_root=tmp_path)
    repaired_smoke = json.loads(smoke_path.read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert repaired_smoke["leads"][0]["proof_asset"] == expected_dark_assets(lead)[0]


def test_repository_state_audit_has_no_findings():
    result = audit_state_leads(state_root=PROJECT_ROOT / "state")

    assert result["ok"] is True, result["findings"]
