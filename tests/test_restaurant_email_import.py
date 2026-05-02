from __future__ import annotations

import json

from pipeline.constants import OUTREACH_SAMPLE_BY_ESTABLISHMENT_PROFILE, OUTREACH_SAMPLE_RAMEN_ONE_PAGE_PDF
from pipeline.outreach import select_outreach_assets
from pipeline.restaurant_email_import import (
    establishment_profile_for,
    import_email_leads,
    normalize_email,
    queue_record_from_email_lead,
    skip_reason,
    sort_email_leads,
    template_assignment,
)
from pipeline.record import list_leads


def _lead(**overrides):
    base = {
        "restaurant_name": "麺屋テスト",
        "website": "https://test-ramen.local",
        "type_of_restaurant": "ramen",
        "city": "Tokyo",
        "email": "OWNER@Test-Ramen.local?subject=test",
        "normalized_email": "",
        "lead": True,
        "source_url": "https://test-ramen.local/menu",
        "email_source_url": "https://test-ramen.local/contact",
        "validation_notes": "Direct page shows Tokyo address evidence and strict ramen evidence.",
        "source_import": {"round": "v2_round_2"},
        "discovery_source": "restaurant_owned_page_email",
        "category_confidence": "high",
        "menu_type": "ramen",
        "rejection_flags": [],
        "quality_tier": "high",
    }
    base.update(overrides)
    return base


def test_normalize_email_strips_mailto_query_and_punctuation():
        assert normalize_email(" <mailto:Owner@Test-Ramen.local?subject=hi>, ") == "owner@test-ramen.local"


def test_menu_type_maps_to_dashboard_profiles():
    assert establishment_profile_for(_lead(menu_type="tsukemen")) == "ramen_only"
    assert establishment_profile_for(_lead(type_of_restaurant="izakaya", menu_type="yakitori")) == "izakaya_yakitori_kushiyaki"
    assert establishment_profile_for(_lead(type_of_restaurant="izakaya", menu_type="kushiage")) == "izakaya_kushiage"
    assert establishment_profile_for(_lead(type_of_restaurant="izakaya", menu_type="oden")) == "izakaya_seafood_sake_oden"
    assert establishment_profile_for(_lead(type_of_restaurant="izakaya", menu_type="tachinomi")) == "izakaya_tachinomi"
    assert establishment_profile_for(_lead(type_of_restaurant="izakaya", menu_type="robatayaki")) == "izakaya_robatayaki"


def test_template_assignment_is_locked_to_glm_policy():
    assignment = template_assignment(_lead(type_of_restaurant="izakaya", menu_type="yakitori"))

    assert assignment["template_locked"] is True
    assert assignment["template_owner"] == "GLM"
    assert assignment["template_edit_policy"] == "locked_glm_seedstyle_only"
    assert assignment["template_profile_id"] == "izakaya_yakitori_kushiyaki"
    assert assignment["template_family"] == "izakaya"


def test_specific_izakaya_profiles_use_locked_izakaya_sample_asset():
    for profile in [
        "izakaya_yakitori_kushiyaki",
        "izakaya_kushiage",
        "izakaya_seafood_sake_oden",
        "izakaya_tachinomi",
        "izakaya_robatayaki",
    ]:
        assert select_outreach_assets("menu_only", establishment_profile=profile) == [
            OUTREACH_SAMPLE_BY_ESTABLISHMENT_PROFILE[profile]
        ]
    assert select_outreach_assets("menu_only", establishment_profile="ramen_only") == [OUTREACH_SAMPLE_RAMEN_ONE_PAGE_PDF]


def test_queue_record_preserves_source_decision_and_blocks_until_verification_promotion():
    record = queue_record_from_email_lead(_lead(lead=False, quality_tier="medium", rejection_flags=["weak_city_evidence"]))

    assert record["lead"] is True
    assert record["source_lead_value"] is False
    assert record["quality_tier"] == "medium"
    assert record["candidate_inbox_status"] == "needs_scope_review"
    assert record["outreach_status"] == "needs_review"
    assert record["pitch_ready"] is False
    assert record["verification_status"] == "needs_review"
    assert record["email_verification_status"] == "verified"
    assert record["name_verification_status"] == "single_source"
    assert record["pitch_readiness_status"] == "needs_scope_review"
    assert record["template_locked"] is True
    assert record["template_owner"] == "GLM"


def test_sort_email_leads_prioritizes_quality_then_city():
    leads = [
        _lead(restaurant_name="Low", city="Tokyo", quality_tier="low", email="low@example.test"),
        _lead(restaurant_name="Osaka", city="Osaka", quality_tier="high", email="osaka@example.test"),
        _lead(restaurant_name="Tokyo", city="Tokyo", quality_tier="high", email="tokyo@example.test"),
    ]

    assert [lead["restaurant_name"] for lead in sort_email_leads(leads)] == ["Tokyo", "Osaka", "Low"]


def test_skip_reason_rejects_bad_email_and_review_artifact_names():
    assert skip_reason(_lead(email="info@sample.com", normalized_email="info@sample.com")) == "bad_email_fragment"
    assert skip_reason(_lead(restaurant_name="東京ラーメンショー２０１２ レポート")) == "review_artifact_name"


def test_import_email_leads_writes_queue_records_and_skips_duplicates(tmp_path):
    input_path = tmp_path / "leads.json"
    input_path.write_text(
        json.dumps([
            _lead(email="owner@test-ramen.local", normalized_email="owner@test-ramen.local"),
            _lead(email="owner@test-ramen.local", normalized_email="owner@test-ramen.local", restaurant_name="Duplicate"),
            _lead(email="info@sample.com", normalized_email="info@sample.com"),
        ]),
        encoding="utf-8",
    )

    result = import_email_leads([input_path], state_root=tmp_path)
    stored = list_leads(state_root=tmp_path)

    assert result.summary()["imported"] == 1
    assert result.summary()["duplicates"] == 1
    assert result.summary()["skipped"] == 1
    assert len(stored) == 1
    assert stored[0]["template_edit_policy"] == "locked_glm_seedstyle_only"
    assert stored[0]["launch_readiness_status"] == "manual_review"
    assert stored[0]["candidate_inbox_status"] != "pitch_ready"
    assert stored[0]["pitch_ready"] is False
