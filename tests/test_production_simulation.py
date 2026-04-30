from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import pytest

from pipeline.production_sim import (
    build_mock_email_payloads,
    collect_corpus,
    prepare_labeling_workflow,
    recommend_controlled_launch,
)
from pipeline.production_sim_oracle import evaluate_simulation
from pipeline.search_replay import (
    REQUIRED_LABEL_FIELDS,
    ReplayCorpusError,
    ReplaySearchError,
    _default_maps_search,
    copy_corpus_snapshot,
    fixture_collect_adapters,
    load_replay_corpus,
    materialize_replay_state,
    reconcile_label_contact_policy,
    validate_label_schema,
)
from pipeline.record import get_primary_contact
from pipeline.utils import write_json, write_text


FIXTURE = Path(__file__).parent / "fixtures" / "production_sim" / "first_slice"
COLLECT_FIXTURE = Path(__file__).parent / "fixtures" / "production_sim" / "collector_fixture.json"


def _required_screenshots(tmp_path: Path) -> list[dict]:
    states = [
        "dashboard_overview",
        "ready_lead_card",
        "manual_review_card",
        "disqualified_card",
        "outreach_editor",
        "inline_menu_sample",
        "inline_ticket_machine_sample",
        "inline_izakaya_sample",
    ]
    screenshots: list[dict] = []
    for state in states:
        path = tmp_path / f"{state}.png"
        path.write_bytes(b"fake-png")
        screenshots.append({
            "path": str(path),
            "lead_id": "",
            "ui_state": state,
            "expected_assertion": state,
            "actual_assertion": "captured",
        })
    return screenshots


def _records_and_labels(tmp_path: Path):
    corpus = load_replay_corpus(FIXTURE)
    records = materialize_replay_state(corpus=corpus, state_root=tmp_path / "state")
    return records, corpus["labels"]


def test_first_slice_fixture_oracle_schema_and_closed_loop(tmp_path):
    records, labels = _records_and_labels(tmp_path)
    payloads = build_mock_email_payloads(records=records, labels=labels)
    report = evaluate_simulation(
        records=records,
        labels=labels,
        mock_payloads=payloads,
        screenshots=_required_screenshots(tmp_path),
    )

    assert report["candidate_count"] == 12
    assert report["labeled_count"] == 12
    assert report["ready_count"] == 3
    assert report["manual_review_count"] == 3
    assert report["disqualified_count"] == 6
    assert report["mock_sends_verified"] == 3
    assert report["p0"] == 0
    assert report["p1"] == 0
    assert report["p2"] == 1
    assert report["production_ready"] is False
    assert report["findings"][0]["id"] == "P2-BROAD-CORPUS-DEFERRED-001"
    assert report["findings"][0]["disposition"] == "deferred"
    assert report["findings"][0]["fix_hint"]


def test_reconcile_label_contact_policy_moves_unsupported_ready_route_to_manual_review(tmp_path):
    corpus = tmp_path / "corpus"
    labels = corpus / "labels"
    labels.mkdir(parents=True)
    write_json(corpus / "manifest.json", {
        "run_id": "test",
        "candidates_file": "candidates.json",
        "labels_dir": "labels",
    })
    write_json(corpus / "candidates.json", [])
    label = {
        "candidate_id": "wrm-test-phone",
        "business_name": "Phone Only Ramen",
        "category_expected": "ramen",
        "readiness_expected": "ready_for_outreach",
        "rejection_reason_expected": "",
        "package_expected": "package_2_printed_delivered_45k",
        "contact_route_expected": "phone",
        "inline_assets_expected": ["ramen_food_menu"],
        "ticket_machine_state_expected": "present",
        "english_menu_state_expected": "missing",
        "proof_strength_minimum": "gold",
        "label_confidence": "high",
        "label_notes": "",
    }
    write_json(labels / "wrm-test-phone.json", label)

    result = reconcile_label_contact_policy(corpus)
    updated = json.loads((labels / "wrm-test-phone.json").read_text(encoding="utf-8"))

    assert result["changed_count"] == 1
    assert updated["legacy_contact_route_expected"] == "phone"
    assert updated["contact_route_expected"] == "none"
    assert updated["readiness_expected"] == "manual_review"
    assert updated["rejection_reason_expected"] == "no_supported_contact_route"
    validate_label_schema(updated)


