from __future__ import annotations

from pipeline.review_enrichment import (
    build_needs_more_info_enrichment_plan,
    write_needs_more_info_enrichment_plan,
)
from pipeline.utils import write_json


def _write_record(tmp_path, record: dict) -> None:
    write_json(tmp_path / "leads" / f"{record['lead_id']}.json", record)


def _lead(
    lead_id: str,
    *,
    pitch_status: str = "needs_email_review",
    contact_type: str = "email",
    outcome: str = "needs_more_info",
) -> dict:
    contact_value = f"{lead_id}@example.test" if contact_type == "email" else "https://shop.example.test/contact"
    record = {
        "lead_id": lead_id,
        "lead": True,
        "business_name": f"Shop {lead_id}",
        "city": "Tokyo",
        "address": "東京都新宿区1-1-1",
        "primary_category_v1": "ramen",
        "type_of_restaurant": "ramen",
        "menu_type": "ramen",
        "establishment_profile": "ramen_only",
        "quality_tier": "high",
        "source_strength": "official_site",
        "email_verification_status": "needs_review" if pitch_status == "needs_email_review" else "verified",
        "name_verification_status": "single_source" if pitch_status == "needs_name_review" else "verified",
        "city_verification_status": "verified",
        "category_verification_status": "needs_review" if pitch_status == "needs_scope_review" else "verified",
        "chain_verification_status": "verified",
        "verification_status": "needs_review",
        "pitch_card_status": pitch_status,
        "manual_review_required": True,
        "launch_readiness_status": "manual_review",
        "outreach_status": "needs_review",
        "pitch_ready": False,
        "contacts": [{"type": contact_type, "value": contact_value, "actionable": True}],
        "operator_review_outcome": outcome,
        "operator_review_note": "No-send review still needs confirmation.",
        "review_status": "needs_more_info",
    }
    if contact_type == "email":
        record["email"] = contact_value
    return record


def test_needs_more_info_enrichment_groups_reviewed_cards_without_promotion(tmp_path):
    _write_record(tmp_path, _lead("wrm-email", pitch_status="needs_email_review"))
    _write_record(tmp_path, _lead("wrm-name", pitch_status="needs_name_review"))
    _write_record(tmp_path, _lead("wrm-scope", pitch_status="needs_scope_review"))
    _write_record(tmp_path, _lead("wrm-form", pitch_status="reviewable", contact_type="contact_form"))
    _write_record(tmp_path, _lead("wrm-hold", outcome="hold"))

    plan = build_needs_more_info_enrichment_plan(state_root=tmp_path, batch_size=2)

    assert plan["scope"] == "no_send_needs_more_info_enrichment"
    assert plan["no_send_safety"]["real_outbound_allowed"] is False
    assert plan["no_send_safety"]["email_send_allowed"] is False
    assert plan["no_send_safety"]["contact_form_submit_allowed"] is False
    assert plan["no_send_safety"]["ready_for_outreach"] == 0
    assert plan["no_send_safety"]["pitch_ready"] == 0
    assert plan["no_send_safety"]["outreach_status_new"] == 0
    assert plan["counts"]["needs_more_info_cards"] == 4
    assert plan["counts"]["batch_count"] == 2
    assert plan["counts"]["enrichment_lane_counts"] == {
        "contact_form_route_enrichment": 1,
        "email_owner_route_enrichment": 1,
        "name_source_enrichment": 1,
        "scope_evidence_enrichment": 1,
    }
    assert plan["allowed_enrichment_outcomes"] == ["hold", "needs_more_info", "pitch_pack_ready", "reject"]
    assert "send_email" in plan["forbidden_actions"]
    assert plan["required_state"] == {
        "launch_readiness_status": "manual_review",
        "outreach_status": "needs_review",
        "pitch_ready": False,
    }
    all_entries = [entry for batch in plan["batches"] for entry in batch["queue"]]
    assert {entry["lead_id"] for entry in all_entries} == {"wrm-email", "wrm-name", "wrm-scope", "wrm-form"}
    assert all(entry["allowed_outcomes"] == ["hold", "needs_more_info", "pitch_pack_ready", "reject"] for entry in all_entries)


def test_needs_more_info_enrichment_writer_creates_json_and_markdown(tmp_path):
    _write_record(tmp_path, _lead("wrm-email", pitch_status="needs_email_review"))

    plan = write_needs_more_info_enrichment_plan(state_root=tmp_path, batch_size=1)

    assert plan["artifact_paths"]["json"].endswith(".json")
    assert plan["artifact_paths"]["markdown"].endswith(".md")
    markdown = open(plan["artifact_paths"]["markdown"], encoding="utf-8").read()
    assert "Needs-More-Info Enrichment Plan" in markdown
    assert "No-Send Safety" in markdown
    assert "email_owner_route_enrichment" in markdown
