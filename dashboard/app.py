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

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
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
        ) or _inline_preview_svg("English ordering sample", "Menu / Order Guide")
        html_body = html_body.replace(f"cid:{MENU_CID}", menu_preview)
    if include_machine_image:
        machine_preview = _dashboard_inline_rendered_preview_data_uri(
            PROJECT_ROOT / "assets" / "templates" / "ticket_machine_guide.html",
            business_name=business_name,
            stem="machine",
        ) or _inline_preview_svg("Ticket machine sample", "Button Map")
        html_body = html_body.replace(f"cid:{MACHINE_CID}", machine_preview)
    return html_body


def _menu_template_for_profile(establishment_profile: str) -> Path:
    templates = PROJECT_ROOT / "assets" / "templates"
    profile = str(establishment_profile or "").lower()
    if "izakaya" in profile:
        return templates / "izakaya_food_drinks_menu.html"
    return templates / "ramen_food_menu.html"


def _dashboard_inline_rendered_preview_data_uri(template_path: Path, *, business_name: str, stem: str) -> str:
    """Render the actual dark menu template for dashboard preview images."""
    try:
        with tempfile.TemporaryDirectory(prefix="wrm-dashboard-preview-") as tmp_dir:
            source = _personalised_email_html(str(template_path), business_name, tmp_dir, stem)
            if not source:
                return ""
            jpeg = _render_dashboard_preview_jpeg(source)
            if not jpeg or not Path(jpeg).exists():
                return ""
            encoded = base64.b64encode(Path(jpeg).read_bytes()).decode("ascii")
            return f"data:image/jpeg;base64,{encoded}"
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
    "ramen_only": "Ramen Only",
    "ramen_with_drinks": "Ramen With Drinks",
    "ramen_ticket_machine": "Ramen With Ticket Machine",
    "ramen_with_sides_add_ons": "Ramen With Sides / Add-ons",
    "izakaya_food_and_drinks": "Izakaya Food And Drinks",
    "izakaya_drink_heavy": "Izakaya Drink Heavy",
    "izakaya_course_heavy": "Izakaya Course Heavy",
}


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

    lead = ensure_lead_dossier(lead)
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
    prepared["lead_evidence_dossier"] = lead.get("lead_evidence_dossier") or {}
    prepared["proof_items"] = lead.get("proof_items") or prepared["lead_evidence_dossier"].get("proof_items") or []
    prepared["proof_strength_label"] = _dashboard_state_label(
        prepared["lead_evidence_dossier"].get("proof_strength"),
        default="No Proof",
    )
    prepared["ticket_machine_state_label"] = _dashboard_state_label(lead.get("ticket_machine_state") or prepared["lead_evidence_dossier"].get("ticket_machine_state"))
    prepared["english_menu_state_label"] = _dashboard_state_label(lead.get("english_menu_state") or prepared["lead_evidence_dossier"].get("english_menu_state"))
    prepared["lead_category_label"] = _dashboard_state_label(lead.get("lead_category"), default="Unclassified")
    package_key = str(lead.get("recommended_primary_package") or "")
    package = PACKAGE_REGISTRY.get(package_key, {})
    prepared["recommended_package_label"] = package.get("label") or ("Custom quote" if package_key == "custom_quote" else package_key)
    prepared["package_recommendation_reason"] = str(lead.get("package_recommendation_reason") or "")
    prepared["custom_quote_reason"] = str(lead.get("custom_quote_reason") or "")
    return prepared


def _is_test_recipient_email(value: str) -> bool:
    """Treat self/test recipients as test sends, including older sent records."""
    normalised = str(value or "").strip().lower()
    if not normalised:
        return False
    from_email = os.environ.get("RESEND_FROM_EMAIL", "chris@webrefurb.com").strip().lower()
    test_recipient = os.environ.get("TEST_RECIPIENT_EMAIL", "").strip().lower()
    test_recipients = {from_email}
    if test_recipient:
        test_recipients.add(test_recipient)
    return normalised in test_recipients