def test_oracle_blocks_production_ready_when_p0_exists(tmp_path):
    records, labels = _records_and_labels(tmp_path)
    poisoned_labels = dict(labels)
    poisoned_labels["wrm-sim-ready-ramen-ticket"] = {
        **poisoned_labels["wrm-sim-ready-ramen-ticket"],
        "readiness_expected": "disqualified",
    }

    report = evaluate_simulation(
        records=records,
        labels=poisoned_labels,
        mock_payloads=[],
        screenshots=_required_screenshots(tmp_path),
    )

    assert report["production_ready"] is False
    assert report["p0"] >= 1
    assert any(item["priority"] == "P0" and item["fix_hint"] for item in report["findings"])


def test_oracle_reports_p1_for_missing_dashboard_screenshots(tmp_path):
    records, labels = _records_and_labels(tmp_path)
    payloads = build_mock_email_payloads(records=records, labels=labels)

    report = evaluate_simulation(records=records, labels=labels, mock_payloads=payloads, screenshots=[])

    assert report["production_ready"] is False
    assert any(item["id"].startswith("P1-DASHBOARD-SCREENSHOTS-MISSING") for item in report["findings"])


def test_oracle_blocks_production_ready_when_positive_profile_coverage_is_short(tmp_path):
    records = []
    labels = {}
    for index in range(300):
        candidate_id = f"wrm-profile-gap-{index:03d}"
        lead_id = f"wrm-profile-gap-lead-{index:03d}"
        records.append({
            "production_sim_candidate_id": candidate_id,
            "lead_id": lead_id,
            "business_name": f"Profile Gap {index:03d}",
            "lead": False,
            "primary_category_v1": "ramen",
            "launch_readiness_status": "disqualified",
            "launch_readiness_reasons": ["already_has_usable_english_solution"],
            "recommended_primary_package": "none",
            "contacts": [],
            "outreach_assets_selected": [],
            "lead_evidence_dossier": {
                "ticket_machine_state": "unknown",
                "english_menu_state": "usable_complete",
                "proof_strength": "none",
            },
        })
        labels[candidate_id] = {
            "candidate_id": candidate_id,
            "business_name": f"Profile Gap {index:03d}",
            "website": "",
            "address": "Tokyo Japan",
            "category_expected": "ramen",
            "readiness_expected": "disqualified",
            "rejection_reason_expected": "already_has_usable_english_solution",
            "package_expected": "none",
            "contact_route_expected": "none",
            "inline_assets_expected": [],
            "ticket_machine_state_expected": "unknown",
            "english_menu_state_expected": "usable_complete",
            "proof_strength_minimum": "none",
            "label_confidence": "high",
        }

    report = evaluate_simulation(
        records=records,
        labels=labels,
        mock_payloads=[],
        screenshots=_required_screenshots(tmp_path),
    )

    assert report["p0"] == 0
    assert report["p1"] == 0
    assert report["p2"] == 1
    assert report["production_ready"] is False
    assert report["findings"][0]["id"] == "P2-EXPECTED-READY-PROFILE-COVERAGE-DEFERRED-001"
    assert report["findings"][0]["actual"]["expected_ready_labels"] == 0


def test_mock_email_payloads_verify_ready_profiles(tmp_path):
    records, labels = _records_and_labels(tmp_path)
    payloads = build_mock_email_payloads(records=records, labels=labels)
    by_lead = {payload["lead_id"]: payload for payload in payloads}

    assert sorted(by_lead) == [
        "wrm-sim-ready-izakaya-course",
        "wrm-sim-ready-ramen-ticket",
        "wrm-sim-ready-simple-ramen",
    ]
    ticket_payload = by_lead["wrm-sim-ready-ramen-ticket"]
    assert ticket_payload["recipient"] == "owner@aosora-ramen.example.jp"
    assert {"webrefurb-logo", "menu-preview", "machine-preview"} <= set(ticket_payload["cid_references"])
    assert ticket_payload["file_attachments"] == []
    assert ticket_payload["external_send_performed"] is False

    izakaya_payload = by_lead["wrm-sim-ready-izakaya-course"]
    assert "menu-preview" in izakaya_payload["cid_references"]
    assert "machine-preview" not in izakaya_payload["cid_references"]
    assert izakaya_payload["selected_package"] == "package_3_qr_menu_65k"


