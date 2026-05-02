from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .constants import OUTREACH_SAMPLE_BY_ESTABLISHMENT_PROFILE
from .record import list_leads
from .review_batches import (
    ALLOWED_REVIEW_OUTCOMES,
    FORBIDDEN_REVIEW_ACTIONS,
    PROFILE_ASSET_GUIDANCE,
    PROFILE_LABELS,
    REQUIRED_REVIEW_STATE,
    build_no_send_review_wave,
)
from .utils import ensure_dir, slugify, utc_now, write_json, write_text


GLM_PRIORITY_PROFILES = (
    "izakaya_yakitori_kushiyaki",
    "izakaya_kushiage",
    "izakaya_seafood_sake_oden",
    "izakaya_tachinomi",
    "izakaya_robatayaki",
)
GLM_INITIAL_THRESHOLD = 5
GLM_HIGH_PRIORITY_THRESHOLD = 10


def build_restaurant_execution_plan(
    *,
    state_root: Path,
    batch_size: int = 120,
    representative_count: int = 5,
) -> dict[str, Any]:
    """Build the no-send completion artifact for the restaurant lead plan.

    This intentionally does not promote leads, set pitch_ready, create launch
    batches, send e-mail, or submit contact forms.
    """
    records = list_leads(state_root=state_root)
    wave = build_no_send_review_wave(state_root=state_root, batch_size=batch_size)
    queue = _flatten_wave_queue(wave)
    safety = wave["no_send_safety"]
    return {
        "generated_at": utc_now(),
        "scope": "restaurant_lead_execution_plan_no_send_completion",
        "finished_until_external_gate": True,
        "external_gates": [
            "operator_review_outcomes_required",
            "explicit_current_chat_outbound_request_required_before_any_send",
        ],
        "no_send_safety": safety,
        "required_review_state": dict(REQUIRED_REVIEW_STATE),
        "allowed_operator_outcomes": list(ALLOWED_REVIEW_OUTCOMES),
        "forbidden_actions": list(FORBIDDEN_REVIEW_ACTIONS),
        "phase_status": _phase_status(wave),
        "queue": {
            "records": len(records),
            "openable_pitch_cards": wave["counts"]["openable_pitch_cards"],
            "approved_route_review_cards": wave["counts"]["approved_route_review_cards"],
            "review_batch_count": wave["counts"]["batch_count"],
            "operator_pack_count": wave["counts"]["operator_pack_count"],
            "review_lane_counts": wave["counts"]["review_lane_counts"],
            "profile_counts": wave["counts"]["profile_counts"],
        },
        "review_wave": {
            "batch_size": wave["batch_size"],
            "batch_count": wave["counts"]["batch_count"],
            "operator_pack_count": wave["counts"]["operator_pack_count"],
            "batches": _wave_batch_summary(wave),
        },
        "glm_design_requests": _glm_design_requests(queue, representative_count=representative_count),
        "promotion_gate_preview": _promotion_gate_preview(queue),
        "inline_pitch_pack_plan": _inline_pitch_pack_plan(wave),
        "next_actions": [
            "Work review-wave batches in order and save only hold, needs_more_info, or reject outcomes.",
            "Keep locked asset routing and audit expectations aligned as review artifacts are regenerated.",
            "Regenerate this execution-plan artifact after operator review outcomes are saved.",
            "Do not send, submit forms, promote records, or set pitch_ready without a new explicit outbound instruction.",
        ],
    }


