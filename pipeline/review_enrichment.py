from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .pitch_cards import OPENABLE_PITCH_CARD_STATUSES
from .record import get_primary_contact, list_leads
from .review_batches import FORBIDDEN_REVIEW_ACTIONS, REQUIRED_REVIEW_STATE
from .utils import ensure_dir, slugify, utc_now, write_json, write_text


ALLOWED_ENRICHMENT_OUTCOMES = ("hold", "needs_more_info", "reject")
DEFAULT_ENRICHMENT_BATCH_SIZE = 80


def build_needs_more_info_enrichment_plan(*, state_root: Path, batch_size: int = DEFAULT_ENRICHMENT_BATCH_SIZE) -> dict[str, Any]:
    """Build a no-send follow-up plan for cards already marked needs_more_info."""
    records = list_leads(state_root=state_root)
    openable = [
        record
        for record in records
        if str(record.get("pitch_card_status") or "") in OPENABLE_PITCH_CARD_STATUSES
    ]
    needs_more_info = [
        record
        for record in openable
        if str(record.get("operator_review_outcome") or "") == "needs_more_info"
    ]
    entries = [_enrichment_entry(record) for record in sorted(needs_more_info, key=_enrichment_sort_key)]
    effective_batch_size = max(1, int(batch_size))
    batches = [
        _enrichment_batch(
            batch_index=index + 1,
            entries=entries[offset : offset + effective_batch_size],
        )
        for index, offset in enumerate(range(0, len(entries), effective_batch_size))
    ]

    return {
        "generated_at": utc_now(),
        "scope": "no_send_needs_more_info_enrichment",
        "batch_size": effective_batch_size,
        "no_send_safety": _safety_summary(records),
        "counts": {
            "records": len(records),
            "openable_pitch_cards": len(openable),
            "needs_more_info_cards": len(needs_more_info),
            "batch_count": len(batches),
            "operator_pack_count": sum(batch["operator_pack_count"] for batch in batches),
            "enrichment_lane_counts": _entry_counter(entries, "enrichment_lane"),
            "profile_counts": _entry_counter(entries, "establishment_profile"),
            "city_counts": _entry_counter(entries, "city"),
        },
        "allowed_enrichment_outcomes": list(ALLOWED_ENRICHMENT_OUTCOMES),
        "forbidden_actions": list(FORBIDDEN_REVIEW_ACTIONS),
        "required_state": dict(REQUIRED_REVIEW_STATE),
        "batches": batches,
        "next_actions": [
            "Work enrichment batches without sending email or submitting forms.",
            "Use saved evidence and reference-only route checks to decide hold, needs_more_info, or reject.",
            "Regenerate this artifact after enrichment outcomes change.",
        ],
    }


