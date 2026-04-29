from __future__ import annotations

import json

import pytest

from pipeline.launch import (
    LaunchBatchError,
    create_launch_batch,
    record_launch_outcome,
    review_launch_batch,
)


def _lead(lead_id: str, profile: str) -> dict:
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
        "outreach_status": "new",
    }


def _write_leads(tmp_path, profiles):
    leads = tmp_path / "leads"
    leads.mkdir(exist_ok=True)
    lead_ids = []
    for idx, profile in enumerate(profiles, start=1):
        lead_id = f"wrm-launch-{idx}"
        lead_ids.append(lead_id)
        (leads / f"{lead_id}.json").write_text(json.dumps(_lead(lead_id, profile)), encoding="utf-8")
    return lead_ids


def test_create_launch_batch_requires_first_batch_review_before_second(tmp_path):
    lead_ids = _write_leads(tmp_path, [
        "ramen_ticket_machine",
        "izakaya_drink_heavy",
        "ramen_only",
        "ramen_only",
        "izakaya_course_heavy",
    ])

    batch = create_launch_batch(lead_ids=lead_ids, state_root=tmp_path)
    assert batch["lead_count"] == 5
    assert batch["batch_number"] == 1
    assert batch["leads"][0]["dossier_states"]["english_menu_state"] == "missing"
    assert batch["leads"][0]["reply_status"] == "not_contacted"
    assert batch["leads"][0]["opt_out"] is False
    assert batch["leads"][0]["bounce"] is False

    with pytest.raises(LaunchBatchError, match="previous_batch_not_reviewed"):
        create_launch_batch(lead_ids=lead_ids, state_root=tmp_path)

    reviewed = review_launch_batch(batch_id=batch["batch_id"], state_root=tmp_path, notes="first batch reviewed")
    assert reviewed["reviewed_at"]


def test_create_launch_batch_persists_dossier_and_rejects_duplicate_leads(tmp_path):
    lead_ids = _write_leads(tmp_path, [
        "ramen_ticket_machine",
        "izakaya_drink_heavy",
        "ramen_only",
        "ramen_only",
        "izakaya_course_heavy",
    ])

    with pytest.raises(LaunchBatchError, match="duplicate_lead_in_batch"):
        create_launch_batch(lead_ids=[lead_ids[0], lead_ids[0], *lead_ids[2:]], state_root=tmp_path)

    batch = create_launch_batch(lead_ids=lead_ids, state_root=tmp_path)
    stored = json.loads((tmp_path / "leads" / f"{lead_ids[0]}.json").read_text(encoding="utf-8"))

    assert stored["launch_batch_id"] == batch["batch_id"]
    assert stored["lead_evidence_dossier"]["ready_to_contact"] is True
    assert stored["launch_readiness_status"] == "ready_for_outreach"


def test_create_launch_batch_requires_measurement_fields(tmp_path):
    lead_ids = _write_leads(tmp_path, [
        "ramen_ticket_machine",
        "izakaya_drink_heavy",
        "ramen_only",
        "ramen_only",
        "izakaya_course_heavy",
    ])
    first_path = tmp_path / "leads" / f"{lead_ids[0]}.json"
    first = json.loads(first_path.read_text(encoding="utf-8"))
    first["message_variant"] = ""
    first["outreach_assets_selected"] = []
    first["proof_items"] = []
    first_path.write_text(json.dumps(first), encoding="utf-8")

    with pytest.raises(LaunchBatchError, match="lead_launch_measurement_incomplete"):
        create_launch_batch(lead_ids=lead_ids, state_root=tmp_path)


def test_record_launch_outcome_tracks_opt_out_bounce_minutes_and_lead_copy(tmp_path):
    lead_ids = _write_leads(tmp_path, [
        "ramen_ticket_machine",
        "izakaya_drink_heavy",
        "ramen_only",
        "ramen_only",
        "izakaya_course_heavy",
    ])
    batch = create_launch_batch(lead_ids=lead_ids, state_root=tmp_path)

    entry = record_launch_outcome(
        batch_id=batch["batch_id"],
        lead_id=lead_ids[0],
        state_root=tmp_path,
        outcome={
            "contacted_at": "2026-04-29T09:00:00+00:00",
            "reply_status": "opted_out",
            "objection": "Not needed",
            "operator_minutes": 7,
            "outcome": "do_not_contact",
        },
    )

    assert entry["contacted_at"] == "2026-04-29T09:00:00+00:00"
    assert entry["reply_status"] == "opted_out"
    assert entry["opt_out"] is True
    assert entry["bounce"] is False
    assert entry["operator_minutes"] == 7
    assert entry["outcome"]["outcome"] == "do_not_contact"

    stored = json.loads((tmp_path / "leads" / f"{lead_ids[0]}.json").read_text(encoding="utf-8"))
    assert stored["launch_outcome"]["reply_status"] == "opted_out"
    assert stored["launch_outcome"]["opt_out"] is True

    bounced = record_launch_outcome(
        batch_id=batch["batch_id"],
        lead_id=lead_ids[1],
        state_root=tmp_path,
        outcome={"bounce": True, "operator_minutes": 2},
    )
    assert bounced["reply_status"] == "bounced"
    assert bounced["bounce"] is True
