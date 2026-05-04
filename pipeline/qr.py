"""Reliable QR menu hosting and versioning.

This module treats public QR menu files as deploy artifacts. The source of
truth lives under state/qr_menus, and published static files are immutable
version folders plus a small live manifest/shell.
"""

from __future__ import annotations

import html
import json
import re
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import PACKAGE_3_KEY, PACKAGE_3_LABEL, PACKAGE_3_PRICE_YEN
from .export import PrintProfile, html_to_pdf_sync, is_valid_pdf
from .final_export_qa import artifact_entry, package_manifest, write_export_qa_report
from .utils import ensure_dir, slugify, write_json, write_text


PUBLIC_BASE_URL = "https://webrefurb.com"
QR_STATES = {
    "draft",
    "needs_extraction",
    "ready_for_review",
    "published",
    "superseded",
    "rollback_active",
    "archived",
}

_QR_INTENT_RE = re.compile(
    r"(?i)\b(qr|online\s+menu|web\s+menu|hosted\s+menu|digital\s+menu|menu\s+page)\b"
)
_QR_INTENT_JA = (
    "qrコード",
    "QRコード",
    "オンラインメニュー",
    "英語メニューページ",
    "ウェブメニュー",
    "webメニュー",
    "デジタルメニュー",
)
_INTERNAL_MARKERS = (
    "data-review-gap",
    "WRM_REVIEW_ONLY",
    "Missing description",
    "Missing ingredients",
    "pending review",
)
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"}
_CONTENT_CONFIRMATION_STATUSES = {
    "pending_owner_confirmation",
    "confirmed_by_owner",
    "not_provided",
    "not_required",
}
_DEFAULT_CONTENT_REQUIREMENTS = {
    "descriptions_required": True,
    "ingredient_allergen_required": True,
}
_QR_PACKAGE_PROMISE = {
    "hosting_term": "12 months of hosting from the publish date",
    "update_policy": "One bundled content update round in the first 30 days; later updates are handled as paid update work.",
    "support": "Basic support during the hosting term covers QR link issues, page-loading failures, and minor approved text fixes.",
    "after_term": "After 12 months the restaurant can renew hosting or let the page retire after export handoff and notice.",
}


class QRMenuError(ValueError):
    """Raised for operator-fixable QR menu workflow errors."""


def utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def detect_qr_intent(text: str) -> bool:
    """Return true when a reply explicitly asks for QR / hosted menu service."""
    value = str(text or "")
    compact = value.replace(" ", "")
    return bool(_QR_INTENT_RE.search(value)) or any(token in compact for token in _QR_INTENT_JA)


def stable_menu_id(*, business_name: str, lead_id: str = "") -> str:
    base = slugify(business_name) if business_name else ""
    if base:
        return base
    if lead_id:
        return slugify(lead_id)
    return f"menu-{uuid.uuid4().hex[:8]}"


def assess_reply_qr_readiness(reply: dict[str, Any]) -> dict[str, Any]:
    body = f"{reply.get('subject', '')}\n{reply.get('body', '')}"
    stored_photo_count = int(reply.get("stored_photo_count") or 0)
    qr_requested = detect_qr_intent(body)
    missing: list[str] = []
    if stored_photo_count <= 0:
        missing.append("stored_menu_photos")
    if not qr_requested:
        missing.append("qr_service_confirmation")
    return {
        "qr_requested": qr_requested,
        "qr_ready": not missing,
        "qr_missing_fields": missing,
        "qr_ready_reason": "stored photos and QR service confirmation detected" if not missing else "",
    }


