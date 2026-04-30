from __future__ import annotations

from pathlib import Path
from typing import Any

from .launch import build_launch_batch_review, list_launch_batches
from .record import get_primary_contact, list_leads
from .utils import ensure_dir, read_json, utc_now, write_json, write_text


CONTACTED_OUTREACH_STATUSES = {"sent", "contacted_form", "replied", "converted"}
FIXTURE_TOKENS = ("qa-", "qa_", "smoke", "test-fixture")


def write_no_send_batch_decision_brief(
    *,
    state_root: Path,
    output_dir: Path | None = None,
    label: str = "batch3-no-send",
) -> dict[str, Any]:
    """Write a no-send decision brief for the next controlled launch step."""
    decision = build_no_send_batch_decision(state_root=state_root)
    output_dir = output_dir or state_root / "launch_decisions"
    ensure_dir(output_dir)
    stamp = utc_now().replace(":", "").replace("-", "").split("+")[0]
    base = output_dir / f"{label}-{stamp}Z"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    write_json(json_path, decision)
    write_text(md_path, _decision_markdown(decision))
    decision["artifact_paths"] = {
        "json": str(json_path),
        "markdown": str(md_path),
    }
    write_json(json_path, decision)
    return decision


def build_no_send_batch_decision(*, state_root: Path) -> dict[str, Any]:
    batches = list_launch_batches(state_root=state_root)
    launched_ids = {
        str(entry.get("lead_id") or "")
        for batch in batches
        for entry in batch.get("leads") or []
        if entry.get("lead_id")
    }
    batch_summaries = [_batch_summary(batch) for batch in batches]
    reply_matches = _reply_matches(state_root=state_root, launched_ids=launched_ids)
    candidates, exclusions = _candidate_pool(state_root=state_root, launched_ids=launched_ids)
    contacted_count = sum(int(item["summary"].get("contacted_count") or 0) for item in batch_summaries)
    response_count = sum(int(item["summary"].get("response_count") or 0) for item in batch_summaries)
    route_failures = _route_failure_count(batches)
    required_mix = {
        "ramen_ticket_machine": any(item["establishment_profile"] == "ramen_ticket_machine" for item in candidates),
        "izakaya_drink_or_course": any(
            item["establishment_profile"] in {"izakaya_drink_heavy", "izakaya_course_heavy"}
            for item in candidates
        ),
    }
    candidate_set_complete = len(candidates) >= 5 and all(required_mix.values())
    real_outbound_allowed = False
    if response_count > 0 and route_failures == 0 and candidate_set_complete:
        recommendation = "ready_for_human_review_only"
        reason = "A no-send candidate set exists, but real outbound still requires explicit operator approval."
    elif not candidate_set_complete:
        recommendation = "hold_real_outbound_prepare_more_candidates"
        reason = "No no-send Batch 3 set satisfies size and required ramen/izakaya profile mix."
    else:
        recommendation = "hold_real_outbound_wait_for_signal"
        reason = "Prior contacted leads have not produced enough owner-response signal to justify volume."

    return {
        "generated_at": utc_now(),
        "scope": "no_send_batch_3_decision_brief",
        "real_outbound_allowed": real_outbound_allowed,
        "real_outbound_requires_explicit_current_chat_request": True,
        "recommendation": recommendation,
        "reason": reason,
        "prior_batches": batch_summaries,
        "aggregate": {
            "batch_count": len(batches),
            "contacted_count": contacted_count,
            "response_count": response_count,
            "response_rate": round(response_count / contacted_count, 4) if contacted_count else 0.0,
            "route_failure_count": route_failures,
            "matched_reply_artifact_count": len(reply_matches),
        },
        "reply_reconciliation": {
            "checked_reply_files": _reply_file_count(state_root),
            "matched_replies": reply_matches,
        },
        "candidate_pool": {
            "eligible_count": len(candidates),
            "required_mix": required_mix,
            "candidate_set_complete": candidate_set_complete,
            "eligible_candidates": candidates,
            "excluded_count": len(exclusions),
            "exclusions": exclusions,
        },
        "next_no_send_actions": _next_no_send_actions(candidate_set_complete=candidate_set_complete),
    }


def _batch_summary(batch: dict[str, Any]) -> dict[str, Any]:
    review = batch.get("phase_12_review") or build_launch_batch_review(batch=batch)
    return {
        "batch_id": batch.get("batch_id"),
        "batch_number": batch.get("batch_number"),
        "reviewed_at": batch.get("reviewed_at"),
        "lead_count": batch.get("lead_count"),
        "summary": review.get("summary") or {},
        "iteration_decisions": review.get("iteration_decisions") or {},
    }