def test_oracle_does_not_require_email_payload_for_contact_form_ready_route(tmp_path):
    records, labels = _records_and_labels(tmp_path)
    target_id = "wrm-sim-ready-simple-ramen"
    target = next(record for record in records if record["lead_id"] == target_id)
    target["contacts"] = [{
        "type": "contact_form",
        "value": "https://aosora-ramen.example.jp/contact",
        "href": "https://aosora-ramen.example.jp/contact",
        "label": "Contact form",
        "actionable": True,
        "confidence": "high",
    }]
    target["primary_contact"] = target["contacts"][0]
    target["email"] = ""
    labels = {
        key: ({**value, "contact_route_expected": "contact_form"} if key == target_id else value)
        for key, value in labels.items()
    }

    report = evaluate_simulation(
        records=records,
        labels=labels,
        mock_payloads=build_mock_email_payloads(records=records, labels=labels),
        screenshots=_required_screenshots(tmp_path),
    )

    assert report["p0"] == 0
    assert not any(item["code"] == "MOCK-SEND-MISSING" and item["lead_id"] == target_id for item in report["findings"])


def test_collect_writes_manifest_schema_and_fetch_failures(tmp_path):
    maps_search, web_search, fetch_page = fixture_collect_adapters(COLLECT_FIXTURE)

    report = collect_corpus(
        run_id="production-sim-collect-schema-test",
        city_set="test",
        cities=["Shibuya"],
        category="ramen",
        limit_per_job=3,
        output_root=tmp_path / "production-sim",
        replay_root=tmp_path / "search-replay",
        screenshot_root=tmp_path / "qa-screenshots",
        maps_search_fn=maps_search,
        web_search_fn=web_search,
        fetch_page_fn=fetch_page,
    )

    manifest_path = Path(report["collection_manifest_path"])
    corpus = load_replay_corpus(manifest_path.parent, require_labels=False)
    manifest = corpus["manifest"]

    assert report["production_ready"] is False
    assert report["p0"] == 0
    assert report["p1"] == 0
    assert report["p2"] == 1
    assert report["external_send_performed"] is False
    assert report["real_launch_batch_created"] is False
    assert manifest["schema_version"] == 2
    assert manifest["run_scope"] == "pilot_broad_collection_scaffold"
    assert manifest["external_send_allowed"] is False
    assert manifest["launch_batch_allowed"] is False
    assert manifest["offline_replay_compatible"] is True
    assert manifest["requires_labels_before_replay"] is True
    assert manifest["candidate_count"] == 2
    assert manifest["raw_candidate_count"] == 3
    assert manifest["duplicate_count"] == 1
    assert manifest["fetch_failure_count"] >= 1
    assert manifest["label_count"] == 0
    assert "ramen_english_menu_check" in {job["job_id"] for job in manifest["search_jobs"]}
    assert "ramen_mobile_order_check" in {job["job_id"] for job in manifest["search_jobs"]}

    failures = (manifest_path.parent / manifest["fetch_failures_file"]).read_text(encoding="utf-8")
    assert "broken.example.jp" in failures
    assert not (tmp_path / "production-sim" / "production-sim-collect-schema-test" / "state" / "leads").exists()


def test_default_maps_search_reports_missing_or_http_error_body(monkeypatch):
    with pytest.raises(ReplaySearchError, match="requires SERPER_API_KEY"):
        _default_maps_search(query="ラーメン Shibuya", api_key="")

    class ResponseBody:
        def read(self):
            return b'{"message":"Bad Request: invalid query"}'

        def close(self):
            return None

    def fail_urlopen(*_, **__):
        raise urllib.error.HTTPError(
            url="https://google.serper.dev/maps",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=ResponseBody(),
        )

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)

    with pytest.raises(ReplaySearchError, match="HTTP 400.*invalid query"):
        _default_maps_search(query="ラーメン Shibuya", api_key="test-key")


