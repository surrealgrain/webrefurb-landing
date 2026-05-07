"""WebRefurbMenu Operator Dashboard.

FastAPI application with sidebar navigation, lead management,
outreach generation, and custom build workflow.
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import json
import logging
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pipeline.business_name import business_name_is_suspicious
from pipeline.utils import load_project_env

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("webrefurb.dashboard")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(_handler)


def _log(action: str, detail: str = "", lead_id: str = "") -> None:
    """Log a dashboard action without exposing secrets."""
    msg = action
    if lead_id:
        msg += f" lead={lead_id}"
    if detail:
        msg += f" detail={_safe_log_detail(detail)}"
    logger.info(msg)


def _safe_log_detail(detail: str) -> str:
    """Keep logs useful without leaking credentials or full addresses."""
    cleaned = re.sub(r"[\w.+-]+@[\w.-]+\.\w+", "[email]", str(detail))
    cleaned = re.sub(
        r"(?i)(api[_-]?key|token|secret|password|authorization)=\S+",
        r"\1=[redacted]",
        cleaned,
    )
    return cleaned[:200]


def _valid_email(value: str) -> bool:
    """Conservative recipient validation for API callers."""
    _, address = parseaddr(value.strip())
    if not address or address != value.strip():
        return False
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", address) is not None


def _safe_upload_name(filename: str) -> str:
    """Strip path components from browser-supplied upload names."""
    safe = Path(filename).name.strip().replace("\x00", "")
    return safe or f"upload-{uuid.uuid4().hex[:8]}"


def _dashboard_email_preview_html(
    text_body: str,
    *,
    include_menu_image: bool,
    include_machine_image: bool,
    business_name: str = "",
    establishment_profile: str = "unknown",
) -> str:
    """Render the dashboard preview from the same HTML email builder."""
    from pipeline.email_html import build_pitch_email_html, LOGO_CID, MENU_CID, MACHINE_CID

    html_body = build_pitch_email_html(
        text_body=text_body,
        include_menu_image=include_menu_image,
        include_machine_image=include_machine_image,
        locale="ja",
    )
    # Replace CID references with dashboard-local SVG/PNG paths for in-browser display
    html_body = html_body.replace(f"cid:{LOGO_CID}", "/assets/webrefurb-email-logo.svg")
    if include_menu_image:
        menu_preview = _dashboard_inline_rendered_preview_data_uri(
            _menu_template_for_profile(establishment_profile),
            business_name=business_name,
            stem="menu",
        ) or _inline_preview_svg("English QR Menu demo", "Show Staff List")
        html_body = html_body.replace(f"cid:{MENU_CID}", menu_preview)
    if include_machine_image:
        html_body = html_body.replace(f"cid:{MACHINE_CID}", "")
    return html_body


def _menu_template_for_profile(establishment_profile: str) -> Path:
    templates = PROJECT_ROOT / "assets" / "templates"
    profile = str(establishment_profile or "").lower()
    if "izakaya" in profile:
        return templates / "qr_code_sign.html"
    return templates / "qr_code_sign.html"


_DASHBOARD_PREVIEW_CACHE_LIMIT = 12
_DASHBOARD_STATIC_PREVIEW_CACHE: dict[tuple[str, int, int], str] = {}
_DASHBOARD_RENDERED_PREVIEW_CACHE: dict[tuple[str, str, str, int, int], str] = {}


def _dashboard_static_preview_path(template_path: Path) -> Path | None:
    previews_dir = PROJECT_ROOT / "assets" / "templates" / "previews"
    candidates = (
        previews_dir / f"{template_path.stem}.png",
        template_path.with_name(f"{template_path.stem}_email_preview.jpg"),
        template_path.with_name(f"{template_path.stem}_email_preview.png"),
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _data_uri_for_preview_image(path: Path) -> str:
    stat = path.stat()
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    cached = _DASHBOARD_STATIC_PREVIEW_CACHE.get(key)
    if cached:
        return cached
    suffix = path.suffix.lower()
    media_type = "image/png" if suffix == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    data_uri = f"data:{media_type};base64,{encoded}"
    _DASHBOARD_STATIC_PREVIEW_CACHE[key] = data_uri
    while len(_DASHBOARD_STATIC_PREVIEW_CACHE) > _DASHBOARD_PREVIEW_CACHE_LIMIT:
        _DASHBOARD_STATIC_PREVIEW_CACHE.pop(next(iter(_DASHBOARD_STATIC_PREVIEW_CACHE)))
    return data_uri


def _dashboard_inline_rendered_preview_data_uri(template_path: Path, *, business_name: str, stem: str) -> str:
    """Render the actual dark menu template for dashboard preview images."""
    static_preview = _dashboard_static_preview_path(template_path)
    if static_preview:
        try:
            return _data_uri_for_preview_image(static_preview)
        except Exception:
            pass

    try:
        stat = template_path.stat()
        key = (
            str(template_path.resolve()),
            str(business_name or ""),
            str(stem or ""),
            stat.st_mtime_ns,
            stat.st_size,
        )
        cached = _DASHBOARD_RENDERED_PREVIEW_CACHE.get(key)
        if cached:
            return cached
        with tempfile.TemporaryDirectory(prefix="wrm-dashboard-preview-") as tmp_dir:
            source = _personalised_email_html(str(template_path), business_name, tmp_dir, stem)
            if not source:
                return ""
            jpeg = _render_dashboard_preview_jpeg(source)
            if not jpeg or not Path(jpeg).exists():
                return ""
            encoded = base64.b64encode(Path(jpeg).read_bytes()).decode("ascii")
            data_uri = f"data:image/jpeg;base64,{encoded}"
            _DASHBOARD_RENDERED_PREVIEW_CACHE[key] = data_uri
            while len(_DASHBOARD_RENDERED_PREVIEW_CACHE) > _DASHBOARD_PREVIEW_CACHE_LIMIT:
                _DASHBOARD_RENDERED_PREVIEW_CACHE.pop(next(iter(_DASHBOARD_RENDERED_PREVIEW_CACHE)))
            return data_uri
    except Exception:
        return ""


def _render_dashboard_preview_jpeg(source: str | Path) -> Path | None:
    """Run Playwright rendering outside FastAPI's event-loop thread."""
    from pipeline.email_html import _ensure_menu_jpeg

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _ensure_menu_jpeg(source)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_ensure_menu_jpeg, source)
        return future.result(timeout=20)


def _safe_draft_assets_for_record(record: dict[str, Any], requested_assets: Any) -> list[str]:
    """Prevent stale browser state from re-saving legacy sample assets."""
    from pipeline.state_audit import expected_dark_assets

    expected = expected_dark_assets(record)
    requested = [str(asset) for asset in requested_assets or []]
    if not requested:
        return []
    if all(asset in expected for asset in requested):
        return requested
    return expected


def _test_fixture_label_for_record(record: dict[str, Any]) -> str:
    """Return a dashboard-only label for records that must never look live."""
    lead_id = str(record.get("lead_id") or "").strip().lower()
    business_name = str(record.get("business_name") or "").strip().lower()
    lock_reason = str(record.get("business_name_lock_reason") or "").strip().lower()

    if record.get("smoke_rehearsal_only") is True:
        return "SMOKE TEST - NO REAL OUTREACH"
    if lead_id.startswith("wrm-qa-") or business_name.startswith("qa ") or "fixture" in lock_reason:
        return "TEST FIXTURE - NOT REAL OUTREACH"
    return ""


def _draft_claims_attached_sample(*values: str) -> bool:
    text = "\n".join(str(value or "") for value in values).lower()
    markers = (
        "添付のサンプル",
        "添付ファイル",
        "attached sample",
        "attached file",
        "reference file",
        "included file",
    )
    return any(marker in text for marker in markers)


def _inline_preview_svg(title: str, label: str) -> str:
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="760" viewBox="0 0 1200 760">
<rect width="1200" height="760" fill="#0f0d0b"/>
<rect x="64" y="64" width="1072" height="632" rx="18" fill="#1c1917" stroke="#3f3a34" stroke-width="2"/>
<text x="96" y="136" fill="#f0ebe3" font-family="Arial, sans-serif" font-size="52" font-weight="700">{title}</text>
<text x="96" y="190" fill="#c53d43" font-family="Arial, sans-serif" font-size="28" font-weight="700">{label}</text>
<rect x="96" y="250" width="460" height="64" rx="8" fill="#292524"/>
<rect x="96" y="340" width="460" height="64" rx="8" fill="#292524"/>
<rect x="96" y="430" width="460" height="64" rx="8" fill="#292524"/>
<rect x="640" y="250" width="360" height="64" rx="8" fill="#292524"/>
<rect x="640" y="340" width="360" height="64" rx="8" fill="#292524"/>
<rect x="640" y="430" width="360" height="64" rx="8" fill="#292524"/>
<text x="96" y="610" fill="#a8a29e" font-family="Arial, sans-serif" font-size="28">Illustrative sample only. Production uses owner-provided photos.</text>
</svg>"""
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _normalise_body(text: str) -> str:
    return "\n\n".join(part.strip() for part in text.strip().split("\n\n") if part.strip())


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DASHBOARD_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = DASHBOARD_ROOT.parent
STATE_ROOT = Path(os.environ.get("WEBREFURB_STATE_ROOT", PROJECT_ROOT / "state")).resolve()
QR_DOCS_ROOT = PROJECT_ROOT / "docs"


def _dashboard_search_category_meta() -> dict[str, dict[str, str]]:
    from pipeline.search_scope import search_category_metadata

    return search_category_metadata()

# Load .env
load_project_env(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(title="WebRefurbMenu Dashboard", version="1.0.0")

templates = Jinja2Templates(directory=str(DASHBOARD_ROOT / "templates"))

# Static files
static_dir = DASHBOARD_ROOT / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Serve state files (generated PDFs, uploads)
uploads_dir = STATE_ROOT / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

# Serve only the dashboard logo asset. Do not mount PROJECT_ROOT here; that
# would expose .env, state files, and source paths from a local dashboard URL.
@app.get("/assets/webrefurb-email-logo.svg")
async def dashboard_email_logo():
    logo = PROJECT_ROOT / "pipeline" / "webrefurb_email_logo.svg"
    if not logo.exists():
        raise HTTPException(status_code=404, detail="Logo asset not found")
    return FileResponse(str(logo), media_type="image/svg+xml")


@app.get("/menus/{asset_path:path}", include_in_schema=False)
async def dashboard_qr_menu_asset(asset_path: str):
    """Serve generated QR menu draft/live files during local dashboard review."""
    root = (QR_DOCS_ROOT / "menus").resolve()
    path = (root / asset_path).resolve()
    if path.is_dir():
        path = path / "index.html"
    try:
        path.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=404, detail="QR menu asset not found")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="QR menu asset not found")
    return FileResponse(str(path))

# ---------------------------------------------------------------------------
# Build job tracking (in-memory)
# ---------------------------------------------------------------------------
_build_jobs: dict[str, dict[str, Any]] = {}

BLOCKED_SEND_STATUSES = {
    "sent",
    "replied",
    "converted",
    "bounced",
    "invalid",
    "skipped",
    "do_not_contact",
    "rejected",
    "needs_review",
    "contacted_form",
}

BLOCKED_REGENERATE_STATUSES = BLOCKED_SEND_STATUSES - {"rejected", "needs_review"}

MANUAL_CONTACT_STATUS_BY_ROUTE = {
    "contact_form": "contacted_form",
}

ESTABLISHMENT_PROFILE_LABELS = {
    "unknown": "Manual Review",
    "ramen": "Ramen",
    "ramen_only": "Ramen",
    "ramen_with_drinks": "Ramen",
    "ramen_ticket_machine": "Ramen",
    "ramen_with_sides_add_ons": "Ramen",
    "soba_only": "Skip",
    "izakaya": "Izakaya",
    "izakaya_food_and_drinks": "Izakaya",
    "izakaya_drink_heavy": "Izakaya",
    "izakaya_course_heavy": "Izakaya",
    "izakaya_yakitori_kushiyaki": "Izakaya",
    "izakaya_kushiage": "Izakaya",
    "izakaya_seafood_sake_oden": "Izakaya",
    "izakaya_tachinomi": "Izakaya",
    "izakaya_robatayaki": "Izakaya",
    "skip": "Skip",
}

LEAD_QUEUE_QUALITY_ORDER = {"v1_clean": 0, "high": 1, "medium": 2, "low": 3}
LEAD_QUEUE_CITY_ORDER = {"Tokyo": 0, "Osaka": 1, "Sapporo": 2, "Fukuoka": 3, "Kyoto": 4}
LEAD_QUEUE_VERIFICATION_ORDER = {"verified": 0, "needs_review": 1, "rejected": 2}
LEAD_QUEUE_PITCH_ORDER = {
    "pitch_ready": 0,
    "pitch_pack_ready_no_send": 1,
    "review_blocked": 2,
    "needs_name_review": 3,
    "needs_email_review": 4,
    "needs_scope_review": 5,
    "rejected": 6,
}

QUALITY_TIER_LABELS = {
    "v1_clean": "V1 Clean",
    "high": "High",
    "medium": "Medium Review",
    "low": "Low Review",
}

VERIFICATION_STATUS_LABELS = {
    "verified": "Verified",
    "needs_review": "Needs Review",
    "rejected": "Rejected",
}

EMAIL_STATUS_LABELS = {
    "verified": "Email Verified",
    "needs_review": "Email Review",
    "rejected": "Email Rejected",
}

NAME_STATUS_LABELS = {
    "two_source_verified": "Name 2x Verified",
    "single_source": "Name Single Source",
    "manually_accepted": "Name Accepted",
    "needs_review": "Name Review",
    "rejected": "Name Rejected",
}

SOURCE_STRENGTH_LABELS = {
    "official_site": "Official Site",
    "restaurant_owned_page": "Restaurant-Owned Page",
    "directory": "Directory",
    "weak_source": "Weak Source",
}

PITCH_READINESS_LABELS = {
    "pitch_ready": "Pitch Ready",
    "pitch_pack_ready_no_send": "Pitch Pack Ready",
    "review_blocked": "Review Blocked",
    "needs_scope_review": "Needs Scope Review",
    "needs_name_review": "Needs Name Review",
    "needs_email_review": "Needs Email Review",
    "rejected": "Rejected",
}

PITCH_CARD_LABELS = {
    "reviewable": "Reviewable",
    "needs_email_review": "Needs Email Review",
    "needs_name_review": "Needs Name Review",
    "needs_scope_review": "Needs Scope Review",
    "hard_blocked": "Hard Blocked",
    "unsupported_route": "Unsupported Route",
}

PITCH_CARD_ORDER = {
    "reviewable": 0,
    "needs_email_review": 1,
    "needs_name_review": 2,
    "needs_scope_review": 3,
    "unsupported_route": 4,
    "hard_blocked": 5,
}

LEAD_REVIEW_OUTCOME_LABELS = {
    "hold": "Hold",
    "needs_more_info": "Needs More Info",
    "pitch_pack_ready": "Pitch Pack Ready",
    "reject": "Reject",
}

LEAD_REVIEW_STATUS_BY_OUTCOME = {
    "hold": "held",
    "needs_more_info": "needs_more_info",
    "pitch_pack_ready": "pitch_pack_ready_no_send",
    "reject": "rejected",
}

MENU_TYPE_LABELS = {
    "ramen": "Ramen",
    "tsukemen": "Tsukemen",
    "abura_soba": "Abura Soba",
    "mazesoba": "Mazesoba",
    "tantanmen": "Tantanmen",
    "chuka_soba": "Chuka Soba",
    "izakaya": "Izakaya",
}


def _lead_queue_sort_key(lead: dict[str, Any]) -> tuple[Any, ...]:
    return (
        PITCH_CARD_ORDER.get(str(lead.get("pitch_card_status") or "").lower(), 99),
        LEAD_QUEUE_QUALITY_ORDER.get(str(lead.get("quality_tier") or "").lower(), 99),
        LEAD_QUEUE_VERIFICATION_ORDER.get(str(lead.get("verification_status") or "").lower(), 99),
        LEAD_QUEUE_PITCH_ORDER.get(str(lead.get("pitch_readiness_status") or "").lower(), 99),
        LEAD_QUEUE_CITY_ORDER.get(str(lead.get("city") or ""), 99),
        str(lead.get("establishment_profile") or ""),
        str(lead.get("business_name") or ""),
        str(lead.get("lead_id") or ""),
    )


def _normalise_contact_label(contact: dict[str, Any] | None) -> str:
    if not contact:
        return "No contact route"
    contact_type = str(contact.get("type") or "").replace("_", " ").title()
    value = str(contact.get("value") or "").strip()
    if contact_type == "Walk In":
        return "Walk-in"
    if contact_type == "Contact Form":
        return "Contact Form"
    if contact_type == "Email" and value:
        return value
    if value:
        return value
    return contact_type


def _lead_contacts(lead: dict[str, Any]) -> list[dict[str, Any]]:
    from pipeline.record import normalise_lead_contacts

    return normalise_lead_contacts(lead)


def _lead_primary_contact(lead: dict[str, Any]) -> dict[str, Any] | None:
    from pipeline.record import get_primary_contact

    return get_primary_contact(lead)


def _has_supported_contact_route(lead: dict[str, Any]) -> bool:
    from pipeline.record import has_supported_contact_route

    return has_supported_contact_route(lead)


def _has_business_email(lead: dict[str, Any]) -> bool:
    """Current send flow still requires a valid e-mail route."""
    from pipeline.record import get_primary_email_contact

    email_contact = get_primary_email_contact(lead)
    if not email_contact:
        return False
    return _valid_email(str(email_contact.get("value") or ""))


def _manual_contact_status(contact_type: str) -> str:
    return MANUAL_CONTACT_STATUS_BY_ROUTE.get(contact_type, "")


def _establishment_profile_label(profile: str) -> str:
    return ESTABLISHMENT_PROFILE_LABELS.get(profile, profile.replace("_", " ").title() if profile else "Manual Review")


def _dashboard_state_label(value: Any, *, default: str = "Unknown") -> str:
    text = str(value or "").strip()
    if not text:
        return default
    return text.replace("_", " ").title()


def _restaurant_email_queue_record(lead: dict[str, Any]) -> bool:
    lead_id = str(lead.get("lead_id") or "")
    source_query = str(lead.get("source_query") or "")
    source_file = str(lead.get("source_file") or "")
    return (
        lead_id.startswith("wrm-email-")
        or source_query == "restaurant_email_import"
        or "restaurant_email_leads" in source_file
    )


def _label_from_map(value: Any, labels: dict[str, str], *, default: str = "Unknown") -> str:
    key = str(value or "").strip()
    if not key:
        return default
    return labels.get(key, _dashboard_state_label(key, default=default))


def _effective_establishment_profile(lead: dict[str, Any]) -> dict[str, Any]:
    override = str(lead.get("establishment_profile_override") or "").strip()
    stored = str(lead.get("establishment_profile") or "").strip() or "unknown"
    effective = override or stored or "unknown"
    mode = "operator_override" if override else "evidence"
    confidence = "operator" if override else str(lead.get("establishment_profile_confidence") or "low")
    note = str(lead.get("establishment_profile_override_note") or "").strip()
    return {
        "effective": effective,
        "label": _establishment_profile_label(effective),
        "mode": mode,
        "confidence": confidence,
        "evidence": list(lead.get("establishment_profile_evidence") or []),
        "source_urls": list(lead.get("establishment_profile_source_urls") or []),
        "override": override,
        "override_note": note,
        "override_at": lead.get("establishment_profile_override_at"),
    }


def _prepare_lead_for_dashboard(lead: dict[str, Any]) -> dict[str, Any]:
    from pipeline.lead_dossier import ensure_lead_dossier
    from pipeline.constants import PACKAGE_REGISTRY
    from pipeline.pitch_cards import apply_pitch_card_state

    lead = ensure_lead_dossier(lead)
    lead = apply_pitch_card_state(lead)
    prepared = dict(lead)
    contacts = _lead_contacts(lead)
    primary_contact = _lead_primary_contact(lead)
    profile = _effective_establishment_profile(lead)
    prepared["contacts"] = contacts
    prepared["primary_contact"] = primary_contact
    prepared["has_supported_contact_route"] = _has_supported_contact_route(lead)
    prepared["can_send_email"] = _has_business_email(lead)
    prepared["primary_contact_label"] = _normalise_contact_label(primary_contact)
    prepared["primary_contact_type"] = str((primary_contact or {}).get("type") or "")
    prepared["establishment_profile_effective"] = profile["effective"]
    prepared["establishment_profile_label"] = profile["label"]
    prepared["establishment_profile_mode"] = profile["mode"]
    prepared["establishment_profile_confidence"] = profile["confidence"]
    prepared["establishment_profile_evidence"] = profile["evidence"]
    prepared["establishment_profile_source_urls"] = profile["source_urls"]
    prepared["establishment_profile_override"] = profile["override"]
    prepared["establishment_profile_override_note"] = profile["override_note"]
    prepared["launch_readiness_status"] = lead.get("launch_readiness_status", "manual_review")
    prepared["launch_readiness_reasons"] = list(lead.get("launch_readiness_reasons") or [])
    prepared["operator_state"] = lead.get("operator_state", "review")
    prepared["operator_reason"] = lead.get("operator_reason", "Review this record before outreach.")
    prepared["contact_policy_evidence"] = lead.get("contact_policy_evidence") or {}
    prepared["lead_evidence_dossier"] = lead.get("lead_evidence_dossier") or {}
    prepared["proof_items"] = lead.get("proof_items") or prepared["lead_evidence_dossier"].get("proof_items") or []
    prepared["proof_strength_label"] = _dashboard_state_label(
        prepared["lead_evidence_dossier"].get("proof_strength"),
        default="No Proof",
    )
    prepared["ticket_machine_state_label"] = _dashboard_state_label(lead.get("ticket_machine_state") or prepared["lead_evidence_dossier"].get("ticket_machine_state"))
    prepared["english_menu_state_label"] = _dashboard_state_label(lead.get("english_menu_state") or prepared["lead_evidence_dossier"].get("english_menu_state"))
    prepared["lead_category_label"] = _dashboard_state_label(lead.get("lead_category"), default="Unclassified")
    prepared["quality_tier_label"] = _label_from_map(lead.get("quality_tier"), QUALITY_TIER_LABELS, default="Unscored")
    prepared["menu_type_label"] = _label_from_map(lead.get("menu_type"), MENU_TYPE_LABELS, default="Unclassified")
    prepared["verification_status_label"] = _label_from_map(lead.get("verification_status"), VERIFICATION_STATUS_LABELS, default="Unverified")
    prepared["email_verification_status_label"] = _label_from_map(lead.get("email_verification_status"), EMAIL_STATUS_LABELS, default="Email Unchecked")
    prepared["name_verification_status_label"] = _label_from_map(lead.get("name_verification_status"), NAME_STATUS_LABELS, default="Name Unchecked")
    prepared["source_strength_label"] = _label_from_map(lead.get("source_strength"), SOURCE_STRENGTH_LABELS, default="Source Unchecked")
    prepared["pitch_readiness_label"] = _label_from_map(lead.get("pitch_readiness_status"), PITCH_READINESS_LABELS, default="Review Blocked")
    prepared["pitch_card_label"] = _label_from_map(lead.get("pitch_card_status"), PITCH_CARD_LABELS, default="Review Blocked")
    prepared["pitch_card_reasons"] = list(lead.get("pitch_card_reasons") or [])
    prepared["pitch_card_openable"] = bool(lead.get("pitch_card_openable"))
    prepared["operator_review_outcome_label"] = _label_from_map(lead.get("operator_review_outcome"), LEAD_REVIEW_OUTCOME_LABELS, default="Not Reviewed")
    prepared["review_status_label"] = _dashboard_state_label(lead.get("review_status"), default="Pending")
    prepared["send_readiness"] = _send_readiness_for_record(lead)
    audit_validation = _validate_tailoring_audit(lead)
    prepared["final_send_check"] = {
        "status": "passed" if audit_validation["valid"] else str(audit_validation["reason"] or "not_checked"),
        "checked_at": lead.get("send_ready_checked_at", ""),
        "tailoring_audit": lead.get("tailoring_audit") or {},
    }
    package_key = str(lead.get("recommended_primary_package") or "")
    package = PACKAGE_REGISTRY.get(package_key, {})
    prepared["recommended_package_label"] = package.get("label") or ("Custom quote" if package_key == "custom_quote" else package_key)
    prepared["package_recommendation_reason"] = str(lead.get("package_recommendation_reason") or "")
    prepared["custom_quote_reason"] = str(lead.get("custom_quote_reason") or "")
    return prepared


def _refresh_operator_lead(record: dict[str, Any]) -> dict[str, Any]:
    from pipeline.lead_dossier import ensure_lead_dossier

    return ensure_lead_dossier(record)


def _build_evidence_audit(classification: dict[str, Any]) -> dict[str, Any]:
    """Extract audit-safe fields from an evidence classification."""
    from datetime import datetime, timezone

    return {
        "evidence_classifier_version": "1.0",
        "template_renderer_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selected_template": classification.get("selected_template", ""),
        "selected_template_reason": classification.get("selected_template_reason", ""),
        "allowed_claims": classification.get("allowed_claims", []),
        "blocked_claims": classification.get("blocked_claims", []),
        "evidence_notes": {
            "menu": classification.get("public_menu_evidence_notes", ""),
            "ticket_machine": classification.get("ticket_machine_evidence_notes", ""),
            "nomihodai": classification.get("nomihodai_evidence_notes", ""),
            "course": classification.get("course_evidence_notes", ""),
        },
        "public_contact_source": classification.get("public_contact_source", ""),
        "human_review_required": classification.get("human_review_required", False),
        "skip_reason": (
            classification.get("selected_template_reason", "")
            if classification.get("selected_template") == "skip"
            else ""
        ),
    }


def _missing_evidence_value(value: Any) -> bool:
    return value is None or value == "" or value == []


def _seed_evidence_value(payload: dict[str, Any], key: str, value: Any) -> None:
    if key not in payload or _missing_evidence_value(payload.get(key)):
        payload[key] = value


def _legacy_observed_menu_topics(*, classification: str, profile: str) -> list[str]:
    topics: list[str] = []
    if profile.startswith("izakaya"):
        topics.extend(["food_items", "drink_items"])
    else:
        topics.extend(["ramen_types", "toppings", "set_items"])

    if classification in {"menu_and_machine", "machine_only"} or profile == "ramen_ticket_machine":
        topics.extend(["ticket_machine_buttons", "purchase_steps"])

    return list(dict.fromkeys(topics))


def _evidence_classifier_payload(
    record: dict[str, Any],
    *,
    business_name: str,
    classification: str,
    profile: str,
) -> dict[str, Any]:
    """Bridge verified legacy dashboard fields into the evidence classifier."""
    payload = dict(record)
    _seed_evidence_value(payload, "business_name", business_name)

    primary_category = str(payload.get("primary_category_v1") or "").lower()
    if primary_category in {"ramen", "izakaya"}:
        restaurant_type = primary_category
    elif profile.startswith("izakaya"):
        restaurant_type = "izakaya"
    elif profile.startswith("ramen"):
        restaurant_type = "ramen"
    else:
        restaurant_type = "unknown"
    if restaurant_type != "unknown":
        _seed_evidence_value(payload, "restaurant_type", restaurant_type)
        _seed_evidence_value(payload, "restaurant_type_confidence", 0.85)

    if bool(record.get("menu_evidence_found")):
        _seed_evidence_value(payload, "public_menu_found", True)
        _seed_evidence_value(payload, "public_menu_source_type", "other")
        _seed_evidence_value(payload, "menu_readability_confidence", 0.8)
        _seed_evidence_value(payload, "public_menu_evidence_notes", "Verified menu_evidence_found legacy field")

    if bool(record.get("machine_evidence_found")):
        _seed_evidence_value(payload, "ticket_machine_confidence", 0.9)
        _seed_evidence_value(payload, "ticket_machine_evidence_type", "explicit_text")
        _seed_evidence_value(payload, "ticket_machine_evidence_notes", "Verified machine_evidence_found legacy field")

    if _missing_evidence_value(payload.get("observed_menu_topics")):
        payload["observed_menu_topics"] = _legacy_observed_menu_topics(
            classification=classification,
            profile=profile,
        )

    return payload


# Claim keywords that require evidence-gated permission.
_CLAIM_VALIDATIONS = [
    ("券売機", "mention_ticket_machine"),
    ("食券", "mention_ticket_machine"),
    ("トッピング", "mention_toppings"),
    ("セット内容", "mention_set_items"),
    ("公開されているメニュー情報をもとに", "offer_sample_from_public_menu"),
]
_DISALLOWED_FIRST_CONTACT_TERMS = ("飲み放題", "コース")


def _validate_email_claims(email_body: str, evidence_audit: dict[str, Any]) -> None:
    """Scan the rendered Japanese email body for unsupported risky claims."""
    if not email_body:
        return

    allowed = set(evidence_audit.get("allowed_claims") or [])
    for keyword in _DISALLOWED_FIRST_CONTACT_TERMS:
        if keyword in email_body:
            raise ValueError(
                f"Send-time claim validation failed: '{keyword}' found in email "
                "but active first-contact copy is generic QR-first copy only"
            )

    for keyword, required_claim in _CLAIM_VALIDATIONS:
        if keyword in email_body and required_claim not in allowed:
            raise ValueError(
                f"Send-time claim validation failed: '{keyword}' found in email "
                f"but '{required_claim}' not in allowed_claims"
            )

    for forbidden in ("BUSINESS_ADDRESS", "所在地", "住所"):
        if forbidden in email_body:
            raise ValueError(
                f"Send-time claim validation failed: '{forbidden}' placeholder found"
            )


def _evidence_batch_skip_reason(record: dict[str, Any]) -> str:
    evidence_audit = record.get("evidence_audit") or {}
    if not evidence_audit.get("selected_template"):
        return "evidence_audit_missing"
    if evidence_audit.get("selected_template") == "skip":
        return f"evidence_skip:{evidence_audit.get('skip_reason') or 'unknown'}"
    if evidence_audit.get("human_review_required"):
        return "evidence_human_review_required"
    return ""


def _ensure_evidence_audit_for_batch_record(record: dict[str, Any]) -> dict[str, Any]:
    if (record.get("evidence_audit") or {}).get("selected_template"):
        return record

    from pipeline.evidence_classifier import classify_lead
    from pipeline.models import QualificationResult
    from pipeline.outreach import build_evidence_gated_email, classify_business
    from pipeline.record import authoritative_business_name, persist_lead_record

    business_name = authoritative_business_name(record)
    q = QualificationResult(
        lead=record.get("lead") is True,
        rejection_reason=record.get("rejection_reason"),
        business_name=business_name,
        menu_evidence_found=record.get("menu_evidence_found", True),
        machine_evidence_found=record.get("machine_evidence_found", False),
    )
    classification = str(record.get("outreach_classification") or classify_business(q))
    profile = _effective_establishment_profile(record)
    evidence_payload = _evidence_classifier_payload(
        record,
        business_name=business_name,
        classification=classification,
        profile=profile["effective"],
    )
    classification_obj = classify_lead(evidence_payload)
    record["evidence_audit"] = _build_evidence_audit(classification_obj)
    if build_evidence_gated_email(classification_obj) is None:
        record["outreach_status"] = "evidence_blocked"
    persist_lead_record(record, state_root=STATE_ROOT)
    return record


def _dashboard_card_counts(leads: list[dict[str, Any]]) -> dict[str, int]:
    from pipeline.pitch_cards import pitch_card_counts

    return pitch_card_counts(leads)


def _compute_search_coverage(leads: list[dict[str, Any]]) -> dict[str, Any]:
    """Count pitch-ready leads by city, category, and city×category cross-tab."""
    from collections import Counter

    city_counts: Counter = Counter()
    category_counts: Counter = Counter()
    cross: dict[str, Counter] = {}

    for lead in leads:
        if lead.get("launch_readiness_status") != "ready_for_outreach":
            continue
        city = str(lead.get("city") or "unknown")
        cat = str(lead.get("primary_category_v1") or lead.get("category") or "other")
        city_counts[city] += 1
        category_counts[cat] += 1
        cross.setdefault(city, Counter())[cat] += 1

    # Convert Counter objects to plain dicts for JSON serialisation
    return {
        "total": sum(city_counts.values()),
        "city": dict(city_counts),
        "category": dict(category_counts),
        "cross": {city: dict(cats) for city, cats in cross.items()},
    }


def _is_test_recipient_email(value: str) -> bool:
    """Only Chris's inbox is allowed for test sends."""
    normalised = str(value or "").strip().lower()
    if not normalised:
        return False
    return normalised == "chris@webrefurb.com"


