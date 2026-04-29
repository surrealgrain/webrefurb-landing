from __future__ import annotations

import json

import pytest

from pipeline.launch import LaunchBatchError, create_launch_batch
from pipeline.launch_smoke import (
    create_launch_smoke_test,
    record_launch_smoke_outcome,
    review_launch_smoke_test,
)
from tests.test_launch import _lead, _write_leads


def test_launch_smoke_uses_launch_gates_without_counting_as_batch(tmp_path):
    lead_ids = _write_leads(tmp_path, [
        "ramen_ticket_machine",
        "izakaya_drink_heavy",
        "ramen_only",
        "ramen_only",
        "izakaya_course_heavy",
    ])

    smoke = create_launch_smoke_test(lead_ids=lead_ids, state_root=tmp_path, notes="no-send real-world rehearsal")
    assert smoke["external_send_performed"] is False
    assert smoke["send_allowed"] is False
    assert smoke["counts_as_launch_batch"] is False
    assert smoke["phase_claim"] == "phase_11_rehearsal_only"
    assert smoke["leads"][0]["reply_status"] == "not_contacted"

    stored = json.loads((tmp_path / "leads" / f"{lead_ids[0]}.json").read_text(encoding="utf-8"))
    assert stored["launch_batch_id"] == ""
    assert stored["last_launch_smoke_test_id"] == smoke["smoke_test_id"]

    batch = create_launch_batch(lead_ids=lead_ids, state_root=tmp_path)
    assert batch["batch_number"] == 1


def test_launch_smoke_rejects_leads_that_real_batch_would_reject(tmp_path):
    lead_ids = _write_leads(tmp_path, [
        "ramen_ticket_machine",
        "ramen_only",
        "ramen_only",
        "ramen_only",
        "ramen_only",
    ])

    with pytest.raises(LaunchBatchError, match="missing_izakaya_drink_or_course_candidate"):
        create_launch_smoke_test(lead_ids=lead_ids, state_root=tmp_path)


def test_launch_smoke_outcomes_are_simulated_not_contacted(tmp_path):
    lead_ids = _write_leads(tmp_path, [
        "ramen_ticket_machine",
        "izakaya_drink_heavy",
        "ramen_only",
        "ramen_only",
        "izakaya_course_heavy",
    ])
    smoke = create_launch_smoke_test(lead_ids=lead_ids, state_root=tmp_path)

    entry = record_launch_smoke_outcome(
        smoke_test_id=smoke["smoke_test_id"],
        lead_id=lead_ids[0],
        state_root=tmp_path,
        outcome={
            "reply_status": "simulated_no_reply",
            "operator_minutes": 6,
            "notes": "Draft and proof passed internal review.",
            "next_action": "eligible_for_real_batch_review",
        },
    )
    assert entry["contacted_at"] == ""
    assert entry["reply_status"] == "not_contacted"
    assert entry["external_send_performed"] is False
    assert entry["simulated_outcome"]["simulated_reply_status"] == "simulated_no_reply"

    with pytest.raises(LaunchBatchError, match="smoke_test_cannot_record_real_contact_timestamp"):
        record_launch_smoke_outcome(
            smoke_test_id=smoke["smoke_test_id"],
            lead_id=lead_ids[0],
            state_root=tmp_path,
            outcome={"contacted_at": "2026-04-29T12:00:00+00:00"},
        )

    reviewed = review_launch_smoke_test(smoke_test_id=smoke["smoke_test_id"], state_root=tmp_path, notes="ready to choose real batch")
    assert reviewed["reviewed_at"]