def _reply_matches(*, state_root: Path, launched_ids: set[str]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    replies_dir = state_root / "replies"
    if not replies_dir.exists():
        return matches
    for path in sorted(replies_dir.glob("*.json")):
        reply = read_json(path)
        lead_id = str((reply or {}).get("lead_id") or "")
        if lead_id in launched_ids:
            matches.append({
                "path": str(path),
                "lead_id": lead_id,
                "received_at": reply.get("received_at"),
                "reply_status": reply.get("reply_status"),
                "classification": reply.get("classification"),
            })
    return matches


def _reply_file_count(state_root: Path) -> int:
    replies_dir = state_root / "replies"
    return len(list(replies_dir.glob("*.json"))) if replies_dir.exists() else 0


def _candidate_pool(*, state_root: Path, launched_ids: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for lead in list_leads(state_root):
        lead_id = str(lead.get("lead_id") or "")
        reasons = _candidate_exclusion_reasons(lead, launched_ids=launched_ids)
        if reasons:
            if _include_exclusion(lead, reasons):
                exclusions.append({
                    "lead_id": lead_id,
                    "business_name": lead.get("business_name"),
                    "reasons": reasons,
                    "launch_readiness_status": lead.get("launch_readiness_status"),
                    "outreach_status": lead.get("outreach_status"),
                })
            continue
        primary = get_primary_contact(lead) or {}
        candidates.append({
            "lead_id": lead_id,
            "business_name": lead.get("business_name"),
            "establishment_profile": lead.get("establishment_profile"),
            "selected_channel": primary.get("type"),
            "recommended_package": lead.get("recommended_primary_package"),
            "message_variant": lead.get("message_variant"),
            "proof_asset": (lead.get("outreach_assets_selected") or [""])[0],
        })
    return candidates, exclusions


def _candidate_exclusion_reasons(lead: dict[str, Any], *, launched_ids: set[str]) -> list[str]:
    lead_id = str(lead.get("lead_id") or "")
    reasons: list[str] = []
    if lead_id in launched_ids or str(lead.get("launch_batch_id") or ""):
        reasons.append("already_in_launch_batch")
    if _is_fixture_lead(lead):
        reasons.append("fixture_or_smoke_lead")
    if str(lead.get("outreach_status") or "") in CONTACTED_OUTREACH_STATUSES:
        reasons.append("already_contacted")
    if str(lead.get("outreach_status") or "") in {"needs_review", "manual_review"}:
        reasons.append("operator_review_required")
    if lead.get("launch_readiness_status") != "ready_for_outreach":
        reasons.append("not_ready_for_outreach")
    primary = get_primary_contact(lead) or {}
    if str(primary.get("type") or "") not in {"email", "contact_form"}:
        reasons.append("no_supported_contact_route")
    return sorted(set(reasons))


def _is_fixture_lead(lead: dict[str, Any]) -> bool:
    if lead.get("smoke_rehearsal_only") or lead.get("production_sim_fixture"):
        return True
    text = " ".join([
        str(lead.get("lead_id") or ""),
        str(lead.get("business_name") or ""),
        str(lead.get("source_query") or ""),
    ]).lower()
    return any(token in text for token in FIXTURE_TOKENS)


def _include_exclusion(lead: dict[str, Any], reasons: list[str]) -> bool:
    if "already_in_launch_batch" in reasons and "not_ready_for_outreach" not in reasons:
        return False
    if "fixture_or_smoke_lead" in reasons:
        return True
    if "operator_review_required" in reasons:
        return True
    if "no_supported_contact_route" in reasons and lead.get("launch_readiness_status") == "ready_for_outreach":
        return True
    return False


def _route_failure_count(batches: list[dict[str, Any]]) -> int:
    count = 0
    for batch in batches:
        for entry in batch.get("leads") or []:
            outcome = entry.get("outcome") or {}
            text = " ".join([
                str(entry.get("reply_status") or ""),
                str(outcome.get("outcome") or ""),
                str(outcome.get("notes") or ""),
            ]).lower()
            if "failed" in text or "phone required" in text or "not_contacted" in text and "contact_form" in text:
                count += 1
    return count


def _next_no_send_actions(*, candidate_set_complete: bool) -> list[str]:
    if candidate_set_complete:
        return [
            "Prepare human review packet for the no-send candidate set.",
            "Before any real contact, re-check Batch 1/2 replies, bounces, opt-outs, and objections.",
            "Do not send or submit forms without an explicit current-chat outbound instruction.",
        ]
    return [
        "Generate or materialize more email/contact-form-supported live candidates without contacting them.",
        "Exclude route-only, social-only, reservation-only, phone-required, and fixture leads before any Batch 3 review.",
        "Rerun launch smoke only after at least five eligible real candidates satisfy the ramen/izakaya mix.",
    ]


def _decision_markdown(decision: dict[str, Any]) -> str:
    aggregate = decision["aggregate"]
    pool = decision["candidate_pool"]
    lines = [
        "# Batch 3 No-Send Decision Brief",
        "",
        f"Generated: {decision['generated_at']}",
        "",
        f"Recommendation: `{decision['recommendation']}`",
        "",
        decision["reason"],
        "",
        "Real outbound allowed: `false`.",
        "Real email or contact-form submission still requires an explicit current-chat outbound request.",
        "",
        "## Prior Batch Signal",
        "",
        f"- Batches reviewed: `{aggregate['batch_count']}`",
        f"- Contacted leads: `{aggregate['contacted_count']}`",
        f"- Owner responses: `{aggregate['response_count']}`",
        f"- Response rate: `{aggregate['response_rate']}`",
        f"- Route failures: `{aggregate['route_failure_count']}`",
        f"- Matched reply artifacts: `{aggregate['matched_reply_artifact_count']}`",
        "",
        "## Candidate Pool",
        "",
        f"- Eligible candidates: `{pool['eligible_count']}`",
        f"- Candidate set complete: `{str(pool['candidate_set_complete']).lower()}`",
        f"- Ramen ticket-machine mix: `{str(pool['required_mix']['ramen_ticket_machine']).lower()}`",
        f"- Izakaya drink/course mix: `{str(pool['required_mix']['izakaya_drink_or_course']).lower()}`",
        "",
        "## Next No-Send Actions",
        "",
    ]
    lines.extend(f"- {action}" for action in decision["next_no_send_actions"])
    return "\n".join(lines) + "\n"
