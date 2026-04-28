"""Final export and operator review gates for paid packages."""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import (
    PACKAGE_1_KEY,
    PACKAGE_1_LABEL,
    PACKAGE_1_PRICE_YEN,
    PACKAGE_2_KEY,
    PACKAGE_2_LABEL,
    PACKAGE_2_PRICE_YEN,
    PACKAGE_REGISTRY,
)
from .export import PrintProfile, html_to_pdf_sync, is_valid_pdf
from .utils import ensure_dir, write_json, write_text


REVIEW_STATUS_PENDING = "pending_review"
REVIEW_STATUS_APPROVED = "approved"
FINAL_EXPORT_READY = "ready"

PACKAGE_1_FILES = (
    "restaurant_menu_print_ready_combined.pdf",
    "food_menu_print_ready.pdf",
    "drinks_menu_print_ready.pdf",
    "food_menu_editable_vector.svg",
    "drinks_menu_editable_vector.svg",
    "menu_data.json",
)

OPTIONAL_PACKAGE_FILES = (
    "ticket_machine_guide_print_ready.pdf",
    "ticket_machine_guide_editable_vector.svg",
    "ticket_machine_guide_browser_preview.html",
)

PREVIEW_FILES = (
    "restaurant_menu_print_master.html",
    "food_menu_browser_preview.html",
)

PACKAGE_2_PRINT_FILES = (
    "PRINT_ORDER.json",
    "PRINT_CHECKLIST.md",
    "DELIVERY_CHECKLIST.md",
)

INTERNAL_MARKERS = (
    "watermark-overlay",
    "WRM_REVIEW_ONLY",
    "Draft menu pending review",
    "data-review-gap",
)


class PackageExportError(ValueError):
    """Raised when a package cannot pass the review/export gate."""


def package_registry() -> list[dict[str, Any]]:
    """Return public package metadata in offer order."""
    return [PACKAGE_REGISTRY[key] for key in (PACKAGE_1_KEY, PACKAGE_2_KEY, "package_3_qr_menu_65k")]


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
            "validation": job.get("package_validation") or {},
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
        delivery_details=job.get("delivery_details") if package_key == PACKAGE_2_KEY else None,
    )
    package = PACKAGE_REGISTRY[package_key]
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
        "print_profile": validation.get("print_profile"),
        "artifacts": _artifact_report(output_dir, package_key=package_key),
    }


