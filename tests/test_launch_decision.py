from __future__ import annotations

import json

from pipeline.launch import create_launch_batch, record_launch_outcome, review_launch_batch
from pipeline.launch_decision import build_no_send_batch_decision


def _lead(lead_id: str, profile: str, *, status: str = "new") -> dict:
    category = "izakaya" if profile.startswith("izakaya") else "ramen"
    snippet = "飲み放題 コース 居酒屋 メニュー" if category == "izakaya" else "券売機 ラーメン 味玉 トッピング メニュー"
    return {
        "lead_id": lead_id,
        "lead": True,
        "business_name": f"Shop {lead_id}",
        "primary_category_v1": category,
        "english_availability": "missing",
        "english_menu_issue": True,
        "menu_evidence_found": True,
        "machine_evidence_found": profile == "ramen_ticket_machine",
        "course_or_drink_plan_evidence_found": category == "izakaya",
        "evidence_urls": [f"https://example.test/{lead_id}/menu"],
        "evidence_snippets": [snippet],
        "contacts": [{"type": "email", "value": f"{lead_id}@example.test", "actionable": True}],
        "establishment_profile": profile,
        "recommended_primary_package": "package_2_printed_delivered_45k",
        "outreach_assets_selected": ["/tmp/sample.pdf"],
        "message_variant": f"email:menu_only:{profile}",
        "outreach_status": status,
    }


def _write_lead(tmp_path, record: dict) -> None:
    leads = tmp_path / "leads"
    leads.mkdir(exist_ok=True)
    (leads / f"{record['lead_id']}.json").write_text(json.dumps(record), encoding="utf-8")


def test_no_send_batch_decision_blocks_real_outbound_and_excludes_prior_batch(tmp_path):
    lead_ids = []
    for idx, profile in enumerate([
        "ramen_ticket_machine",
        "izakaya_drink_heavy",
        "ramen_only",
        "ramen_only",
        "izakaya_course_heavy",
    ], start=1):
        lead_id = f"wrm-launch-{idx}"
        lead_ids.append(lead_id)
        _write_lead(tmp_path, _lead(lead_id, profile))
    _write_lead(tmp_path, _lead("wrm-next-real", "ramen_ticket_machine", status="needs_review"))
    _write_lead(tmp_path, _lead("wrm-qa-fixture", "izakaya_drink_heavy"))

    batch = create_launch_batch(lead_ids=lead_ids, state_root=tmp_path)
    for lead_id in lead_ids:
        record_launch_outcome(
            batch_id=batch["batch_id"],
            lead_id=lead_id,
            state_root=tmp_path,
            outcome={"contacted_at": "2026-04-30T00:00:00+00:00", "reply_status": "no_reply"},
        )
    review_launch_batch(batch_id=batch["batch_id"], state_root=tmp_path)

    decision = build_no_send_batch_decision(state_root=tmp_path)

    assert decision["real_outbound_allowed"] is False
    assert decision["aggregate"]["contacted_count"] == 5
    assert decision["aggregate"]["response_count"] == 0
    assert decision["candidate_pool"]["eligible_count"] == 0
    exclusions = {item["lead_id"]: item["reasons"] for item in decision["candidate_pool"]["exclusions"]}
    assert "operator_review_required" in exclusions["wrm-next-real"]
    assert "fixture_or_smoke_lead" in exclusions["wrm-qa-fixture"]
