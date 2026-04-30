from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .constants import PROJECT_ROOT
from .email_html import LOGO_CID, MACHINE_CID, MENU_CID, build_pitch_email_html
from .launch import LaunchBatchError
from .launch_smoke import create_launch_smoke_test, prepare_launch_smoke_drafts
from .models import QualificationResult
from .outreach import build_outreach_email, classify_business
from .production_sim_oracle import evaluate_simulation
from .record import authoritative_business_name, get_primary_contact
from .search_replay import (
    collect_replay_corpus,
    copy_corpus_snapshot,
    load_replay_corpus,
    materialize_replay_state,
    prepare_stratified_labeling_workflow,
)
from .utils import ensure_dir, read_json, write_json, write_text


DEFAULT_CORPUS = PROJECT_ROOT / "tests" / "fixtures" / "production_sim" / "first_slice"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "state" / "production-sim"
DEFAULT_REPLAY_ROOT = PROJECT_ROOT / "state" / "search-replay"
DEFAULT_SCREENSHOT_ROOT = PROJECT_ROOT / "state" / "qa-screenshots"


def default_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"production-sim-{stamp}"


def run_replay(
    *,
    corpus_dir: str | Path = DEFAULT_CORPUS,
    run_id: str | None = None,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    replay_root: str | Path = DEFAULT_REPLAY_ROOT,
    screenshot_root: str | Path = DEFAULT_SCREENSHOT_ROOT,
    screenshots: bool = False,
    dashboard_port: int = 0,
) -> dict[str, Any]:
    """Run the deterministic no-send production simulation fixture."""
    run_id = run_id or default_run_id()
    run_dir = Path(output_root) / run_id
    state_root = run_dir / "state"
    screenshot_dir = Path(screenshot_root) / run_id
    replay_snapshot = Path(replay_root) / run_id

    ensure_dir(run_dir)
    ensure_dir(state_root)
    ensure_dir(screenshot_dir)
    copy_corpus_snapshot(corpus_dir=corpus_dir, replay_root=replay_snapshot)

    corpus = load_replay_corpus(corpus_dir)
    records = materialize_replay_state(corpus=corpus, state_root=state_root)
    decisions = [_decision_artifact(record=record, labels=corpus["labels"], state_root=state_root) for record in records]
    write_json(run_dir / "decisions.json", decisions)

    payloads = build_mock_email_payloads(records=records, labels=corpus["labels"])
    payload_path = run_dir / "mock-email-payloads.json"
    for payload in payloads:
        payload["payload_path"] = str(payload_path)
    write_json(payload_path, payloads)

    screenshot_manifest: list[dict[str, Any]] = []
    if screenshots:
        try:
            screenshot_manifest = capture_dashboard_screenshots(
                run_id=run_id,
                state_root=state_root,
                screenshot_dir=screenshot_dir,
                records=records,
                labels=corpus["labels"],
                port=dashboard_port,
            )
        except Exception as exc:
            screenshot_manifest = [{
                "path": "",
                "lead_id": "",
                "ui_state": "screenshot_error",
                "expected_assertion": "dashboard screenshots captured through Playwright",
                "actual_assertion": f"{type(exc).__name__}: {exc}",
            }]
    write_json(run_dir / "screenshot-manifest.json", screenshot_manifest)

    report = evaluate_simulation(
        records=records,
        labels=corpus["labels"],
        mock_payloads=payloads,
        screenshots=screenshot_manifest,
    )
    report.update({
        "run_id": run_id,
        "state_root": str(state_root),
        "corpus": str(corpus_dir),
        "replay_manifest": str(replay_snapshot / "manifest.json"),
        "report_path": str(run_dir / "report.json"),
        "report_markdown_path": str(run_dir / "report.md"),
        "decisions_path": str(run_dir / "decisions.json"),
        "mock_email_payloads_path": str(payload_path),
        "screenshot_manifest_path": str(run_dir / "screenshot-manifest.json"),
        "screenshots_dir": str(screenshot_dir),
        "external_send_performed": False,
        "real_launch_batch_created": False,
    })
    write_json(run_dir / "report.json", _report_json_payload(report))
    write_text(run_dir / "report.md", _report_markdown(report))
    return report


