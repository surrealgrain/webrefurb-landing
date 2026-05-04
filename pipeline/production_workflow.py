"""Deterministic reply-to-production workflow helpers."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import PACKAGE_1_KEY, PACKAGE_2_KEY, PACKAGE_3_KEY
from .extract import extract_from_file, extract_from_text
from .ocr import extract_ocr_hints
from .utils import write_json

REPLY_INTENTS = {
    "interested",
    "price_question",
    "menu_photos_sent",
    "ticket_machine_photos_sent",
    "other_question",
    "not_interested",
    "unsubscribe",
}

NEXT_ACTIONS = {
    "ask_for_photos",
    "review_uploaded_photos",
    "answer_question",
    "send_quote",
    "build_sample",
    "close",
}

ORDER_STAGE_SEQUENCE = (
    "lead",
    "contact",
    "reply",
    "quote",
    "payment_pending",
    "paid",
    "intake",
    "production",
    "owner_review",
    "approval",
    "final_export",
    "download",
    "delivery_follow_up",
)

OWNER_ASSET_TYPES = {
    "food_menu_photo",
    "drink_menu_photo",
    "course_nomihodai_rules",
    "ticket_machine_photo",
    "wall_menu_signage",
    "shop_logo",
    "food_item_photo",
    "storefront_reference_photo",
    "irrelevant_unclear",
}

QUALITY_ISSUES = {
    "blurry",
    "cropped",
    "glare",
    "low_resolution",
    "duplicate",
    "missing_page_edges",
    "text_too_small",
    "wrong_file",
    "unreadable",
}

OPERATOR_ASSET_STATES = {"usable", "needs_better_photo", "not_needed"}

CORRECTION_TYPES = {
    "rename_item",
    "fix_price",
    "remove_item",
    "add_item",
    "change_photo",
    "correct_rule",
    "change_section",
    "approve_as_is",
}

PRODUCTION_QA_KEYS = (
    "all_source_photos_reviewed",
    "low_quality_photos_resolved",
    "japanese_item_names_checked",
    "english_labels_reviewed",
    "prices_hidden_or_owner_confirmed",
    "allergens_ingredients_hidden_or_owner_confirmed",
    "ticket_machine_buttons_mapped_or_unresolved",
    "pdf_mobile_previews_rendered",
    "visual_overflow_checks_passed",
    "forbidden_customer_language_scan_passed",
)

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"}
_MENU_WORDS = ("menu", "menyu", "メニュー", "品書", "お品書", "献立")
_DRINK_WORDS = ("drink", "drinks", "beverage", "nomihodai", "ドリンク", "飲み", "飲物", "酒", "日本酒", "焼酎", "飲み放題")
_COURSE_WORDS = ("course", "nomihodai", "rule", "rules", "コース", "飲み放題", "放題", "ルール")
_TICKET_WORDS = ("ticket", "machine", "kenbaiki", "vending", "券売機", "食券", "発券")
_LOGO_WORDS = ("logo", "ロゴ")
_STOREFRONT_WORDS = ("storefront", "exterior", "front", "店外", "外観")
_WALL_WORDS = ("wall", "sign", "kanban", "chalkboard", "壁", "看板", "黒板")
_ITEM_PHOTO_WORDS = ("dish", "foodphoto", "itemphoto", "料理写真", "商品写真")


def classify_reply_intent(body: str, attachments: Any = None) -> dict[str, Any]:
    """Classify an inbound owner reply into the Run 6 intent taxonomy."""
    text = str(body or "")
    lowered = text.lower()
    attachment_list = _normalise_attachment_list(attachments)
    filenames = " ".join(str(item.get("filename") or item.get("name") or item.get("stored_path") or "") for item in attachment_list)
    combined = f"{lowered} {filenames.lower()}"
    has_image = any(_attachment_is_image(item) for item in attachment_list)
    mentions_photo = _contains_any(combined, ("photo", "photos", "image", "images", "pic", "picture")) or any(
        token in text for token in ("写真", "画像", "添付", "送付", "送り", "アップロード")
    )
    mentions_ticket = _contains_any(combined, _TICKET_WORDS)
    mentions_price = _contains_any(combined, ("price", "cost", "quote", "estimate", "how much")) or any(
        token in text for token in ("料金", "費用", "価格", "見積", "いくら")
    )
    interested = _contains_any(combined, ("interested", "please", "sounds good", "go ahead", "tell me more")) or any(
        token in text for token in ("興味", "お願いします", "お願い", "詳しく", "検討", "希望", "作成")
    )
    signals: list[str] = []
    if has_image:
        signals.append("image_attachment")
    if mentions_photo:
        signals.append("photo_language")
    if mentions_ticket:
        signals.append("ticket_machine_language")
    if mentions_price:
        signals.append("price_language")
    if interested:
        signals.append("positive_language")

    if _contains_any(combined, ("unsubscribe", "stop email", "do not contact", "remove me")) or any(
        token in text for token in ("配信停止", "送らないで", "連絡不要")
    ):
        return _intent("unsubscribe", signals, positive=False)
    if _contains_any(combined, ("not interested", "no thank", "decline")) or any(
        token in text for token in ("不要", "必要ありません", "結構です", "お断り")
    ):
        return _intent("not_interested", signals, positive=False)
    if (has_image or mentions_photo) and mentions_ticket:
        return _intent("ticket_machine_photos_sent", signals, positive=True)
    if has_image or mentions_photo:
        return _intent("menu_photos_sent", signals, positive=True)
    if mentions_price:
        return _intent("price_question", signals, positive=True)
    if interested:
        return _intent("interested", signals, positive=True)
    return _intent("other_question", signals, positive=False)


def next_action_for_reply(
    reply: dict[str, Any],
    *,
    assets: list[dict[str, Any]] | None = None,
    order: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Return exactly one operator next action for a reply."""
    if str(reply.get("workflow_status") or "") in {"done", "archived"}:
        return _next("close", "Close", "No open operator action.")
    intent = str(reply.get("reply_intent") or "").strip()
    if intent not in REPLY_INTENTS:
        intent = classify_reply_intent(str(reply.get("body") or ""), reply.get("attachments"))["intent"]
    if intent in {"unsubscribe", "not_interested"}:
        return _next("close", "Close", "Owner declined or opted out.")
    if intent == "price_question":
        return _next("answer_question", "Answer question", "Owner asked about pricing or quote details.")
    if intent == "other_question":
        return _next("answer_question", "Answer question", "Owner reply needs a direct answer before production.")

    asset_list = list(assets or [])
    usable = [asset for asset in asset_list if asset.get("operator_status") == "usable"]
    needs_review = [
        asset for asset in asset_list
        if asset.get("operator_status") in {"", None, "needs_better_photo"}
    ]
    if asset_list and needs_review:
        return _next("review_uploaded_photos", "Review uploaded photos", "Classify each received owner asset as usable, needs better photo, or not needed.")
    if usable:
        if order and str((order.get("payment") or {}).get("status") or "") == "confirmed":
            return _next("build_sample", "Build sample", "Paid order has usable production assets.")
        return _next("send_quote", "Send quote", "Usable assets are ready; confirm package and quote before production.")
    return _next("ask_for_photos", "Ask for photos", "Positive reply needs current menu or ticket-machine photos.")


