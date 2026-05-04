"""Run 8 no-send production-readiness verification helpers."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .constants import PACKAGE_1_KEY, PACKAGE_2_KEY, PACKAGE_3_KEY, PROJECT_ROOT
from .export import build_custom_package
from .final_export_qa import sha256_file, validate_qr_artifacts, validate_zip_package
from .launch import validate_launch_leads, LaunchBatchError
from .operator_state import OPERATOR_READY
from .package_export import approve_package_export
from .populate import build_menu_data, build_ticket_data
from .production_workflow import ingest_owner_assets
from .qr import approve_qr_package, create_qr_draft, create_qr_sign
from .record import get_primary_contact
from .utils import ensure_dir, read_json, utc_now, write_json


SCREEN_NAMES = (
    "dashboard-operator-queue",
    "dashboard-review-lane",
    "dashboard-ready-lane",
    "dashboard-skipped-lane",
    "dashboard-done-lane",
    "lead-evidence-debug-drawer",
    "outreach-modal",
    "reply-intake-lane",
    "owner-asset-inbox",
    "extraction-review-workspace",
    "ticket-machine-mapping-workspace",
    "build-studio",
    "owner-preview",
    "homepage",
    "pricing",
    "sample-ramen-preview",
    "sample-izakaya-preview",
    "qr-menu",
    "qr-sign",
)


def run_run8_readiness(
    *,
    state_root: Path,
    docs_root: Path,
    capture_screenshots: bool = True,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run the Run 8 no-send verification path without contacting shops."""
    run_id = run_id or _run_id()
    artifacts = ensure_run8_artifacts(state_root=state_root, docs_root=docs_root, run_id=run_id)
    smoke_gate = write_no_send_smoke_gate_report(state_root=state_root, run_id=run_id)
    download_validation = validate_sample_exports(artifacts["exports"])
    screenshot_report = {
        "ok": False,
        "skipped": True,
        "screenshots": [],
        "console_errors": [],
        "findings": ["screenshot_capture_skipped"],
    }
    if capture_screenshots:
        screenshot_report = capture_run8_screenshots(
            state_root=state_root,
            docs_root=docs_root,
            run_id=run_id,
            artifacts=artifacts,
        )

    blockers: list[str] = []
    if not download_validation["ok"]:
        blockers.append("sample_export_download_validation_failed")
    if capture_screenshots and not screenshot_report["ok"]:
        blockers.append("browser_screenshot_validation_failed")
    if not smoke_gate["passed"]:
        blockers.extend(smoke_gate["blockers"])

    report = {
        "run_id": run_id,
        "created_at": utc_now(),
        "no_real_outreach": True,
        "external_send_performed": False,
        "real_launch_batch_created": False,
        "artifacts": artifacts,
        "download_validation": download_validation,
        "screenshots": screenshot_report,
        "no_send_smoke_gate": smoke_gate,
        "controlled_launch_selection_allowed": smoke_gate["passed"] and not blockers,
        "blockers": sorted(set(blockers)),
    }
    report["ok_until_send_gate"] = download_validation["ok"] and (not capture_screenshots or screenshot_report["ok"])
    report["completion_gate"] = {
        "screenshots_cover_actual_screens": bool(capture_screenshots and screenshot_report["ok"]),
        "final_exports_downloaded_opened_validated": download_validation["ok"],
        "known_visual_content_export_print_defects_tracked": not screenshot_report.get("findings") and download_validation["ok"],
        "batch1_contains_5_to_10_reviewed_leads": smoke_gate["passed"],
        "contacted_leads_have_measurement_records": False,
        "blocked_reason": "real outreach and contacted-lead measurement require explicit current-chat send approval",
    }
    output_path = state_root / "run8-readiness" / f"{run_id}.json"
    write_json(output_path, report)
    report["report_path"] = str(output_path)
    return report


