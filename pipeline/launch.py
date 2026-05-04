from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .lead_dossier import ensure_lead_dossier, READINESS_READY
from .launch_freeze import assert_launch_not_frozen
from .operator_state import OPERATOR_READY
from .record import get_primary_contact, load_lead, persist_lead_record
from .utils import ensure_dir, read_json, utc_now, write_json


class LaunchBatchError(ValueError):
    pass


POSITIVE_REPLY_STATUSES = {
    "positive",
    "positive_reply",
    "interested",
    "owner_interested",
    "owner_requested_sample",
    "owner_requested_quote",
    "quote_requested",
    "sample_requested",
}
NON_RESPONSE_REPLY_STATUSES = {"", "not_contacted", "no_reply", "bounced"}


def create_launch_batch(
    *,
    lead_ids: list[str],
    state_root: Path,
    notes: str = "",
) -> dict[str, Any]:
    """Create a controlled launch batch from 5-10 ready leads."""
    assert_launch_not_frozen(state_root=state_root)
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
        if lead.get("operator_state") != OPERATOR_READY:
            raise LaunchBatchError(f"lead_operator_not_ready:{lead_id}:{lead.get('operator_reason') or 'review_required'}")
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


def review_launch_batch(
    *,
    batch_id: str,
    state_root: Path,
    notes: str = "",
    iteration_decisions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    batch = load_launch_batch(batch_id=batch_id, state_root=state_root)
    if not batch:
        raise LaunchBatchError("batch_not_found")
    reviewed_at = utc_now()
    batch["reviewed_at"] = reviewed_at
    batch["review_notes"] = notes
    batch["phase_12_review"] = build_launch_batch_review(
        batch=batch,
        reviewed_at=reviewed_at,
        notes=notes,
        iteration_decisions=iteration_decisions,
    )
    write_json(_batch_path(state_root, batch_id), batch)
    return batch


def build_launch_batch_review(
    *,
    batch: dict[str, Any],
    reviewed_at: str | None = None,
    notes: str = "",
    iteration_decisions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize observed Batch 1 outcomes for the Phase 12 gate."""
    entries = list(batch.get("leads") or [])
    contacted = [entry for entry in entries if _was_contacted(entry)]
    responses = [entry for entry in contacted if _has_owner_response(entry)]
    positives = [entry for entry in responses if _is_positive_reply(entry)]
    objections = [
        {
            "lead_id": entry.get("lead_id"),
            "business_name": entry.get("business_name"),
            "objection": str(entry.get("objection") or (entry.get("outcome") or {}).get("objection") or "").strip(),
        }
        for entry in contacted
        if str(entry.get("objection") or (entry.get("outcome") or {}).get("objection") or "").strip()
    ]
    opt_outs = [entry for entry in contacted if _truthy(entry.get("opt_out")) or _reply_status(entry) == "opted_out"]
    bounces = [entry for entry in contacted if _truthy(entry.get("bounce")) or _reply_status(entry) == "bounced"]
    no_replies = [entry for entry in contacted if _reply_status(entry) in {"", "no_reply", "not_contacted"}]

    summary = {
        "lead_count": len(entries),
        "contacted_count": len(contacted),
        "response_count": len(responses),
        "response_rate": _rate(len(responses), len(contacted)),
        "positive_reply_count": len(positives),
        "positive_reply_rate": _rate(len(positives), len(contacted)),
        "no_reply_count": len(no_replies),
        "objection_count": len(objections),
        "opt_out_count": len(opt_outs),
        "bounce_count": len(bounces),
        "operator_minutes_total": sum(_operator_minutes(entry) for entry in contacted),
        "operator_minutes_average": _rate(sum(_operator_minutes(entry) for entry in contacted), len(contacted)),
    }

    review = {
        "reviewed_at": reviewed_at or utc_now(),
        "notes": notes,
        "summary": summary,
        "positive_replies": [_brief_entry(entry) for entry in positives],
        "objections": objections,
        "opt_outs": [_brief_entry(entry) for entry in opt_outs],
        "bounces": [_brief_entry(entry) for entry in bounces],
        "channel_performance": _group_performance(contacted, key="selected_channel"),
        "package_fit": _package_fit_summary(contacted, objections=objections, positive_count=len(positives)),
        "proof_asset_performance": _group_performance(contacted, key="proof_asset", fallback="customer_safe_proof_item_only"),
        "iteration_decisions": _iteration_decisions(
            summary=summary,
            objections=objections,
            overrides=iteration_decisions,
        ),
        "batch_2_gate": {
            "phase_12_review_recorded": True,
            "next_phase": "Phase 13 may select Batch 2 only after this saved review, using approved email/contact-form routes.",
        },
    }
    return review


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
    proof_asset = (lead.get("outreach_assets_selected") or [""])[0]
    if not proof_asset:
        proof_asset = str(lead.get("hosted_menu_sample_url") or lead.get("sample_menu_url") or "")
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
        "proof_asset": proof_asset,
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
    if not proof_asset:
        proof_asset = str(lead.get("hosted_menu_sample_url") or lead.get("sample_menu_url") or "")
    proof_items = lead.get("proof_items") or (lead.get("lead_evidence_dossier") or {}).get("proof_items") or []
    if not proof_asset and not any(item.get("customer_preview_eligible") for item in proof_items):
        missing.append("proof_asset")
    if not str(lead.get("recommended_primary_package") or "").strip():
        missing.append("recommended_package")
    return missing


def _batch_path(state_root: Path, batch_id: str) -> Path:
    return state_root / "launch_batches" / f"{batch_id}.json"


def _was_contacted(entry: dict[str, Any]) -> bool:
    return bool(str(entry.get("contacted_at") or "").strip()) or _reply_status(entry) not in {"", "not_contacted"}


def _has_owner_response(entry: dict[str, Any]) -> bool:
    status = _reply_status(entry)
    return status not in NON_RESPONSE_REPLY_STATUSES


def _is_positive_reply(entry: dict[str, Any]) -> bool:
    status = _reply_status(entry)
    outcome = str((entry.get("outcome") or {}).get("outcome") or "").strip().lower()
    return status in POSITIVE_REPLY_STATUSES or outcome in POSITIVE_REPLY_STATUSES


def _reply_status(entry: dict[str, Any]) -> str:
    return str(entry.get("reply_status") or (entry.get("outcome") or {}).get("reply_status") or "").strip().lower()


def _operator_minutes(entry: dict[str, Any]) -> int:
    try:
        return max(0, int(entry.get("operator_minutes") or (entry.get("outcome") or {}).get("operator_minutes") or 0))
    except (TypeError, ValueError):
        return 0


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _brief_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "lead_id": entry.get("lead_id"),
        "business_name": entry.get("business_name"),
        "selected_channel": entry.get("selected_channel", ""),
        "reply_status": _reply_status(entry),
        "recommended_package": entry.get("recommended_package", ""),
    }


def _group_performance(
    entries: list[dict[str, Any]],
    *,
    key: str,
    fallback: str = "unknown",
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        group_key = str(entry.get(key) or "").strip() or fallback
        grouped.setdefault(group_key, []).append(entry)

    performance: dict[str, Any] = {}
    for group_key, group_entries in sorted(grouped.items()):
        responses = [entry for entry in group_entries if _has_owner_response(entry)]
        positives = [entry for entry in responses if _is_positive_reply(entry)]
        performance[group_key] = {
            "contacted_count": len(group_entries),
            "response_count": len(responses),
            "response_rate": _rate(len(responses), len(group_entries)),
            "positive_reply_count": len(positives),
            "positive_reply_rate": _rate(len(positives), len(group_entries)),
            "no_reply_count": sum(1 for entry in group_entries if _reply_status(entry) in {"", "no_reply", "not_contacted"}),
            "opt_out_count": sum(1 for entry in group_entries if _truthy(entry.get("opt_out")) or _reply_status(entry) == "opted_out"),
            "bounce_count": sum(1 for entry in group_entries if _truthy(entry.get("bounce")) or _reply_status(entry) == "bounced"),
            "operator_minutes_total": sum(_operator_minutes(entry) for entry in group_entries),
        }
    return performance


def _package_fit_summary(
    entries: list[dict[str, Any]],
    *,
    objections: list[dict[str, Any]],
    positive_count: int,
) -> dict[str, Any]:
    recommendations: dict[str, Any] = {}
    for package_key, group in _group_entries(entries, key="recommended_package", fallback="unknown").items():
        recommendations[package_key] = {
            "contacted_count": len(group),
            "positive_reply_count": sum(1 for entry in group if _is_positive_reply(entry)),
            "objection_count": sum(1 for entry in group if str(entry.get("objection") or "").strip()),
        }

    if positive_count or objections:
        assessment = "Observed replies exist; inspect objections and positive package requests before changing recommendation rules."
    else:
        assessment = "No replies or package-fit objections observed yet; recommendation rules remain unchanged."

    return {
        "recommendations": recommendations,
        "observed_package_mismatch_count": 0,
        "assessment": assessment,
    }


def _group_entries(
    entries: list[dict[str, Any]],
    *,
    key: str,
    fallback: str,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        group_key = str(entry.get(key) or "").strip() or fallback
        grouped.setdefault(group_key, []).append(entry)
    return grouped


def _iteration_decisions(
    *,
    summary: dict[str, Any],
    objections: list[dict[str, Any]],
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    if summary["positive_reply_count"] or summary["opt_out_count"] or summary["bounce_count"] or objections:
        default_reason = "Observed outcomes require operator review before changing launch rules."
    else:
        default_reason = "No positive replies, objections, opt-outs, or bounces were observed."

    decisions: dict[str, Any] = {
        "scoring_update": {
            "action": "no_change",
            "reason": default_reason,
        },
        "search_terms_update": {
            "action": "no_change",
            "reason": "All contacted leads remain waiting or uninformative; lead-quality evidence is insufficient to adjust search terms.",
        },
        "outreach_wording_update": {
            "action": "no_change",
            "reason": "No reply or objection identified a wording problem.",
        },
        "package_recommendation_update": {
            "action": "no_change",
            "reason": "No package-fit objection or conversion was observed.",
        },
    }
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(decisions.get(key), dict):
            decisions[key] = {**decisions[key], **value}
        else:
            decisions[key] = value
    return decisions


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