def write_needs_more_info_enrichment_plan(
    *,
    state_root: Path,
    output_dir: Path | None = None,
    label: str = "needs-more-info-enrichment",
    batch_size: int = DEFAULT_ENRICHMENT_BATCH_SIZE,
) -> dict[str, Any]:
    plan = build_needs_more_info_enrichment_plan(state_root=state_root, batch_size=batch_size)
    output_dir = output_dir or state_root / "review_batches"
    ensure_dir(output_dir)
    stamp = plan["generated_at"].replace(":", "").replace("-", "").split("+")[0]
    base = output_dir / f"{slugify(label)}-{stamp}Z"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    write_json(json_path, plan)
    write_text(md_path, _enrichment_markdown(plan))
    plan["artifact_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    write_json(json_path, plan)
    return plan


def _enrichment_entry(record: dict[str, Any]) -> dict[str, Any]:
    primary = get_primary_contact(record) or {}
    lane = _enrichment_lane(record, primary)
    return {
        "lead_id": str(record.get("lead_id") or ""),
        "business_name": str(record.get("business_name") or ""),
        "city": str(record.get("city") or ""),
        "primary_category": str(record.get("primary_category_v1") or record.get("type_of_restaurant") or "unknown"),
        "establishment_profile": str(record.get("establishment_profile_override") or record.get("establishment_profile") or "unknown"),
        "pitch_card_status": str(record.get("pitch_card_status") or ""),
        "primary_route_type": str(primary.get("type") or "none"),
        "enrichment_lane": lane,
        "operator_review_note": str(record.get("operator_review_note") or ""),
        "evidence_tasks": _evidence_tasks(record, lane),
        "allowed_outcomes": list(ALLOWED_ENRICHMENT_OUTCOMES),
        "forbidden_actions": list(FORBIDDEN_REVIEW_ACTIONS),
    }


def _enrichment_lane(record: dict[str, Any], primary: dict[str, Any]) -> str:
    pitch_status = str(record.get("pitch_card_status") or "")
    route_type = str(primary.get("type") or "")
    if route_type == "contact_form":
        return "contact_form_route_enrichment"
    if pitch_status == "needs_email_review":
        return "email_owner_route_enrichment"
    if pitch_status == "needs_name_review":
        return "name_source_enrichment"
    if pitch_status == "needs_scope_review":
        return "scope_evidence_enrichment"
    return "final_quality_enrichment"


def _evidence_tasks(record: dict[str, Any], lane: str) -> list[str]:
    tasks = {
        "email_owner_route_enrichment": [
            "Confirm saved email belongs to the restaurant/operator, not a directory, hotel, reviewer, or generic scraped artifact.",
            "If owner-route evidence is still weak, keep needs_more_info; if clearly invalid, reject.",
        ],
        "contact_form_route_enrichment": [
            "Inspect the saved form route only; do not submit and do not attach assets.",
            "Confirm it is a business contact route, not reservations-only, recruiting-only, social login, or phone-only.",
        ],
        "name_source_enrichment": [
            "Confirm the saved business name from two reliable source signals.",
            "Reject names that are directory titles, article titles, reviewer handles, contact labels, or extraction artifacts.",
        ],
        "scope_evidence_enrichment": [
            "Confirm Japan location and ramen/izakaya scope from saved evidence.",
            "Reject non-scope restaurants, chains, non-Japan locations, or already-solved English/QR ordering cases.",
        ],
        "final_quality_enrichment": [
            "Confirm evidence is consistent enough for future manual review while keeping the record blocked.",
        ],
    }
    result = list(tasks.get(lane, tasks["final_quality_enrichment"]))
    if not record.get("proof_items") and not (record.get("lead_evidence_dossier") or {}).get("proof_items"):
        result.append("Add or confirm a customer-safe proof item before any future promotion preview.")
    return result


def _enrichment_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    lane_order = {
        "needs_email_review": 0,
        "needs_name_review": 1,
        "needs_scope_review": 2,
        "reviewable": 3,
    }
    return (
        lane_order.get(str(record.get("pitch_card_status") or ""), 99),
        str(record.get("city") or ""),
        str(record.get("establishment_profile") or ""),
        str(record.get("business_name") or ""),
        str(record.get("lead_id") or ""),
    )


def _enrichment_batch(*, batch_index: int, entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "batch_id": f"needs-more-info-{batch_index:02d}",
        "batch_index": batch_index,
        "card_count": len(entries),
        "operator_pack_count": len(_operator_packs(entries, batch_index=batch_index)),
        "enrichment_lane_counts": _entry_counter(entries, "enrichment_lane"),
        "profile_counts": _entry_counter(entries, "establishment_profile"),
        "operator_packs": _operator_packs(entries, batch_index=batch_index),
        "queue": entries,
    }


def _operator_packs(entries: list[dict[str, Any]], *, batch_index: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        grouped[str(entry["enrichment_lane"])].append(entry)
    packs: list[dict[str, Any]] = []
    for lane, lane_entries in sorted(grouped.items()):
        packs.append({
            "pack_id": f"batch-{batch_index:02d}-{lane}",
            "enrichment_lane": lane,
            "card_count": len(lane_entries),
            "allowed_outcomes": list(ALLOWED_ENRICHMENT_OUTCOMES),
            "forbidden_actions": list(FORBIDDEN_REVIEW_ACTIONS),
            "lead_ids": [entry["lead_id"] for entry in lane_entries],
        })
    return packs


def _safety_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "real_outbound_allowed": False,
        "contact_form_submit_allowed": False,
        "email_send_allowed": False,
        "launch_readiness_status_counts": _counter(records, lambda record: str(record.get("launch_readiness_status") or "unknown")),
        "outreach_status_counts": _counter(records, lambda record: str(record.get("outreach_status") or "unknown")),
        "ready_for_outreach": sum(1 for record in records if record.get("launch_readiness_status") == "ready_for_outreach"),
        "pitch_ready": sum(1 for record in records if record.get("pitch_ready") is True),
        "outreach_status_new": sum(1 for record in records if record.get("outreach_status") == "new"),
    }


def _entry_counter(entries: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(str(entry.get(field) or "unknown") for entry in entries).items()))


def _counter(records: list[dict[str, Any]], key_fn: Any) -> dict[str, int]:
    return dict(sorted(Counter(str(key_fn(record) or "unknown") for record in records).items()))


def _enrichment_markdown(plan: dict[str, Any]) -> str:
    counts = plan["counts"]
    lines = [
        "# Needs-More-Info Enrichment Plan",
        "",
        f"Generated: `{plan['generated_at']}`",
        "",
        "## No-Send Safety",
        "",
        f"- Real outbound allowed: `{str(plan['no_send_safety']['real_outbound_allowed']).lower()}`",
        f"- Contact-form submit allowed: `{str(plan['no_send_safety']['contact_form_submit_allowed']).lower()}`",
        f"- Email send allowed: `{str(plan['no_send_safety']['email_send_allowed']).lower()}`",
        f"- Ready for outreach: `{plan['no_send_safety']['ready_for_outreach']}`",
        f"- Pitch ready: `{plan['no_send_safety']['pitch_ready']}`",
        f"- Outreach status new: `{plan['no_send_safety']['outreach_status_new']}`",
        "",
        "## Counts",
        "",
        f"- Openable pitch cards: `{counts['openable_pitch_cards']}`",
        f"- Needs-more-info cards: `{counts['needs_more_info_cards']}`",
        f"- Enrichment batches: `{counts['batch_count']}`",
        f"- Operator packs: `{counts['operator_pack_count']}`",
        f"- Lane counts: `{counts['enrichment_lane_counts']}`",
        "",
        "## Batches",
        "",
    ]
    for batch in plan["batches"]:
        lines.extend([
            f"### {batch['batch_id']}",
            "",
            f"- Cards: `{batch['card_count']}`",
            f"- Lanes: `{batch['enrichment_lane_counts']}`",
            f"- Profiles: `{batch['profile_counts']}`",
            "",
        ])
        for pack in batch["operator_packs"]:
            lines.append(
                f"- `{pack['pack_id']}`: `{pack['card_count']}` cards, lane `{pack['enrichment_lane']}`"
            )
        lines.append("")
    lines.extend([
        "## Allowed Outcomes",
        "",
        ", ".join(f"`{item}`" for item in plan["allowed_enrichment_outcomes"]),
        "",
        "## Forbidden Actions",
        "",
        ", ".join(f"`{item}`" for item in plan["forbidden_actions"]),
        "",
    ])
    return "\n".join(lines)