def test_collect_dedupes_across_jobs_and_records_duplicate_sources(tmp_path):
    maps_search, web_search, fetch_page = fixture_collect_adapters(COLLECT_FIXTURE)
    report = collect_corpus(
        run_id="production-sim-collect-dedupe-test",
        cities=["Shibuya"],
        category="ramen",
        limit_per_job=3,
        output_root=tmp_path / "production-sim",
        replay_root=tmp_path / "search-replay",
        maps_search_fn=maps_search,
        web_search_fn=web_search,
        fetch_page_fn=fetch_page,
    )

    root = Path(report["collection_manifest_path"]).parent
    corpus = load_replay_corpus(root, require_labels=False)
    candidates = corpus["candidates"]
    duplicates = json.loads((root / "duplicates.json").read_text(encoding="utf-8"))

    assert len(candidates) == 2
    assert len(duplicates) == 1
    duplicate = duplicates[0]
    assert duplicate["source_job"]["job_id"] == "ramen_meal_ticket"
    assert any(key.startswith("place_id:place-aosora") for key in duplicate["matched_keys"])
    canonical = next(candidate for candidate in candidates if candidate["business_name"] == "青空ラーメン")
    assert canonical["duplicate_source_jobs"][0]["job_id"] == "ramen_meal_ticket"


def test_collect_corpus_is_offline_replay_loadable_without_labels(tmp_path):
    maps_search, web_search, fetch_page = fixture_collect_adapters(COLLECT_FIXTURE)
    report = collect_corpus(
        run_id="production-sim-collect-offline-test",
        cities=["Shibuya"],
        category="ramen",
        limit_per_job=3,
        output_root=tmp_path / "production-sim",
        replay_root=tmp_path / "search-replay",
        maps_search_fn=maps_search,
        web_search_fn=web_search,
        fetch_page_fn=fetch_page,
    )

    root = Path(report["collection_manifest_path"]).parent
    corpus = load_replay_corpus(root, require_labels=False)

    assert corpus["labels"] == {}
    assert sorted(corpus["unlabeled_candidate_ids"])
    for candidate in corpus["candidates"]:
        for page in candidate["capture"]["pages"]:
            assert (root / page["path"]).exists()
        assert candidate["capture"]["serper_maps_artifacts"]

    report_dir = tmp_path / "production-sim" / "production-sim-collect-offline-test"
    assert (report_dir / "report.json").exists()
    assert (report_dir / "mock-email-payloads.json").read_text(encoding="utf-8").strip() == "[]"


def test_materialize_collected_candidate_runs_offline_qualification(tmp_path):
    corpus_root = tmp_path / "search-replay" / "collected-candidate"
    corpus_root.mkdir(parents=True)
    candidate = _label_candidate(
        "wrm-replay-live-ticket",
        "青空ラーメン",
        "Shibuya",
        "ramen",
        "ramen_ticket_machine",
        "ticket_machine_lookup",
        "https://aosora.example.jp",
        "03-1111-2222",
        "券売機 食券 ラーメン メニュー 味玉 チャーシュー トッピング お問い合わせ mailto:owner@aosora.example.jp",
    )
    for page in candidate["capture"]["pages"]:
        write_text(corpus_root / page["path"], page["html"])
        del page["html"]
    corpus = {
        "root": corpus_root,
        "manifest": {"run_id": "collected-candidate"},
        "candidates": [candidate],
        "labels": {},
        "unlabeled_candidate_ids": [candidate["candidate_id"]],
    }

    records = materialize_replay_state(corpus=corpus, state_root=tmp_path / "state")

    record = records[0]
    primary = get_primary_contact(record)
    assert record["production_sim_candidate_id"] == "wrm-replay-live-ticket"
    assert record["lead"] is True
    assert record["launch_readiness_status"] == "ready_for_outreach"
    assert record["primary_category_v1"] == "ramen"
    assert record["recommended_primary_package"] == "package_2_printed_delivered_45k"
    assert record["ticket_machine_state"] == "present"
    assert primary["type"] == "email"
    assert primary["value"] == "owner@aosora.example.jp"
    assert any("ticket_machine_guide" in path for path in record["outreach_assets_selected"])
    assert (tmp_path / "state" / "leads" / f"{record['lead_id']}.json").exists()


