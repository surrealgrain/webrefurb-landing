from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .lead_dossier import ensure_lead_dossier, READINESS_READY
from .record import get_primary_contact, load_lead, persist_lead_record
from .utils import ensure_dir, read_json, utc_now, write_json


class LaunchBatchError(ValueError):
    pass


def create_launch_batch(
    *,
    lead_ids: list[str],
    state_root: Path,
    notes: str = "",
) -> dict[str, Any]:
    """Create a controlled launch batch from 5-10 ready leads."""
    previous = list_launch_batches(state_root=state_root)
    unreviewed = [batch for batch in previous if not batch.get("reviewed_at")]
    if unreviewed:
        raise LaunchBatchError("previous_batch_not_reviewed")
    if not 5 <= len(lead_ids) <= 10:
        raise LaunchBatchError("batch_size_must_be_5_to_10")
    if len(set(lead_ids)) != len(lead_ids):
        raise LaunchBatchError("duplicate_lead_in_batch")

    entries, ready_leads = validate_launch_leads(lead_ids=lead_ids, state_root=state_root)

    batch_id = "launch-" + hashlib.sha1(("|".join(lead_ids) + utc_now()).encode("utf-8")).hexdigest()[:10]
    batch = {
        "batch_id": batch_id,
        "batch_number": len(previous) + 1,
        "created_at": utc_now(),
        "reviewed_at": "",
        "notes": notes,
        "lead_count": len(entries),
        "leads": entries,
    }
    path = _batch_path(state_root, batch_id)
    ensure_dir(path.parent)
    write_json(path, batch)

    for lead in ready_leads:
        lead["launch_batch_id"] = batch_id
        persist_lead_record(lead, state_root=state_root)

    return batch


