"""Outreach send policy helpers.

These helpers are intentionally provider-neutral. The dashboard still performs
the actual Resend call; this module handles durable opt-out and batch policy
decisions that are easy to test.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


REAL_SEND_BATCH_LIMIT = 10
DOMAIN_COOLDOWN_HOURS = 24
DO_NOT_CONTACT_STATUSES = {"do_not_contact", "unsubscribed", "bounced", "complained", "invalid"}


def apply_opt_out(record: dict[str, Any], *, reason: str = "owner_opt_out", now: str | None = None) -> dict[str, Any]:
    updated = dict(record)
    stamp = now or datetime.now(timezone.utc).isoformat()
    updated["do_not_contact"] = True
    updated["outreach_status"] = "do_not_contact"
    updated["opt_out_reason"] = reason
    updated["opt_out_at"] = stamp
    updated["send_ready_checked"] = False
    updated["manual_real_send_approved"] = False
    return updated


def record_blocks_send(record: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if record.get("do_not_contact") is True:
        reasons.append("do_not_contact")
    if str(record.get("outreach_status") or "").lower() in DO_NOT_CONTACT_STATUSES:
        reasons.append(f"terminal_outreach_status:{record.get('outreach_status')}")
    if str(record.get("email_verification_status") or "").lower() == "bounced":
        reasons.append("email_bounced")
    return reasons


def batch_send_policy(
    records: list[dict[str, Any]],
    *,
    approved: bool,
    sent_history: list[dict[str, Any]] | None = None,
    now: str | None = None,
    max_batch_size: int = REAL_SEND_BATCH_LIMIT,
    domain_cooldown_hours: int = DOMAIN_COOLDOWN_HOURS,
) -> dict[str, Any]:
    reasons: list[str] = []
    if not approved:
        reasons.append("manual_batch_approval_missing")
    if len(records) > max_batch_size:
        reasons.append("batch_size_limit_exceeded")
    blocked_records = []
    for record in records:
        blockers = record_blocks_send(record)
        if blockers:
            blocked_records.append({"lead_id": record.get("lead_id", ""), "reasons": blockers})
    if blocked_records:
        reasons.append("record_blockers_present")

    cooldown_hits = domain_cooldown_hits(records, sent_history or [], now=now, hours=domain_cooldown_hours)
    if cooldown_hits:
        reasons.append("domain_cooldown_active")

    return {
        "ok": not reasons,
        "reasons": reasons,
        "blocked_records": blocked_records,
        "cooldown_hits": cooldown_hits,
        "max_batch_size": max_batch_size,
    }


def domain_cooldown_hits(
    records: list[dict[str, Any]],
    sent_history: list[dict[str, Any]],
    *,
    now: str | None = None,
    hours: int = DOMAIN_COOLDOWN_HOURS,
) -> list[str]:
    current = datetime.fromisoformat((now or datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00"))
    domains = {_email_domain(str(record.get("email") or "")) for record in records}
    domains.discard("")
    hits: set[str] = set()
    for sent in sent_history:
        domain = _email_domain(str(sent.get("to") or sent.get("email") or ""))
        if domain not in domains:
            continue
        try:
            sent_at = datetime.fromisoformat(str(sent.get("sent_at") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if current - sent_at < timedelta(hours=hours):
            hits.add(domain)
    return sorted(hits)


def _email_domain(value: str) -> str:
    value = value.strip().lower()
    if "@" not in value:
        return ""
    return value.rsplit("@", 1)[1]
