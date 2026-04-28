"""Final export and operator review gates for paid packages."""

from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from .constants import (
    PACKAGE_1_KEY,
    PACKAGE_1_LABEL,
    PACKAGE_1_PRICE_YEN,
    PACKAGE_2_KEY,
    PACKAGE_2_LABEL,
    PACKAGE_2_PRICE_YEN,
    PACKAGE_REGISTRY,
    TEMPLATE_PACKAGE_MENU,
)
from .export import PrintProfile, html_to_pdf_sync, is_valid_pdf
from .utils import ensure_dir, write_json, write_text


REVIEW_STATUS_PENDING = "pending_review"
REVIEW_STATUS_APPROVED = "approved"
FINAL_EXPORT_READY = "ready"

PACKAGE_1_FILES = (
    "food_menu_print_ready.pdf",
    "drinks_menu_print_ready.pdf",
    "food_menu.html",
    "drinks_menu.html",
    "menu_data.json",
)

OPTIONAL_PACKAGE_FILES = (
    "ticket_machine_guide_print_ready.pdf",
    "ticket_machine_guide.html",
)

PREVIEW_FILES = (
    "food_menu.html",
    "drinks_menu.html",
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
    menu_data = _load_menu_data(output_dir, [])
    review_checklist = _derive_review_checklist(menu_data or {}, validation=validation)
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
        "review_checklist": review_checklist,
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
    if menu_data:
        _validate_menu_schema(menu_data, errors)
        _validate_rendered_outputs(output_dir=output_dir, menu_data=menu_data, errors=errors)

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
    if data.get("approval_blockers"):
        errors.append("approval_blockers_present")
    return data


def _validate_menu_schema(menu_data: dict[str, Any], errors: list[str]) -> None:
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
        ("food_menu.html", f"food_menu_print_{profile['paper_size'].lower()}.pdf"),
        ("drinks_menu.html", f"drinks_menu_print_{profile['paper_size'].lower()}.pdf"),
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
    html = path.read_text(encoding="utf-8", errors="ignore")
    item_en: list[str] = []
    item_jp: list[str] = []
    all_text: list[str] = []

    # Extract text from <span class="item-en"> and <span class="item-jp">
    for match in re.finditer(r'<span\s+class="([^"]*)"[^>]*>(.*?)</span>', html, re.DOTALL):
        classes = match.group(1).split()
        text = re.sub(r'<[^>]+>', '', match.group(2)).strip()
        if not text:
            continue
        if "item-en" in classes:
            item_en.append(text)
            all_text.append(text)
        elif "item-jp" in classes:
            item_jp.append(text)
            all_text.append(text)

    # Extract section titles
    for match in re.finditer(r'<span\s+class="section-title"[^>]*>(.*?)</span>', html, re.DOTALL):
        text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
        if text:
            all_text.append(text)

    # Extract menu title
    for match in re.finditer(r'<h1\s+class="menu-title"[^>]*>(.*?)</h1>', html, re.DOTALL):
        text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
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
    """Load placeholder item text from v4c HTML templates."""
    items: set[str] = set()
    for template_name in (
        "ramen_food_menu.html", "izakaya_food_menu.html",
        "ramen_drinks_menu.html", "izakaya_drinks_menu.html",
    ):
        template_path = TEMPLATE_PACKAGE_MENU / template_name
        if template_path.exists():
            report = _html_text_report(template_path)
            items.update(report["all"])
    return items


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
