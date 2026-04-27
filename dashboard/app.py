"""WebRefurbMenu Operator Dashboard.

FastAPI application with sidebar navigation, lead management,
outreach generation, and custom build workflow.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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

# Serve template package PDFs for inline email images
app.mount(
    "/assets",
    StaticFiles(directory=str(PROJECT_ROOT)),
    name="assets",
)

# ---------------------------------------------------------------------------
# Build job tracking (in-memory)
# ---------------------------------------------------------------------------
_build_jobs: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Routes — Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard_main(request: Request):
    """Main dashboard view."""
    from pipeline.record import list_leads
    leads = list_leads(state_root=STATE_ROOT)
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
    return result


@app.post("/api/outreach/{lead_id}")
async def api_outreach(lead_id: str):
    """Generate outreach package for a lead."""
    from pipeline.record import load_lead
    from pipeline.outreach import classify_business, select_outreach_assets, build_outreach_email
    from pipeline.models import QualificationResult

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")

    if record.get("outreach_status") == "do_not_contact":
        raise HTTPException(status_code=403, detail="Lead is marked Do Not Contact")

    # Build qualification result for classification
    q = QualificationResult(
        lead=record["lead"],
        rejection_reason=record.get("rejection_reason"),
        business_name=record["business_name"],
        menu_evidence_found=record.get("menu_evidence_found", True),
        machine_evidence_found=record.get("machine_evidence_found", False),
    )

    classification = classify_business(q)
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
    persist_lead_record(record, state_root=STATE_ROOT)

    return {
        "classification": classification,
        "assets": [str(p) for p in assets],
        "subject": email["subject"],
        "body": email["body"],
        "include_inperson": include_inperson,
        "include_machine_image": email["include_machine_image"],
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
    _blocked_statuses = {"sent", "replied", "converted", "do_not_contact"}
    if record.get("outreach_status") in _blocked_statuses:
        raise HTTPException(
            status_code=409,
            detail=f"Lead already has status '{record.get('outreach_status')}' — cannot re-send",
        )

    body = await request.json()
    to_email = body.get("email", "")
    subject = body.get("subject", "")
    email_body = body.get("body", "")
    asset_paths = body.get("assets", [])
    include_machine_image = body.get("include_machine_image", False)

    if not to_email:
        raise HTTPException(status_code=400, detail="Email address required")

    # Rate limit check
    today_sends = _count_today_sends()
    if today_sends >= MAX_SENDS_PER_DAY:
        raise HTTPException(
            status_code=429,
            detail=f"Daily send limit reached ({today_sends}/{MAX_SENDS_PER_DAY})",
        )

    # Send via Resend with inline menu preview
    from pipeline.constants import TEMPLATE_PACKAGE_MENU

    menu_html = TEMPLATE_PACKAGE_MENU / "restaurant_menu_print_master.html"
    if not menu_html.exists():
        menu_html = TEMPLATE_PACKAGE_MENU / "food_menu_browser_preview.html"

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
        # Never auto-retry
        raise HTTPException(status_code=502, detail=f"Send failed: {exc}")

    # Update lead
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
    )

    return {"status": "sent", "sends_today": today_sends + 1}


@app.get("/api/sent")
async def api_sent():
    """Return all sent emails."""
    sent_dir = STATE_ROOT / "sent"
    if not sent_dir.exists():
        return []
    results = []
    for path in sorted(sent_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
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

    try:
        await _send_email_resend(
            to=to_email,
            subject=f"Re: {body.get('subject', '')}",
            body=reply_body,
            attachments=[],
            in_reply_to=in_reply_to,
        )
    except Exception as exc:
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
    else:
        record["outreach_status"] = "new"
        record["status_history"].append({
            "status": "new",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "Manually unflagged Do Not Contact",
        })

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
            dest = job_dir / photo.filename
            content = await photo.read()
            dest.write_bytes(content)
            photo_paths.append(str(dest))

    ticket_path: str | None = None
    if ticket_photo and ticket_photo.filename:
        dest = job_dir / f"ticket_{ticket_photo.filename}"
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
    (STATE_ROOT / "jobs" / f"{job_id}.json").parent.mkdir(parents=True, exist_ok=True)
    json.dump(job_meta, (STATE_ROOT / "jobs" / f"{job_id}.json").open("w"), ensure_ascii=False)

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

    except Exception as exc:
        meta["status"] = "failed"
        meta["error"] = str(exc)

    # Persist updated meta
    meta_path = STATE_ROOT / "jobs" / f"{job_id}.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(meta, meta_path.open("w"), ensure_ascii=False)


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
    import concurrent.futures
    import resend as _resend
    from pipeline.email_html import (
        build_pitch_email_html,
        build_inline_attachments,
        render_menu_to_jpeg,
    )

    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        raise RuntimeError("RESEND_API_KEY not configured")

    _resend.api_key = api_key

    from_email = os.environ.get("RESEND_FROM_EMAIL", "chris@webrefurb.com")
    from_name = os.environ.get("RESEND_FROM_NAME", "Chris（クリス）")

    # Render menu HTML to JPEG for inline CID embedding (run in thread —
    # Playwright uses its own event loop which conflicts with asyncio)
    menu_image_path = None
    if menu_html_path:
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            menu_image_path = await loop.run_in_executor(
                pool,
                lambda: render_menu_to_jpeg(menu_html_path),
            )

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
                    "filename": p.name,
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
        sent_at = data.get("sent_at", "")
        if sent_at.startswith(today):
            count += 1
    return count


def _save_sent_email(
    lead_id: str,
    to_email: str,
    subject: str,
    body: str,
    classification: str = "",
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
        "status": "delivered",
        "classification": classification,
    }

    path = sent_dir / f"{lead_id}_{ts}.json"
    json.dump(record, path.open("w"), ensure_ascii=False)
