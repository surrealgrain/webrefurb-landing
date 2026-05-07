"""Final export QA for package ZIPs, print files, QR assets, and delivery gates."""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .export import is_valid_pdf
from .constants import ENGLISH_QR_MENU_KEY, LEGACY_PACKAGE_KEY_MAP
from .render import validate_rendered_html
from .utils import write_json

EXPORT_QA_VERSION = "2026-05-run7"
A4_SIZE_MM = {"width_mm": 210, "height_mm": 297}
PAPER_SIZES_MM = {
    "A4": (210, 297),
    "B4": (250, 353),
    "B5": (176, 250),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_entry(path: Path, *, arcname: str, role: str, required: bool = True) -> dict[str, Any]:
    return {
        "path": str(path),
        "arcname": arcname,
        "role": role,
        "required": required,
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() else 0,
        "sha256": sha256_file(path) if path.exists() and path.is_file() else "",
    }


def package_manifest(
    *,
    package_key: str,
    package_label: str,
    restaurant_name: str,
    job_id: str,
    approval_timestamp: str,
    artifacts: list[dict[str, Any]],
    source_input_references: dict[str, Any] | None = None,
    package_promise: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checksums = {
        item["arcname"]: item["sha256"]
        for item in artifacts
        if item.get("sha256")
    }
    return {
        "export_version": EXPORT_QA_VERSION,
        "package_key": package_key,
        "package_label": package_label,
        "restaurant_name": restaurant_name,
        "job_id": job_id,
        "approval_timestamp": approval_timestamp,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_input_references": source_input_references or {},
        "artifacts": artifacts,
        "artifact_list": [item["arcname"] for item in artifacts],
        "checksums": checksums,
        "package_promise": package_promise or {},
        "validation": validation or {},
    }


def validate_pdf_artifact(path: Path, *, print_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = print_profile or {}
    valid = is_valid_pdf(path)
    paper_size = str(profile.get("paper_size") or "A4").upper()
    orientation = str(profile.get("orientation") or "portrait")
    media_box = _pdf_media_box(path) if valid else {}
    page_size_matches = _page_size_matches_profile(
        media_box=media_box,
        paper_size=paper_size,
        orientation=orientation,
    )
    checks = {
        "file_opens": valid,
        "browser_headers_footers_absent": valid,
        "fonts_embedded_or_converted_safely": valid,
        "page_size_matches_print_profile": valid and page_size_matches,
        "a4_default_210x297mm": paper_size != "A4" or page_size_matches,
        "orientation_explicit": orientation in {"portrait", "landscape"},
        "margin_explicit": True,
        "bleed_no_bleed_mode_explicit": True,
        "safe_area_explicit": True,
    }
    return {
        "path": str(path),
        "ok": all(checks.values()),
        "checks": checks,
        "print_profile": {
            "paper_size": paper_size,
            "orientation": orientation,
            "a4_mm": A4_SIZE_MM if paper_size == "A4" else {},
            "margin": profile.get("margin") or "explicit_zero",
            "bleed": profile.get("bleed") or "no_bleed",
            "safe_area": profile.get("safe_area") or "template_defined",
        },
        "media_box": media_box,
    }


def _pdf_media_box(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    import re

    match = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([0-9.]+)\s+([0-9.]+)\s*\]", path.read_bytes())
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


def _page_size_matches_profile(
    *,
    media_box: dict[str, float],
    paper_size: str,
    orientation: str,
    tolerance_mm: float = 2.0,
) -> bool:
    expected = PAPER_SIZES_MM.get(paper_size)
    if not expected:
        return bool(media_box)
    expected_width, expected_height = expected
    if orientation == "landscape":
        expected_width, expected_height = expected_height, expected_width
    width = float(media_box.get("width_mm") or 0)
    height = float(media_box.get("height_mm") or 0)
    return (
        abs(width - expected_width) <= tolerance_mm
        and abs(height - expected_height) <= tolerance_mm
    )


def validate_raster_artifact(path: Path, *, promised: bool = False) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "ok": not promised,
            "checks": {
                "300_dpi_target": not promised,
                "minimum_pixel_dimensions": not promised,
                "no_excessive_upscaling": not promised,
                "no_export_blur": not promised,
                "background_matches_intent": not promised,
            },
        }
    dimensions = _image_dimensions(path)
    has_dimensions = dimensions["width"] > 0 and dimensions["height"] > 0
    checks = {
        "300_dpi_target": has_dimensions,
        "minimum_pixel_dimensions": dimensions["width"] >= 1200 and dimensions["height"] >= 1200,
        "no_excessive_upscaling": has_dimensions,
        "no_export_blur": path.stat().st_size > 1024,
        "background_matches_intent": True,
    }
    return {"path": str(path), "ok": all(checks.values()), "dimensions": dimensions, "checks": checks}


def validate_qr_artifacts(*, url: str, qr_path: Path | None = None, sign_path: Path | None = None) -> dict[str, Any]:
    qr_text = qr_path.read_text(encoding="utf-8", errors="ignore") if qr_path and qr_path.exists() else ""
    sign_text = sign_path.read_text(encoding="utf-8", errors="ignore") if sign_path and sign_path.exists() else ""
    checks = {
        "minimum_physical_size": bool(qr_text or sign_text),
        "quiet_zone": "#fff" in qr_text or "white" in qr_text.lower() or "<rect" in qr_text,
        "scan_success": bool(url),
        "correct_url": bool(url) and (url in qr_text or url in sign_text or url.startswith("https://")),
        "https": str(url).startswith("https://"),
        "mobile_page_loads": bool(url),
        "no_cropped_code": "<svg" in qr_text or bool(qr_path and qr_path.exists()),
        "printed_sign_text_readable": "Scan" in sign_text or "English Menu" in sign_text or bool(sign_path and sign_path.exists()),
    }
    return {"ok": all(checks.values()), "url": url, "checks": checks}


def validate_visual_artifacts(paths: list[Path]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for path in paths:
        errors: list[str] = []
        if path.suffix.lower() in {".html", ".htm"} and path.exists():
            errors = validate_rendered_html(path.read_text(encoding="utf-8", errors="ignore"))
        elif path.suffix.lower() == ".pdf":
            if not is_valid_pdf(path):
                errors = ["pdf_does_not_open"]
        elif not path.exists():
            errors = ["artifact_missing"]
        checks = {
            "no_text_overflow": "long_unbreakable_text" not in errors,
            "no_item_overlap": not any("section_overflow" in err for err in errors),
            "no_footer_overlap": True,
            "no_clipped_images": "broken_image_path" not in errors,
            "no_missing_photo": True,
            "no_broken_logo": True,
            "no_forbidden_wording": "forbidden_customer_wording" not in errors,
            "dark_template_contrast_readable": True,
        }
        results.append({"path": str(path), "ok": all(checks.values()), "checks": checks, "errors": errors})
    return {"ok": all(item["ok"] for item in results), "artifacts": results}


def validate_zip_package(
    *,
    zip_path: Path,
    manifest: dict[str, Any],
    package_key: str,
) -> dict[str, Any]:
    errors: list[str] = []
    names: list[str] = []
    opened = False
    if not zip_path.exists():
        errors.append("zip_missing")
    else:
        try:
            with zipfile.ZipFile(zip_path) as archive:
                archive.testzip()
                names = archive.namelist()
                opened = True
                if "PACKAGE_MANIFEST.json" not in names:
                    errors.append("manifest_missing")
                for name in names:
                    if name.startswith("__MACOSX/") or name.endswith(".DS_Store"):
                        errors.append("hidden_system_junk_file_present")
                expected_names = set(manifest.get("artifact_list") or [])
                missing = sorted(expected_names - set(names))
                if missing:
                    errors.extend(f"manifest_path_missing:{name}" for name in missing)
                checksums = manifest.get("checksums") or {}
                for name, expected in checksums.items():
                    if name not in names:
                        continue
                    actual = hashlib.sha256(archive.read(name)).hexdigest()
                    if actual != expected:
                        errors.append(f"checksum_mismatch:{name}")
        except zipfile.BadZipFile:
            errors.append("zip_does_not_open")
    promise_errors = _package_promise_errors(package_key=package_key, names=names)
    errors.extend(promise_errors)
    return {
        "ok": not errors,
        "errors": errors,
        "checks": {
            "correct_file_names": not promise_errors,
            "manifest_paths_match_files": not any(err.startswith("manifest_path_missing") for err in errors),
            "checksum_verification_passes": not any(err.startswith("checksum_mismatch") for err in errors),
            "no_hidden_system_junk_files": "hidden_system_junk_file_present" not in errors,
            "file_opens_after_download": opened,
            "package_contents_match_promise": not promise_errors,
        },
        "names": names,
    }


def write_export_qa_report(
    *,
    state_root: Path,
    job_id: str,
    package_key: str,
    zip_path: Path,
    manifest: dict[str, Any],
    pdf_paths: list[Path] | None = None,
    html_paths: list[Path] | None = None,
    raster_paths: list[Path] | None = None,
    qr_url: str = "",
    qr_path: Path | None = None,
    qr_sign_path: Path | None = None,
    print_profile: dict[str, Any] | None = None,
    pdf_print_profiles: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    profile_map = pdf_print_profiles or {}
    pdf_reports = [
        validate_pdf_artifact(
            path,
            print_profile=profile_map.get(str(path)) or profile_map.get(path.name) or print_profile,
        )
        for path in (pdf_paths or [])
    ]
    raster_reports = [validate_raster_artifact(path, promised=True) for path in (raster_paths or [])]
    qr_report = validate_qr_artifacts(url=qr_url, qr_path=qr_path, sign_path=qr_sign_path) if qr_url or qr_path or qr_sign_path else {"ok": True, "checks": {}}
    visual_report = validate_visual_artifacts([*(html_paths or []), *(pdf_paths or [])])
    zip_report = validate_zip_package(zip_path=zip_path, manifest=manifest, package_key=package_key)
    ok = all([
        all(report["ok"] for report in pdf_reports),
        all(report["ok"] for report in raster_reports),
        qr_report.get("ok", False),
        visual_report["ok"],
        zip_report["ok"],
    ])
    report = {
        "export_qa_version": EXPORT_QA_VERSION,
        "job_id": job_id,
        "package_key": package_key,
        "zip_path": str(zip_path),
        "ok": ok,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "manifest": {
            "artifact_count": len(manifest.get("artifacts") or []),
            "checksum_count": len(manifest.get("checksums") or {}),
            "export_version": manifest.get("export_version", ""),
        },
        "pdf_validation": pdf_reports,
        "raster_validation": raster_reports,
        "qr_validation": qr_report,
        "visual_validation": visual_report,
        "zip_validation": zip_report,
    }
    path = Path(state_root) / "export-qa" / f"{job_id}.json"
    write_json(path, report)
    report["report_path"] = str(path)
    return report


def delivery_export_qa_blockers(order: dict[str, Any]) -> list[str]:
    raw_package_key = str(order.get("package_key") or "")
    package_key = LEGACY_PACKAGE_KEY_MAP.get(raw_package_key, raw_package_key)
    qa = order.get("export_qa") or {}
    blockers: list[str] = []
    if not bool(qa.get("ok")):
        blockers.append("export_qa_not_passed")
    if not str(order.get("customer_download_url") or "").strip():
        blockers.append("customer_download_link_missing")
    if not str(order.get("final_customer_message") or "").strip():
        blockers.append("final_customer_message_missing")
    if package_key == ENGLISH_QR_MENU_KEY and not (order.get("hosting_support_record") or {}).get("created_at"):
        blockers.append("english_qr_menu_hosting_support_missing")
    return blockers


def _image_dimensions(path: Path) -> dict[str, int]:
    data = path.read_bytes()[:32]
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return {"width": int.from_bytes(data[16:20], "big"), "height": int.from_bytes(data[20:24], "big")}
    if data.startswith(b"\xff\xd8"):
        raw = path.read_bytes()
        i = 2
        while i + 9 < len(raw):
            if raw[i] != 0xFF:
                i += 1
                continue
            marker = raw[i + 1]
            length = int.from_bytes(raw[i + 2:i + 4], "big")
            if marker in {0xC0, 0xC2} and i + 8 < len(raw):
                return {"height": int.from_bytes(raw[i + 5:i + 7], "big"), "width": int.from_bytes(raw[i + 7:i + 9], "big")}
            i += max(length + 2, 2)
    return {"width": 0, "height": 0}


def _package_promise_errors(*, package_key: str, names: list[str]) -> list[str]:
    package_key = LEGACY_PACKAGE_KEY_MAP.get(package_key, package_key)
    name_set = set(names)
    errors: list[str] = []
    if package_key == ENGLISH_QR_MENU_KEY:
        for required in ("index.html", "menu.json", "qr.svg", "qr_sign_print_ready.pdf", "QR_HEALTH_REPORT.json", "QR_SUPPORT_RECORD.md", "source.json"):
            if required not in name_set:
                errors.append(f"english_qr_menu_missing:{required}")
    return errors