def write_restaurant_execution_plan(
    *,
    state_root: Path,
    output_dir: Path | None = None,
    label: str = "restaurant-lead-execution-plan",
    batch_size: int = 120,
    representative_count: int = 5,
) -> dict[str, Any]:
    plan = build_restaurant_execution_plan(
        state_root=state_root,
        batch_size=batch_size,
        representative_count=representative_count,
    )
    output_dir = output_dir or state_root / "execution_plans"
    ensure_dir(output_dir)
    stamp = plan["generated_at"].replace(":", "").replace("-", "").split("+")[0]
    base = output_dir / f"{slugify(label)}-{stamp}Z"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    write_json(json_path, plan)
    write_text(md_path, _execution_plan_markdown(plan))
    plan["artifact_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    write_json(json_path, plan)
    return plan


def _phase_status(wave: dict[str, Any]) -> list[dict[str, Any]]:
    safety = wave["no_send_safety"]
    clean_safety = (
        safety["ready_for_outreach"] == 0
        and safety["pitch_ready"] == 0
        and safety["outreach_status_new"] == 0
    )
    return [
        {
            "phase": "P1 Corpus Consolidation",
            "status": "complete",
            "evidence": "All current importable records are in the dashboard lead queue.",
        },
        {
            "phase": "P2 Verification System",
            "status": "complete_for_current_queue",
            "evidence": "Verification fields and pitch-card states are populated; unresolved cards remain manual review.",
        },
        {
            "phase": "P3 Dashboard Pill System",
            "status": "complete_for_no_send_review",
            "evidence": "Dashboard filters, lanes, route/profile filters, and no-send outcomes are available.",
        },
        {
            "phase": "P4 Promotion Workflow",
            "status": "blocked_by_current_safety_boundary",
            "evidence": "Promotion candidates are previewed only; live pitch_ready mutation is forbidden in this run.",
        },
        {
            "phase": "P5 GLM Locked Menu Assets",
            "status": "complete_for_current_profiles",
            "evidence": "Dedicated locked templates are available for all current specific izakaya profiles.",
        },
        {
            "phase": "P6 Inline Pitch Packs",
            "status": "planned_no_send_only",
            "evidence": "Locked asset routing is wired for review planning; draft generation remains blocked until review/promotion gates.",
        },
        {
            "phase": "P7 Outreach Readiness",
            "status": "not_started",
            "evidence": "Real outbound remains false; clean safety counters are required and currently clean." if clean_safety else "Safety counters are not clean.",
        },
    ]


def _flatten_wave_queue(wave: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for batch in wave.get("batches") or []:
        for entry in batch.get("review_queue") or []:
            copied = dict(entry)
            copied["review_batch_id"] = batch.get("batch_id")
            entries.append(copied)
    return entries


def _wave_batch_summary(wave: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "batch_id": batch["batch_id"],
            "card_count": batch["card_count"],
            "review_lane_counts": batch["review_lane_counts"],
            "profile_counts": batch["profile_counts"],
            "operator_pack_count": batch["review_throughput"]["operator_pack_count"],
        }
        for batch in wave.get("batches") or []
    ]


def _glm_design_requests(queue: list[dict[str, Any]], *, representative_count: int) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for profile, entries in sorted(_grouped(queue, "establishment_profile").items()):
        guidance = PROFILE_ASSET_GUIDANCE.get(profile, {})
        selected_count = len(entries)
        priority_index = GLM_PRIORITY_PROFILES.index(profile) if profile in GLM_PRIORITY_PROFILES else 99
        locked_asset = OUTREACH_SAMPLE_BY_ESTABLISHMENT_PROFILE.get(profile)
        request_ready = (
            locked_asset is None
            and selected_count >= GLM_INITIAL_THRESHOLD
            and profile in GLM_PRIORITY_PROFILES
        )
        high_priority = (
            locked_asset is None
            and selected_count >= GLM_HIGH_PRIORITY_THRESHOLD
            and profile in GLM_PRIORITY_PROFILES
        )
        requests.append({
            "profile_id": profile,
            "profile_label": PROFILE_LABELS.get(profile, profile.replace("_", " ").title()),
            "family": guidance.get("family", "manual_review"),
            "asset_profile": guidance.get("asset_profile", "manual_review"),
            "selected_cards": selected_count,
            "priority_rank": priority_index + 1 if priority_index < 99 else None,
            "request_status": (
                "locked_asset_available"
                if locked_asset is not None
                else "high_priority_request_ready"
                if high_priority
                else "initial_request_ready"
                if request_ready
                else "covered_or_monitor"
            ),
            "request_glm_now": request_ready,
            "menu_structure_requirements": guidance.get("brief", "Confirm scope and route quality before assigning locked GLM assets."),
            "existing_design_constraint": "GLM locked templates only; Codex may route returned assets but must not edit locked design content.",
            "required_outputs": [
                f"locked asset available: `{locked_asset}`" if locked_asset is not None else f"locked menu design for `{profile}`",
                f"profile mapping for `{profile}`",
                "seedstyle-compatible source asset" if locked_asset is None else "Codex routing and audit expectations stay aligned",
            ],
            "representative_examples": _representative_examples(entries, limit=representative_count),
        })
    return sorted(
        requests,
        key=lambda item: (
            item["priority_rank"] is None,
            item["priority_rank"] or 999,
            -int(item["selected_cards"]),
            str(item["profile_id"]),
        ),
    )


def _representative_examples(entries: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for entry in entries[: max(0, limit)]:
        examples.append({
            "lead_id": entry.get("lead_id"),
            "business_name": entry.get("business_name"),
            "city": entry.get("city"),
            "review_batch_id": entry.get("review_batch_id"),
            "review_lane": entry.get("review_lane"),
            "quality_tier": entry.get("quality_tier"),
            "source_strength": entry.get("source_strength"),
            "primary_route_type": entry.get("primary_route_type"),
        })
    return examples


def _promotion_gate_preview(queue: list[dict[str, Any]]) -> dict[str, Any]:
    blocker_counts: Counter[str] = Counter()
    cards: list[dict[str, Any]] = []
    for entry in queue:
        blockers = ["current_chat_forbids_promotion", "operator_review_outcome_missing"]
        review_lane = str(entry.get("review_lane") or "")
        if review_lane == "email_route_review":
            blockers.append("email_review_required")
        elif review_lane == "name_review":
            blockers.append("name_review_required")
        elif review_lane == "scope_review":
            blockers.append("scope_review_required")
        elif review_lane == "contact_form_review":
            blockers.append("contact_form_route_review_required")
        for blocker in blockers:
            blocker_counts[blocker] += 1
        cards.append({
            "lead_id": entry.get("lead_id"),
            "review_batch_id": entry.get("review_batch_id"),
            "review_lane": review_lane,
            "establishment_profile": entry.get("establishment_profile"),
            "blocked_by": blockers,
        })
    return {
        "live_promotion_allowed": False,
        "pitch_ready_mutation_allowed": False,
        "ready_for_outreach_mutation_allowed": False,
        "candidate_count": len(queue),
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "required_post_review_state": dict(REQUIRED_REVIEW_STATE),
        "candidate_cards": cards,
    }


def _inline_pitch_pack_plan(wave: dict[str, Any]) -> dict[str, Any]:
    pitch_plan = wave["pitch_pack_plan"]
    return {
        "draft_generation_allowed": False,
        "reason": "Inline pitch packs require operator-reviewed and promoted records; this run is no-send/no-promotion.",
        "planned_cards": pitch_plan["selected_cards"],
        "stage": pitch_plan["stage"],
        "email_policy": pitch_plan["email_policy"],
        "contact_form_policy": pitch_plan["contact_form_policy"],
        "attachment_policy_counts": pitch_plan["attachment_policy_counts"],
        "glm_reference_asset_counts": pitch_plan["glm_reference_asset_counts"],
        "route_asset_counts": pitch_plan["route_asset_counts"],
        "strategy_counts": pitch_plan["strategy_counts"],
    }


def _grouped(entries: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        groups.setdefault(str(entry.get(key) or "unknown"), []).append(entry)
    return groups


def _execution_plan_markdown(plan: dict[str, Any]) -> str:
    queue = plan["queue"]
    safety = plan["no_send_safety"]
    lines = [
        "# Restaurant Lead Execution Plan Completion",
        "",
        f"Generated: {plan['generated_at']}",
        "",
        "Real outbound allowed: `false`.",
        "Promotion, pitch_ready mutation, e-mail sending, and contact-form submission are blocked.",
        "",
        "## Queue",
        "",
        f"- Records: `{queue['records']}`",
        f"- Openable pitch cards: `{queue['openable_pitch_cards']}`",
        f"- Approved-route review cards: `{queue['approved_route_review_cards']}`",
        f"- Review batches: `{queue['review_batch_count']}`",
        f"- Operator packs: `{queue['operator_pack_count']}`",
        f"- Ready for outreach: `{safety['ready_for_outreach']}`",
        f"- Pitch ready: `{safety['pitch_ready']}`",
        f"- Outreach status new: `{safety['outreach_status_new']}`",
        "",
        "## Phase Status",
        "",
    ]
    for phase in plan["phase_status"]:
        lines.append(f"- `{phase['phase']}`: `{phase['status']}`. {phase['evidence']}")
    lines.extend(["", "## GLM Requests", ""])
    for request in plan["glm_design_requests"]:
        lines.append(
            f"- `{request['profile_id']}`: `{request['selected_cards']}` cards, "
            f"`{request['request_status']}`. {request['menu_structure_requirements']}"
        )
        lines.append(f"  - Required outputs: {', '.join(request['required_outputs'])}")
        lines.append(f"  - Constraint: {request['existing_design_constraint']}")
        if request["representative_examples"]:
            lines.append("  - Representative examples:")
            for example in request["representative_examples"]:
                lines.append(
                    "    - "
                    f"`{example['lead_id']}` | {example['business_name']} | {example['city']} | "
                    f"`{example['review_lane']}` | `{example['quality_tier']}` | `{example['source_strength']}`"
                )
    lines.extend(["", "## Promotion Gate Preview", ""])
    gate = plan["promotion_gate_preview"]
    lines.append(f"- Candidate cards: `{gate['candidate_count']}`")
    lines.append(f"- Live promotion allowed: `{str(gate['live_promotion_allowed']).lower()}`")
    for blocker, count in gate["blocker_counts"].items():
        lines.append(f"- `{blocker}`: `{count}`")
    lines.extend(["", "## Inline Pitch-Pack Plan", ""])
    pack = plan["inline_pitch_pack_plan"]
    lines.append(f"- Draft generation allowed: `{str(pack['draft_generation_allowed']).lower()}`")
    lines.append(f"- Planned cards: `{pack['planned_cards']}`")
    for path, count in pack["glm_reference_asset_counts"].items():
        lines.append(f"- `{path}`: `{count}` cards")
    lines.extend(["", "## Next Actions", ""])
    lines.extend(f"- {action}" for action in plan["next_actions"])
    lines.append("")
    return "\n".join(lines)