def test_label_workflow_creates_stratified_drafts_without_finalizing_labels(tmp_path):
    corpus_root = _write_labeling_corpus(tmp_path / "search-replay" / "label-workflow")

    report = prepare_labeling_workflow(
        corpus_dir=corpus_root,
        sample_size=8,
        output_root=tmp_path / "production-sim",
    )

    sample_path = Path(report["labeling_sample_path"])
    queue_path = Path(report["labeling_review_queue_path"])
    offline_plan_path = Path(report["offline_replay_plan_path"])
    dashboard_plan_path = Path(report["dashboard_verification_plan_path"])
    manifest = json.loads((corpus_root / "manifest.json").read_text(encoding="utf-8"))
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    offline_plan = json.loads(offline_plan_path.read_text(encoding="utf-8"))
    dashboard_plan = json.loads(dashboard_plan_path.read_text(encoding="utf-8"))
    drafts = sorted((corpus_root / "labeling" / "drafts").glob("*.json"))

    assert report["production_ready"] is False
    assert report["p0"] == 0
    assert report["p1"] == 0
    assert report["p2"] == 1
    assert report["candidate_count"] == 8
    assert report["labeled_count"] == 0
    assert report["labeling_sample_count"] == 8
    assert report["draft_label_count"] == 8
    assert report["offline_replay_ready"] is False
    assert report["dashboard_verification_ready"] is False
    assert report["external_send_performed"] is False
    assert report["real_launch_batch_created"] is False

    assert manifest["label_count"] == 0
    assert manifest["labeling_workflow"]["sample_size"] == 8
    assert manifest["labeling_workflow"]["offline_replay_ready"] is False
    assert manifest["labeling_workflow"]["offline_replay_plan_file"] == "labeling/offline-replay-plan.json"
    assert manifest["labeling_workflow"]["dashboard_verification_plan_file"] == "labeling/dashboard-verification-plan.json"
    assert len(drafts) == 8
    assert load_replay_corpus(corpus_root, require_labels=False)["labels"] == {}
    assert offline_plan["ready"] is False
    assert offline_plan["blocked_by"] == ["finalized_label_count=0"]
    assert "--screenshots --fail-on p0,p1" in offline_plan["command_after_labels"]
    assert dashboard_plan["ready"] is False
    assert "blocked_send_error" in dashboard_plan["required_screenshot_states"]

    strata = [item["sample_strata"] for item in sample]
    assert {"ramen", "izakaya"} <= {item["category"] for item in strata}
    assert {"Shibuya", "Namba", "Gion"} <= {item["market"] for item in strata}
    assert {"suspected_ready_review_required", "suspected_disqualified_already_solved", "suspected_manual_no_supported_contact"} <= {
        item["suspected_class"] for item in strata
    }
    assert {"ramen_ticket_machine", "izakaya_course_nomihodai", "mobile_order_check"} <= {
        item["evidence_profile"] for item in strata
    }
    assert {"email", "contact_form", "website_only"} <= {item["contact_route_profile"] for item in strata}
    assert len(queue["low_confidence_drafts"]) == 8
    assert queue["expected_ready_second_pass_required"]

    ready_draft = next(
        json.loads(path.read_text(encoding="utf-8"))
        for path in drafts
        if json.loads(path.read_text(encoding="utf-8"))["second_pass_review"]["required"] is True
    )
    assert REQUIRED_LABEL_FIELDS <= set(ready_draft)
    assert ready_draft["label_status"] == "draft_needs_operator_review"
    assert ready_draft["label_confidence"] == "low"
    assert ready_draft["second_pass_review"]["status"] == "pending"


def test_labeled_collected_corpus_replays_only_finalized_label_subset(tmp_path):
    corpus_root = _write_labeling_corpus(tmp_path / "search-replay" / "partial-labels")
    label = {
        "candidate_id": "wrm-label-ticket",
        "business_name": "青空ラーメン",
        "website": "https://ticket.example.jp",
        "address": "Shibuya Japan",
        "category_expected": "ramen",
        "readiness_expected": "ready_for_outreach",
        "rejection_reason_expected": "",
        "package_expected": "package_2_printed_delivered_45k",
        "contact_route_expected": "email",
        "inline_assets_expected": ["ramen_food_menu", "ticket_machine_guide"],
        "ticket_machine_state_expected": "present",
        "english_menu_state_expected": "missing",
        "proof_strength_minimum": "gold",
        "label_confidence": "high",
        "label_notes": "Reviewed subset label.",
    }
    write_json(corpus_root / "labels" / "wrm-label-ticket.json", label)
    manifest = json.loads((corpus_root / "manifest.json").read_text(encoding="utf-8"))
    manifest["labeling_workflow"] = {"sample_size": 1}
    write_json(corpus_root / "manifest.json", manifest)

    corpus = load_replay_corpus(corpus_root)

    assert [candidate["candidate_id"] for candidate in corpus["candidates"]] == ["wrm-label-ticket"]
    assert len(corpus["labels"]) == 1
    assert "wrm-label-meal" in corpus["unlabeled_candidate_ids"]