def ensure_run8_artifacts(*, state_root: Path, docs_root: Path, run_id: str) -> dict[str, Any]:
    reply = _ensure_workspace_reply(state_root=state_root, run_id=run_id)
    p1 = _build_and_approve_package(
        state_root=state_root,
        job_id=f"{run_id}-package1",
        package_key=PACKAGE_1_KEY,
        item_count=18,
        include_ticket=False,
    )
    p2 = _build_and_approve_package(
        state_root=state_root,
        job_id=f"{run_id}-package2",
        package_key=PACKAGE_2_KEY,
        item_count=50,
        include_ticket=True,
        delivery_details={
            "delivery_contact_name": "Run 8 Operator",
            "delivery_address": "1-2-3 Tokyo",
            "delivery_phone": "",
            "delivery_notes": "Run 8 no-send sample export.",
        },
    )
    p3 = _build_and_approve_qr_package(
        state_root=state_root,
        docs_root=docs_root,
        reply=reply,
        run_id=run_id,
    )
    return {
        "reply_id": reply["reply_id"],
        "exports": {
            PACKAGE_1_KEY: p1,
            PACKAGE_2_KEY: p2,
            PACKAGE_3_KEY: p3,
        },
    }


def write_no_send_smoke_gate_report(*, state_root: Path, run_id: str) -> dict[str, Any]:
    """Attempt the same readiness gate as a real launch, but do not send or create a batch."""
    candidates = _launch_ready_candidates(state_root)
    selected = _select_smoke_candidates(candidates)
    blockers: list[str] = []
    validation_error = ""
    smoke_entries: list[dict[str, Any]] = []
    if len(selected) < 5:
        blockers.append("ready_for_outreach_count_below_5")
    if not any(item.get("establishment_profile") == "ramen_ticket_machine" for item in selected):
        blockers.append("missing_ramen_ticket_machine_candidate")
    if not any(item.get("establishment_profile") in {"izakaya_drink_heavy", "izakaya_course_heavy"} for item in selected):
        blockers.append("missing_izakaya_drink_or_course_candidate")
    if not blockers:
        try:
            smoke_entries, _ = validate_launch_leads(
                lead_ids=[str(item["lead_id"]) for item in selected],
                state_root=state_root,
            )
        except LaunchBatchError as exc:
            validation_error = str(exc)
            blockers.append("same_gate_validation_failed")

    report = {
        "rehearsal_id": f"{run_id}-no-send-smoke-gate",
        "created_at": utc_now(),
        "source": "live_state_public_shop_evidence",
        "passed": not blockers,
        "blockers": sorted(set(blockers)),
        "validation_error": validation_error,
        "lead_count": len(selected),
        "lead_ids": [str(item.get("lead_id") or "") for item in selected],
        "leads": smoke_entries,
        "candidate_pool": {
            "ready_for_outreach_operator_ready": len(candidates),
            "required_size": "5_to_10",
            "selected_without_mutation": len(selected),
        },
        "external_send_performed": False,
        "send_allowed": False,
        "counts_as_launch_batch": False,
        "real_launch_batch_created": False,
        "contacted_leads_marked": 0,
    }
    path = state_root / "rehearsals" / f"{run_id}-no-send-smoke-gate.json"
    write_json(path, report)
    report["report_path"] = str(path)
    return report