def validate_launch_leads(*, lead_ids: list[str], state_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate launch lead readiness and return launch entries plus loaded leads."""
    entries: list[dict[str, Any]] = []
    ready_leads: list[dict[str, Any]] = []
    category_profiles: set[str] = set()
    for lead_id in lead_ids:
        lead = load_lead(lead_id, state_root=state_root)
        if not lead:
            raise LaunchBatchError(f"lead_not_found:{lead_id}")
        lead = ensure_lead_dossier(lead)
        if lead.get("launch_readiness_status") != READINESS_READY:
            raise LaunchBatchError(f"lead_not_ready:{lead_id}")
        measurement_missing = _missing_launch_measurement_fields(lead)
        if measurement_missing:
            raise LaunchBatchError(f"lead_launch_measurement_incomplete:{lead_id}:{','.join(measurement_missing)}")
        profile = str(lead.get("establishment_profile") or "")
        category_profiles.add(profile)
        entries.append(_launch_entry_from_lead(lead))
        ready_leads.append(lead)

    if not any(profile == "ramen_ticket_machine" for profile in category_profiles):
        raise LaunchBatchError("missing_ramen_ticket_machine_candidate")
    if not any(profile in {"izakaya_drink_heavy", "izakaya_course_heavy"} for profile in category_profiles):
        raise LaunchBatchError("missing_izakaya_drink_or_course_candidate")
    return entries, ready_leads


def record_launch_outcome(
    *,
    batch_id: str,
    lead_id: str,
    state_root: Path,
    outcome: dict[str, Any],
) -> dict[str, Any]:
    batch = load_launch_batch(batch_id=batch_id, state_root=state_root)
    if not batch:
        raise LaunchBatchError("batch_not_found")
    for entry in batch.get("leads") or []:
        if entry.get("lead_id") == lead_id:
            outcome_update = _normalise_launch_outcome(outcome)
            for key in ("contacted_at", "reply_status", "objection", "opt_out", "bounce", "operator_minutes"):
                if key in outcome_update:
                    entry[key] = outcome_update[key]
            entry["outcome"] = {
                **(entry.get("outcome") or {}),
                **outcome_update,
                "updated_at": utc_now(),
            }
            write_json(_batch_path(state_root, batch_id), batch)
            lead = load_lead(lead_id, state_root=state_root)
            if lead:
                lead["launch_outcome"] = entry["outcome"]
                persist_lead_record(lead, state_root=state_root)
            return entry
    raise LaunchBatchError("lead_not_in_batch")


def review_launch_batch(*, batch_id: str, state_root: Path, notes: str = "") -> dict[str, Any]:
    batch = load_launch_batch(batch_id=batch_id, state_root=state_root)
    if not batch:
        raise LaunchBatchError("batch_not_found")
    batch["reviewed_at"] = utc_now()
    batch["review_notes"] = notes
    write_json(_batch_path(state_root, batch_id), batch)
    return batch


def load_launch_batch(*, batch_id: str, state_root: Path) -> dict[str, Any] | None:
    return read_json(_batch_path(state_root, batch_id))


def list_launch_batches(*, state_root: Path) -> list[dict[str, Any]]:
    root = state_root / "launch_batches"
    if not root.exists():
        return []
    batches = [read_json(path) for path in sorted(root.glob("launch-*.json"))]
    return [batch for batch in batches if batch]


def _launch_entry_from_lead(lead: dict[str, Any]) -> dict[str, Any]:
    dossier = lead.get("lead_evidence_dossier") or {}
    primary_contact = get_primary_contact(lead) or {}
    return {
        "lead_id": lead.get("lead_id"),
        "business_name": lead.get("business_name"),
        "dossier_states": {
            "ticket_machine_state": dossier.get("ticket_machine_state"),
            "english_menu_state": dossier.get("english_menu_state"),
            "menu_complexity_state": dossier.get("menu_complexity_state"),
            "izakaya_rules_state": dossier.get("izakaya_rules_state"),
        },
        "selected_channel": primary_contact.get("type", ""),
        "message_variant": lead.get("message_variant", ""),
        "proof_asset": (lead.get("outreach_assets_selected") or [""])[0],
        "recommended_package": lead.get("recommended_primary_package", ""),
        "contacted_at": "",
        "reply_status": "not_contacted",
        "objection": "",
        "opt_out": False,
        "bounce": False,
        "operator_minutes": 0,
        "outcome": {},
    }


def _missing_launch_measurement_fields(lead: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    primary_contact = get_primary_contact(lead) or {}
    if not primary_contact.get("type"):
        missing.append("selected_channel")
    if not str(lead.get("message_variant") or "").strip():
        missing.append("message_variant")
    proof_asset = (lead.get("outreach_assets_selected") or [""])[0]
    proof_items = lead.get("proof_items") or (lead.get("lead_evidence_dossier") or {}).get("proof_items") or []
    if not proof_asset and not any(item.get("customer_preview_eligible") for item in proof_items):
        missing.append("proof_asset")
    if not str(lead.get("recommended_primary_package") or "").strip():
        missing.append("recommended_package")
    return missing


def _batch_path(state_root: Path, batch_id: str) -> Path:
    return state_root / "launch_batches" / f"{batch_id}.json"


def _normalise_launch_outcome(outcome: dict[str, Any]) -> dict[str, Any]:
    update = dict(outcome or {})
    reply_status = str(update.get("reply_status") or "").strip()
    opt_out = _truthy(update.get("opt_out")) or _truthy(update.get("opted_out")) or reply_status == "opted_out"
    bounce = _truthy(update.get("bounce")) or _truthy(update.get("bounced")) or reply_status == "bounced"

    if opt_out and not reply_status:
        reply_status = "opted_out"
    if bounce and not reply_status:
        reply_status = "bounced"

    normalised: dict[str, Any] = {}
    if "contacted_at" in update:
        normalised["contacted_at"] = str(update.get("contacted_at") or "")
    if reply_status:
        normalised["reply_status"] = reply_status
    if "objection" in update:
        normalised["objection"] = str(update.get("objection") or "")
    if "outcome" in update:
        normalised["outcome"] = str(update.get("outcome") or "")
    if "notes" in update:
        normalised["notes"] = str(update.get("notes") or "")
    if opt_out or "opt_out" in update or "opted_out" in update:
        normalised["opt_out"] = opt_out
    if bounce or "bounce" in update or "bounced" in update:
        normalised["bounce"] = bounce
    if "operator_minutes" in update:
        try:
            normalised["operator_minutes"] = max(0, int(update.get("operator_minutes") or 0))
        except (TypeError, ValueError):
            raise LaunchBatchError("invalid_operator_minutes")
    return normalised


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "opted_out", "bounced"}