def create_qr_draft(
    *,
    reply: dict[str, Any],
    state_root: Path,
    docs_root: Path,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    readiness = assess_reply_qr_readiness(reply)
    if not readiness["qr_ready"]:
        raise QRMenuError("QR menu is not ready: " + ", ".join(readiness["qr_missing_fields"]))

    menu_id = stable_menu_id(
        business_name=str(reply.get("business_name") or ""),
        lead_id=str(reply.get("lead_id") or ""),
    )
    job_id = f"qr-{uuid.uuid4().hex[:8]}"
    version_id = f"draft-{utc_compact()}-{uuid.uuid4().hex[:6]}"
    source = _source_from_reply(reply, menu_id=menu_id, version_id=version_id, job_id=job_id, payload=payload)
    if not source.get("items"):
        return _create_needs_extraction_job(
            reply=reply,
            state_root=state_root,
            menu_id=menu_id,
            job_id=job_id,
            version_id=version_id,
            source=source,
        )

    _write_state_version(state_root, menu_id, version_id, source, status="draft")
    draft_dir = docs_root / "menus" / "_drafts" / job_id
    _write_public_version(draft_dir, source=source, public_url=_draft_url(job_id), draft=True)

    report = validate_source_for_publish(source=source, public_dir=draft_dir, draft=True)
    job = {
        "job_id": job_id,
        "menu_id": menu_id,
        "version_id": version_id,
        "status": "ready_for_review",
        "reply_id": reply.get("reply_id", ""),
        "lead_id": reply.get("lead_id", ""),
        "draft_url": f"/menus/_drafts/{job_id}/",
        "qr_asset_url": f"/menus/_drafts/{job_id}/qr.svg",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "validation": report,
    }
    _write_qr_job(state_root, job)
    _append_audit(state_root, menu_id, "draft_created", {"job_id": job_id, "version_id": version_id})
    return job


def get_qr_job(*, state_root: Path, job_id: str) -> dict[str, Any] | None:
    path = state_root / "qr_jobs" / f"{job_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def get_qr_review(*, state_root: Path, docs_root: Path, job_id: str) -> dict[str, Any]:
    job = get_qr_job(state_root=state_root, job_id=job_id)
    if not job:
        raise QRMenuError("QR job not found")
    draft_dir = docs_root / "menus" / "_drafts" / job_id
    source = _read_state_source(state_root, job["menu_id"], job["version_id"])
    if job.get("status") == "needs_extraction":
        validation = {
            "ok": False,
            "errors": ["structured_menu_items_required"],
            "warnings": [],
        }
    else:
        validation = validate_source_for_publish(source=source, public_dir=draft_dir, draft=True)
    job["validation"] = validation
    _write_qr_job(state_root, job)
    return {
        **job,
        "package_key": PACKAGE_3_KEY,
        "package_label": PACKAGE_3_LABEL,
        "price_yen": PACKAGE_3_PRICE_YEN,
        "review_status": job.get("review_status", "pending_review"),
        "final_export_status": job.get("final_export_status", ""),
        "download_url": f"/api/qr/{job_id}/download" if job.get("final_export_path") else "",
        "source": source,
        "completeness": _completeness_report(source),
        "content_requirements": _content_requirements(source),
        "owner_confirmation": _owner_confirmation_summary(source),
        "package_promise": _QR_PACKAGE_PROMISE,
        "publish_validation": validate_source_for_publish(source=source, public_dir=None, draft=False),
        "draft_url": job.get("draft_url", ""),
        "qr_asset_url": job.get("qr_asset_url", ""),
        "extraction_required": job.get("status") == "needs_extraction",
        "next_step": (
            "Run QR extraction from the stored menu photos or submit structured menu items before review."
            if job.get("status") == "needs_extraction" else ""
        ),
    }


def publish_qr_job(*, state_root: Path, docs_root: Path, job_id: str) -> dict[str, Any]:
    job = get_qr_job(state_root=state_root, job_id=job_id)
    if not job:
        raise QRMenuError("QR job not found")

    menu_id = job["menu_id"]
    draft_source = _read_state_source(state_root, menu_id, job["version_id"])
    publish_version = f"v-{utc_compact()}-{uuid.uuid4().hex[:6]}"
    source = {**draft_source, "version_id": publish_version, "status": "published"}
    public_dir = docs_root / "menus" / menu_id / "versions" / publish_version
    if public_dir.exists():
        raise QRMenuError("Version folder already exists; refusing to overwrite")

    report = validate_source_for_publish(source=source, public_dir=None, draft=False)
    if not report["ok"]:
        job["status"] = "validation_failed"
        job["validation"] = report
        _write_qr_job(state_root, job)
        raise QRMenuError("QR publish blocked: " + ", ".join(report["errors"]))

    include_sign = bool(job.get("qr_sign_created_at"))
    _write_state_version(state_root, menu_id, publish_version, source, status="published")
    _write_public_version(
        public_dir,
        source=source,
        public_url=f"{PUBLIC_BASE_URL}/menus/{menu_id}/",
        draft=False,
        include_sign=include_sign,
    )
    publish_manifest = _manifest_for_public_dir(public_dir)
    _write_publish_manifest(state_root, menu_id, publish_version, publish_manifest)
    _publish_live_pointer(docs_root=docs_root, menu_id=menu_id, version_id=publish_version, publish_manifest=publish_manifest)
    _mark_previous_versions_superseded(state_root=state_root, menu_id=menu_id, current_version=publish_version)

    job["status"] = "published"
    job["published_version_id"] = publish_version
    job["live_url"] = f"{PUBLIC_BASE_URL}/menus/{menu_id}/"
    if include_sign:
        job["qr_sign_url"] = f"/menus/{menu_id}/versions/{publish_version}/qr_sign.html"
        job["qr_sign_svg_url"] = f"/menus/{menu_id}/versions/{publish_version}/qr_sign.svg"
    job["published_at"] = datetime.now(timezone.utc).isoformat()
    job["validation"] = {"ok": True, "errors": [], "warnings": []}
    _write_qr_job(state_root, job)
    _append_audit(state_root, menu_id, "published", {"job_id": job_id, "version_id": publish_version})
    health = check_qr_health(state_root=state_root, docs_root=docs_root, menu_id=menu_id)
    return {**job, "health": health}


def create_qr_sign(*, state_root: Path, docs_root: Path, job_id: str) -> dict[str, Any]:
    """Create or refresh the printable QR sign for a draft or published QR job."""
    job = get_qr_job(state_root=state_root, job_id=job_id)
    if not job:
        raise QRMenuError("QR job not found")
    menu_id = job["menu_id"]
    version_id = str(job.get("published_version_id") or job.get("version_id") or "")
    source = _read_state_source(state_root, menu_id, version_id)
    if job.get("status") == "published" and job.get("published_version_id"):
        public_dir = docs_root / "menus" / menu_id / "versions" / job["published_version_id"]
        sign_url = f"/menus/{menu_id}/versions/{job['published_version_id']}/qr_sign.html"
        sign_svg_url = f"/menus/{menu_id}/versions/{job['published_version_id']}/qr_sign.svg"
        if not (public_dir / "qr_sign.html").exists() or not (public_dir / "qr_sign.svg").exists():
            raise QRMenuError("QR sign must be created before publishing this version")
        return {
            "job_id": job_id,
            "menu_id": menu_id,
            "version_id": version_id,
            "qr_sign_url": sign_url,
            "qr_sign_svg_url": sign_svg_url,
        }
    else:
        public_dir = docs_root / "menus" / "_drafts" / job_id
        sign_url = f"/menus/_drafts/{job_id}/qr_sign.html"
        sign_svg_url = f"/menus/_drafts/{job_id}/qr_sign.svg"
        public_url = _draft_url(job_id)
        draft = True
    ensure_dir(public_dir)
    _write_qr_sign(public_dir, source=source, public_url=public_url, draft=draft)
    job["qr_sign_url"] = sign_url
    job["qr_sign_svg_url"] = sign_svg_url
    job["qr_sign_created_at"] = datetime.now(timezone.utc).isoformat()
    _write_qr_job(state_root, job)
    _append_audit(state_root, menu_id, "qr_sign_created", {"job_id": job_id, "version_id": version_id})
    return {
        "job_id": job_id,
        "menu_id": menu_id,
        "version_id": version_id,
        "qr_sign_url": sign_url,
        "qr_sign_svg_url": sign_svg_url,
    }


def approve_qr_package(
    *,
    state_root: Path,
    docs_root: Path,
    job_id: str,
    reviewer: str = "operator",
) -> dict[str, Any]:
    """Approve, publish, health-check, and package the paid Live QR English Menu."""
    job = get_qr_job(state_root=state_root, job_id=job_id)
    if not job:
        raise QRMenuError("QR job not found")
    if not job.get("qr_sign_created_at"):
        raise QRMenuError("QR package approval blocked: qr_sign_missing")

    if job.get("status") != "published":
        published = publish_qr_job(state_root=state_root, docs_root=docs_root, job_id=job_id)
        job = published

    menu_id = str(job.get("menu_id") or "")
    version_id = str(job.get("published_version_id") or "")
    health = check_qr_health(state_root=state_root, docs_root=docs_root, menu_id=menu_id)
    if not health.get("ok"):
        raise QRMenuError("QR package approval blocked: health_check_failed")

    version_dir = docs_root / "menus" / menu_id / "versions" / version_id
    sign_html = version_dir / "qr_sign.html"
    if not sign_html.exists():
        raise QRMenuError("QR package approval blocked: qr_sign_missing")

    export_dir = state_root / "final_exports" / job_id
    ensure_dir(export_dir)
    sign_pdf = export_dir / "qr_sign_print_ready.pdf"
    html_to_pdf_sync(sign_html, sign_pdf, print_profile=PrintProfile(paper_size="A4", orientation="portrait"))
    if not is_valid_pdf(sign_pdf):
        raise QRMenuError("QR package approval blocked: qr_sign_pdf_invalid")

    health_path = export_dir / "QR_HEALTH_REPORT.json"
    write_json(health_path, health)
    support_path = export_dir / "QR_SUPPORT_RECORD.md"
    write_text(
        support_path,
        "# QR Support Record\n\n"
        f"- Restaurant: {job.get('restaurant_name', '')}\n"
        f"- Live URL: {job.get('live_url', '')}\n"
        "- Hosting term: 12 months from publish date\n"
        "- Support: QR link issues, page-loading failures, and minor approved text fixes during the hosting term\n",
    )

    state_source = state_root / "qr_menus" / menu_id / "versions" / version_id / "source.json"
    artifacts: list[dict[str, Any]] = []
    for filename in ("index.html", "menu.json", "qr.svg", "qr_sign.html", "qr_sign.svg"):
        path = version_dir / filename
        if path.exists():
            role = "qr_image" if filename == "qr.svg" else "hosted_menu_backup"
            artifacts.append(artifact_entry(path, arcname=filename, role=role))
    if state_source.exists():
        artifacts.append(artifact_entry(state_source, arcname="source.json", role="source_input"))
    artifacts.extend([
        artifact_entry(sign_pdf, arcname=sign_pdf.name, role="qr_sign_pdf"),
        artifact_entry(health_path, arcname=health_path.name, role="qr_health_check"),
        artifact_entry(support_path, arcname=support_path.name, role="hosting_support_record"),
    ])
    manifest = _qr_package_manifest(job=job, health=health, artifacts=artifacts)
    manifest_path = export_dir / "PACKAGE_MANIFEST.json"
    write_json(manifest_path, manifest)

    zip_path = export_dir / f"{job_id}-{PACKAGE_3_KEY}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename in ("index.html", "menu.json", "qr.svg", "qr_sign.html", "qr_sign.svg"):
            path = version_dir / filename
            if path.exists():
                archive.write(path, arcname=filename)
        if state_source.exists():
            archive.write(state_source, arcname="source.json")
        archive.write(sign_pdf, arcname=sign_pdf.name)
        archive.write(health_path, arcname=health_path.name)
        archive.write(support_path, arcname=support_path.name)
        archive.write(manifest_path, arcname=manifest_path.name)

    now = datetime.now(timezone.utc).isoformat()
    export_qa = write_export_qa_report(
        state_root=state_root,
        job_id=job_id,
        package_key=PACKAGE_3_KEY,
        zip_path=zip_path,
        manifest=manifest,
        pdf_paths=[sign_pdf],
        html_paths=[version_dir / "index.html", version_dir / "qr_sign.html"],
        qr_url=str(job.get("live_url") or ""),
        qr_path=version_dir / "qr.svg",
        qr_sign_path=version_dir / "qr_sign.html",
        print_profile={"paper_size": "A4", "orientation": "portrait"},
    )
    if not export_qa["ok"]:
        raise QRMenuError("QR package approval blocked: export_qa_failed")

    job["package_key"] = PACKAGE_3_KEY
    job["package_label"] = PACKAGE_3_LABEL
    job["price_yen"] = PACKAGE_3_PRICE_YEN
    job["review_status"] = "approved"
    job["reviewed_by"] = reviewer
    job["reviewed_at"] = now
    job["final_export_status"] = "ready"
    job["final_export_path"] = str(zip_path)
    job["final_export_created_at"] = now
    job["qr_sign_print_ready_pdf"] = str(sign_pdf)
    job["export_qa_status"] = "passed"
    job["export_qa_report_path"] = export_qa["report_path"]
    _write_qr_job(state_root, job)
    _append_audit(state_root, menu_id, "package_3_approved", {"job_id": job_id, "version_id": version_id})
    return {
        **job,
        "download_url": f"/api/qr/{job_id}/download",
        "health": health,
        "export_qa": export_qa,
        "package_promise": _QR_PACKAGE_PROMISE,
    }


def create_edit_draft(
    *,
    state_root: Path,
    docs_root: Path,
    menu_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    live = _read_live_manifest(docs_root, menu_id)
    current = live.get("current_version")
    if not current:
        raise QRMenuError("Live menu has no current version")
    source = _read_state_source(state_root, menu_id, current)
    version_id = f"draft-{utc_compact()}-{uuid.uuid4().hex[:6]}"
    job_id = f"qr-{uuid.uuid4().hex[:8]}"
    draft_source = {**source, "version_id": version_id, "job_id": job_id, "status": "draft"}
    if "items" in payload:
        draft_source["items"] = _items_from_payload({"items": payload["items"]})
    _write_state_version(state_root, menu_id, version_id, draft_source, status="draft")
    draft_dir = docs_root / "menus" / "_drafts" / job_id
    _write_public_version(draft_dir, source=draft_source, public_url=_draft_url(job_id), draft=True)
    job = {
        "job_id": job_id,
        "menu_id": menu_id,
        "version_id": version_id,
        "status": "ready_for_review",
        "draft_url": f"/menus/_drafts/{job_id}/",
        "qr_asset_url": f"/menus/_drafts/{job_id}/qr.svg",
        "created_from_version": current,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "validation": validate_source_for_publish(source=draft_source, public_dir=draft_dir, draft=True),
    }
    _write_qr_job(state_root, job)
    _append_audit(state_root, menu_id, "edit_draft_created", {"job_id": job_id, "from_version": current})
    return job


def confirm_qr_content(
    *,
    state_root: Path,
    docs_root: Path,
    job_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    job = get_qr_job(state_root=state_root, job_id=job_id)
    if not job:
        raise QRMenuError("QR job not found")
    if job.get("status") == "needs_extraction":
        raise QRMenuError("QR content cannot be confirmed before structured extraction is complete")

    source = _read_state_source(state_root, job["menu_id"], job["version_id"])
    confirm_descriptions = bool(payload.get("confirm_descriptions", True))
    confirm_ingredient_allergen = bool(payload.get("confirm_ingredient_allergen", True))
    confirmed_by = str(payload.get("confirmed_by") or "operator")
    confirmation_source = str(payload.get("confirmation_source") or _default_confirmation_source(source))
    notes = str(payload.get("notes") or "")
    confirmed_at = datetime.now(timezone.utc).isoformat()

    updated_items = []
    any_changes = False
    for item in source.get("items") or []:
        updated_item = dict(item)
        if confirm_descriptions and str(item.get("description") or "").strip():
            updated_item["description_confirmation"] = _confirmed_content_record(
                kind="description",
                source=confirmation_source,
                confirmed_by=confirmed_by,
                confirmed_at=confirmed_at,
                notes=notes,
            )
            any_changes = True
        if confirm_ingredient_allergen and _item_has_ingredient_allergen_content(item):
            updated_item["ingredient_allergen_confirmation"] = _confirmed_content_record(
                kind="ingredient_allergen",
                source=confirmation_source,
                confirmed_by=confirmed_by,
                confirmed_at=confirmed_at,
                notes=notes,
            )
            any_changes = True
        updated_items.append(updated_item)

    if not any_changes:
        raise QRMenuError("No owner-provided description or ingredient/allergen content was available to confirm")

    updated_source = {
        **source,
        "items": updated_items,
        "last_content_confirmation_at": confirmed_at,
    }
    _write_state_version(state_root, job["menu_id"], job["version_id"], updated_source, status="draft")
    draft_dir = docs_root / "menus" / "_drafts" / job_id
    if draft_dir.exists():
        _write_public_version(draft_dir, source=updated_source, public_url=_draft_url(job_id), draft=True)
    job["validation"] = validate_source_for_publish(source=updated_source, public_dir=draft_dir if draft_dir.exists() else None, draft=True)
    _write_qr_job(state_root, job)
    _append_audit(
        state_root,
        job["menu_id"],
        "content_confirmed",
        {
            "job_id": job_id,
            "version_id": job["version_id"],
            "confirmed_by": confirmed_by,
            "confirmation_source": confirmation_source,
            "confirm_descriptions": confirm_descriptions,
            "confirm_ingredient_allergen": confirm_ingredient_allergen,
        },
    )
    return job


def complete_qr_extraction(
    *,
    state_root: Path,
    docs_root: Path,
    job_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    job = get_qr_job(state_root=state_root, job_id=job_id)
    if not job:
        raise QRMenuError("QR job not found")
    if job.get("status") != "needs_extraction":
        raise QRMenuError("QR extraction step is only available for needs_extraction jobs")

    source = _read_state_source(state_root, job["menu_id"], job["version_id"])
    items = _items_from_payload(payload)
    extraction_method = "structured_payload"
    if not items:
        items = _items_from_photo_assets(source.get("photo_assets") or [])
        extraction_method = "stored_menu_photos"
    if not items:
        raise QRMenuError("QR extraction needs structured items, menu_data, raw_text, or extractable menu photos")

    updated_source = {
        **source,
        "status": "draft",
        "items": items,
        "restaurant_name": str(payload.get("restaurant_name") or source.get("restaurant_name") or job["menu_id"]),
        "extraction_method": extraction_method,
        "extraction_completed_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_state_version(state_root, job["menu_id"], job["version_id"], updated_source, status="draft")
    draft_dir = docs_root / "menus" / "_drafts" / job_id
    _write_public_version(draft_dir, source=updated_source, public_url=_draft_url(job_id), draft=True)
    validation = validate_source_for_publish(source=updated_source, public_dir=draft_dir, draft=True)
    job.update({
        "status": "ready_for_review",
        "draft_url": f"/menus/_drafts/{job_id}/",
        "qr_asset_url": f"/menus/_drafts/{job_id}/qr.svg",
        "validation": validation,
        "extraction_required": False,
        "extraction_completed_at": updated_source["extraction_completed_at"],
        "extraction_method": extraction_method,
    })
    _write_qr_job(state_root, job)
    _append_audit(
        state_root,
        job["menu_id"],
        "extraction_completed",
        {"job_id": job_id, "version_id": job["version_id"], "item_count": len(items), "method": extraction_method},
    )
    return job


def rollback_qr_menu(*, state_root: Path, docs_root: Path, menu_id: str, version_id: str = "") -> dict[str, Any]:
    live = _read_live_manifest(docs_root, menu_id)
    versions = list(live.get("versions") or [])
    if not version_id:
        candidates = [v for v in versions if v != live.get("current_version")]
        if not candidates:
            raise QRMenuError("No previous version available for rollback")
        version_id = candidates[-1]
    if version_id not in versions:
        raise QRMenuError("Rollback version is not published")
    public_dir = docs_root / "menus" / menu_id / "versions" / version_id
    if not public_dir.exists():
        raise QRMenuError("Rollback version files are missing")
    publish_manifest = _manifest_for_public_dir(public_dir)
    _publish_live_pointer(docs_root=docs_root, menu_id=menu_id, version_id=version_id, publish_manifest=publish_manifest, rollback=True)
    _append_audit(state_root, menu_id, "rollback_active", {"version_id": version_id})
    return check_qr_health(state_root=state_root, docs_root=docs_root, menu_id=menu_id)


def check_qr_health(*, state_root: Path, docs_root: Path, menu_id: str) -> dict[str, Any]:
    errors: list[str] = []
    menu_root = docs_root / "menus" / menu_id
    manifest_path = menu_root / "manifest.json"
    live = _read_live_manifest(docs_root, menu_id)
    current = live.get("current_version", "")
    version_dir = menu_root / "versions" / current
    shell = menu_root / "index.html"
    if not manifest_path.exists():
        errors.append("live_manifest_missing")
    if not current:
        errors.append("manifest_missing_current_version")
    if not shell.exists():
        errors.append("live_shell_missing")
    if not version_dir.exists():
        errors.append("current_version_missing")
    publish_manifest = state_root / "qr_menus" / menu_id / "versions" / current / "publish_manifest.json"
    if current and not publish_manifest.exists():
        errors.append("publish_manifest_missing")
    source_path = state_root / "qr_menus" / menu_id / "versions" / current / "source.json"
    if current and not source_path.exists():
        errors.append("source_data_missing")

    required_docs = ("index.html", "menu.json", "qr.svg")
    for rel in required_docs:
        if current and not (version_dir / rel).exists():
            errors.append(f"asset_missing:{rel}")

    expected = live.get("checksums") or {}
    if current and not expected:
        errors.append("manifest_checksums_missing")
    drift: list[str] = []
    for rel, checksum in expected.items():
        path = version_dir / rel
        if not path.exists():
            continue
        actual = _sha256_file(path)
        if actual != checksum:
            drift.append(rel)

    approved_jobs = _approved_qr_jobs_for_menu(state_root=state_root, menu_id=menu_id, version_id=current)
    for approved_job in approved_jobs:
        sign_pdf = Path(str(approved_job.get("qr_sign_print_ready_pdf") or ""))
        export_zip = Path(str(approved_job.get("final_export_path") or ""))
        if not sign_pdf.exists():
            errors.append("sign_pdf_missing")
        if not export_zip.exists():
            errors.append("package_export_missing")

    ok = not errors and not drift
    report = {
        "menu_id": menu_id,
        "ok": ok,
        "status": "healthy" if ok else "unhealthy",
        "current_version": current,
        "live_url": f"{PUBLIC_BASE_URL}/menus/{menu_id}/",
        "errors": errors,
        "checksum_drift": drift,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(state_root / "qr_health" / f"{menu_id}.json", report)
    return report


def validate_source_for_publish(*, source: dict[str, Any], public_dir: Path | None, draft: bool) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not source.get("restaurant_name"):
        errors.append("restaurant_name_missing")
    requirements = _content_requirements(source)
    items = source.get("items") or []
    if not items:
        errors.append("menu_items_missing")
    for idx, item in enumerate(items):
        if not item.get("name"):
            errors.append(f"item_{idx}_english_name_missing")
        if not item.get("japanese_name"):
            errors.append(f"item_{idx}_japanese_name_missing")
        if requirements["descriptions_required"] and not item.get("description"):
            (warnings if draft else errors).append(f"item_{idx}_description_missing")
        if item.get("description") and not _content_is_owner_confirmed(item.get("description_confirmation")):
            (warnings if draft else errors).append(f"item_{idx}_description_owner_confirmation_required")
        if requirements["ingredient_allergen_required"] and not _item_has_ingredient_allergen_content(item):
            (warnings if draft else errors).append(f"item_{idx}_ingredient_allergen_missing")
        if _item_has_ingredient_allergen_content(item) and not _content_is_owner_confirmed(item.get("ingredient_allergen_confirmation")):
            (warnings if draft else errors).append(f"item_{idx}_ingredient_allergen_owner_confirmation_required")
        if str(item.get("name") or "").startswith("["):
            errors.append(f"item_{idx}_unresolved_translation")
    if public_dir:
        for filename in ("index.html", "menu.json", "qr.svg"):
            path = public_dir / filename
            if not path.exists():
                errors.append(f"{filename}_missing")
        index_path = public_dir / "index.html"
        if index_path.exists() and not draft:
            content = index_path.read_text(encoding="utf-8")
            for marker in _INTERNAL_MARKERS:
                if marker in content:
                    errors.append(f"internal_marker_present:{marker}")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def _source_from_reply(
    reply: dict[str, Any],
    *,
    menu_id: str,
    version_id: str,
    job_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    items = _items_from_payload(payload)
    return {
        "menu_id": menu_id,
        "version_id": version_id,
        "job_id": job_id,
        "status": "draft",
        "restaurant_name": str(payload.get("restaurant_name") or reply.get("business_name") or menu_id),
        "lead_id": str(reply.get("lead_id") or ""),
        "reply_id": str(reply.get("reply_id") or ""),
        "items": items,
        "photo_assets": _stored_photo_assets(reply),
        "ticket_machine": payload.get("ticket_machine") or None,
        "content_requirements": _content_requirements_from_payload(payload),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _create_needs_extraction_job(
    *,
    reply: dict[str, Any],
    state_root: Path,
    menu_id: str,
    job_id: str,
    version_id: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    source = {**source, "status": "needs_extraction"}
    _write_state_version(state_root, menu_id, version_id, source, status="needs_extraction")
    job = {
        "job_id": job_id,
        "menu_id": menu_id,
        "version_id": version_id,
        "status": "needs_extraction",
        "reply_id": reply.get("reply_id", ""),
        "lead_id": reply.get("lead_id", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "validation": {
            "ok": False,
            "errors": ["structured_menu_items_required"],
            "warnings": [],
        },
        "extraction_required": True,
        "needs_extraction_reason": "photo_only_reply_requires_structured_menu_extraction",
    }
    _write_qr_job(state_root, job)
    _append_audit(state_root, menu_id, "needs_extraction", {"job_id": job_id, "version_id": version_id})
    return job


def _items_from_payload_menu_data(menu_data: Any) -> list[dict[str, Any]]:
    if not isinstance(menu_data, dict):
        return []
    items: list[dict[str, Any]] = []
    for section in menu_data.get("sections") or []:
        for item in section.get("items") or []:
            if isinstance(item, dict):
                items.append(_normalise_qr_item(item, section_title=section.get("title", "")))
    return items


def _items_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items") or _items_from_payload_menu_data(payload.get("menu_data"))
    if items:
        return _dedupe_qr_items([_normalise_qr_item(item) for item in items if isinstance(item, dict)])

    raw_text = str(payload.get("raw_text") or payload.get("menu_text") or "").strip()
    if raw_text:
        from .extract import extract_from_text

        return _items_from_extracted_items(extract_from_text(raw_text))

    return []


def _items_from_photo_assets(photo_assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from .extract import extract_from_file

    extracted = []
    for asset in photo_assets:
        stored_path = str(asset.get("stored_path") or "")
        if not stored_path:
            continue
        extracted.extend(extract_from_file(stored_path))
    return _items_from_extracted_items(extracted)


def _items_from_extracted_items(extracted_items: list[Any]) -> list[dict[str, Any]]:
    if not extracted_items:
        return []

    from .translate import translate_items

    translated_items = translate_items(extracted_items)
    items = []
    for extracted, translated in zip(extracted_items, translated_items):
        items.append(_normalise_qr_item({
            "name": translated.name or extracted.name,
            "japanese_name": translated.japanese_name or extracted.japanese_name or extracted.name,
            "price": translated.price or extracted.price,
            "description": translated.description or "",
            "ingredients": [],
            "section": translated.section or extracted.section_hint or "Menu",
            "source_text": translated.source_text or extracted.source_text or extracted.name,
            "source_provenance": translated.source_provenance or extracted.source_provenance or "",
            "approval_status": translated.approval_status or extracted.approval_status or "pending_review",
        }))
    return _dedupe_qr_items(items)


def _normalise_qr_item(item: dict[str, Any], *, section_title: str = "") -> dict[str, Any]:
    ingredients = item.get("ingredients") or []
    if isinstance(ingredients, str):
        ingredients = [part.strip() for part in re.split(r"[,、]", ingredients) if part.strip()]
    allergens = item.get("allergens") or []
    if isinstance(allergens, str):
        allergens = [part.strip() for part in re.split(r"[,、]", allergens) if part.strip()]
    description = str(item.get("description") or "")
    return {
        "name": str(item.get("name") or ""),
        "japanese_name": str(item.get("japanese_name") or item.get("ja") or ""),
        "price": str(item.get("price") or ""),
        "description": description,
        "ingredients": ingredients,
        "allergens": allergens,
        "section": str(item.get("section") or section_title or "Menu"),
        "photo": str(item.get("photo") or ""),
        "source_text": str(item.get("source_text") or item.get("japanese_name") or item.get("name") or ""),
        "source_provenance": str(item.get("source_provenance") or ""),
        "approval_status": str(item.get("approval_status") or "pending_review"),
        "description_confirmation": _normalise_content_confirmation(
            item.get("description_confirmation"),
            content_present=bool(description.strip()),
            content_kind="description",
            default_source=str(item.get("source_provenance") or ""),
        ),
        "ingredient_allergen_confirmation": _normalise_content_confirmation(
            item.get("ingredient_allergen_confirmation") or item.get("ingredients_confirmation"),
            content_present=bool(ingredients or allergens),
            content_kind="ingredient_allergen",
            default_source=str(item.get("source_provenance") or ""),
        ),
    }


def _dedupe_qr_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = (
            str(item.get("japanese_name") or "").strip(),
            str(item.get("name") or "").strip(),
            str(item.get("section") or "").strip(),
            str(item.get("price") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _stored_photo_assets(reply: dict[str, Any]) -> list[dict[str, str]]:
    assets: list[dict[str, str]] = []
    for attachment in reply.get("attachments") or []:
        stored_path = str(attachment.get("stored_path") or "")
        if not stored_path or Path(stored_path).suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        if Path(stored_path).exists():
            assets.append({
                "filename": Path(stored_path).name,
                "stored_path": stored_path,
                "stored_url": str(attachment.get("stored_url") or ""),
            })
    return assets


def _write_state_version(state_root: Path, menu_id: str, version_id: str, source: dict[str, Any], *, status: str) -> None:
    if status not in QR_STATES:
        raise QRMenuError(f"Unknown QR status: {status}")
    version_root = state_root / "qr_menus" / menu_id / "versions" / version_id
    ensure_dir(version_root)
    record_path = state_root / "qr_menus" / menu_id / "menu_record.json"
    record = {}
    if record_path.exists():
        record = json.loads(record_path.read_text(encoding="utf-8"))
    record.update({
        "menu_id": menu_id,
        "restaurant_name": source.get("restaurant_name", ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    versions = record.get("versions") or []
    if version_id not in versions:
        versions.append(version_id)
    record["versions"] = versions
    write_json(record_path, record)
    write_json(version_root / "source.json", {**source, "status": status})
    write_json(version_root / "validation_report.json", validate_source_for_publish(source=source, public_dir=None, draft=status == "draft"))


def _write_public_version(
    public_dir: Path,
    *,
    source: dict[str, Any],
    public_url: str,
    draft: bool,
    include_sign: bool = False,
) -> None:
    if public_dir.exists() and not draft:
        raise QRMenuError("Refusing to overwrite an immutable public version")
    ensure_dir(public_dir)
    _copy_public_photo_assets(public_dir, source)
    write_json(public_dir / "menu.json", _public_menu_json(source, public_url=public_url, draft=draft))
    write_text(public_dir / "index.html", _render_mobile_menu_html(source, public_url=public_url, draft=draft))
    write_text(public_dir / "qr.svg", _render_qr_svg(public_url))
    if include_sign:
        _write_qr_sign(public_dir, source=source, public_url=public_url, draft=draft)


def _write_qr_sign(public_dir: Path, *, source: dict[str, Any], public_url: str, draft: bool) -> None:
    write_text(public_dir / "qr_sign.html", _render_qr_sign_html(source, public_url=public_url, draft=draft))
    write_text(public_dir / "qr_sign.svg", _render_qr_sign_svg(source, public_url=public_url, draft=draft))


def _copy_public_photo_assets(public_dir: Path, source: dict[str, Any]) -> None:
    assets_dir = public_dir / "assets"
    for asset in source.get("photo_assets") or []:
        src = Path(str(asset.get("stored_path") or ""))
        if not src.exists():
            continue
        ensure_dir(assets_dir)
        shutil.copy2(src, assets_dir / src.name)


def _public_menu_json(source: dict[str, Any], *, public_url: str, draft: bool) -> dict[str, Any]:
    return {
        "restaurant_name": source.get("restaurant_name", ""),
        "menu_id": source.get("menu_id", ""),
        "version_id": source.get("version_id", ""),
        "public_url": public_url,
        "draft": draft,
        "items": source.get("items") or [],
        "ticket_machine": source.get("ticket_machine"),
        "content_requirements": _content_requirements(source),
    }


def _render_mobile_menu_html(source: dict[str, Any], *, public_url: str, draft: bool) -> str:
    restaurant = html.escape(str(source.get("restaurant_name") or "English Menu"))
    items = source.get("items") or []
    sections: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        sections.setdefault(str(item.get("section") or "Menu"), []).append(item)

    section_nav = "".join(f'<a href="#sec-{slugify(name)}">{html.escape(name)}</a>' for name in sections)
    cards = []
    for section, section_items in sections.items():
        cards.append(f'<section id="sec-{slugify(section)}"><h2>{html.escape(section)}</h2>')
        for item in section_items:
            desc = html.escape(str(item.get("description") or ""))
            ingredients = item.get("ingredients") or []
            allergens = item.get("allergens") or []
            gaps = []
            if not desc:
                gaps.append("Missing description")
            if not ingredients and not allergens:
                gaps.append("Missing ingredients or allergens")
            gap_html = ""
            if draft and gaps:
                gap_html = f'<div class="review-gap" data-review-gap="true">{" · ".join(gaps)}</div>'
            ingredient_html = ""
            if ingredients:
                ingredient_html = '<p class="ingredients">Ingredients: ' + html.escape(", ".join(map(str, ingredients))) + "</p>"
            allergen_html = ""
            if allergens:
                allergen_html = '<p class="ingredients">Allergens: ' + html.escape(", ".join(map(str, allergens))) + "</p>"
            cards.append(
                '<article class="dish-card">'
                f'<div><h3>{html.escape(str(item.get("name") or ""))}</h3>'
                f'<p class="jp">{html.escape(str(item.get("japanese_name") or ""))}</p></div>'
                f'<span class="price">{html.escape(str(item.get("price") or ""))}</span>'
                f'{f"<p>{desc}</p>" if desc else ""}{ingredient_html}{allergen_html}{gap_html}'
                '</article>'
            )
        cards.append("</section>")

    ticket_html = ""
    if source.get("ticket_machine"):
        ticket_html = '<section id="ticket"><h2>Ordering Guide</h2><p>Use this guide at the ticket machine before handing your ticket to staff.</p></section>'

    draft_banner = '<div class="draft-banner">WRM_REVIEW_ONLY · Draft menu pending review</div>' if draft else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{restaurant} English Menu</title>
<style>
:root {{ color-scheme: light; --ink:#151515; --muted:#687076; --line:#E6E2D8; --accent:#0E7A8A; --paper:#FFFEFA; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:#F7F4EC; }}
header {{ padding:28px 18px 14px; background:var(--paper); border-bottom:1px solid var(--line); position:sticky; top:0; z-index:2; }}
h1 {{ margin:0; font-size:28px; letter-spacing:0; }}
.sub {{ margin-top:8px; color:var(--muted); line-height:1.45; }}
nav {{ display:flex; gap:8px; overflow-x:auto; padding:12px 18px; background:rgba(255,254,250,.92); position:sticky; top:102px; z-index:2; border-bottom:1px solid var(--line); }}
nav a {{ flex:0 0 auto; color:var(--accent); text-decoration:none; border:1px solid #BFE5EA; border-radius:999px; padding:8px 12px; font-weight:700; font-size:13px; background:#ECFEFF; }}
main {{ padding:18px; max-width:760px; margin:0 auto; }}
section {{ margin:0 0 28px; }}
h2 {{ font-size:13px; text-transform:uppercase; color:var(--muted); letter-spacing:.12em; margin:0 0 10px; }}
.dish-card {{ background:var(--paper); border:1px solid var(--line); border-radius:14px; padding:16px; margin-bottom:10px; box-shadow:0 6px 18px rgba(0,0,0,.04); }}
.dish-card h3 {{ margin:0; font-size:20px; }}
.jp {{ margin:4px 0 0; color:var(--muted); }}
.price {{ display:inline-block; margin-top:10px; font-weight:800; }}
.ingredients {{ color:#39434A; font-size:14px; line-height:1.5; }}
.review-gap,.draft-banner {{ background:#FFF7ED; color:#9A3412; border:1px solid #FDBA74; border-radius:10px; padding:9px 10px; font-size:13px; margin-top:10px; }}
.draft-banner {{ margin:12px 18px 0; }}
footer {{ padding:28px 18px 40px; color:var(--muted); text-align:center; }}
</style>
</head>
<body>
{draft_banner}
<header><h1>{restaurant}</h1><p class="sub">English menu for easy ordering. Please confirm availability and prices with staff.</p></header>
<nav>{section_nav}{'<a href="#ticket">Ordering Guide</a>' if ticket_html else ''}</nav>
<main>{"".join(cards)}{ticket_html}</main>
<footer>Hosted by WebRefurb · {html.escape(public_url)}</footer>
</body>
</html>
"""


def _render_qr_sign_html(source: dict[str, Any], *, public_url: str, draft: bool) -> str:
    restaurant = html.escape(str(source.get("restaurant_name") or "English Menu"))
    draft_banner = '<div class="draft">WRM_REVIEW_ONLY · QR sign draft</div>' if draft else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{restaurant} QR Sign</title>
<style>
:root {{ --ink:#151515; --muted:#687076; --line:#E6E2D8; --accent:#0E7A8A; --paper:#FFFEFA; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; min-height:100vh; display:grid; place-items:center; background:#F7F4EC; color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
.sign {{ width:min(92vw,720px); aspect-ratio:4/5; background:var(--paper); border:1px solid var(--line); border-radius:28px; padding:44px; display:grid; grid-template-rows:auto auto 1fr auto; gap:24px; text-align:center; box-shadow:0 18px 60px rgba(0,0,0,.08); }}
.brand {{ font-size:12px; letter-spacing:.22em; text-transform:uppercase; color:var(--accent); font-weight:800; }}
h1 {{ margin:0; font-size:clamp(42px,8vw,72px); line-height:.98; letter-spacing:0; }}
.qr-wrap {{ align-self:center; justify-self:center; width:min(72%,360px); aspect-ratio:1; border:14px solid #F7F4EC; border-radius:24px; display:grid; place-items:center; background:#fff; }}
.qr-wrap img {{ width:100%; height:100%; display:block; }}
.restaurant {{ color:var(--muted); font-size:clamp(18px,3vw,26px); font-weight:700; }}
.draft {{ position:fixed; top:18px; left:50%; transform:translateX(-50%); padding:9px 14px; border-radius:999px; border:1px solid #FDBA74; background:#FFF7ED; color:#9A3412; font-size:13px; font-weight:700; }}
@media print {{ body {{ background:#fff; }} .sign {{ box-shadow:none; width:100vw; min-height:100vh; border-radius:0; border:0; }} .draft {{ display:none; }} }}
</style>
</head>
<body>
{draft_banner}
<main class="sign">
  <div class="brand">WebRefurb</div>
  <h1>Scan QR for English Menu</h1>
  <div class="qr-wrap"><img src="qr.svg" alt="QR code for English menu"></div>
  <div class="restaurant">{restaurant}</div>
</main>
</body>
</html>
"""


def _render_qr_sign_svg(source: dict[str, Any], *, public_url: str, draft: bool) -> str:
    restaurant = html.escape(str(source.get("restaurant_name") or "English Menu"))
    draft_text = '<text x="400" y="45" text-anchor="middle" font-size="18" fill="#9A3412">WRM_REVIEW_ONLY · QR sign draft</text>' if draft else ""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1000" viewBox="0 0 800 1000" role="img" aria-label="Scan QR for English Menu">
<rect width="800" height="1000" fill="#F7F4EC"/>
{draft_text}
<rect x="58" y="72" width="684" height="856" rx="34" fill="#FFFEFA" stroke="#E6E2D8" stroke-width="2"/>
<text x="400" y="150" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" font-size="18" font-weight="800" letter-spacing="5" fill="#0E7A8A">WEBREFURB</text>
<text x="400" y="285" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" font-size="72" font-weight="900" fill="#151515">Scan QR for</text>
<text x="400" y="365" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" font-size="72" font-weight="900" fill="#151515">English Menu</text>
<rect x="222" y="438" width="356" height="356" rx="28" fill="#F7F4EC"/>
<image href="qr.svg" x="250" y="466" width="300" height="300"/>
<text x="400" y="865" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" font-size="30" font-weight="700" fill="#687076">{restaurant}</text>
<text x="400" y="905" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" font-size="18" fill="#687076">{html.escape(public_url)}</text>
</svg>
"""


def _render_qr_svg(url: str) -> str:
    try:
        import qrcode
    except ImportError as exc:
        raise QRMenuError("qrcode package is required to generate QR assets") from exc
    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(url)
    qr.make(fit=True)
    matrix: list[list[bool]] = qr.get_matrix()
    cell = 8
    size_px = len(matrix) * cell
    rects = []
    for y, row in enumerate(matrix):
        for x, filled in enumerate(row):
            if filled:
                rects.append(f'<rect x="{x * cell}" y="{y * cell}" width="{cell}" height="{cell}"/>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size_px} {size_px}" role="img" aria-label="QR code for {html.escape(url)}"><rect width="100%" height="100%" fill="#fff"/><g fill="#111">{"".join(rects)}</g></svg>\n'


def _qr_package_manifest(*, job: dict[str, Any], health: dict[str, Any], artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    manifest = package_manifest(
        package_key=PACKAGE_3_KEY,
        package_label=PACKAGE_3_LABEL,
        restaurant_name=str(job.get("restaurant_name") or ""),
        job_id=str(job.get("job_id") or ""),
        approval_timestamp=str(job.get("reviewed_at") or datetime.now(timezone.utc).isoformat()),
        artifacts=artifacts,
        source_input_references={
            "reply_id": job.get("reply_id", ""),
            "menu_id": job.get("menu_id", ""),
            "published_version_id": job.get("published_version_id", ""),
            "live_url": job.get("live_url", ""),
        },
        package_promise=_QR_PACKAGE_PROMISE,
        validation={"health": health},
    )
    manifest["menu_id"] = job.get("menu_id", "")
    manifest["published_version_id"] = job.get("published_version_id", "")
    manifest["live_url"] = job.get("live_url", "")
    manifest["health"] = health
    manifest["price_yen"] = PACKAGE_3_PRICE_YEN
    return manifest


def _manifest_for_public_dir(public_dir: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for filename in ("index.html", "menu.json", "qr.svg", "qr_sign.html", "qr_sign.svg"):
        path = public_dir / filename
        if path.exists():
            checksums[filename] = _sha256_file(path)
    return checksums


def _publish_live_pointer(
    *,
    docs_root: Path,
    menu_id: str,
    version_id: str,
    publish_manifest: dict[str, str],
    rollback: bool = False,
) -> None:
    menu_root = docs_root / "menus" / menu_id
    ensure_dir(menu_root)
    existing = _read_live_manifest(docs_root, menu_id)
    versions = list(existing.get("versions") or [])
    if version_id not in versions:
        versions.append(version_id)
    manifest = {
        "menu_id": menu_id,
        "current_version": version_id,
        "versions": versions,
        "checksums": publish_manifest,
        "status": "rollback_active" if rollback else "published",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(menu_root / "manifest.json", manifest)
    write_text(menu_root / "index.html", _live_shell_html(menu_id, version_id))


def _live_shell_html(menu_id: str, version_id: str) -> str:
    target = f"versions/{version_id}/"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="0; url={target}">
<title>Opening English Menu</title>
<script>location.replace({json.dumps(target)});</script>
</head>
<body><p><a href="{html.escape(target)}">Open menu</a></p></body>
</html>
"""


def _write_publish_manifest(state_root: Path, menu_id: str, version_id: str, checksums: dict[str, str]) -> None:
    write_json(
        state_root / "qr_menus" / menu_id / "versions" / version_id / "publish_manifest.json",
        {
            "menu_id": menu_id,
            "version_id": version_id,
            "checksums": checksums,
            "published_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def _mark_previous_versions_superseded(*, state_root: Path, menu_id: str, current_version: str) -> None:
    versions_root = state_root / "qr_menus" / menu_id / "versions"
    if not versions_root.exists():
        return
    for source_path in versions_root.glob("*/source.json"):
        if source_path.parent.name == current_version:
            continue
        data = json.loads(source_path.read_text(encoding="utf-8"))
        if data.get("status") == "published":
            data["status"] = "superseded"
            write_json(source_path, data)


def _read_live_manifest(docs_root: Path, menu_id: str) -> dict[str, Any]:
    path = docs_root / "menus" / menu_id / "manifest.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_state_source(state_root: Path, menu_id: str, version_id: str) -> dict[str, Any]:
    path = state_root / "qr_menus" / menu_id / "versions" / version_id / "source.json"
    if not path.exists():
        raise QRMenuError("QR source version not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _approved_qr_jobs_for_menu(*, state_root: Path, menu_id: str, version_id: str) -> list[dict[str, Any]]:
    jobs = []
    jobs_root = state_root / "qr_jobs"
    if not jobs_root.exists():
        return jobs
    for path in jobs_root.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("menu_id") != menu_id:
            continue
        if version_id and data.get("published_version_id") != version_id:
            continue
        if data.get("review_status") == "approved":
            jobs.append(data)
    return jobs


def _write_qr_job(state_root: Path, job: dict[str, Any]) -> None:
    write_json(state_root / "qr_jobs" / f"{job['job_id']}.json", job)


def _append_audit(state_root: Path, menu_id: str, action: str, detail: dict[str, Any]) -> None:
    path = state_root / "qr_menus" / menu_id / "audit_log.jsonl"
    ensure_dir(path.parent)
    record = {
        "at": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "detail": detail,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n")


def _draft_url(job_id: str) -> str:
    return f"{PUBLIC_BASE_URL}/menus/_drafts/{job_id}/"


def _sha256_file(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _completeness_report(source: dict[str, Any]) -> dict[str, Any]:
    missing_descriptions = []
    missing_ingredient_allergen = []
    for idx, item in enumerate(source.get("items") or []):
        label = item.get("japanese_name") or item.get("name") or f"item_{idx}"
        if not item.get("description"):
            missing_descriptions.append(label)
        if not _item_has_ingredient_allergen_content(item):
            missing_ingredient_allergen.append(label)
    return {
        "missing_descriptions": missing_descriptions,
        "missing_ingredient_allergen": missing_ingredient_allergen,
        "item_count": len(source.get("items") or []),
        "photo_count": len(source.get("photo_assets") or []),
    }


def _content_requirements(source: dict[str, Any]) -> dict[str, bool]:
    raw = source.get("content_requirements") or {}
    return {
        "descriptions_required": bool(raw.get("descriptions_required", _DEFAULT_CONTENT_REQUIREMENTS["descriptions_required"])),
        "ingredient_allergen_required": bool(raw.get("ingredient_allergen_required", _DEFAULT_CONTENT_REQUIREMENTS["ingredient_allergen_required"])),
    }


def _content_requirements_from_payload(payload: dict[str, Any]) -> dict[str, bool]:
    raw = payload.get("content_requirements") or payload.get("package_promise") or {}
    return {
        "descriptions_required": bool(raw.get("descriptions_required", _DEFAULT_CONTENT_REQUIREMENTS["descriptions_required"])),
        "ingredient_allergen_required": bool(raw.get("ingredient_allergen_required", _DEFAULT_CONTENT_REQUIREMENTS["ingredient_allergen_required"])),
    }


def _normalise_content_confirmation(
    value: Any,
    *,
    content_present: bool,
    content_kind: str,
    default_source: str,
) -> dict[str, Any]:
    if isinstance(value, dict):
        status = str(value.get("status") or "")
        if status not in _CONTENT_CONFIRMATION_STATUSES:
            status = "confirmed_by_owner" if value.get("confirmed") else ""
        if not status:
            status = "pending_owner_confirmation" if content_present else "not_provided"
        return {
            "kind": content_kind,
            "status": status,
            "source": str(value.get("source") or default_source or ""),
            "confirmed_by": str(value.get("confirmed_by") or ""),
            "confirmed_at": str(value.get("confirmed_at") or ""),
            "notes": str(value.get("notes") or ""),
        }
    if value is True:
        return _confirmed_content_record(
            kind=content_kind,
            source=default_source,
            confirmed_by="operator",
            confirmed_at="",
            notes="",
        )
    status = "pending_owner_confirmation" if content_present else "not_provided"
    return {
        "kind": content_kind,
        "status": status,
        "source": default_source,
        "confirmed_by": "",
        "confirmed_at": "",
        "notes": "",
    }


def _confirmed_content_record(*, kind: str, source: str, confirmed_by: str, confirmed_at: str, notes: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "status": "confirmed_by_owner",
        "source": source,
        "confirmed_by": confirmed_by,
        "confirmed_at": confirmed_at,
        "notes": notes,
    }


def _content_is_owner_confirmed(value: Any) -> bool:
    return isinstance(value, dict) and str(value.get("status") or "") == "confirmed_by_owner"


def _default_confirmation_source(source: dict[str, Any]) -> str:
    reply_id = str(source.get("reply_id") or "")
    if reply_id:
        return f"reply:{reply_id}"
    if source.get("photo_assets"):
        return "owner_menu_photos"
    return "owner_material"


def _item_has_ingredient_allergen_content(item: dict[str, Any]) -> bool:
    return bool((item.get("ingredients") or []) or (item.get("allergens") or []))


def _owner_confirmation_summary(source: dict[str, Any]) -> dict[str, Any]:
    description_required = 0
    description_confirmed = 0
    ingredient_allergen_required = 0
    ingredient_allergen_confirmed = 0
    for item in source.get("items") or []:
        if item.get("description"):
            description_required += 1
            if _content_is_owner_confirmed(item.get("description_confirmation")):
                description_confirmed += 1
        if _item_has_ingredient_allergen_content(item):
            ingredient_allergen_required += 1
            if _content_is_owner_confirmed(item.get("ingredient_allergen_confirmation")):
                ingredient_allergen_confirmed += 1
    return {
        "description_required_count": description_required,
        "description_confirmed_count": description_confirmed,
        "description_pending_count": max(description_required - description_confirmed, 0),
        "ingredient_allergen_required_count": ingredient_allergen_required,
        "ingredient_allergen_confirmed_count": ingredient_allergen_confirmed,
        "ingredient_allergen_pending_count": max(ingredient_allergen_required - ingredient_allergen_confirmed, 0),
    }