def test_controlled_launch_recommendation_runs_no_send_smoke(tmp_path):
    run_dir, lead_ids = _write_recommendation_run(tmp_path)

    report = recommend_controlled_launch(
        run=run_dir,
        lead_ids=lead_ids,
        url_check_fn=lambda url: True,
    )

    assert report["controlled_launch_recommendation"] == "PROCEED_TO_CONTROLLED_BATCH_1_SELECTION"
    assert report["production_ready"] is True
    assert report["p0"] == 0
    assert report["p1"] == 0
    assert report["no_send_smoke"]["passed"] is True
    assert report["no_send_smoke"]["source_urls_checked"] == 10
    assert report["external_send_performed"] is False
    assert report["real_launch_batch_created"] is False

    state_root = Path(report["state_root"])
    assert not (state_root / "launch_batches").exists()
    smoke_path = state_root / "launch_smoke_tests" / f"{report['no_send_smoke']['smoke_test_id']}.json"
    smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    assert smoke["counts_as_launch_batch"] is False
    assert smoke["send_allowed"] is False
    assert all(entry["reply_status"] == "not_contacted" for entry in smoke["leads"])

    stored = json.loads((state_root / "leads" / f"{lead_ids[0]}.json").read_text(encoding="utf-8"))
    assert stored["message_variant"] == "email:menu_and_machine:ramen_ticket_machine"
    assert stored["outreach_draft_body"]
    assert stored["outreach_sent_at"] is None
    assert stored["launch_batch_id"] == ""


def test_controlled_launch_recommendation_blocks_when_live_source_check_fails(tmp_path):
    run_dir, lead_ids = _write_recommendation_run(tmp_path)

    report = recommend_controlled_launch(
        run=run_dir,
        lead_ids=lead_ids,
        url_check_fn=lambda url: not url.endswith("/lead-3/menu"),
    )

    assert report["controlled_launch_recommendation"] == "DO_NOT_LAUNCH_REQUIRED_FIXES_REMAIN"
    assert report["production_ready"] is False
    assert report["p1"] == 1
    assert report["no_send_smoke"]["passed"] is False
    assert report["no_send_smoke"]["source_url_failures"] == [{
        "lead_id": "wrm-smoke-3",
        "url": "https://example.test/lead-3/menu",
        "error": "not_loadable",
    }]
    assert report["findings"][-1]["code"] == "SMOKE-SOURCE-URL-CHECK-FAILED"
    assert report["real_launch_batch_created"] is False


def test_copy_corpus_snapshot_preserves_source_when_target_is_same_path(tmp_path):
    corpus_root = _write_labeling_corpus(tmp_path / "search-replay" / "self-snapshot")

    copy_corpus_snapshot(corpus_dir=corpus_root, replay_root=corpus_root)

    assert (corpus_root / "manifest.json").exists()
    assert (corpus_root / "candidates.json").exists()
    assert json.loads((corpus_root / "source.json").read_text(encoding="utf-8"))["snapshot"] == "source_equals_target"


def test_expected_ready_label_requires_high_confidence_or_approved_second_pass():
    label = {
        "candidate_id": "wrm-label-ready",
        "business_name": "Ready Ramen",
        "website": "https://ready.example.jp",
        "address": "Tokyo Japan",
        "category_expected": "ramen",
        "readiness_expected": "ready_for_outreach",
        "rejection_reason_expected": "",
        "package_expected": "package_2_printed_delivered_45k",
        "contact_route_expected": "email",
        "inline_assets_expected": ["ramen_food_menu", "ticket_machine_guide"],
        "ticket_machine_state_expected": "present",
        "english_menu_state_expected": "missing",
        "proof_strength_minimum": "gold",
        "label_confidence": "medium",
        "label_notes": "",
    }

    with pytest.raises(ReplayCorpusError, match="expected-ready labels require"):
        validate_label_schema(label)

    validate_label_schema({**label, "second_pass_review": {"status": "approved", "reviewer": "operator"}})