def collect_corpus(
    *,
    run_id: str | None = None,
    city_set: str = "launch-markets",
    cities: list[str] | None = None,
    category: str = "all",
    limit_per_job: int = 5,
    stage: str = "pilot",
    serper_api_key: str = "",
    search_provider: str | None = None,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    replay_root: str | Path = DEFAULT_REPLAY_ROOT,
    screenshot_root: str | Path = DEFAULT_SCREENSHOT_ROOT,
    fetch_timeout_seconds: int = 8,
    contact_pages_per_candidate: int = 2,
    evidence_pages_per_candidate: int = 2,
    maps_search_fn: Any | None = None,
    web_search_fn: Any | None = None,
    fetch_page_fn: Any | None = None,
) -> dict[str, Any]:
    """Collect a no-send pilot/broad replay corpus and write a report shell."""
    run_id = run_id or default_run_id().replace("production-sim-", "production-sim-pilot-corpus-", 1)
    run_dir = Path(output_root) / run_id
    screenshot_dir = Path(screenshot_root) / run_id
    ensure_dir(run_dir)
    ensure_dir(screenshot_dir)

    collection = collect_replay_corpus(
        run_id=run_id,
        replay_root=replay_root,
        city_set=city_set,
        cities=cities,
        category=category,
        limit_per_job=limit_per_job,
        stage=stage,
        serper_api_key=serper_api_key,
        search_provider=search_provider,
        fetch_timeout_seconds=fetch_timeout_seconds,
        contact_pages_per_candidate=contact_pages_per_candidate,
        evidence_pages_per_candidate=evidence_pages_per_candidate,
        maps_search_fn=maps_search_fn,
        web_search_fn=web_search_fn,
        fetch_page_fn=fetch_page_fn,
    )
    manifest = collection["manifest"]
    empty_payload_path = run_dir / "mock-email-payloads.json"
    write_json(run_dir / "decisions.json", [])
    write_json(empty_payload_path, [])
    write_json(run_dir / "screenshot-manifest.json", [])

    report = {
        "run_id": run_id,
        "production_ready": False,
        "p0": 0,
        "p1": 0,
        "p2": 1,
        "candidate_count": int(manifest.get("candidate_count") or 0),
        "labeled_count": int(manifest.get("label_count") or 0),
        "ready_count": 0,
        "manual_review_count": 0,
        "disqualified_count": 0,
        "mock_sends_verified": 0,
        "screenshots": [],
        "findings": [{
            "id": "P2-BROAD-CORPUS-LABELING-PENDING-001",
            "priority": "P2",
            "code": "BROAD-CORPUS-LABELING-PENDING",
            "lead_id": "",
            "business_name": "",
            "expected": "pilot/broad corpus collected, labeled, replayed, and dashboard-verified before production-ready claim",
            "actual": {
                "raw_candidates": manifest.get("raw_candidate_count"),
                "deduped_candidates": manifest.get("candidate_count"),
                "labels": manifest.get("label_count"),
                "fetch_failures": manifest.get("fetch_failure_count"),
            },
            "evidence": [str(collection["manifest_path"])],
            "fix_hint": "Label a stratified sample from this corpus, replay it offline, capture dashboard screenshots, and keep fixing until P0/P1 are zero.",
            "disposition": "deferred",
        }],
        "next_required_fixes": [
            "Label a stratified sample from this corpus, replay it offline, capture dashboard screenshots, and keep fixing until P0/P1 are zero."
        ],
        "state_root": "",
        "corpus": str(Path(replay_root) / run_id),
        "replay_manifest": str(collection["manifest_path"]),
        "report_path": str(run_dir / "report.json"),
        "report_markdown_path": str(run_dir / "report.md"),
        "decisions_path": str(run_dir / "decisions.json"),
        "mock_email_payloads_path": str(empty_payload_path),
        "screenshot_manifest_path": str(run_dir / "screenshot-manifest.json"),
        "screenshots_dir": str(screenshot_dir),
        "external_send_performed": False,
        "real_launch_batch_created": False,
        "collection_manifest_path": str(collection["manifest_path"]),
        "duplicates_path": str(Path(replay_root) / run_id / "duplicates.json"),
        "fetch_failures_path": str(Path(replay_root) / run_id / "fetch-failures.json"),
        "search_failures_path": str(Path(replay_root) / run_id / "search-failures.json"),
    }
    write_json(run_dir / "report.json", _report_json_payload(report))
    write_text(run_dir / "report.md", _report_markdown(report))
    return report


