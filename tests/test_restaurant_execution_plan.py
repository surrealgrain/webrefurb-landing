from __future__ import annotations

from pipeline.restaurant_execution_plan import build_restaurant_execution_plan, write_restaurant_execution_plan
from pipeline.utils import write_json


def _write_record(tmp_path, record: dict) -> None:
    write_json(tmp_path / "leads" / f"{record['lead_id']}.json", record)


def _lead(
    lead_id: str,
    *,
    profile: str = "izakaya_yakitori_kushiyaki",
    contact_type: str = "email",
    pitch_case: str = "email_review",
    outcome: str = "",
) -> dict:
    category = "izakaya" if profile.startswith("izakaya") else "ramen"
    contact_value = f"{lead_id}@example.test" if contact_type == "email" else "https://shop.example.test/contact"
    record = {
        "lead_id": lead_id,
        "lead": True,
        "business_name": f"Shop {lead_id}",
        "city": "Tokyo",
        "address": "東京都新宿区1-1-1",
        "primary_category_v1": category,
        "type_of_restaurant": category,
        "menu_type": category,
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
    }
    if contact_type == "email":
        record["email"] = contact_value
    if outcome:
        record["operator_review_outcome"] = outcome
        record["review_status"] = outcome
    return record


def test_execution_plan_finishes_no_send_artifacts_without_promotion(tmp_path):
    for index in range(10):
        _write_record(tmp_path, _lead(f"wrm-yakitori-{index}", profile="izakaya_yakitori_kushiyaki"))
    for index in range(3):
        _write_record(tmp_path, _lead(f"wrm-ramen-{index}", profile="ramen_only"))

    plan = build_restaurant_execution_plan(state_root=tmp_path, batch_size=5, representative_count=3)

    assert plan["scope"] == "restaurant_lead_execution_plan_no_send_completion"
    assert plan["finished_until_external_gate"] is True
    assert plan["no_send_safety"]["real_outbound_allowed"] is False
    assert plan["no_send_safety"]["ready_for_outreach"] == 0
    assert plan["no_send_safety"]["pitch_ready"] == 0
    assert plan["no_send_safety"]["outreach_status_new"] == 0
    assert plan["queue"]["approved_route_review_cards"] == 13
    assert plan["review_wave"]["batch_count"] == 3
    assert plan["promotion_gate_preview"]["live_promotion_allowed"] is False
    assert plan["promotion_gate_preview"]["pitch_ready_mutation_allowed"] is False
    assert plan["promotion_gate_preview"]["candidate_count"] == 13
    assert plan["needs_more_info_enrichment"]["needs_more_info_cards"] == 0
    assert plan["inline_pitch_pack_plan"]["draft_generation_allowed"] is False
    yakitori = next(item for item in plan["glm_design_requests"] if item["profile_id"] == "izakaya_yakitori_kushiyaki")
    assert yakitori["request_status"] == "locked_asset_available"
    assert yakitori["request_glm_now"] is False
    assert len(yakitori["representative_examples"]) == 3
    ramen = next(item for item in plan["glm_design_requests"] if item["profile_id"] == "ramen_only")
    assert ramen["request_status"] == "covered_or_monitor"
    assert ramen["request_glm_now"] is False


def test_execution_plan_writer_creates_json_and_markdown(tmp_path):
    _write_record(tmp_path, _lead("wrm-yakitori", profile="izakaya_yakitori_kushiyaki", outcome="needs_more_info"))
    _write_record(tmp_path, _lead("wrm-yakitori-unreviewed", profile="izakaya_yakitori_kushiyaki"))

    plan = write_restaurant_execution_plan(state_root=tmp_path, batch_size=1)

    assert plan["needs_more_info_enrichment"]["needs_more_info_cards"] == 1
    artifact_paths = plan["artifact_paths"]
    assert artifact_paths["json"].endswith(".json")
    assert artifact_paths["markdown"].endswith(".md")
    markdown = open(artifact_paths["markdown"], encoding="utf-8").read()
    assert "Restaurant Lead Execution Plan Completion" in markdown
    assert "Real outbound allowed: `false`" in markdown
    assert "Promotion Gate Preview" in markdown
    assert "Inline Pitch-Pack Plan" in markdown
    assert "Needs-More-Info Enrichment" in markdown
    assert "Representative examples" in markdown
    assert "Required outputs" in markdown