def build_order_intake_record(
    *,
    reply: dict[str, Any],
    lead: dict[str, Any] | None,
    package_key: str,
    order_id: str = "",
) -> dict[str, Any]:
    """Create a draft intake record without treating it as a paid order."""
    now = datetime.now(timezone.utc).isoformat()
    reply_id = str(reply.get("reply_id") or "")
    intake_id = f"intake-{reply_id.replace('reply-', '')}"[:80]
    return {
        "order_intake_id": intake_id,
        "order_id": order_id,
        "lead_id": str(reply.get("lead_id") or (lead or {}).get("lead_id") or ""),
        "reply_id": reply_id,
        "business_name": str(reply.get("business_name") or (lead or {}).get("business_name") or ""),
        "package_key": package_key,
        "status": "draft",
        "reply_intent": str(reply.get("reply_intent") or ""),
        "next_action": next_action_for_reply(reply),
        "source_channel": str(reply.get("channel") or ""),
        "created_at": now,
        "updated_at": now,
    }


def order_stage_status(order: dict[str, Any], *, has_reply: bool = False, has_download: bool = False) -> list[dict[str, Any]]:
    """Summarize every package stage from lead through delivery/follow-up."""
    state = str(order.get("state") or "")
    payment = order.get("payment") or {}
    intake = order.get("intake") or {}
    approval = order.get("approval") or {}
    final_export_ready = str(order.get("final_export_status") or "") == "ready" or bool(order.get("final_export_path"))
    completed = {
        "lead": bool(order.get("lead_id")),
        "contact": bool(order.get("lead_id") or order.get("business_name")),
        "reply": has_reply or bool(order.get("reply_id") or order.get("reply_ids")),
        "quote": state in {"quoted", "quote_sent", "payment_pending", "paid", "intake_needed", "in_production", "owner_review", "owner_approved", "delivered", "closed"},
        "payment_pending": state in {"payment_pending", "paid", "intake_needed", "in_production", "owner_review", "owner_approved", "delivered", "closed"},
        "paid": str(payment.get("status") or "") == "confirmed",
        "intake": bool(intake.get("is_complete")),
        "production": state in {"in_production", "owner_review", "owner_approved", "delivered", "closed"},
        "owner_review": state in {"owner_review", "owner_approved", "delivered", "closed"},
        "approval": bool(approval.get("approved")),
        "final_export": final_export_ready,
        "download": has_download or bool(order.get("downloaded_at")),
        "delivery_follow_up": state in {"delivered", "closed"} or bool(order.get("follow_up_due_at")),
    }
    return [{"stage": stage, "complete": bool(completed.get(stage))} for stage in ORDER_STAGE_SEQUENCE]


