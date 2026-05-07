"""Final export and operator review gates for English QR Menu artifacts."""

from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from .constants import (
    ENGLISH_QR_MENU_KEY,
    PACKAGE_REGISTRY,
)
from .export import is_valid_pdf
from .final_export_qa import artifact_entry, package_manifest, sha256_file, write_export_qa_report
from .utils import ensure_dir, write_json, write_text


REVIEW_STATUS_PENDING = "pending_review"
REVIEW_STATUS_APPROVED = "approved"
FINAL_EXPORT_READY = "ready"

QR_MENU_FILES = (
    "index.html",
    "menu.json",
    "qr.svg",
)

QR_MENU_OPTIONAL_FILES = (
    "qr_sign.html",
    "qr_sign.svg",
    "qr_sign_print_ready.pdf",
    "source.json",
    "CONFIRMATION_SUMMARY.json",
)

PREVIEW_FILES = ("index.html",)

INTERNAL_MARKERS = (
    "watermark-overlay",
    "WRM_REVIEW_ONLY",
    "Draft menu pending review",
    "data-review-gap",
)

ALLOWED_PRICE_STATUSES = {
    "unknown",
    "detected_in_source",
    "pending_business_confirmation",
    "confirmed_by_business",
}

ALLOWED_PRICE_VISIBILITY = {
    "not_applicable",
    "pending_business_confirmation",
    "customer_visible",
    "intentionally_hidden",
}


class PackageExportError(ValueError):
    """Raised when a package cannot pass the review/export gate."""


def package_registry() -> list[dict[str, Any]]:
    """Return public package metadata in offer order."""
    return [PACKAGE_REGISTRY[ENGLISH_QR_MENU_KEY]]


def get_build_history(*, state_root: Path) -> dict[str, Any]:
    """Return custom build jobs for the operator dashboard."""
    jobs: list[dict[str, Any]] = []
    for path in sorted((state_root / "jobs").glob("*.json"), reverse=True):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        package_key = _normalise_build_package(job.get("package_key"))
        package = PACKAGE_REGISTRY[package_key]
        output_dir_value = str(job.get("output_dir") or "").strip()
        if output_dir_value:
            output_dir = Path(output_dir_value)
            validation = validate_package_output(
                output_dir=output_dir,
                package_key=package_key,
                delivery_details=None,
            )
        else:
            validation = _validation_result(errors=["output_dir_missing"], warnings=[])
        jobs.append({
            "job_id": job.get("job_id", path.stem),
            "restaurant_name": job.get("restaurant_name", ""),
            "package_key": package_key,
            "package_label": package["label"],
            "price_yen": package["price_yen"],
            "status": job.get("status", ""),
            "review_status": job.get("review_status", REVIEW_STATUS_PENDING),
            "final_export_status": job.get("final_export_status", ""),
            "created_at": job.get("created_at", ""),
            "completed_at": job.get("completed_at", ""),
            "validation": validation,
            "paid_operations": package_paid_operations_status(state_root=state_root, job=job),
            "download_url": f"/api/build/{job.get('job_id', path.stem)}/download" if job.get("final_export_path") else "",
        })
    return {"builds": jobs}


def get_package_review(*, state_root: Path, job_id: str) -> dict[str, Any]:
    """Return review metadata and validation for a custom build job."""
    job = _load_job(state_root=state_root, job_id=job_id)
    package_key = _normalise_build_package(job.get("package_key"))
    output_dir = Path(str(job.get("output_dir") or ""))
    validation = validate_package_output(
        output_dir=output_dir,
        package_key=package_key,
        delivery_details=None,
    )
    package = PACKAGE_REGISTRY[package_key]
    menu_data = _load_menu_data(output_dir, [])
    review_checklist = _derive_review_checklist(menu_data or {}, validation=validation)
    paid_operations = package_paid_operations_status(state_root=state_root, job=job)
    return {
        "job_id": job_id,
        "package_key": package_key,
        "package_label": package["label"],
        "price_yen": package["price_yen"],
        "status": job.get("status", ""),
        "review_status": job.get("review_status", REVIEW_STATUS_PENDING),
        "final_export_status": job.get("final_export_status", ""),
        "restaurant_name": job.get("restaurant_name", ""),
        "output_dir": str(output_dir) if output_dir else "",
        "preview_url": f"/api/build/{job_id}/preview",
        "download_url": f"/api/build/{job_id}/download" if job.get("final_export_path") else "",
        "final_export_path": job.get("final_export_path", ""),
        "validation": validation,
        "paid_operations": paid_operations,
        "print_profile": validation.get("print_profile"),
        "review_checklist": review_checklist,
        "artifacts": _artifact_report(output_dir, package_key=package_key),
    }