def _is_lead_business_recipient(lead_id: str, to_email: str) -> bool:
    """True only when the recipient is the restaurant email saved on the lead."""
    from pipeline.record import load_lead

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        return False
    business_email = str(record.get("email") or "").strip().lower()
    normalised_to = str(to_email or "").strip().lower()
    return bool(business_email) and normalised_to == business_email and _valid_email(normalised_to)


FORBIDDEN_FINAL_CHECK_TERMS = (
    " ai ",
    "artificial intelligence",
    "automation",
    "automated",
    "scraping",
    "scraped",
    "internal tool",
    "crawler",
    "classifier",
    "qr ordering system",
    "ordering system",
    "online ordering",
    " pos ",
    "checkout",
    "place order",
    "submit order",
    "package_1_remote_30k",
    "package_2_printed_delivered_45k",
    "package_3_qr_menu_65k",
    "llm",
    "gpt",
)
FINAL_CHECK_PRICE_RE = re.compile(r"(?:¥|JPY\s*)(30,?000|45,?000|65,?000)|(?:30,?000|45,?000|65,?000)\s*円", re.I)


def _sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_json_hash(payload: Any) -> str:
    from pipeline.utils import sha256_text

    return sha256_text(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def _normalised_final_check_assets(assets: list[str] | None, record: dict[str, Any], *, classification: str, profile: str) -> list[str]:
    from pipeline.outreach import select_outreach_assets

    if assets is not None:
        return [str(asset) for asset in assets]
    stored = record.get("outreach_assets_selected")
    if stored:
        return [str(asset) for asset in stored]
    return [str(path) for path in select_outreach_assets(classification, establishment_profile=profile)]


def _eligible_proof_items(record: dict[str, Any]) -> list[dict[str, str]]:
    proof_items = record.get("proof_items") or (record.get("lead_evidence_dossier") or {}).get("proof_items") or []
    selected: list[dict[str, str]] = []
    for idx, item in enumerate(proof_items):
        if not isinstance(item, dict) or item.get("customer_preview_eligible") is not True:
            continue
        selected.append({
            "proof_item_id": str(item.get("proof_item_id") or item.get("id") or f"proof-{idx}"),
            "source_type": str(item.get("source_type") or ""),
            "url": str(item.get("url") or ""),
            "snippet": str(item.get("snippet") or ""),
            "screenshot_path": str(item.get("screenshot_path") or ""),
        })
    return selected


def _expected_final_check_images(
    record: dict[str, Any],
    *,
    classification: str,
    profile: str,
    include_machine_image: bool | None,
) -> dict[str, bool]:
    from pipeline.outreach import build_outreach_email
    from pipeline.record import authoritative_business_name

    default_email = build_outreach_email(
        business_name=authoritative_business_name(record),
        classification=classification,
        establishment_profile=profile,
        include_inperson_line=record.get("outreach_include_inperson", True),
        city=record.get("city", ""),
        lead_dossier=record.get("lead_evidence_dossier") or {},
    )
    expected_machine = bool(default_email.get("include_machine_image"))
    resolved_machine = record.get("outreach_include_machine_image", expected_machine) if include_machine_image is None else bool(include_machine_image)
    return {
        "include_menu_image": bool(default_email.get("include_menu_image")),
        "include_machine_image": bool(resolved_machine),
    }


def _final_check_render_dir(lead_id: str) -> Path:
    return STATE_ROOT / "final_checks" / Path(lead_id).name


def _render_final_check_previews(
    record: dict[str, Any],
    *,
    business_name: str,
    profile: str,
    include_menu_image: bool,
    include_machine_image: bool,
) -> list[dict[str, str]]:
    """Materialize the exact inline HTML used for the generic sample seal check."""
    lead_id = str(record.get("lead_id") or "lead")
    output_dir = _final_check_render_dir(lead_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    previews: list[dict[str, str]] = []
    preview_sources: list[tuple[str, Path]] = []
    if include_menu_image:
        preview_sources.append(("menu", _menu_template_for_profile(profile)))

    for kind, source in preview_sources:
        with tempfile.TemporaryDirectory(prefix=f"wrm-final-check-{kind}-") as tmp_dir:
            rendered = _personalised_email_html(str(source), business_name, tmp_dir, kind)
            if not rendered:
                previews.append({
                    "kind": kind,
                    "source_path": str(source),
                    "path": "",
                    "sha256": "",
                    "status": "missing_source",
                })
                continue
            destination = output_dir / f"{kind}.html"
            rendered_text = Path(rendered).read_text(encoding="utf-8")
            destination.write_text(rendered_text, encoding="utf-8")
            previews.append({
                "kind": kind,
                "source_path": str(source),
                "path": str(destination),
                "sha256": _sha256_file(destination),
                "status": "rendered",
            })
    return previews


def _tailoring_audit_inputs(
    record: dict[str, Any],
    *,
    recipient: str = "",
    subject: str = "",
    body: str = "",
    assets: list[str] | None = None,
    include_machine_image: bool | None = None,
    rendered_previews: list[dict[str, str]] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    from pipeline.models import QualificationResult
    from pipeline.outreach import classify_business
    from pipeline.record import authoritative_business_name, get_primary_email_contact

    lead_id = str(record.get("lead_id") or "")
    business_name = authoritative_business_name(record)
    q = QualificationResult(
        lead=record.get("lead") is True,
        rejection_reason=record.get("rejection_reason"),
        business_name=business_name,
        menu_evidence_found=record.get("menu_evidence_found", True),
        machine_evidence_found=record.get("machine_evidence_found", False),
    )
    classification = str(record.get("outreach_classification") or classify_business(q))
    profile = _effective_establishment_profile(record)["effective"]
    email_contact = get_primary_email_contact(record)
    resolved_recipient = str(recipient or (email_contact or {}).get("value") or record.get("email") or "").strip().lower()
    resolved_subject = str(subject or record.get("outreach_draft_subject") or "").strip()
    resolved_body = str(body or record.get("outreach_draft_body") or "").strip()
    resolved_assets = _normalised_final_check_assets(assets, record, classification=classification, profile=profile)
    image_flags = _expected_final_check_images(
        record,
        classification=classification,
        profile=profile,
        include_machine_image=include_machine_image,
    )
    resolved_machine = image_flags["include_machine_image"]

    asset_hashes: list[dict[str, str]] = []
    issues: list[str] = []
    for path_text in resolved_assets:
        path = Path(path_text)
        if not path.exists():
            issues.append(f"asset_missing:{path_text}")
            asset_hashes.append({"path": path_text, "sha256": ""})
            continue
        asset_hashes.append({"path": path_text, "sha256": _sha256_file(path)})

    if rendered_previews is None:
        rendered_previews = list((record.get("tailoring_audit") or {}).get("rendered_previews") or [])
    preview_hashes: list[dict[str, str]] = []
    for preview in rendered_previews or []:
        path_text = str(preview.get("path") or "")
        path = Path(path_text) if path_text else None
        if not path or not path.exists():
            issues.append(f"rendered_preview_missing:{preview.get('kind') or 'unknown'}")
            preview_hashes.append({
                "kind": str(preview.get("kind") or ""),
                "path": path_text,
                "source_path": str(preview.get("source_path") or ""),
                "sha256": "",
            })
            continue
        preview_hashes.append({
            "kind": str(preview.get("kind") or ""),
            "path": path_text,
            "source_path": str(preview.get("source_path") or ""),
            "sha256": _sha256_file(path),
        })

    expected_preview_kinds: set[str] = set()
    if image_flags["include_menu_image"]:
        expected_preview_kinds.add("menu")
    if resolved_machine:
        expected_preview_kinds.add("machine")
    actual_preview_kinds = {item["kind"] for item in preview_hashes if item.get("sha256")}
    for missing_kind in sorted(expected_preview_kinds - actual_preview_kinds):
        issues.append(f"rendered_preview_missing:{missing_kind}")

    proof_items = _eligible_proof_items(record)
    package_key = str(record.get("recommended_primary_package") or "")
    package_reason = str(record.get("package_recommendation_reason") or "")
    inputs = {
        "lead_id": lead_id,
        "recipient": resolved_recipient,
        "subject": resolved_subject,
        "subject_hash": _canonical_json_hash(resolved_subject),
        "body_hash": _canonical_json_hash(resolved_body),
        "asset_hashes": asset_hashes,
        "rendered_preview_hashes": preview_hashes,
        "locked_business_name": business_name,
        "selected_proof_items": proof_items,
        "selected_proof_hash": _canonical_json_hash(proof_items),
        "package_key": package_key,
        "package_recommendation_reason": package_reason,
        "classification": classification,
        "establishment_profile": profile,
        "include_machine_image": resolved_machine,
        "include_menu_image": image_flags["include_menu_image"],
    }
    inputs["input_hash"] = _canonical_json_hash(inputs)
    return inputs, issues


def _validate_tailoring_audit(
    record: dict[str, Any],
    *,
    recipient: str = "",
    subject: str = "",
    body: str = "",
    assets: list[str] | None = None,
    include_machine_image: bool | None = None,
) -> dict[str, Any]:
    audit = record.get("tailoring_audit") or {}
    if record.get("send_ready_checked") is not True or not audit:
        return {"valid": False, "reason": "final_check_missing", "issues": ["final_check_missing"]}
    if audit.get("passed") is not True:
        return {"valid": False, "reason": "final_check_failed", "issues": list(audit.get("failure_reasons") or ["final_check_failed"])}

    inputs, issues = _tailoring_audit_inputs(
        record,
        recipient=recipient,
        subject=subject,
        body=body,
        assets=assets,
        include_machine_image=include_machine_image,
    )
    if issues:
        return {"valid": False, "reason": "final_check_stale", "issues": issues, "current_input_hash": inputs["input_hash"]}
    if str(audit.get("input_hash") or "") != inputs["input_hash"]:
        return {
            "valid": False,
            "reason": "final_check_stale",
            "issues": ["final_check_hash_mismatch"],
            "current_input_hash": inputs["input_hash"],
            "audit_input_hash": audit.get("input_hash"),
        }
    return {"valid": True, "reason": "", "issues": [], "inputs": inputs}


def _clear_tailoring_audit(record: dict[str, Any], reason: str) -> None:
    previous = record.get("tailoring_audit") if isinstance(record.get("tailoring_audit"), dict) else {}
    record["send_ready_checked"] = False
    record["send_ready_checked_at"] = ""
    record["send_ready_checklist"] = []
    record["tailoring_audit"] = {
        "passed": False,
        "invalidated_at": datetime.now(timezone.utc).isoformat(),
        "invalidation_reason": reason,
        "previous_input_hash": previous.get("input_hash", ""),
    }
    record["manual_real_send_approved"] = False
    record["manual_real_send_approved_at"] = ""


def _send_readiness_for_record(
    record: dict[str, Any],
    *,
    recipient: str = "",
    subject: str = "",
    body: str = "",
    assets: list[str] | None = None,
    include_machine_image: bool | None = None,
    final_check: bool = False,
) -> dict[str, Any]:
    """Return the minimal send gate used by green dashboard tags and batch send."""
    from pipeline.lead_dossier import ensure_lead_dossier, READINESS_READY
    from pipeline.operator_state import OPERATOR_READY
    from pipeline.record import authoritative_business_name, get_primary_email_contact
    from pipeline.models import QualificationResult
    from pipeline.outreach import classify_business, select_outreach_assets, build_outreach_email
    from pipeline.constants import ENGLISH_QR_MENU_KEY

    checked = dict(record)
    if not checked.get("lead_evidence_dossier") or not checked.get("launch_readiness_status"):
        checked = ensure_lead_dossier(checked)
    lead_id = str(checked.get("lead_id") or "")
    business_name = authoritative_business_name(checked)
    reasons: list[str] = []
    tags: list[str] = []

    if checked.get("launch_readiness_status") != READINESS_READY:
        reasons.append("launch_not_ready")
    if checked.get("operator_state") != OPERATOR_READY:
        reasons.append("operator_not_ready")

    email_contact = get_primary_email_contact(checked)
    email = str(recipient or (email_contact or {}).get("value") or checked.get("email") or "").strip().lower()
    if not email or not _valid_email(email):
        reasons.append("email_not_verified")
    elif lead_id and not _is_lead_business_recipient(lead_id, email):
        reasons.append("email_not_saved_business_route")

    if business_name_is_suspicious(business_name):
        reasons.append("restaurant_name_not_safe")

    resolved_subject = subject or str(checked.get("outreach_draft_subject") or "").strip()
    resolved_body = body or str(checked.get("outreach_draft_body") or "").strip()
    if not resolved_subject or not resolved_body:
        reasons.append("checked_draft_missing")
    padded_body = f" {resolved_subject}\n{resolved_body} ".lower()
    if any(term in padded_body for term in FORBIDDEN_FINAL_CHECK_TERMS):
        reasons.append("banned_customer_copy_term")
    if resolved_body and ("qr" not in padded_body or ("show staff" not in padded_body and "スタッフ" not in resolved_body)):
        reasons.append("stale_or_non_qr_first_draft")
    if final_check:
        if not resolved_subject or not resolved_body:
            reasons.append("translations_not_checked")
    else:
        audit_validation = _validate_tailoring_audit(
            checked,
            recipient=email,
            subject=resolved_subject,
            body=resolved_body,
            assets=assets,
            include_machine_image=include_machine_image,
        )
        if not audit_validation["valid"]:
            reasons.append(str(audit_validation["reason"] or "final_check_missing"))

    q = QualificationResult(
        lead=checked.get("lead") is True,
        rejection_reason=checked.get("rejection_reason"),
        business_name=business_name,
        menu_evidence_found=checked.get("menu_evidence_found", True),
        machine_evidence_found=checked.get("machine_evidence_found", False),
    )
    classification = checked.get("outreach_classification") or classify_business(q)
    profile = _effective_establishment_profile(checked)
    expected_assets = [
        str(path) for path in select_outreach_assets(
            classification,
            establishment_profile=profile["effective"],
        )
    ]
    resolved_assets = [str(path) for path in (assets if assets is not None else checked.get("outreach_assets_selected") or expected_assets)]
    missing_assets = [path for path in expected_assets if path not in resolved_assets]
    missing_files = [path for path in resolved_assets if path and not Path(path).exists()]
    if missing_assets or missing_files:
        reasons.append("inline_pitch_asset_missing")

    default_email = build_outreach_email(
        business_name=business_name,
        classification=classification,
        establishment_profile=profile["effective"],
        include_inperson_line=checked.get("outreach_include_inperson", True),
        city=checked.get("city", ""),
    )
    if default_email.get("include_menu_image"):
        menu_template = _menu_template_for_profile(profile["effective"])
        if not menu_template.exists():
            reasons.append("inline_menu_template_missing")
    if checked.get("outreach_status") in BLOCKED_SEND_STATUSES:
        reasons.append("already_contacted_or_blocked")
    if checked.get("lead_category") == "skip" or checked.get("lead") is not True:
        reasons.append("skipped_or_not_true_lead")
    if str(checked.get("recommended_primary_package") or "") != ENGLISH_QR_MENU_KEY:
        reasons.append("active_product_missing")
    if _is_lead_business_recipient(lead_id, email) and checked.get("manual_real_send_approved") is not True:
        reasons.append("manual_real_send_approval_missing")

    if reasons:
        reason_set = set(reasons)
        if "launch_not_ready" in reason_set:
            tags.append("REVIEW")
        if "operator_not_ready" in reason_set:
            tags.append("REVIEW")
        if "email_not_verified" in reason_set or "email_not_saved_business_route" in reason_set:
            tags.append("EMAIL")
        if "translations_not_checked" in reason_set or "checked_draft_missing" in reason_set:
            tags.append("COPY")
        if "final_check_missing" in reason_set or "final_check_failed" in reason_set or "final_check_stale" in reason_set:
            tags.append("CHECK")
        if any(reason in reason_set for reason in ("inline_pitch_asset_missing", "inline_menu_template_missing", "machine_inline_missing", "machine_template_missing")):
            tags.append("SAMPLE")
        if "restaurant_name_not_safe" in reason_set:
            tags.append("NAME")
        if "already_contacted_or_blocked" in reason_set:
            tags.append("BLOCKED")
        if "manual_real_send_approval_missing" in reason_set:
            tags.append("APPROVE")
        if "banned_customer_copy_term" in reason_set or "stale_or_non_qr_first_draft" in reason_set:
            tags.append("COPY")
    else:
        tags.append("SEND READY")

    status = "ready_to_send" if not reasons else "not_ready"
    return {
        "status": status,
        "label": "Send Ready" if status == "ready_to_send" else "Check",
        "tags": tags,
        "reasons": reasons,
        "email": email,
        "business_name": business_name,
        "classification": classification,
        "establishment_profile": profile["effective"],
        "operator_state": checked.get("operator_state", "review"),
        "operator_reason": checked.get("operator_reason", "Review this record before outreach."),
    }


def _send_batch_dir() -> Path:
    return STATE_ROOT / "send_batches"


def _send_batch_path(batch_id: str) -> Path:
    return _send_batch_dir() / f"{batch_id}.json"


def _load_send_batch(batch_id: str) -> dict[str, Any] | None:
    from pipeline.utils import read_json

    return read_json(_send_batch_path(batch_id))


def _save_send_batch(batch: dict[str, Any]) -> None:
    from pipeline.utils import write_json

    write_json(_send_batch_path(str(batch.get("batch_id") or "")), batch)


def _list_send_batches() -> list[dict[str, Any]]:
    from pipeline.utils import read_json

    root = _send_batch_dir()
    if not root.exists():
        return []
    batches: list[dict[str, Any]] = []
    for path in sorted(root.glob("send-batch-*.json"), reverse=True):
        if path.name.endswith(("-release-manifest.json", "-mock-payloads.json")):
            continue
        batch = read_json(path)
        if not batch or not isinstance(batch.get("leads"), list) or "status" not in batch:
            continue
        batches.append(_send_batch_summary(batch))
    return batches


def _send_batch_summary(batch: dict[str, Any]) -> dict[str, Any]:
    leads = list(batch.get("leads") or [])
    status_counts: dict[str, int] = {}
    for entry in leads:
        status = str(entry.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    next_entry = next((entry for entry in leads if entry.get("status") in {"scheduled", "sending"}), None)
    return {
        **batch,
        "status_counts": status_counts,
        "sent_count": status_counts.get("sent", 0),
        "failed_count": status_counts.get("failed", 0),
        "scheduled_count": status_counts.get("scheduled", 0),
        "next_scheduled_at": str((next_entry or {}).get("scheduled_at") or ""),
        "cancelable": str(batch.get("status") or "") in {"scheduled", "running", "paused"},
    }


def _send_planner_payload() -> dict[str, Any]:
    from pipeline.record import list_leads

    leads = [_prepare_lead_for_dashboard(lead) for lead in list_leads(state_root=STATE_ROOT)]
    ready = [
        lead for lead in leads
        if _send_readiness_for_record(lead)["status"] == "ready_to_send"
        and lead.get("send_ready_checked") is True
        and str(lead.get("primary_contact_type") or "") == "email"
    ]
    batches = _list_send_batches()
    return {
        "ready_count": len(ready),
        "selected_limit": 10,
        "batches": batches,
        "counts": {
            "batches": len(batches),
            "scheduled": sum(1 for batch in batches if batch.get("status") == "scheduled"),
            "running": sum(1 for batch in batches if batch.get("status") == "running"),
            "completed": sum(1 for batch in batches if batch.get("status") == "completed"),
            "failed": sum(1 for batch in batches if batch.get("status") == "failed"),
            "canceled": sum(1 for batch in batches if str(batch.get("status") or "").endswith("canceled")),
        },
    }


def _cancel_send_batch(batch_id: str) -> dict[str, Any]:
    batch = _load_send_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="send_batch_not_found")
    status = str(batch.get("status") or "")
    if status in {"completed", "failed", "canceled", "partially_canceled"}:
        return _send_batch_summary(batch)
    canceled_at = datetime.now(timezone.utc).isoformat()
    sent_count = 0
    for entry in batch.get("leads") or []:
        entry_status = str(entry.get("status") or "")
        if entry_status == "sent":
            sent_count += 1
            continue
        if entry_status in {"scheduled", "sending"}:
            entry["status"] = "canceled"
            entry["canceled_at"] = canceled_at
    batch["status"] = "partially_canceled" if sent_count else "canceled"
    batch["canceled_at"] = canceled_at
    _save_send_batch(batch)
    return _send_batch_summary(batch)


def _create_send_batch(*, lead_ids: list[str], delay_seconds: int, notes: str = "") -> dict[str, Any]:
    from pipeline.record import load_lead
    from pipeline.launch_freeze import LaunchFreezeError, assert_launch_not_frozen

    if not 1 <= len(lead_ids) <= 10:
        raise HTTPException(status_code=422, detail="send_batch_size_must_be_1_to_10")
    if len(set(lead_ids)) != len(lead_ids):
        raise HTTPException(status_code=422, detail="duplicate_lead_in_send_batch")
    delay_seconds = max(0, min(delay_seconds, 3600))
    try:
        assert_launch_not_frozen(state_root=STATE_ROOT)
    except LaunchFreezeError as exc:
        raise HTTPException(status_code=423, detail=f"launch_frozen:{exc}") from exc

    now = datetime.now(timezone.utc)
    entries: list[dict[str, Any]] = []
    release_entries: list[dict[str, Any]] = []
    mock_payloads: list[dict[str, Any]] = []
    for idx, lead_id in enumerate(lead_ids):
        record = load_lead(lead_id, state_root=STATE_ROOT)
        if not record:
            raise HTTPException(status_code=404, detail=f"lead_not_found:{lead_id}")
        record = _ensure_evidence_audit_for_batch_record(record)
        evidence_skip_reason = _evidence_batch_skip_reason(record)
        if evidence_skip_reason:
            raise HTTPException(status_code=422, detail=f"lead_evidence_blocked:{lead_id}:{evidence_skip_reason}")
        gate = _send_readiness_for_record(record)
        if gate["status"] != "ready_to_send":
            raise HTTPException(status_code=422, detail=f"lead_not_send_ready:{lead_id}:{','.join(gate['reasons'])}")
        if record.get("send_ready_checked") is not True:
            raise HTTPException(status_code=422, detail=f"lead_final_check_missing:{lead_id}")
        audit_validation = _validate_tailoring_audit(record, recipient=gate["email"])
        if not audit_validation["valid"]:
            raise HTTPException(status_code=422, detail=f"lead_final_check_invalid:{lead_id}:{audit_validation['reason']}")
        audit = record.get("tailoring_audit") or {}
        inputs = audit_validation.get("inputs") or {}
        entries.append({
            "lead_id": lead_id,
            "business_name": gate["business_name"],
            "email": gate["email"],
            "scheduled_at": (now + timedelta(seconds=delay_seconds * idx)).isoformat(),
            "status": "scheduled",
            "attempted_at": "",
            "sent_at": "",
            "error": "",
        })
        release_entries.append({
            "lead_id": lead_id,
            "business_name": gate["business_name"],
            "recipient": gate["email"],
            "subject": str(record.get("outreach_draft_subject") or ""),
            "package_key": inputs.get("package_key") or record.get("recommended_primary_package") or "",
            "proof_items": list(audit.get("selected_proof_items") or []),
            "inline_assets": list(record.get("outreach_assets_selected") or []),
            "rendered_previews": list(audit.get("rendered_previews") or []),
            "checklist": list(audit.get("checklist") or record.get("send_ready_checklist") or []),
            "tailoring_audit_input_hash": audit.get("input_hash", ""),
        })
        mock_payloads.append({
            "lead_id": lead_id,
            "recipient": gate["email"],
            "subject": str(record.get("outreach_draft_subject") or ""),
            "text_body_hash": inputs.get("body_hash") or "",
            "assets": list(record.get("outreach_assets_selected") or []),
            "include_menu_image": bool(inputs.get("include_menu_image")),
            "include_machine_image": bool(inputs.get("include_machine_image")),
            "classification": gate["classification"],
            "establishment_profile": gate["establishment_profile"],
            "tailoring_audit_input_hash": audit.get("input_hash", ""),
        })

    batch_id = "send-batch-" + uuid.uuid4().hex[:10]
    from pipeline.utils import write_json

    release_manifest_path = _send_batch_dir() / f"{batch_id}-release-manifest.json"
    mock_payloads_path = _send_batch_dir() / f"{batch_id}-mock-payloads.json"
    write_json(mock_payloads_path, {
        "batch_id": batch_id,
        "created_at": now.isoformat(),
        "payloads": mock_payloads,
    })
    write_json(release_manifest_path, {
        "batch_id": batch_id,
        "created_at": now.isoformat(),
        "lead_count": len(release_entries),
        "mock_payloads_path": str(mock_payloads_path),
        "leads": release_entries,
    })
    batch = {
        "batch_id": batch_id,
        "created_at": now.isoformat(),
        "notes": notes,
        "delay_seconds": delay_seconds,
        "status": "scheduled",
        "lead_count": len(entries),
        "leads": entries,
        "release_manifest_path": str(release_manifest_path),
        "mock_payloads_path": str(mock_payloads_path),
    }
    _save_send_batch(batch)
    return batch


def _final_checklist_for_record(
    record: dict[str, Any],
    *,
    gate: dict[str, Any],
    subject: str,
    body: str,
    assets: list[str],
    include_machine_image: bool | None,
    rendered_previews: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    from pipeline.record import authoritative_business_name

    business_name = authoritative_business_name(record)
    reasons = set(gate.get("reasons") or [])
    checklist = [
        {
            "key": "launch",
            "label": "Launch readiness",
            "status": "fail" if {"launch_not_ready", "operator_not_ready"} & reasons else "pass",
            "detail": "Ready for outreach" if not {"launch_not_ready", "operator_not_ready"} & reasons else str(gate.get("operator_reason") or "Lead is not ready for outreach"),
        },
        {
            "key": "email",
            "label": "Restaurant email",
            "status": "fail" if {"email_not_verified", "email_not_saved_business_route"} & reasons else "pass",
            "detail": gate.get("email") or "No verified restaurant email",
        },
        {
            "key": "copy",
            "label": "Checked translation",
            "status": "fail" if {"translations_not_checked", "checked_draft_missing"} & reasons else "pass",
            "detail": "Subject/body present and checked" if subject and body else "Subject/body missing",
        },
    ]

    if business_name and business_name in subject and business_name in body:
        name_status = "pass"
        name_detail = "Restaurant name appears in the checked subject and body"
    else:
        name_status = "fail"
        name_detail = "Restaurant name is missing from the checked subject or body"
    checklist.append({"key": "name", "label": "Restaurant name", "status": name_status, "detail": name_detail})

    sample_failed = bool({"inline_pitch_asset_missing", "inline_menu_template_missing", "machine_inline_missing", "machine_template_missing"} & reasons)
    checklist.append({
        "key": "sample",
        "label": "Generic demo",
        "status": "fail" if sample_failed else "pass",
        "detail": "Generic QR demo link is used; no first-contact sample attachments" if not sample_failed else "Expected demo proof is missing",
    })

    rendered_previews = rendered_previews or []
    seal_failures: list[str] = []
    for preview in rendered_previews:
        path_text = str(preview.get("path") or "")
        kind = str(preview.get("kind") or "sample")
        if not path_text or not Path(path_text).exists():
            seal_failures.append(f"{kind} preview missing")
            continue
        rendered_text = Path(path_text).read_text(encoding="utf-8")
        if "見本" not in rendered_text:
            seal_failures.append(f"{kind} preview missing generic sample seal")
    if not rendered_previews:
        seal_status = "pass"
        seal_detail = "No first-contact inline sample is used"
    elif not seal_failures:
        seal_status = "pass"
        seal_detail = "Generic sample seal renders as 見本"
    else:
        seal_status = "fail"
        seal_detail = "; ".join(seal_failures) or "No rendered inline sample was available for the seal check"
    checklist.append({"key": "seal", "label": "Sample seal", "status": seal_status, "detail": seal_detail})

    proof_items = _eligible_proof_items(record)
    checklist.append({
        "key": "proof",
        "label": "Customer-safe proof",
        "status": "pass" if proof_items else "fail",
        "detail": f"{len(proof_items)} customer-safe proof item(s) selected" if proof_items else "No customer-safe proof item tied to this establishment",
    })

    from pipeline.constants import ENGLISH_QR_MENU_KEY

    package_key = str(record.get("recommended_primary_package") or "")
    package_status = "pass" if package_key == ENGLISH_QR_MENU_KEY else "fail"
    checklist.append({
        "key": "package",
        "label": "Package fit",
        "status": package_status,
        "detail": package_key or "No fixed package recommendation is saved",
    })

    profile = gate.get("establishment_profile") or _effective_establishment_profile(record)["effective"]
    body_text = f"{subject}\n{body}"
    diagnosis_terms = ("QR", "英語QR", "Show Staff", "スタッフ")
    diagnosis_ok = any(term in body_text for term in diagnosis_terms)
    checklist.append({
        "key": "diagnosis",
        "label": "QR-first copy",
        "status": "pass" if diagnosis_ok else "fail",
        "detail": "Copy mentions QR menu and Show Staff List" if diagnosis_ok else "Copy does not mention the QR menu and Show Staff List flow",
    })

    padded = f" {body_text.lower()} "
    forbidden = [term.strip() for term in FORBIDDEN_FINAL_CHECK_TERMS if term in padded]
    price_claims = {match.group(1) or match.group(2) for match in FINAL_CHECK_PRICE_RE.finditer(body_text)}
    compliance_failures = []
    if forbidden:
        compliance_failures.append("forbidden terms: " + ", ".join(sorted(set(forbidden))))
    if len({claim.replace(",", "") for claim in price_claims}) >= 3:
        compliance_failures.append("cold copy includes all three fixed prices")
    checklist.append({
        "key": "compliance",
        "label": "Compliance copy scan",
        "status": "fail" if compliance_failures else "pass",
        "detail": "; ".join(compliance_failures) if compliance_failures else "No forbidden terms or all-price cold pitch found",
    })

    return checklist


async def _run_send_batch(batch_id: str) -> None:
    batch = _load_send_batch(batch_id)
    if not batch:
        return
    if str(batch.get("status") or "") == "canceled":
        return
    batch["status"] = "running"
    _save_send_batch(batch)

    for entry in list(batch.get("leads") or []):
        batch = _load_send_batch(batch_id) or batch
        if str(batch.get("status") or "") in {"canceled", "partially_canceled", "paused"}:
            return
        if entry.get("status") != "scheduled":
            continue
        try:
            scheduled_at = datetime.fromisoformat(str(entry.get("scheduled_at") or "").replace("Z", "+00:00"))
        except ValueError:
            scheduled_at = datetime.now(timezone.utc)
        wait_seconds = max(0.0, (scheduled_at - datetime.now(timezone.utc)).total_seconds())
        if wait_seconds:
            await asyncio.sleep(wait_seconds)

        batch = _load_send_batch(batch_id) or batch
        if str(batch.get("status") or "") in {"canceled", "partially_canceled", "paused"}:
            return
        matching = next((item for item in batch.get("leads") or [] if item.get("lead_id") == entry.get("lead_id")), None)
        if not matching or matching.get("status") != "scheduled":
            continue
        matching["attempted_at"] = datetime.now(timezone.utc).isoformat()
        matching["status"] = "sending"
        _save_send_batch(batch)

        from pipeline.record import load_lead

        record = load_lead(str(matching.get("lead_id") or ""), state_root=STATE_ROOT)
        if not record:
            matching["status"] = "skipped"
            matching["error"] = "lead_not_found"
            _save_send_batch(batch)
            continue
        evidence_skip_reason = _evidence_batch_skip_reason(record)
        if evidence_skip_reason:
            matching["status"] = "skipped"
            matching["error"] = evidence_skip_reason
            _save_send_batch(batch)
            continue

        try:
            await _send_lead_email_payload(str(matching.get("lead_id") or ""), require_send_ready=True)
        except Exception as exc:
            matching["status"] = "failed"
            matching["error"] = str(getattr(exc, "detail", "") or exc)
            _save_send_batch(batch)
            continue

        matching["status"] = "sent"
        matching["sent_at"] = datetime.now(timezone.utc).isoformat()
        _save_send_batch(batch)

    batch = _load_send_batch(batch_id) or batch
    if str(batch.get("status") or "") in {"canceled", "partially_canceled", "paused"}:
        return
    statuses = [str(entry.get("status") or "") for entry in batch.get("leads") or []]
    batch["status"] = "failed" if any(status == "failed" for status in statuses) else "completed"
    batch["completed_at"] = datetime.now(timezone.utc).isoformat()
    _save_send_batch(batch)


# ---------------------------------------------------------------------------
# Routes — Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard_main(request: Request):
    """Main dashboard view."""
    from pipeline.launch_freeze import launch_freeze_status
    from pipeline.record import list_leads
    leads = [
        _prepare_lead_for_dashboard(lead)
        for lead in list_leads(state_root=STATE_ROOT)
        if lead.get("lead") is True
        and (
            _restaurant_email_queue_record(lead)
            or lead.get("outreach_status", "new") not in BLOCKED_SEND_STATUSES
            or lead.get("launch_readiness_status") == "disqualified"
        )
        and (
            _restaurant_email_queue_record(lead)
            or _has_supported_contact_route(lead)
        )
    ]
    leads = sorted(leads, key=_lead_queue_sort_key)
    leads = _attach_reply_summaries(leads)
    return templates.TemplateResponse(request, "index.html", {
        "leads": leads,
        "lead_card_counts": _dashboard_card_counts(leads),
        "search_category_meta": _dashboard_search_category_meta(),
        "search_coverage": _compute_search_coverage(leads),
        "launch_freeze": launch_freeze_status(state_root=STATE_ROOT),
    })


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------

@app.get("/api/leads")
async def api_leads():
    """Return dashboard-ready lead records as JSON."""
    from pipeline.launch_freeze import launch_freeze_status
    from pipeline.record import list_leads
    leads = [_prepare_lead_for_dashboard(lead) for lead in list_leads(state_root=STATE_ROOT)]
    leads = sorted(leads, key=_lead_queue_sort_key)
    leads = _attach_reply_summaries(leads)
    return {
        "leads": leads,
        "card_counts": _dashboard_card_counts(leads),
        "launch_freeze": launch_freeze_status(state_root=STATE_ROOT),
    }


@app.get("/api/funnel")
async def api_funnel():
    """Return send-ready funnel counts: total → categorized → email valid → send-ready."""
    from pipeline.record import list_leads
    leads = list_leads(state_root=STATE_ROOT)
    total = len(leads)
    categorized = sum(
        1 for lead in leads
        if lead.get("primary_category_v1") in {"ramen", "izakaya"}
    )
    email_valid = sum(
        1 for lead in leads
        if lead.get("primary_category_v1") in {"ramen", "izakaya"}
        and lead.get("email_mx_valid") is not False
        and lead.get("email")
    )
    send_ready = sum(
        1 for lead in leads
        if lead.get("operator_state") == "ready"
    )
    by_category = {}
    for cat in ("ramen", "izakaya"):
        cat_leads = [l for l in leads if l.get("primary_category_v1") == cat]
        by_category[cat] = {
            "total": len(cat_leads),
            "email_valid": sum(
                1 for l in cat_leads
                if l.get("email_mx_valid") is not False and l.get("email")
            ),
            "send_ready": sum(1 for l in cat_leads if l.get("operator_state") == "ready"),
        }
    return {
        "total": total,
        "categorized": categorized,
        "email_valid": email_valid,
        "send_ready": send_ready,
        "by_category": by_category,
    }


@app.get("/api/search/categories")
async def api_search_categories():
    """Return dashboard search category metadata from Python source of truth."""
    return {"categories": _dashboard_search_category_meta()}


@app.get("/api/search/coverage")
async def api_search_coverage():
    """Return pitch-ready lead counts by city and category."""
    from pipeline.record import list_leads
    leads = list_leads(state_root=STATE_ROOT)
    return _compute_search_coverage(leads)


@app.post("/api/send-batches")
async def api_create_send_batch(request: Request, background_tasks: BackgroundTasks):
    """Schedule up to 10 green send-ready email leads with a delay between sends."""
    payload = await request.json()
    lead_ids = [str(lead_id or "").strip() for lead_id in payload.get("lead_ids") or [] if str(lead_id or "").strip()]
    delay_seconds = int(payload.get("delay_seconds") or 900)
    start = payload.get("start", True) is not False
    batch = _create_send_batch(
        lead_ids=lead_ids,
        delay_seconds=delay_seconds,
        notes=str(payload.get("notes") or ""),
    )
    if start:
        background_tasks.add_task(_run_send_batch, batch["batch_id"])
    return batch


@app.get("/api/send-batches")
async def api_send_batches():
    """Return delayed send batches for the dashboard send planner."""
    return _send_planner_payload()


@app.post("/api/send-batches/{batch_id}/cancel")
async def api_cancel_send_batch(batch_id: str):
    """Cancel unsent leads in a delayed send batch."""
    return _cancel_send_batch(batch_id)


@app.delete("/api/leads/{lead_id}")
async def api_delete_lead(lead_id: str):
    """Delete a lead record from the operator queue."""
    from pipeline.record import load_lead

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")

    path = STATE_ROOT / "leads" / f"{lead_id}.json"
    try:
        path.unlink()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Lead not found")

    _log("lead_deleted", record.get("business_name", ""), lead_id=lead_id)
    return {"status": "deleted", "lead_id": lead_id}


@app.post("/api/leads/{lead_id}/profile")
async def api_update_lead_profile(lead_id: str, request: Request):
    """Update or clear the operator establishment-profile override."""
    from pipeline.record import load_lead, persist_lead_record

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")

    body = await request.json()
    clear_override = bool(body.get("clear_override"))

    if clear_override:
        record["establishment_profile_override"] = ""
        record["establishment_profile_override_note"] = ""
        record["establishment_profile_override_at"] = None
        action = "establishment_profile_override_cleared"
    else:
        profile = str(body.get("profile") or "").strip()
        note = str(body.get("note") or "").strip()
        if profile not in ESTABLISHMENT_PROFILE_LABELS:
            raise HTTPException(status_code=400, detail="Invalid establishment profile")
        record["establishment_profile_override"] = profile
        record["establishment_profile_override_note"] = note
        record["establishment_profile_override_at"] = datetime.now(timezone.utc).isoformat()
        action = "establishment_profile_override_saved"

    _clear_tailoring_audit(record, "establishment_profile_changed")
    record = _refresh_operator_lead(record)
    persist_lead_record(record, state_root=STATE_ROOT)
    prepared = _prepare_lead_for_dashboard(record)
    _log(action, f"profile={prepared.get('establishment_profile_effective', '')}", lead_id=lead_id)
    return prepared


@app.post("/api/leads/{lead_id}/review-outcome")
async def api_update_lead_review_outcome(lead_id: str, request: Request):
    """Record a no-send manual review outcome without promoting the lead."""
    from pipeline.record import load_lead, persist_lead_record

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")

    body = await request.json()
    outcome = str(body.get("outcome") or "").strip()
    note = str(body.get("note") or "").strip()
    if outcome not in LEAD_REVIEW_OUTCOME_LABELS:
        raise HTTPException(status_code=400, detail="Invalid no-send review outcome")
    if str(record.get("launch_readiness_status") or "manual_review") != "manual_review":
        raise HTTPException(status_code=409, detail="Only manual-review leads can be reviewed here")
    if str(record.get("outreach_status") or "") != "needs_review":
        raise HTTPException(status_code=409, detail="Only needs_review leads can be reviewed here")

    now = datetime.now(timezone.utc).isoformat()
    record["operator_review_outcome"] = outcome
    record["operator_review_note"] = note
    record["operator_reviewed_at"] = now
    record["review_status"] = LEAD_REVIEW_STATUS_BY_OUTCOME[outcome]
    record["manual_review_required"] = True
    record["launch_readiness_status"] = "manual_review"
    reasons = list(record.get("launch_readiness_reasons") or [])
    reason = f"operator_review_outcome:{outcome}"
    if reason not in reasons:
        reasons.append(reason)
    record["launch_readiness_reasons"] = reasons
    record["pitch_ready"] = False
    if outcome == "pitch_pack_ready":
        record["pitch_pack_ready_no_send"] = True
        record["pitch_pack_ready_at"] = now
        record["candidate_inbox_status"] = "pitch_pack_ready_no_send"
        record["pitch_readiness_status"] = "pitch_pack_ready_no_send"
    else:
        record["pitch_pack_ready_no_send"] = False
        if outcome == "reject":
            record["candidate_inbox_status"] = "rejected"
            record["pitch_readiness_status"] = "rejected"
    record["outreach_status"] = "needs_review"
    record.setdefault("status_history", []).append({
        "status": f"operator_review_{outcome}",
        "timestamp": now,
        "note": note or LEAD_REVIEW_OUTCOME_LABELS[outcome],
    })

    record = _refresh_operator_lead(record)
    persist_lead_record(record, state_root=STATE_ROOT)
    prepared = _prepare_lead_for_dashboard(record)
    _log("lead_review_outcome_saved", f"outcome={outcome}", lead_id=lead_id)
    return prepared


@app.post("/api/leads/{lead_id}/operator-action")
async def api_lead_operator_action(lead_id: str, request: Request):
    """Apply a compact operator action from the lead queue."""
    from pipeline.record import load_lead, persist_lead_record

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")

    body = await request.json()
    action = str(body.get("action") or "").strip()
    note = str(body.get("note") or "").strip()
    now = datetime.now(timezone.utc).isoformat()

    if action == "approve_real_shop":
        business_name = str(record.get("business_name") or "").strip()
        if not business_name or business_name_is_suspicious(business_name):
            raise HTTPException(status_code=422, detail="Fix the restaurant name before approval")
        verified_by = list(record.get("business_name_verified_by") or [])
        if "operator" not in {str(item).lower() for item in verified_by}:
            verified_by.append("operator")
        record["business_name_locked"] = True
        record["business_name_lock_reason"] = "operator_approved_real_shop"
        record["business_name_verified_by"] = verified_by
        record["name_verification_status"] = "manually_accepted"
        if str(record.get("verification_status") or "") != "rejected":
            record["verification_status"] = "verified"
        record["operator_real_shop_approved_at"] = now
        history_status = "operator_approved_real_shop"
        log_detail = "approved_real_shop"
    elif action == "skip":
        record["outreach_status"] = "skipped"
        record["review_status"] = "rejected"
        record["operator_review_outcome"] = "reject"
        record["operator_review_note"] = note or "Skipped from operator queue"
        record["operator_reviewed_at"] = now
        record["manual_review_required"] = True
        history_status = "operator_skipped"
        log_detail = "skipped"
    else:
        raise HTTPException(status_code=400, detail="Invalid operator action")

    record.setdefault("status_history", []).append({
        "status": history_status,
        "timestamp": now,
        "note": note or log_detail.replace("_", " "),
    })
    record = _refresh_operator_lead(record)
    persist_lead_record(record, state_root=STATE_ROOT)
    _log("lead_operator_action", log_detail, lead_id=lead_id)
    return _prepare_lead_for_dashboard(record)


@app.post("/api/leads/{lead_id}/operator-fields")
async def api_update_lead_operator_fields(lead_id: str, request: Request):
    """Update operator-editable lead fields used by quick actions."""
    from pipeline.constants import PACKAGE_REGISTRY
    from pipeline.record import load_lead, persist_lead_record

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")

    body = await request.json()
    changed: list[str] = []
    now = datetime.now(timezone.utc).isoformat()

    if "business_name" in body:
        business_name = str(body.get("business_name") or "").strip()
        if not business_name:
            raise HTTPException(status_code=400, detail="Restaurant name is required")
        if business_name_is_suspicious(business_name):
            raise HTTPException(status_code=422, detail="Restaurant name looks unsafe")
        record["business_name"] = business_name
        record["business_name_locked"] = True
        record["business_name_lock_reason"] = "operator_fixed_name"
        verified_by = list(record.get("business_name_verified_by") or [])
        if "operator" not in {str(item).lower() for item in verified_by}:
            verified_by.append("operator")
        record["business_name_verified_by"] = verified_by
        record["name_verification_status"] = "manually_accepted"
        changed.append("name")

    if "recommended_primary_package" in body:
        package_key = str(body.get("recommended_primary_package") or "").strip()
        if package_key not in PACKAGE_REGISTRY:
            raise HTTPException(status_code=400, detail="Invalid package")
        record["recommended_primary_package"] = package_key
        record["package_recommendation_reason"] = (
            str(body.get("package_recommendation_reason") or "").strip()
            or "Operator selected package after review."
        )
        record["operator_package_override"] = True
        changed.append("package")

    if not changed:
        raise HTTPException(status_code=400, detail="No supported field update supplied")

    _clear_tailoring_audit(record, "operator_field_update")
    record["operator_fields_updated_at"] = now
    record.setdefault("status_history", []).append({
        "status": "operator_fields_updated",
        "timestamp": now,
        "note": ", ".join(changed),
    })
    record = _refresh_operator_lead(record)
    persist_lead_record(record, state_root=STATE_ROOT)
    _log("lead_operator_fields_updated", ",".join(changed), lead_id=lead_id)
    return _prepare_lead_for_dashboard(record)


@app.post("/api/leads/{lead_id}/contacted")
async def api_mark_manual_contacted(lead_id: str, request: Request):
    """Persist a non-email outreach action as contacted."""
    from pipeline.record import load_lead, persist_lead_record

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")

    primary_contact = _lead_primary_contact(record)
    primary_contact_type = str((primary_contact or {}).get("type") or "")
    status = _manual_contact_status(primary_contact_type)
    if not status:
        raise HTTPException(status_code=400, detail="Lead does not have a supported manual contact route")
    if record.get("outreach_status") in BLOCKED_SEND_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Lead already has status '{record.get('outreach_status')}'",
        )

    body = await request.json()
    note = str(body.get("note") or "").strip()
    route_label = primary_contact_type.replace("_", " ") if primary_contact_type else "manual"
    record["outreach_status"] = status
    record["outreach_contacted_at"] = datetime.now(timezone.utc).isoformat()
    record["outreach_contacted_via"] = primary_contact_type
    record.setdefault("status_history", []).append({
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": note or f"Marked contacted after {route_label} outreach",
    })

    record = _refresh_operator_lead(record)
    persist_lead_record(record, state_root=STATE_ROOT)
    _log("manual_contact_marked", f"route={primary_contact_type}", lead_id=lead_id)
    return {
        "status": "ok",
        "lead_id": lead_id,
        "outreach_status": status,
        "contact_type": primary_contact_type,
    }


@app.post("/api/search")
async def api_search(request: Request):
    """Search for businesses, qualify them, and add leads."""
    body = await request.json()
    category = body.get("category", "ramen")
    city = body.get("city", "").strip()
    mode = body.get("mode", "unified")

    from pipeline.search_provider import configured_search_provider, search_provider_requires_api_key

    try:
        search_provider = configured_search_provider(os.environ.get("WEBREFURB_SEARCH_PROVIDER"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    serper_api_key = os.environ.get("SERPER_API_KEY", "")
    if search_provider_requires_api_key(search_provider) and not serper_api_key:
        raise HTTPException(status_code=500, detail="SERPER_API_KEY is only required when the serper search provider is explicitly selected")

    from pipeline.search_scope import search_query_for_scope, search_jobs_for_scope, merge_search_results

    query = search_query_for_scope(category=category, city=city)
    _log("search_started", f"query={query[:80]} category={category} provider={search_provider} mode={mode}")

    from pipeline.record import list_leads
    existing_actionable_ids = {
        lead.get("lead_id")
        for lead in list_leads(state_root=STATE_ROOT)
        if lead.get("lead") is True and _has_supported_contact_route(lead)
    }

    import concurrent.futures
    loop = asyncio.get_running_loop()

    def current_actionable_ids() -> set[str]:
        return {
            lead.get("lead_id")
            for lead in list_leads(state_root=STATE_ROOT)
            if lead.get("lead") is True and _has_supported_contact_route(lead)
        }

    async def run_codex_jobs() -> list[dict[str, Any]]:
        from pipeline.search_scope import codex_search_jobs_for_scope
        from pipeline.search import codex_search_and_qualify

        search_jobs = codex_search_jobs_for_scope(category=category, city=city)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            return await asyncio.gather(*[
                loop.run_in_executor(
                    pool,
                    lambda job=job: codex_search_and_qualify(
                        query=job["query"],
                        search_provider=search_provider,
                        category=job["category"],
                        state_root=STATE_ROOT,
                        search_job=job,
                    ),
                )
                for job in search_jobs
            ])

    async def run_friction_jobs() -> list[dict[str, Any]]:
        from pipeline.search import search_and_qualify

        search_jobs = search_jobs_for_scope(category=category, city=city, query=query)
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return await asyncio.gather(*[
                loop.run_in_executor(
                    pool,
                    lambda job=job: search_and_qualify(
                        query=job["query"],
                        serper_api_key=serper_api_key,
                        search_provider=search_provider,
                        category=job["category"],
                        state_root=STATE_ROOT,
                        search_job=job,
                    ),
                )
                for job in search_jobs
            ])

    if mode == "codex":
        raw_results = await run_codex_jobs()
    elif mode == "friction":
        raw_results = await run_friction_jobs()
    else:
        raw_results = await run_codex_jobs()
        if not (current_actionable_ids() - existing_actionable_ids):
            raw_results.extend(await run_friction_jobs())
        mode = "unified"

    result = merge_search_results(raw_results, query=query, category=category)
    result["search_mode"] = mode

    actionable_leads = [
        lead for lead in list_leads(state_root=STATE_ROOT)
        if lead.get("lead") is True and _has_supported_contact_route(lead)
    ]
    new_actionable_ids = [
        lead.get("lead_id")
        for lead in actionable_leads
        if lead.get("lead_id") not in existing_actionable_ids
    ]
    pipeline_added_count = int(result.get("leads") or 0)
    result["pipeline_reported_leads"] = pipeline_added_count
    result["leads"] = len(new_actionable_ids)
    result["added_lead_ids"] = new_actionable_ids
    if pipeline_added_count != result["leads"]:
        result["contact_route_mismatch"] = {
            "pipeline_reported_leads": pipeline_added_count,
            "saved_actionable_leads": result["leads"],
        }

    duplicate_count = sum(
        1 for decision in result.get("decisions", [])
        if decision.get("reason") == "already_tracked"
    )
    if result.get("leads", 0):
        _log("lead_created", f"count={result.get('leads', 0)}")
    if duplicate_count:
        _log("duplicate_skipped", f"count={duplicate_count}")
    _log("search_completed", f"leads={result.get('leads', 0)} total={result.get('total_candidates', 0)}")

    # Add coverage note if searching a well-covered area
    coverage = _compute_search_coverage(list_leads(state_root=STATE_ROOT))
    search_city = body.get("city", "").strip() or "Japan"
    search_cat = body.get("category", "all")
    city_count = coverage["city"].get(search_city, 0) if search_city != "Japan" else coverage["total"]
    if city_count >= 50:
        result["coverage_note"] = f"{search_city} already has {city_count} pitch-ready leads"

    return result


@app.get("/api/outreach/{lead_id}")
async def api_outreach_preview(lead_id: str):
    """Return the current outreach preview, preferring a saved draft."""
    return await _build_outreach_payload(lead_id, regenerate=False)


@app.post("/api/outreach/{lead_id}")
async def api_outreach(lead_id: str):
    """Regenerate the outreach package for a lead."""
    return await _build_outreach_payload(lead_id, regenerate=True)


@app.post("/api/outreach/{lead_id}/final-check")
async def api_outreach_final_check(lead_id: str, request: Request):
    """Run the second-pass checklist for the exact current pitch draft."""
    from pipeline.record import authoritative_business_name
    from pipeline.record import load_lead, persist_lead_record

    payload = await request.json()
    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")

    subject = str(payload.get("subject") or "").strip()
    body = str(payload.get("body") or "").strip()
    assets = [str(asset) for asset in payload.get("assets") or []]
    include_machine_image = payload.get("include_machine_image")
    if include_machine_image is not None:
        include_machine_image = bool(include_machine_image)

    gate = _send_readiness_for_record(
        record,
        subject=subject,
        body=body,
        assets=assets,
        include_machine_image=include_machine_image,
        final_check=True,
    )
    business_name = authoritative_business_name(record)
    image_flags = _expected_final_check_images(
        record,
        classification=str(gate.get("classification") or record.get("outreach_classification") or ""),
        profile=str(gate.get("establishment_profile") or _effective_establishment_profile(record)["effective"]),
        include_machine_image=include_machine_image,
    )
    rendered_previews = _render_final_check_previews(
        record,
        business_name=business_name,
        profile=str(gate.get("establishment_profile") or _effective_establishment_profile(record)["effective"]),
        include_menu_image=image_flags["include_menu_image"],
        include_machine_image=image_flags["include_machine_image"],
    )
    checklist = _final_checklist_for_record(
        record,
        gate=gate,
        subject=subject,
        body=body,
        assets=assets,
        include_machine_image=include_machine_image,
        rendered_previews=rendered_previews,
    )
    candidate_record = dict(record)
    candidate_record["outreach_draft_subject"] = subject
    candidate_record["outreach_draft_body"] = body
    if assets:
        candidate_record["outreach_assets_selected"] = assets
    if include_machine_image is not None:
        candidate_record["outreach_include_machine_image"] = include_machine_image
    audit_inputs, audit_input_issues = _tailoring_audit_inputs(
        candidate_record,
        recipient=str(gate.get("email") or ""),
        subject=subject,
        body=body,
        assets=assets,
        include_machine_image=include_machine_image,
        rendered_previews=rendered_previews,
    )
    failure_reasons = [
        f"{item['key']}:{item['detail']}"
        for item in checklist
        if item.get("status") != "pass"
    ]
    failure_reasons.extend(audit_input_issues)
    passed = gate["status"] == "ready_to_send" and not failure_reasons
    checked_at = datetime.now(timezone.utc).isoformat()
    tailoring_audit = {
        "passed": passed,
        "checked_at": checked_at,
        "checked_by": str(payload.get("checked_by") or "dashboard_operator"),
        "recipient": audit_inputs["recipient"],
        "subject": audit_inputs["subject"],
        "subject_hash": audit_inputs["subject_hash"],
        "body_hash": audit_inputs["body_hash"],
        "asset_hashes": audit_inputs["asset_hashes"],
        "rendered_previews": rendered_previews,
        "rendered_preview_hashes": audit_inputs["rendered_preview_hashes"],
        "locked_business_name": audit_inputs["locked_business_name"],
        "selected_proof_items": audit_inputs["selected_proof_items"],
        "selected_proof_hash": audit_inputs["selected_proof_hash"],
        "package_key": audit_inputs["package_key"],
        "package_recommendation_reason": audit_inputs["package_recommendation_reason"],
        "classification": audit_inputs["classification"],
        "establishment_profile": audit_inputs["establishment_profile"],
        "include_menu_image": audit_inputs["include_menu_image"],
        "include_machine_image": audit_inputs["include_machine_image"],
        "checklist": checklist,
        "failure_reasons": failure_reasons,
        "input_hash": audit_inputs["input_hash"],
    }
    if passed:
        record["outreach_draft_subject"] = subject
        record["outreach_draft_body"] = body
        if assets:
            record["outreach_assets_selected"] = assets
        if include_machine_image is not None:
            record["outreach_include_machine_image"] = include_machine_image
        record["send_ready_checked"] = True
        record["send_ready_checked_at"] = checked_at
        record["send_ready_checklist"] = checklist
        record["tailoring_audit"] = tailoring_audit
        record["manual_real_send_approved"] = True
        record["manual_real_send_approved_at"] = checked_at
        record = _refresh_operator_lead(record)
        persist_lead_record(record, state_root=STATE_ROOT)
        gate = _send_readiness_for_record(record)
    else:
        record["send_ready_checked"] = False
        record["send_ready_checklist"] = checklist
        record["tailoring_audit"] = tailoring_audit
        record["manual_real_send_approved"] = False
        record["manual_real_send_approved_at"] = ""
        record = _refresh_operator_lead(record)
        persist_lead_record(record, state_root=STATE_ROOT)

    return {
        "passed": passed,
        "send_readiness": gate,
        "checklist": checklist,
        "tailoring_audit": tailoring_audit,
    }


async def _build_outreach_payload(lead_id: str, *, regenerate: bool) -> dict[str, Any]:
    """Build an outreach payload.

    GET preview loads saved draft content. POST intentionally regenerates from
    the locked template and clears the saved manual draft.
    """
    from pipeline.record import authoritative_business_name, load_lead, persist_lead_record
    from pipeline.outreach import (
        build_manual_outreach_message,
        build_evidence_gated_email,
        classify_business,
        describe_outreach_assets,
        select_outreach_assets,
    )
    from pipeline.evidence_classifier import classify_lead
    from pipeline.models import QualificationResult

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")
    business_name = authoritative_business_name(record)
    test_fixture_label = _test_fixture_label_for_record(record)

    if business_name_is_suspicious(business_name):
        record["outreach_status"] = "needs_review"
        record["outreach_classification"] = None
        from pipeline.record import persist_lead_record
        record = _refresh_operator_lead(record)
        persist_lead_record(record, state_root=STATE_ROOT)
        raise HTTPException(
            status_code=422,
            detail="Business name looks unsafe or contact-route-derived. Fix the name before generating outreach.",
        )

    verified_by = list(record.get("business_name_verified_by") or [])
    if not record.get("business_name_locked") and record.get("business_name_source") and len(verified_by) < 2:
        record["outreach_status"] = "needs_review"
        from pipeline.record import persist_lead_record
        record = _refresh_operator_lead(record)
        persist_lead_record(record, state_root=STATE_ROOT)
        raise HTTPException(
            status_code=422,
            detail="Business name is not verified by two sources yet. Confirm it with Google and Tabelog before generating outreach.",
        )

    if regenerate and record.get("outreach_status") == "do_not_contact":
        raise HTTPException(status_code=403, detail="Lead is marked Do Not Contact")

    if regenerate and record.get("outreach_status") in BLOCKED_REGENERATE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Lead already has status '{record.get('outreach_status')}'",
        )

    from pipeline.lead_dossier import ensure_lead_dossier, READINESS_DISQUALIFIED, READINESS_READY
    from pipeline.operator_state import OPERATOR_READY
    record = ensure_lead_dossier(record)
    launch_readiness_status = record.get("launch_readiness_status")
    operator_state = record.get("operator_state")
    operator_reason = str(record.get("operator_reason") or "Review this record before outreach.")
    if regenerate and operator_state != OPERATOR_READY:
        from pipeline.record import persist_lead_record
        record = _refresh_operator_lead(record)
        persist_lead_record(record, state_root=STATE_ROOT)
        raise HTTPException(
            status_code=422,
            detail=f"Lead is not launch-ready for outreach: {operator_reason}",
        )
    if not regenerate and launch_readiness_status == READINESS_DISQUALIFIED:
        from pipeline.record import persist_lead_record
        record = _refresh_operator_lead(record)
        persist_lead_record(record, state_root=STATE_ROOT)
        raise HTTPException(
            status_code=422,
            detail="Lead is disqualified and cannot be previewed as a pitch.",
        )
    if not regenerate:
        from pipeline.pitch_cards import apply_pitch_card_state, is_pitch_card_openable

        record = apply_pitch_card_state(record)
        if not is_pitch_card_openable(record):
            raise HTTPException(
                status_code=422,
                detail=f"Lead is not launch-ready for outreach: not pitch-card reviewable: {record.get('pitch_card_status') or 'blocked'}",
            )

    # Build qualification result for classification
    q = QualificationResult(
        lead=record["lead"],
        rejection_reason=record.get("rejection_reason"),
        business_name=business_name,
        menu_evidence_found=record.get("menu_evidence_found", True),
        machine_evidence_found=record.get("machine_evidence_found", False),
    )

    classification = classify_business(q)
    contacts = _lead_contacts(record)
    primary_contact = _lead_primary_contact(record)
    profile = _effective_establishment_profile(record)
    send_enabled = _has_business_email(record)
    primary_contact_type = str((primary_contact or {}).get("type") or "")
    if primary_contact_type not in {"email", "contact_form"}:
        raise HTTPException(
            status_code=422,
            detail="Lead is not launch-ready for outreach: no supported e-mail or contact-form route for pitch preview.",
        )
    from pipeline.constants import GENERIC_DEMO_URL

    sample_result: dict[str, Any] = {"ok": True, "sample_menu_url": GENERIC_DEMO_URL, "generic_demo": True}
    sample_menu_url = GENERIC_DEMO_URL
    if primary_contact_type == "contact_form":
        contact_action = "use_contact_form"
        contact_action_note = "Use this short no-attachment QR-first version in the restaurant's saved contact form route. Dashboard e-mail sending stays disabled for this lead."
    else:
        contact_action = "send_email"
        contact_action_note = "This lead has a saved business e-mail route."

    draft_channel = primary_contact_type if primary_contact_type and primary_contact_type != "email" else "email"
    assets = select_outreach_assets(
        classification,
        contact_type=draft_channel,
        establishment_profile=profile["effective"],
    )
    include_inperson = record.get("outreach_include_inperson", True)
    if draft_channel == "email":
        # Evidence-gated email builder
        evidence_payload = _evidence_classifier_payload(
            record,
            business_name=business_name,
            classification=classification,
            profile=profile["effective"],
        )
        lead_classification = classify_lead(evidence_payload)
        draft = build_evidence_gated_email(lead_classification)
        if draft is None:
            # Evidence-gated classifier says skip — fall through with skip marker.
            draft = {
                "subject": "",
                "body": "",
                "english_body": "",
                "include_menu_image": False,
                "include_machine_image": False,
            }
        # Store the evidence audit alongside the draft
        record["evidence_audit"] = _build_evidence_audit(lead_classification)
    else:
        draft = build_manual_outreach_message(
            business_name=business_name,
            classification=classification,
            channel=draft_channel,
            establishment_profile=profile["effective"],
            include_inperson_line=include_inperson,
            lead_dossier=record.get("lead_evidence_dossier") or {},
            sample_menu_url=sample_menu_url,
        )

    # Update lead record
    record["outreach_classification"] = classification
    record["outreach_assets_selected"] = [str(p) for p in assets]
    record["message_variant"] = f"{draft_channel}:{classification}:{profile['effective']}"
    if record.get("outreach_status") == "new":
        record["outreach_status"] = "draft"
        record["status_history"].append({
            "status": "draft",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    if regenerate:
        record["outreach_draft_body"] = None
        record["outreach_draft_english_body"] = None
        record["outreach_draft_subject"] = None
        record["outreach_draft_manually_edited"] = False
        record["outreach_draft_edited_at"] = None
        _clear_tailoring_audit(record, "outreach_regenerated")

    record = _refresh_operator_lead(record)
    persist_lead_record(record, state_root=STATE_ROOT)

    subject = draft["subject"]
    body = draft["body"]
    english_body = draft["english_body"]
    generated_subject = subject
    generated_body = body
    generated_english_body = english_body
    saved_assets = record.get("outreach_assets_selected") or []
    if not regenerate:
        subject = record.get("outreach_draft_subject") or subject
        body = record.get("outreach_draft_body") or body
        english_body = record.get("outreach_draft_english_body") or english_body
        if saved_assets:
            assets = [Path(p) for p in saved_assets]
        if not assets and _draft_claims_attached_sample(subject, body, english_body):
            subject = generated_subject
            body = generated_body
            english_body = generated_english_body
            record["outreach_draft_body"] = None
            record["outreach_draft_english_body"] = None
            record["outreach_draft_subject"] = None
            record["outreach_draft_manually_edited"] = False
            record["outreach_draft_edited_at"] = None
            _clear_tailoring_audit(record, "unsafe_saved_draft_reset")
            record = _refresh_operator_lead(record)
            persist_lead_record(record, state_root=STATE_ROOT)
    asset_details = describe_outreach_assets(
        assets,
        classification=classification,
        establishment_profile=profile["effective"],
    )

    action = "draft_generated" if regenerate else "email_previewed"
    _log(action, f"classification={classification}", lead_id=lead_id)

    # Build shop-specific preview from lead evidence
    from pipeline.preview import build_shop_preview_from_record
    shop_preview_html = build_shop_preview_from_record(record=record)
    proof_items = record.get("proof_items") or (record.get("lead_evidence_dossier") or {}).get("proof_items") or []

    return {
        "classification": classification,
        "assets": [str(p) for p in assets],
        "asset_details": asset_details["assets"],
        "asset_strategy_label": asset_details["strategy_label"],
        "asset_strategy_note": asset_details["strategy_note"],
        "subject": subject,
        "body": body,
        "english_body": english_body,
        "preview_html": _dashboard_email_preview_html(
            body,
            include_menu_image=draft["include_menu_image"],
            include_machine_image=record.get("outreach_include_machine_image", draft["include_machine_image"]),
            business_name=business_name,
            establishment_profile=profile["effective"],
        ),
        "shop_preview_html": shop_preview_html,
        "include_inperson": include_inperson,
        "include_menu_image": draft["include_menu_image"],
        "include_machine_image": record.get("outreach_include_machine_image", draft["include_machine_image"]),
        "business_name": business_name,
        "email": record.get("email", ""),
        "contacts": contacts,
        "primary_contact": primary_contact,
        "draft_channel": draft_channel,
        "establishment_profile": profile["effective"],
        "establishment_profile_label": profile["label"],
        "establishment_profile_mode": profile["mode"],
        "establishment_profile_confidence": profile["confidence"],
        "establishment_profile_evidence": profile["evidence"],
        "establishment_profile_source_urls": profile["source_urls"],
        "establishment_profile_override": profile["override"],
        "establishment_profile_override_note": profile["override_note"],
        "send_enabled": bool(send_enabled and not test_fixture_label),
        "contact_action": contact_action,
        "contact_action_note": contact_action_note,
        "has_saved_draft": bool(record.get("outreach_draft_body") or record.get("outreach_draft_english_body")),
        "send_blocked": bool(test_fixture_label) or record.get("outreach_status") in BLOCKED_SEND_STATUSES,
        "review_only": record.get("launch_readiness_status") != READINESS_READY,
        "outreach_status": record.get("outreach_status"),
        "operator_state": record.get("operator_state"),
        "operator_reason": record.get("operator_reason"),
        "contact_policy_evidence": record.get("contact_policy_evidence") or {},
        "launch_readiness_status": record.get("launch_readiness_status"),
        "launch_readiness_reasons": record.get("launch_readiness_reasons") or [],
        "lead_evidence_dossier": record.get("lead_evidence_dossier") or {},
        "proof_items": proof_items,
        "operator_review_outcome": record.get("operator_review_outcome", ""),
        "operator_review_outcome_label": _label_from_map(record.get("operator_review_outcome"), LEAD_REVIEW_OUTCOME_LABELS, default="Not Reviewed"),
        "operator_review_note": record.get("operator_review_note", ""),
        "operator_reviewed_at": record.get("operator_reviewed_at", ""),
        "pitch_pack_ready_no_send": bool(record.get("pitch_pack_ready_no_send")),
        "pitch_pack_ready_at": record.get("pitch_pack_ready_at", ""),
        "send_readiness": _send_readiness_for_record(record, subject=subject, body=body, assets=[str(p) for p in assets]),
        "final_send_check": {
            "status": "passed" if _validate_tailoring_audit(record, subject=subject, body=body, assets=[str(p) for p in assets])["valid"] else "not_checked",
            "checked_at": record.get("send_ready_checked_at", ""),
            "checklist": record.get("send_ready_checklist") or [],
            "tailoring_audit": record.get("tailoring_audit") or {},
        },
        "review_status": record.get("review_status", "pending"),
        "review_status_label": _dashboard_state_label(record.get("review_status"), default="Pending"),
        "message_variant": record.get("message_variant", ""),
        "sample_menu_url": sample_menu_url,
        "generic_demo": sample_result,
        "is_test_fixture": bool(test_fixture_label),
        "test_fixture_label": test_fixture_label,
    }


@app.post("/api/draft/{lead_id}")
async def api_save_draft(lead_id: str, request: Request):
    """Save a draft for a lead (subject, body, edited fields)."""
    from pipeline.record import load_lead, persist_lead_record

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")

    body = await request.json()
    record["outreach_draft_body"] = body.get("body", "")
    record["outreach_draft_english_body"] = body.get("english_body", "")
    record["outreach_draft_subject"] = body.get("subject", "")
    record["outreach_draft_edited_at"] = datetime.now(timezone.utc).isoformat()
    record["outreach_draft_manually_edited"] = True

    # Persist draft assets and toggles
    if "assets" in body:
        record["outreach_assets_selected"] = _safe_draft_assets_for_record(record, body["assets"])
    if "include_inperson" in body:
        record["outreach_include_inperson"] = body["include_inperson"]
    if "include_machine_image" in body:
        record["outreach_include_machine_image"] = body["include_machine_image"]
    _clear_tailoring_audit(record, "draft_saved")

    record = _refresh_operator_lead(record)
    persist_lead_record(record, state_root=STATE_ROOT)
    _log("draft_saved", lead_id=lead_id)

    return {"status": "saved"}


@app.post("/api/translate-draft")
async def api_translate_draft(request: Request):
    """Translate the editable English draft into Japanese and render preview HTML."""
    body = await request.json()
    english_body = _normalise_body(body.get("english_body", ""))
    business_name = body.get("business_name", "").strip()
    classification = body.get("classification", "menu_only")
    establishment_profile = str(body.get("establishment_profile") or "unknown").strip()
    draft_channel = str(body.get("draft_channel") or "email").strip().lower()
    include_inperson = body.get("include_inperson", True)
    include_menu_image = bool(body.get("include_menu_image", True))
    include_machine_image = bool(body.get("include_machine_image", False))
    sample_menu_url = str(body.get("sample_menu_url") or "").strip()
    city = str(body.get("city") or "").strip()

    if not english_body:
        raise HTTPException(status_code=400, detail="English body required")
    if not business_name:
        raise HTTPException(status_code=400, detail="Restaurant name required")

    from pipeline.outreach import build_manual_outreach_message, build_outreach_email

    candidate_profiles = [establishment_profile] if establishment_profile and establishment_profile != "unknown" else [
        "unknown",
        "ramen",
        "izakaya",
    ]
    japanese_body = ""
    normalised_english_body = _normalise_body(english_body)
    for candidate_profile in candidate_profiles:
        if draft_channel == "email":
            candidate_draft = build_outreach_email(
                business_name=business_name,
                classification=classification,
                establishment_profile=candidate_profile,
                include_inperson_line=include_inperson,
                city=city,
            )
        else:
            candidate_draft = build_manual_outreach_message(
                business_name=business_name,
                classification=classification,
                channel=draft_channel,
                establishment_profile=candidate_profile,
                include_inperson_line=include_inperson,
                sample_menu_url=sample_menu_url,
            )
        if normalised_english_body == _normalise_body(candidate_draft["english_body"]):
            japanese_body = candidate_draft["body"]
            break

    if not japanese_body:
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail="OPENROUTER_API_KEY not configured; cannot translate edited English draft",
            )

        from pipeline.llm_client import call_llm

        try:
            japanese_body = call_llm(
                model="google/gemini-2.0-flash-001",
                system=(
                    "You translate operator-edited English cold outreach emails into polite, natural Japanese. "
                    "Keep the restaurant name exactly as provided, without translating, romanizing, or changing it. "
                    "Preserve line breaks, Chris（クリス） signature, and polite tone. "
                    "Do not mention AI, automation, internal tools, or anything not present in the English source. "
                    "Return only the Japanese email body, no subject and no commentary."
                ),
                user=(
                    f"Restaurant name that must remain exact: {business_name}\n\n"
                    f"English body to translate:\n{english_body}"
                ),
                api_key=api_key,
                max_tokens=1400,
            ).strip()
        except Exception as exc:
            _log("draft_translation_failed", str(exc)[:200])
            raise HTTPException(status_code=502, detail=f"Draft translation failed: {exc}")

        if not japanese_body:
            raise HTTPException(status_code=502, detail="Draft translation returned empty body")

        if business_name not in japanese_body:
            parts = japanese_body.split("\n\n", 1)
            rest = parts[1] if len(parts) > 1 else japanese_body
            japanese_body = f"{business_name} ご担当者様\n\n{rest}"

    return {
        "body": japanese_body,
        "preview_html": _dashboard_email_preview_html(
            japanese_body,
            include_menu_image=include_menu_image,
            include_machine_image=include_machine_image,
            business_name=business_name,
            establishment_profile=establishment_profile,
        ),
    }


async def _send_lead_email_payload(
    lead_id: str,
    *,
    email: str = "",
    subject: str = "",
    email_body: str = "",
    asset_paths: list[str] | None = None,
    include_machine_image: bool | None = None,
    require_send_ready: bool = False,
) -> dict[str, Any]:
    """Send one lead email using either explicit payload fields or saved draft fields."""
    from pipeline.record import authoritative_business_name, load_lead, persist_lead_record
    from pipeline.constants import OUTREACH_STATUS_SENT, MAX_SENDS_PER_DAY

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")
    business_name = authoritative_business_name(record)

    fixture_label = _test_fixture_label_for_record(record)
    if fixture_label:
        raise HTTPException(status_code=403, detail=f"{fixture_label}: sending is disabled")

    if record.get("outreach_status") == "do_not_contact":
        raise HTTPException(status_code=403, detail="Lead is marked Do Not Contact")

    # Block re-sending to already-contacted businesses
    if record.get("outreach_status") in BLOCKED_SEND_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Lead already has status '{record.get('outreach_status')}' — cannot re-send",
        )

    to_email = email or str(record.get("email") or "")
    subject = subject or str(record.get("outreach_draft_subject") or "")
    email_body = email_body or str(record.get("outreach_draft_body") or "")

    if not to_email:
        raise HTTPException(status_code=400, detail="Email address required")
    if not _valid_email(to_email):
        raise HTTPException(status_code=400, detail="Recipient email address is invalid")

    if not subject:
        raise HTTPException(status_code=400, detail="Subject required")

    if not email_body:
        raise HTTPException(status_code=400, detail="Email body required")
    padded_copy = f" {subject}\n{email_body} ".lower()
    banned_terms = [term.strip() for term in FORBIDDEN_FINAL_CHECK_TERMS if term in padded_copy]
    if banned_terms:
        raise HTTPException(status_code=422, detail=f"Outbound copy contains banned terms: {', '.join(sorted(set(banned_terms)))}")
    if "qr" not in padded_copy or ("show staff" not in padded_copy and "スタッフ" not in email_body):
        raise HTTPException(status_code=422, detail="Outbound copy must be regenerated with QR-first Show Staff List wording")

    normalised_to = to_email.strip().lower()
    is_business_send = _is_lead_business_recipient(lead_id, normalised_to)
    is_test_send = not is_business_send
    if is_test_send and not _is_test_recipient_email(normalised_to):
        raise HTTPException(status_code=403, detail="Test sends are only allowed to chris@webrefurb.com")
    if is_business_send:
        from pipeline.launch_freeze import LaunchFreezeError, assert_launch_not_frozen

        try:
            assert_launch_not_frozen(state_root=STATE_ROOT)
        except LaunchFreezeError as exc:
            raise HTTPException(status_code=423, detail=f"launch_frozen:{exc}") from exc
        require_send_ready = True
        if record.get("manual_real_send_approved") is not True:
            raise HTTPException(status_code=422, detail="Lead is not send-ready: manual_real_send_approval_missing")
    else:
        require_send_ready = False
    if require_send_ready:
        if record.get("send_ready_checked") is not True:
            raise HTTPException(status_code=422, detail="Lead is not send-ready: final_check_missing")
        gate = _send_readiness_for_record(
            record,
            recipient=normalised_to,
            subject=subject,
            body=email_body,
            assets=asset_paths,
            include_machine_image=include_machine_image,
        )
        if gate["status"] != "ready_to_send":
            raise HTTPException(status_code=422, detail=f"Lead is not send-ready: {', '.join(gate['reasons'])}")
    if is_business_send:
        from pipeline.lead_dossier import ensure_lead_dossier, READINESS_READY
        from pipeline.operator_state import OPERATOR_READY

        record = ensure_lead_dossier(record)
        if record.get("operator_state") != OPERATOR_READY:
            persist_lead_record(record, state_root=STATE_ROOT)
            raise HTTPException(
                status_code=422,
                detail=f"Lead is not launch-ready for outreach: {record.get('operator_reason') or 'Review this record before outreach.'}",
            )
        if record.get("launch_readiness_status") != READINESS_READY:
            persist_lead_record(record, state_root=STATE_ROOT)
            reasons = ", ".join(record.get("launch_readiness_reasons") or ["not_ready"])
            raise HTTPException(status_code=422, detail=f"Lead is not launch-ready for outreach: {reasons}")

    from pipeline.models import QualificationResult
    from pipeline.outreach import classify_business, select_outreach_assets

    q = QualificationResult(
        lead=record["lead"],
        rejection_reason=record.get("rejection_reason"),
        business_name=business_name,
        menu_evidence_found=record.get("menu_evidence_found", True),
        machine_evidence_found=record.get("machine_evidence_found", False),
    )
    classification = record.get("outreach_classification") or classify_business(q)
    profile = _effective_establishment_profile(record)
    required_assets = list(record.get("outreach_assets_selected") or [])
    if not required_assets:
        required_assets = [
            str(p) for p in select_outreach_assets(
                classification,
                establishment_profile=profile["effective"],
            )
        ]
    if asset_paths is None:
        asset_paths = record.get("outreach_assets_selected") or required_assets

    missing_required = [p for p in required_assets if p not in asset_paths]
    if missing_required:
        names = ", ".join(Path(p).name for p in missing_required)
        raise HTTPException(status_code=400, detail=f"Required attachment missing: {names}")

    missing_files = [p for p in asset_paths if not Path(p).exists()]
    if missing_files:
        names = ", ".join(Path(p).name for p in missing_files)
        raise HTTPException(status_code=400, detail=f"Attachment file not found: {names}")

    # --- Evidence-gated send gate -------------------------------------------
    # No automatic outbound email may be sent without an evidence audit.
    evidence_audit = record.get("evidence_audit") or {}
    if not evidence_audit.get("selected_template"):
        # Pre-existing lead without audit: re-classify now
        from pipeline.evidence_classifier import classify_lead as _evidence_classify
        from pipeline.outreach import build_evidence_gated_email as _build_evidence_email

        evidence_payload = _evidence_classifier_payload(
            record,
            business_name=business_name,
            classification=classification,
            profile=profile["effective"],
        )
        classification_obj = _evidence_classify(evidence_payload)
        evidence_email = _build_evidence_email(classification_obj)
        evidence_audit = _build_evidence_audit(classification_obj)
        record["evidence_audit"] = evidence_audit
        persist_lead_record(record, state_root=STATE_ROOT)

        if evidence_email is None:
            raise HTTPException(
                status_code=422,
                detail=f"Evidence-gated classifier blocked send: {evidence_audit.get('skip_reason', 'unknown')}",
            )

        # Use the freshly rendered email
        subject = subject or evidence_email.get("subject", "")
        email_body = email_body or evidence_email.get("body", "")

    # Block sends that the evidence audit marks as skip or human-review
    if evidence_audit.get("selected_template") == "skip":
        raise HTTPException(
            status_code=422,
            detail=f"Evidence audit blocks send (skip): {evidence_audit.get('skip_reason', 'unknown')}",
        )
    if evidence_audit.get("human_review_required"):
        raise HTTPException(
            status_code=422,
            detail="Evidence audit requires human review before sending",
        )

    # Send-time claim validation on the final email body
    try:
        _validate_email_claims(email_body, evidence_audit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Derive image flags from evidence audit
    tmpl = evidence_audit.get("selected_template", "")
    include_menu_image = False
    expected_machine_image = False
    if include_machine_image is None:
        include_machine_image = record.get("outreach_include_machine_image", expected_machine_image)
    if expected_machine_image and not include_machine_image:
        raise HTTPException(status_code=400, detail=f"Required machine image missing for {classification} lead")

    # Rate limit check
    today_sends = _count_today_sends()
    if today_sends >= MAX_SENDS_PER_DAY:
        raise HTTPException(
            status_code=429,
            detail=f"Daily send limit reached ({today_sends}/{MAX_SENDS_PER_DAY})",
        )

    _log("send_attempted", f"to={to_email}", lead_id=lead_id)

    menu_html = None
    if include_menu_image:
        menu_html = _menu_template_for_profile(profile["effective"])
        if not menu_html.exists():
            raise HTTPException(status_code=400, detail="Required menu preview image source file not found")

    try:
        result = await _send_email_resend(
            to=to_email,
            subject=subject,
            body=email_body,
            attachments=asset_paths,
            menu_html_path=str(menu_html) if menu_html and menu_html.exists() else None,
            machine_html_path=None,
            include_menu_image=include_menu_image,
            include_machine_image=include_machine_image,
            business_name=business_name,
        )
    except Exception as exc:
        _log("send_failed", str(exc)[:200], lead_id=lead_id)
        # Never auto-retry
        raise HTTPException(status_code=502, detail=f"Send failed: {exc}")

    if is_business_send:
        # Update lead only for real business sends.
        record["outreach_status"] = OUTREACH_STATUS_SENT
        record["outreach_sent_at"] = datetime.now(timezone.utc).isoformat()
        record["outreach_draft_body"] = email_body
        record["status_history"].append({
            "status": OUTREACH_STATUS_SENT,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        record = _refresh_operator_lead(record)
        persist_lead_record(record, state_root=STATE_ROOT)

    # Track sent email
    _save_sent_email(
        lead_id, to_email, subject, email_body,
        classification=record.get("outreach_classification", ""),
        test_send=is_test_send,
        attachment_metadata=_sent_record_attachment_metadata(
            send_result=result,
            requested_assets=asset_paths,
            menu_html_path=str(menu_html) if menu_html and menu_html.exists() else "",
            machine_html_path=str(machine_html) if machine_html and machine_html.exists() else "",
            include_menu_image=include_menu_image,
            include_machine_image=include_machine_image,
        ),
        tailoring_audit=record.get("tailoring_audit") or {},
    )

    _log("send_succeeded", f"sends_today={today_sends + 1} test={is_test_send}", lead_id=lead_id)

    return {"status": "test_sent" if is_test_send else "sent", "sends_today": today_sends + 1}


@app.post("/api/send/{lead_id}")
async def api_send(lead_id: str, request: Request):
    """Send outreach email via Resend."""
    body = await request.json()
    if "email" in body and not str(body.get("email") or "").strip():
        raise HTTPException(status_code=400, detail="Email address required")
    if "subject" in body and not str(body.get("subject") or "").strip():
        raise HTTPException(status_code=400, detail="Subject required")
    if "body" in body and not str(body.get("body") or "").strip():
        raise HTTPException(status_code=400, detail="Email body required")
    return await _send_lead_email_payload(
        lead_id,
        email=body.get("email", ""),
        subject=body.get("subject", ""),
        email_body=body.get("body", ""),
        asset_paths=body.get("assets"),
        include_machine_image=body.get("include_machine_image"),
        require_send_ready=True,
    )


@app.get("/api/sent")
async def api_sent():
    """Return all sent emails."""
    sent_dir = STATE_ROOT / "sent"
    if not sent_dir.exists():
        return []
    results = []
    reply_summaries = _reply_summaries_by_lead()
    for path in sorted(sent_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if (
            data.get("test_send")
            or _is_test_recipient_email(data.get("to", ""))
            or not _is_lead_business_recipient(str(data.get("lead_id") or ""), str(data.get("to") or ""))
        ):
            continue
        data["reply_summary"] = reply_summaries.get(str(data.get("lead_id") or ""), {
            "total": 0,
            "open": 0,
            "unread": 0,
            "latest_received_at": "",
            "latest_subject": "",
            "latest_workflow_status": "",
            "latest_action_label": "",
        })
        results.append(data)
    return results


@app.post("/api/translate-reply")
async def api_translate_reply(request: Request):
    """Translate an English reply draft into natural Japanese."""
    body = await request.json()
    english_text = body.get("text", "").strip()
    business_name = body.get("business_name", "")

    if not english_text:
        raise HTTPException(status_code=400, detail="Text required")

    _log("translate_reply", f"len={len(english_text)}")

    try:
        from pipeline.translate_reply import translate_reply
        from pipeline.llm_client import LLMClientError

        japanese = translate_reply(
            english_text,
            business_name=business_name or None,
        )
    except LLMClientError as exc:
        _log("translate_failed", str(exc)[:200])
        raise HTTPException(status_code=502, detail=f"Translation failed: {exc}")

    return {"japanese": japanese}


@app.post("/api/reply/{lead_id}")
async def api_reply(lead_id: str, request: Request):
    """Send a reply to a lead."""
    from pipeline.record import load_lead, persist_lead_record
    from pipeline.constants import OUTREACH_STATUS_REPLIED

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")

    body = await request.json()
    to_email = body.get("email", "")
    reply_body = body.get("body", "")
    in_reply_to = body.get("in_reply_to", "")
    reply_id = str(body.get("reply_id") or "").strip()

    if not to_email or not reply_body:
        raise HTTPException(status_code=400, detail="Email and body required")
    if not _valid_email(to_email):
        raise HTTPException(status_code=400, detail="Recipient email address is invalid")

    _log("reply_sent", f"to={to_email}", lead_id=lead_id)

    try:
        send_result = await _send_email_resend(
            to=to_email,
            subject=f"Re: {body.get('subject', '')}",
            body=reply_body,
            attachments=[],
            in_reply_to=in_reply_to,
        )
    except Exception as exc:
        _log("reply_failed", str(exc)[:200], lead_id=lead_id)
        raise HTTPException(status_code=502, detail=f"Reply failed: {exc}")

    record["outreach_status"] = OUTREACH_STATUS_REPLIED
    record["status_history"].append({
        "status": OUTREACH_STATUS_REPLIED,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    record = _refresh_operator_lead(record)
    persist_lead_record(record, state_root=STATE_ROOT)

    thread_reply_count = 0
    if reply_id:
        thread = _append_operator_reply_to_incoming(
            reply_id,
            lead_id=lead_id,
            to_email=to_email,
            subject=f"Re: {body.get('subject', '')}",
            body=reply_body,
            provider_result=send_result if isinstance(send_result, dict) else {},
        )
        thread_reply_count = len((thread or {}).get("operator_replies") or [])

    return {"status": "replied", "reply_id": reply_id, "thread_reply_count": thread_reply_count}


@app.post("/api/incoming-reply/{lead_id}")
async def api_incoming_reply(lead_id: str, request: Request):
    """Process an incoming reply from a lead. Checks for opt-out tokens."""
    from pipeline.record import load_lead, persist_lead_record
    from pipeline.constants import OPT_OUT_TOKENS, OUTREACH_STATUS_DO_NOT_CONTACT

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")

    body = await request.json()
    reply_text = body.get("body", "")
    channel = _normalise_reply_channel(body.get("channel") or body.get("source") or "email")
    incoming = _save_incoming_reply(
        lead_id=lead_id,
        channel=channel,
        body=reply_text,
        from_email=body.get("from", "") or body.get("from_email", ""),
        subject=body.get("subject", ""),
        business_name=record.get("business_name", ""),
        attachments=body.get("attachments") or body.get("files") or body.get("images"),
    )
    reply_ids = list(record.get("reply_ids") or [])
    if incoming["reply_id"] not in reply_ids:
        reply_ids.append(incoming["reply_id"])
    record["reply_ids"] = reply_ids
    record["latest_reply_id"] = incoming["reply_id"]
    record["latest_reply_intent"] = incoming.get("reply_intent", "")
    record["latest_reply_next_action"] = (incoming.get("next_action") or {}).get("key", "")

    # Check for opt-out tokens in the reply
    opted_out = False
    if reply_text:
        reply_lower = reply_text.lower()
        for token in OPT_OUT_TOKENS:
            if token in reply_text or token.lower() in reply_lower:
                opted_out = True
                break

    if opted_out:
        record["outreach_status"] = OUTREACH_STATUS_DO_NOT_CONTACT
        record["status_history"].append({
            "status": OUTREACH_STATUS_DO_NOT_CONTACT,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "Opted out — incoming reply contained opt-out language",
        })
        record = _refresh_operator_lead(record)
        persist_lead_record(record, state_root=STATE_ROOT)
        _log("opt_out_detected", lead_id=lead_id)
        return {
            "status": "opted_out",
            "outreach_status": OUTREACH_STATUS_DO_NOT_CONTACT,
            "reply_id": incoming["reply_id"],
            "channel": channel,
        }

    record = _refresh_operator_lead(record)
    persist_lead_record(record, state_root=STATE_ROOT)

    return {
        "status": "ok",
        "outreach_status": record.get("outreach_status"),
        "reply_id": incoming["reply_id"],
        "channel": channel,
    }


@app.get("/api/replies")
async def api_replies(channel: str | None = None):
    """Return incoming replies, grouped by e-mail or contact form."""
    selected_channel = _normalise_reply_channel(channel) if channel else ""
    replies = _list_incoming_replies(channel=selected_channel)
    all_replies = _list_incoming_replies()
    counts = {
        "email_unread": sum(1 for reply in all_replies if reply.get("channel") == "email" and not reply.get("read_at")),
        "form_unread": sum(1 for reply in all_replies if reply.get("channel") == "form" and not reply.get("read_at")),
        "email_total": sum(1 for reply in all_replies if reply.get("channel") == "email"),
        "form_total": sum(1 for reply in all_replies if reply.get("channel") == "form"),
    }
    return {"replies": replies, "counts": counts}


@app.get("/api/inbox")
async def api_inbox(channel: str | None = None, status: str | None = None):
    """Return enriched inbound replies as operator conversations."""
    selected_channel = _normalise_reply_channel(channel) if channel else ""
    selected_status = str(status or "").strip()
    return _inbox_payload(channel=selected_channel, status=selected_status)


@app.post("/api/replies/{reply_id}/workflow")
async def api_update_reply_workflow(reply_id: str, request: Request):
    """Update one reply's operator workflow state without losing the raw message."""
    payload = await request.json()
    workflow_status = str(payload.get("workflow_status") or payload.get("status") or "").strip()
    note = str(payload.get("note") or "").strip()
    return _update_incoming_reply_workflow(reply_id, workflow_status=workflow_status, note=note)


@app.get("/api/replies/{reply_id}/assets")
async def api_reply_assets(reply_id: str):
    """Return the owner asset inbox for a reply."""
    from pipeline.production_workflow import load_asset_manifest

    reply = _load_incoming_reply(reply_id)
    if not reply:
        raise HTTPException(status_code=404, detail="reply_not_found")
    manifest = load_asset_manifest(reply_id, state_root=STATE_ROOT)
    return {"reply_id": reply_id, "assets": manifest.get("assets") or []}


@app.post("/api/replies/{reply_id}/assets/{asset_id}/review")
async def api_review_reply_asset(reply_id: str, asset_id: str, request: Request):
    """Save the operator-facing asset status: usable, needs better photo, or not needed."""
    from pipeline.production_workflow import update_asset_operator_status

    payload = await request.json()
    status = str(payload.get("operator_status") or payload.get("status") or "").strip()
    note = str(payload.get("note") or "").strip()
    try:
        manifest = update_asset_operator_status(
            reply_id=reply_id,
            asset_id=asset_id,
            status=status,
            note=note,
            state_root=STATE_ROOT,
        )
    except ValueError as exc:
        status_code = 404 if str(exc) == "asset_not_found" else 422
        raise HTTPException(status_code=status_code, detail=str(exc))
    reply = _load_incoming_reply(reply_id)
    enriched = _enrich_reply_for_inbox(reply or {"reply_id": reply_id})
    return {"status": "ok", "assets": manifest.get("assets") or [], "reply": enriched}


@app.get("/api/replies/{reply_id}/workspace")
async def api_reply_workspace(reply_id: str):
    """Return the structured production workspace for a reply."""
    from pipeline.production_workflow import (
        build_production_workspace,
        build_ticket_machine_mapping,
        extract_structured_menu_content,
        load_asset_manifest,
        recheck_package_fit,
    )

    reply = _load_incoming_reply(reply_id)
    if not reply:
        raise HTTPException(status_code=404, detail="reply_not_found")
    manifest = load_asset_manifest(reply_id, state_root=STATE_ROOT)
    assets = manifest.get("assets") or []
    extracted = extract_structured_menu_content(raw_text=str(reply.get("body") or ""), assets=assets)
    ticket_mapping = build_ticket_machine_mapping(assets=assets)
    package_fit = recheck_package_fit(
        assets=assets,
        current_package_key=str(reply.get("package_key") or ""),
    )
    workspace = build_production_workspace(
        reply=reply,
        assets=assets,
        extracted_content=extracted,
        ticket_mapping=ticket_mapping,
        package_fit=package_fit,
    )
    return {"reply_id": reply_id, "workspace": workspace}


# ---------------------------------------------------------------------------
# Resend webhook — bounce, complaint, delivery events
# ---------------------------------------------------------------------------

@app.post("/api/webhooks/resend")
async def api_resend_webhook(request: Request):
    """Handle inbound webhook events from Resend.

    Processes: email.bounced, email.complained, email.delivered.
    Bounced emails mark the lead as bounced. Complaints mark as do_not_contact.
    """
    import hmac
    import hashlib

    from pipeline.record import load_lead, persist_lead_record
    from pipeline.constants import (
        OUTREACH_STATUS_BOUNCED,
        OUTREACH_STATUS_DO_NOT_CONTACT,
    )

    body = await request.body()
    payload = await request.json()

    # Optional signature verification
    webhook_secret = os.environ.get("RESEND_WEBHOOK_SECRET", "")
    if webhook_secret:
        signature = request.headers.get("svix-signature", "")
        if signature:
            expected = hmac.new(
                webhook_secret.encode(), body, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(f"sha256={expected}", signature):
                raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event_type = payload.get("type", "")
    data = payload.get("data", {})

    if event_type == "email.bounced":
        to_email = str(data.get("to", "")).strip().lower()
        bounce_type = data.get("bounce_type", "permanent")
        _handle_email_bounce(
            to_email=to_email,
            bounce_type=bounce_type,
            details=data,
        )
        _log("email_bounced", f"to={to_email} type={bounce_type}")
        return {"status": "bounced", "email": to_email}

    if event_type == "email.complained":
        to_email = str(data.get("to", "")).strip().lower()
        _handle_email_complaint(to_email=to_email, details=data)
        _log("email_complaint", f"to={to_email}")
        return {"status": "complaint", "email": to_email}

    if event_type == "email.delivered":
        to_email = str(data.get("to", "")).strip().lower()
        _log("email_delivered", f"to={to_email}")
        return {"status": "delivered", "email": to_email}

    return {"status": "ignored", "type": event_type}


def _find_lead_by_email(to_email: str) -> dict[str, Any] | None:
    """Find a lead record by its saved email address."""
    from pipeline.record import list_leads
    leads = list_leads(state_root=STATE_ROOT)
    for record in leads:
        if (record.get("email") or "").strip().lower() == to_email:
            return record
    return None


def _handle_email_bounce(
    *,
    to_email: str,
    bounce_type: str,
    details: dict[str, Any],
) -> None:
    """Mark a lead as bounced when an email bounces."""
    from pipeline.record import load_lead, persist_lead_record
    from pipeline.constants import OUTREACH_STATUS_BOUNCED, OUTREACH_STATUS_INVALID

    record = _find_lead_by_email(to_email)
    if not record:
        return

    status = OUTREACH_STATUS_INVALID if bounce_type == "invalid" else OUTREACH_STATUS_BOUNCED
    record["outreach_status"] = status
    record["status_history"].append({
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": f"Email bounced: {bounce_type}",
        "bounce_details": details,
    })
    record = _refresh_operator_lead(record)
    persist_lead_record(record, state_root=STATE_ROOT)


def _handle_email_complaint(
    *,
    to_email: str,
    details: dict[str, Any],
) -> None:
    """Mark a lead as do_not_contact when a spam complaint is received."""
    from pipeline.record import load_lead, persist_lead_record
    from pipeline.constants import OUTREACH_STATUS_DO_NOT_CONTACT

    record = _find_lead_by_email(to_email)
    if not record:
        return

    record["outreach_status"] = OUTREACH_STATUS_DO_NOT_CONTACT
    record["status_history"].append({
        "status": OUTREACH_STATUS_DO_NOT_CONTACT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": "Spam complaint received via Resend webhook",
        "complaint_details": details,
    })
    record = _refresh_operator_lead(record)
    persist_lead_record(record, state_root=STATE_ROOT)


@app.post("/api/leads/{lead_id}/mark-unreachable")
async def api_mark_unreachable(lead_id: str, request: Request):
    """Operator marks a lead as bounced/invalid/unreachable for non-email channels."""
    from pipeline.record import load_lead, persist_lead_record
    from pipeline.constants import OUTREACH_STATUS_BOUNCED, OUTREACH_STATUS_INVALID

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")

    body = await request.json()
    reason = str(body.get("reason") or "bounced").strip()
    note = str(body.get("note") or "").strip()

    status = OUTREACH_STATUS_INVALID if reason == "invalid" else OUTREACH_STATUS_BOUNCED
    record["outreach_status"] = status
    record["status_history"].append({
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": note or f"Operator marked as {reason}",
    })
    record = _refresh_operator_lead(record)
    persist_lead_record(record, state_root=STATE_ROOT)
    _log("marked_unreachable", f"reason={reason}", lead_id=lead_id)
    return {"status": status, "lead_id": lead_id}


@app.get("/api/qr-menus")
async def api_qr_menus():
    """List live/draft QR menus for the operator dashboard."""
    records: list[dict[str, Any]] = []
    root = STATE_ROOT / "qr_menus"
    if not root.exists():
        return {"menus": []}

    for record_path in sorted(root.glob("*/menu_record.json")):
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        menu_id = str(record.get("menu_id") or record_path.parent.name)
        manifest_path = QR_DOCS_ROOT / "menus" / menu_id / "manifest.json"
        manifest: dict[str, Any] = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                manifest = {}
        health_path = STATE_ROOT / "qr_health" / f"{menu_id}.json"
        health: dict[str, Any] = {}
        if health_path.exists():
            try:
                health = json.loads(health_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                health = {}
        audit_path = STATE_ROOT / "qr_menus" / menu_id / "audit_log.jsonl"
        audit: list[dict[str, Any]] = []
        if audit_path.exists():
            for line in audit_path.read_text(encoding="utf-8").splitlines()[-8:]:
                try:
                    audit.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        records.append({
            **record,
            "menu_id": menu_id,
            "live_url": f"https://webrefurb.com/menus/{menu_id}/" if manifest.get("current_version") else "",
            "current_version": manifest.get("current_version", ""),
            "versions": manifest.get("versions", record.get("versions", [])),
            "status": manifest.get("status", "draft"),
            "health": health,
            "audit": audit,
        })
    return {"menus": records}


@app.get("/api/packages")
async def api_packages():
    """Return the finalized paid package registry."""
    from pipeline.package_export import package_registry

    return {"packages": package_registry()}


def _order_path(order_id: str) -> Path:
    safe_id = str(order_id or "").strip()
    if not re.fullmatch(r"ord-[a-zA-Z0-9_-]{4,64}", safe_id):
        raise HTTPException(status_code=400, detail="Invalid order id")
    return STATE_ROOT / "orders" / f"{safe_id}.json"


def _load_order_record(order_id: str) -> dict[str, Any]:
    path = _order_path(order_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Order not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_order_record(order: dict[str, Any]) -> dict[str, Any]:
    from pipeline.utils import write_json

    order["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json(_order_path(str(order.get("order_id") or "")), order)
    return order


@app.get("/api/orders")
async def api_orders():
    """Return paid order records for quote/payment/intake tracking."""
    orders_dir = STATE_ROOT / "orders"
    records: list[dict[str, Any]] = []
    for path in sorted(orders_dir.glob("*.json"), reverse=True) if orders_dir.exists() else []:
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return {"orders": records}


@app.post("/api/orders")
async def api_create_order(request: Request):
    """Create a quote/order record from a lead and selected package."""
    from pipeline.quote import create_order, write_order_artifacts
    from pipeline.record import load_lead
    from pipeline.utils import write_json

    body = await request.json()
    lead_id = str(body.get("lead_id") or "").strip()
    package_key = str(body.get("package_key") or "").strip()
    lead = load_lead(lead_id, state_root=STATE_ROOT) if lead_id else None
    business_name = str(body.get("business_name") or (lead or {}).get("business_name") or "").strip()
    if not business_name:
        raise HTTPException(status_code=422, detail="business_name is required")
    try:
        order_model = create_order(
            lead_id=lead_id,
            business_name=business_name,
            package_key=package_key,
            is_custom=bool(body.get("is_custom")),
            custom_price_yen=int(body["custom_price_yen"]) if str(body.get("custom_price_yen") or "").strip() else None,
            custom_reason=str(body.get("custom_reason") or ""),
        )
        artifact_paths = write_order_artifacts(state_root=STATE_ROOT, order=order_model)
        order_model.artifact_paths = artifact_paths
        order = order_model.to_dict()
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    write_json(_order_path(order["order_id"]), order)
    _log("order_created", f"package={package_key}", lead_id=lead_id)
    return order


@app.get("/api/orders/{order_id}")
async def api_get_order(order_id: str):
    from pipeline.production_workflow import order_stage_status

    order = _load_order_record(order_id)
    order["workflow_stages"] = order_stage_status(order, has_reply=bool(order.get("reply_ids")))
    return order


@app.post("/api/orders/{order_id}/quote-sent")
async def api_mark_quote_sent(order_id: str, request: Request):
    order = _load_order_record(order_id)
    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()
    order["state"] = "quote_sent"
    order["quote_sent_at"] = now
    order.setdefault("state_history", []).append({
        "state": "quote_sent",
        "timestamp": now,
        "note": str(body.get("note") or "Quote sent to owner"),
    })
    return _write_order_record(order)


@app.post("/api/orders/{order_id}/payment-pending")
async def api_mark_payment_pending(order_id: str, request: Request):
    order = _load_order_record(order_id)
    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()
    payment = dict(order.get("payment") or {})
    payment.update({
        "method": str(body.get("method") or payment.get("method") or "bank_transfer"),
        "status": "pending",
        "amount_yen": int(body.get("amount_yen") or payment.get("amount_yen") or 0),
        "reference": str(body.get("reference") or payment.get("reference") or ""),
        "invoice_number": str(body.get("invoice_number") or payment.get("invoice_number") or ""),
        "invoice_registration_number": str(body.get("invoice_registration_number") or payment.get("invoice_registration_number") or ""),
    })
    order["payment"] = payment
    order["state"] = "payment_pending"
    order.setdefault("state_history", []).append({
        "state": "payment_pending",
        "timestamp": now,
        "note": str(body.get("note") or "Payment instructions sent"),
    })
    return _write_order_record(order)


@app.post("/api/orders/{order_id}/payment")
async def api_confirm_order_payment(order_id: str, request: Request):
    order = _load_order_record(order_id)
    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()
    payment = dict(order.get("payment") or {})
    payment.update({
        "method": str(body.get("method") or payment.get("method") or "bank_transfer"),
        "status": "confirmed",
        "amount_yen": int(body.get("amount_yen") or payment.get("amount_yen") or 0),
        "reference": str(body.get("reference") or payment.get("reference") or ""),
        "paid_at": str(body.get("paid_at") or payment.get("paid_at") or now),
        "confirmed_at": now,
        "confirmed_by": str(body.get("confirmed_by") or "operator"),
        "invoice_number": str(body.get("invoice_number") or payment.get("invoice_number") or ""),
        "invoice_registration_number": str(body.get("invoice_registration_number") or payment.get("invoice_registration_number") or ""),
    })
    order["payment"] = payment
    order["state"] = "paid"
    order.setdefault("state_history", []).append({"state": "paid", "timestamp": now, "note": "Payment confirmed"})
    written = _write_order_record(order)
    try:
        from pipeline.quote import order_from_dict, write_order_artifacts
        written["artifact_paths"] = write_order_artifacts(state_root=STATE_ROOT, order=order_from_dict(written))
        written = _write_order_record(written)
    except Exception:
        pass
    return written


@app.post("/api/orders/{order_id}/intake")
async def api_update_order_intake(order_id: str, request: Request):
    order = _load_order_record(order_id)
    body = await request.json()
    intake = dict(order.get("intake") or {})
    for key in (
        "full_menu_photos",
        "structured_options",
        "price_confirmation",
        "dietary_ingredient_notes",
        "qr_sign_confirmation",
        "business_contact_confirmed",
    ):
        if key in body:
            intake[key] = bool(body.get(key))
    if "notes" in body:
        intake["notes"] = str(body.get("notes") or "")
    intake["is_complete"] = all(bool(intake.get(key)) for key in (
        "full_menu_photos",
        "price_confirmation",
        "qr_sign_confirmation",
        "business_contact_confirmed",
    ))
    order["intake"] = intake
    if intake["is_complete"] and order.get("state") in {"paid", "intake_needed"}:
        order["state"] = "in_production"
        order.setdefault("state_history", []).append({
            "state": "in_production",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "Intake complete",
        })
    return _write_order_record(order)


@app.post("/api/orders/{order_id}/production-qa")
async def api_record_production_qa(order_id: str, request: Request):
    """Record the pre-owner-preview QA checklist."""
    from pipeline.production_workflow import evaluate_pre_owner_preview_qa

    order = _load_order_record(order_id)
    body = await request.json()
    qa = evaluate_pre_owner_preview_qa(body if isinstance(body, dict) else {})
    order["production_qa"] = qa
    if qa["ok"] and order.get("state") == "in_production":
        order.setdefault("state_history", []).append({
            "state": "production_qa_passed",
            "timestamp": qa["checked_at"],
            "note": "Pre-owner-preview QA passed",
        })
    return _write_order_record(order)


@app.post("/api/orders/{order_id}/owner-review")
async def api_mark_owner_review(order_id: str, request: Request):
    order = _load_order_record(order_id)
    body = await request.json()
    from pipeline.quote import can_approve_production, order_from_dict

    ok, blockers = can_approve_production(order_from_dict(order))
    production_qa = order.get("production_qa") or {}
    if not bool(production_qa.get("ok")):
        blockers.append("production_qa_not_passed")
    if not ok:
        raise HTTPException(status_code=409, detail={"blockers": blockers})
    if blockers:
        raise HTTPException(status_code=409, detail={"blockers": blockers})

    now = datetime.now(timezone.utc).isoformat()
    order["state"] = "owner_review"
    order.setdefault("state_history", []).append({
        "state": "owner_review",
        "timestamp": now,
        "note": str(body.get("note") or "Output sent for owner review"),
    })
    return _write_order_record(order)


@app.post("/api/orders/{order_id}/corrections")
async def api_create_order_correction(order_id: str, request: Request):
    """Convert owner correction requests into structured tasks."""
    from pipeline.production_workflow import build_correction_task

    order = _load_order_record(order_id)
    body = await request.json()
    task_type = str(body.get("task_type") or "").strip()
    try:
        task = build_correction_task(task_type, body if isinstance(body, dict) else {})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    corrections = list(order.get("correction_tasks") or [])
    corrections.append(task)
    order["correction_tasks"] = corrections
    revisions = dict(order.get("revisions") or {})
    if task["task_type"] != "approve_as_is":
        revisions["current_round"] = int(revisions.get("current_round") or 0) + 1
    order["revisions"] = revisions
    return _write_order_record(order)


@app.post("/api/orders/{order_id}/owner-approval")
async def api_record_owner_approval(order_id: str, request: Request):
    order = _load_order_record(order_id)
    body = await request.json()
    if order.get("state") != "owner_review":
        raise HTTPException(status_code=409, detail={"blockers": [f"order_state_not_owner_review:{order.get('state')}"]})
    payment = order.get("payment") or {}
    intake = order.get("intake") or {}
    intake_complete = bool(intake.get("is_complete")) or all(
        bool(intake.get(key))
        for key in ("full_menu_photos", "price_confirmation", "qr_sign_confirmation", "business_contact_confirmed")
    )
    blockers: list[str] = []
    if str(payment.get("status") or "") != "confirmed":
        blockers.append("payment_not_confirmed")
    if not intake_complete:
        blockers.append("owner_intake_incomplete")
    if not bool(order.get("privacy_note_accepted") or body.get("privacy_note_accepted")):
        blockers.append("privacy_note_not_accepted")
    if blockers:
        raise HTTPException(status_code=409, detail={"blockers": blockers})

    now = datetime.now(timezone.utc).isoformat()
    approval = dict(order.get("approval") or {})
    approval.update({
        "approved": bool(body.get("approved", True)),
        "approver_name": str(body.get("approver_name") or approval.get("approver_name") or ""),
        "approved_package": str(body.get("approved_package") or order.get("package_key") or ""),
        "approved_at": now,
        "source_data_checksum": str(body.get("source_data_checksum") or approval.get("source_data_checksum") or ""),
        "artifact_checksum": str(body.get("artifact_checksum") or approval.get("artifact_checksum") or ""),
        "notes": str(body.get("notes") or approval.get("notes") or ""),
    })
    order["approval"] = approval
    if "privacy_note_accepted" in body:
        order["privacy_note_accepted"] = bool(body.get("privacy_note_accepted"))
    if approval["approved"] and not all([
        approval.get("approver_name"),
        approval.get("approved_package"),
        approval.get("source_data_checksum"),
        approval.get("artifact_checksum"),
    ]):
        raise HTTPException(status_code=422, detail="Owner approval record is incomplete")
    order["state"] = "owner_approved" if approval["approved"] else "owner_review"
    order.setdefault("state_history", []).append({"state": order["state"], "timestamp": now, "note": "Owner output approval recorded"})
    return _write_order_record(order)


@app.post("/api/orders/{order_id}/delivered")
async def api_mark_order_delivered(order_id: str, request: Request):
    order = _load_order_record(order_id)
    body = await request.json()
    from pipeline.quote import can_approve_package, order_from_dict
    from pipeline.final_export_qa import delivery_export_qa_blockers

    if "export_qa" in body:
        order["export_qa"] = body.get("export_qa") or {}
    if "customer_download_url" in body:
        order["customer_download_url"] = str(body.get("customer_download_url") or "")
    if "final_customer_message" in body:
        order["final_customer_message"] = str(body.get("final_customer_message") or "")
    if "print_handoff_record" in body:
        order["print_handoff_record"] = body.get("print_handoff_record") or {}
    if "hosting_support_record" in body:
        order["hosting_support_record"] = body.get("hosting_support_record") or {}

    ok, blockers = can_approve_package(order_from_dict(order))
    blockers.extend(delivery_export_qa_blockers(order))
    if not ok:
        raise HTTPException(status_code=409, detail={"blockers": blockers})
    if blockers:
        raise HTTPException(status_code=409, detail={"blockers": blockers})

    now = datetime.now(timezone.utc).isoformat()
    order["state"] = "delivered"
    order["delivered_at"] = now
    order["delivery_tracking"] = str(body.get("delivery_tracking") or order.get("delivery_tracking") or "")
    order["follow_up_status"] = str(body.get("follow_up_status") or order.get("follow_up_status") or "pending")
    default_follow_up_due = (datetime.now(timezone.utc) + timedelta(days=14)).date().isoformat()
    order["follow_up_due_at"] = str(body.get("follow_up_due_at") or order.get("follow_up_due_at") or default_follow_up_due)
    order.setdefault("state_history", []).append({
        "state": "delivered",
        "timestamp": now,
        "note": str(body.get("note") or "Package delivered"),
    })
    return _write_order_record(order)


@app.get("/api/orders/{order_id}/artifacts")
async def api_order_artifacts(order_id: str):
    order = _load_order_record(order_id)
    artifacts = dict(order.get("artifact_paths") or {})
    result: dict[str, Any] = {"order_id": order_id, "artifacts": artifacts, "contents": {}}
    for key, raw_path in artifacts.items():
        path = Path(str(raw_path))
        if path.exists() and path.is_file():
            result["contents"][key] = path.read_text(encoding="utf-8")
    return result


@app.post("/api/build/{job_id}/order")
async def api_link_build_order(job_id: str, request: Request):
    """Attach a paid order record to an existing build before final export."""
    body = await request.json()
    order_id = str(body.get("order_id") or "").strip()
    _load_order_record(order_id)
    meta_path = STATE_ROOT / "jobs" / f"{job_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Build job not found")
    job = json.loads(meta_path.read_text(encoding="utf-8"))
    job["order_id"] = order_id
    from pipeline.utils import write_json
    write_json(meta_path, job)
    _build_jobs[job_id] = job
    return {"status": "ok", "job_id": job_id, "order_id": order_id}


@app.get("/api/builds")
async def api_builds():
    """Return custom build history for package review."""
    from pipeline.package_export import get_build_history

    return get_build_history(state_root=STATE_ROOT)


@app.post("/api/replies/mark-read")
async def api_mark_replies_read(request: Request):
    """Mark incoming replies read for one channel."""
    body = await request.json()
    channel = _normalise_reply_channel(body.get("channel", "email"))
    updated = _mark_replies_read(channel)
    return {"status": "ok", "channel": channel, "updated": updated}


@app.post("/api/flag-dnc/{lead_id}")
async def api_flag_dnc(lead_id: str, request: Request):
    """Flag or unflag a lead as Do Not Contact."""
    from pipeline.record import load_lead, persist_lead_record
    from pipeline.constants import OUTREACH_STATUS_DO_NOT_CONTACT
    from pipeline.lead_dossier import ensure_lead_dossier

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")

    body = await request.json()
    flag = body.get("flag", True)

    if flag:
        record["outreach_status"] = OUTREACH_STATUS_DO_NOT_CONTACT
        record["status_history"].append({
            "status": OUTREACH_STATUS_DO_NOT_CONTACT,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "Manually flagged Do Not Contact",
        })
        _log("status_changed", "do_not_contact", lead_id=lead_id)
    else:
        record["outreach_status"] = "new"
        record["status_history"].append({
            "status": "new",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "Manually unflagged Do Not Contact",
        })
        _log("status_changed", "new (unflagged DNC)", lead_id=lead_id)

    record = ensure_lead_dossier(record)
    persist_lead_record(record, state_root=STATE_ROOT)
    return _prepare_lead_for_dashboard(record)


@app.post("/api/translate-line")
async def api_translate_line(request: Request):
    """Translate a single Japanese text line to English."""
    body = await request.json()
    text = body.get("text", "")
    if not text:
        return {"translated": ""}

    from pipeline.translate import translate_items
    from pipeline.models import ExtractedItem

    items = [ExtractedItem(name=text, japanese_name=text)]
    translated = translate_items(items)
    return {"translated": translated[0].name if translated else text}


@app.post("/api/build")
async def api_build(
    name: str = Form(...),
    menu_text: str = Form(""),
    notes: str = Form(""),
    lead_id: str = Form(""),
    reply_id: str = Form(""),
    source: str = Form(""),
    package_key: str = Form("english_qr_menu_65k"),
    menu_photos: list[UploadFile] = File(default=[]),
    ticket_photo: UploadFile | None = File(default=None),
):
    """Accept owner materials and create an English QR Menu draft job."""
    from pipeline.constants import ENGLISH_QR_MENU_KEY, PACKAGE_REGISTRY
    from pipeline.qr import QRMenuError, create_qr_draft

    if package_key != ENGLISH_QR_MENU_KEY:
        raise HTTPException(status_code=422, detail="Only english_qr_menu_65k is active")

    job_id = str(uuid.uuid4())[:8]
    job_dir = STATE_ROOT / "uploads" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded files
    photo_paths: list[str] = []
    for photo in menu_photos:
        if photo.filename:
            dest = job_dir / _safe_upload_name(photo.filename)
            content = await photo.read()
            dest.write_bytes(content)
            photo_paths.append(str(dest))

    if reply_id:
        for stored_path in _stored_reply_photo_paths(reply_id):
            if stored_path not in photo_paths:
                photo_paths.append(stored_path)

    if reply_id and not photo_paths:
        raise HTTPException(
            status_code=400,
            detail="No stored reply photos were available for this build.",
        )

    ticket_path: str | None = None
    if ticket_photo and ticket_photo.filename:
        dest = job_dir / f"ticket_{_safe_upload_name(ticket_photo.filename)}"
        content = await ticket_photo.read()
        dest.write_bytes(content)
        ticket_path = str(dest)

    reply = {
        "reply_id": reply_id or f"manual-{job_id}",
        "lead_id": lead_id,
        "business_name": name,
        "subject": "English QR Menu",
        "body": "Please create the English QR menu.",
        "stored_photo_count": len(photo_paths) or (1 if menu_text.strip() else 0),
        "attachments": [{"stored_path": path} for path in photo_paths],
    }
    payload: dict[str, Any] = {
        "restaurant_name": name,
        "raw_text": menu_text,
        "notes": notes,
        "ticket_machine": {"stored_path": ticket_path} if ticket_path else None,
    }
    try:
        result = create_qr_draft(
            reply=reply,
            state_root=STATE_ROOT,
            docs_root=QR_DOCS_ROOT,
            payload=payload,
        )
    except QRMenuError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    _log("qr_build_started", f"name={name[:50]}", lead_id=str(result.get("job_id") or job_id))
    return {**result, "package_label": PACKAGE_REGISTRY[package_key]["label"], "price_yen": PACKAGE_REGISTRY[package_key]["price_yen"]}


@app.get("/api/build/{job_id}/status")
async def api_build_status(job_id: str):
    """Poll build job status."""
    job = _build_jobs.get(job_id)
    if not job:
        # Check disk
        meta_path = STATE_ROOT / "jobs" / f"{job_id}.json"
        if meta_path.exists():
            job = json.loads(meta_path.read_text(encoding="utf-8"))
        else:
            raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/build/{job_id}/preview")
async def api_build_preview(job_id: str):
    """Serve the populated HTML for browser preview."""
    job = _build_jobs.get(job_id)
    if not job:
        meta_path = STATE_ROOT / "jobs" / f"{job_id}.json"
        if meta_path.exists():
            job = json.loads(meta_path.read_text(encoding="utf-8"))
    if not job or job.get("status") not in {"ready_for_review", "completed"}:
        raise HTTPException(status_code=404, detail="Preview not available")

    output_dir = Path(job.get("output_dir", ""))
    preview_path = output_dir / "food_menu.html"
    if not preview_path.exists():
        preview_path = output_dir / "drinks_menu.html"
    if not preview_path.exists():
        raise HTTPException(status_code=404, detail="Preview file not found")

    return FileResponse(str(preview_path), media_type="text/html")


@app.get("/api/build/{job_id}/review")
async def api_build_review(job_id: str):
    """Return package review metadata and validation for a build."""
    from pipeline.package_export import PackageExportError, get_package_review

    try:
        return get_package_review(state_root=STATE_ROOT, job_id=job_id)
    except PackageExportError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/build/{job_id}/approve")
async def api_build_approve(job_id: str, request: Request):
    """Approve package review and create the final customer export."""
    from pipeline.package_export import PackageExportError, approve_package_export

    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        result = approve_package_export(
            state_root=STATE_ROOT,
            job_id=job_id,
            package_key=str((body or {}).get("package_key") or ""),
        )
    except PackageExportError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 422
        raise HTTPException(status_code=status_code, detail=str(exc))

    meta_path = STATE_ROOT / "jobs" / f"{job_id}.json"
    if meta_path.exists():
        _build_jobs[job_id] = json.loads(meta_path.read_text(encoding="utf-8"))
    _log(f"{result.get('package_key', 'package')}_approved", lead_id=job_id)
    return result


@app.get("/api/build/{job_id}/download")
async def api_build_download(job_id: str):
    """Download the approved Package 1 final export."""
    job = _build_jobs.get(job_id)
    if not job:
        meta_path = STATE_ROOT / "jobs" / f"{job_id}.json"
        if meta_path.exists():
            job = json.loads(meta_path.read_text(encoding="utf-8"))
    if not job:
        raise HTTPException(status_code=404, detail="Build job not found")
    if job.get("review_status") != "approved" or job.get("final_export_status") != "ready":
        raise HTTPException(status_code=409, detail="Package export is not approved yet")
    if job.get("export_qa_status") != "passed":
        raise HTTPException(status_code=409, detail="Package export QA has not passed")
    export_path = Path(str(job.get("final_export_path") or ""))
    if not export_path.exists() or not export_path.is_file():
        raise HTTPException(status_code=404, detail="Final export file not found")
    return FileResponse(
        str(export_path),
        media_type="application/zip",
        filename=export_path.name,
    )


@app.get("/api/build/{job_id}/{asset_path:path}", include_in_schema=False)
async def api_build_asset(job_id: str, asset_path: str):
    """Serve generated build assets referenced by the preview HTML."""
    job = _build_jobs.get(job_id)
    if not job:
        meta_path = STATE_ROOT / "jobs" / f"{job_id}.json"
        if meta_path.exists():
            job = json.loads(meta_path.read_text(encoding="utf-8"))
    if not job or job.get("status") not in {"ready_for_review", "completed"}:
        raise HTTPException(status_code=404, detail="Build asset not available")

    output_dir = Path(job.get("output_dir", "")).resolve()
    path = (output_dir / asset_path).resolve()
    try:
        path.relative_to(output_dir)
    except ValueError:
        raise HTTPException(status_code=404, detail="Build asset not found")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Build asset not found")
    return FileResponse(str(path))


@app.post("/api/qr/{reply_id}")
async def api_create_qr(reply_id: str, request: Request):
    """Create a versioned QR menu draft from a QR-ready reply."""
    from pipeline.qr import QRMenuError, create_qr_draft

    try:
        body = await request.json()
    except Exception:
        body = {}

    reply = _load_incoming_reply(reply_id)
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    try:
        return create_qr_draft(
            reply=reply,
            state_root=STATE_ROOT,
            docs_root=QR_DOCS_ROOT,
            payload=body if isinstance(body, dict) else {},
        )
    except QRMenuError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/qr/{job_id}/status")
async def api_qr_status(job_id: str):
    from pipeline.qr import get_qr_job

    job = get_qr_job(state_root=STATE_ROOT, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="QR job not found")
    return job


@app.get("/api/qr/{job_id}/review")
async def api_qr_review(job_id: str):
    from pipeline.qr import QRMenuError, get_qr_review

    try:
        return get_qr_review(state_root=STATE_ROOT, docs_root=QR_DOCS_ROOT, job_id=job_id)
    except QRMenuError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/qr/{job_id}/extract")
async def api_qr_extract(job_id: str, request: Request):
    from pipeline.qr import QRMenuError, complete_qr_extraction

    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        return complete_qr_extraction(
            state_root=STATE_ROOT,
            docs_root=QR_DOCS_ROOT,
            job_id=job_id,
            payload=body if isinstance(body, dict) else {},
        )
    except QRMenuError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/qr/{job_id}/confirm")
async def api_qr_confirm(job_id: str, request: Request):
    from pipeline.qr import QRMenuError, confirm_qr_content

    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        return confirm_qr_content(
            state_root=STATE_ROOT,
            docs_root=QR_DOCS_ROOT,
            job_id=job_id,
            payload=body if isinstance(body, dict) else {},
        )
    except QRMenuError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/qr/{job_id}/sign")
async def api_qr_sign(job_id: str):
    from pipeline.qr import QRMenuError, create_qr_sign

    try:
        return create_qr_sign(state_root=STATE_ROOT, docs_root=QR_DOCS_ROOT, job_id=job_id)
    except QRMenuError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/qr/{job_id}/publish")
async def api_qr_publish(job_id: str):
    from pipeline.qr import QRMenuError, publish_qr_job

    try:
        return publish_qr_job(state_root=STATE_ROOT, docs_root=QR_DOCS_ROOT, job_id=job_id)
    except QRMenuError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/qr/{job_id}/approve")
async def api_qr_approve(job_id: str):
    from pipeline.qr import QRMenuError, approve_qr_package

    try:
        return approve_qr_package(state_root=STATE_ROOT, docs_root=QR_DOCS_ROOT, job_id=job_id)
    except QRMenuError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/qr/{job_id}/download")
async def api_qr_download(job_id: str):
    from pipeline.qr import get_qr_job

    job = get_qr_job(state_root=STATE_ROOT, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="QR job not found")
    if job.get("review_status") != "approved" or job.get("final_export_status") != "ready":
        raise HTTPException(status_code=409, detail="QR package export is not approved yet")
    if job.get("export_qa_status") != "passed":
        raise HTTPException(status_code=409, detail="QR package export QA has not passed")
    export_path = Path(str(job.get("final_export_path") or ""))
    if not export_path.exists() or not export_path.is_file():
        raise HTTPException(status_code=404, detail="Final export file not found")
    return FileResponse(
        str(export_path),
        media_type="application/zip",
        filename=export_path.name,
    )


@app.post("/api/qr/{menu_id}/draft")
async def api_qr_edit_draft(menu_id: str, request: Request):
    from pipeline.qr import QRMenuError, create_edit_draft

    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        return create_edit_draft(
            state_root=STATE_ROOT,
            docs_root=QR_DOCS_ROOT,
            menu_id=menu_id,
            payload=body if isinstance(body, dict) else {},
        )
    except QRMenuError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/qr/{menu_id}/rollback")
async def api_qr_rollback(menu_id: str, request: Request):
    from pipeline.qr import QRMenuError, rollback_qr_menu

    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        return rollback_qr_menu(
            state_root=STATE_ROOT,
            docs_root=QR_DOCS_ROOT,
            menu_id=menu_id,
            version_id=str((body or {}).get("version_id") or ""),
        )
    except QRMenuError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/qr/{menu_id}/health")
async def api_qr_health(menu_id: str):
    from pipeline.qr import check_qr_health

    return check_qr_health(state_root=STATE_ROOT, docs_root=QR_DOCS_ROOT, menu_id=menu_id)


# ---------------------------------------------------------------------------
# Email sending via Resend
# ---------------------------------------------------------------------------

async def _send_email_resend(
    *,
    to: str,
    subject: str,
    body: str,
    attachments: list[str],
    in_reply_to: str = "",
    menu_html_path: str | None = None,
    machine_html_path: str | None = None,
    include_menu_image: bool = True,
    include_machine_image: bool = False,
    business_name: str = "",
) -> dict:
    """Send an email via Resend with CID-embedded inline images + PDF attachments."""
    import asyncio
    import base64
    import resend as _resend
    from pipeline.email_html import (
        build_pitch_email_html,
        build_inline_attachments,
        _ensure_menu_jpeg,
    )

    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        raise RuntimeError("RESEND_API_KEY not configured")

    _resend.api_key = api_key

    from_email = os.environ.get("RESEND_FROM_EMAIL", "chris@webrefurb.com")
    from_name = os.environ.get("RESEND_FROM_NAME", "Chris（クリス）")
    reply_to = os.environ.get("RESEND_REPLY_TO_EMAIL", from_email).strip() or from_email

    with tempfile.TemporaryDirectory(prefix="wrm-email-") as tmp_dir:
        # Render lead-specific HTML templates to JPEG for CID embedding.
        # Uses asyncio.to_thread because Playwright's sync API cannot run
        # inside an async event loop (it raises an error otherwise).
        menu_jpeg, machine_jpeg = await asyncio.to_thread(
            _render_inline_jpegs_sync,
            menu_html_path=menu_html_path if include_menu_image and menu_html_path else None,
            machine_html_path=machine_html_path if include_machine_image and machine_html_path else None,
            business_name=business_name,
            tmp_dir=tmp_dir,
        )

        # Build HTML email body — all images via cid: references
        html_body = build_pitch_email_html(
            text_body=body,
            include_menu_image=bool(menu_jpeg),
            include_machine_image=bool(machine_jpeg),
            locale="ja",
        )

        params: dict[str, Any] = {
            "from": f"{from_name} <{from_email}>",
            "to": [to],
            "subject": subject,
            "text": body,
            "html": html_body,
            "reply_to": reply_to,
        }

        if in_reply_to:
            params["headers"] = {"In-Reply-To": in_reply_to}

        # CID inline attachments only (logo + menu + machine) — no file attachments
        # Cold outreach with PDF attachments looks scammy; inline images are sufficient.
        # PDFs can be sent in follow-up replies after the business expresses interest.
        all_attachments = build_inline_attachments(
            menu_jpeg_path=menu_jpeg,
            machine_jpeg_path=machine_jpeg,
        )

        if all_attachments:
            params["attachments"] = all_attachments

        provider_result = _resend.Emails.send(params)
        attachment_metadata = _inline_attachment_metadata(all_attachments)
        if isinstance(provider_result, dict):
            return {**provider_result, "attachment_metadata": attachment_metadata}
        return {
            "provider_result": provider_result,
            "attachment_metadata": attachment_metadata,
        }


def _personalised_email_html(source_path: str | None, business_name: str, tmp_dir: str, stem: str) -> str | None:
    if not source_path:
        return None
    source = Path(source_path)
    if not source.exists():
        return None
    html_text = source.read_text(encoding="utf-8")
    if business_name:
        html_text = html_text.replace('data-slot="seal-text">見本<', f'data-slot="seal-text">{business_name}<')
    output = Path(tmp_dir) / f"{stem}.html"
    output.write_text(html_text, encoding="utf-8")
    return str(output)


def _render_inline_jpegs_sync(
    *,
    menu_html_path: str | None,
    machine_html_path: str | None,
    business_name: str,
    tmp_dir: str,
) -> tuple[str | None, str | None]:
    """Render personalised HTML templates to JPEG (runs in a thread for async safety)."""
    from pipeline.email_html import _ensure_menu_jpeg

    menu_source = _personalised_email_html(menu_html_path, business_name, tmp_dir, "menu") if menu_html_path else None
    machine_source = _personalised_email_html(machine_html_path, business_name, tmp_dir, "machine") if machine_html_path else None
    menu_jpeg = _ensure_menu_jpeg(menu_source) if menu_source else None
    machine_jpeg = _ensure_menu_jpeg(machine_source) if machine_source else None
    return menu_jpeg, machine_jpeg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_today_sends() -> int:
    """Count emails sent today (JST)."""
    sent_dir = STATE_ROOT / "sent"
    if not sent_dir.exists():
        return 0

    jst = timezone(timedelta(hours=9))
    today = datetime.now(jst).strftime("%Y-%m-%d")

    count = 0
    for path in sent_dir.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if (
            data.get("test_send")
            or _is_test_recipient_email(data.get("to", ""))
            or not _is_lead_business_recipient(str(data.get("lead_id") or ""), str(data.get("to") or ""))
        ):
            continue
        sent_at = data.get("sent_at", "")
        try:
            sent_dt = datetime.fromisoformat(sent_at.replace("Z", "+00:00")).astimezone(jst)
        except ValueError:
            continue
        if sent_dt.strftime("%Y-%m-%d") == today:
            count += 1
    return count


def _professional_attachment_name(path: Path) -> str:
    """Use recipient-friendly sample PDF names without changing source files."""
    lower = path.name.lower()
    if "menu" in lower:
        return "WebRefurb-English-Menu-Sample.pdf"
    return path.name


def _inline_attachment_metadata(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return attachment metadata suitable for records without storing content."""
    import base64
    import hashlib

    metadata: list[dict[str, Any]] = []
    for item in attachments:
        content = str(item.get("content") or "")
        try:
            raw = base64.b64decode(content.encode("ascii"), validate=True) if content else b""
        except Exception:
            raw = b""
        metadata.append({
            "filename": item.get("filename", ""),
            "mime_type": item.get("mime_type", ""),
            "content_id": item.get("content_id", ""),
            "disposition": item.get("disposition", ""),
            "inline": item.get("disposition") == "inline",
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest() if raw else "",
        })
    return metadata


def _sent_record_attachment_metadata(
    *,
    send_result: dict[str, Any] | None,
    requested_assets: list[str] | None,
    menu_html_path: str = "",
    machine_html_path: str = "",
    include_menu_image: bool = False,
    include_machine_image: bool = False,
) -> dict[str, Any]:
    inline_attachments = []
    if isinstance(send_result, dict):
        inline_attachments = list(send_result.get("attachment_metadata") or [])
    file_attachments: list[dict[str, Any]] = []
    return {
        "requested_assets": [str(path) for path in requested_assets or []],
        "render_sources": {
            "menu_html_path": menu_html_path,
            "machine_html_path": machine_html_path,
            "include_menu_image": bool(include_menu_image),
            "include_machine_image": bool(include_machine_image),
        },
        "inline_attachments": inline_attachments,
        "file_attachments": file_attachments,
        "attachment_count": len(inline_attachments) + len(file_attachments),
    }


def _save_sent_email(
    lead_id: str,
    to_email: str,
    subject: str,
    body: str,
    classification: str = "",
    test_send: bool = False,
    attachment_metadata: dict[str, Any] | None = None,
    tailoring_audit: dict[str, Any] | None = None,
) -> None:
    """Persist a sent email record."""
    sent_dir = STATE_ROOT / "sent"
    sent_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    attachment_metadata = attachment_metadata or {
        "requested_assets": [],
        "render_sources": {},
        "inline_attachments": [],
        "file_attachments": [],
        "attachment_count": 0,
    }
    attachments = [
        *list(attachment_metadata.get("inline_attachments") or []),
        *list(attachment_metadata.get("file_attachments") or []),
    ]
    record = {
        "lead_id": lead_id,
        "to": to_email,
        "subject": subject,
        "body": body,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "status": "sent",
        "classification": classification,
        "test_send": test_send,
        "attachment_metadata": attachment_metadata,
        "attachments": attachments,
        "inline_attachments": list(attachment_metadata.get("inline_attachments") or []),
        "file_attachments": list(attachment_metadata.get("file_attachments") or []),
        "requested_attachment_paths": list(attachment_metadata.get("requested_assets") or []),
        "tailoring_audit": tailoring_audit or {},
    }

    path = sent_dir / f"{lead_id}_{ts}.json"
    from pipeline.utils import write_json
    write_json(path, record)


def _append_operator_reply_to_incoming(
    reply_id: str,
    *,
    lead_id: str,
    to_email: str,
    subject: str,
    body: str,
    provider_result: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Track dashboard follow-ups on the inbound reply thread."""
    path = _reply_record_path(reply_id)
    if not path or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    sent_at = datetime.now(timezone.utc).isoformat()
    operator_replies = list(data.get("operator_replies") or [])
    operator_replies.append({
        "lead_id": lead_id,
        "to": to_email,
        "subject": subject,
        "body": body,
        "sent_at": sent_at,
        "provider_id": str((provider_result or {}).get("id") or ""),
    })
    data["operator_replies"] = operator_replies
    data["latest_operator_reply_at"] = sent_at
    if not data.get("read_at"):
        data["read_at"] = sent_at

    from pipeline.utils import write_json
    write_json(path, data)
    return data


def _normalise_reply_channel(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"form", "forms", "contact_form", "contact-form", "webform", "website_form"}:
        return "form"
    return "email"


def _attachment_is_image(attachment: dict[str, str]) -> bool:
    image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"}
    content_type = str(attachment.get("content_type") or "").lower()
    filename = str(attachment.get("filename") or "").lower()
    return content_type.startswith("image/") or Path(filename).suffix in image_extensions


def _decode_attachment_content(item: dict[str, Any], fallback_content_type: str) -> tuple[bytes, str]:
    raw_content = item.get("content") or item.get("data") or item.get("body")
    if not raw_content:
        return b"", fallback_content_type
    if isinstance(raw_content, list):
        try:
            return bytes(raw_content), fallback_content_type
        except ValueError:
            return b"", fallback_content_type
    if not isinstance(raw_content, str):
        return b"", fallback_content_type

    content = raw_content.strip()
    content_type = fallback_content_type
    if content.startswith("data:") and "," in content:
        header, content = content.split(",", 1)
        content_type = header[5:].split(";", 1)[0] or fallback_content_type
    try:
        return base64.b64decode(content, validate=False), content_type
    except Exception:
        return b"", fallback_content_type


def _normalise_reply_attachments(raw_attachments: Any, *, reply_id: str = "") -> list[dict[str, str]]:
    """Keep safe inbound attachment metadata and store image content when provided."""
    if not raw_attachments:
        return []
    if isinstance(raw_attachments, dict):
        raw_items = [raw_attachments]
    elif isinstance(raw_attachments, list):
        raw_items = raw_attachments
    else:
        return []

    normalised: list[dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or item.get("name") or "").strip()
        content_type = str(item.get("content_type") or item.get("contentType") or item.get("mime_type") or "").strip()
        url = str(item.get("url") or item.get("href") or "").strip()
        if not filename and url:
            filename = Path(url.split("?", 1)[0]).name
        stored_path = str(item.get("stored_path") or "").strip()
        stored_url = str(item.get("stored_url") or "").strip()
        record = {
            "filename": _safe_upload_name(filename) if filename else "",
            "content_type": content_type,
            "url": url,
            "stored_path": stored_path,
            "stored_url": stored_url,
        }
        if not filename and not content_type and not stored_path:
            continue
        if reply_id and not stored_path:
            content_bytes, decoded_content_type = _decode_attachment_content(item, content_type)
            if decoded_content_type:
                record["content_type"] = decoded_content_type
            if content_bytes and _attachment_is_image(record):
                attachment_dir = STATE_ROOT / "uploads" / "reply-attachments" / reply_id
                attachment_dir.mkdir(parents=True, exist_ok=True)
                safe_name = record["filename"] or f"reply-photo-{uuid.uuid4().hex[:8]}.jpg"
                dest = attachment_dir / safe_name
                dest.write_bytes(content_bytes)
                record["stored_path"] = str(dest)
                record["stored_url"] = f"/uploads/reply-attachments/{reply_id}/{safe_name}"
        normalised.append(record)
    return normalised


def _reply_has_photo_evidence(body: str, attachments: list[dict[str, str]]) -> bool:
    for attachment in attachments:
        if _attachment_is_image(attachment):
            return True

    text = str(body or "")
    has_photo_word = bool(re.search(r"(?i)\b(photo|photos|image|images|menu\s+pics?)\b", text)) or "写真" in text or "画像" in text
    has_sent_intent = bool(re.search(r"(?i)\b(attached|attachment|sent|uploaded|shared)\b", text)) or any(
        token in text for token in ("添付", "送付", "送り", "共有", "アップロード")
    )
    has_image_reference = bool(re.search(r"(?i)\.(jpe?g|png|webp|gif|heic|heif)(?:\b|\?)", text))
    return (has_photo_word and has_sent_intent) or (has_image_reference and (has_photo_word or "メニュー" in text))


def _reply_context_from_lead(lead: dict[str, Any] | None) -> dict[str, str]:
    if not lead:
        return {}
    return {
        "package_key": str(lead.get("recommended_primary_package") or lead.get("package_key") or ""),
        "establishment_profile": str(
            lead.get("establishment_profile_effective")
            or lead.get("establishment_profile")
            or ""
        ),
        "primary_category_v1": str(lead.get("primary_category_v1") or lead.get("category") or ""),
    }


def _apply_reply_context_from_lead(reply: dict[str, Any], lead: dict[str, Any] | None = None) -> dict[str, Any]:
    if not lead:
        lead_id = str(reply.get("lead_id") or "")
        if lead_id:
            from pipeline.record import load_lead

            lead = load_lead(lead_id, state_root=STATE_ROOT)
    for key, value in _reply_context_from_lead(lead).items():
        if value and not reply.get(key):
            reply[key] = value
    return reply


def _stored_reply_photo_paths(reply_id: str) -> list[str]:
    if not reply_id:
        return []
    path = STATE_ROOT / "replies" / f"{reply_id}.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    paths: list[str] = []
    for attachment in _normalise_reply_attachments(data.get("attachments")):
        stored_path = str(attachment.get("stored_path") or "")
        if stored_path and _attachment_is_image(attachment) and Path(stored_path).exists():
            paths.append(stored_path)
    return paths


def _find_order_for_lead(lead_id: str) -> dict[str, Any] | None:
    orders_dir = STATE_ROOT / "orders"
    if not lead_id or not orders_dir.exists():
        return None
    matches: list[dict[str, Any]] = []
    for path in orders_dir.glob("ord-*.json"):
        try:
            order = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if str(order.get("lead_id") or "") == lead_id:
            order["_path"] = str(path)
            matches.append(order)
    if not matches:
        return None
    matches.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return matches[0]


def _attach_reply_to_order(order: dict[str, Any], reply_id: str) -> None:
    path = Path(str(order.get("_path") or ""))
    if not path.exists():
        return
    reply_ids = list(order.get("reply_ids") or [])
    if reply_id not in reply_ids:
        reply_ids.append(reply_id)
    order["reply_ids"] = reply_ids
    order["latest_reply_id"] = reply_id
    order.pop("_path", None)
    from pipeline.utils import write_json
    write_json(path, order)


def _write_positive_reply_order_intake(reply: dict[str, Any], lead: dict[str, Any] | None, order: dict[str, Any] | None) -> dict[str, Any] | None:
    from pipeline.constants import ENGLISH_QR_MENU_KEY
    from pipeline.production_workflow import build_order_intake_record
    from pipeline.utils import write_json

    if not bool(reply.get("reply_positive")):
        return None
    package_key = str(
        reply.get("package_key")
        or (lead or {}).get("recommended_primary_package")
        or (lead or {}).get("package_key")
        or ENGLISH_QR_MENU_KEY
    )
    intake = build_order_intake_record(
        reply=reply,
        lead=lead,
        package_key=package_key,
        order_id=str((order or {}).get("order_id") or ""),
    )
    intake["next_action"] = reply.get("next_action") or intake.get("next_action")
    path = STATE_ROOT / "order_intake" / f"{intake['order_intake_id']}.json"
    write_json(path, intake)
    return intake


def _save_incoming_reply(
    *,
    lead_id: str,
    channel: str,
    body: str,
    from_email: str = "",
    subject: str = "",
    business_name: str = "",
    attachments: Any = None,
) -> dict[str, Any]:
    from pipeline.production_workflow import classify_reply_intent, ingest_owner_assets, next_action_for_reply
    from pipeline.record import load_lead

    replies_dir = STATE_ROOT / "replies"
    replies_dir.mkdir(parents=True, exist_ok=True)

    lead = load_lead(lead_id, state_root=STATE_ROOT) if lead_id else None
    created_at = datetime.now(timezone.utc).isoformat()
    reply_id = f"reply-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    attachment_meta = _normalise_reply_attachments(attachments, reply_id=reply_id)
    has_photos = _reply_has_photo_evidence(body, attachment_meta)
    photo_count = sum(1 for attachment in attachment_meta if _attachment_is_image(attachment))
    stored_photo_count = sum(
        1
        for attachment in attachment_meta
        if _attachment_is_image(attachment) and attachment.get("stored_path") and Path(attachment["stored_path"]).exists()
    )
    record = {
        "reply_id": reply_id,
        "lead_id": lead_id,
        "business_name": str(business_name or ""),
        "channel": _normalise_reply_channel(channel),
        "from": str(from_email or ""),
        "subject": str(subject or ""),
        "body": str(body or ""),
        "attachments": attachment_meta,
        "photo_count": photo_count,
        "stored_photo_count": stored_photo_count,
        "has_photos": has_photos,
        "received_at": created_at,
        "read_at": None,
    }
    record.update(_reply_context_from_lead(lead))
    intent = classify_reply_intent(str(body or ""), attachment_meta)
    record["reply_intent"] = intent["intent"]
    record["reply_intent_signals"] = intent["signals"]
    record["reply_positive"] = intent["positive"]
    asset_manifest = ingest_owner_assets(record, state_root=STATE_ROOT)
    record["owner_assets"] = {
        "manifest_path": str(STATE_ROOT / "owner-assets" / reply_id / "manifest.json"),
        "assets": asset_manifest.get("assets") or [],
    }
    record["next_action"] = next_action_for_reply(record, assets=asset_manifest.get("assets") or [])
    order = _find_order_for_lead(lead_id)
    if order:
        record["order_id"] = str(order.get("order_id") or "")
        _attach_reply_to_order(order, reply_id)
    intake = _write_positive_reply_order_intake(record, lead, order)
    if intake:
        record["order_intake_id"] = intake["order_intake_id"]

    from pipeline.utils import write_json
    write_json(replies_dir / f"{reply_id}.json", record)
    return record


def _list_incoming_replies(*, channel: str = "") -> list[dict[str, Any]]:
    replies_dir = STATE_ROOT / "replies"
    if not replies_dir.exists():
        return []

    results: list[dict[str, Any]] = []
    for path in sorted(replies_dir.glob("reply-*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        data["channel"] = _normalise_reply_channel(data.get("channel", "email"))
        data["attachments"] = _normalise_reply_attachments(data.get("attachments"))
        data["photo_count"] = int(data.get("photo_count") or 0)
        data["stored_photo_count"] = sum(
            1
            for attachment in data["attachments"]
            if _attachment_is_image(attachment)
            and attachment.get("stored_path")
            and Path(attachment["stored_path"]).exists()
        )
        data["has_photos"] = bool(data.get("has_photos")) or _reply_has_photo_evidence(
            str(data.get("body") or ""),
            data["attachments"],
        )
        data["business_name"] = str(data.get("business_name") or "")
        _apply_reply_context_from_lead(data)
        try:
            from pipeline.production_workflow import classify_reply_intent, load_asset_manifest, next_action_for_reply
            if not data.get("reply_intent"):
                intent = classify_reply_intent(str(data.get("body") or ""), data["attachments"])
                data["reply_intent"] = intent["intent"]
                data["reply_intent_signals"] = intent["signals"]
                data["reply_positive"] = intent["positive"]
            manifest = load_asset_manifest(str(data.get("reply_id") or ""), state_root=STATE_ROOT)
            if manifest.get("assets"):
                data["owner_assets"] = {
                    "manifest_path": str(STATE_ROOT / "owner-assets" / str(data.get("reply_id") or "") / "manifest.json"),
                    "assets": manifest.get("assets") or [],
                }
            data["next_action"] = next_action_for_reply(data, assets=(data.get("owner_assets") or {}).get("assets") or [])
        except Exception:
            pass
        try:
            from pipeline.qr import assess_reply_qr_readiness
            data.update(assess_reply_qr_readiness(data))
        except Exception:
            data.update({
                "qr_requested": False,
                "qr_ready": False,
                "qr_missing_fields": ["qr_readiness_unavailable"],
                "qr_ready_reason": "",
            })
        if channel and data.get("channel") != channel:
            continue
        results.append(data)
    return results


def _load_incoming_reply(reply_id: str) -> dict[str, Any] | None:
    reply_id = Path(str(reply_id or "")).name
    if not reply_id.startswith("reply-"):
        return None
    path = STATE_ROOT / "replies" / f"{reply_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    data["attachments"] = _normalise_reply_attachments(data.get("attachments"))
    data["stored_photo_count"] = sum(
        1
        for attachment in data["attachments"]
        if _attachment_is_image(attachment)
        and attachment.get("stored_path")
        and Path(attachment["stored_path"]).exists()
    )
    data["photo_count"] = int(data.get("photo_count") or 0)
    data["has_photos"] = bool(data.get("has_photos")) or _reply_has_photo_evidence(str(data.get("body") or ""), data["attachments"])
    _apply_reply_context_from_lead(data)
    try:
        from pipeline.production_workflow import classify_reply_intent, load_asset_manifest, next_action_for_reply
        if not data.get("reply_intent"):
            intent = classify_reply_intent(str(data.get("body") or ""), data["attachments"])
            data["reply_intent"] = intent["intent"]
            data["reply_intent_signals"] = intent["signals"]
            data["reply_positive"] = intent["positive"]
        manifest = load_asset_manifest(str(data.get("reply_id") or ""), state_root=STATE_ROOT)
        if manifest.get("assets"):
            data["owner_assets"] = {
                "manifest_path": str(STATE_ROOT / "owner-assets" / str(data.get("reply_id") or "") / "manifest.json"),
                "assets": manifest.get("assets") or [],
            }
        data["next_action"] = next_action_for_reply(data, assets=(data.get("owner_assets") or {}).get("assets") or [])
    except Exception:
        pass
    from pipeline.qr import assess_reply_qr_readiness
    data.update(assess_reply_qr_readiness(data))
    return data


REPLY_WORKFLOW_STATUSES = {
    "new",
    "needs_reply",
    "waiting_on_owner",
    "ready_to_build",
    "qr_requested",
    "quote_requested",
    "objection",
    "done",
    "archived",
}


def _reply_record_path(reply_id: str) -> Path | None:
    safe_id = Path(str(reply_id or "")).name
    if not safe_id.startswith("reply-"):
        return None
    return STATE_ROOT / "replies" / f"{safe_id}.json"


def _latest_sent_for_lead(lead_id: str) -> dict[str, Any] | None:
    sent_dir = STATE_ROOT / "sent"
    if not lead_id or not sent_dir.exists():
        return None
    matches: list[dict[str, Any]] = []
    for path in sent_dir.glob(f"{lead_id}_*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("test_send"):
            continue
        data["sent_record_id"] = path.stem
        matches.append(data)
    if not matches:
        return None
    matches.sort(key=lambda item: str(item.get("sent_at") or ""), reverse=True)
    sent = matches[0]
    body = str(sent.get("body") or "")
    return {
        "sent_record_id": sent.get("sent_record_id", ""),
        "to": sent.get("to", ""),
        "subject": sent.get("subject", ""),
        "sent_at": sent.get("sent_at", ""),
        "status": sent.get("status", ""),
        "classification": sent.get("classification", ""),
        "body_excerpt": body[:420],
        "requested_attachment_paths": list(sent.get("requested_attachment_paths") or []),
    }


def _reply_next_action(reply: dict[str, Any], lead: dict[str, Any] | None) -> dict[str, str]:
    try:
        from pipeline.production_workflow import load_asset_manifest, next_action_for_reply

        assets = (reply.get("owner_assets") or {}).get("assets") or []
        if not assets and reply.get("reply_id"):
            assets = load_asset_manifest(str(reply.get("reply_id") or ""), state_root=STATE_ROOT).get("assets") or []
        order = _find_order_for_lead(str(reply.get("lead_id") or "")) if reply.get("lead_id") else None
        return next_action_for_reply(reply, assets=assets, order=order)
    except Exception:
        pass

    status = str(reply.get("workflow_status") or "").strip()
    if status in {"done", "archived"}:
        return {"key": status, "label": "Closed", "detail": "No open operator action."}
    if lead and str(lead.get("outreach_status") or "") == "do_not_contact":
        return {"key": "do_not_contact", "label": "Do Not Contact", "detail": "Reply or lead is marked do-not-contact."}
    if reply.get("qr_ready") is True:
        return {"key": "create_qr", "label": "Create QR", "detail": "Owner reply has menu photos and QR intent."}
    if int(reply.get("stored_photo_count") or 0) > 0:
        return {"key": "create_menu", "label": "Create Menu", "detail": "Stored owner photos are ready for package production."}
    if reply.get("has_photos") is True:
        return {"key": "collect_photos", "label": "Collect Photos", "detail": "Photos were mentioned but no stored image is available yet."}
    if reply.get("qr_requested") is True:
        return {"key": "request_qr_details", "label": "Request QR Details", "detail": "QR interest is present, but required menu details are missing."}
    return {"key": "needs_reply", "label": "Reply Needed", "detail": "Open the pitch context and respond from the conversation."}


def _reply_workflow_status(reply: dict[str, Any], next_action: dict[str, str]) -> str:
    stored = str(reply.get("workflow_status") or "").strip()
    if stored in REPLY_WORKFLOW_STATUSES:
        return stored
    key = next_action.get("key", "needs_reply")
    if key in {"create_menu", "build_sample"}:
        return "ready_to_build"
    if key == "review_uploaded_photos":
        return "ready_to_build"
    if key == "ask_for_photos":
        return "waiting_on_owner"
    if key in {"answer_question", "send_quote"}:
        return "needs_reply"
    if key == "close":
        return "done"
    if key in {"create_qr", "request_qr_details"}:
        return "qr_requested"
    if key == "do_not_contact":
        return "done"
    return "needs_reply"


def _enrich_reply_for_inbox(reply: dict[str, Any]) -> dict[str, Any]:
    from pipeline.record import load_lead

    lead_id = str(reply.get("lead_id") or "")
    raw_lead = load_lead(lead_id, state_root=STATE_ROOT) if lead_id else None
    lead = _prepare_lead_for_dashboard(raw_lead) if raw_lead else None
    reply = _apply_reply_context_from_lead(dict(reply), lead)
    latest_sent = _latest_sent_for_lead(lead_id)
    next_action = _reply_next_action(reply, lead)
    workflow_status = _reply_workflow_status(reply, next_action)
    business_name = str(
        reply.get("business_name")
        or (lead or {}).get("business_name")
        or lead_id
        or "Unknown restaurant"
    )
    _, reply_address = parseaddr(str(reply.get("from") or ""))
    if not _valid_email(reply_address):
        reply_address = ""
    operator_replies = list(reply.get("operator_replies") or [])
    latest_operator_reply = operator_replies[-1] if operator_replies else {}
    lead_summary = {
        "lead_id": lead_id,
        "business_name": business_name,
        "city": str((lead or {}).get("city") or ""),
        "category": str((lead or {}).get("primary_category_v1") or ""),
        "menu_type_label": str((lead or {}).get("menu_type_label") or ""),
        "profile_label": str((lead or {}).get("establishment_profile_label") or ""),
        "establishment_profile": str((lead or {}).get("establishment_profile_effective") or (lead or {}).get("establishment_profile") or ""),
        "package_key": str((lead or {}).get("recommended_primary_package") or (lead or {}).get("package_key") or ""),
        "package_label": str((lead or {}).get("recommended_package_label") or ""),
        "pitch_card_status": str((lead or {}).get("pitch_card_status") or ""),
        "pitch_card_label": str((lead or {}).get("pitch_card_label") or ""),
        "review_outcome": str((lead or {}).get("operator_review_outcome") or ""),
        "outreach_status": str((lead or {}).get("outreach_status") or ""),
        "launch_readiness_status": str((lead or {}).get("launch_readiness_status") or ""),
        "primary_contact_label": str((lead or {}).get("primary_contact_label") or ""),
    }
    return {
        **reply,
        "conversation_id": f"lead:{lead_id}" if lead_id else f"reply:{reply.get('reply_id', '')}",
        "business_name": business_name,
        "workflow_status": workflow_status,
        "next_action": next_action,
        "lead": lead_summary,
        "original_pitch": latest_sent or {},
        "has_original_pitch": bool(latest_sent),
        "reply_to_email": reply_address,
        "reply_age_label": _reply_age_label(str(reply.get("received_at") or "")),
        "operator_reply_count": len(operator_replies),
        "latest_operator_reply": latest_operator_reply,
    }


def _reply_age_label(received_at: str) -> str:
    if not received_at:
        return ""
    try:
        received = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
    except ValueError:
        return ""
    delta = datetime.now(timezone.utc) - received.astimezone(timezone.utc)
    if delta.days > 0:
        return f"{delta.days}d old"
    hours = int(delta.total_seconds() // 3600)
    if hours > 0:
        return f"{hours}h old"
    minutes = max(0, int(delta.total_seconds() // 60))
    return f"{minutes}m old"


def _inbox_payload(*, channel: str = "", status: str = "") -> dict[str, Any]:
    replies = [_enrich_reply_for_inbox(reply) for reply in _list_incoming_replies(channel=channel)]
    if status and status != "all":
        replies = [reply for reply in replies if str(reply.get("workflow_status") or "") == status]
    all_replies = [_enrich_reply_for_inbox(reply) for reply in _list_incoming_replies()]
    open_statuses = {"new", "needs_reply", "waiting_on_owner", "ready_to_build", "qr_requested", "quote_requested", "objection"}
    counts = {
        "total": len(all_replies),
        "unread": sum(1 for reply in all_replies if not reply.get("read_at")),
        "open": sum(1 for reply in all_replies if reply.get("workflow_status") in open_statuses),
        "needs_reply": sum(1 for reply in all_replies if reply.get("workflow_status") == "needs_reply"),
        "waiting_on_owner": sum(1 for reply in all_replies if reply.get("workflow_status") == "waiting_on_owner"),
        "ready_to_build": sum(1 for reply in all_replies if reply.get("workflow_status") == "ready_to_build"),
        "qr_requested": sum(1 for reply in all_replies if reply.get("workflow_status") == "qr_requested"),
        "done": sum(1 for reply in all_replies if reply.get("workflow_status") in {"done", "archived"}),
        "email_total": sum(1 for reply in all_replies if reply.get("channel") == "email"),
        "form_total": sum(1 for reply in all_replies if reply.get("channel") == "form"),
    }
    return {"replies": replies, "counts": counts}


def _reply_summaries_by_lead() -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    latest_sort_keys: dict[str, datetime] = {}
    for reply in _list_incoming_replies():
        lead_id = str(reply.get("lead_id") or "").strip()
        if not lead_id:
            continue
        next_action = _reply_next_action(reply, None)
        workflow_status = _reply_workflow_status(reply, next_action)
        summary = summaries.setdefault(lead_id, {
            "total": 0,
            "open": 0,
            "unread": 0,
            "latest_received_at": "",
            "latest_subject": "",
            "latest_workflow_status": "",
            "latest_action_label": "",
        })
        summary["total"] += 1
        if workflow_status not in {"done", "archived"}:
            summary["open"] += 1
        if not reply.get("read_at"):
            summary["unread"] += 1
        received_at = str(reply.get("received_at") or "")
        try:
            received_key = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
        except ValueError:
            received_key = datetime.min.replace(tzinfo=timezone.utc)
        if received_key >= latest_sort_keys.get(lead_id, datetime.min.replace(tzinfo=timezone.utc)):
            latest_sort_keys[lead_id] = received_key
            summary["latest_received_at"] = received_at
            summary["latest_subject"] = str(reply.get("subject") or "")
            summary["latest_workflow_status"] = workflow_status
            summary["latest_action_label"] = str(next_action.get("label") or "")
    return summaries


def _attach_reply_summaries(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = _reply_summaries_by_lead()
    empty = {
        "total": 0,
        "open": 0,
        "unread": 0,
        "latest_received_at": "",
        "latest_subject": "",
        "latest_workflow_status": "",
        "latest_action_label": "",
    }
    for lead in leads:
        lead_id = str(lead.get("lead_id") or "")
        lead["reply_summary"] = summaries.get(lead_id, dict(empty))
    return leads


def _update_incoming_reply_workflow(reply_id: str, *, workflow_status: str, note: str = "") -> dict[str, Any]:
    path = _reply_record_path(reply_id)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="reply_not_found")
    if workflow_status not in REPLY_WORKFLOW_STATUSES:
        raise HTTPException(status_code=422, detail="invalid_reply_workflow_status")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="reply_record_invalid")

    now = datetime.now(timezone.utc).isoformat()
    data["workflow_status"] = workflow_status
    data["workflow_updated_at"] = now
    if note:
        data["operator_note"] = note
    if not data.get("read_at"):
        data["read_at"] = now
    if workflow_status in {"done", "archived"}:
        data["handled_at"] = now
    from pipeline.utils import write_json
    write_json(path, data)
    enriched = _enrich_reply_for_inbox(_load_incoming_reply(str(data.get("reply_id") or reply_id)) or data)
    return {"status": "ok", "reply": enriched, "counts": _inbox_payload()["counts"]}


def _mark_replies_read(channel: str) -> int:
    replies_dir = STATE_ROOT / "replies"
    if not replies_dir.exists():
        return 0

    from pipeline.utils import write_json

    updated = 0
    read_at = datetime.now(timezone.utc).isoformat()
    selected_channel = _normalise_reply_channel(channel)
    for path in replies_dir.glob("reply-*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if _normalise_reply_channel(data.get("channel", "email")) != selected_channel or data.get("read_at"):
            continue
        data["read_at"] = read_at
        write_json(path, data)
        updated += 1
    return updated
