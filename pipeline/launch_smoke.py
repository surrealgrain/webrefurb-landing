from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .launch import LaunchBatchError, validate_launch_leads
from .models import QualificationResult
from .outreach import (
    build_manual_outreach_message,
    build_outreach_email,
    classify_business,
    select_outreach_assets,
)
from .record import load_lead, persist_lead_record
from .utils import ensure_dir, read_json, utc_now, write_json


def prepare_launch_smoke_drafts(*, lead_ids: list[str], state_root: Path) -> list[dict[str, Any]]:
    """Generate no-send drafts needed before a launch rehearsal can be selected."""
    prepared: list[dict[str, Any]] = []
    for lead_id in lead_ids:
        lead = load_lead(lead_id, state_root=state_root)
        if not lead:
            raise LaunchBatchError(f"lead_not_found:{lead_id}")
        prepared.append(_prepare_launch_smoke_draft(lead=lead, state_root=state_root))
    return prepared


def create_launch_smoke_test(
    *,
    lead_ids: list[str],
    state_root: Path,
    notes: str = "",
    scenario: str = "real_world_no_send",
) -> dict[str, Any]:
    """Create a no-send rehearsal using the same lead gates as a launch batch."""
    if not 5 <= len(lead_ids) <= 10:
        raise LaunchBatchError("smoke_size_must_be_5_to_10")
    if len(set(lead_ids)) != len(lead_ids):
        raise LaunchBatchError("duplicate_lead_in_smoke_test")

    entries, ready_leads = validate_launch_leads(lead_ids=lead_ids, state_root=state_root)
    smoke_id = "smoke-" + hashlib.sha1(("|".join(lead_ids) + utc_now()).encode("utf-8")).hexdigest()[:10]
    smoke = {
        "smoke_test_id": smoke_id,
        "scenario": scenario,
        "created_at": utc_now(),
        "reviewed_at": "",
        "notes": notes,
        "lead_count": len(entries),
        "external_send_performed": False,
        "send_allowed": False,
        "counts_as_launch_batch": False,
        "phase_claim": "phase_11_rehearsal_only",
        "leads": [_smoke_entry(entry) for entry in entries],
    }
    path = _smoke_path(state_root, smoke_id)
    ensure_dir(path.parent)
    write_json(path, smoke)

    for lead in ready_leads:
        smoke_ids = list(lead.get("launch_smoke_test_ids") or [])
        if smoke_id not in smoke_ids:
            smoke_ids.append(smoke_id)
        lead["launch_smoke_test_ids"] = smoke_ids
        lead["last_launch_smoke_test_id"] = smoke_id
        persist_lead_record(lead, state_root=state_root)

    return smoke


def _prepare_launch_smoke_draft(*, lead: dict[str, Any], state_root: Path) -> dict[str, Any]:
    business_name = str(lead.get("business_name") or "")
    primary_contact = _primary_contact(lead)
    contact_type = str((primary_contact or {}).get("type") or "email")
    draft_channel = contact_type if contact_type and contact_type != "email" else "email"
    classification = str(lead.get("outreach_classification") or "")
    if not classification:
        classification = classify_business(QualificationResult(
            lead=lead.get("lead") is True,
            rejection_reason=lead.get("rejection_reason"),
            business_name=business_name,
            menu_evidence_found=lead.get("menu_evidence_found", True),
            machine_evidence_found=lead.get("machine_evidence_found", False),
        ))
    profile = _effective_profile(lead)
    sample_menu_url = str(lead.get("sample_menu_url") or lead.get("hosted_menu_sample_url") or "")
    if draft_channel == "contact_form":
        from .hosted_sample import ensure_hosted_menu_sample

        lead, sample_result = ensure_hosted_menu_sample(lead, state_root=state_root)
        if not sample_result.get("ok"):
            persist_lead_record(lead, state_root=state_root)
            raise LaunchBatchError(f"hosted_sample_publish_failed:{lead.get('lead_id', '')}")
        sample_menu_url = str(sample_result.get("sample_menu_url") or sample_menu_url)

    assets = select_outreach_assets(
        classification,
        contact_type=draft_channel,
        establishment_profile=profile,
    )
    if draft_channel == "email":
        draft = build_outreach_email(
            business_name=business_name,
            classification=classification,
            establishment_profile=profile,
            include_inperson_line=lead.get("outreach_include_inperson", True),
            lead_dossier=lead.get("lead_evidence_dossier") or {},
        )
    else:
        draft = build_manual_outreach_message(
            business_name=business_name,
            classification=classification,
            channel=draft_channel,
            establishment_profile=profile,
            include_inperson_line=lead.get("outreach_include_inperson", True),
            lead_dossier=lead.get("lead_evidence_dossier") or {},
            sample_menu_url=sample_menu_url,
        )

    lead["primary_contact"] = primary_contact
    lead["outreach_classification"] = classification
    lead["outreach_assets_selected"] = [str(path) for path in assets]
    lead["message_variant"] = f"{draft_channel}:{classification}:{profile}"
    lead["outreach_draft_subject"] = draft.get("subject", "")
    lead["outreach_draft_body"] = draft.get("body", "")
    lead["outreach_draft_english_body"] = draft.get("english_body", "")
    lead["outreach_draft_manually_edited"] = False
    lead["outreach_draft_edited_at"] = ""
    lead["no_send_draft_generated_at"] = utc_now()
    lead["outreach_sent_at"] = lead.get("outreach_sent_at") or None
    if lead.get("outreach_status") == "new":
        lead["outreach_status"] = "draft"
        history = list(lead.get("status_history") or [])
        history.append({"status": "draft", "timestamp": utc_now()})
        lead["status_history"] = history
    persist_lead_record(lead, state_root=state_root)
    return lead