def prepare_labeling_workflow(
    *,
    corpus_dir: str | Path,
    sample_size: int = 120,
    seed: str = "production-sim-labeling-v1",
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    """Create a stratified no-send labeling workflow for a collected corpus."""
    summary = prepare_stratified_labeling_workflow(
        corpus_dir=corpus_dir,
        sample_size=sample_size,
        seed=seed,
    )
    run_id = str(summary["run_id"])
    run_dir = Path(output_root) / run_id
    ensure_dir(run_dir)

    existing_report = read_json(run_dir / "report.json", default={})
    report = dict(existing_report or {})
    report.update({
        "run_id": run_id,
        "production_ready": False,
        "p0": 0,
        "p1": 0,
        "p2": 1,
        "candidate_count": int(summary["candidate_count"]),
        "labeled_count": int(summary["finalized_label_count"]),
        "labeling_sample_count": int(summary["sample_size"]),
        "draft_label_count": int(summary["draft_label_count"]),
        "ready_count": int(report.get("ready_count") or 0),
        "manual_review_count": int(report.get("manual_review_count") or 0),
        "disqualified_count": int(report.get("disqualified_count") or 0),
        "mock_sends_verified": int(report.get("mock_sends_verified") or 0),
        "screenshots": list(report.get("screenshots") or []),
        "findings": [{
            "id": "P2-STRATIFIED-LABELING-PENDING-001",
            "priority": "P2",
            "code": "STRATIFIED-LABELING-PENDING",
            "lead_id": "",
            "business_name": "",
            "expected": "100-150 finalized operator labels plus offline replay and dashboard verification before production-ready claim",
            "actual": {
                "candidate_count": summary["candidate_count"],
                "finalized_labels": summary["finalized_label_count"],
                "draft_labels": summary["draft_label_count"],
                "labeling_sample": summary["sample_size"],
                "offline_replay_ready": summary["offline_replay_ready"],
                "dashboard_verification_ready": summary["dashboard_verification_ready"],
            },
            "evidence": [
                summary["sample_path"],
                summary["review_queue_path"],
                summary["checklist_path"],
                summary["offline_replay_plan_path"],
                summary["dashboard_verification_plan_path"],
            ],
            "fix_hint": "Complete reviewed labels in labels/, then run offline replay with screenshots and mocked payload verification.",
            "disposition": "deferred",
        }],
        "next_required_fixes": summary["next_required_fixes"],
        "corpus": str(summary["corpus"]),
        "labeling_summary_path": summary["summary_path"],
        "labeling_sample_path": summary["sample_path"],
        "labeling_drafts_dir": summary["drafts_dir"],
        "labeling_review_queue_path": summary["review_queue_path"],
        "labeling_checklist_path": summary["checklist_path"],
        "offline_replay_plan_path": summary["offline_replay_plan_path"],
        "dashboard_verification_plan_path": summary["dashboard_verification_plan_path"],
        "offline_replay_ready": summary["offline_replay_ready"],
        "dashboard_verification_ready": summary["dashboard_verification_ready"],
        "external_send_performed": False,
        "real_launch_batch_created": False,
    })
    report.setdefault("report_path", str(run_dir / "report.json"))
    report.setdefault("report_markdown_path", str(run_dir / "report.md"))
    report.setdefault("decisions_path", str(run_dir / "decisions.json"))
    report.setdefault("mock_email_payloads_path", str(run_dir / "mock-email-payloads.json"))
    report.setdefault("screenshot_manifest_path", str(run_dir / "screenshot-manifest.json"))
    report.setdefault("screenshots_dir", str(DEFAULT_SCREENSHOT_ROOT / run_id))
    write_json(run_dir / "report.json", _report_json_payload(report))
    write_text(run_dir / "report.md", _report_markdown(report))
    return report


def recommend_controlled_launch(
    *,
    run: str | Path,
    lead_ids: list[str],
    check_live_urls: bool = True,
    url_check_fn: Any | None = None,
) -> dict[str, Any]:
    """Run the no-send smoke gate and write the controlled-launch recommendation."""
    run_dir = _resolve_report_run_dir(run)
    report = load_report(run_dir)
    state_root = Path(str(report.get("state_root") or run_dir / "state"))
    decisions = read_json(Path(str(report.get("decisions_path") or run_dir / "decisions.json")), default=[])
    labels = _labels_for_report(report)
    findings = list(report.get("findings") or [])
    existing_batch_count = _launch_batch_count(state_root)

    smoke_summary: dict[str, Any] = {
        "passed": False,
        "smoke_test_id": "",
        "lead_count": len(lead_ids),
        "lead_ids": list(lead_ids),
        "state_root": str(state_root),
        "source_urls_checked": 0,
        "source_url_failures": [],
        "drafts_verified": False,
        "proof_assets_verified": False,
        "inline_assets_verified": False,
        "no_contact_marked": False,
        "real_launch_batch_created": existing_batch_count > 0,
        "external_send_performed": False,
        "counts_as_launch_batch": False,
    }

    smoke_findings: list[dict[str, Any]] = []
    if existing_batch_count:
        smoke_findings.append(_recommendation_finding(
            priority="P0",
            code="REAL-LAUNCH-BATCH-PRESENT",
            expected="no launch_batches records in simulation state during no-send smoke",
            actual={"launch_batch_count": existing_batch_count},
            fix_hint="Use an isolated production simulation state root and remove any real batch creation from the smoke path.",
        ))

    try:
        prepare_launch_smoke_drafts(lead_ids=lead_ids, state_root=state_root)
        smoke = create_launch_smoke_test(
            lead_ids=lead_ids,
            state_root=state_root,
            notes="production-sim no-send real-world smoke",
            scenario="production_sim_no_send_real_world_smoke",
        )
        smoke_summary.update({
            "smoke_test_id": smoke["smoke_test_id"],
            "smoke_path": str(state_root / "launch_smoke_tests" / f"{smoke['smoke_test_id']}.json"),
            "external_send_performed": bool(smoke.get("external_send_performed")),
            "counts_as_launch_batch": bool(smoke.get("counts_as_launch_batch")),
        })
        smoke_findings.extend(_verify_smoke_acceptance(
            smoke=smoke,
            lead_ids=lead_ids,
            state_root=state_root,
            labels=labels,
            check_live_urls=check_live_urls,
            url_check_fn=url_check_fn or _url_loads,
            summary=smoke_summary,
        ))
    except LaunchBatchError as exc:
        smoke_findings.append(_recommendation_finding(
            priority="P1",
            code="NO-SEND-SMOKE-FAILED",
            expected="5-10 selected leads pass the same launch-readiness gates without sending",
            actual=str(exc),
            fix_hint="Generate/review drafts and fix the selected lead set until launch smoke validates one ramen ticket-machine and one izakaya drink/course lead.",
        ))

    smoke_findings = _number_recommendation_findings(smoke_findings)
    findings.extend(smoke_findings)
    smoke_blockers = [item for item in smoke_findings if item["priority"] in {"P0", "P1"}]
    smoke_summary["passed"] = not smoke_blockers and bool(smoke_summary.get("smoke_test_id"))

    existing_ready = bool(report.get("production_ready")) and int(report.get("p0") or 0) == 0 and int(report.get("p1") or 0) == 0
    recommendation = (
        "PROCEED_TO_CONTROLLED_BATCH_1_SELECTION"
        if existing_ready and smoke_summary["passed"]
        else "DO_NOT_LAUNCH_REQUIRED_FIXES_REMAIN"
    )
    package_distribution = Counter(
        str(item.get("actual_package") or "none")
        for item in decisions
        if str(item.get("actual_readiness") or "") == "ready_for_outreach"
    )

    report.update({
        "no_send_smoke": smoke_summary,
        "controlled_launch_recommendation": recommendation,
        "controlled_launch_recommendation_reason": (
            "simulation production_ready=true and no-send smoke passed with zero P0/P1 findings"
            if recommendation == "PROCEED_TO_CONTROLLED_BATCH_1_SELECTION"
            else "production simulation or no-send smoke still has launch-blocking findings"
        ),
        "controlled_launch_selection_allowed": recommendation == "PROCEED_TO_CONTROLLED_BATCH_1_SELECTION",
        "real_outreach_performed": False,
        "external_send_performed": False,
        "real_launch_batch_created": _launch_batch_count(state_root) > 0,
        "package_distribution": dict(sorted(package_distribution.items())),
        "false_ready_count": _count_findings(findings, "READINESS-MISMATCH", "P0"),
        "wrong_package_count": _count_findings(findings, "PACKAGE-MISMATCH", "P0") + _count_findings(findings, "PACKAGE-MISMATCH", "P1"),
        "wrong_inline_assets_count": _count_findings(findings, "INLINE-ASSET-MISMATCH", "P0") + _count_findings(findings, "INLINE-ASSET-MISMATCH", "P1"),
        "findings": findings,
    })
    report["p0"] = sum(1 for item in findings if item.get("priority") == "P0")
    report["p1"] = sum(1 for item in findings if item.get("priority") == "P1")
    report["p2"] = sum(1 for item in findings if item.get("priority") == "P2")
    report["production_ready"] = existing_ready and smoke_summary["passed"] and report["p0"] == 0 and report["p1"] == 0
    report["next_required_fixes"] = [
        str(item["fix_hint"])
        for item in findings
        if item.get("priority") in {"P0", "P1"} or item.get("disposition") == "deferred"
    ]

    write_json(run_dir / "report.json", _report_json_payload(report))
    write_text(run_dir / "report.md", _report_markdown(report))
    write_json(run_dir / "controlled-launch-recommendation.json", {
        "run_id": report.get("run_id"),
        "recommendation": recommendation,
        "no_send_smoke": smoke_summary,
        "p0": report["p0"],
        "p1": report["p1"],
        "p2": report["p2"],
        "report_path": str(run_dir / "report.json"),
        "report_markdown_path": str(run_dir / "report.md"),
        "external_send_performed": False,
        "real_launch_batch_created": report["real_launch_batch_created"],
    })
    return report


def build_mock_email_payloads(*, records: list[dict[str, Any]], labels: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Build no-send email payloads for expected-ready email candidates."""
    payloads: list[dict[str, Any]] = []
    for record in records:
        candidate_id = str(record.get("production_sim_candidate_id") or record.get("lead_id") or "")
        label = labels[candidate_id]
        if label["readiness_expected"] != "ready_for_outreach" or label["contact_route_expected"] != "email":
            continue
        if record.get("launch_readiness_status") != "ready_for_outreach":
            continue
        payloads.append(build_mock_email_payload(record))
    return payloads


def build_mock_email_payload(record: dict[str, Any]) -> dict[str, Any]:
    """Create the same logical email payload shape without calling Resend."""
    business_name = authoritative_business_name(record)
    primary = get_primary_contact(record) or {}
    q = QualificationResult(
        lead=record.get("lead") is True,
        rejection_reason=record.get("rejection_reason"),
        business_name=business_name,
        menu_evidence_found=record.get("menu_evidence_found", True),
        machine_evidence_found=record.get("machine_evidence_found", False),
    )
    classification = str(record.get("outreach_classification") or classify_business(q))
    establishment_profile = str(record.get("establishment_profile") or "unknown")
    draft = build_outreach_email(
        business_name=business_name,
        classification=classification,
        establishment_profile=establishment_profile,
        include_inperson_line=record.get("outreach_include_inperson", True),
        lead_dossier=record.get("lead_evidence_dossier") or {},
    )
    include_menu = bool(draft["include_menu_image"])
    include_machine = bool(record.get("outreach_include_machine_image", draft["include_machine_image"]))
    html_body = build_pitch_email_html(
        text_body=str(draft["body"]),
        include_menu_image=include_menu,
        include_machine_image=include_machine,
        locale="ja",
    )
    cid_references = sorted(set(re.findall(r"cid:([A-Za-z0-9_-]+)", html_body)))
    inline_attachments = [{"filename": "logo.png", "mime_type": "image/png", "content_id": LOGO_CID}]
    if include_menu:
        inline_attachments.append({"filename": "english-menu-sample.jpg", "mime_type": "image/jpeg", "content_id": MENU_CID})
    if include_machine:
        inline_attachments.append({"filename": "ticket-machine-guide.jpg", "mime_type": "image/jpeg", "content_id": MACHINE_CID})

    return {
        "lead_id": record.get("lead_id"),
        "business_name": business_name,
        "recipient": str(primary.get("value") or "").strip().lower(),
        "reply_to": os.environ.get("RESEND_REPLY_TO_EMAIL", os.environ.get("RESEND_FROM_EMAIL", "chris@webrefurb.com")).strip() or "chris@webrefurb.com",
        "subject": draft["subject"],
        "text_body": draft["body"],
        "html_body": html_body,
        "cid_references": cid_references,
        "inline_attachments": inline_attachments,
        "file_attachments": [],
        "filenames": [item["filename"] for item in inline_attachments],
        "mime_types": [item["mime_type"] for item in inline_attachments],
        "content_ids": [item["content_id"] for item in inline_attachments],
        "selected_package": record.get("recommended_primary_package"),
        "establishment_profile": establishment_profile,
        "outreach_classification": classification,
        "selected_assets": list(record.get("outreach_assets_selected") or []),
        "mock_send": True,
        "external_send_performed": False,
    }


def capture_dashboard_screenshots(
    *,
    run_id: str,
    state_root: str | Path,
    screenshot_dir: str | Path,
    records: list[dict[str, Any]],
    labels: dict[str, dict[str, Any]],
    port: int = 0,
) -> list[dict[str, Any]]:
    """Drive the dashboard with Playwright and save operator-state screenshots."""
    ensure_dir(Path(screenshot_dir))
    port = port or _free_port()
    proc = _start_dashboard_server(state_root=Path(state_root), port=port)
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_dashboard(base_url)
        return _playwright_dashboard_flow(
            base_url=base_url,
            screenshot_dir=Path(screenshot_dir),
            records=records,
            labels=labels,
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()


def report_fails_on(report: dict[str, Any], priorities: set[str]) -> bool:
    return any(report.get(priority.lower(), 0) for priority in priorities)


def _decision_artifact(*, record: dict[str, Any], labels: dict[str, dict[str, Any]], state_root: Path) -> dict[str, Any]:
    candidate_id = str(record.get("production_sim_candidate_id") or record.get("lead_id") or "")
    label = labels[candidate_id]
    return {
        "candidate_id": candidate_id,
        "lead_id": record.get("lead_id"),
        "business_name": record.get("business_name"),
        "expected_readiness": label["readiness_expected"],
        "actual_readiness": record.get("launch_readiness_status"),
        "expected_package": label["package_expected"],
        "actual_package": record.get("recommended_primary_package"),
        "expected_contact_route": label["contact_route_expected"],
        "actual_contact_route": str((get_primary_contact(record) or {}).get("type") or "none"),
        "record_path": str(state_root / "leads" / f"{record.get('lead_id')}.json"),
        "readiness_reasons": record.get("launch_readiness_reasons") or [],
    }


def _start_dashboard_server(*, state_root: Path, port: int) -> subprocess.Popen:
    env = dict(os.environ)
    env["WEBREFURB_STATE_ROOT"] = str(state_root.resolve())
    env["RESEND_API_KEY"] = ""
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "dashboard.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_for_dashboard(base_url: str) -> None:
    deadline = time.time() + 30
    last_error = ""
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/api/leads", timeout=2)
            if response.status_code == 200:
                return
            last_error = f"status {response.status_code}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"dashboard did not become ready: {last_error}")


def _playwright_dashboard_flow(
    *,
    base_url: str,
    screenshot_dir: Path,
    records: list[dict[str, Any]],
    labels: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    from playwright.sync_api import sync_playwright

    manifest: list[dict[str, Any]] = []
    ready_records = _dashboard_records_by_actual(records, "ready_for_outreach")
    manual_records = _dashboard_records_by_actual(records, "manual_review")
    disqualified_records = _dashboard_records_by_actual(records, "disqualified")
    ticket_ready = _first_with_asset(ready_records, "ticket_machine_guide")
    izakaya_ready = _first_with_asset(ready_records, "izakaya_food_drinks")
    first_ready = ready_records[0] if ready_records else None

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
        page.goto(base_url, wait_until="networkidle")
        page.locator("#lead-list").wait_for(timeout=15000)
        _screenshot(page, "dashboard-overview.png", screenshot_dir, manifest, "", "dashboard_overview", "lead buckets visible", "dashboard loaded")

        if first_ready:
            _card_screenshot(page, first_ready, "ready-lead-card.png", screenshot_dir, manifest, "ready_lead_card", "ready card shows fit/proof/contact/package")
        if manual_records:
            _card_screenshot(page, manual_records[0], "manual-review-card.png", screenshot_dir, manifest, "manual_review_card", "manual review card shows readiness reason")
        if disqualified_records:
            _card_screenshot(page, disqualified_records[0], "disqualified-card.png", screenshot_dir, manifest, "disqualified_card", "disqualified card is blocked/read-only")

        if ticket_ready:
            _open_preview(page, ticket_ready)
            _screenshot(page, "outreach-editor-ticket-machine.png", screenshot_dir, manifest, str(ticket_ready["lead_id"]), "outreach_editor", "outreach editor opens for ready lead", "editor visible")
            _locator_screenshot(page, "#jp-preview", "inline-ticket-machine-sample.png", screenshot_dir, manifest, str(ticket_ready["lead_id"]), "inline_ticket_machine_sample", "ticket-machine CID preview visible")
            _locator_screenshot(page, "#jp-preview", "inline-menu-sample-ticket-lead.png", screenshot_dir, manifest, str(ticket_ready["lead_id"]), "inline_menu_sample", "menu CID preview visible")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        elif first_ready:
            _open_preview(page, first_ready)
            _screenshot(page, "outreach-editor-ready.png", screenshot_dir, manifest, str(first_ready["lead_id"]), "outreach_editor", "outreach editor opens for ready lead", "editor visible")
            _locator_screenshot(page, "#jp-preview", "inline-menu-sample.png", screenshot_dir, manifest, str(first_ready["lead_id"]), "inline_menu_sample", "menu CID preview visible")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

        if izakaya_ready:
            _open_preview(page, izakaya_ready)
            _locator_screenshot(page, "#jp-preview", "inline-izakaya-sample.png", screenshot_dir, manifest, str(izakaya_ready["lead_id"]), "inline_izakaya_sample", "izakaya food/drinks sample visible")
            page.keyboard.press("Escape")

        browser.close()

    return manifest


def _open_preview(page: Any, record: dict[str, Any]) -> None:
    lead_id = str(record["lead_id"])
    card = page.locator(f'[data-lead-id="{lead_id}"]')
    card.locator("button.btn-secondary").first.click()
    page.locator("#preview-modal[open]").wait_for(timeout=20000)
    page.locator("#jp-preview").wait_for(timeout=20000)


def _card_screenshot(
    page: Any,
    record: dict[str, Any],
    filename: str,
    screenshot_dir: Path,
    manifest: list[dict[str, Any]],
    ui_state: str,
    expected: str,
) -> None:
    lead_id = str(record["lead_id"])
    locator = page.locator(f'[data-lead-id="{lead_id}"]')
    path = screenshot_dir / filename
    locator.screenshot(path=str(path))
    manifest.append({
        "path": str(path),
        "lead_id": lead_id,
        "ui_state": ui_state,
        "expected_assertion": expected,
        "actual_assertion": "card captured",
    })


def _screenshot(
    page: Any,
    filename: str,
    screenshot_dir: Path,
    manifest: list[dict[str, Any]],
    lead_id: str,
    ui_state: str,
    expected: str,
    actual: str,
) -> None:
    path = screenshot_dir / filename
    page.screenshot(path=str(path), full_page=True)
    manifest.append({
        "path": str(path),
        "lead_id": lead_id,
        "ui_state": ui_state,
        "expected_assertion": expected,
        "actual_assertion": actual,
    })


def _locator_screenshot(
    page: Any,
    selector: str,
    filename: str,
    screenshot_dir: Path,
    manifest: list[dict[str, Any]],
    lead_id: str,
    ui_state: str,
    expected: str,
) -> None:
    path = screenshot_dir / filename
    page.locator(selector).screenshot(path=str(path))
    manifest.append({
        "path": str(path),
        "lead_id": lead_id,
        "ui_state": ui_state,
        "expected_assertion": expected,
        "actual_assertion": "element captured",
    })


def _records_by_expected(records: list[dict[str, Any]], labels: dict[str, dict[str, Any]], readiness: str) -> list[dict[str, Any]]:
    return [
        record for record in records
        if labels[str(record.get("production_sim_candidate_id") or record.get("lead_id"))]["readiness_expected"] == readiness
        and record.get("lead") is True
    ]


def _dashboard_records_by_actual(records: list[dict[str, Any]], readiness: str) -> list[dict[str, Any]]:
    if readiness == "ready_for_outreach":
        return [
            record for record in records
            if record.get("lead") is True
            and record.get("launch_readiness_status") == readiness
            and str((get_primary_contact(record) or {}).get("type") or "") in {"email", "contact_form"}
        ]
    return [
        record for record in records
        if (
            record.get("lead") is True
            or (
                record.get("production_sim_fixture") is True
                and record.get("launch_readiness_status") == "disqualified"
            )
        )
        and record.get("launch_readiness_status") == readiness
    ]


def _first_with_asset(records: list[dict[str, Any]], asset_key: str) -> dict[str, Any] | None:
    for record in records:
        if any(asset_key in str(path) for path in record.get("outreach_assets_selected") or []):
            return record
    return None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _report_json_payload(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "decisions"}


def _report_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Production Simulation Report: {report['run_id']}",
        "",
        f"- production_ready: `{str(report['production_ready']).lower()}`",
        f"- candidates: `{report['candidate_count']}`",
        f"- labeled: `{report['labeled_count']}`",
        f"- ready/manual/disqualified: `{report['ready_count']}` / `{report['manual_review_count']}` / `{report['disqualified_count']}`",
        f"- mocked sends verified: `{report['mock_sends_verified']}`",
        f"- P0/P1/P2: `{report['p0']}` / `{report['p1']}` / `{report['p2']}`",
        f"- package distribution: `{report.get('package_distribution') or {}}`",
        f"- false-ready count: `{report.get('false_ready_count', 0)}`",
        f"- wrong-package count: `{report.get('wrong_package_count', 0)}`",
        f"- wrong-inline-assets count: `{report.get('wrong_inline_assets_count', 0)}`",
        f"- external_send_performed: `{str(report['external_send_performed']).lower()}`",
        f"- real_launch_batch_created: `{str(report['real_launch_batch_created']).lower()}`",
        "",
        "## Artifacts",
        "",
        f"- report JSON: `{report['report_path']}`",
        f"- decisions: `{report['decisions_path']}`",
        f"- mock email payloads: `{report['mock_email_payloads_path']}`",
        f"- screenshot manifest: `{report['screenshot_manifest_path']}`",
        f"- screenshots: `{report['screenshots_dir']}`",
        "",
    ]
    if report.get("no_send_smoke"):
        smoke = report["no_send_smoke"]
        lines.extend([
            "## No-Send Smoke",
            "",
            f"- passed: `{str(smoke.get('passed')).lower()}`",
            f"- smoke test ID: `{smoke.get('smoke_test_id') or 'n/a'}`",
            f"- lead count: `{smoke.get('lead_count')}`",
            f"- source URLs checked: `{smoke.get('source_urls_checked')}`",
            f"- drafts verified: `{str(smoke.get('drafts_verified')).lower()}`",
            f"- proof assets verified: `{str(smoke.get('proof_assets_verified')).lower()}`",
            f"- inline assets verified: `{str(smoke.get('inline_assets_verified')).lower()}`",
            f"- no contact marked: `{str(smoke.get('no_contact_marked')).lower()}`",
            "",
        ])
    if report.get("controlled_launch_recommendation"):
        lines.extend([
            "## Controlled Launch Recommendation",
            "",
            f"`{report['controlled_launch_recommendation']}`",
            "",
            str(report.get("controlled_launch_recommendation_reason") or ""),
            "",
        ])
    lines.extend([
        "## Findings",
        "",
    ])
    if report["findings"]:
        for finding in report["findings"]:
            lines.extend([
                f"### {finding['id']}",
                "",
                f"- priority: `{finding['priority']}`",
                f"- disposition: `{finding['disposition']}`",
                f"- lead: `{finding.get('lead_id') or 'n/a'}`",
                f"- expected: `{finding['expected']}`",
                f"- actual: `{finding['actual']}`",
                f"- fix hint: {finding['fix_hint']}",
                "",
            ])
    else:
        lines.append("No findings.")
        lines.append("")
    return "\n".join(lines)


def load_report(run_dir: str | Path) -> dict[str, Any]:
    report = read_json(Path(run_dir) / "report.json")
    if not isinstance(report, dict):
        raise FileNotFoundError(f"report not found under {run_dir}")
    return report


def _verify_smoke_acceptance(
    *,
    smoke: dict[str, Any],
    lead_ids: list[str],
    state_root: Path,
    labels: dict[str, dict[str, Any]],
    check_live_urls: bool,
    url_check_fn: Any,
    summary: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    source_failures: list[dict[str, str]] = []
    source_checked = 0
    drafts_ok = True
    proof_assets_ok = True
    inline_assets_ok = True
    no_contact_ok = True

    if smoke.get("external_send_performed") or smoke.get("send_allowed") or smoke.get("counts_as_launch_batch"):
        findings.append(_recommendation_finding(
            priority="P0",
            code="SMOKE-SEND-BOUNDARY-BROKEN",
            expected="no-send smoke cannot send or count as a launch batch",
            actual={
                "external_send_performed": smoke.get("external_send_performed"),
                "send_allowed": smoke.get("send_allowed"),
                "counts_as_launch_batch": smoke.get("counts_as_launch_batch"),
            },
            fix_hint="Keep launch smoke in rehearsal mode with send_allowed=false and counts_as_launch_batch=false.",
        ))

    for lead_id in lead_ids:
        lead = read_json(state_root / "leads" / f"{lead_id}.json", default={})
        if not lead:
            findings.append(_recommendation_finding(
                priority="P1",
                code="SMOKE-LEAD-MISSING",
                lead_id=lead_id,
                expected="selected smoke lead exists in isolated state",
                actual="missing",
                fix_hint="Select only materialized production-sim leads for the no-send smoke.",
            ))
            continue
        if not str(lead.get("message_variant") or "") or not str(lead.get("outreach_draft_body") or ""):
            drafts_ok = False
            findings.append(_recommendation_finding(
                priority="P1",
                code="SMOKE-DRAFT-MISSING",
                lead_id=lead_id,
                business_name=str(lead.get("business_name") or ""),
                expected="message_variant and no-send draft body exist before controlled launch selection",
                actual={"message_variant": lead.get("message_variant"), "draft_body": bool(lead.get("outreach_draft_body"))},
                fix_hint="Generate and review no-send outreach drafts before including the lead in smoke or launch selection.",
            ))
        selected_assets = [Path(str(path)) for path in lead.get("outreach_assets_selected") or []]
        contact_type = str(((lead.get("primary_contact") or {}).get("type")) or "")
        if contact_type != "contact_form" and not selected_assets:
            proof_assets_ok = False
            findings.append(_recommendation_finding(
                priority="P1",
                code="SMOKE-PROOF-ASSET-MISSING",
                lead_id=lead_id,
                business_name=str(lead.get("business_name") or ""),
                expected="non-contact-form smoke lead has selected proof/sample assets",
                actual=[],
                fix_hint="Tune outreach asset selection or route contact-form leads through no-attachment copy.",
            ))
        for asset in selected_assets:
            if not asset.exists():
                proof_assets_ok = False
                findings.append(_recommendation_finding(
                    priority="P1",
                    code="SMOKE-PROOF-ASSET-MISSING",
                    lead_id=lead_id,
                    business_name=str(lead.get("business_name") or ""),
                    expected="selected proof/sample asset exists on disk",
                    actual=str(asset),
                    fix_hint="Regenerate the selected sample asset or replace stale asset paths before launch selection.",
                ))
        label = labels.get(str(lead.get("production_sim_candidate_id") or lead_id))
        if label:
            expected_assets = sorted(label.get("inline_assets_expected") or [])
            actual_assets = _logical_asset_names([str(path) for path in selected_assets])
            if expected_assets != actual_assets:
                inline_assets_ok = False
                findings.append(_recommendation_finding(
                    priority="P1",
                    code="SMOKE-INLINE-ASSET-MISMATCH",
                    lead_id=lead_id,
                    business_name=str(lead.get("business_name") or ""),
                    expected=expected_assets,
                    actual=actual_assets,
                    fix_hint="Align outreach asset selection with the reviewed label profile before controlled launch selection.",
                ))
        urls = _source_urls_for_smoke_lead(lead)
        if check_live_urls and not urls:
            source_failures.append({"lead_id": lead_id, "url": "", "error": "no_source_url"})
        for url in urls:
            if not check_live_urls:
                continue
            source_checked += 1
            if not url_check_fn(url):
                source_failures.append({"lead_id": lead_id, "url": url, "error": "not_loadable"})
        if lead.get("launch_batch_id") or lead.get("outreach_sent_at"):
            no_contact_ok = False
            findings.append(_recommendation_finding(
                priority="P0",
                code="SMOKE-MARKED-CONTACTED",
                lead_id=lead_id,
                business_name=str(lead.get("business_name") or ""),
                expected="smoke lead remains uncontacted and outside launch batches",
                actual={"launch_batch_id": lead.get("launch_batch_id"), "outreach_sent_at": lead.get("outreach_sent_at")},
                fix_hint="Remove real contact/batch mutation from no-send smoke and rerun from isolated state.",
            ))

    for entry in smoke.get("leads") or []:
        if entry.get("contacted_at") or entry.get("reply_status") != "not_contacted" or entry.get("external_send_performed"):
            no_contact_ok = False
            findings.append(_recommendation_finding(
                priority="P0",
                code="SMOKE-ENTRY-MARKED-CONTACTED",
                lead_id=str(entry.get("lead_id") or ""),
                business_name=str(entry.get("business_name") or ""),
                expected="smoke entry remains not_contacted",
                actual={
                    "contacted_at": entry.get("contacted_at"),
                    "reply_status": entry.get("reply_status"),
                    "external_send_performed": entry.get("external_send_performed"),
                },
                fix_hint="Keep smoke outcomes simulated only and never write contacted timestamps.",
            ))

    if source_failures:
        findings.append(_recommendation_finding(
            priority="P1",
            code="SMOKE-SOURCE-URL-CHECK-FAILED",
            expected="all selected smoke source URLs still load",
            actual=source_failures,
            fix_hint="Refresh or replace stale source evidence, then promote the surprise into replay labels if it affects readiness.",
        ))

    summary.update({
        "source_urls_checked": source_checked,
        "source_url_failures": source_failures,
        "drafts_verified": drafts_ok,
        "proof_assets_verified": proof_assets_ok,
        "inline_assets_verified": inline_assets_ok,
        "no_contact_marked": no_contact_ok,
        "real_launch_batch_created": _launch_batch_count(state_root) > 0,
    })
    return findings


def _resolve_report_run_dir(run: str | Path) -> Path:
    run_path = Path(run)
    if run_path.exists():
        return run_path
    return DEFAULT_OUTPUT_ROOT / str(run)


def _labels_for_report(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    corpus_path = str(report.get("corpus") or "").strip()
    if not corpus_path:
        return {}
    try:
        corpus = load_replay_corpus(corpus_path, require_labels=False)
    except Exception:
        return {}
    return corpus.get("labels") or {}


def _source_urls_for_smoke_lead(lead: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for item in lead.get("evidence_urls") or []:
        value = str(item or "").strip()
        if value.startswith(("http://", "https://")) and value not in urls:
            urls.append(value)
    for item in lead.get("proof_items") or (lead.get("lead_evidence_dossier") or {}).get("proof_items") or []:
        value = str((item or {}).get("url") or "").strip()
        if value.startswith(("http://", "https://")) and value not in urls:
            urls.append(value)
    website = str(lead.get("website") or "").strip()
    if website.startswith(("http://", "https://")) and website not in urls:
        urls.append(website)
    return urls[:5]


def _url_loads(url: str) -> bool:
    try:
        response = httpx.head(url, timeout=8, follow_redirects=True)
        if response.status_code < 500 and response.status_code not in {403, 404, 410}:
            return True
    except Exception:
        pass
    try:
        response = httpx.get(url, timeout=10, follow_redirects=True)
        return response.status_code < 500 and response.status_code not in {403, 404, 410}
    except Exception:
        return False


def _logical_asset_names(paths: list[str]) -> list[str]:
    result: list[str] = []
    for value in paths:
        name = str(value)
        if "ticket_machine_guide" in name:
            result.append("ticket_machine_guide")
        elif "izakaya_food_drinks_menu" in name or "izakaya_food_menu" in name or "izakaya_drinks_menu" in name:
            result.append("izakaya_food_drinks")
        elif "ramen_food_menu" in name or "ramen_drinks_menu" in name:
            result.append("ramen_food_menu")
        elif name:
            result.append(name)
    return sorted(set(result))


def _launch_batch_count(state_root: Path) -> int:
    root = state_root / "launch_batches"
    if not root.exists():
        return 0
    return len(list(root.glob("launch-*.json")))


def _recommendation_finding(
    *,
    priority: str,
    code: str,
    expected: Any,
    actual: Any,
    fix_hint: str,
    lead_id: str = "",
    business_name: str = "",
) -> dict[str, Any]:
    return {
        "id": "",
        "priority": priority,
        "code": code,
        "lead_id": lead_id,
        "business_name": business_name,
        "expected": expected,
        "actual": actual,
        "evidence": [],
        "fix_hint": fix_hint,
        "disposition": "blocker" if priority in {"P0", "P1"} else "observation",
    }


def _number_recommendation_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counters: dict[tuple[str, str], int] = {}
    numbered: list[dict[str, Any]] = []
    for finding in findings:
        key = (str(finding["priority"]), str(finding["code"]))
        counters[key] = counters.get(key, 0) + 1
        item = dict(finding)
        item["id"] = f"{item['priority']}-{item['code']}-{counters[key]:03d}"
        numbered.append(item)
    return numbered


def _count_findings(findings: list[dict[str, Any]], code: str, priority: str) -> int:
    return sum(1 for item in findings if item.get("code") == code and item.get("priority") == priority)