def _is_lead_business_recipient(lead_id: str, to_email: str) -> bool:
    """True only when the recipient is the restaurant email saved on the lead."""
    from pipeline.record import load_lead

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        return False
    business_email = str(record.get("email") or "").strip().lower()
    normalised_to = str(to_email or "").strip().lower()
    return bool(business_email) and normalised_to == business_email and _valid_email(normalised_to)


# ---------------------------------------------------------------------------
# Routes — Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard_main(request: Request):
    """Main dashboard view."""
    from pipeline.record import list_leads
    leads = [
        _prepare_lead_for_dashboard(lead)
        for lead in list_leads(state_root=STATE_ROOT)
        if (
            lead.get("lead") is True
            or (
                lead.get("production_sim_fixture") is True
                and lead.get("launch_readiness_status") == "disqualified"
            )
        )
        and (
            lead.get("outreach_status", "new") not in BLOCKED_SEND_STATUSES
            or lead.get("launch_readiness_status") == "disqualified"
        )
        and (
            _has_supported_contact_route(lead)
            or (
                lead.get("production_sim_fixture") is True
                and lead.get("launch_readiness_status") in {"manual_review", "disqualified"}
            )
        )
    ]
    return templates.TemplateResponse(request, "index.html", {
        "leads": leads,
    })


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------

@app.get("/api/leads")
async def api_leads():
    """Return dashboard-ready lead records as JSON."""
    from pipeline.record import list_leads
    return [_prepare_lead_for_dashboard(lead) for lead in list_leads(state_root=STATE_ROOT)]


@app.get("/api/launch-batches")
async def api_launch_batches():
    from pipeline.launch import list_launch_batches

    return {"batches": list_launch_batches(state_root=STATE_ROOT)}


@app.post("/api/launch-batches")
async def api_create_launch_batch(request: Request):
    from pipeline.launch import LaunchBatchError, create_launch_batch

    payload = await request.json()
    try:
        batch = create_launch_batch(
            lead_ids=list(payload.get("lead_ids") or []),
            state_root=STATE_ROOT,
            notes=str(payload.get("notes") or ""),
        )
    except LaunchBatchError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return batch


@app.post("/api/launch-batches/{batch_id}/review")
async def api_review_launch_batch(batch_id: str, request: Request):
    from pipeline.launch import LaunchBatchError, review_launch_batch

    payload = await request.json()
    try:
        return review_launch_batch(
            batch_id=batch_id,
            state_root=STATE_ROOT,
            notes=str(payload.get("notes") or ""),
            iteration_decisions=(
                payload.get("iteration_decisions")
                if isinstance(payload.get("iteration_decisions"), dict)
                else None
            ),
        )
    except LaunchBatchError as exc:
        raise HTTPException(status_code=404 if str(exc) == "batch_not_found" else 422, detail=str(exc))


