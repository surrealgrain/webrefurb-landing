from __future__ import annotations

from pipeline.review_batches import build_no_send_review_batch, write_no_send_review_batch_brief
from pipeline.utils import write_json


def _write_record(tmp_path, record: dict) -> None:
    write_json(tmp_path / "leads" / f"{record['lead_id']}.json", record)


def _lead(
    lead_id: str,
    *,
    contact_type: str = "email",
    contact_value: str = "owner@example.test",
    pitch_case: str = "email_review",
    profile: str = "ramen_only",
    outcome: str = "",
) -> dict:
    record = {
        "lead_id": lead_id,
        "lead": True,
        "business_name": f"Shop {lead_id}",
        "city": "Tokyo",
        "address": "東京都新宿区1-1-1",
        "primary_category_v1": "ramen" if profile.startswith("ramen") else "izakaya",
        "type_of_restaurant": "ramen" if profile.startswith("ramen") else "izakaya",
        "menu_type": "ramen" if profile.startswith("ramen") else "izakaya",
        "establishment_profile": profile,
        "quality_tier": "high",
        "source_strength": "official_site",
        "email_verification_status": "needs_review" if pitch_case == "email_review" else "verified",
        "name_verification_status": "single_source" if pitch_case == "name_review" else "verified",
        "city_verification_status": "verified",
        "category_verification_status": "needs_review" if pitch_case == "scope_review" else "verified",
        "chain_verification_status": "verified",
        "verification_status": "needs_review",
        "manual_review_required": True,
        "launch_readiness_status": "manual_review",
        "outreach_status": "needs_review",
        "pitch_ready": False,
        "contacts": [{"type": contact_type, "value": contact_value, "actionable": True}],
        "status_history": [{"status": "needs_review", "timestamp": "2026-05-02T00:00:00+00:00"}],
    }
    if contact_type == "email":
        record["email"] = contact_value
    if outcome:
        record["operator_review_outcome"] = outcome
        record["review_status"] = "held"
    return record


def test_review_batch_groups_openable_cards_without_promoting(tmp_path):
    _write_record(tmp_path, _lead("wrm-review-email", pitch_case="email_review"))
    _write_record(
        tmp_path,
        _lead(
            "wrm-review-form",
            contact_type="contact_form",
            contact_value="https://shop.example.test/contact",
            pitch_case="final_review",
            profile="izakaya_food_and_drinks",
        ),
    )
    _write_record(tmp_path, _lead("wrm-review-scope", pitch_case="scope_review"))
    _write_record(tmp_path, _lead("wrm-review-reviewed", pitch_case="name_review", outcome="hold"))
    _write_record(tmp_path, _lead("wrm-reference-phone", contact_type="phone", contact_value="03-0000-0000"))

    batch = build_no_send_review_batch(state_root=tmp_path, batch_size=10)

    assert batch["no_send_safety"]["real_outbound_allowed"] is False
    assert batch["no_send_safety"]["email_send_allowed"] is False
    assert batch["no_send_safety"]["contact_form_submit_allowed"] is False
    assert batch["no_send_safety"]["ready_for_outreach"] == 0
    assert batch["no_send_safety"]["pitch_ready"] == 0
    assert batch["no_send_safety"]["outreach_status_new"] == 0

    queue = {entry["lead_id"]: entry for entry in batch["review_queue"]}
    assert set(queue) == {"wrm-review-email", "wrm-review-form", "wrm-review-scope"}
    assert queue["wrm-review-email"]["review_lane"] == "email_route_review"
    assert queue["wrm-review-form"]["review_lane"] == "contact_form_review"
    assert queue["wrm-review-scope"]["review_lane"] == "scope_review"
    assert "wrm-reference-phone" not in queue
    assert "wrm-review-reviewed" not in queue
    assert batch["counts"]["review_outcome_counts"]["hold"] == 1
    assert batch["counts"]["review_outcome_counts"]["not_reviewed"] >= 3
    assert batch["glm"]["category_counts"]["ramen_only"]["openable_cards"] >= 2


def test_review_batch_writer_creates_json_and_markdown(tmp_path):
    _write_record(tmp_path, _lead("wrm-review-email", pitch_case="email_review"))

    batch = write_no_send_review_batch_brief(state_root=tmp_path, batch_size=1)

    artifact_paths = batch["artifact_paths"]
    assert artifact_paths["json"].endswith(".json")
    assert artifact_paths["markdown"].endswith(".md")
    assert "No-Send Pitch-Card Review Batch" in open(artifact_paths["markdown"], encoding="utf-8").read()
    assert batch["counts"]["selected_review_queue"] == 1
