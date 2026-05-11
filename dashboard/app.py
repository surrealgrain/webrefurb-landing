"""WebRefurb QR Menu Studio — Operator Dashboard.

FastAPI application for the QR Menu Studio workflow:
Leads → Studio workspace (Materials, Items, Preview) → Owner Review → Publish

v1 scope: ramen / izakaya / skip only. No ordering, no POS, no rollback.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import subprocess
import uuid
from datetime import datetime, timezone, timedelta
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pipeline.constants import (
    ACTIVE_LEAD_CATEGORIES,
    ENGLISH_QR_MENU_KEY,
    ENGLISH_QR_MENU_LABEL,
    ENGLISH_QR_MENU_PRICE_YEN,
    OUTREACH_STATUS_SENT,
)
from pipeline.utils import load_project_env
from pipeline.lead_quality import lead_quality_summary
from pipeline.send_policy import apply_opt_out, batch_send_policy, record_blocks_send
from pipeline.trial_workflow import (
    create_trial_record,
    list_trial_records,
    load_trial_record,
    save_trial_record,
    transition_trial,
    trial_metrics,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("webrefurb.studio")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(_h)


def _log(action: str, detail: str = "", **fields: Any) -> None:
    msg = action
    if fields:
        field_text = " ".join(f"{key}={value}" for key, value in sorted(fields.items()))
        msg += f" {field_text}"
    if detail:
        msg += f" {detail[:200]}"
    logger.info(msg)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DASHBOARD_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = DASHBOARD_ROOT.parent
STATE_ROOT = Path(os.environ.get("WEBREFURB_STATE_ROOT", PROJECT_ROOT / "state")).resolve()
QR_DOCS_ROOT = PROJECT_ROOT / "docs"
TEMPLATES_DIR = PROJECT_ROOT / "assets" / "templates"

# Studio workspace state
STUDIO_DIR = STATE_ROOT / "studio"
STUDIO_DIR.mkdir(parents=True, exist_ok=True)
REVIEWS_DIR = STATE_ROOT / "reviews"
REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR = STATE_ROOT / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR = STATE_ROOT / "audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# v1 Constants
# ---------------------------------------------------------------------------
ALLOWED_CATEGORIES = {"ramen", "izakaya", "skip"}

STUDIO_STATUSES = (
    "intake",           # Initial state, no materials yet
    "materials_received", # Photos/text uploaded
    "editing",          # Items being composed
    "owner_review",     # Sent to owner for confirmation
    "ready_to_publish", # Owner confirmed, ready for operator to publish
    "published",        # Live
    "needs_update",     # Published but needs changes
)

CONFIRMABLE_FIELDS = ("price", "description", "ingredients", "allergens")

ALLOWED_TAGS = (
    "popular", "spicy", "vegetarian", "vegan",
    "pork", "beef", "chicken", "seafood",
    "alcohol", "dairy", "egg", "wheat", "nuts",
)

# Banned terms in customer-facing output
BANNED_CUSTOMER_TERMS = (
    "ordering system", "qr ordering system",
    "place order", "submit order", "send order",
    "pos", "pos system", "checkout page",
)

# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path, default: Any = None) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return default
    return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _studio_path(workspace_id: str) -> Path:
    return STUDIO_DIR / f"{workspace_id}.json"


def _review_path(token: str) -> Path:
    return REVIEWS_DIR / f"{token}.json"


def _load_leads() -> list[dict]:
    """Load leads from state/leads/*.json"""
    leads_dir = STATE_ROOT / "leads"
    if not leads_dir.exists():
        return []
    leads = []
    for f in sorted(leads_dir.glob("*.json")):
        data = _load_json(f)
        if data:
            leads.append(data)
    return leads


def _load_workspace(workspace_id: str) -> dict | None:
    return _load_json(_studio_path(workspace_id))


def _save_workspace(workspace: dict) -> None:
    workspace["updated_at"] = _now_iso()
    _save_json(_studio_path(workspace["id"]), workspace)


def _create_workspace(*, restaurant_name: str, restaurant_name_ja: str = "",
                      category: str = "ramen", lead_id: str = "") -> dict:
    ws_id = f"ws-{uuid.uuid4().hex[:12]}"
    workspace = {
        "id": ws_id,
        "lead_id": lead_id,
        "restaurant_name": restaurant_name,
        "restaurant_name_ja": restaurant_name_ja,
        "category": category,
        "status": "intake",
        "materials": [],
        "items": [],
        "categories": [],
        "owner_review": {
            "status": "not_sent",
            "token": "",
            "sent_at": "",
            "expires_at": "",
            "approved_at": "",
            "changes_requested_at": "",
            "notes": "",
        },
        "trial": {
            "status": "not_requested",
            "trial_id": "",
            "public_url": "",
            "trial_ends_at": "",
        },
        "publish": {
            "ready": False,
            "checks": {},
            "published_at": "",
            "published_url": "",
            "qr_code_generated": False,
            "qr_sign_generated": False,
            "health_status": "unknown",
        },
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    _save_workspace(workspace)
    _append_dashboard_audit("workspace_created", workspace_id=ws_id, detail={"restaurant_name": restaurant_name, "category": category})
    _log("workspace_created", f"id={ws_id} name={restaurant_name[:50]}")
    return workspace


# ---------------------------------------------------------------------------
# Publish check logic
# ---------------------------------------------------------------------------

def _run_publish_checks(workspace: dict) -> dict[str, bool]:
    """Run all pre-publish checks. Returns dict of check_name -> pass."""
    items = workspace.get("items", [])
    owner = workspace.get("owner_review", {})
    pub = workspace.get("publish", {})

    has_items = len(items) > 0
    all_named = all(it.get("name_en") for it in items) if has_items else False
    owner_approved = owner.get("status") == "approved"

    # Sensitive field checks: all must be confirmed OR hidden
    prices_ok = True
    descs_ok = True
    ingredients_ok = True
    allergens_ok = True

    for it in items:
        if it.get("price") and not it.get("price_confirmed") and not it.get("hidden"):
            prices_ok = False
        if it.get("description") and not it.get("desc_confirmed") and not it.get("hidden"):
            descs_ok = False
        if it.get("ingredients") and not it.get("ingredients_confirmed") and not it.get("hidden"):
            ingredients_ok = False
        if it.get("allergens") and not it.get("allergens_confirmed") and not it.get("hidden"):
            allergens_ok = False

    checks = {
        "restaurant_name_confirmed": bool(workspace.get("restaurant_name")),
        "materials_confirmed": len(workspace.get("materials", [])) > 0 or has_items,
        "has_items": has_items,
        "all_items_named": all_named,
        "owner_approved": owner_approved,
        "prices_confirmed_or_hidden": prices_ok,
        "descriptions_confirmed_or_hidden": descs_ok,
        "ingredients_confirmed_or_hidden": ingredients_ok,
        "allergens_confirmed_or_hidden": allergens_ok,
        "qr_code_generated": pub.get("qr_code_generated", False),
        "qr_sign_generated": pub.get("qr_sign_generated", False),
    }
    return checks


def _publish_ready(checks: dict[str, bool]) -> bool:
    return all(checks.values())


def _append_dashboard_audit(action: str, *, workspace_id: str = "", lead_id: str = "", detail: dict[str, Any] | None = None) -> None:
    audit_dir = STATE_ROOT / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "at": _now_iso(),
        "action": action,
        "workspace_id": workspace_id,
        "lead_id": lead_id,
        "detail": detail or {},
    }
    path = audit_dir / "dashboard.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _workspace_workflow_summary(workspace: dict) -> dict[str, Any]:
    checks = _run_publish_checks(workspace)
    failed = [key for key, ok in checks.items() if not ok]
    owner_fields = _fields_needing_confirmation(workspace)
    trial = workspace.get("trial") or {}
    next_actions: list[str] = []
    if not workspace.get("items"):
        next_actions.append("add_menu_items")
    if owner_fields:
        next_actions.append("owner_confirmation_required")
    if workspace.get("owner_review", {}).get("status") != "approved":
        next_actions.append("send_or_complete_owner_review")
    if not _publish_ready(checks):
        next_actions.append("resolve_publish_blockers")
    elif workspace.get("status") != "published":
        next_actions.append("publish_when_manually_approved")
    return {
        "lead_status": "linked" if workspace.get("lead_id") else "manual_workspace",
        "trial_status": trial.get("status", "not_requested"),
        "owner_confirmation": {
            "review_status": workspace.get("owner_review", {}).get("status", "not_sent"),
            "fields_needing_confirmation": owner_fields,
        },
        "publish_status": {
            "status": workspace.get("status", "intake"),
            "ready": _publish_ready(checks),
            "blockers": failed,
            "published_url": workspace.get("publish", {}).get("published_url", ""),
        },
        "next_actions": next_actions,
    }


def _current_git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="WebRefurb QR Menu Studio", version="2.0.0")

templates = Jinja2Templates(directory=str(DASHBOARD_ROOT / "templates"))

# Static files
static_dir = DASHBOARD_ROOT / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


@app.get("/assets/webrefurb-email-logo.svg")
async def dashboard_email_logo():
    logo = PROJECT_ROOT / "pipeline" / "webrefurb_email_logo.svg"
    if not logo.exists():
        raise HTTPException(status_code=404)
    return FileResponse(str(logo), media_type="image/svg+xml")


@app.get("/menus/{asset_path:path}", include_in_schema=False)
async def serve_menu_asset(asset_path: str):
    root = (QR_DOCS_ROOT / "menus").resolve()
    path = (root / asset_path).resolve()
    if path.is_dir():
        index = path / "index.html"
        if index.exists():
            return FileResponse(str(index))
        raise HTTPException(status_code=404)
    if path.exists() and str(path).startswith(str(root)):
        return FileResponse(str(path))
    raise HTTPException(status_code=404)


# ===================================================================
# PAGE ROUTES
# ===================================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard_index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/review/{token}", response_class=HTMLResponse)
async def owner_review_page(request: Request, token: str):
    review = _load_json(_review_path(token))
    if not review:
        return templates.TemplateResponse(request, "owner_review.html", {
            "status": "expired",
            "restaurant_name": "",
            "restaurant_name_ja": "",
            "review_token": token,
            "menu_data": {"categories": []},
            "fields_needing_confirmation": [],
            "expires_at": "",
        })
    workspace = _load_workspace(review.get("workspace_id", ""))
    menu_data = _build_menu_data(workspace) if workspace else {"categories": []}
    fields = _fields_needing_confirmation(workspace) if workspace else []

    return templates.TemplateResponse(request, "owner_review.html", {
        "status": review.get("status", "pending"),
        "restaurant_name": review.get("restaurant_name", ""),
        "restaurant_name_ja": review.get("restaurant_name_ja", ""),
        "review_token": token,
        "menu_data": menu_data,
        "fields_needing_confirmation": fields,
        "expires_at": review.get("expires_at", ""),
    })


# ===================================================================
# API — Leads
# ===================================================================

@app.get("/api/leads")
async def api_leads():
    leads = _load_leads()
    # Enrich with category filter and QR readiness
    result = []
    for lead in leads:
        cat = lead.get("lead_category") or lead.get("primary_category_v1") or "other"
        if cat not in ALLOWED_CATEGORIES:
            cat = "skip"
        result.append({
            "id": lead.get("lead_id", ""),
            "business_name": lead.get("business_name", ""),
            "business_name_ja": lead.get("business_name_ja", ""),
            "category": cat,
            "contact_route": lead.get("email", "") or lead.get("contact_route", ""),
            "recommended_product": ENGLISH_QR_MENU_LABEL,
            "lead_quality": lead_quality_summary(lead),
            "evidence": {
                "english": lead.get("english_menu_state", "unknown"),
                "qr": lead.get("menu_evidence_found", False),
            },
            "outreach_status": lead.get("outreach_status", "new"),
            "safety_status": lead.get("safety_status", "unknown"),
            "send_approved": lead.get("send_approved", False),
            "updated_at": lead.get("updated_at", ""),
        })
    return result


@app.get("/api/leads/{lead_id}")
async def api_lead_detail(lead_id: str):
    leads = _load_leads()
    for lead in leads:
        if lead.get("lead_id") == lead_id:
            return {**lead, "lead_quality": lead_quality_summary(lead), "send_blockers": record_blocks_send(lead)}
    raise HTTPException(status_code=404, detail="Lead not found")


# ===================================================================
# API — Studio Workspaces
# ===================================================================

@app.get("/api/studio")
async def api_list_studios():
    """List all studio workspaces."""
    workspaces = []
    for f in sorted(STUDIO_DIR.glob("*.json")):
        ws = _load_json(f)
        if ws:
            workspaces.append({
                "id": ws["id"],
                "restaurant_name": ws.get("restaurant_name", ""),
                "category": ws.get("category", ""),
                "status": ws.get("status", "intake"),
                "trial_status": (ws.get("trial") or {}).get("status", "not_requested"),
                "item_count": len(ws.get("items", [])),
                "owner_review_status": ws.get("owner_review", {}).get("status", "not_sent"),
                "published_url": ws.get("publish", {}).get("published_url", ""),
                "publish_ready": _publish_ready(_run_publish_checks(ws)),
                "updated_at": ws.get("updated_at", ""),
            })
    return workspaces


@app.post("/api/studio")
async def api_create_studio(request: Request):
    """Create a new studio workspace."""
    body = await request.json()
    name = str(body.get("restaurant_name", "")).strip()
    if not name:
        raise HTTPException(status_code=422, detail="restaurant_name required")
    category = str(body.get("category", "ramen")).strip().lower()
    if category not in ("ramen", "izakaya"):
        category = "ramen"
    ws = _create_workspace(
        restaurant_name=name,
        restaurant_name_ja=str(body.get("restaurant_name_ja", "")),
        category=category,
        lead_id=str(body.get("lead_id", "")),
    )
    return ws


@app.get("/api/studio/{workspace_id}")
async def api_get_studio(workspace_id: str):
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    # Attach computed publish checks
    ws["publish"]["checks"] = _run_publish_checks(ws)
    ws["publish"]["ready"] = _publish_ready(ws["publish"]["checks"])
    ws["workflow"] = _workspace_workflow_summary(ws)
    return ws


# ===================================================================
# API — Materials
# ===================================================================

@app.post("/api/studio/{workspace_id}/materials/upload")
async def api_upload_materials(workspace_id: str, files: list[UploadFile] = File(...)):
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)

    ws_dir = UPLOADS_DIR / workspace_id
    ws_dir.mkdir(parents=True, exist_ok=True)

    for f in files:
        safe_name = Path(f.filename or "upload").name
        if not safe_name:
            safe_name = f"upload-{uuid.uuid4().hex[:8]}"
        dest = ws_dir / safe_name
        content = await f.read()
        dest.write_bytes(content)
        ws["materials"].append({
            "id": f"mat-{uuid.uuid4().hex[:8]}",
            "filename": safe_name,
            "path": f"/uploads/{workspace_id}/{safe_name}",
            "type": "file",
            "size": len(content),
            "uploaded_at": _now_iso(),
        })

    if ws["status"] == "intake":
        ws["status"] = "materials_received"
    _save_workspace(ws)
    _log("materials_uploaded", f"ws={workspace_id} count={len(files)}")
    return {"materials": ws["materials"], "status": ws["status"]}


@app.post("/api/studio/{workspace_id}/materials/text")
async def api_paste_material_text(workspace_id: str, request: Request):
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)

    body = await request.json()
    text = str(body.get("text", "")).strip()
    label = str(body.get("label", "Pasted text"))[:100]
    if not text:
        raise HTTPException(status_code=422, detail="text required")

    ws["materials"].append({
        "id": f"mat-{uuid.uuid4().hex[:8]}",
        "filename": label,
        "type": "text",
        "content": text,
        "uploaded_at": _now_iso(),
    })
    if ws["status"] == "intake":
        ws["status"] = "materials_received"
    _save_workspace(ws)
    return {"materials": ws["materials"], "status": ws["status"]}


@app.delete("/api/studio/{workspace_id}/materials/{material_id}")
async def api_delete_material(workspace_id: str, material_id: str):
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)
    ws["materials"] = [m for m in ws["materials"] if m.get("id") != material_id]
    _save_workspace(ws)
    return {"ok": True}


@app.post("/api/studio/{workspace_id}/materials/scrape")
async def api_scrape_url(workspace_id: str, request: Request):
    """Scrape a URL via Firecrawl and save the content as a text material."""
    import urllib.request
    import urllib.error

    body = await request.json()
    url = str(body.get("url", "")).strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL required")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="FIRECRAWL_API_KEY not configured")

    # Call Firecrawl REST API
    payload = json.dumps({"url": url}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.firecrawl.dev/v2/scrape",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = f"Firecrawl error: {exc.code}"
        try:
            detail += f" — {exc.read().decode()[:200]}"
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=detail)

    markdown = data.get("data", {}).get("markdown", "")
    title = data.get("data", {}).get("metadata", {}).get("title", url)

    if not markdown.strip():
        raise HTTPException(status_code=422, detail="No content extracted from URL")

    # Save as text material
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)
    ws["materials"].append({
        "id": f"mat-{uuid.uuid4().hex[:8]}",
        "filename": f"Scraped: {title[:60]}",
        "type": "text",
        "content": markdown[:50000],  # cap at 50KB
        "source_url": url,
        "uploaded_at": _now_iso(),
    })
    if ws["status"] == "intake":
        ws["status"] = "materials_received"
    _save_workspace(ws)
    _log("materials_scraped", f"ws={workspace_id} url={url[:80]} chars={len(markdown)}")
    return {"materials": ws["materials"], "status": ws["status"], "chars": len(markdown)}


# ===================================================================
# API — Menu Items
# ===================================================================

@app.post("/api/studio/{workspace_id}/items")
async def api_add_item(workspace_id: str, request: Request):
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)

    body = await request.json()
    item = _normalize_item(body)
    ws["items"].append(item)
    if ws["status"] in ("intake", "materials_received"):
        ws["status"] = "editing"
    _save_workspace(ws)
    _log("item_added", f"ws={workspace_id} item={item.get('name_en', '')[:50]}")
    return item


@app.put("/api/studio/{workspace_id}/items/{item_id}")
async def api_update_item(workspace_id: str, item_id: str, request: Request):
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)

    body = await request.json()
    updated = False
    for i, existing in enumerate(ws["items"]):
        if existing.get("id") == item_id:
            ws["items"][i] = _normalize_item(body, existing)
            updated = True
            break
    if not updated:
        raise HTTPException(status_code=404, detail="Item not found")
    _save_workspace(ws)
    return ws["items"][[it["id"] for it in ws["items"]].index(item_id)]


@app.delete("/api/studio/{workspace_id}/items/{item_id}")
async def api_delete_item(workspace_id: str, item_id: str):
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)
    ws["items"] = [it for it in ws["items"] if it.get("id") != item_id]
    _save_workspace(ws)
    return {"ok": True}


@app.post("/api/studio/{workspace_id}/items/bulk-confirm")
async def api_bulk_confirm(workspace_id: str, request: Request):
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)

    body = await request.json()
    fields = body.get("fields", [])
    item_ids = body.get("item_ids", [])

    # Map user-facing field names to internal confirmation keys
    field_key_map = {
        "price": "price_confirmed",
        "description": "desc_confirmed",
        "ingredients": "ingredients_confirmed",
        "allergens": "allergens_confirmed",
    }

    count = 0
    for it in ws["items"]:
        if item_ids and it.get("id") not in item_ids:
            continue
        for f in fields:
            key = field_key_map.get(f)
            if key:
                it[key] = True
                count += 1

    _save_workspace(ws)
    _log("bulk_confirm", f"ws={workspace_id} fields={fields} count={count}")
    return {"confirmed_count": count}


@app.post("/api/studio/{workspace_id}/items/reorder")
async def api_reorder_items(workspace_id: str, request: Request):
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)

    body = await request.json()
    ordered_ids = body.get("item_ids", [])
    id_to_item = {it["id"]: it for it in ws["items"]}
    ws["items"] = [id_to_item[iid] for iid in ordered_ids if iid in id_to_item]
    _save_workspace(ws)
    return {"ok": True}


def _normalize_item(data: dict, existing: dict | None = None) -> dict:
    """Normalize item data from API input."""
    if existing:
        item = dict(existing)
    else:
        item = {"id": f"item-{uuid.uuid4().hex[:8]}"}

    item["category"] = str(data.get("category", item.get("category", "")))
    item["name_ja"] = str(data.get("name_ja", item.get("name_ja", "")))
    item["name_en"] = str(data.get("name_en", item.get("name_en", "")))
    item["price"] = str(data.get("price", item.get("price", "")))
    item["description"] = str(data.get("description", item.get("description", "")))
    item["ingredients"] = str(data.get("ingredients", item.get("ingredients", "")))
    item["allergens"] = str(data.get("allergens", item.get("allergens", "")))
    item["image"] = str(data.get("image", item.get("image", "")))
    item["visible"] = bool(data.get("visible", item.get("visible", True)))
    item["hidden"] = bool(data.get("hidden", item.get("hidden", False)))

    # Tags
    raw_tags = data.get("tags", item.get("tags", []))
    item["tags"] = [t for t in raw_tags if t in ALLOWED_TAGS]

    # Confirmation flags — map API names to storage names
    confirm_map = {
        "price_confirmed": "price_confirmed",
        "desc_confirmed": "desc_confirmed",
        "description_confirmed": "desc_confirmed",
        "ingredients_confirmed": "ingredients_confirmed",
        "allergens_confirmed": "allergens_confirmed",
    }
    for api_key, store_key in confirm_map.items():
        val = data.get(api_key, None)
        if val is None:
            val = item.get(store_key, False)
        item[store_key] = bool(val)

    return item


# ===================================================================
# API — Preview
# ===================================================================

@app.get("/api/studio/{workspace_id}/preview")
async def api_preview(workspace_id: str):
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)
    return _build_menu_data(ws)


@app.get("/api/studio/{workspace_id}/preview/html", response_class=HTMLResponse)
async def api_preview_html(workspace_id: str):
    """Render the customer-facing menu as HTML for the preview iframe."""
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)
    menu_data = _build_menu_data(ws)
    template = TEMPLATES_DIR / "customer_qr_menu.html"
    if template.exists():
        html = template.read_text("utf-8")
        html = html.replace("{{RESTAURANT_NAME}}", menu_data.get("restaurant_name", ""))
        html = html.replace("{{RESTAURANT_NAME_JA}}", menu_data.get("restaurant_name_ja", ""))
        menu_json = json.dumps(menu_data, ensure_ascii=False, indent=2)
        if "{{MENU_DATA}}" in html:
            html = html.replace("{{MENU_DATA}}", menu_json)
        else:
            html = html.replace(
                'type="application/json">',
                'type="application/json">\n' + menu_json + "\n",
                1,
            )
    else:
        html = _generate_minimal_menu_html(menu_data)
    return html


def _build_menu_data(workspace: dict) -> dict:
    """Build menu data structure for preview and customer rendering."""
    items = workspace.get("items", [])
    categories = workspace.get("categories", [])

    # Auto-detect categories from items if not explicitly set
    if not categories:
        seen = []
        for it in items:
            cat = it.get("category", "Other")
            if cat and cat not in seen:
                seen.append(cat)
        categories = [{"id": f"cat-{i+1}", "name_en": c, "name_ja": ""} for i, c in enumerate(seen)]

    cat_map = {c.get("name_en", f"cat-{i+1}"): c for i, c in enumerate(categories)}

    menu_categories = []
    for cat_def in categories:
        cat_name = cat_def.get("name_en", "Other")
        cat_items = []
        for it in items:
            if it.get("category", "Other") == cat_name and it.get("visible", True) and not it.get("hidden"):
                cat_items.append({
                    "id": it["id"],
                    "name_en": it.get("name_en", ""),
                    "name_ja": it.get("name_ja", ""),
                    "price": it.get("price", "") if it.get("price_confirmed") else "",
                    "description": it.get("description", "") if it.get("desc_confirmed") else "",
                    "ingredients": it.get("ingredients", "") if it.get("ingredients_confirmed") else "",
                    "allergens": it.get("allergens", "") if it.get("allergens_confirmed") else "",
                    "tags": it.get("tags", []),
                    "image": it.get("image", ""),
                    "price_confirmed": it.get("price_confirmed", False),
                    "desc_confirmed": it.get("desc_confirmed", False),
                })
        if cat_items:
            menu_categories.append({
                "id": cat_def.get("id", f"cat-{len(menu_categories)+1}"),
                "name_en": cat_name,
                "name_ja": cat_def.get("name_ja", ""),
                "items": cat_items,
            })

    return {
        "restaurant_name": workspace.get("restaurant_name", ""),
        "restaurant_name_ja": workspace.get("restaurant_name_ja", ""),
        "categories": menu_categories,
    }


def _fields_needing_confirmation(workspace: dict) -> list[str]:
    """Identify which fields have unconfirmed data."""
    fields = set()
    for it in workspace.get("items", []):
        if it.get("price") and not it.get("price_confirmed"):
            fields.add("price")
        if it.get("description") and not it.get("desc_confirmed"):
            fields.add("description")
        if it.get("ingredients") and not it.get("ingredients_confirmed"):
            fields.add("ingredients")
        if it.get("allergens") and not it.get("allergens_confirmed"):
            fields.add("allergens")
    return sorted(fields)


# ===================================================================
# API — Owner Review
# ===================================================================

@app.post("/api/studio/{workspace_id}/review-link")
async def api_create_review_link(workspace_id: str):
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)

    token = secrets.token_urlsafe(24)
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    review = {
        "workspace_id": workspace_id,
        "restaurant_name": ws.get("restaurant_name", ""),
        "restaurant_name_ja": ws.get("restaurant_name_ja", ""),
        "token": token,
        "status": "pending",
        "created_at": _now_iso(),
        "expires_at": expires,
    }
    _save_json(_review_path(token), review)

    ws["owner_review"] = {
        "status": "pending",
        "token": token,
        "sent_at": _now_iso(),
        "expires_at": expires,
        "approved_at": "",
        "changes_requested_at": "",
        "notes": "",
    }
    ws["status"] = "owner_review"
    _save_workspace(ws)

    _log("review_link_created", f"ws={workspace_id}")
    return {"review_url": f"/review/{token}", "token": token, "expires_at": expires}


@app.post("/api/review/{token}/approve")
async def api_review_approve(token: str):
    review = _load_json(_review_path(token))
    if not review:
        raise HTTPException(status_code=404, detail="Review link not found")
    if review.get("status") == "expired":
        raise HTTPException(status_code=410, detail="Review link expired")

    review["status"] = "approved"
    review["approved_at"] = _now_iso()
    _save_json(_review_path(token), review)

    ws = _load_workspace(review["workspace_id"])
    if ws:
        ws["owner_review"]["status"] = "approved"
        ws["owner_review"]["approved_at"] = _now_iso()
        ws["status"] = "ready_to_publish"
        _save_workspace(ws)

    _log("owner_approved", f"ws={review.get('workspace_id', '')}")
    return {"status": "approved"}


@app.post("/api/review/{token}/request-changes")
async def api_review_request_changes(token: str, request: Request):
    review = _load_json(_review_path(token))
    if not review:
        raise HTTPException(status_code=404)
    if review.get("status") == "expired":
        raise HTTPException(status_code=410, detail="Review link expired")

    body = await request.json()
    notes = str(body.get("notes", ""))[:2000]

    review["status"] = "changes_requested"
    review["changes_requested_at"] = _now_iso()
    review["notes"] = notes
    _save_json(_review_path(token), review)

    ws = _load_workspace(review["workspace_id"])
    if ws:
        ws["owner_review"]["status"] = "changes_requested"
        ws["owner_review"]["changes_requested_at"] = _now_iso()
        ws["owner_review"]["notes"] = notes
        ws["status"] = "editing"
        _save_workspace(ws)

    _log("owner_requested_changes", f"ws={review.get('workspace_id', '')}")
    return {"status": "changes_requested"}


# ===================================================================
# API — Publish
# ===================================================================

@app.post("/api/studio/{workspace_id}/publish")
async def api_publish(workspace_id: str):
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)

    checks = _run_publish_checks(ws)
    if not _publish_ready(checks):
        failed = [k for k, v in checks.items() if not v]
        raise HTTPException(status_code=422, detail=f"Publish blocked: {', '.join(failed)}")

    # Generate hosted URL
    slug = re.sub(r"[^a-z0-9]+", "-", ws.get("restaurant_name", "").lower()).strip("-")[:40]
    if not slug:
        slug = workspace_id
    published_url = f"/menus/{slug}/"

    ws["status"] = "published"
    ws["publish"] = {
        "ready": True,
        "checks": checks,
        "published_at": _now_iso(),
        "published_url": published_url,
        "qr_code_generated": True,
        "qr_sign_generated": True,
        "health_status": "healthy",
    }

    # Build and save the static menu HTML
    _publish_menu_html(ws, slug)

    _save_workspace(ws)
    _log("menu_published", f"ws={workspace_id} url={published_url}")
    return {"status": "published", "url": published_url, "checks": checks}


@app.post("/api/studio/{workspace_id}/unpublish")
async def api_unpublish(workspace_id: str):
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)
    ws["status"] = "needs_update"
    ws["publish"]["health_status"] = "unpublished"
    _save_workspace(ws)
    _log("menu_unpublished", f"ws={workspace_id}")
    return {"status": "needs_update"}


@app.post("/api/studio/{workspace_id}/regenerate-qr")
async def api_regenerate_qr(workspace_id: str):
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)
    ws["publish"]["qr_code_generated"] = True
    ws["publish"]["qr_sign_generated"] = True
    _save_workspace(ws)
    return {"qr_code_generated": True, "qr_sign_generated": True}


@app.get("/api/studio/{workspace_id}/export")
async def api_export_package(workspace_id: str):
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)
    if ws.get("status") != "published":
        raise HTTPException(status_code=422, detail="Menu must be published first")

    # Return export metadata (actual ZIP generation would use pipeline/qr.py)
    export = {
        "workspace_id": workspace_id,
        "restaurant_name": ws.get("restaurant_name", ""),
        "published_url": ws.get("publish", {}).get("published_url", ""),
        "qr_code_generated": ws.get("publish", {}).get("qr_code_generated", False),
        "qr_sign_generated": ws.get("publish", {}).get("qr_sign_generated", False),
        "menu_data": _build_menu_data(ws),
        "confirmation_summary": {
            "total_items": len(ws.get("items", [])),
            "prices_confirmed": sum(1 for it in ws.get("items", []) if it.get("price_confirmed")),
            "descriptions_confirmed": sum(1 for it in ws.get("items", []) if it.get("desc_confirmed")),
            "ingredients_confirmed": sum(1 for it in ws.get("items", []) if it.get("ingredients_confirmed")),
            "allergens_confirmed": sum(1 for it in ws.get("items", []) if it.get("allergens_confirmed")),
        },
    }
    return export


@app.post("/api/studio/{workspace_id}/mark-needs-update")
async def api_mark_needs_update(workspace_id: str):
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)
    ws["status"] = "needs_update"
    _save_workspace(ws)
    return {"status": "needs_update"}


@app.post("/api/studio/{workspace_id}/archive")
async def api_archive_studio(workspace_id: str, request: Request):
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)
    body = await request.json()
    reason = str(body.get("reason") or "manual_archive")[:500]
    ws["status"] = "archived"
    ws["archived_at"] = _now_iso()
    ws["archive_reason"] = reason
    publish = ws.setdefault("publish", {})
    publish["health_status"] = "archived"
    _save_workspace(ws)
    _append_dashboard_audit("workspace_archived", workspace_id=workspace_id, detail={"reason": reason})
    return {"status": "archived", "reason": reason}


# ===================================================================
# API — Trial Lifecycle
# ===================================================================

@app.get("/api/trials")
async def api_trials():
    trials = list_trial_records(state_root=STATE_ROOT)
    return {"trials": trials, "metrics": trial_metrics(trials)}


@app.post("/api/studio/{workspace_id}/trial")
async def api_create_trial(workspace_id: str, request: Request):
    ws = _load_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404)
    body = await request.json()
    record = create_trial_record(
        lead={
            "lead_id": ws.get("lead_id", ""),
            "business_name": ws.get("restaurant_name", ""),
        },
        requested_by=str(body.get("requested_by") or "operator"),
        source_channel=str(body.get("source_channel") or "dashboard"),
    )
    save_trial_record(state_root=STATE_ROOT, record=record)
    ws["trial"] = {
        "status": record["status"],
        "trial_id": record["trial_id"],
        "public_url": record.get("public_url", ""),
        "trial_ends_at": record.get("trial_ends_at", ""),
    }
    _save_workspace(ws)
    _append_dashboard_audit("trial_created", workspace_id=workspace_id, detail={"trial_id": record["trial_id"]})
    return record


@app.post("/api/trials/{trial_id}/transition")
async def api_transition_trial(trial_id: str, request: Request):
    record = load_trial_record(state_root=STATE_ROOT, trial_id=trial_id)
    if not record:
        raise HTTPException(status_code=404)
    body = await request.json()
    try:
        updated = transition_trial(
            record,
            str(body.get("status") or ""),
            actor=str(body.get("actor") or "operator"),
            reason=str(body.get("reason") or ""),
            public_url=str(body.get("public_url") or ""),
            menu_id=str(body.get("menu_id") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_trial_record(state_root=STATE_ROOT, record=updated)
    for path in STUDIO_DIR.glob("*.json"):
        ws = _load_json(path)
        if not ws or (ws.get("trial") or {}).get("trial_id") != trial_id:
            continue
        ws["trial"] = {
            "status": updated["status"],
            "trial_id": trial_id,
            "public_url": updated.get("public_url", ""),
            "trial_ends_at": updated.get("trial_ends_at", ""),
        }
        _save_workspace(ws)
    _append_dashboard_audit("trial_transitioned", detail={"trial_id": trial_id, "status": updated["status"]})
    return updated


def _publish_menu_html(workspace: dict, slug: str) -> None:
    """Generate and save the static customer-facing menu HTML."""
    menu_data = _build_menu_data(workspace)
    template = TEMPLATES_DIR / "customer_qr_menu.html"

    if not template.exists():
        # If template doesn't exist yet, create a minimal one
        html = _generate_minimal_menu_html(menu_data)
    else:
        html = template.read_text("utf-8")
        # Replace placeholders
        html = html.replace("{{RESTAURANT_NAME}}", menu_data.get("restaurant_name", ""))
        html = html.replace("{{RESTAURANT_NAME_JA}}", menu_data.get("restaurant_name_ja", ""))
        # Embed menu data
        menu_json = json.dumps(menu_data, ensure_ascii=False, indent=2)
        if "{{MENU_DATA}}" in html:
            html = html.replace("{{MENU_DATA}}", menu_json)
        else:
            # Inject into the menu-data script tag
            html = html.replace(
                'type="application/json">',
                f'type="application/json">\n{menu_json}\n',
                1,
            )

    # Write to docs/menus/{slug}/
    menu_dir = QR_DOCS_ROOT / "menus" / slug
    menu_dir.mkdir(parents=True, exist_ok=True)
    (menu_dir / "index.html").write_text(html, "utf-8")


def _generate_minimal_menu_html(menu_data: dict) -> str:
    """Fallback: generate a minimal menu page if template isn't available."""
    import html as html_mod
    name = html_mod.escape(menu_data.get("restaurant_name", ""))
    name_ja = html_mod.escape(menu_data.get("restaurant_name_ja", ""))
    menu_json = json.dumps(menu_data, ensure_ascii=False)

    # Build as plain string (not f-string) to avoid JS brace conflicts
    parts = []
    parts.append('<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">')
    parts.append('<meta name="viewport" content="width=device-width,initial-scale=1.0">')
    parts.append(f'<title>{name} — English Menu</title>')
    parts.append('<style>')
    parts.append('body{font-family:system-ui,sans-serif;margin:0;padding:0;background:#fff;color:#1a1a1a}')
    parts.append('.header{padding:20px;border-bottom:1px solid #e5e7eb}')
    parts.append('.header h1{margin:0;font-size:22px}')
    parts.append('.header p{margin:4px 0 0;color:#6b7280;font-size:14px}')
    parts.append('.section{padding:16px}.section h2{font-size:16px;font-weight:600;margin:0 0 12px;color:#0E7490}')
    parts.append('.item{padding:12px 0;border-bottom:1px solid #f3f4f6}')
    parts.append('.item-name{font-weight:600;font-size:15px}')
    parts.append('.item-ja{color:#6b7280;font-size:13px}')
    parts.append('.item-price{float:right;font-weight:600}')
    parts.append('.add-btn{background:#0E7490;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:13px;cursor:pointer;margin-top:6px}')
    parts.append('.badge{position:fixed;bottom:20px;right:20px;width:52px;height:52px;border-radius:26px;background:#0E7490;color:#fff;display:none;align-items:center;justify-content:center;font-size:18px;font-weight:700;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,.15)}')
    parts.append('.overlay{position:fixed;inset:0;background:#fff;display:none;flex-direction:column;z-index:100}')
    parts.append('.overlay.open{display:flex}')
    parts.append('.overlay-header{padding:20px;text-align:center;border-bottom:2px solid #e5e7eb}')
    parts.append('.overlay-item{padding:14px 20px;border-bottom:1px solid #f3f4f6}')
    parts.append('.overlay-item .ja{font-size:22px;font-weight:700}')
    parts.append('.overlay-item .en{font-size:13px;color:#6b7280}')
    parts.append('.overlay-item .price{float:right;font-size:16px;font-weight:600}')
    parts.append('.overlay-item .remove{color:#C43D2F;cursor:pointer;font-size:14px;margin-top:4px}')
    parts.append('.overlay-footer{padding:20px;text-align:center;border-top:2px solid #e5e7eb;margin-top:auto}')
    parts.append('.close-btn{background:#f3f4f6;border:none;border-radius:8px;padding:10px 24px;font-size:15px;cursor:pointer;margin-top:10px}')
    parts.append('</style></head><body>')
    parts.append(f'<div class="header"><h1>{name}</h1><p>{name_ja}</p></div>')
    parts.append('<div id="menuSections"></div>')
    parts.append('<div class="badge" id="listBadge" onclick="toggleOverlay()">0</div>')
    parts.append('<div class="overlay" id="staffOverlay">')
    parts.append('<div class="overlay-header"><h2>Show to Staff</h2><p>スタッフに見せる</p></div>')
    parts.append('<div id="staffList"></div>')
    parts.append('<div class="overlay-footer"><p>Please show this screen to staff.</p><p>スタッフにこの画面をお見せください。</p>')
    parts.append('<button class="close-btn" onclick="toggleOverlay()">Close</button></div></div>')
    # Menu data
    parts.append('<script id="menu-data" type="application/json">')
    parts.append(menu_json)
    parts.append('</script>')
    # JS — built as raw string to avoid f-string brace conflicts
    parts.append("""<script>
const M=JSON.parse(document.getElementById('menu-data').textContent);
let L=JSON.parse(localStorage.getItem('wr_staff_list')||'[]');
function render(){var s=document.getElementById('menuSections');s.innerHTML='';
M.categories.forEach(function(c){var h='<div class="section"><h2>'+c.name_en+'</h2>';
c.items.forEach(function(it){var inList=L.filter(function(x){return x.id===it.id}).length;
h+='<div class="item"><span class="item-price">'+(it.price||'')+'</span>';
h+='<div class="item-name">'+it.name_en+'</div>';
h+='<div class="item-ja">'+(it.name_ja||'')+'</div>';
if(it.description)h+='<div style="color:#6b7280;font-size:13px;margin-top:4px">'+it.description+'</div>';
h+='<button class="add-btn" onclick="addToList(\\''+it.id+'\\')">'+(inList?'In list ('+inList+')':'Add to list')+'</button></div>';});
h+='</div>';s.innerHTML+=h;});updateBadge();}
function addToList(id){var found=null;M.categories.forEach(function(c){c.items.forEach(function(it){if(it.id===id)found=it})});
if(found)L.push({id:found.id,name_en:found.name_en,name_ja:found.name_ja,price:found.price});
localStorage.setItem('wr_staff_list',JSON.stringify(L));render();}
function removeFromList(idx){L.splice(idx,1);localStorage.setItem('wr_staff_list',JSON.stringify(L));render();renderStaffList();}
function updateBadge(){var b=document.getElementById('listBadge');b.textContent=L.length;b.style.display=L.length?'flex':'none';}
function toggleOverlay(){var o=document.getElementById('staffOverlay');o.classList.toggle('open');if(o.classList.contains('open'))renderStaffList();}
function renderStaffList(){var el=document.getElementById('staffList');el.innerHTML='';
var counts={};L.forEach(function(it){counts[it.id]=(counts[it.id]||0)+1});
Object.keys(counts).forEach(function(id){var count=counts[id];var it=L.find(function(x){return x.id===id});
el.innerHTML+='<div class="overlay-item"><span class="price">'+(it.price||'')+'</span>';
el.innerHTML+='<div class="ja">'+(it.name_ja||it.name_en)+'</div>';
el.innerHTML+='<div class="en">'+it.name_en+(count>1?' x'+count:'')+'</div>';
el.innerHTML+='<div class="remove" onclick="removeFromList('+L.indexOf(it)+')">Remove</div></div>';});}
render();
</script></body></html>""")
    return '\n'.join(parts)


# ===================================================================
# API — Published Menus
# ===================================================================

@app.get("/api/published")
async def api_published_menus():
    menus = []
    for f in sorted(STUDIO_DIR.glob("*.json")):
        ws = _load_json(f)
        if ws and ws.get("status") == "published":
            menus.append({
                "id": ws["id"],
                "restaurant_name": ws.get("restaurant_name", ""),
                "restaurant_name_ja": ws.get("restaurant_name_ja", ""),
                "category": ws.get("category", ""),
                "published_url": ws.get("publish", {}).get("published_url", ""),
                "qr_code_generated": ws.get("publish", {}).get("qr_code_generated", False),
                "published_at": ws.get("publish", {}).get("published_at", ""),
                "health_status": ws.get("publish", {}).get("health_status", "unknown"),
                "needs_update": ws.get("status") == "needs_update",
                "item_count": len(ws.get("items", [])),
            })
    return menus


# ===================================================================
# API — Banned term check
# ===================================================================

@app.get("/api/banned-terms-check")
async def api_banned_terms_check():
    """Scan all customer-facing templates for banned terms."""
    violations = []
    template_dir = TEMPLATES_DIR
    if template_dir.exists():
        for f in template_dir.glob("*.html"):
            content = f.read_text("utf-8").lower()
            for term in BANNED_CUSTOMER_TERMS:
                if term in content:
                    violations.append({"file": f.name, "term": term})
    return {"violations": violations, "total": len(violations)}


# ===================================================================
# API — Health / Status
# ===================================================================

@app.get("/api/health")
async def api_health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "product": ENGLISH_QR_MENU_KEY,
        "categories": list(ALLOWED_CATEGORIES),
        "studio_count": len(list(STUDIO_DIR.glob("*.json"))),
        "git_commit": _current_git_commit(),
        "environment": os.environ.get("WEBREFURB_ENV", "local"),
    }


@app.get("/api/diagnostics")
async def api_diagnostics():
    return {
        "status": "ok",
        "git_commit": _current_git_commit(),
        "environment": os.environ.get("WEBREFURB_ENV", "local"),
        "state_root": str(STATE_ROOT),
        "docs_root": str(QR_DOCS_ROOT),
        "route_count": len(app.routes),
    }


@app.post("/api/send-batch/policy-check")
async def api_send_batch_policy_check(request: Request):
    body = await request.json()
    lead_ids = [str(item) for item in body.get("lead_ids") or []]
    approved = body.get("approved") is True
    leads = [lead for lead in _load_leads() if lead.get("lead_id") in lead_ids]
    sent_history = _load_sent_history()
    return batch_send_policy(leads, approved=approved, sent_history=sent_history)


# ===================================================================
# Email Sending — Resend Integration
# ===================================================================

BLOCKED_SEND_STATUSES = {
    "sent", "replied", "converted", "bounced", "invalid",
    "skipped", "do_not_contact", "rejected", "needs_review", "contacted_form",
}


def _valid_email(value: str) -> bool:
    _, address = parseaddr(value.strip())
    if not address or address != value.strip():
        return False
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", address) is not None


def _is_test_recipient_email(value: str) -> bool:
    normalised = str(value or "").strip().lower()
    if not normalised:
        return False
    from_email = os.environ.get("RESEND_FROM_EMAIL", "chris@webrefurb.com").strip().lower()
    test_recipient = os.environ.get("TEST_RECIPIENT_EMAIL", "").strip().lower()
    test_recipients = {from_email}
    if test_recipient:
        test_recipients.add(test_recipient)
    return normalised in test_recipients


def _find_lead_by_email(to_email: str) -> dict[str, Any] | None:
    leads = _load_leads()
    for record in leads:
        if (record.get("email") or "").strip().lower() == to_email:
            return record
    return None


def _is_lead_business_recipient(lead_id: str, email: str) -> bool:
    """Return whether the address appears to be a non-test restaurant recipient."""
    return bool(str(lead_id or "").strip()) and _valid_email(email) and not _is_test_recipient_email(email)


def _record_contact_emails(record: dict[str, Any]) -> list[str]:
    emails = [str(record.get("email") or "").strip()]
    for contact in record.get("contacts") or []:
        if not isinstance(contact, dict):
            continue
        if str(contact.get("type") or "").lower() != "email":
            continue
        if contact.get("actionable") is False:
            continue
        emails.append(str(contact.get("value") or "").strip())
    return [email for email in dict.fromkeys(emails) if email]


def _customer_copy_has_qr_first_signal(text: str) -> bool:
    lowered = text.lower()
    return "qr" in lowered or "英語qrメニュー" in lowered or "英語QRメニュー" in text


def _customer_copy_has_banned_term(text: str) -> bool:
    lowered = text.lower()
    for term in BANNED_CUSTOMER_TERMS:
        if re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", lowered):
            return True
    return False


def _send_readiness_for_record(
    record: dict[str, Any],
    *,
    final_check: bool = False,
    to_email: str = "",
) -> dict[str, Any]:
    """Evaluate whether a lead can be sent first-contact outreach."""
    reasons: list[str] = []

    email = str(to_email or record.get("email") or "").strip()
    valid_emails = [candidate for candidate in _record_contact_emails(record) if _valid_email(candidate)]
    if email and _valid_email(email) and email not in valid_emails:
        valid_emails.append(email)

    category = str(record.get("category") or record.get("primary_category_v1") or "").strip().lower()
    if record.get("lead") is not True or category == "skip":
        reasons.append("skipped_or_not_true_lead")
    if category and category not in ACTIVE_LEAD_CATEGORIES:
        reasons.append("unsupported_lead_category")
    if record.get("recommended_primary_package") != ENGLISH_QR_MENU_KEY:
        reasons.append("active_product_missing")
    if not valid_emails:
        reasons.append("email_not_verified")

    copy_fields = [
        str(record.get("outreach_draft_body") or ""),
        str(record.get("outreach_draft_english_body") or ""),
    ]
    combined_copy = "\n".join(part for part in copy_fields if part.strip())
    populated_copy_fields = [part for part in copy_fields if part.strip()]
    if not populated_copy_fields or any(not _customer_copy_has_qr_first_signal(part) for part in populated_copy_fields):
        reasons.append("stale_or_non_qr_first_draft")
    if _customer_copy_has_banned_term(combined_copy):
        reasons.append("banned_customer_copy_term")

    if final_check and _is_lead_business_recipient(str(record.get("lead_id") or ""), email or (valid_emails[0] if valid_emails else "")):
        if record.get("manual_real_send_approved") is not True:
            reasons.append("manual_real_send_approval_missing")

    return {
        "status": "ready_to_send" if not reasons else "not_ready",
        "reasons": reasons,
        "final_check": final_check,
    }


def _count_today_sends() -> int:
    sent_dir = STATE_ROOT / "sent"
    if not sent_dir.exists():
        return 0
    jst = timezone(timedelta(hours=9))
    today = datetime.now(jst).strftime("%Y-%m-%d")
    count = 0
    for path in sent_dir.glob("*.json"):
        data = _load_json(path)
        if not data:
            continue
        if data.get("test_send") or _is_test_recipient_email(data.get("to", "")):
            continue
        sent_at = data.get("sent_at", "")
        try:
            sent_dt = datetime.fromisoformat(sent_at.replace("Z", "+00:00")).astimezone(jst)
            if sent_dt.strftime("%Y-%m-%d") == today:
                count += 1
        except ValueError:
            continue
    return count


def _save_sent_email(
    lead_id: str,
    to_email: str,
    subject: str,
    body: str,
    classification: str = "",
    test_send: bool = False,
    attachment_metadata: dict[str, Any] | None = None,
) -> None:
    sent_dir = STATE_ROOT / "sent"
    sent_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    attachment_metadata = attachment_metadata or {
        "requested_assets": [], "render_sources": {},
        "inline_attachments": [], "file_attachments": [], "attachment_count": 0,
    }
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
    }
    path = sent_dir / f"{lead_id}_{ts}.json"
    from pipeline.utils import write_json
    write_json(path, record)


def _load_sent_history() -> list[dict[str, Any]]:
    sent_dir = STATE_ROOT / "sent"
    if not sent_dir.exists():
        return []
    history: list[dict[str, Any]] = []
    for path in sorted(sent_dir.glob("*.json")):
        data = _load_json(path)
        if data:
            history.append(data)
    return history


async def _send_email_resend(
    *,
    to: str,
    subject: str,
    body: str,
    in_reply_to: str = "",
    include_menu_image: bool = False,
    menu_html_path: str | None = None,
    business_name: str = "",
) -> dict:
    """Send an email via Resend with optional inline menu preview image."""
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

    # Render menu JPEG if requested
    menu_jpeg = None
    if include_menu_image and menu_html_path:
        menu_jpeg = await asyncio.to_thread(_ensure_menu_jpeg, menu_html_path)

    # Build HTML email body
    html_body = build_pitch_email_html(
        text_body=body,
        include_menu_image=bool(menu_jpeg),
        include_machine_image=False,
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

    # CID inline attachments (logo + menu preview)
    all_attachments = build_inline_attachments(
        menu_jpeg_path=menu_jpeg,
        machine_jpeg_path=None,
    )
    if all_attachments:
        params["attachments"] = all_attachments

    provider_result = _resend.Emails.send(params)

    attachment_metadata = []
    for item in all_attachments:
        content = str(item.get("content") or "")
        try:
            raw = base64.b64decode(content.encode("ascii"), validate=True) if content else b""
        except Exception:
            raw = b""
        attachment_metadata.append({
            "filename": item.get("filename", ""),
            "mime_type": item.get("mime_type", ""),
            "content_id": item.get("content_id", ""),
            "inline": item.get("disposition") == "inline",
            "size_bytes": len(raw),
        })

    result = {
        "provider_id": str(provider_result) if provider_result else "",
        "attachment_metadata": attachment_metadata,
    }
    return result


async def _send_lead_email_payload(
    *,
    lead_id: str,
    record: dict[str, Any],
    to_email: str,
    subject: str,
    email_body: str,
    is_test_send: bool,
) -> dict[str, Any]:
    """Send one lead email and persist sent status only after provider success."""
    include_menu_image = False
    menu_html_path = None
    ws_data = None
    for ws_file in STUDIO_DIR.glob("*.json"):
        ws = _load_json(ws_file)
        if ws and ws.get("lead_id") == lead_id:
            ws_data = ws
            break
    if ws_data and ws_data.get("items"):
        menu_data = _build_menu_data(ws_data)
        import tempfile
        tmp_dir = tempfile.mkdtemp(prefix="wrm-email-preview-")
        preview_path = Path(tmp_dir) / "menu_preview.html"
        preview_html = _generate_minimal_menu_html(menu_data)
        preview_path.write_text(preview_html, "utf-8")
        menu_html_path = str(preview_path)
        include_menu_image = True

    _log("send_attempted", f"to={to_email} test={is_test_send}", lead_id=lead_id)

    try:
        result = await _send_email_resend(
            to=to_email,
            subject=subject,
            body=email_body,
            include_menu_image=include_menu_image,
            menu_html_path=menu_html_path,
            business_name=record.get("business_name", ""),
        )
    except Exception as exc:
        _log("send_failed", str(exc)[:200], lead_id=lead_id)
        raise HTTPException(status_code=502, detail=f"Send failed: {exc}")

    if not is_test_send:
        from pipeline.record import persist_lead_record
        record["outreach_status"] = OUTREACH_STATUS_SENT
        record["outreach_sent_at"] = datetime.now(timezone.utc).isoformat()
        record["outreach_draft_body"] = email_body
        if "status_history" not in record:
            record["status_history"] = []
        record["status_history"].append({
            "status": OUTREACH_STATUS_SENT,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        persist_lead_record(record, state_root=STATE_ROOT)

    return result


# ===================================================================
# API — Send Email
# ===================================================================

@app.post("/api/send/{lead_id}")
async def api_send(lead_id: str, request: Request):
    """Send outreach email via Resend.

    Safety gates:
    - Lead must exist and have a valid email
    - Lead must not be in a blocked status (already sent, bounced, DNC, etc.)
    - Business sends require send_ready_checked=True
    - Test sends (to self) always allowed
    - Daily send limit enforced
    """
    body = await request.json()

    # Load lead
    from pipeline.record import load_lead, persist_lead_record
    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Block DNC
    if record.get("outreach_status") == "do_not_contact":
        raise HTTPException(status_code=403, detail="Lead is marked Do Not Contact")

    # Block re-sending to already-contacted businesses
    if record.get("outreach_status") in BLOCKED_SEND_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Lead already has status '{record.get('outreach_status')}' — cannot re-send",
        )

    # Get email fields
    to_email = str(body.get("email") or "").strip() or str(record.get("email") or "").strip()
    subject = str(body.get("subject") or "").strip() or str(record.get("outreach_draft_subject") or "").strip()
    email_body = str(body.get("body") or "").strip() or str(record.get("outreach_draft_body") or "").strip()

    if not to_email:
        raise HTTPException(status_code=400, detail="Email address required")
    if not _valid_email(to_email):
        raise HTTPException(status_code=400, detail="Invalid email address")
    if not subject:
        raise HTTPException(status_code=400, detail="Subject required")
    if not email_body:
        raise HTTPException(status_code=400, detail="Email body required")

    # Determine if this is a test send (to self) or business send
    from_email = os.environ.get("RESEND_FROM_EMAIL", "chris@webrefurb.com").strip().lower()
    is_test_send = to_email.strip().lower() in {from_email} or _is_test_recipient_email(to_email)

    # Business sends require send_ready gate
    if not is_test_send:
        if record.get("send_ready_checked") is not True:
            raise HTTPException(status_code=422, detail="Lead is not send-ready: final_check_missing")
        readiness = _send_readiness_for_record(record, final_check=True, to_email=to_email)
        if readiness["status"] != "ready_to_send":
            raise HTTPException(status_code=422, detail=f"Lead is not send-ready: {','.join(readiness['reasons'])}")

    # Rate limit
    today_sends = _count_today_sends()
    max_sends = int(os.environ.get("MAX_SENDS_PER_DAY", "50"))
    if today_sends >= max_sends:
        raise HTTPException(status_code=429, detail=f"Daily send limit reached ({today_sends}/{max_sends})")

    result = await _send_lead_email_payload(
        lead_id=lead_id,
        record=record,
        to_email=to_email,
        subject=subject,
        email_body=email_body,
        is_test_send=is_test_send,
    )

    # Track sent email
    _save_sent_email(
        lead_id, to_email, subject, email_body,
        classification=record.get("outreach_classification", ""),
        test_send=is_test_send,
        attachment_metadata=result.get("attachment_metadata"),
    )

    _log("send_succeeded", f"sends_today={today_sends + 1} test={is_test_send}", lead_id=lead_id)
    return {"status": "test_sent" if is_test_send else "sent", "sends_today": today_sends + 1}


@app.get("/api/sent")
async def api_sent():
    """Return all sent email records."""
    return _load_sent_history()


# ===================================================================
# API — Resend Webhook (bounce, complaint, delivery)
# ===================================================================

@app.post("/api/webhooks/resend")
async def api_resend_webhook(request: Request):
    """Handle inbound webhook events from Resend.

    Processes: email.bounced, email.complained, email.delivered.
    """
    body_bytes = await request.body()
    payload = await request.json()

    # Optional signature verification
    webhook_secret = os.environ.get("RESEND_WEBHOOK_SECRET", "")
    if webhook_secret:
        signature = request.headers.get("svix-signature", "")
        if signature:
            expected = hmac.new(
                webhook_secret.encode(), body_bytes, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(f"sha256={expected}", signature):
                raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event_type = payload.get("type", "")
    data = payload.get("data", {})
    to_email = str(data.get("to", "")).strip().lower()

    if event_type == "email.bounced":
        bounce_type = data.get("bounce_type", "permanent")
        record = _find_lead_by_email(to_email)
        if record:
            status = "invalid" if bounce_type == "invalid" else "bounced"
            record["outreach_status"] = status
            if "status_history" not in record:
                record["status_history"] = []
            record["status_history"].append({
                "status": status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": f"Email bounced: {bounce_type}",
            })
            from pipeline.record import persist_lead_record
            persist_lead_record(record, state_root=STATE_ROOT)
        _log("email_bounced", f"to={to_email} type={bounce_type}")
        return {"status": "bounced", "email": to_email}

    if event_type == "email.complained":
        record = _find_lead_by_email(to_email)
        if record:
            record = apply_opt_out(record, reason="spam_complaint")
            if "status_history" not in record:
                record["status_history"] = []
            record["status_history"].append({
                "status": "do_not_contact",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": "Spam complaint received via Resend webhook",
            })
            from pipeline.record import persist_lead_record
            persist_lead_record(record, state_root=STATE_ROOT)
        _log("email_complaint", f"to={to_email}")
        return {"status": "complaint", "email": to_email}

    if event_type == "email.delivered":
        _log("email_delivered", f"to={to_email}")
        return {"status": "delivered", "email": to_email}

    return {"status": "ignored", "type": event_type}


@app.post("/api/leads/{lead_id}/mark-unreachable")
async def api_mark_unreachable(lead_id: str, request: Request):
    """Operator marks a lead as bounced/invalid for non-email channels."""
    from pipeline.record import load_lead, persist_lead_record

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")

    body = await request.json()
    reason = str(body.get("reason", "marked_unreachable"))
    record["outreach_status"] = "bounced"
    if "status_history" not in record:
        record["status_history"] = []
    record["status_history"].append({
        "status": "bounced",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": reason,
    })
    persist_lead_record(record, state_root=STATE_ROOT)
    _log("mark_unreachable", reason, lead_id=lead_id)
    return {"status": "bounced"}


# ===================================================================
# API — Translation (incoming JA→EN, outgoing EN→JA)
# ===================================================================

@app.post("/api/translate/incoming")
async def api_translate_incoming(request: Request):
    """Translate a Japanese reply into English so the operator can read it."""
    from pipeline.llm_client import call_llm, LLMClientError

    body = await request.json()
    japanese_text = str(body.get("text", "")).strip()
    if not japanese_text:
        raise HTTPException(status_code=400, detail="Text required")

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY not configured")

    system_prompt = (
        "Translate the following Japanese text into clear, natural English. "
        "This is a reply from a Japanese restaurant owner to an outreach email about English menu creation. "
        "Preserve the meaning and tone. Output ONLY the English translation, no notes or explanations."
    )

    try:
        english = await asyncio.to_thread(
            call_llm,
            model="google/gemini-2.0-flash-001",
            system=system_prompt,
            user=japanese_text,
            api_key=api_key,
            max_tokens=2048,
            timeout_seconds=30,
        )
        return {"translation": english.strip()}
    except LLMClientError as exc:
        raise HTTPException(status_code=502, detail=f"Translation failed: {exc}")


@app.post("/api/translate/outgoing")
async def api_translate_outgoing(request: Request):
    """Translate an English reply into natural Japanese business email."""
    from pipeline.translate_reply import translate_reply, validate_translated_reply
    from pipeline.llm_client import LLMClientError

    body = await request.json()
    english_text = str(body.get("text", "")).strip()
    business_name = str(body.get("business_name", "")).strip() or None
    if not english_text:
        raise HTTPException(status_code=400, detail="Text required")

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY not configured")

    try:
        japanese = await asyncio.to_thread(
            translate_reply,
            english_text,
            business_name=business_name,
        )
        issues = validate_translated_reply(japanese)
        return {"translation": japanese, "quality_issues": issues}
    except LLMClientError as exc:
        raise HTTPException(status_code=502, detail=f"Translation failed: {exc}")


@app.post("/api/leads/{lead_id}/mark-replied")
async def api_mark_replied(lead_id: str, request: Request):
    """Mark a lead as replied (operator confirms they got a reply in Gmail)."""
    from pipeline.record import load_lead, persist_lead_record

    record = load_lead(lead_id, state_root=STATE_ROOT)
    if not record:
        raise HTTPException(status_code=404, detail="Lead not found")

    record["outreach_status"] = "replied"
    if "status_history" not in record:
        record["status_history"] = []
    record["status_history"].append({
        "status": "replied",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    persist_lead_record(record, state_root=STATE_ROOT)
    _log("mark_replied", lead_id=lead_id)
    return {"status": "replied"}