@app.post("/api/launch-batches/{batch_id}/leads/{lead_id}/outcome")
async def api_record_launch_outcome(batch_id: str, lead_id: str, request: Request):
    from pipeline.launch import LaunchBatchError, record_launch_outcome

    payload = await request.json()
    try:
        return record_launch_outcome(batch_id=batch_id, lead_id=lead_id, state_root=STATE_ROOT, outcome=payload)
    except LaunchBatchError as exc:
        raise HTTPException(status_code=404 if "not_found" in str(exc) or "not_in_batch" in str(exc) else 422, detail=str(exc))


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

    persist_lead_record(record, state_root=STATE_ROOT)
    prepared = _prepare_lead_for_dashboard(record)
    _log(action, f"profile={prepared.get('establishment_profile_effective', '')}", lead_id=lead_id)
    return prepared


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

    from pipeline.search_provider import configured_search_provider, search_provider_requires_api_key

    try:
        search_provider = configured_search_provider(os.environ.get("WEBREFURB_SEARCH_PROVIDER"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    serper_api_key = os.environ.get("SERPER_API_KEY", "")
    if search_provider_requires_api_key(search_provider) and not serper_api_key:
        raise HTTPException(status_code=500, detail="SERPER_API_KEY not configured for serper search provider")

    from pipeline.search_scope import search_query_for_scope, search_jobs_for_scope, merge_search_results

    query = search_query_for_scope(category=category, city=city)
    _log("search_started", f"query={query[:80]} category={category} provider={search_provider}")

    from pipeline.record import list_leads
    existing_actionable_ids = {
        lead.get("lead_id")
        for lead in list_leads(state_root=STATE_ROOT)
        if lead.get("lead") is True and _has_supported_contact_route(lead)
    }

    from pipeline.search import search_and_qualify
    import concurrent.futures
    loop = asyncio.get_running_loop()

    search_jobs = search_jobs_for_scope(category=category, city=city, query=query)
    with concurrent.futures.ThreadPoolExecutor() as pool:
        raw_results = await asyncio.gather(*[
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

    result = merge_search_results(raw_results, query=query, category=category)

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
    return result


@app.get("/api/outreach/{lead_id}")
async def api_outreach_preview(lead_id: str):
    """Return the current outreach preview, preferring a saved draft."""
    return await _build_outreach_payload(lead_id, regenerate=False)


@app.post("/api/outreach/{lead_id}")
async def api_outreach(lead_id: str):
    """Regenerate the outreach package for a lead."""
    return await _build_outreach_payload(lead_id, regenerate=True)


async def _build_outreach_payload(lead_id: str, *, regenerate: bool) -> dict[str, Any]:
    """Build an outreach payload.

    GET preview loads saved draft content. POST intentionally regenerates from
    the locked template and clears the saved manual draft.
    """
    from pipeline.record import authoritative_business_name, load_lead
    from pipeline.outreach import (
        build_manual_outreach_message,
        build_outreach_email,
        classify_business,
        describe_outreach_assets,
        select_outreach_assets,
    )
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
        persist_lead_record(record, state_root=STATE_ROOT)
        raise HTTPException(
            status_code=422,
            detail="Business name looks unsafe or contact-route-derived. Fix the name before generating outreach.",
        )

    verified_by = list(record.get("business_name_verified_by") or [])
    if not record.get("business_name_locked") and record.get("business_name_source") and len(verified_by) < 2:
        record["outreach_status"] = "needs_review"
        from pipeline.record import persist_lead_record
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

    from pipeline.lead_dossier import ensure_lead_dossier, READINESS_READY
    record = ensure_lead_dossier(record)
    if record.get("launch_readiness_status") != READINESS_READY:
        from pipeline.record import persist_lead_record
        persist_lead_record(record, state_root=STATE_ROOT)
        reasons = ", ".join(record.get("launch_readiness_reasons") or ["not_ready"])
        raise HTTPException(
            status_code=422,
            detail=f"Lead is not launch-ready for outreach: {reasons}",
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
    if primary_contact_type == "contact_form":
        contact_action = "use_contact_form"
        contact_action_note = "Use this no-attachment version in the restaurant's saved contact form route. Dashboard e-mail sending stays disabled for this lead."
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
        draft = build_outreach_email(
            business_name=business_name,
            classification=classification,
            establishment_profile=profile["effective"],
            include_inperson_line=include_inperson,
            lead_dossier=record.get("lead_evidence_dossier") or {},
        )
    else:
        draft = build_manual_outreach_message(
            business_name=business_name,
            classification=classification,
            channel=draft_channel,
            establishment_profile=profile["effective"],
            include_inperson_line=include_inperson,
            lead_dossier=record.get("lead_evidence_dossier") or {},
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

    from pipeline.record import persist_lead_record
    if regenerate:
        record["outreach_draft_body"] = None
        record["outreach_draft_english_body"] = None
        record["outreach_draft_subject"] = None
        record["outreach_draft_manually_edited"] = False
        record["outreach_draft_edited_at"] = None

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
        "outreach_status": record.get("outreach_status"),
        "launch_readiness_status": record.get("launch_readiness_status"),
        "launch_readiness_reasons": record.get("launch_readiness_reasons") or [],
        "lead_evidence_dossier": record.get("lead_evidence_dossier") or {},
        "proof_items": proof_items,
        "message_variant": record.get("message_variant", ""),
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

    if not english_body:
        raise HTTPException(status_code=400, detail="English body required")
    if not business_name:
        raise HTTPException(status_code=400, detail="Restaurant name required")

    from pipeline.outreach import build_manual_outreach_message, build_outreach_email

    candidate_profiles = [establishment_profile] if establishment_profile and establishment_profile != "unknown" else [
        "unknown",
        "ramen_only",
        "ramen_with_drinks",
        "ramen_ticket_machine",
        "ramen_with_sides_add_ons",
        "izakaya_food_and_drinks",
        "izakaya_drink_heavy",
        "izakaya_course_heavy",
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
            )
        else:
            candidate_draft = build_manual_outreach_message(
                business_name=business_name,
                classification=classification,
                channel=draft_channel,
                establishment_profile=candidate_profile,
                include_inperson_line=include_inperson,
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


@app.post("/api/send/{lead_id}")
async def api_send(lead_id: str, request: Request):
    """Send outreach email via Resend."""
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

    body = await request.json()
    to_email = body.get("email", "")
    subject = body.get("subject") if "subject" in body else (record.get("outreach_draft_subject") or "")
    email_body = body.get("body") if "body" in body else (record.get("outreach_draft_body") or "")
    asset_paths = body.get("assets")
    include_machine_image = body.get("include_machine_image")

    if not to_email:
        raise HTTPException(status_code=400, detail="Email address required")
    if not _valid_email(to_email):
        raise HTTPException(status_code=400, detail="Recipient email address is invalid")

    if not subject:
        raise HTTPException(status_code=400, detail="Subject required")

    if not email_body:
        raise HTTPException(status_code=400, detail="Email body required")

    normalised_to = to_email.strip().lower()
    is_business_send = _is_lead_business_recipient(lead_id, normalised_to)
    is_test_send = not is_business_send
    if is_business_send:
        from pipeline.lead_dossier import ensure_lead_dossier, READINESS_READY

        record = ensure_lead_dossier(record)
        if record.get("launch_readiness_status") != READINESS_READY:
            persist_lead_record(record, state_root=STATE_ROOT)
            reasons = ", ".join(record.get("launch_readiness_reasons") or ["not_ready"])
            raise HTTPException(status_code=422, detail=f"Lead is not launch-ready for outreach: {reasons}")

    from pipeline.models import QualificationResult
    from pipeline.outreach import classify_business, select_outreach_assets, build_outreach_email

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

    default_email = build_outreach_email(
        business_name=business_name,
        classification=classification,
        establishment_profile=profile["effective"],
        include_inperson_line=record.get("outreach_include_inperson", True),
    )
    include_menu_image = default_email["include_menu_image"]
    expected_machine_image = default_email["include_machine_image"]
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

    machine_html = None
    if include_machine_image:
        machine_html = PROJECT_ROOT / "assets" / "templates" / "ticket_machine_guide.html"

    try:
        result = await _send_email_resend(
            to=to_email,
            subject=subject,
            body=email_body,
            attachments=asset_paths,
            menu_html_path=str(menu_html) if menu_html and menu_html.exists() else None,
            machine_html_path=str(machine_html) if machine_html and machine_html.exists() else None,
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
    )

    _log("send_succeeded", f"sends_today={today_sends + 1} test={is_test_send}", lead_id=lead_id)

    return {"status": "test_sent" if is_test_send else "sent", "sends_today": today_sends + 1}


@app.get("/api/sent")
async def api_sent():
    """Return all sent emails."""
    sent_dir = STATE_ROOT / "sent"
    if not sent_dir.exists():
        return []
    results = []
    for path in sorted(sent_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if (
            data.get("test_send")
            or _is_test_recipient_email(data.get("to", ""))
            or not _is_lead_business_recipient(str(data.get("lead_id") or ""), str(data.get("to") or ""))
        ):
            continue
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

    if not to_email or not reply_body:
        raise HTTPException(status_code=400, detail="Email and body required")
    if not _valid_email(to_email):
        raise HTTPException(status_code=400, detail="Recipient email address is invalid")

    _log("reply_sent", f"to={to_email}", lead_id=lead_id)

    try:
        await _send_email_resend(
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
    persist_lead_record(record, state_root=STATE_ROOT)

    return {"status": "replied"}


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
        persist_lead_record(record, state_root=STATE_ROOT)
        _log("opt_out_detected", lead_id=lead_id)
        return {
            "status": "opted_out",
            "outreach_status": OUTREACH_STATUS_DO_NOT_CONTACT,
            "reply_id": incoming["reply_id"],
            "channel": channel,
        }

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
    return _load_order_record(order_id)


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
        "ticket_machine_photos",
        "price_confirmation",
        "dietary_ingredient_notes",
        "delivery_details",
        "business_contact_confirmed",
    ):
        if key in body:
            intake[key] = bool(body.get(key))
    if "notes" in body:
        intake["notes"] = str(body.get("notes") or "")
    intake["is_complete"] = all(bool(intake.get(key)) for key in (
        "full_menu_photos",
        "price_confirmation",
        "delivery_details",
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


@app.post("/api/orders/{order_id}/owner-review")
async def api_mark_owner_review(order_id: str, request: Request):
    order = _load_order_record(order_id)
    body = await request.json()
    from pipeline.quote import can_approve_production, order_from_dict

    ok, blockers = can_approve_production(order_from_dict(order))
    if not ok:
        raise HTTPException(status_code=409, detail={"blockers": blockers})

    now = datetime.now(timezone.utc).isoformat()
    order["state"] = "owner_review"
    order.setdefault("state_history", []).append({
        "state": "owner_review",
        "timestamp": now,
        "note": str(body.get("note") or "Output sent for owner review"),
    })
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
        for key in ("full_menu_photos", "price_confirmation", "delivery_details", "business_contact_confirmed")
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

    ok, blockers = can_approve_package(order_from_dict(order))
    if not ok:
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

    persist_lead_record(record, state_root=STATE_ROOT)
    return {"outreach_status": record["outreach_status"]}


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
    package_key: str = Form("package_1_remote_30k"),
    menu_photos: list[UploadFile] = File(default=[]),
    ticket_photo: UploadFile | None = File(default=None),
):
    """Accept custom build form data and start build job."""
    from pipeline.constants import PACKAGE_1_KEY, PACKAGE_2_KEY, PACKAGE_3_KEY, PACKAGE_REGISTRY

    if package_key not in {PACKAGE_1_KEY, PACKAGE_2_KEY, PACKAGE_3_KEY}:
        raise HTTPException(status_code=422, detail="Unsupported custom build package")

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

    # Save job metadata
    job_meta = {
        "job_id": job_id,
        "restaurant_name": name,
        "menu_text": menu_text,
        "notes": notes,
        "lead_id": lead_id,
        "reply_id": reply_id,
        "source": source,
        "package_key": package_key,
        "package_label": PACKAGE_REGISTRY[package_key]["label"],
        "price_yen": PACKAGE_REGISTRY[package_key]["price_yen"],
        "photo_paths": photo_paths,
        "ticket_path": ticket_path,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _build_jobs[job_id] = job_meta
    from pipeline.utils import write_json
    write_json(STATE_ROOT / "jobs" / f"{job_id}.json", job_meta)

    _log("build_started", f"name={name[:50]}", lead_id=job_id)

    # Start build in background
    asyncio.create_task(_run_build_job(job_id, job_meta))

    return {"job_id": job_id, "status": "started"}


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
            delivery_details=body if isinstance(body, dict) else {},
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
# Background build runner
# ---------------------------------------------------------------------------

async def _run_build_job(job_id: str, meta: dict[str, Any]) -> None:
    """Execute a custom build job in the background."""
    try:
        from pipeline.custom_build import run_custom_build
        from pipeline.models import CustomBuildInput
        import concurrent.futures

        build_input = CustomBuildInput(
            restaurant_name=meta["restaurant_name"],
            menu_items_text=meta.get("menu_text", ""),
            menu_photo_paths=meta.get("photo_paths", []),
            ticket_machine_photo_path=meta.get("ticket_path"),
            notes=meta.get("notes", ""),
        )

        output_dir = STATE_ROOT / "builds" / job_id

        # run_custom_build uses asyncio.run() internally, so it must run
        # in a thread to avoid "cannot be called from a running event loop"
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(
                pool,
                lambda: run_custom_build(build_input, output_dir=output_dir),
            )

        from pipeline.package_export import (
            REVIEW_STATUS_PENDING,
            validate_package_output,
        )

        meta["status"] = "ready_for_review"
        meta["review_status"] = REVIEW_STATUS_PENDING
        meta["final_export_status"] = ""
        meta["output_dir"] = str(result.output_dir)
        meta["artifacts"] = {
            "food_pdf": str(result.food_pdf) if result.food_pdf else "",
            "drinks_pdf": str(result.drinks_pdf) if result.drinks_pdf else "",
            "combined_pdf": str(result.combined_pdf) if result.combined_pdf else "",
            "ticket_machine_pdf": str(result.ticket_machine_pdf) if result.ticket_machine_pdf else "",
            "menu_json": str(result.menu_json) if result.menu_json else "",
        }
        meta["package_validation"] = validate_package_output(
            output_dir=result.output_dir,
            package_key=meta.get("package_key", ""),
        )
        meta["completed_at"] = datetime.now(timezone.utc).isoformat()
        meta.setdefault("status_history", []).append({
            "status": "ready_for_review",
            "timestamp": meta["completed_at"],
        })
        _log("build_ready_for_review", lead_id=job_id)

    except Exception as exc:
        meta["status"] = "failed"
        meta["error"] = str(exc)
        _log("build_failed", str(exc)[:200], lead_id=job_id)

    # Persist updated meta
    from pipeline.utils import write_json
    write_json(STATE_ROOT / "jobs" / f"{job_id}.json", meta)


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
        # The red seal must match the locked restaurant name for every inline sample.
        menu_source = _personalised_email_html(menu_html_path, business_name, tmp_dir, "menu") if include_menu_image and menu_html_path else None
        machine_source = _personalised_email_html(machine_html_path, business_name, tmp_dir, "machine") if include_machine_image and machine_html_path else None
        menu_jpeg = _ensure_menu_jpeg(menu_source) if menu_source else None
        machine_jpeg = _ensure_menu_jpeg(machine_source) if machine_source else None

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
        from pipeline.render import replace_seal_text

        html_text = replace_seal_text(html_text, business_name)
    output = Path(tmp_dir) / f"{stem}.html"
    output.write_text(html_text, encoding="utf-8")
    return str(output)


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
    if "ticket" in lower or "machine" in lower:
        return "WebRefurb-Ticket-Machine-Guide-Sample.pdf"
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
    }

    path = sent_dir / f"{lead_id}_{ts}.json"
    from pipeline.utils import write_json
    write_json(path, record)


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
    replies_dir = STATE_ROOT / "replies"
    replies_dir.mkdir(parents=True, exist_ok=True)

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
    from pipeline.qr import assess_reply_qr_readiness
    data.update(assess_reply_qr_readiness(data))
    return data


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
