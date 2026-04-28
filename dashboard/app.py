"""WebRefurbMenu Operator Dashboard.

FastAPI application with sidebar navigation, lead management,
outreach generation, and custom build workflow.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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


def _dashboard_email_preview_html(text_body: str, *, include_machine_image: bool) -> str:
    """Render the dashboard preview from the same HTML email builder."""
    from pipeline.email_html import build_pitch_email_html

    html_body = build_pitch_email_html(
        text_body=text_body,
        menu_image_path="dashboard-preview",
        include_menu_image=True,
        include_machine_image=include_machine_image,
        locale="ja",
    )
    return html_body.replace("cid:webrefurb-logo", "/assets/webrefurb-email-logo.svg")


def _normalise_body(text: str) -> str:
    return "\n\n".join(part.strip() for part in text.strip().split("\n\n") if part.strip())


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DASHBOARD_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = DASHBOARD_ROOT.parent
STATE_ROOT = PROJECT_ROOT / "state"

# Load .env
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

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
}

BLOCKED_REGENERATE_STATUSES = BLOCKED_SEND_STATUSES - {"rejected", "needs_review"}


def _has_business_email(lead: dict[str, Any]) -> bool:
    """Dashboard Leads are actionable only when a business email is present."""
    return _valid_email(str(lead.get("email") or ""))


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
        lead for lead in list_leads(state_root=STATE_ROOT)
        if lead.get("lead") is True
        and lead.get("outreach_status", "new") not in BLOCKED_SEND_STATUSES
        and _has_business_email(lead)
    ]
    return templates.TemplateResponse(request, "index.html", {
        "leads": leads,
    })


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------

@app.get("/api/leads")
async def api_leads():
    """Return all leads as JSON."""
    from pipeline.record import list_leads
    return list_leads(state_root=STATE_ROOT)


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


@app.post("/api/search")
async def api_search(request: Request):
    """Search for businesses, qualify them, and add leads."""
    body = await request.json()
    query = body.get("query", "").strip()
    category = body.get("category", "ramen")
    if not query:
        raise HTTPException(status_code=400, detail="Query required")

    serper_api_key = os.environ.get("SERPER_API_KEY", "")
    if not serper_api_key:
        raise HTTPException(status_code=500, detail="SERPER_API_KEY not configured")

    _log("search_started", f"query={query[:80]} category={category}")

    from pipeline.search import search_and_qualify
    import concurrent.futures
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(
            pool,
            lambda: search_and_qualify(
                query=query,
                serper_api_key=serper_api_key,
                category=category,
                state_root=STATE_ROOT,
            ),
        )

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
    from pipeline.record import load_lead
    from pipeline.outreach import classify_business, select_outreach_assets, build_outreach_email
    from pipeline.models import QualificationResult

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")

    if regenerate and record.get("outreach_status") == "do_not_contact":
        raise HTTPException(status_code=403, detail="Lead is marked Do Not Contact")

    if regenerate and record.get("outreach_status") in BLOCKED_REGENERATE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Lead already has status '{record.get('outreach_status')}'",
        )

    # Build qualification result for classification
    q = QualificationResult(
        lead=record["lead"],
        rejection_reason=record.get("rejection_reason"),
        business_name=record["business_name"],
        menu_evidence_found=record.get("menu_evidence_found", True),
        machine_evidence_found=record.get("machine_evidence_found", False),
    )

    classification = classify_business(q)

    # Block machine_only — no email template exists yet
    if classification == "machine_only":
        record["outreach_status"] = "needs_review"
        record["outreach_classification"] = classification
        from pipeline.record import persist_lead_record
        persist_lead_record(record, state_root=STATE_ROOT)
        raise HTTPException(
            status_code=422,
            detail="Machine-only outreach is not supported yet. No email template exists for this classification.",
        )

    assets = select_outreach_assets(classification)
    include_inperson = record.get("outreach_include_inperson", True)
    email = build_outreach_email(
        business_name=record["business_name"],
        classification=classification,
        include_inperson_line=include_inperson,
    )

    # Update lead record
    record["outreach_classification"] = classification
    record["outreach_assets_selected"] = [str(p) for p in assets]
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

    subject = email["subject"]
    body = email["body"]
    english_body = email["english_body"]
    saved_assets = record.get("outreach_assets_selected") or []
    if not regenerate:
        subject = record.get("outreach_draft_subject") or subject
        body = record.get("outreach_draft_body") or body
        english_body = record.get("outreach_draft_english_body") or english_body
        if saved_assets:
            assets = [Path(p) for p in saved_assets]

    action = "draft_generated" if regenerate else "email_previewed"
    _log(action, f"classification={classification}", lead_id=lead_id)

    return {
        "classification": classification,
        "assets": [str(p) for p in assets],
        "subject": subject,
        "body": body,
        "english_body": english_body,
        "preview_html": _dashboard_email_preview_html(
            body,
            include_machine_image=record.get("outreach_include_machine_image", email["include_machine_image"]),
        ),
        "include_inperson": include_inperson,
        "include_machine_image": record.get("outreach_include_machine_image", email["include_machine_image"]),
        "business_name": record["business_name"],
        "email": record.get("email", ""),
        "has_saved_draft": bool(record.get("outreach_draft_body") or record.get("outreach_draft_english_body")),
        "send_blocked": record.get("outreach_status") in BLOCKED_SEND_STATUSES,
        "outreach_status": record.get("outreach_status"),
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
        record["outreach_assets_selected"] = body["assets"]
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
    include_inperson = body.get("include_inperson", True)
    include_machine_image = bool(body.get("include_machine_image", False))

    if not english_body:
        raise HTTPException(status_code=400, detail="English body required")
    if not business_name:
        raise HTTPException(status_code=400, detail="Restaurant name required")

    from pipeline.outreach import build_outreach_email

    default_email = build_outreach_email(
        business_name=business_name,
        classification=classification,
        include_inperson_line=include_inperson,
    )
    if _normalise_body(english_body) == _normalise_body(default_email["english_body"]):
        japanese_body = default_email["body"]
    else:
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
            include_machine_image=include_machine_image,
        ),
    }


@app.post("/api/send/{lead_id}")
async def api_send(lead_id: str, request: Request):
    """Send outreach email via Resend."""
    from pipeline.record import load_lead, persist_lead_record
    from pipeline.constants import OUTREACH_STATUS_SENT, MAX_SENDS_PER_DAY

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")

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

    from pipeline.models import QualificationResult
    from pipeline.outreach import classify_business, select_outreach_assets

    q = QualificationResult(
        lead=record["lead"],
        rejection_reason=record.get("rejection_reason"),
        business_name=record["business_name"],
        menu_evidence_found=record.get("menu_evidence_found", True),
        machine_evidence_found=record.get("machine_evidence_found", False),
    )
    classification = record.get("outreach_classification") or classify_business(q)
    if classification == "machine_only":
        raise HTTPException(
            status_code=422,
            detail="Machine-only outreach is not supported yet. No email template exists for this classification.",
        )

    required_assets = [str(p) for p in select_outreach_assets(classification)]
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

    expected_machine_image = classification == "menu_and_machine"
    if include_machine_image is None:
        include_machine_image = record.get("outreach_include_machine_image", expected_machine_image)
    if expected_machine_image and not include_machine_image:
        raise HTTPException(status_code=400, detail="Required machine image missing for menu_and_machine lead")

    # Rate limit check
    today_sends = _count_today_sends()
    if today_sends >= MAX_SENDS_PER_DAY:
        raise HTTPException(
            status_code=429,
            detail=f"Daily send limit reached ({today_sends}/{MAX_SENDS_PER_DAY})",
        )

    _log("send_attempted", f"to={to_email}", lead_id=lead_id)

    # Send via Resend with inline menu preview
    from pipeline.constants import TEMPLATE_PACKAGE_MENU

    menu_html = TEMPLATE_PACKAGE_MENU / "restaurant_menu_print_master.html"
    if not menu_html.exists():
        menu_html = TEMPLATE_PACKAGE_MENU / "food_menu_browser_preview.html"
    if not menu_html.exists():
        raise HTTPException(status_code=400, detail="Required menu preview image source file not found")

    try:
        result = await _send_email_resend(
            to=to_email,
            subject=subject,
            body=email_body,
            attachments=asset_paths,
            menu_html_path=str(menu_html) if menu_html.exists() else None,
            include_machine_image=include_machine_image,
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
        return {"status": "opted_out", "outreach_status": OUTREACH_STATUS_DO_NOT_CONTACT}

    return {"status": "ok", "outreach_status": record.get("outreach_status")}


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
    menu_photos: list[UploadFile] = File(default=[]),
    ticket_photo: UploadFile | None = File(default=None),
):
    """Accept custom build form data and start build job."""
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
    if not job or job.get("status") != "completed":
        raise HTTPException(status_code=404, detail="Preview not available")

    output_dir = Path(job.get("output_dir", ""))
    preview_path = output_dir / "restaurant_menu_print_master.html"
    if not preview_path.exists():
        preview_path = output_dir / "food_menu_browser_preview.html"
    if not preview_path.exists():
        raise HTTPException(status_code=404, detail="Preview file not found")

    return FileResponse(str(preview_path), media_type="text/html")


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

        meta["status"] = "completed"
        meta["output_dir"] = str(result.output_dir)
        meta["completed_at"] = datetime.now(timezone.utc).isoformat()
        _log("build_completed", lead_id=job_id)

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
    include_machine_image: bool = False,
) -> dict:
    """Send an email via the Resend SDK with HTML body, header/footer, inline menu image."""
    import base64
    import resend as _resend
    from pipeline.email_html import (
        build_pitch_email_html,
        build_inline_attachments,
    )

    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        raise RuntimeError("RESEND_API_KEY not configured")

    _resend.api_key = api_key

    from_email = os.environ.get("RESEND_FROM_EMAIL", "chris@webrefurb.com")
    from_name = os.environ.get("RESEND_FROM_NAME", "Chris（クリス）")
    reply_to = os.environ.get("RESEND_REPLY_TO_EMAIL", from_email).strip() or from_email

    # The email builder uses hosted preview image URLs. Keep the local HTML
    # existence check in api_send, but avoid rendering work during send.
    menu_image_path = "hosted-menu-sample" if menu_html_path else None

    # Build HTML email body — all images via cid: references
    # Japanese outreach → locale="ja" so footer/header links point to /ja
    html_body = build_pitch_email_html(
        text_body=body,
        menu_image_path=menu_image_path,
        include_menu_image=bool(menu_image_path),
        include_machine_image=include_machine_image,
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

    # Attachments: inline images (logo + menu via CID) + PDF files
    all_attachments = build_inline_attachments(menu_image_path)

    if attachments:
        for file_path in attachments:
            p = Path(file_path)
            if p.exists():
                all_attachments.append({
                    "filename": _professional_attachment_name(p),
                    "content": base64.b64encode(p.read_bytes()).decode("ascii"),
                    "disposition": "attachment",
                })

    if all_attachments:
        params["attachments"] = all_attachments

    return _resend.Emails.send(params)


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


def _save_sent_email(
    lead_id: str,
    to_email: str,
    subject: str,
    body: str,
    classification: str = "",
    test_send: bool = False,
) -> None:
    """Persist a sent email record."""
    sent_dir = STATE_ROOT / "sent"
    sent_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    record = {
        "lead_id": lead_id,
        "to": to_email,
        "subject": subject,
        "body": body,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "status": "sent",
        "classification": classification,
        "test_send": test_send,
    }

    path = sent_dir / f"{lead_id}_{ts}.json"
    from pipeline.utils import write_json
    write_json(path, record)