def validate_package_output(
    *,
    output_dir: Path,
    package_key: str = ENGLISH_QR_MENU_KEY,
    delivery_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate that a package is safe to approve."""
    package_key = _normalise_build_package(package_key)
    errors: list[str] = []
    warnings: list[str] = []

    if not output_dir or not output_dir.exists():
        return _validation_result(errors=["output_dir_missing"], warnings=warnings)

    _validate_qr_assets(output_dir, errors)
    menu_data = _load_menu_data(output_dir, errors)
    if menu_data:
        _validate_menu_schema(menu_data, errors)
        _validate_rendered_outputs(output_dir=output_dir, menu_data=menu_data, errors=errors)

    result: dict[str, Any] = {}

    return _validation_result(errors=errors, warnings=warnings, **result)


def validate_package1_output(*, output_dir: Path) -> dict[str, Any]:
    """Backward-compatible validator wrapper for legacy callers."""
    return validate_package_output(output_dir=output_dir, package_key=ENGLISH_QR_MENU_KEY)


def select_print_profile(menu_data: dict[str, Any] | None) -> dict[str, Any]:
    """Return the optional printable QR sign profile for legacy callers."""
    item_count = _menu_item_count(menu_data or {})
    return {
        "paper_size": "A4",
        "orientation": "portrait",
        "duplex": False,
        "copy_count": 1,
        "physical_scope": "printable QR sign",
        "item_count": item_count,
        "reason": "english_qr_menu_printable_sign",
        "custom_quote_required": False,
    }


def approve_package_export(
    *,
    state_root: Path,
    job_id: str,
    package_key: str | None = None,
    reviewer: str = "operator",
    delivery_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Approve a reviewed build and create the final ZIP for its package."""
    job = _load_job(state_root=state_root, job_id=job_id)
    selected_key = _normalise_build_package(package_key or job.get("package_key"))
    output_dir = Path(str(job.get("output_dir") or ""))
    validation = validate_package_output(
        output_dir=output_dir,
        package_key=selected_key,
        delivery_details=None,
    )
    if not validation["ok"]:
        package_name = PACKAGE_REGISTRY[selected_key]["label"]
        raise PackageExportError(f"{package_name} review blocked: " + ", ".join(validation["errors"]))
    paid_operations = package_paid_operations_status(state_root=state_root, job=job)
    if not paid_operations["ok"]:
        raise PackageExportError("Paid operations blocked: " + ", ".join(paid_operations["blockers"]))

    export_dir = state_root / "final_exports" / job_id
    ensure_dir(export_dir)
    package = PACKAGE_REGISTRY[selected_key]
    generated_files: list[Path] = []
    generated_files.extend(_write_owner_content_pack(output_dir=output_dir, export_dir=export_dir, job=job))
    now = datetime.now(timezone.utc).isoformat()
    manifest = _final_manifest(
        job=job,
        output_dir=output_dir,
        package_key=selected_key,
        validation=validation,
        generated_files=generated_files,
        approval_timestamp=now,
    )
    manifest_path = export_dir / "PACKAGE_MANIFEST.json"
    write_json(manifest_path, manifest)

    zip_path = export_dir / f"{job_id}-{selected_key}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in _package_files(output_dir, package_key=selected_key):
            archive.write(output_dir / name, arcname=name)
        for path in generated_files:
            archive.write(path, arcname=path.name)
        archive.write(manifest_path, arcname="PACKAGE_MANIFEST.json")

    pdf_paths = [output_dir / name for name in _package_files(output_dir, package_key=selected_key) if name.endswith(".pdf")]
    pdf_paths.extend(path for path in generated_files if path.suffix.lower() == ".pdf")
    html_paths = [output_dir / name for name in _package_files(output_dir, package_key=selected_key) if name.endswith(".html")]
    default_pdf_profile = {"paper_size": "A4", "orientation": "portrait"}
    pdf_print_profiles: dict[str, dict[str, Any]] = {str(path): default_pdf_profile for path in pdf_paths}
    export_qa = write_export_qa_report(
        state_root=state_root,
        job_id=job_id,
        package_key=selected_key,
        zip_path=zip_path,
        manifest=manifest,
        pdf_paths=pdf_paths,
        html_paths=html_paths,
        print_profile=default_pdf_profile,
        pdf_print_profiles=pdf_print_profiles,
    )
    if not export_qa["ok"]:
        raise PackageExportError("Export QA blocked: " + ", ".join(_export_qa_errors(export_qa)))

    job["status"] = "completed"
    job["package_key"] = selected_key
    job["review_status"] = REVIEW_STATUS_APPROVED
    job["reviewed_by"] = reviewer
    job["reviewed_at"] = now
    job["final_export_status"] = FINAL_EXPORT_READY
    job["final_export_path"] = str(zip_path)
    job["final_export_created_at"] = now
    job["export_qa_status"] = "passed"
    job["export_qa_report_path"] = export_qa["report_path"]
    job["package_validation"] = validation
    job["paid_operations"] = paid_operations
    _append_history(job, f"{selected_key}_approved", now, reviewer)
    _write_job(state_root=state_root, job=job)

    return {
        "job_id": job_id,
        "status": job["status"],
        "package_key": selected_key,
        "package_label": package["label"],
        "price_yen": package["price_yen"],
        "review_status": job["review_status"],
        "final_export_status": job["final_export_status"],
        "final_export_path": str(zip_path),
        "download_url": f"/api/build/{job_id}/download",
        "validation": validation,
        "paid_operations": paid_operations,
        "export_qa": export_qa,
    }


def _export_qa_errors(export_qa: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(export_qa.get("zip_validation", {}).get("errors") or [])
    for report in export_qa.get("pdf_validation") or []:
        if report.get("ok"):
            continue
        failed = [
            key for key, passed in (report.get("checks") or {}).items()
            if passed is False
        ]
        errors.append(f"pdf_failed:{Path(str(report.get('path') or '')).name}:{'|'.join(failed) or 'unknown'}")
    for report in export_qa.get("raster_validation") or []:
        if report.get("ok"):
            continue
        failed = [
            key for key, passed in (report.get("checks") or {}).items()
            if passed is False
        ]
        errors.append(f"raster_failed:{Path(str(report.get('path') or '')).name}:{'|'.join(failed) or 'unknown'}")
    qr_report = export_qa.get("qr_validation") or {}
    if qr_report and not qr_report.get("ok", True):
        failed = [
            key for key, passed in (qr_report.get("checks") or {}).items()
            if passed is False
        ]
        errors.append(f"qr_failed:{'|'.join(failed) or 'unknown'}")
    visual_report = export_qa.get("visual_validation") or {}
    for report in visual_report.get("artifacts") or []:
        if report.get("ok"):
            continue
        errors.extend(report.get("errors") or [f"visual_failed:{Path(str(report.get('path') or '')).name}"])
    return errors or ["unknown_export_qa_failure"]


def package_paid_operations_status(*, state_root: Path, job: dict[str, Any]) -> dict[str, Any]:
    """Return paid-ops readiness for a package build.

    Final package export is customer-facing. It must not be approved until the
    paid workflow has a quote, confirmed payment, complete intake, and explicit
    owner approval for the output.
    """
    order_id = str(job.get("order_id") or "").strip()
    order = job.get("order") if isinstance(job.get("order"), dict) else None
    if order is None and order_id:
        order_path = state_root / "orders" / f"{order_id}.json"
        if order_path.exists():
            try:
                order = json.loads(order_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                order = None

    blockers: list[str] = []
    if not order:
        blockers.append("paid_order_missing")
        return {"ok": False, "order_id": order_id, "blockers": blockers}

    quote = order.get("quote") or {}
    payment = order.get("payment") or {}
    intake = order.get("intake") or {}
    approval = order.get("approval") or {}
    state = str(order.get("state") or "").strip()

    if not quote or not str(quote.get("quote_date") or "").strip():
        blockers.append("quote_not_recorded")
    if str(payment.get("status") or "").strip() != "confirmed":
        blockers.append("payment_not_confirmed")
    intake_complete = bool(intake.get("is_complete")) or all(
        bool(intake.get(key))
        for key in (
            "full_menu_photos",
            "price_confirmation",
            "qr_sign_confirmation",
            "business_contact_confirmed",
        )
    )
    if not intake_complete:
        blockers.append("owner_intake_incomplete")
    if not bool(approval.get("approved")):
        blockers.append("owner_output_not_approved")
    if not str(approval.get("approver_name") or "").strip():
        blockers.append("owner_approver_name_missing")
    if not str(approval.get("approved_package") or "").strip():
        blockers.append("owner_approved_package_missing")
    if not str(approval.get("source_data_checksum") or "").strip():
        blockers.append("owner_source_checksum_missing")
    if not str(approval.get("artifact_checksum") or "").strip():
        blockers.append("owner_artifact_checksum_missing")
    if not bool(order.get("privacy_note_accepted")):
        blockers.append("privacy_note_not_accepted")
    if state and state not in {"owner_review", "owner_approved"}:
        blockers.append(f"order_state_not_owner_review:{state}")

    return {
        "ok": not blockers,
        "order_id": str(order.get("order_id") or order_id),
        "blockers": blockers,
        "payment_status": str(payment.get("status") or ""),
        "intake_complete": intake_complete,
        "owner_approved": bool(approval.get("approved")),
        "order_state": state,
    }


def approve_package1_export(*, state_root: Path, job_id: str, reviewer: str = "operator") -> dict[str, Any]:
    """Backward-compatible approval wrapper for legacy callers."""
    return approve_package_export(
        state_root=state_root,
        job_id=job_id,
        package_key=ENGLISH_QR_MENU_KEY,
        reviewer=reviewer,
    )


def _validate_qr_assets(output_dir: Path, errors: list[str]) -> None:
    for name in QR_MENU_FILES:
        path = output_dir / name
        if not path.exists():
            errors.append(f"{name}_missing")
            continue
        if path.stat().st_size == 0:
            errors.append(f"{name}_empty")
    sign_pdf = output_dir / "qr_sign_print_ready.pdf"
    if sign_pdf.exists() and not is_valid_pdf(sign_pdf):
        errors.append("qr_sign_print_ready.pdf_not_pdf")


def _validate_preview_assets(output_dir: Path, errors: list[str]) -> None:
    preview_found = False
    for name in PREVIEW_FILES:
        path = output_dir / name
        if path.exists():
            preview_found = True
            _check_html_markers(path, errors)
    if not preview_found:
        errors.append("preview_html_missing")


def _load_menu_data(output_dir: Path, errors: list[str]) -> dict[str, Any] | None:
    menu_json = output_dir / "menu.json"
    if not menu_json.exists():
        return None
    try:
        data = json.loads(menu_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        errors.append("menu_json_invalid")
        return None
    items = data.get("items") or []
    if not items:
        errors.append("menu_items_missing")
    if data.get("approval_blockers"):
        errors.append("approval_blockers_present")
    return data


def _validate_menu_schema(menu_data: dict[str, Any], errors: list[str]) -> None:
    if isinstance(menu_data.get("items"), list):
        for index, item in enumerate(menu_data.get("items") or []):
            if not isinstance(item, dict):
                errors.append(f"item_{index}_invalid")
                return
            if not str(item.get("japanese_name") or "").strip():
                errors.append(f"item_{index}_japanese_name_missing")
            if not str(item.get("english_name") or "").strip():
                errors.append(f"item_{index}_english_name_missing")
        return
    for panel_key in ("food", "drinks"):
        panel = menu_data.get(panel_key) or {}
        for section in panel.get("sections") or []:
            if not str(section.get("title") or "").strip():
                errors.append(f"{panel_key}_section_title_missing")
            for item in section.get("items") or []:
                if not isinstance(item, dict):
                    errors.append(f"{panel_key}_item_invalid")
                    return
                required = (
                    item.get("japanese_name") or item.get("source_text"),
                    item.get("english_name") or item.get("name"),
                    item.get("section"),
                    item.get("price_status"),
                    item.get("source_provenance"),
                    item.get("approval_status"),
                )
                if not all(str(value or "").strip() for value in required):
                    errors.append(f"{panel_key}_item_schema_incomplete")
                    return
                # Block bracket fallback translations from reaching export
                english_name = str(item.get("english_name") or item.get("name") or "").strip()
                if english_name.startswith("[") and english_name.endswith("]"):
                    errors.append(
                        f"{panel_key}_unresolved_translation:{english_name}"
                    )
                price_status = str(item.get("price_status") or "").strip()
                price_visibility = str(item.get("price_visibility") or "").strip()
                if price_status not in ALLOWED_PRICE_STATUSES:
                    errors.append(f"{panel_key}_price_status_invalid:{price_status or 'missing'}")
                if price_visibility and price_visibility not in ALLOWED_PRICE_VISIBILITY:
                    errors.append(f"{panel_key}_price_visibility_invalid:{price_visibility}")
                if price_status == "confirmed_by_business" and price_visibility == "pending_business_confirmation":
                    errors.append(f"{panel_key}_price_visibility_conflicts_with_confirmation")


def _validate_rendered_outputs(*, output_dir: Path, menu_data: dict[str, Any], errors: list[str]) -> None:
    if isinstance(menu_data.get("items"), list):
        return
    show_prices = bool(menu_data.get("show_prices"))
    for panel_key, file_name in (("food", "food_menu.html"), ("drinks", "drinks_menu.html")):
        html_path = output_dir / file_name
        if not html_path.exists():
            continue
        expected_panel = menu_data.get(panel_key) or {}
        opposite_panel = menu_data.get("drinks" if panel_key == "food" else "food") or {}
        expected_items = [item for section in expected_panel.get("sections") or [] for item in section.get("items") or []]
        opposite_names = {
            str(item.get("english_name") or item.get("name") or "").strip()
            for section in opposite_panel.get("sections") or []
            for item in section.get("items") or []
            if str(item.get("english_name") or item.get("name") or "").strip()
        }
        rendered = _html_text_report(html_path)
        expected_english = {_customer_visible_english(item, show_prices=show_prices) for item in expected_items}
        expected_japanese = {
            str(item.get("japanese_name") or item.get("source_text") or "").strip()
            for item in expected_items
            if str(item.get("japanese_name") or item.get("source_text") or "").strip()
        }
        expected_sections = _expected_rendered_section_titles(expected_panel)
        for item in expected_items:
            english = _customer_visible_english(item, show_prices=show_prices)
            japanese = str(item.get("japanese_name") or item.get("source_text") or "").strip()
            price = str(item.get("price") or "").strip()
            if english and english not in rendered["item_en"]:
                errors.append(f"{panel_key}_output_missing_item:{english}")
            if japanese and japanese not in rendered["item_jp"]:
                errors.append(f"{panel_key}_output_missing_source_text:{japanese}")
            if _item_price_should_render(item, show_prices=show_prices) and price and not any(price in line for line in rendered["item_en"]):
                errors.append(f"{panel_key}_price_missing:{price}")
            if price and not _item_price_should_render(item, show_prices=show_prices):
                if any(price in line for line in rendered["item_en"]):
                    errors.append(f"{panel_key}_unconfirmed_price_visible:{price}")
        for title in expected_sections:
            if title not in rendered["all"]:
                errors.append(f"{panel_key}_section_title_missing_in_output:{title}")

        if show_prices and not any(_item_price_should_render(item, show_prices=show_prices) for item in expected_items):
            errors.append(f"{panel_key}_show_prices_without_confirmed_prices")

        stale = [
            text for text in rendered["all"]
            if text in TEMPLATE_PLACEHOLDER_ITEMS and text not in expected_english
            and text not in expected_japanese
            and text not in expected_sections
        ]
        if stale:
            errors.append(f"{panel_key}_stale_template_text_present")

        if any("[" in text and "]" in text for text in rendered["item_en"]):
            errors.append(f"{panel_key}_placeholder_translation_present")
        if any(name and any(name in line for line in rendered["item_en"]) for name in opposite_names):
            errors.append(f"{panel_key}_wrong_section_bleed")

    _validate_preview_html_links(output_dir=output_dir, menu_data=menu_data, errors=errors)


def _validate_preview_html_links(*, output_dir: Path, menu_data: dict[str, Any], errors: list[str]) -> None:
    # v4c HTML templates are self-contained — no external image references to validate
    pass


def _write_owner_content_pack(*, output_dir: Path, export_dir: Path, job: dict[str, Any]) -> list[Path]:
    menu_data_path = output_dir / "menu.json"
    menu_data: dict[str, Any] = {}
    if menu_data_path.exists():
        try:
            menu_data = json.loads(menu_data_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            menu_data = {}
    content_path = export_dir / "CONFIRMATION_SUMMARY.json"
    write_json(content_path, {
        "job_id": job.get("job_id", ""),
        "restaurant_name": job.get("restaurant_name", ""),
        "owner_approved": True,
        "source_output_dir": str(output_dir),
        "menu_json_checksum": sha256_file(menu_data_path) if menu_data_path.exists() else "",
        "item_count": len(menu_data.get("items") or []),
        "confirmation_policy": "prices_descriptions_ingredients_allergens_owner_confirmed_before_publish",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return [content_path]


def _package_files(output_dir: Path, *, package_key: str) -> list[str]:
    files = [name for name in QR_MENU_FILES if (output_dir / name).exists()]
    for name in QR_MENU_OPTIONAL_FILES:
        if (output_dir / name).exists():
            files.append(name)
    return files


def _load_job(*, state_root: Path, job_id: str) -> dict[str, Any]:
    path = state_root / "jobs" / f"{job_id}.json"
    if not path.exists():
        raise PackageExportError("Build job not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_job(*, state_root: Path, job: dict[str, Any]) -> None:
    write_json(state_root / "jobs" / f"{job['job_id']}.json", job)


def _artifact_report(output_dir: Path, *, package_key: str) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    if not output_dir or not output_dir.exists():
        return artifacts
    names = list(QR_MENU_FILES) + list(QR_MENU_OPTIONAL_FILES)
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        path = output_dir / name
        required = name in QR_MENU_FILES
        artifacts.append({
            "name": name,
            "exists": path.exists(),
            "bytes": path.stat().st_size if path.exists() else 0,
            "required": required,
        })
    return artifacts


def _check_html_markers(path: Path, errors: list[str]) -> None:
    content = path.read_text(encoding="utf-8", errors="ignore")
    for marker in INTERNAL_MARKERS:
        if marker in content:
            errors.append(f"internal_marker_present:{marker}")


def _svg_text_report(path: Path) -> dict[str, list[str]]:
    root = ET.parse(str(path)).getroot()
    svg_text = "{http://www.w3.org/2000/svg}text"
    item_en: list[str] = []
    item_jp: list[str] = []
    all_text: list[str] = []
    for elem in root.iter(svg_text):
        text = " ".join(part.strip() for part in elem.itertext()).strip()
        if not text:
            continue
        all_text.append(text)
        classes = elem.get("class", "").split()
        if "item-en" in classes:
            item_en.append(text)
        elif "item-jp" in classes:
            item_jp.append(text)
    return {"all": all_text, "item_en": item_en, "item_jp": item_jp}


def _html_text_report(path: Path) -> dict[str, list[str]]:
    """Extract text content from a v4c HTML template for validation."""
    import html as html_lib

    raw = path.read_text(encoding="utf-8", errors="ignore")
    item_en: list[str] = []
    item_jp: list[str] = []
    all_text: list[str] = []

    # Extract text from <span class="item-en"> and <span class="item-jp">
    for match in re.finditer(r'<span\s+class="([^"]*)"[^>]*>(.*?)</span>', raw, re.DOTALL):
        classes = match.group(1).split()
        text = re.sub(r'<[^>]+>', '', match.group(2)).strip()
        text = html_lib.unescape(text)
        if not text:
            continue
        if "item-en" in classes:
            item_en.append(text)
            all_text.append(text)
        elif "item-jp" in classes:
            item_jp.append(text)
            all_text.append(text)

    # Extract section titles
    for match in re.finditer(r'<span\s+class="section-title"[^>]*>(.*?)</span>', raw, re.DOTALL):
        text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
        text = html_lib.unescape(text)
        if text:
            all_text.append(text)

    # Extract menu title
    for match in re.finditer(r'<h1\s+class="menu-title"[^>]*>(.*?)</h1>', raw, re.DOTALL):
        text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
        text = html_lib.unescape(text)
        if text:
            all_text.append(text)

    return {"all": all_text, "item_en": item_en, "item_jp": item_jp}


def _template_item_texts(path: Path) -> set[str]:
    if not path.exists():
        return set()
    if path.suffix.lower() == ".svg":
        report = _svg_text_report(path)
    else:
        report = _html_text_report(path)
    return set(report["all"])


def _load_template_placeholder_items() -> set[str]:
    """Legacy print templates are retired; no placeholder whitelist is active."""
    return set()


TEMPLATE_PLACEHOLDER_ITEMS: set[str] = _load_template_placeholder_items()


def _allowed_static_svg_text(panel_key: str) -> set[str]:
    return {"FOOD MENU" if panel_key == "food" else "DRINKS MENU"}


def _expected_rendered_section_titles(panel: dict[str, Any]) -> set[str]:
    title = _effective_panel_title(panel)
    sections = list(panel.get("sections") or [])
    if not sections:
        return set()
    if _should_fold_sides_into_ramen(sections):
        expected: set[str] = set()
        first = sections[0]
        first_title = str(first.get("title") or "").strip()
        if not _section_heading_is_redundant(title, first_title):
            expected.add(first_title)
        expected.add("SIDES / ADD-ONS")
        return expected
    return {
        section_title
        for section in sections
        for section_title in [str(section.get("title") or "").strip()]
        if section_title and not _section_heading_is_redundant(title, section_title)
    }


def _section_heading_is_redundant(panel_title: str, section_title: str) -> bool:
    normalized_panel = _normalize_menu_title(panel_title)
    normalized_section = _normalize_menu_title(section_title)
    return normalized_panel == normalized_section or normalized_panel == f"{normalized_section} MENU"


def _effective_panel_title(panel: dict[str, Any]) -> str:
    title = str(panel.get("title") or "")
    sections = list(panel.get("sections") or [])
    if _normalize_menu_title(title) == "FOOD MENU":
        rendered_sections = sections[:1] if _should_fold_sides_into_ramen(sections) else sections
        if len(rendered_sections) == 1 and _is_ramen_title(str(rendered_sections[0].get("title") or "")):
            return "RAMEN MENU"
    return title


def _normalize_menu_title(value: str) -> str:
    return " ".join(str(value or "").strip().upper().replace("&", "AND").split())


def _should_fold_sides_into_ramen(sections: list[dict[str, Any]]) -> bool:
    if len(sections) < 2:
        return False
    first_title = str(sections[0].get("title") or "")
    if not _is_ramen_title(first_title):
        return False
    return all(_is_side_addon_title(str(section.get("title") or "")) for section in sections[1:])


def _is_ramen_title(title: str) -> bool:
    normalized = str(title or "").strip().upper()
    return normalized in {"RAMEN", "NOODLES", "RAMEN MENU"} or "RAMEN" in normalized


def _is_side_addon_title(title: str) -> bool:
    normalized = str(title or "").strip().upper().replace("&", "AND")
    side_tokens = ("SIDE", "SMALL PLATE", "ADD-ON", "ADD ON", "TOPPING", "EXTRA")
    return any(token in normalized for token in side_tokens)


def _customer_visible_english(item: dict[str, Any], *, show_prices: bool = False) -> str:
    english = str(item.get("english_name") or item.get("name") or "").strip()
    price = str(item.get("price") or "").strip()
    if _item_price_should_render(item, show_prices=show_prices) and price:
        return f"{english}  {price}"
    return english


def _item_price_requires_output(item: dict[str, Any]) -> bool:
    price = str(item.get("price") or "").strip()
    if not price:
        return False
    if str(item.get("price_visibility") or "").strip() == "intentionally_hidden":
        return False
    return str(item.get("price_status") or "").strip() == "confirmed_by_business"


def _item_price_should_render(item: dict[str, Any], *, show_prices: bool) -> bool:
    return show_prices and _item_price_requires_output(item)


def _final_manifest(
    *,
    job: dict[str, Any],
    output_dir: Path,
    package_key: str,
    validation: dict[str, Any],
    generated_files: list[Path] | None = None,
    approval_timestamp: str = "",
) -> dict[str, Any]:
    package = PACKAGE_REGISTRY[package_key]
    artifacts: list[dict[str, Any]] = []
    for name in _package_files(output_dir, package_key=package_key):
        role = "qr_sign_pdf" if name.endswith(".pdf") else "hosted_menu_html" if name.endswith(".html") else "menu_asset"
        artifacts.append(artifact_entry(output_dir / name, arcname=name, role=role))
    for path in generated_files or []:
        role = "confirmation_summary"
        artifacts.append(artifact_entry(path, arcname=path.name, role=role))
    return package_manifest(
        package_key=package_key,
        package_label=package["label"],
        restaurant_name=str(job.get("restaurant_name") or ""),
        job_id=str(job.get("job_id") or ""),
        approval_timestamp=approval_timestamp or datetime.now(timezone.utc).isoformat(),
        artifacts=artifacts,
        source_input_references={
            "lead_id": job.get("lead_id", ""),
            "reply_id": job.get("reply_id", ""),
            "order_id": job.get("order_id", ""),
            "output_dir": str(output_dir),
            "photo_paths": list(job.get("photo_paths") or []),
        },
        validation=validation,
    )


def _append_history(job: dict[str, Any], status: str, timestamp: str, reviewer: str) -> None:
    history = job.setdefault("status_history", [])
    if isinstance(history, list):
        history.append({
            "status": status,
            "timestamp": timestamp,
            "reviewer": reviewer,
        })


def _normalise_build_package(package_key: Any) -> str:
    from .constants import LEGACY_PACKAGE_KEY_MAP

    value = str(package_key or ENGLISH_QR_MENU_KEY)
    if value in PACKAGE_REGISTRY:
        return value
    if value in LEGACY_PACKAGE_KEY_MAP:
        return LEGACY_PACKAGE_KEY_MAP[value]
    raise PackageExportError(f"Unsupported build package: {value}")


def _validation_result(*, errors: list[str], warnings: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }


def _derive_review_checklist(menu_data: dict[str, Any], *, validation: dict[str, Any] | None = None) -> dict[str, Any]:
    food_sections = (menu_data.get("food") or {}).get("sections") or []
    drinks_sections = (menu_data.get("drinks") or {}).get("sections") or []
    all_sections = [*food_sections, *drinks_sections]
    all_items = [item for section in all_sections for item in section.get("items") or [] if isinstance(item, dict)]
    show_prices = bool(menu_data.get("show_prices"))
    source_price_count = sum(1 for item in all_items if str(item.get("price") or "").strip())
    visible_price_count = sum(1 for item in all_items if _item_price_should_render(item, show_prices=show_prices))
    errors = (validation or {}).get("errors") or []
    return {
        "item_count": len(all_items),
        "price_count": visible_price_count,
        "source_price_count": source_price_count,
        "hidden_price_count": max(0, source_price_count - visible_price_count),
        "food_section_count": len(food_sections),
        "drinks_section_count": len(drinks_sections),
        "section_split": "separated" if food_sections and drinks_sections else "single_panel_only",
        "stale_text_absent": not any("stale_template_text_present" in str(err) for err in errors),
        "owner_source_present": all(bool(str(item.get("source_provenance") or "").strip()) for item in all_items),
    }


def _menu_item_count(menu_data: dict[str, Any]) -> int:
    count = 0
    sections = menu_data.get("sections")
    if not sections:
        sections = [*(menu_data.get("food", {}).get("sections") or []), *(menu_data.get("drinks", {}).get("sections") or [])]
    for section in sections or []:
        if isinstance(section, dict):
            count += len(section.get("items") or [])
    return count