def ingest_owner_assets(reply: dict[str, Any], *, state_root: Path) -> dict[str, Any]:
    """Build a reply-scoped owner asset inbox and preserve original files."""
    reply_id = str(reply.get("reply_id") or "").strip()
    if not reply_id:
        raise ValueError("reply_id is required")
    root = Path(state_root) / "owner-assets" / reply_id
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    original_dir = root / "original"
    preview_dir = root / "previews"
    original_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)
    assets: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    body = str(reply.get("body") or "")
    for index, attachment in enumerate(_normalise_attachment_list(reply.get("attachments"))):
        source = Path(str(attachment.get("stored_path") or ""))
        filename = _safe_name(str(attachment.get("filename") or source.name or f"asset-{index}"))
        content_type = str(attachment.get("content_type") or "")
        if not source.exists() or not source.is_file():
            continue
        digest = _sha256_file(source)
        duplicate = digest in seen_hashes
        seen_hashes.add(digest)
        suffix = source.suffix.lower() or Path(filename).suffix.lower()
        asset_id = f"asset-{index + 1}-{digest[:10]}"
        original_path = original_dir / f"{digest[:12]}-{filename}"
        if not original_path.exists():
            shutil.copyfile(source, original_path)
        preview_path = ""
        if suffix in _IMAGE_EXTENSIONS:
            preview = preview_dir / f"{asset_id}{suffix}"
            if not preview.exists():
                shutil.copyfile(original_path, preview)
            preview_path = str(preview)
        asset_type = classify_owner_asset_type(filename=filename, body=body, content_type=content_type)
        quality_issues = detect_photo_quality_issues(
            path=original_path,
            filename=filename,
            content_type=content_type,
            duplicate=duplicate,
            asset_type=asset_type,
        )
        assets.append({
            "asset_id": asset_id,
            "reply_id": reply_id,
            "source_channel": str(reply.get("channel") or ""),
            "source_attachment_filename": filename,
            "source_attachment_stored_path": str(source),
            "original_path": str(original_path),
            "preview_path": preview_path,
            "sha256": digest,
            "content_type": content_type,
            "asset_type": asset_type,
            "quality_issues": quality_issues,
            "operator_status": _default_operator_asset_status(asset_type, quality_issues),
            "reviewed_at": "",
        })
    manifest = {
        "reply_id": reply_id,
        "lead_id": str(reply.get("lead_id") or ""),
        "source_channel": str(reply.get("channel") or ""),
        "assets": assets,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(manifest_path, manifest)
    return manifest


def classify_owner_asset_type(*, filename: str, body: str = "", content_type: str = "") -> str:
    text = f"{filename} {body} {content_type}".lower()
    if _contains_any(text, _TICKET_WORDS):
        return "ticket_machine_photo"
    if _contains_any(text, _COURSE_WORDS):
        return "course_nomihodai_rules"
    if _contains_any(text, _DRINK_WORDS):
        return "drink_menu_photo"
    if _contains_any(text, _LOGO_WORDS):
        return "shop_logo"
    if _contains_any(text, _WALL_WORDS):
        return "wall_menu_signage"
    if _contains_any(text, _STOREFRONT_WORDS):
        return "storefront_reference_photo"
    if _contains_any(text, _ITEM_PHOTO_WORDS):
        return "food_item_photo"
    if _contains_any(text, _MENU_WORDS):
        return "food_menu_photo"
    if content_type.startswith("image/"):
        return "food_menu_photo"
    return "irrelevant_unclear"


def detect_photo_quality_issues(
    *,
    path: Path,
    filename: str,
    content_type: str = "",
    duplicate: bool = False,
    asset_type: str = "",
) -> list[str]:
    text = filename.lower()
    issues: list[str] = []
    if duplicate:
        issues.append("duplicate")
    if asset_type == "irrelevant_unclear":
        issues.append("wrong_file")
    if not content_type.startswith("image/") and Path(filename).suffix.lower() not in {*_IMAGE_EXTENSIONS, ".pdf"}:
        issues.append("wrong_file")
    if path.exists() and path.stat().st_size < 1500 and Path(filename).suffix.lower() in _IMAGE_EXTENSIONS:
        issues.append("low_resolution")
    for marker, issue in (
        ("blur", "blurry"),
        ("cropped", "cropped"),
        ("crop", "cropped"),
        ("glare", "glare"),
        ("edge", "missing_page_edges"),
        ("small", "text_too_small"),
        ("unreadable", "unreadable"),
    ):
        if marker in text:
            issues.append(issue)
    return sorted(set(issue for issue in issues if issue in QUALITY_ISSUES))


def extract_structured_menu_content(*, raw_text: str = "", assets: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Extract menu fields and group them into operator-review sections."""
    extracted = extract_from_text(raw_text) if raw_text else []
    issues: list[str] = []
    if not extracted:
        for asset in assets or []:
            if asset.get("operator_status") != "usable":
                continue
            if asset.get("asset_type") not in {"food_menu_photo", "drink_menu_photo", "course_nomihodai_rules", "wall_menu_signage"}:
                continue
            extracted.extend(extract_from_file(str(asset.get("original_path") or "")))
            if extracted:
                break
            hints = extract_ocr_hints(str(asset.get("original_path") or ""))
            if hints:
                issues.append("low_confidence_ocr")
                for line in hints[0].text_lines:
                    extracted.extend(extract_from_text(line))
    sections: dict[str, list[dict[str, Any]]] = {}
    seen_names: set[str] = set()
    for item in extracted:
        section = _normalise_section(str(item.section_hint or item.section_hint or "notes"))
        name = str(item.japanese_name or item.name or item.source_text or "").strip()
        if name in seen_names:
            issues.append("duplicate_items")
        seen_names.add(name)
        price = str(item.price or "").strip()
        sections.setdefault(section, []).append({
            "japanese_item_name": name,
            "tentative_english_label": _tentative_english_label(name),
            "description": "",
            "option_rule_text": "",
            "price": price,
            "price_status": "detected_in_source" if price else "unknown",
            "owner_confirmation_status": "pending_review",
            "source_provenance": str(item.source_provenance or "owner_text"),
        })
    return {
        "sections": [{"section": key, "items": value} for key, value in sections.items()],
        "issues": sorted(set(issues)),
    }


def build_ticket_machine_mapping(*, assets: list[dict[str, Any]] | None = None, raw_text: str = "") -> dict[str, Any]:
    """Create a visual ticket-machine mapping model suitable for UI rows."""
    candidate_assets = [asset for asset in assets or [] if asset.get("asset_type") == "ticket_machine_photo"]
    lines = [line.strip() for line in str(raw_text or "").splitlines() if line.strip()]
    rows: list[dict[str, Any]] = []
    duplicate_labels: set[str] = set()
    seen_labels: set[str] = set()
    if lines:
        for row_index, line in enumerate(lines[:8], start=1):
            labels = [part.strip() for part in re.split(r"[,、\t|/]+", line) if part.strip()]
            buttons = []
            for col_index, label in enumerate(labels[:8], start=1):
                if label in seen_labels:
                    duplicate_labels.add(label)
                seen_labels.add(label)
                buttons.append({
                    "row": row_index,
                    "column": col_index,
                    "group": _normalise_section(label),
                    "color": "",
                    "button_label": label,
                    "linked_menu_item": "",
                    "status": "unmapped",
                })
            rows.append({"row": row_index, "buttons": buttons})
    elif candidate_assets:
        rows.append({
            "row": 1,
            "buttons": [{
                "row": 1,
                "column": 1,
                "group": "ramen",
                "color": "",
                "button_label": "unread_ticket_machine_button",
                "linked_menu_item": "",
                "status": "unmapped",
            }],
        })
    return {
        "source_asset_ids": [str(asset.get("asset_id") or "") for asset in candidate_assets],
        "rows": rows,
        "columns": max((len(row["buttons"]) for row in rows), default=0),
        "groups": sorted({button["group"] for row in rows for button in row["buttons"]}),
        "unmapped_buttons": [button for row in rows for button in row["buttons"] if not button.get("linked_menu_item")],
        "duplicate_labels": sorted(duplicate_labels),
        "ui": {
            "type": "ticket_machine_grid",
            "row_count": len(rows),
            "button_count": sum(len(row["buttons"]) for row in rows),
        },
    }


def recheck_package_fit(
    *,
    assets: list[dict[str, Any]],
    current_package_key: str = "",
    override_package_key: str = "",
    override_reason: str = "",
) -> dict[str, Any]:
    """Re-score package fit after owner assets arrive."""
    if override_package_key:
        if not str(override_reason or "").strip():
            return {
                "package_key": current_package_key or PACKAGE_1_KEY,
                "requires_custom_quote": False,
                "reason": "operator_override_requires_reason",
                "blockers": ["operator_package_override_reason_missing"],
            }
        return {
            "package_key": override_package_key,
            "requires_custom_quote": override_package_key == "custom_quote",
            "reason": str(override_reason),
            "blockers": [],
        }
    usable_assets = [asset for asset in assets if asset.get("operator_status") == "usable"]
    types = {str(asset.get("asset_type") or "") for asset in usable_assets}
    if len(usable_assets) > 8:
        return {"package_key": "custom_quote", "requires_custom_quote": True, "reason": "huge_or_unclear_asset_set_requires_custom_quote", "blockers": []}
    pending_asset_review = bool(assets) and not usable_assets
    menu_rule_types = {"drink_menu_photo", "course_nomihodai_rules", "wall_menu_signage"}
    if current_package_key == PACKAGE_3_KEY and assets:
        return {
            "package_key": PACKAGE_3_KEY,
            "requires_custom_quote": False,
            "reason": "current_qr_menu_package_preserved_for_owner_assets",
            "blockers": ["owner_assets_need_review"] if pending_asset_review else [],
        }
    if len(types & menu_rule_types) >= 2:
        return {"package_key": PACKAGE_3_KEY, "requires_custom_quote": False, "reason": "multiple_drink_course_rule_assets_fit_qr_menu", "blockers": []}
    if current_package_key == PACKAGE_2_KEY and assets:
        return {
            "package_key": PACKAGE_2_KEY,
            "requires_custom_quote": False,
            "reason": "current_printed_delivery_package_preserved_for_owner_assets",
            "blockers": ["owner_assets_need_review"] if pending_asset_review else [],
        }
    if "ticket_machine_photo" in types:
        return {"package_key": PACKAGE_1_KEY, "requires_custom_quote": False, "reason": "ticket_machine_guide_fits_english_ordering_files", "blockers": []}
    return {"package_key": PACKAGE_1_KEY, "requires_custom_quote": False, "reason": "simple_one_page_menu_fits_english_ordering_files", "blockers": []}


def build_production_workspace(
    *,
    reply: dict[str, Any],
    assets: list[dict[str, Any]],
    extracted_content: dict[str, Any],
    ticket_mapping: dict[str, Any],
    package_fit: dict[str, Any],
) -> dict[str, Any]:
    """Return the structured build-studio workspace shape."""
    unresolved = list(extracted_content.get("issues") or [])
    if ticket_mapping.get("unmapped_buttons"):
        unresolved.append("ticket_machine_unmapped_buttons")
    if package_fit.get("blockers"):
        unresolved.extend(package_fit["blockers"])
    return {
        "left_rail": {
            "source_assets": assets,
            "extracted_content": extracted_content,
            "unresolved_questions": sorted(set(unresolved)),
        },
        "center": {
            "live_rendered_preview": {
                "status": "pending_render",
                "preview_url": "",
            },
            "ticket_machine_mapping": ticket_mapping,
            "ticket_machine_mapping_ui": ticket_mapping.get("ui", {}),
        },
        "right_rail": {
            "structured_controls": {
                "profile": str(reply.get("establishment_profile") or ""),
                "template": "",
                "section_order": [],
                "item_density": "balanced",
                "photo_usage": "owner_photos_only",
                "price_visibility": "owner_confirmed_only",
                "outputs": {
                    "qr": package_fit.get("package_key") == PACKAGE_3_KEY,
                    "print": package_fit.get("package_key") in {PACKAGE_1_KEY, PACKAGE_2_KEY},
                    "ticket": bool(ticket_mapping.get("rows")),
                },
                "notes": "",
            }
        },
        "package_fit": package_fit,
    }


def evaluate_pre_owner_preview_qa(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the pre-owner-preview QA checklist."""
    checklist = {key: bool(payload.get(key)) for key in PRODUCTION_QA_KEYS}
    blockers = [key for key, passed in checklist.items() if not passed]
    return {
        "ok": not blockers,
        "checklist": checklist,
        "blockers": blockers,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def build_correction_task(task_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize one owner correction request into a structured task."""
    if task_type not in CORRECTION_TYPES:
        raise ValueError(f"unsupported_correction_type:{task_type}")
    return {
        "task_id": f"correction-{uuid.uuid4().hex[:10]}",
        "task_type": task_type,
        "status": "open" if task_type != "approve_as_is" else "approved",
        "item_id": str(payload.get("item_id") or ""),
        "section": str(payload.get("section") or ""),
        "current_value": str(payload.get("current_value") or ""),
        "requested_value": str(payload.get("requested_value") or ""),
        "note": str(payload.get("note") or ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def load_asset_manifest(reply_id: str, *, state_root: Path) -> dict[str, Any]:
    path = Path(state_root) / "owner-assets" / Path(str(reply_id)).name / "manifest.json"
    if not path.exists():
        return {"reply_id": reply_id, "assets": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"reply_id": reply_id, "assets": []}


def update_asset_operator_status(
    *,
    reply_id: str,
    asset_id: str,
    status: str,
    state_root: Path,
    note: str = "",
) -> dict[str, Any]:
    if status not in OPERATOR_ASSET_STATES:
        raise ValueError("invalid_operator_asset_status")
    root = Path(state_root) / "owner-assets" / Path(str(reply_id)).name
    manifest_path = root / "manifest.json"
    manifest = load_asset_manifest(reply_id, state_root=state_root)
    updated = False
    now = datetime.now(timezone.utc).isoformat()
    for asset in manifest.get("assets") or []:
        if str(asset.get("asset_id") or "") == asset_id:
            asset["operator_status"] = status
            asset["operator_note"] = note
            asset["reviewed_at"] = now
            updated = True
            break
    if not updated:
        raise ValueError("asset_not_found")
    write_json(manifest_path, manifest)
    return manifest


def _intent(intent: str, signals: list[str], *, positive: bool) -> dict[str, Any]:
    return {"intent": intent, "signals": sorted(set(signals)), "positive": positive}


def _next(key: str, label: str, detail: str) -> dict[str, str]:
    return {"key": key, "label": label, "detail": detail}


def _normalise_attachment_list(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _attachment_is_image(attachment: dict[str, Any]) -> bool:
    content_type = str(attachment.get("content_type") or attachment.get("contentType") or "").lower()
    filename = str(attachment.get("filename") or attachment.get("name") or attachment.get("stored_path") or "").lower()
    return content_type.startswith("image/") or Path(filename).suffix.lower() in _IMAGE_EXTENSIONS


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles)


def _safe_name(filename: str) -> str:
    safe = Path(str(filename or "")).name.strip().replace("\x00", "")
    return safe or f"asset-{uuid.uuid4().hex[:8]}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _default_operator_asset_status(asset_type: str, issues: list[str]) -> str:
    if asset_type == "irrelevant_unclear" or "wrong_file" in issues or "duplicate" in issues:
        return "not_needed"
    if issues:
        return "needs_better_photo"
    return "usable"


def _normalise_section(text: str) -> str:
    lowered = str(text or "").lower()
    if any(token in lowered for token in ("topping", "トッピング", "追加")):
        return "toppings"
    if any(token in lowered for token in ("rice", "side", "ご飯", "丼", "餃子", "サイド")):
        return "rice_sides"
    if any(token in lowered for token in ("drink", "beer", "ドリンク", "飲み", "酒")):
        return "drinks"
    if any(token in lowered for token in ("course", "コース", "放題")):
        return "courses"
    if any(token in lowered for token in ("rule", "note", "注意", "ルール")):
        return "rules"
    if any(token in lowered for token in ("special", "限定", "おすすめ")):
        return "specials"
    if any(token in lowered for token in ("set", "セット")):
        return "set_menus"
    if any(token in lowered for token in ("ramen", "ラーメン", "麺")):
        return "ramen"
    return "notes"


def _tentative_english_label(name: str) -> str:
    text = str(name or "").strip()
    known = {
        "醤油": "Shoyu",
        "味噌": "Miso",
        "塩": "Salt",
        "餃子": "Gyoza",
        "唐揚げ": "Fried Chicken",
        "ビール": "Beer",
    }
    for jp, en in known.items():
        if jp in text:
            return en if text == jp else text.replace(jp, en)
    return text
