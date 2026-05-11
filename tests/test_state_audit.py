"""Tests for persisted state drift audits."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.constants import PROJECT_ROOT
from pipeline.lead_dossier import migrate_lead_record
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
        "recommended_primary_package": "package_2_printed_delivered_45k",
        "package_recommendation_reason": "ramen_ticket_machine_needs_counter_ready_mapping",
        "custom_quote_reason": "",
        "address": "東京都渋谷区1-1-1",
        "evidence_urls": ["https://audit.example.jp/menu"],
        "evidence_snippets": ["醤油ラーメン 味玉 トッピング メニュー"],
        "contacts": [{"type": "email", "value": "owner@audit.example.jp", "actionable": True}],
        "outreach_assets_selected": [],
    }
    lead, _ = migrate_lead_record(lead)
    lead.update(overrides)
    path = leads / f"{lead['lead_id']}.json"
    path.write_text(json.dumps(lead, ensure_ascii=False), encoding="utf-8")
    return lead


def _codes(result):
    return {finding["code"] for finding in result["findings"]}


def _write_approved_contact_only_candidate(tmp_path: Path, **overrides):
    lead = _write_lead(tmp_path)
    path = tmp_path / "leads" / f"{lead['lead_id']}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record.update({
        "lead": False,
        "review_status": "approved",
        "verification_status": "verified",
        "rejection_reason": "no_verified_business_email_route",
        "launch_readiness_status": "disqualified",
        "launch_readiness_reasons": ["not_a_binary_true_lead"],
        "outreach_status": "do_not_contact",
        "operator_state": "skip",
        "send_ready_checked": False,
        "send_ready_checked_at": "",
        "send_ready_checklist": [],
        "outreach_draft_subject": None,
        "outreach_draft_body": None,
        "outreach_draft_english_body": None,
        "outreach_english_body": None,
    })
    record.update(overrides)
    record, _ = migrate_lead_record(record)
    record.update({
        "review_status": "approved",
        "rejection_reason": str(record.get("rejection_reason") or "no_verified_business_email_route"),
        "send_ready_checked": record.get("send_ready_checked") is True,
        "send_ready_checked_at": str(record.get("send_ready_checked_at") or ""),
        "send_ready_checklist": list(record.get("send_ready_checklist") or []),
        "outreach_draft_subject": record.get("outreach_draft_subject"),
        "outreach_draft_body": record.get("outreach_draft_body"),
        "outreach_draft_english_body": record.get("outreach_draft_english_body"),
        "outreach_english_body": record.get("outreach_english_body"),
    })
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return record


def test_state_audit_accepts_correct_dark_assets(tmp_path):
    _write_lead(tmp_path)
    result = audit_state_leads(state_root=tmp_path)
    assert result["ok"] is True
    assert result["checked"] == 1
    assert result["state_counts"]["launch_readiness_status"] == {"ready_for_outreach": 1}
    assert result["state_counts"]["operator_state"] == {"ready": 1}


def test_state_audit_allows_approved_false_contact_only_candidate(tmp_path):
    _write_approved_contact_only_candidate(tmp_path)

    result = audit_state_leads(state_root=tmp_path)

    assert result["ok"] is True


def test_state_audit_rejects_approved_false_non_shop_source_candidate(tmp_path):
    _write_approved_contact_only_candidate(
        tmp_path,
        business_name="東京、定番つけ麺20選 - タイムアウト東京",
        locked_business_name="東京、定番つけ麺20選 - タイムアウト東京",
        rejection_reason="source_not_exact_single_shop_article",
    )

    result = audit_state_leads(state_root=tmp_path)

    assert result["ok"] is False
    assert "approved_false_lead_not_contact_only" in _codes(result)


def test_state_audit_rejects_approved_contact_only_with_poisoned_entity_name(tmp_path):
    _write_approved_contact_only_candidate(
        tmp_path,
        business_name="(silve856)",
        locked_business_name="(silve856)",
    )

    result = audit_state_leads(state_root=tmp_path)

    assert result["ok"] is False
    assert "approved_contact_only_entity_quality_flag" in _codes(result)


def test_state_audit_rejects_approved_true_lead_not_ready(tmp_path):
    _write_lead(
        tmp_path,
        review_status="approved",
        launch_readiness_status="manual_review",
        launch_readiness_reasons=["manual_review_required"],
    )

    result = audit_state_leads(state_root=tmp_path)

    assert result["ok"] is False
    assert "approved_true_lead_not_ready" in _codes(result)


def test_state_audit_allows_approved_sent_lead_not_ready(tmp_path):
    _write_lead(
        tmp_path,
        review_status="approved",
        outreach_status="sent",
        operator_state="done",
        operator_reason="Done because the first outreach was sent.",
        launch_readiness_status="manual_review",
        launch_readiness_reasons=["no_customer_safe_proof_item"],
        evidence_urls=[],
        evidence_snippets=[],
        proof_items=[],
        lead_evidence_dossier={
            "proof_items": [],
            "proof_strength": "none",
            "readiness_reasons": ["no_customer_safe_proof_item"],
            "ready_to_contact": False,
            "ticket_machine_state": "absent",
            "english_menu_state": "unknown",
            "izakaya_rules_state": "unknown",
            "menu_complexity_state": "medium",
        },
    )

    result = audit_state_leads(state_root=tmp_path)

    assert result["ok"] is True
    assert "approved_true_lead_not_ready" not in _codes(result)


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


def test_state_audit_rejects_retired_first_contact_assets(tmp_path):
    attachment = tmp_path / "retired-first-contact-sample.pdf"
    attachment.write_text("retired", encoding="utf-8")
    _write_lead(
        tmp_path,
        outreach_assets_selected=[str(attachment)],
    )

    result = audit_state_leads(state_root=tmp_path)

    assert result["ok"] is False
    assert "outreach_assets_do_not_match_dark_profile" in _codes(result)
    assert "first_contact_attachments_not_supported" in _codes(result)


def test_state_audit_rejects_any_first_contact_attachment_for_qualified_lead(tmp_path):
    attachment = tmp_path / "wrong-first-contact-sample.pdf"
    attachment.write_text("retired", encoding="utf-8")
    _write_lead(
        tmp_path,
        primary_category_v1="izakaya",
        establishment_profile="izakaya_drink_heavy",
        outreach_classification="menu_only",
        machine_evidence_found=False,
        outreach_assets_selected=[str(attachment)],
    )

    result = audit_state_leads(state_root=tmp_path)

    assert result["ok"] is False
    assert "outreach_assets_do_not_match_dark_profile" in _codes(result)


def test_state_audit_rejects_dnc_records_with_assets(tmp_path):
    attachment = tmp_path / "blocked-contact-sample.pdf"
    attachment.write_text("retired", encoding="utf-8")
    _write_lead(
        tmp_path,
        outreach_status="do_not_contact",
        launch_readiness_status="disqualified",
        outreach_assets_selected=[str(attachment)],
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


def test_state_audit_allows_quarantined_restaurant_email_reject_name(tmp_path):
    _write_lead(
        tmp_path,
        lead_id="wrm-email-v2-round-2-elissa-828-5e83eb8e",
        business_name="elissa_828@hotmail.com",
        locked_business_name="elissa_828@hotmail.com",
        business_name_locked=True,
        source_query="restaurant_email_import",
        source_file="restaurant_email_leads.json",
        verification_status="rejected",
        pitch_readiness_status="rejected",
        pitch_ready=False,
        candidate_inbox_status="rejected",
        outreach_status="needs_review",
        launch_readiness_status="manual_review",
        launch_readiness_reasons=[
            "restaurant_email_verification_not_promoted",
            "restaurant_email_verification_rejected",
        ],
    )

    result = audit_state_leads(state_root=tmp_path)

    assert "authoritative_business_name_suspicious" not in _codes(result)


def test_expected_dark_assets_maps_profiles():
    assert expected_dark_assets({
        "lead": True,
        "outreach_status": "draft",
        "primary_category_v1": "izakaya",
        "establishment_profile": "izakaya_course_heavy",
        "outreach_classification": "menu_only",
    }) == []
    assert expected_dark_assets({
        "lead": True,
        "outreach_status": "draft",
        "primary_category_v1": "izakaya",
        "establishment_profile": "izakaya_robatayaki",
        "outreach_classification": "menu_only",
    }) == []
    assert expected_dark_assets({
        "lead": True,
        "outreach_status": "draft",
        "primary_category_v1": "ramen",
        "establishment_profile": "ramen_ticket_machine",
        "outreach_classification": "menu_and_machine",
    }) == []


def test_state_audit_rejects_first_contact_attachments(tmp_path):
    attachment = tmp_path / "first-contact-sample.pdf"
    attachment.write_text("not used by QR-first outreach", encoding="utf-8")
    _write_lead(
        tmp_path,
        outreach_assets_selected=[str(attachment)],
    )

    result = audit_state_leads(state_root=tmp_path)

    assert result["ok"] is False
    assert "outreach_assets_do_not_match_dark_profile" in _codes(result)
    assert "first_contact_attachments_not_supported" in _codes(result)


def test_state_audit_rejects_saved_draft_claiming_attachment_without_assets(tmp_path):
    _write_lead(
        tmp_path,
        contacts=[{"type": "contact_form", "value": "https://example.test/contact", "actionable": True}],
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
        contacts=[{"type": "contact_form", "value": "https://example.test/contact", "actionable": True}],
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


def test_repair_state_leads_quarantines_ready_stale_copy_and_final_check(tmp_path):
    lead = _write_lead(
        tmp_path,
        send_ready_checked=True,
        send_ready_checked_at="2026-05-03T00:00:00+00:00",
        send_ready_checklist=["copy_checked"],
        tailoring_audit={"passed": True, "input_hash": "old-hash"},
        outreach_draft_subject="英語メニュー制作のご提案",
        outreach_draft_body="突然のご連絡にて失礼いたします。\n添付のサンプルをご覧ください。",
    )
    final_dir = tmp_path / "final_checks" / lead["lead_id"]
    final_dir.mkdir(parents=True)
    (final_dir / "menu.html").write_text("<html></html>", encoding="utf-8")

    result = repair_state_leads(state_root=tmp_path)
    repaired = json.loads((tmp_path / "leads" / f"{lead['lead_id']}.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert repaired["launch_readiness_status"] == "manual_review"
    assert repaired["outreach_status"] == "needs_review"
    assert repaired["send_ready_checked"] is False
    assert repaired["outreach_draft_body"] is None
    assert not final_dir.exists()
    assert any(reason.startswith("stale_copy:") for reason in repaired["launch_readiness_reasons"])


def test_repair_state_leads_quarantines_ready_entity_title(tmp_path):
    lead = _write_lead(
        tmp_path,
        business_name="東京、定番つけ麺20選 - タイムアウト東京",
        locked_business_name="東京、定番つけ麺20選 - タイムアウト東京",
    )

    result = repair_state_leads(state_root=tmp_path)
    repaired = json.loads((tmp_path / "leads" / f"{lead['lead_id']}.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert repaired["launch_readiness_status"] == "manual_review"
    assert "entity_quality:media_blog_pr_or_directory_title" in repaired["launch_readiness_reasons"]


def test_repair_state_leads_quarantines_ready_placeholder_email(tmp_path):
    lead = _write_lead(
        tmp_path,
        contacts=[{"type": "email", "value": "%22@gmail.com", "actionable": True}],
        email="%22@gmail.com",
    )

    result = repair_state_leads(state_root=tmp_path)
    repaired = json.loads((tmp_path / "leads" / f"{lead['lead_id']}.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert repaired["launch_readiness_status"] == "manual_review"
    assert any(reason.startswith("placeholder_email:") for reason in repaired["launch_readiness_reasons"])


def test_repair_state_leads_rescores_import_default_package_without_quarantine(tmp_path):
    lead = _write_lead(
        tmp_path,
        primary_category_v1="izakaya",
        category="izakaya",
        evidence_snippets=["飲み放題 コース 居酒屋 メニュー"],
        course_or_drink_plan_evidence_found=True,
        izakaya_rules_state="unknown",
        recommended_primary_package="package_1_remote_30k",
        package_recommendation_reason="Imported public email lead; start with remote English ordering files until menu scope is reviewed.",
    )

    result = repair_state_leads(state_root=tmp_path)
    repaired = json.loads((tmp_path / "leads" / f"{lead['lead_id']}.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert repaired["launch_readiness_status"] == "ready_for_outreach"
    assert repaired["recommended_primary_package"] == "english_qr_menu_65k"
    assert repaired["package_recommendation_reason"] == "izakaya_english_qr_menu_show_staff_list_fit"
    assert not any(reason.startswith("package_rescore:") for reason in repaired["launch_readiness_reasons"])


def test_repair_state_leads_restores_resolved_package_only_quarantine(tmp_path):
    lead = _write_lead(
        tmp_path,
        primary_category_v1="izakaya",
        category="izakaya",
        evidence_snippets=["居酒屋 メニュー 焼き鳥 生ビール"],
        recommended_primary_package="package_2_printed_delivered_45k",
        package_recommendation_reason="izakaya_menu_needs_ordering_materials_without_live_update_signal",
        launch_readiness_status="manual_review",
        launch_readiness_reasons=["manual_review_required", "production_readiness_regeneration_required"],
        manual_review_required=True,
        outreach_status="needs_review",
    )

    result = repair_state_leads(state_root=tmp_path)
    repaired = json.loads((tmp_path / "leads" / f"{lead['lead_id']}.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert repaired["launch_readiness_status"] == "ready_for_outreach"
    assert repaired["launch_readiness_reasons"] == ["qualified_with_safe_proof_and_contact_route"]
    assert repaired["manual_review_required"] is False
    assert repaired["outreach_status"] == "draft"


def test_repair_state_leads_normalizes_assets_and_locked_name(tmp_path):
    lead = _write_lead(
        tmp_path,
        business_name="QA Phase10 Ramen",
        locked_business_name="青空ラーメン",
        business_name_locked=True,
        outreach_draft_body="QA Phase10 Ramen ご担当者様\n\n本文",
        outreach_assets_selected=[str(tmp_path / "retired-first-contact-sample.pdf")],
    )

    result = repair_state_leads(state_root=tmp_path)
    repaired = json.loads((tmp_path / "leads" / f"{lead['lead_id']}.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["repaired"][0]["lead_id"] == "wrm-audit"
    assert repaired["business_name"] == "青空ラーメン"
    assert repaired["outreach_draft_body"] in {"", None}
    assert repaired["outreach_status"] == "needs_review"
    assert repaired["outreach_assets_selected"] == []


def test_repository_state_audit_has_no_findings():
    result = audit_state_leads(state_root=PROJECT_ROOT / "state")

    assert result["ok"] is True, result["findings"]