def _primary_contact(lead: dict[str, Any]) -> dict[str, Any]:
    primary = lead.get("primary_contact") if isinstance(lead.get("primary_contact"), dict) else {}
    if primary and primary.get("actionable"):
        return dict(primary)
    for contact in lead.get("contacts") or []:
        if isinstance(contact, dict) and contact.get("actionable"):
            return dict(contact)
    return {}


def _effective_profile(lead: dict[str, Any]) -> str:
    profile = str(lead.get("establishment_profile") or "").strip()
    if profile:
        return profile
    category = str(lead.get("primary_category_v1") or "")
    if category == "izakaya":
        return "izakaya_food_and_drinks"
    return "ramen_only"


def record_launch_smoke_outcome(
    *,
    smoke_test_id: str,
    lead_id: str,
    state_root: Path,
    outcome: dict[str, Any],
) -> dict[str, Any]:
    smoke = load_launch_smoke_test(smoke_test_id=smoke_test_id, state_root=state_root)
    if not smoke:
        raise LaunchBatchError("smoke_test_not_found")
    for entry in smoke.get("leads") or []:
        if entry.get("lead_id") == lead_id:
            simulated = _normalise_smoke_outcome(outcome)
            entry["simulated_outcome"] = {**(entry.get("simulated_outcome") or {}), **simulated, "updated_at": utc_now()}
            write_json(_smoke_path(state_root, smoke_test_id), smoke)
            lead = load_lead(lead_id, state_root=state_root)
            if lead:
                lead["last_launch_smoke_outcome"] = entry["simulated_outcome"]
                persist_lead_record(lead, state_root=state_root)
            return entry
    raise LaunchBatchError("lead_not_in_smoke_test")


def review_launch_smoke_test(*, smoke_test_id: str, state_root: Path, notes: str = "") -> dict[str, Any]:
    smoke = load_launch_smoke_test(smoke_test_id=smoke_test_id, state_root=state_root)
    if not smoke:
        raise LaunchBatchError("smoke_test_not_found")
    smoke["reviewed_at"] = utc_now()
    smoke["review_notes"] = notes
    write_json(_smoke_path(state_root, smoke_test_id), smoke)
    return smoke


def load_launch_smoke_test(*, smoke_test_id: str, state_root: Path) -> dict[str, Any] | None:
    return read_json(_smoke_path(state_root, smoke_test_id))


def list_launch_smoke_tests(*, state_root: Path) -> list[dict[str, Any]]:
    root = state_root / "launch_smoke_tests"
    if not root.exists():
        return []
    smokes = [read_json(path) for path in sorted(root.glob("smoke-*.json"))]
    return [smoke for smoke in smokes if smoke]


def _smoke_entry(entry: dict[str, Any]) -> dict[str, Any]:
    updated = dict(entry)
    updated["external_send_performed"] = False
    updated["reply_status"] = "not_contacted"
    updated["contacted_at"] = ""
    updated["simulated_outcome"] = {}
    return updated


def _smoke_path(state_root: Path, smoke_test_id: str) -> Path:
    return state_root / "launch_smoke_tests" / f"{smoke_test_id}.json"


def _normalise_smoke_outcome(outcome: dict[str, Any]) -> dict[str, Any]:
    update = dict(outcome or {})
    blocked_contact_fields = {"contacted_at", "outreach_sent_at", "sent_at"}
    if any(update.get(key) for key in blocked_contact_fields):
        raise LaunchBatchError("smoke_test_cannot_record_real_contact_timestamp")
    normalised = {
        "simulated_reply_status": str(update.get("simulated_reply_status") or update.get("reply_status") or "simulated_not_sent"),
        "operator_minutes": _operator_minutes(update.get("operator_minutes")),
        "notes": str(update.get("notes") or ""),
        "risk": str(update.get("risk") or ""),
        "next_action": str(update.get("next_action") or ""),
    }
    return normalised


def _operator_minutes(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        raise LaunchBatchError("invalid_operator_minutes")
