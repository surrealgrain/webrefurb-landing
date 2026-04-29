from __future__ import annotations

from pathlib import Path

from pipeline.production_sim import run_replay


FIXTURE = Path(__file__).parent / "fixtures" / "production_sim" / "first_slice"


def test_playwright_dashboard_screenshot_flow_uses_isolated_state(tmp_path):
    report = run_replay(
        corpus_dir=FIXTURE,
        run_id="production-sim-test-dashboard",
        output_root=tmp_path / "production-sim",
        replay_root=tmp_path / "search-replay",
        screenshot_root=tmp_path / "qa-screenshots",
        screenshots=True,
    )

    assert report["p0"] == 0
    assert report["p1"] == 0
    assert report["mock_sends_verified"] == 3
    assert report["external_send_performed"] is False
    assert report["real_launch_batch_created"] is False
    assert str(tmp_path / "production-sim") in report["state_root"]

    states = {item["ui_state"] for item in report["screenshots"]}
    assert {
        "dashboard_overview",
        "ready_lead_card",
        "manual_review_card",
        "disqualified_card",
        "outreach_editor",
        "inline_menu_sample",
        "inline_ticket_machine_sample",
        "inline_izakaya_sample",
    } <= states
    for item in report["screenshots"]:
        path = Path(item["path"])
        assert path.exists()
        assert path.stat().st_size > 0

    assert Path(report["report_path"]).exists()
    assert Path(report["mock_email_payloads_path"]).exists()
    assert Path(report["screenshot_manifest_path"]).exists()
