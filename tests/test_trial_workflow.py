from __future__ import annotations

import pytest

from pipeline.trial_workflow import (
    TrialWorkflowError,
    create_trial_record,
    list_trial_records,
    save_trial_record,
    transition_trial,
    trial_followup_stage,
    trial_metrics,
    trial_publicly_indexable,
)


def test_trial_lifecycle_tracks_live_converted_and_archive(tmp_path):
    trial = create_trial_record(
        lead={"lead_id": "wrm-hinode", "business_name": "Hinode Ramen"},
        now="2026-05-01T00:00:00+00:00",
    )

    assert trial["status"] == "requested"
    assert trial_publicly_indexable(trial) is False

    trial = transition_trial(trial, "accepted", now="2026-05-01T01:00:00+00:00")
    trial = transition_trial(trial, "intake_needed", now="2026-05-01T02:00:00+00:00")
    trial = transition_trial(trial, "build_started", now="2026-05-02T00:00:00+00:00")
    trial = transition_trial(trial, "owner_review", now="2026-05-03T00:00:00+00:00")
    trial = transition_trial(
        trial,
        "live_trial",
        now="2026-05-04T00:00:00+00:00",
        public_url="https://webrefurb.com/menus/hinode/",
        menu_id="hinode",
    )

    assert trial_publicly_indexable(trial) is True
    assert trial["trial_ends_at"] == "2026-05-11T00:00:00+00:00"
    assert trial_followup_stage(trial, now="2026-05-09T00:00:00+00:00") == "day_5"
    assert trial_followup_stage(trial, now="2026-05-11T00:00:00+00:00") == "day_7"
    assert trial_followup_stage(trial, now="2026-05-14T00:00:00+00:00") == "day_10"

    trial = transition_trial(trial, "converted", now="2026-05-12T00:00:00+00:00")
    trial = transition_trial(trial, "archived", now="2026-05-20T00:00:00+00:00")
    assert trial_publicly_indexable(trial) is False

    save_trial_record(state_root=tmp_path, record=trial)
    assert list_trial_records(state_root=tmp_path)[0]["trial_id"] == "trial-wrm-hinode"


def test_trial_invalid_transition_is_blocked():
    trial = create_trial_record(lead={"business_name": "Hinode Ramen"})
    with pytest.raises(TrialWorkflowError):
        transition_trial(trial, "live_trial")


def test_trial_metrics_are_privacy_light():
    requested = create_trial_record(lead={"lead_id": "one"})
    converted = transition_trial(create_trial_record(lead={"lead_id": "two"}), "accepted")
    converted = transition_trial(converted, "intake_needed")
    converted = transition_trial(converted, "build_started")
    converted = transition_trial(converted, "owner_review")
    converted = transition_trial(converted, "live_trial")
    converted = transition_trial(converted, "converted")

    metrics = trial_metrics([requested, converted])

    assert metrics["requested"] == 2
    assert metrics["converted"] == 1
    assert metrics["conversion_rate"] == 0.5
