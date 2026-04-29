from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .launch import LaunchBatchError, validate_launch_leads
from .record import load_lead, persist_lead_record
from .utils import ensure_dir, read_json, utc_now, write_json


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