def _write_recommendation_run(tmp_path: Path) -> tuple[Path, list[str]]:
    run_dir = tmp_path / "production-sim" / "production-sim-recommend"
    state_root = run_dir / "state"
    leads_dir = state_root / "leads"
    leads_dir.mkdir(parents=True)
    lead_ids = []
    profiles = [
        ("ramen_ticket_machine", "ramen", "menu_and_machine", "package_2_printed_delivered_45k"),
        ("izakaya_drink_heavy", "izakaya", "menu_only", "package_3_qr_menu_65k"),
        ("ramen_only", "ramen", "menu_only", "package_1_remote_30k"),
        ("ramen_only", "ramen", "menu_only", "package_1_remote_30k"),
        ("izakaya_course_heavy", "izakaya", "menu_only", "package_3_qr_menu_65k"),
    ]
    for index, (profile, category, classification, package) in enumerate(profiles, start=1):
        lead_id = f"wrm-smoke-{index}"
        lead_ids.append(lead_id)
        snippet = "飲み放題 コース 居酒屋 メニュー" if category == "izakaya" else "券売機 ラーメン 味玉 トッピング メニュー"
        write_json(leads_dir / f"{lead_id}.json", {
            "lead_id": lead_id,
            "lead": True,
            "business_name": f"Aosora Ramen Smoke {index}",
            "website": f"https://example.test/lead-{index}",
            "address": "Tokyo Japan",
            "primary_category_v1": category,
            "english_availability": "missing",
            "english_menu_issue": True,
            "menu_evidence_found": True,
            "machine_evidence_found": profile == "ramen_ticket_machine",
            "course_or_drink_plan_evidence_found": category == "izakaya",
            "evidence_urls": [f"https://example.test/lead-{index}/menu"],
            "evidence_snippets": [snippet],
            "proof_items": [{
                "source_type": "official_or_shop_site",
                "url": f"https://example.test/lead-{index}/menu",
                "snippet": snippet,
                "operator_visible": True,
                "customer_preview_eligible": True,
                "rejection_reason": "",
            }],
            "contacts": [{"type": "email", "value": f"lead-{index}@example.test", "actionable": True}],
            "primary_contact": {"type": "email", "value": f"lead-{index}@example.test", "actionable": True},
            "establishment_profile": profile,
            "recommended_primary_package": package,
            "outreach_classification": classification,
            "outreach_assets_selected": [],
            "message_variant": "",
            "outreach_status": "new",
            "launch_batch_id": "",
            "launch_outcome": {},
            "status_history": [{"status": "new", "timestamp": "2026-04-29T00:00:00+00:00"}],
        })
    decisions = [
        {
            "lead_id": lead_id,
            "actual_readiness": "ready_for_outreach",
            "actual_package": profiles[index][3],
        }
        for index, lead_id in enumerate(lead_ids)
    ]
    write_json(run_dir / "decisions.json", decisions)
    write_json(run_dir / "mock-email-payloads.json", [])
    write_json(run_dir / "screenshot-manifest.json", [])
    write_json(run_dir / "report.json", {
        "run_id": "production-sim-recommend",
        "production_ready": True,
        "p0": 0,
        "p1": 0,
        "p2": 0,
        "candidate_count": 300,
        "labeled_count": 120,
        "ready_count": 5,
        "manual_review_count": 0,
        "disqualified_count": 295,
        "mock_sends_verified": 0,
        "screenshots": [],
        "findings": [],
        "next_required_fixes": [],
        "state_root": str(state_root),
        "corpus": "",
        "report_path": str(run_dir / "report.json"),
        "report_markdown_path": str(run_dir / "report.md"),
        "decisions_path": str(run_dir / "decisions.json"),
        "mock_email_payloads_path": str(run_dir / "mock-email-payloads.json"),
        "screenshot_manifest_path": str(run_dir / "screenshot-manifest.json"),
        "screenshots_dir": str(tmp_path / "qa-screenshots" / "production-sim-recommend"),
        "external_send_performed": False,
        "real_launch_batch_created": False,
    })
    return run_dir, lead_ids