def validate_sample_exports(exports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    package_reports: dict[str, Any] = {}
    for package_key, export in exports.items():
        zip_path = Path(str(export.get("final_export_path") or ""))
        manifest_path = Path(str(export.get("manifest_path") or ""))
        manifest = read_json(manifest_path, default={})
        zip_validation = validate_zip_package(
            zip_path=zip_path,
            manifest=manifest if isinstance(manifest, dict) else {},
            package_key=package_key,
        )
        pdf_reports = [_pdf_download_report(path) for path in _zip_pdf_members(zip_path)]
        qr_report = {"ok": True, "checks": {}}
        if package_key == PACKAGE_3_KEY:
            qr_report = validate_qr_artifacts(
                url=str(export.get("live_url") or ""),
                qr_path=Path(str(export.get("qr_path") or "")),
                sign_path=Path(str(export.get("qr_sign_path") or "")),
            )
        package_reports[package_key] = {
            "ok": zip_validation["ok"] and all(item["ok"] for item in pdf_reports) and qr_report["ok"],
            "zip_path": str(zip_path),
            "manifest_path": str(manifest_path),
            "zip_validation": zip_validation,
            "pdf_validation": pdf_reports,
            "qr_validation": qr_report,
            "open_after_download_success": zip_validation["checks"]["file_opens_after_download"],
        }
    return {
        "ok": all(item["ok"] for item in package_reports.values()),
        "packages": package_reports,
    }


def capture_run8_screenshots(
    *,
    state_root: Path,
    docs_root: Path,
    run_id: str,
    artifacts: dict[str, Any],
) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    screenshot_dir = state_root / "qa-screenshots" / run_id
    ensure_dir(screenshot_dir)
    dashboard_port = _free_port()
    docs_port = _free_port()
    dashboard = _start_dashboard_server(state_root=state_root, port=dashboard_port)
    docs = _start_docs_server(docs_root=docs_root, port=docs_port)
    base_url = f"http://127.0.0.1:{dashboard_port}"
    site_url = f"http://127.0.0.1:{docs_port}"
    manifest: list[dict[str, Any]] = []
    console_errors: list[str] = []
    findings: list[str] = []
    try:
        _wait_for_url(f"{base_url}/api/leads")
        _wait_for_url(f"{site_url}/")
        preview_lead_id = _first_openable_lead_id(base_url)
        reply_id = str(artifacts.get("reply_id") or "")
        qr_export = artifacts["exports"][PACKAGE_3_KEY]
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for viewport_name, viewport in {
                "desktop": {"width": 1440, "height": 1100},
                "mobile": {"width": 390, "height": 844},
            }.items():
                page = browser.new_page(viewport=viewport, device_scale_factor=1)
                page.route("**/favicon.ico", lambda route: route.fulfill(status=204, body=""))
                page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
                page.on("pageerror", lambda exc: console_errors.append(str(exc)))
                _capture_dashboard_flow(
                    page=page,
                    base_url=base_url,
                    site_url=site_url,
                    screenshot_dir=screenshot_dir,
                    manifest=manifest,
                    findings=findings,
                    viewport_name=viewport_name,
                    preview_lead_id=preview_lead_id,
                    reply_id=reply_id,
                    artifacts=artifacts,
                    qr_export=qr_export,
                )
                page.close()
            browser.close()
    finally:
        _stop_process(dashboard)
        _stop_process(docs)

    expected = {f"{name}-{viewport}.png" for name in SCREEN_NAMES for viewport in ("desktop", "mobile")}
    actual = {Path(item["path"]).name for item in manifest}
    missing = sorted(expected - actual)
    findings.extend(f"missing_screenshot:{name}" for name in missing)
    return {
        "ok": not findings and not console_errors,
        "screenshot_dir": str(screenshot_dir),
        "screenshots": manifest,
        "console_errors": console_errors,
        "findings": sorted(set(findings)),
    }


def _capture_dashboard_flow(
    *,
    page: Any,
    base_url: str,
    site_url: str,
    screenshot_dir: Path,
    manifest: list[dict[str, Any]],
    findings: list[str],
    viewport_name: str,
    preview_lead_id: str,
    reply_id: str,
    artifacts: dict[str, Any],
    qr_export: dict[str, Any],
) -> None:
    page.goto(base_url, wait_until="networkidle")
    page.locator("#lead-list").wait_for(timeout=20000)
    _save_screen(page, screenshot_dir, manifest, findings, "dashboard-operator-queue", viewport_name, operator_screen=True)
    for mode, name in (
        ("review", "dashboard-review-lane"),
        ("ready", "dashboard-ready-lane"),
        ("skip", "dashboard-skipped-lane"),
        ("done", "dashboard-done-lane"),
    ):
        page.evaluate("mode => window.setLeadQueueMode(mode)", mode)
        page.locator("#lead-list").wait_for(timeout=10000)
        _save_screen(page, screenshot_dir, manifest, findings, name, viewport_name, operator_screen=True)

    if preview_lead_id:
        page.evaluate("leadId => window.openPreview(leadId)", preview_lead_id)
        page.locator("#preview-modal[open]").wait_for(timeout=20000)
        _save_screen(page, screenshot_dir, manifest, findings, "outreach-modal", viewport_name, operator_screen=True)
        page.evaluate("() => { const panel = document.getElementById('lead-dossier-panel'); if (panel) panel.open = true; }")
        _save_screen(page, screenshot_dir, manifest, findings, "lead-evidence-debug-drawer", viewport_name, operator_screen=True)
        page.keyboard.press("Escape")

    page.evaluate("() => window.switchTab('inbox')")
    page.locator("#inbox-list").wait_for(timeout=15000)
    _save_screen(page, screenshot_dir, manifest, findings, "reply-intake-lane", viewport_name, operator_screen=True)
    _save_screen(page, screenshot_dir, manifest, findings, "owner-asset-inbox", viewport_name, operator_screen=True)
    if reply_id:
        page.evaluate("replyId => window.openProductionWorkspace(replyId)", reply_id)
        page.locator("#production-workspace-modal[open]").wait_for(timeout=15000)
        for name in (
            "extraction-review-workspace",
            "ticket-machine-mapping-workspace",
            "build-studio",
            "owner-preview",
        ):
            _save_screen(page, screenshot_dir, manifest, findings, name, viewport_name, operator_screen=True)
        page.keyboard.press("Escape")

    page.evaluate("() => window.switchTab('builds')")
    page.locator("#build-list").wait_for(timeout=15000)
    _save_screen(page, screenshot_dir, manifest, findings, "build-studio", viewport_name, operator_screen=True)
    p1_job = artifacts["exports"][PACKAGE_1_KEY]["job_id"]
    page.evaluate("jobId => window.showBuildReview(jobId)", p1_job)
    page.locator("#build-review-modal[open]").wait_for(timeout=15000)
    _save_screen(page, screenshot_dir, manifest, findings, "owner-preview", viewport_name, operator_screen=True)

    for url, name in (
        (f"{site_url}/", "homepage"),
        (f"{site_url}/pricing.html", "pricing"),
        (f"{site_url}/samples/ramen.html", "sample-ramen-preview"),
        (f"{site_url}/samples/izakaya.html", "sample-izakaya-preview"),
        (f"{site_url}/menus/{qr_export['menu_id']}/", "qr-menu"),
        (f"{site_url}{qr_export['qr_sign_url']}", "qr-sign"),
    ):
        page.goto(url, wait_until="networkidle")
        _save_screen(page, screenshot_dir, manifest, findings, name, viewport_name, operator_screen=False)


def _save_screen(
    page: Any,
    screenshot_dir: Path,
    manifest: list[dict[str, Any]],
    findings: list[str],
    name: str,
    viewport_name: str,
    *,
    operator_screen: bool,
) -> None:
    path = screenshot_dir / f"{name}-{viewport_name}.png"
    page.screenshot(path=str(path), full_page=True)
    checks = _browser_checks(page, operator_screen=operator_screen)
    if not checks["ok"]:
        findings.extend(f"{name}:{issue}" for issue in checks["issues"])
    manifest.append({
        "screen": name,
        "viewport": viewport_name,
        "path": str(path),
        "checks": checks,
    })


def _browser_checks(page: Any, *, operator_screen: bool) -> dict[str, Any]:
    return page.evaluate(
        """operatorScreen => {
          const text = document.body ? document.body.innerText : "";
          const body = document.body;
          const issues = [];
          if (!body || body.scrollWidth > window.innerWidth + 3) issues.push("horizontal_overflow");
          const badButtons = [...document.querySelectorAll("button,a")].filter(el => {
            const imageAlt = [...el.querySelectorAll("img[alt]")]
              .map(img => img.getAttribute("alt") || "")
              .join(" ");
            const label = (
              el.getAttribute("aria-label") ||
              el.innerText ||
              el.textContent ||
              imageAlt ||
              el.getAttribute("title") ||
              ""
            ).trim();
            const rect = el.getBoundingClientRect();
            return rect.width > 8 && rect.height > 8 && !label;
          }).slice(0, 3);
          if (badButtons.length) issues.push("inaccessible_primary_controls");
          if (/\\[[^\\]\\n]{2,}\\]/.test(text)) issues.push("bracketed_fallback_text");
          if (/Lorem ipsum|TODO|TBD|Missing description|Missing ingredients|STATUS:\\s*SAMPLE/i.test(text)) issues.push("stale_placeholder_text");
          if (!operatorScreen && /\\b(ai|automation|scraping|pipeline)\\b/i.test(text)) issues.push("forbidden_customer_language");
          const imgs = [...document.images].filter(img => img.complete && img.naturalWidth === 0);
          if (imgs.length) issues.push("broken_image");
          return { ok: issues.length === 0, issues };
        }""",
        operator_screen,
    )


def _ensure_workspace_reply(*, state_root: Path, run_id: str) -> dict[str, Any]:
    reply_id = f"reply-{run_id}-workspace-reply"
    source_image = PROJECT_ROOT / "docs" / "assets" / "previews" / "ramen-ticket-machine.png"
    if not source_image.exists():
        source_image = PROJECT_ROOT / "docs" / "assets" / "previews" / "simple-ramen-menu.png"
    reply = {
        "reply_id": reply_id,
        "lead_id": "",
        "business_name": "Run8 QR",
        "channel": "email",
        "from": "owner@example.invalid",
        "subject": "Menu photos and ticket machine",
        "body": "Please use these current menu and ticket machine photos for the English ordering files and QR English menu.",
        "received_at": utc_now(),
        "workflow_status": "ready_to_build",
        "reply_intent": "ticket_machine_photos_sent",
        "stored_photo_count": 1,
        "photo_count": 1,
        "attachments": [{
            "filename": "run8-ticket-machine-menu.png",
            "stored_path": str(source_image),
            "content_type": "image/png",
        }],
        "run8_rehearsal": True,
    }
    manifest = ingest_owner_assets(reply, state_root=state_root)
    reply["owner_assets"] = {
        "manifest_path": str(state_root / "owner-assets" / reply_id / "manifest.json"),
        "assets": manifest.get("assets") or [],
    }
    write_json(state_root / "replies" / f"{reply_id}.json", reply)
    return reply


def _build_and_approve_package(
    *,
    state_root: Path,
    job_id: str,
    package_key: str,
    item_count: int,
    include_ticket: bool,
    delivery_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output_dir = state_root / "builds" / job_id
    menu_data = _sample_menu_data(item_count=item_count)
    ticket_data = _sample_ticket_data() if include_ticket else None
    asyncio.run(build_custom_package(
        output_dir=output_dir,
        menu_data=menu_data,
        ticket_data=ticket_data,
        restaurant_name="Run 8 Hinode Ramen",
    ))
    order_id = f"ord-{job_id}"
    _write_paid_order(
        state_root=state_root,
        order_id=order_id,
        package_key=package_key,
        output_dir=output_dir,
    )
    write_json(state_root / "jobs" / f"{job_id}.json", {
        "job_id": job_id,
        "restaurant_name": "Run 8 Hinode Ramen",
        "status": "ready_for_review",
        "package_key": package_key,
        "output_dir": str(output_dir),
        "order_id": order_id,
        "run8_rehearsal": True,
        "created_at": utc_now(),
    })
    result = approve_package_export(
        state_root=state_root,
        job_id=job_id,
        package_key=package_key,
        reviewer="run8-verifier",
        delivery_details=delivery_details,
    )
    manifest_path = state_root / "final_exports" / job_id / "PACKAGE_MANIFEST.json"
    return {
        "job_id": job_id,
        "package_key": package_key,
        "final_export_path": result["final_export_path"],
        "manifest_path": str(manifest_path),
        "export_qa_report_path": result["export_qa"]["report_path"],
        "download_url": result["download_url"],
    }


def _build_and_approve_qr_package(
    *,
    state_root: Path,
    docs_root: Path,
    reply: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    payload = {
        "restaurant_name": "Run 8 Izakaya QR",
        "items": _sample_qr_items(),
        "content_requirements": {
            "descriptions_required": True,
            "ingredient_allergen_required": True,
        },
    }
    job = create_qr_draft(reply=reply, state_root=state_root, docs_root=docs_root, payload=payload)
    create_qr_sign(state_root=state_root, docs_root=docs_root, job_id=job["job_id"])
    approved = approve_qr_package(
        state_root=state_root,
        docs_root=docs_root,
        job_id=job["job_id"],
        reviewer="run8-verifier",
    )
    version = str(approved.get("published_version_id") or "")
    menu_id = str(approved.get("menu_id") or "")
    return {
        "job_id": approved["job_id"],
        "menu_id": menu_id,
        "package_key": PACKAGE_3_KEY,
        "final_export_path": approved["final_export_path"],
        "manifest_path": str(state_root / "final_exports" / approved["job_id"] / "PACKAGE_MANIFEST.json"),
        "export_qa_report_path": approved["export_qa"]["report_path"],
        "download_url": approved["download_url"],
        "live_url": approved.get("live_url", ""),
        "qr_path": str(docs_root / "menus" / menu_id / "versions" / version / "qr.svg"),
        "qr_sign_path": str(docs_root / "menus" / menu_id / "versions" / version / "qr_sign.html"),
        "qr_sign_url": str(approved.get("qr_sign_url") or f"/menus/{menu_id}/versions/{version}/qr_sign.html"),
    }


def _sample_menu_data(*, item_count: int) -> dict[str, Any]:
    food_count = max(8, min(item_count - 8, 34))
    drink_count = max(0, item_count - food_count)
    first_food_count = min(food_count, 18)
    second_food_count = max(0, food_count - first_food_count)
    food_sections = [{
        "title": "RAMEN",
        "section": "ramen",
        "data_section": "ramen",
        "item_type": "food",
        "items": [_menu_item(index, section="ramen", prefix="Ramen") for index in range(1, first_food_count + 1)],
    }]
    if second_food_count:
        food_sections.append({
            "title": "SIDES / ADD-ONS",
            "section": "sides",
            "data_section": "sides-add-ons",
            "item_type": "food",
            "items": [_menu_item(index, section="sides", prefix="Side") for index in range(1, second_food_count + 1)],
        })
    drinks_sections = [
        {
            "title": "DRINKS",
            "section": "drinks",
            "data_section": "beer-highballs",
            "item_type": "drink",
            "items": [_menu_item(index, section="drinks", prefix="Drink") for index in range(1, drink_count + 1)],
        }
    ] if drink_count else []
    sections = [*food_sections, *drinks_sections]
    return build_menu_data(
        menu_type="ramen",
        title="RUN 8 HINODE RAMEN MENU",
        sections=sections,
        food_sections=food_sections,
        drinks_sections=drinks_sections,
        show_prices=False,
        footer_note="",
    )


def _menu_item(index: int, *, section: str, prefix: str) -> dict[str, Any]:
    return {
        "name": f"{prefix} {index}",
        "english_name": f"{prefix} {index}",
        "japanese_name": f"{prefix} {index}",
        "source_text": f"{prefix} {index}",
        "section": section,
        "price": f"JPY {800 + index * 10}",
        "price_status": "confirmed_by_business",
        "price_visibility": "intentionally_hidden",
        "source_provenance": "run8_owner_material",
        "approval_status": "owner_approved",
    }


def _sample_ticket_data() -> dict[str, Any]:
    return build_ticket_data(
        title="TICKET MACHINE GUIDE",
        steps=["Insert money", "Choose a ramen button", "Take the ticket", "Give the ticket to staff"],
        rows=[
            {"category": "ramen", "buttons": ["Ramen 1", "Ramen 2", "Ramen 3"]},
            {"category": "sides", "buttons": ["Gyoza", "Rice", "Extra Noodles"]},
        ],
        footer_note="",
    )


def _sample_qr_items() -> list[dict[str, Any]]:
    confirmed = {
        "status": "confirmed_by_owner",
        "source": "run8_owner_material",
        "confirmed_by": "Run 8 Operator",
        "confirmed_at": utc_now(),
        "notes": "",
    }
    return [
        {
            "name": "Grilled Skewers",
            "japanese_name": "Yakitori Set",
            "price": "JPY 1200",
            "description": "Assorted grilled chicken skewers with tare sauce.",
            "ingredients": ["chicken", "soy"],
            "allergens": ["soy"],
            "section": "Skewers",
            "source_text": "Yakitori Set",
            "source_provenance": "run8_owner_material",
            "approval_status": "owner_approved",
            "description_confirmation": confirmed,
            "ingredient_allergen_confirmation": confirmed,
        },
        {
            "name": "Nomihodai Course",
            "japanese_name": "Nomihodai Course",
            "price": "JPY 3500",
            "description": "Two-hour drink course with last order thirty minutes before closing.",
            "ingredients": ["alcohol"],
            "allergens": [],
            "section": "Courses",
            "source_text": "Nomihodai Course",
            "source_provenance": "run8_owner_material",
            "approval_status": "owner_approved",
            "description_confirmation": confirmed,
            "ingredient_allergen_confirmation": confirmed,
        },
    ]


def _write_paid_order(*, state_root: Path, order_id: str, package_key: str, output_dir: Path) -> None:
    checksum = _dir_checksum(output_dir)
    price = {PACKAGE_1_KEY: 30000, PACKAGE_2_KEY: 45000, PACKAGE_3_KEY: 65000}.get(package_key, 0)
    write_json(state_root / "orders" / f"{order_id}.json", {
        "order_id": order_id,
        "state": "owner_approved",
        "package_key": package_key,
        "business_name": "Run 8 Hinode Ramen",
        "quote": {
            "package_key": package_key,
            "package_label": package_key,
            "price_yen": price,
            "quote_date": "2026-05-04",
        },
        "payment": {
            "status": "confirmed",
            "amount_yen": price,
            "confirmed_at": utc_now(),
            "reference": order_id,
        },
        "intake": {
            "is_complete": True,
            "full_menu_photos": True,
            "price_confirmation": True,
            "delivery_details": True,
            "business_contact_confirmed": True,
        },
        "approval": {
            "approved": True,
            "approver_name": "Run 8 Operator",
            "approved_package": package_key,
            "source_data_checksum": checksum,
            "artifact_checksum": checksum,
            "approved_at": utc_now(),
        },
        "privacy_note_accepted": True,
        "run8_rehearsal": True,
    })


def _launch_ready_candidates(state_root: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for path in sorted((state_root / "leads").glob("*.json")):
        record = read_json(path, default={})
        if not isinstance(record, dict):
            continue
        primary = get_primary_contact(record) or {}
        if (
            record.get("lead") is True
            and record.get("operator_state") == OPERATOR_READY
            and record.get("launch_readiness_status") == "ready_for_outreach"
            and str(primary.get("type") or "") in {"email", "contact_form"}
        ):
            candidates.append(record)
    return candidates


def _select_smoke_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for predicate in (
        lambda item: item.get("establishment_profile") == "ramen_ticket_machine",
        lambda item: item.get("establishment_profile") in {"izakaya_drink_heavy", "izakaya_course_heavy"},
        lambda item: True,
    ):
        for item in candidates:
            if len(selected) >= 10:
                return selected
            if item in selected or not predicate(item):
                continue
            selected.append(item)
            if len(selected) >= 5 and any(x.get("establishment_profile") == "ramen_ticket_machine" for x in selected) and any(
                x.get("establishment_profile") in {"izakaya_drink_heavy", "izakaya_course_heavy"} for x in selected
            ):
                return selected
    return selected


def _zip_pdf_members(zip_path: Path) -> list[Path]:
    if not zip_path.exists():
        return []
    output_dir = zip_path.parent / "_download_check" / zip_path.stem
    ensure_dir(output_dir)
    pdfs: list[Path] = []
    with zipfile.ZipFile(zip_path) as archive:
        for name in archive.namelist():
            if not name.lower().endswith(".pdf"):
                continue
            target = output_dir / Path(name).name
            target.write_bytes(archive.read(name))
            pdfs.append(target)
    return pdfs


def _pdf_download_report(path: Path) -> dict[str, Any]:
    media_box = _pdf_media_box(path)
    orientation = ""
    if media_box:
        orientation = "landscape" if media_box["width_pt"] > media_box["height_pt"] else "portrait"
    return {
        "path": str(path),
        "ok": path.exists() and path.read_bytes()[:4] == b"%PDF" and bool(media_box),
        "file_opens": path.exists() and path.read_bytes()[:4] == b"%PDF",
        "media_box": media_box,
        "orientation": orientation,
        "embedded_or_usable_fonts": b"/Font" in path.read_bytes() if path.exists() else False,
    }


def _pdf_media_box(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    import re

    data = path.read_bytes()
    match = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([0-9.]+)\s+([0-9.]+)\s*\]", data)
    if not match:
        return {}
    width_pt = float(match.group(1))
    height_pt = float(match.group(2))
    return {
        "width_pt": width_pt,
        "height_pt": height_pt,
        "width_mm": round(width_pt * 25.4 / 72, 2),
        "height_mm": round(height_pt * 25.4 / 72, 2),
    }


def _dir_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(path.glob("*")):
        if file_path.is_file():
            digest.update(file_path.name.encode("utf-8"))
            digest.update(sha256_file(file_path).encode("ascii"))
    return digest.hexdigest()


def _first_openable_lead_id(base_url: str) -> str:
    data = httpx.get(f"{base_url}/api/leads", timeout=10).json()
    for lead in data.get("leads") or []:
        if lead.get("pitch_card_openable") and str(lead.get("primary_contact_type") or "") in {"email", "contact_form"}:
            return str(lead.get("lead_id") or "")
    return ""


def _start_dashboard_server(*, state_root: Path, port: int) -> subprocess.Popen:
    env = dict(os.environ)
    env["WEBREFURB_STATE_ROOT"] = str(state_root.resolve())
    env["RESEND_API_KEY"] = ""
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "dashboard.app:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _start_docs_server(*, docs_root: Path, port: int) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(docs_root)],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_for_url(url: str) -> None:
    deadline = time.time() + 30
    last_error = ""
    while time.time() < deadline:
        try:
            response = httpx.get(url, timeout=2)
            if response.status_code < 500:
                return
            last_error = f"status {response.status_code}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"server did not become ready at {url}: {last_error}")


def _stop_process(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_id() -> str:
    return "run8-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