def validate_package_output(
    *,
    output_dir: Path,
    package_key: str = PACKAGE_1_KEY,
    delivery_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate that a package is safe to approve."""
    package_key = _normalise_build_package(package_key)
    errors: list[str] = []
    warnings: list[str] = []

    if not output_dir or not output_dir.exists():
        return _validation_result(errors=["output_dir_missing"], warnings=warnings)

    _validate_remote_assets(output_dir, errors)
    _validate_preview_assets(output_dir, errors)
    menu_data = _load_menu_data(output_dir, errors)

    result: dict[str, Any] = {}
    if package_key == PACKAGE_2_KEY:
        print_profile = select_print_profile(menu_data)
        result["print_profile"] = print_profile
        if print_profile["custom_quote_required"]:
            errors.append("custom_quote_required")
        details = delivery_details or {}
        if not str(details.get("delivery_contact_name") or "").strip():
            errors.append("delivery_contact_name_missing")
        if not str(details.get("delivery_address") or "").strip():
            errors.append("delivery_address_missing")

    return _validation_result(errors=errors, warnings=warnings, **result)


def validate_package1_output(*, output_dir: Path) -> dict[str, Any]:
    """Backward-compatible Package 1 validator."""
    return validate_package_output(output_dir=output_dir, package_key=PACKAGE_1_KEY)


def select_print_profile(menu_data: dict[str, Any] | None) -> dict[str, Any]:
    """Select compact print specs for one food laminate and one drinks laminate."""
    item_count = _menu_item_count(menu_data or {})
    if item_count <= 36:
        paper_size = "A4"
        reason = "normal_content_density"
    elif item_count <= 64:
        paper_size = "B4"
        reason = "dense_menu_compact_upsize"
    else:
        paper_size = "B4"
        reason = "too_dense_for_one_food_and_one_drinks_laminate"
    return {
        "paper_size": paper_size,
        "orientation": "portrait",
        "duplex": True,
        "laminated": True,
        "copy_count": 10,
        "physical_scope": "one food laminate and one drinks laminate, front/back allowed",
        "item_count": item_count,
        "reason": reason,
        "custom_quote_required": item_count > 64,
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
        delivery_details=delivery_details if selected_key == PACKAGE_2_KEY else None,
    )
    if not validation["ok"]:
        package_name = PACKAGE_REGISTRY[selected_key]["label"]
        raise PackageExportError(f"{package_name} review blocked: " + ", ".join(validation["errors"]))

    export_dir = state_root / "final_exports" / job_id
    ensure_dir(export_dir)
    package = PACKAGE_REGISTRY[selected_key]
    generated_files: list[Path] = []
    if selected_key == PACKAGE_2_KEY:
        generated_files = _write_package2_print_pack(
            output_dir=output_dir,
            export_dir=export_dir,
            job=job,
            validation=validation,
            delivery_details=delivery_details or {},
        )

    manifest = _final_manifest(job=job, output_dir=output_dir, package_key=selected_key, validation=validation)
    manifest_path = export_dir / "PACKAGE_MANIFEST.json"
    write_json(manifest_path, manifest)

    zip_path = export_dir / f"{job_id}-{selected_key}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in _package_files(output_dir, package_key=selected_key):
            archive.write(output_dir / name, arcname=name)
        for path in generated_files:
            archive.write(path, arcname=path.name)
        archive.write(manifest_path, arcname="PACKAGE_MANIFEST.json")

    now = datetime.now(timezone.utc).isoformat()
    job["status"] = "completed"
    job["package_key"] = selected_key
    job["review_status"] = REVIEW_STATUS_APPROVED
    job["reviewed_by"] = reviewer
    job["reviewed_at"] = now
    job["final_export_status"] = FINAL_EXPORT_READY
    job["final_export_path"] = str(zip_path)
    job["final_export_created_at"] = now
    job["package_validation"] = validation
    if selected_key == PACKAGE_2_KEY:
        job["delivery_details"] = delivery_details or {}
        job["print_profile"] = validation.get("print_profile")
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
    }


def approve_package1_export(*, state_root: Path, job_id: str, reviewer: str = "operator") -> dict[str, Any]:
    """Backward-compatible Package 1 approval wrapper."""
    return approve_package_export(
        state_root=state_root,
        job_id=job_id,
        package_key=PACKAGE_1_KEY,
        reviewer=reviewer,
    )


def _validate_remote_assets(output_dir: Path, errors: list[str]) -> None:
    for name in PACKAGE_1_FILES:
        path = output_dir / name
        if not path.exists():
            errors.append(f"{name}_missing")
            continue
        if path.stat().st_size == 0:
            errors.append(f"{name}_empty")
        if path.suffix.lower() == ".pdf" and not is_valid_pdf(path):
            errors.append(f"{name}_not_pdf")
    for name in OPTIONAL_PACKAGE_FILES:
        path = output_dir / name
        if path.exists() and path.suffix.lower() == ".pdf" and not is_valid_pdf(path):
            errors.append(f"{name}_not_pdf")


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
    menu_json = output_dir / "menu_data.json"
    if not menu_json.exists():
        return None
    try:
        data = json.loads(menu_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        errors.append("menu_data_invalid_json")
        return None
    sections = data.get("sections") or []
    if not sections:
        errors.append("menu_sections_missing")
    elif not any(section.get("items") for section in sections if isinstance(section, dict)):
        errors.append("menu_items_missing")
    return data


def _write_package2_print_pack(
    *,
    output_dir: Path,
    export_dir: Path,
    job: dict[str, Any],
    validation: dict[str, Any],
    delivery_details: dict[str, Any],
) -> list[Path]:
    profile = validation["print_profile"]
    pdf_profile = PrintProfile(paper_size=profile["paper_size"], orientation=profile["orientation"])
    generated: list[Path] = []
    for html_name, pdf_name in (
        ("food_menu_browser_preview.html", f"food_menu_print_{profile['paper_size'].lower()}.pdf"),
        ("drinks_menu_browser_preview.html", f"drinks_menu_print_{profile['paper_size'].lower()}.pdf"),
    ):
        source = output_dir / html_name
        if source.exists():
            target = export_dir / pdf_name
            html_to_pdf_sync(source, target, print_profile=pdf_profile)
            generated.append(target)

    print_order = {
        "package_key": PACKAGE_2_KEY,
        "package_label": PACKAGE_2_LABEL,
        "price_yen": PACKAGE_2_PRICE_YEN,
        "job_id": job.get("job_id", ""),
        "restaurant_name": job.get("restaurant_name", ""),
        "print_profile": profile,
        "line_items": [
            {
                "name": "Food menu laminate",
                "file": f"food_menu_print_{profile['paper_size'].lower()}.pdf",
                "copies": profile["copy_count"],
                "laminated": True,
                "duplex": True,
            },
            {
                "name": "Drinks menu laminate",
                "file": f"drinks_menu_print_{profile['paper_size'].lower()}.pdf",
                "copies": profile["copy_count"],
                "laminated": True,
                "duplex": True,
            },
        ],
        "delivery": {
            "contact_name": str(delivery_details.get("delivery_contact_name") or "").strip(),
            "address": str(delivery_details.get("delivery_address") or "").strip(),
            "phone": str(delivery_details.get("delivery_phone") or "").strip(),
            "notes": str(delivery_details.get("delivery_notes") or "").strip(),
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    print_order_path = export_dir / "PRINT_ORDER.json"
    write_json(print_order_path, print_order)
    generated.append(print_order_path)

    print_checklist = export_dir / "PRINT_CHECKLIST.md"
    write_text(print_checklist, _print_checklist(print_order))
    generated.append(print_checklist)

    delivery_checklist = export_dir / "DELIVERY_CHECKLIST.md"
    write_text(delivery_checklist, _delivery_checklist(print_order))
    generated.append(delivery_checklist)
    return generated


def _print_checklist(print_order: dict[str, Any]) -> str:
    profile = print_order["print_profile"]
    return (
        "# Print Checklist\n\n"
        f"- Package: {PACKAGE_2_LABEL} (¥{PACKAGE_2_PRICE_YEN:,})\n"
        f"- Paper: {profile['paper_size']} {profile['orientation']}\n"
        "- Scope: one food laminate and one drinks laminate\n"
        f"- Copies: {profile['copy_count']} each\n"
        "- Duplex: yes\n"
        "- Lamination: yes\n"
        "- Confirm PDFs open and text is legible before printing\n"
    )


def _delivery_checklist(print_order: dict[str, Any]) -> str:
    delivery = print_order["delivery"]
    return (
        "# Delivery Checklist\n\n"
        f"- Contact: {delivery['contact_name']}\n"
        f"- Address: {delivery['address']}\n"
        f"- Phone: {delivery['phone'] or 'Not provided'}\n"
        f"- Notes: {delivery['notes'] or 'None'}\n"
        "- Confirm food and drinks laminates are included\n"
        "- Confirm delivery completed with restaurant staff\n"
    )


def _package_files(output_dir: Path, *, package_key: str) -> list[str]:
    files = [name for name in PACKAGE_1_FILES if (output_dir / name).exists()]
    for name in OPTIONAL_PACKAGE_FILES:
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
    names = list(PACKAGE_1_FILES) + list(OPTIONAL_PACKAGE_FILES) + list(PREVIEW_FILES)
    if package_key == PACKAGE_2_KEY:
        names += list(PACKAGE_2_PRINT_FILES)
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        path = output_dir / name
        artifacts.append({
            "name": name,
            "exists": path.exists(),
            "bytes": path.stat().st_size if path.exists() else 0,
            "required": name in PACKAGE_1_FILES,
        })
    return artifacts


def _check_html_markers(path: Path, errors: list[str]) -> None:
    content = path.read_text(encoding="utf-8", errors="ignore")
    for marker in INTERNAL_MARKERS:
        if marker in content:
            errors.append(f"internal_marker_present:{marker}")


def _final_manifest(
    *,
    job: dict[str, Any],
    output_dir: Path,
    package_key: str,
    validation: dict[str, Any],
) -> dict[str, Any]:
    package = PACKAGE_REGISTRY[package_key]
    return {
        "package_key": package_key,
        "package_label": package["label"],
        "price_yen": package["price_yen"],
        "job_id": job.get("job_id", ""),
        "restaurant_name": job.get("restaurant_name", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_output_dir": str(output_dir),
        "files": _package_files(output_dir, package_key=package_key),
        "validation": validation,
    }


def _append_history(job: dict[str, Any], status: str, timestamp: str, reviewer: str) -> None:
    history = job.setdefault("status_history", [])
    if isinstance(history, list):
        history.append({
            "status": status,
            "timestamp": timestamp,
            "reviewer": reviewer,
        })


def _normalise_build_package(package_key: Any) -> str:
    value = str(package_key or PACKAGE_1_KEY)
    if value in {PACKAGE_1_KEY, PACKAGE_2_KEY}:
        return value
    if value in {"package_B_remote_30k", "package_1"}:
        return PACKAGE_1_KEY
    if value in {"package_A_printed_delivered_45k", "package_2"}:
        return PACKAGE_2_KEY
    raise PackageExportError(f"Unsupported build package: {value}")


def _validation_result(*, errors: list[str], warnings: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }


def _menu_item_count(menu_data: dict[str, Any]) -> int:
    count = 0
    for section in menu_data.get("sections") or []:
        if isinstance(section, dict):
            count += len(section.get("items") or [])
    return count
