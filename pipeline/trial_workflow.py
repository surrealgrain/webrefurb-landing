"""Trial lifecycle helpers for the English QR Menu workflow.

The trial state lives separately from first-contact outreach. A restaurant can
reply, request a trial, decline, convert, or be archived without weakening the
send gates used for cold outreach.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .constants import ENGLISH_QR_MENU_KEY, TRIAL_DURATION_DAYS
from .utils import write_json


TRIAL_STATES = (
    "requested",
    "accepted",
    "intake_needed",
    "build_started",
    "owner_review",
    "live_trial",
    "trial_ending",
    "converted",
    "declined",
    "archived",
)

TERMINAL_TRIAL_STATES = {"converted", "declined", "archived"}
PUBLIC_TRIAL_STATES = {"live_trial", "trial_ending", "converted"}

_ALLOWED_TRANSITIONS = {
    "requested": {"accepted", "declined", "archived"},
    "accepted": {"intake_needed", "build_started", "declined", "archived"},
    "intake_needed": {"build_started", "declined", "archived"},
    "build_started": {"owner_review", "declined", "archived"},
    "owner_review": {"live_trial", "build_started", "declined", "archived"},
    "live_trial": {"trial_ending", "converted", "declined", "archived"},
    "trial_ending": {"converted", "declined", "archived"},
    "converted": {"archived"},
    "declined": {"archived"},
    "archived": set(),
}


class TrialWorkflowError(ValueError):
    """Raised when a trial transition would create unsafe state."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_trial_id(*, lead_id: str = "", business_name: str = "") -> str:
    seed = str(lead_id or business_name or "").strip()
    if seed:
        safe = re.sub(r"[^a-z0-9]+", "-", seed.lower()).strip("-")
        return f"trial-{safe[:64]}"
    return f"trial-{uuid.uuid4().hex[:10]}"


def create_trial_record(
    *,
    lead: dict[str, Any] | None = None,
    reply: dict[str, Any] | None = None,
    requested_by: str = "operator",
    source_channel: str = "reply",
    now: str | None = None,
) -> dict[str, Any]:
    """Create an internal trial record without implying owner approval."""
    lead = lead or {}
    reply = reply or {}
    created_at = now or utc_now()
    lead_id = str(reply.get("lead_id") or lead.get("lead_id") or "")
    business_name = str(reply.get("business_name") or lead.get("business_name") or "")
    trial_id = stable_trial_id(lead_id=lead_id, business_name=business_name)
    record = {
        "trial_id": trial_id,
        "lead_id": lead_id,
        "reply_id": str(reply.get("reply_id") or ""),
        "business_name": business_name,
        "package_key": ENGLISH_QR_MENU_KEY,
        "status": "requested",
        "source_channel": source_channel,
        "requested_by": requested_by,
        "requested_at": created_at,
        "accepted_at": "",
        "live_trial_started_at": "",
        "trial_ends_at": "",
        "converted_at": "",
        "declined_at": "",
        "archived_at": "",
        "decline_reason": "",
        "public_url": "",
        "menu_id": "",
        "history": [],
        "privacy_note": "Owner-provided menu information is used only to create and operate the QR menu.",
    }
    _append_history(record, "requested", actor=requested_by, reason="trial record created", at=created_at)
    return record


def transition_trial(
    record: dict[str, Any],
    new_status: str,
    *,
    actor: str = "operator",
    reason: str = "",
    now: str | None = None,
    public_url: str = "",
    menu_id: str = "",
) -> dict[str, Any]:
    """Return a copy of the trial record moved to a validated state."""
    if new_status not in TRIAL_STATES:
        raise TrialWorkflowError(f"Unknown trial status: {new_status}")
    current = str(record.get("status") or "requested")
    if current not in TRIAL_STATES:
        raise TrialWorkflowError(f"Unknown current trial status: {current}")
    if new_status != current and new_status not in _ALLOWED_TRANSITIONS[current]:
        raise TrialWorkflowError(f"Invalid trial transition: {current} -> {new_status}")
    if new_status == current:
        unchanged = {**record}
        if public_url:
            unchanged["public_url"] = public_url
        if menu_id:
            unchanged["menu_id"] = menu_id
        return unchanged

    updated = {**record, "status": new_status, "updated_at": now or utc_now()}
    at = str(updated["updated_at"])
    if new_status == "accepted" and not updated.get("accepted_at"):
        updated["accepted_at"] = at
    if new_status == "live_trial":
        updated["live_trial_started_at"] = at
        updated["trial_ends_at"] = _plus_days(at, TRIAL_DURATION_DAYS)
    if new_status == "converted" and not updated.get("converted_at"):
        updated["converted_at"] = at
    if new_status == "declined" and not updated.get("declined_at"):
        updated["declined_at"] = at
        updated["decline_reason"] = reason
    if new_status == "archived" and not updated.get("archived_at"):
        updated["archived_at"] = at
    if public_url:
        updated["public_url"] = public_url
    if menu_id:
        updated["menu_id"] = menu_id
    _append_history(updated, new_status, actor=actor, reason=reason, at=at)
    return updated


def trial_publicly_indexable(record: dict[str, Any]) -> bool:
    """Return true only for trial states that may remain publicly reachable."""
    return str(record.get("status") or "") in PUBLIC_TRIAL_STATES and not record.get("archived_at")


def trial_followup_stage(record: dict[str, Any], *, now: str | None = None) -> str:
    """Return the current trial follow-up stage: day_5, day_7, day_10, or empty."""
    started_raw = str(record.get("live_trial_started_at") or "")
    if str(record.get("status") or "") not in {"live_trial", "trial_ending"} or not started_raw:
        return ""
    try:
        started = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
        current = datetime.fromisoformat((now or utc_now()).replace("Z", "+00:00"))
    except ValueError:
        return ""
    days = (current - started).days
    if days >= 10:
        return "day_10"
    if days >= TRIAL_DURATION_DAYS:
        return "day_7"
    if days >= 5:
        return "day_5"
    return ""


def trial_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {state: 0 for state in TRIAL_STATES}
    for record in records:
        status = str(record.get("status") or "")
        if status in counts:
            counts[status] += 1
    requested = len(records)
    converted = counts["converted"]
    accepted = sum(counts[state] for state in TRIAL_STATES if state not in {"requested", "declined", "archived"})
    return {
        "requested": requested,
        "accepted_or_later": accepted,
        "converted": converted,
        "declined": counts["declined"],
        "archived": counts["archived"],
        "conversion_rate": round(converted / requested, 4) if requested else 0.0,
        "by_status": counts,
    }


def save_trial_record(*, state_root: Path, record: dict[str, Any]) -> Path:
    path = Path(state_root) / "trials" / f"{record['trial_id']}.json"
    write_json(path, record)
    return path


def load_trial_record(*, state_root: Path, trial_id: str) -> dict[str, Any] | None:
    path = Path(state_root) / "trials" / f"{trial_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_trial_records(*, state_root: Path) -> list[dict[str, Any]]:
    root = Path(state_root) / "trials"
    if not root.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return records


def _append_history(record: dict[str, Any], status: str, *, actor: str, reason: str, at: str) -> None:
    history = list(record.get("history") or [])
    history.append({
        "status": status,
        "actor": actor,
        "reason": reason,
        "at": at,
    })
    record["history"] = history


def _plus_days(iso_value: str, days: int) -> str:
    value = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
    return (value + timedelta(days=days)).isoformat()