def _write_labeling_corpus(root: Path) -> Path:
    root.mkdir(parents=True)
    candidates = [
        _label_candidate("wrm-label-ticket", "青空ラーメン", "Shibuya", "ramen", "ramen_ticket_machine", "ticket_machine_lookup", "https://ticket.example.jp", "03-1111-1111", "券売機 メニュー mailto:owner@ticket.example.jp"),
        _label_candidate("wrm-label-meal", "食券そば", "Namba", "ramen", "ramen_meal_ticket", "ticket_machine_lookup", "https://meal.example.jp", "06-1111-1111", "食券 ラーメン メニュー お問い合わせ"),
        _label_candidate("wrm-label-course", "酒場みなと", "Gion", "izakaya", "izakaya_nomihodai_course", "course_drink_lookup", "https://course.example.jp", "075-111-1111", "飲み放題 コース 居酒屋 line.me/R/ti/p/@course"),
        _label_candidate("wrm-label-chain", "Chain Ramen", "Umeda", "ramen", "ramen_chain_branch_check", "chain_infrastructure_check", "https://chain.example.jp", "06-2222-2222", "店舗一覧 チェーン ラーメン"),
        _label_candidate("wrm-label-english", "English Ramen", "Shinjuku", "ramen", "ramen_english_menu_check", "english_solution_check", "https://english.example.jp", "03-2222-2222", "English menu available contact form"),
        _label_candidate("wrm-label-mobile", "Mobile Izakaya", "Hakata", "izakaya", "izakaya_mobile_order_check", "mobile_order_solution_check", "https://instagram.com/mobile_izakaya", "092-111-1111", "mobile order multilingual QR instagram.com/mobile_izakaya"),
        _label_candidate("wrm-label-no-contact", "路地裏中華そば", "Nara", "ramen", "ramen_official_menu", "official_menu_lookup", "https://nocontact.example.jp", "", "ラーメン メニュー 味玉 チャーシュー"),
        _label_candidate("wrm-label-fetch-failed", "金沢酒場", "Kanazawa", "izakaya", "izakaya_menu_photo", "menu_photo_lookup", "https://broken.example.jp", "", "", capture_status="fetch_failed"),
    ]
    for candidate in candidates:
        pages = (candidate.get("capture") or {}).get("pages") or []
        for page in pages:
            write_text(root / page["path"], page["html"])
            del page["html"]
    write_json(root / "candidates.json", candidates)
    write_json(root / "manifest.json", {
        "schema_version": 2,
        "run_id": "label-workflow",
        "created_for": "PRODUCTION_SIMULATION_TEST_PLAN.md",
        "candidates_file": "candidates.json",
        "labels_dir": "labels",
        "external_send_allowed": False,
        "launch_batch_allowed": False,
        "candidate_count": len(candidates),
        "label_count": 0,
    })
    (root / "labels").mkdir()
    return root


def _label_candidate(
    candidate_id: str,
    name: str,
    city: str,
    category: str,
    job_id: str,
    purpose: str,
    website: str,
    phone: str,
    html: str,
    *,
    capture_status: str = "captured",
) -> dict:
    pages = []
    failures = []
    if capture_status == "captured":
        pages.append({
            "source": "homepage",
            "url": website,
            "path": f"pages/{candidate_id}/homepage.html",
            "bytes": len(html.encode("utf-8")),
            "sha256": "test",
            "html": f"<html><body>{html}</body></html>",
        })
    else:
        failures.append({
            "candidate_id": candidate_id,
            "business_name": name,
            "url": website,
            "source": "homepage",
            "error_type": "TimeoutError",
            "error": "timeout",
        })
    return {
        "candidate_id": candidate_id,
        "business_name": name,
        "website": website,
        "address": f"{city} Japan",
        "phone": phone,
        "category_hint": category,
        "source_search_job": {
            "job_id": job_id,
            "query": f"{job_id} {city}",
            "city": city,
            "category": category,
            "purpose": purpose,
        },
        "capture": {
            "status": capture_status,
            "serper_maps_artifacts": [f"serper/{candidate_id}.json"],
            "serper_web_artifacts": [],
            "pages": pages,
            "fetch_failures": failures,
        },
    }
