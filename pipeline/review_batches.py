from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .outreach import describe_outreach_assets, select_outreach_assets
from .pitch_cards import OPENABLE_PITCH_CARD_STATUSES, pitch_card_counts
from .record import get_primary_contact, list_leads
from .utils import ensure_dir, slugify, utc_now, write_json, write_text


APPROVED_REVIEW_ROUTE_TYPES = {"email", "contact_form"}
REFERENCE_ONLY_ROUTE_TYPES = {"phone", "line", "instagram", "reservation", "map_url", "walk_in", "website"}
ALLOWED_REVIEW_OUTCOMES = ("hold", "needs_more_info", "pitch_pack_ready", "reject")
FORBIDDEN_REVIEW_ACTIONS = (
    "send_email",
    "submit_contact_form",
    "promote_record",
    "set_pitch_ready",
    "set_ready_for_outreach",
)
REQUIRED_REVIEW_STATE = {
    "launch_readiness_status": "manual_review",
    "outreach_status": "needs_review",
    "pitch_ready": False,
}
DEFAULT_OPERATOR_PACK_SIZE = 30

PITCH_CARD_REVIEW_ORDER = {
    "needs_email_review": 0,
    "reviewable": 1,
    "needs_name_review": 2,
    "needs_scope_review": 3,
}

QUALITY_ORDER = {"v1_clean": 0, "high": 1, "medium": 2, "low": 3}
CITY_ORDER = {"Tokyo": 0, "Osaka": 1, "Sapporo": 2, "Fukuoka": 3, "Kyoto": 4}

PROFILE_LABELS = {
    "ramen_ticket_machine": "Ramen Ticket Machine",
    "ramen_only": "Ramen Menu Translation",
    "ramen_with_drinks": "Ramen With Drinks",
    "ramen_with_sides_add_ons": "Ramen With Sides / Add-ons",
    "izakaya_food_and_drinks": "Izakaya Food And Drinks",
    "izakaya_drink_heavy": "Izakaya Drinks / Courses",
    "izakaya_course_heavy": "Izakaya Courses",
    "izakaya_yakitori_kushiyaki": "Yakitori / Kushiyaki",
    "izakaya_kushiage": "Kushikatsu / Kushiage",
    "izakaya_seafood_sake_oden": "Seafood / Sake / Oden",
    "izakaya_tachinomi": "Tachinomi",
    "izakaya_robatayaki": "Robatayaki",
}

PROFILE_ASSET_GUIDANCE = {
    "ramen_ticket_machine": {
        "family": "ramen",
        "asset_profile": "ramen_food_menu + ticket_machine_guide",
        "brief": "Prioritize compact item names, topping clarity, and a ticket-machine ordering explainer.",
    },
    "ramen_only": {
        "family": "ramen",
        "asset_profile": "ramen_food_menu",
        "brief": "Prioritize one-page ramen translation with soup, noodle, topping, and set-menu sections.",
    },
    "ramen_with_drinks": {
        "family": "ramen",
        "asset_profile": "ramen_food_menu + ramen_drinks_menu",
        "brief": "Prioritize ramen item clarity with a small drink section for beer, highball, and pairings.",
    },
    "ramen_with_sides_add_ons": {
        "family": "ramen",
        "asset_profile": "ramen_food_menu",
        "brief": "Prioritize ramen, toppings, side dishes, add-ons, and set combinations on one compact page.",
    },
    "izakaya_food_and_drinks": {
        "family": "izakaya",
        "asset_profile": "izakaya_food_menu + izakaya_drinks_menu",
        "brief": "Prioritize food and drink pairing clarity, house recommendations, and group-order scanning.",
    },
    "izakaya_drink_heavy": {
        "family": "izakaya",
        "asset_profile": "izakaya_drinks_menu",
        "brief": "Prioritize drink categories, all-you-can-drink rules, and concise pairing notes.",
    },
    "izakaya_course_heavy": {
        "family": "izakaya",
        "asset_profile": "izakaya_food_drinks_menu",
        "brief": "Prioritize course structure, reservation notes, drink-plan options, and per-person pricing clarity.",
    },
    "izakaya_yakitori_kushiyaki": {
        "family": "izakaya",
        "asset_profile": "izakaya_yakitori_kushiyaki_menu",
        "brief": "Prioritize skewer cuts, sauce/salt options, set platters, and drink pairing sections.",
    },
    "izakaya_kushiage": {
        "family": "izakaya",
        "asset_profile": "izakaya_kushiage_menu",
        "brief": "Prioritize fried skewer categories, dipping rules, set counts, and allergen-friendly labels.",
    },
    "izakaya_seafood_sake_oden": {
        "family": "izakaya",
        "asset_profile": "izakaya_seafood_sake_oden_menu",
        "brief": "Prioritize seasonal seafood, sake/shochu pairing, oden items, and freshness notes.",
    },
    "izakaya_tachinomi": {
        "family": "izakaya",
        "asset_profile": "izakaya_tachinomi_menu",
        "brief": "Prioritize fast scanning, small plates, drink rounds, and standing-bar ordering cues.",
    },
    "izakaya_robatayaki": {
        "family": "izakaya",
        "asset_profile": "izakaya_robatayaki_menu",
        "brief": "Prioritize grill categories, ingredient display, doneness notes, and shared-plate ordering.",
    },
}


def build_no_send_review_batch(*, state_root: Path, batch_size: int = 120) -> dict[str, Any]:
    """Build a no-send pitch-card review batch without mutating lead state."""
    records = list_leads(state_root=state_root)
    openable_records = [
        record
        for record in records
        if str(record.get("pitch_card_status") or "") in OPENABLE_PITCH_CARD_STATUSES
    ]
    unreviewed_records = [
        record
        for record in openable_records
        if not str(record.get("operator_review_outcome") or "").strip()
    ]
    queue = [_review_queue_entry(record) for record in sorted(unreviewed_records, key=_review_sort_key)]
    queue = [entry for entry in queue if entry["primary_route_type"] in APPROVED_REVIEW_ROUTE_TYPES][: max(0, batch_size)]
    operator_packs = _operator_review_packs(queue)

    return {
        "generated_at": utc_now(),
        "scope": "no_send_pitch_card_review_batch",
        "batch_size": batch_size,
        "no_send_safety": _safety_summary(records),
        "counts": {
            "records": len(records),
            "openable_pitch_cards": len(openable_records),
            "unreviewed_openable_pitch_cards": len(unreviewed_records),
            "selected_review_queue": len(queue),
            "pitch_card_counts": pitch_card_counts(records),
            "route_counts": _counter(records, _primary_route_type),
            "approved_review_route_counts": _counter(openable_records, _primary_route_type, allowed=APPROVED_REVIEW_ROUTE_TYPES),
            "review_outcome_counts": _review_outcome_counts(openable_records),
            "review_lane_counts": _counter(openable_records, _review_lane),
            "city_counts": _counter(openable_records, lambda record: str(record.get("city") or "unknown")),
            "category_counts": _nested_counter(openable_records, _primary_category, _menu_type),
            "profile_counts": _counter(openable_records, _profile_id),
            "pitch_pack_asset_counts": _pitch_pack_asset_counts(openable_records),
        },
        "glm": {
            "category_counts": _glm_category_counts(openable_records),
            "design_briefs": _glm_design_briefs(openable_records),
            "selected_batch_briefs": _selected_glm_briefs(queue),
        },
        "pitch_pack_plan": _pitch_pack_plan(queue),
        "review_throughput": {
            "selected_cards": len(queue),
            "operator_pack_size": DEFAULT_OPERATOR_PACK_SIZE,
            "operator_pack_count": len(operator_packs),
            "allowed_operator_outcomes": list(ALLOWED_REVIEW_OUTCOMES),
            "forbidden_actions": list(FORBIDDEN_REVIEW_ACTIONS),
            "required_state": dict(REQUIRED_REVIEW_STATE),
            "operator_packs": operator_packs,
        },
        "review_queue": queue,
        "next_actions": [
            "Review selected cards using email/contact-form routes only; do not send or submit.",
            "Save hold, needs_more_info, pitch_pack_ready, or reject outcomes for manual-review tracking.",
            "Keep launch readiness manual_review until an explicit outbound approval gate is added.",
        ],
    }


def write_no_send_review_batch_brief(
    *,
    state_root: Path,
    output_dir: Path | None = None,
    label: str = "pitch-card-review",
    batch_size: int = 120,
) -> dict[str, Any]:
    batch = build_no_send_review_batch(state_root=state_root, batch_size=batch_size)
    output_dir = output_dir or state_root / "review_batches"
    ensure_dir(output_dir)
    stamp = batch["generated_at"].replace(":", "").replace("-", "").split("+")[0]
    base = output_dir / f"{slugify(label)}-{stamp}Z"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    write_json(json_path, batch)
    write_text(md_path, _review_batch_markdown(batch))
    batch["artifact_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    write_json(json_path, batch)
    return batch


def build_no_send_review_wave(*, state_root: Path, batch_size: int = 120) -> dict[str, Any]:
    """Build no-send review waves for all unreviewed approved-route pitch cards."""
    records = list_leads(state_root=state_root)
    openable_records = [
        record
        for record in records
        if str(record.get("pitch_card_status") or "") in OPENABLE_PITCH_CARD_STATUSES
    ]
    unreviewed_records = [
        record
        for record in openable_records
        if not str(record.get("operator_review_outcome") or "").strip()
    ]
    queue = [_review_queue_entry(record) for record in sorted(unreviewed_records, key=_review_sort_key)]
    queue = [entry for entry in queue if entry["primary_route_type"] in APPROVED_REVIEW_ROUTE_TYPES]
    effective_batch_size = max(1, int(batch_size))
    batches = [
        _review_wave_batch(
            batch_index=index + 1,
            entries=queue[offset : offset + effective_batch_size],
            total_batches=(len(queue) + effective_batch_size - 1) // effective_batch_size,
        )
        for index, offset in enumerate(range(0, len(queue), effective_batch_size))
    ]

    return {
        "generated_at": utc_now(),
        "scope": "no_send_pitch_card_review_wave",
        "batch_size": effective_batch_size,
        "no_send_safety": _safety_summary(records),
        "counts": {
            "records": len(records),
            "openable_pitch_cards": len(openable_records),
            "unreviewed_openable_pitch_cards": len(unreviewed_records),
            "approved_route_review_cards": len(queue),
            "batch_count": len(batches),
            "operator_pack_count": sum(batch["review_throughput"]["operator_pack_count"] for batch in batches),
            "pitch_card_counts": pitch_card_counts(records),
            "route_counts": _counter(records, _primary_route_type),
            "approved_review_route_counts": _counter(openable_records, _primary_route_type, allowed=APPROVED_REVIEW_ROUTE_TYPES),
            "review_outcome_counts": _review_outcome_counts(openable_records),
            "review_lane_counts": _entry_counter(queue, "review_lane"),
            "city_counts": _entry_counter(queue, "city"),
            "profile_counts": _entry_counter(queue, "establishment_profile"),
        },
        "glm": {
            "category_counts": _glm_category_counts(openable_records),
            "design_briefs": _glm_design_briefs(openable_records),
            "wave_briefs": _selected_glm_briefs(queue),
        },
        "pitch_pack_plan": _pitch_pack_plan(queue),
        "review_throughput": {
            "selected_cards": len(queue),
            "operator_pack_size": DEFAULT_OPERATOR_PACK_SIZE,
            "operator_pack_count": sum(batch["review_throughput"]["operator_pack_count"] for batch in batches),
            "allowed_operator_outcomes": list(ALLOWED_REVIEW_OUTCOMES),
            "forbidden_actions": list(FORBIDDEN_REVIEW_ACTIONS),
            "required_state": dict(REQUIRED_REVIEW_STATE),
        },
        "batches": batches,
        "next_actions": [
            "Work batches in order and save only hold, needs_more_info, pitch_pack_ready, or reject outcomes.",
            "Do not send emails, submit contact forms, or set ready_for_outreach.",
            "Regenerate the wave after operator outcomes are saved so reviewed cards fall out of the queue.",
        ],
    }


def write_no_send_review_wave_brief(
    *,
    state_root: Path,
    output_dir: Path | None = None,
    label: str = "pitch-card-review-wave",
    batch_size: int = 120,
) -> dict[str, Any]:
    wave = build_no_send_review_wave(state_root=state_root, batch_size=batch_size)
    output_dir = output_dir or state_root / "review_batches"
    ensure_dir(output_dir)
    stamp = wave["generated_at"].replace(":", "").replace("-", "").split("+")[0]
    base = output_dir / f"{slugify(label)}-{stamp}Z"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    write_json(json_path, wave)
    write_text(md_path, _review_wave_markdown(wave))
    wave["artifact_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    write_json(json_path, wave)
    return wave


def _safety_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "real_outbound_allowed": False,
        "contact_form_submit_allowed": False,
        "email_send_allowed": False,
        "approved_review_route_types": sorted(APPROVED_REVIEW_ROUTE_TYPES),
        "reference_only_route_types": sorted(REFERENCE_ONLY_ROUTE_TYPES),
        "launch_readiness_status_counts": _counter(records, lambda record: str(record.get("launch_readiness_status") or "unknown")),
        "outreach_status_counts": _counter(records, lambda record: str(record.get("outreach_status") or "unknown")),
        "ready_for_outreach": sum(1 for record in records if record.get("launch_readiness_status") == "ready_for_outreach"),
        "pitch_ready": sum(1 for record in records if record.get("pitch_ready") is True),
        "pitch_pack_ready_no_send": sum(1 for record in records if record.get("pitch_pack_ready_no_send") is True),
        "outreach_status_new": sum(1 for record in records if record.get("outreach_status") == "new"),
    }


def _review_queue_entry(record: dict[str, Any]) -> dict[str, Any]:
    primary = get_primary_contact(record) or {}
    route_type = str(primary.get("type") or "")
    return {
        "lead_id": str(record.get("lead_id") or ""),
        "business_name": str(record.get("business_name") or ""),
        "city": str(record.get("city") or ""),
        "address": str(record.get("address") or ""),
        "primary_category": _primary_category(record),
        "menu_type": _menu_type(record),
        "establishment_profile": _profile_id(record),
        "establishment_profile_label": PROFILE_LABELS.get(_profile_id(record), _profile_id(record).replace("_", " ").title()),
        "pitch_card_status": str(record.get("pitch_card_status") or ""),
        "review_lane": _review_lane(record),
        "primary_route_type": route_type,
        "primary_route_value": _approved_route_value(primary),
        "quality_tier": str(record.get("quality_tier") or ""),
        "source_strength": str(record.get("source_strength") or ""),
        "review_action": _review_action(record),
        "pitch_pack_plan": _record_pitch_pack_plan(record),
        "pitch_card_reasons": list(record.get("pitch_card_reasons") or [])[:4],
    }


def _review_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        PITCH_CARD_REVIEW_ORDER.get(str(record.get("pitch_card_status") or ""), 99),
        QUALITY_ORDER.get(str(record.get("quality_tier") or ""), 99),
        CITY_ORDER.get(str(record.get("city") or ""), 99),
        str(record.get("establishment_profile") or ""),
        str(record.get("business_name") or ""),
        str(record.get("lead_id") or ""),
    )


def _review_action(record: dict[str, Any]) -> str:
    lane = _review_lane(record)
    if lane == "email_route_review":
        return "Confirm the saved address is a business owner route, then hold or needs_more_info."
    if lane == "contact_form_review":
        return "Open the form only for inspection; do not submit. Confirm it is a business contact route."
    if lane == "name_review":
        return "Confirm the saved shop name is not a directory or extraction artifact."
    if lane == "scope_review":
        return "Confirm Japan ramen/izakaya scope and reject non-scope records."
    return "Review evidence and save a no-send manual outcome."


def _review_lane(record: dict[str, Any]) -> str:
    route_type = _primary_route_type(record)
    pitch_status = str(record.get("pitch_card_status") or "")
    if route_type == "contact_form":
        return "contact_form_review"
    if pitch_status == "needs_email_review":
        return "email_route_review"
    if pitch_status == "needs_name_review":
        return "name_review"
    if pitch_status == "needs_scope_review":
        return "scope_review"
    if pitch_status == "reviewable":
        return "final_quality_review"
    return "blocked"


def _approved_route_value(primary: dict[str, Any]) -> str:
    route_type = str(primary.get("type") or "")
    if route_type not in APPROVED_REVIEW_ROUTE_TYPES:
        return ""
    return str(primary.get("value") or primary.get("url") or primary.get("label") or "")


def _record_pitch_pack_plan(record: dict[str, Any]) -> dict[str, Any]:
    profile = _profile_id(record)
    classification = _classification(record)
    route_type = _primary_route_type(record)
    guidance = PROFILE_ASSET_GUIDANCE.get(profile, {})
    route_assets = select_outreach_assets(classification, contact_type=route_type, establishment_profile=profile)
    reference_assets = select_outreach_assets(classification, contact_type="email", establishment_profile=profile)
    route_description = describe_outreach_assets(route_assets, classification=classification, establishment_profile=profile)
    reference_description = describe_outreach_assets(reference_assets, classification=classification, establishment_profile=profile)
    return {
        "classification": classification,
        "template_owner": "GLM",
        "template_edit_policy": "locked_glm_seedstyle_only",
        "family": guidance.get("family", "manual_review"),
        "asset_profile": guidance.get("asset_profile", "manual_review"),
        "selected_channel": route_type,
        "attachment_policy": _attachment_policy(route_type),
        "strategy_label": reference_description["strategy_label"],
        "strategy_note": reference_description["strategy_note"],
        "route_assets": [str(path) for path in route_assets],
        "route_asset_labels": [item["label"] for item in route_description["assets"]],
        "glm_reference_assets": [str(path) for path in reference_assets],
        "glm_reference_asset_labels": [item["label"] for item in reference_description["assets"]],
    }


def _classification(record: dict[str, Any]) -> str:
    existing = str(record.get("outreach_classification") or "").strip()
    if existing:
        return existing
    has_menu = bool(record.get("menu_evidence_found"))
    has_machine = bool(record.get("machine_evidence_found"))
    if has_menu and has_machine:
        return "menu_and_machine"
    if has_menu:
        return "menu_machine_unconfirmed"
    if has_machine:
        return "machine_only"
    return "menu_only"


def _attachment_policy(route_type: str) -> str:
    if route_type == "email":
        return "email_assets_review_only_no_send"
    if route_type == "contact_form":
        return "contact_form_no_attachment_no_submit"
    return "reference_only_no_outreach"


def _primary_route_type(record: dict[str, Any]) -> str:
    primary = get_primary_contact(record) or {}
    return str(primary.get("type") or "none")


def _primary_category(record: dict[str, Any]) -> str:
    return str(record.get("primary_category_v1") or record.get("type_of_restaurant") or "unknown")


def _menu_type(record: dict[str, Any]) -> str:
    return str(record.get("menu_type") or "unknown")


def _profile_id(record: dict[str, Any]) -> str:
    return str(record.get("establishment_profile_override") or record.get("establishment_profile") or "unknown")


def _review_outcome_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(record.get("operator_review_outcome") or "not_reviewed") for record in records)
    counts["reviewed"] = sum(value for key, value in counts.items() if key != "not_reviewed")
    return dict(sorted(counts.items()))


def _pitch_pack_asset_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in records:
        plan = _record_pitch_pack_plan(record)
        for path in plan["glm_reference_assets"]:
            counts[path] += 1
    return dict(sorted(counts.items()))


def _pitch_pack_plan(queue: list[dict[str, Any]]) -> dict[str, Any]:
    route_assets: Counter[str] = Counter()
    reference_assets: Counter[str] = Counter()
    attachment_policies: Counter[str] = Counter()
    strategies: Counter[str] = Counter()
    for entry in queue:
        plan = entry["pitch_pack_plan"]
        attachment_policies[str(plan["attachment_policy"])] += 1
        strategies[str(plan["strategy_label"])] += 1
        for path in plan["route_assets"]:
            route_assets[path] += 1
        for path in plan["glm_reference_assets"]:
            reference_assets[path] += 1
    return {
        "selected_cards": len(queue),
        "template_owner": "GLM",
        "template_edit_policy": "locked_glm_seedstyle_only",
        "stage": "planning_only_no_send",
        "real_outbound_allowed": False,
        "operator_review_required": True,
        "email_policy": "review_assets_only_no_send",
        "contact_form_policy": "inspect_only_no_attachment_no_submit",
        "route_asset_counts": dict(sorted(route_assets.items())),
        "glm_reference_asset_counts": dict(sorted(reference_assets.items())),
        "attachment_policy_counts": dict(sorted(attachment_policies.items())),
        "strategy_counts": dict(sorted(strategies.items())),
    }


def _counter(
    records: list[dict[str, Any]],
    key_fn: Any,
    *,
    allowed: set[str] | None = None,
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in records:
        value = str(key_fn(record) or "unknown")
        if allowed is not None and value not in allowed:
            continue
        counts[value] += 1
    return dict(sorted(counts.items()))


def _nested_counter(records: list[dict[str, Any]], outer_fn: Any, inner_fn: Any) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        counts[str(outer_fn(record) or "unknown")][str(inner_fn(record) or "unknown")] += 1
    return {outer: dict(sorted(inner.items())) for outer, inner in sorted(counts.items())}


def _glm_category_counts(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for profile, profile_records in _grouped(records, _profile_id).items():
        guidance = PROFILE_ASSET_GUIDANCE.get(profile, {})
        result[profile] = {
            "profile_label": PROFILE_LABELS.get(profile, profile.replace("_", " ").title()),
            "template_owner": "GLM",
            "template_edit_policy": "locked_glm_seedstyle_only",
            "family": guidance.get("family", "manual_review"),
            "asset_profile": guidance.get("asset_profile", "manual_review"),
            "openable_cards": len(profile_records),
            "review_lanes": _counter(profile_records, _review_lane),
            "routes": _counter(profile_records, _primary_route_type),
            "categories": _nested_counter(profile_records, _primary_category, _menu_type),
            "cities": _counter(profile_records, lambda record: str(record.get("city") or "unknown")),
        }
    return result


def _glm_design_briefs(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    briefs: list[dict[str, Any]] = []
    for profile, profile_records in sorted(_grouped(records, _profile_id).items()):
        guidance = PROFILE_ASSET_GUIDANCE.get(profile, {})
        briefs.append({
            "profile_id": profile,
            "profile_label": PROFILE_LABELS.get(profile, profile.replace("_", " ").title()),
            "template_owner": "GLM",
            "template_edit_policy": "locked_glm_seedstyle_only",
            "family": guidance.get("family", "manual_review"),
            "asset_profile": guidance.get("asset_profile", "manual_review"),
            "openable_cards": len(profile_records),
            "unreviewed_cards": sum(1 for record in profile_records if not str(record.get("operator_review_outcome") or "").strip()),
            "review_lane_counts": _counter(profile_records, _review_lane),
            "route_counts": _counter(profile_records, _primary_route_type),
            "city_counts": _counter(profile_records, lambda record: str(record.get("city") or "unknown")),
            "brief": guidance.get("brief", "Confirm scope and route quality before assigning locked GLM assets."),
        })
    return briefs


def _selected_glm_briefs(queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    briefs: list[dict[str, Any]] = []
    for profile, entries in sorted(_grouped(queue, lambda entry: entry["establishment_profile"]).items()):
        guidance = PROFILE_ASSET_GUIDANCE.get(profile, {})
        briefs.append({
            "profile_id": profile,
            "profile_label": PROFILE_LABELS.get(profile, profile.replace("_", " ").title()),
            "template_owner": "GLM",
            "template_edit_policy": "locked_glm_seedstyle_only",
            "family": guidance.get("family", "manual_review"),
            "asset_profile": guidance.get("asset_profile", "manual_review"),
            "selected_cards": len(entries),
            "review_lane_counts": _entry_counter(entries, "review_lane"),
            "route_counts": _entry_counter(entries, "primary_route_type"),
            "city_counts": _entry_counter(entries, "city"),
            "attachment_policy_counts": _entry_plan_counter(entries, "attachment_policy"),
            "route_asset_counts": _entry_asset_counts(entries, "route_assets"),
            "glm_reference_asset_counts": _entry_asset_counts(entries, "glm_reference_assets"),
            "allowed_operator_outcomes": list(ALLOWED_REVIEW_OUTCOMES),
            "brief": guidance.get("brief", "Confirm scope and route quality before assigning locked GLM assets."),
            "review_focus": _selected_brief_focus(entries),
        })
    return briefs


def _operator_review_packs(
    queue: list[dict[str, Any]],
    *,
    pack_size: int = DEFAULT_OPERATOR_PACK_SIZE,
    pack_id_prefix: str = "",
) -> list[dict[str, Any]]:
    packs: list[dict[str, Any]] = []
    if pack_size <= 0:
        return packs

    grouped_entries = _grouped(queue, _operator_pack_key)
    for group_key in sorted(grouped_entries):
        entries = grouped_entries[group_key]
        for offset in range(0, len(entries), pack_size):
            chunk = entries[offset : offset + pack_size]
            if not chunk:
                continue
            review_lane = str(chunk[0].get("review_lane") or "manual_review")
            pack_number = len(packs) + 1
            packs.append({
                "pack_id": f"{pack_id_prefix}pack-{pack_number:02d}-{slugify(group_key)}",
                "scope": "no_send_manual_review_only",
                "card_count": len(chunk),
                "review_lane": review_lane,
                "primary_route_counts": _entry_counter(chunk, "primary_route_type"),
                "profile_counts": _entry_counter(chunk, "establishment_profile"),
                "city_counts": _entry_counter(chunk, "city"),
                "attachment_policy_counts": _entry_plan_counter(chunk, "attachment_policy"),
                "route_asset_counts": _entry_asset_counts(chunk, "route_assets"),
                "glm_reference_asset_counts": _entry_asset_counts(chunk, "glm_reference_assets"),
                "allowed_operator_outcomes": list(ALLOWED_REVIEW_OUTCOMES),
                "forbidden_actions": list(FORBIDDEN_REVIEW_ACTIONS),
                "required_state": dict(REQUIRED_REVIEW_STATE),
                "review_focus": _pack_review_focus(review_lane),
                "lead_ids": [str(entry["lead_id"]) for entry in chunk],
            })
    return packs


def _review_wave_batch(*, batch_index: int, entries: list[dict[str, Any]], total_batches: int) -> dict[str, Any]:
    operator_packs = _operator_review_packs(entries, pack_id_prefix=f"batch-{batch_index:02d}-")
    return {
        "batch_id": f"review-wave-{batch_index:02d}",
        "scope": "no_send_manual_review_only",
        "batch_index": batch_index,
        "total_batches": total_batches,
        "card_count": len(entries),
        "review_lane_counts": _entry_counter(entries, "review_lane"),
        "route_counts": _entry_counter(entries, "primary_route_type"),
        "profile_counts": _entry_counter(entries, "establishment_profile"),
        "city_counts": _entry_counter(entries, "city"),
        "glm": {
            "selected_batch_briefs": _selected_glm_briefs(entries),
        },
        "pitch_pack_plan": _pitch_pack_plan(entries),
        "review_throughput": {
            "selected_cards": len(entries),
            "operator_pack_size": DEFAULT_OPERATOR_PACK_SIZE,
            "operator_pack_count": len(operator_packs),
            "allowed_operator_outcomes": list(ALLOWED_REVIEW_OUTCOMES),
            "forbidden_actions": list(FORBIDDEN_REVIEW_ACTIONS),
            "required_state": dict(REQUIRED_REVIEW_STATE),
            "operator_packs": operator_packs,
        },
        "review_queue": entries,
    }


def _operator_pack_key(entry: dict[str, Any]) -> str:
    plan = entry.get("pitch_pack_plan") or {}
    return "|".join([
        str(entry.get("review_lane") or "manual_review"),
        str(entry.get("primary_route_type") or "none"),
        str(entry.get("establishment_profile") or "unknown"),
        str(plan.get("asset_profile") or plan.get("strategy_label") or "asset_review"),
    ])


def _pack_review_focus(review_lane: str) -> str:
    if review_lane == "email_route_review":
        return "Confirm the saved email is a business owner route; do not send. Save hold, needs_more_info, pitch_pack_ready, or reject only."
    if review_lane == "contact_form_review":
        return "Inspect the contact form route only; do not submit and do not attach assets. Save hold, needs_more_info, pitch_pack_ready, or reject only."
    if review_lane == "name_review":
        return "Confirm the shop name is a real restaurant name, not a directory artifact. Save hold, needs_more_info, pitch_pack_ready, or reject only."
    if review_lane == "scope_review":
        return "Confirm Japan ramen/izakaya scope and reject non-scope records. Keep valid but unresolved records on hold."
    return "Review evidence quality only; keep the record manual-review blocked."


def _selected_brief_focus(entries: list[dict[str, Any]]) -> str:
    route_counts = _entry_counter(entries, "primary_route_type")
    if route_counts == {"contact_form": len(entries)}:
        return "Use GLM assets as reference only; contact forms stay no-attachment and no-submit during review."
    if "contact_form" in route_counts:
        return "Split email and contact-form cards before drafting; forms cannot carry attachments and must not be submitted."
    return "Review GLM asset fit for email-route cards only; do not draft or send outbound messages from this batch."


def _entry_counter(entries: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts = Counter(str(entry.get(key) or "unknown") for entry in entries)
    return dict(sorted(counts.items()))


def _entry_plan_counter(entries: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for entry in entries:
        plan = entry.get("pitch_pack_plan") or {}
        counts[str(plan.get(key) or "unknown")] += 1
    return dict(sorted(counts.items()))


def _entry_asset_counts(entries: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for entry in entries:
        plan = entry.get("pitch_pack_plan") or {}
        for path in plan.get(key) or []:
            counts[str(path)] += 1
    return dict(sorted(counts.items()))


def _grouped(records: list[dict[str, Any]], key_fn: Any) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(key_fn(record) or "unknown")].append(record)
    return dict(groups)


def _review_batch_markdown(batch: dict[str, Any]) -> str:
    safety = batch["no_send_safety"]
    counts = batch["counts"]
    lines = [
        "# No-Send Pitch-Card Review Batch",
        "",
        f"Generated: {batch['generated_at']}",
        "",
        "Real outbound allowed: `false`.",
        "Email sending and contact-form submission are blocked for this batch.",
        "",
        "## Queue",
        "",
        f"- Openable pitch cards: `{counts['openable_pitch_cards']}`",
        f"- Unreviewed openable cards: `{counts['unreviewed_openable_pitch_cards']}`",
        f"- Selected review queue: `{counts['selected_review_queue']}`",
        f"- Ready for outreach: `{safety['ready_for_outreach']}`",
        f"- Pitch ready: `{safety['pitch_ready']}`",
        f"- Pitch-pack ready no-send: `{safety['pitch_pack_ready_no_send']}`",
        f"- Outreach status new: `{safety['outreach_status_new']}`",
        "",
        "## GLM Briefs",
        "",
    ]
    for brief in batch["glm"]["design_briefs"]:
        lines.append(
            f"- `{brief['profile_id']}`: `{brief['openable_cards']}` cards, "
            f"asset profile `{brief['asset_profile']}`. {brief['brief']}"
        )
    lines.extend(["", "## Selected Batch GLM Briefs", ""])
    for brief in batch["glm"]["selected_batch_briefs"]:
        lines.append(
            f"- `{brief['profile_id']}`: `{brief['selected_cards']}` selected cards, "
            f"routes `{brief['route_counts']}`, assets `{brief['glm_reference_asset_counts']}`. "
            f"{brief['review_focus']}"
        )
    lines.extend(["", "## Pitch-Pack Plan", ""])
    lines.append(f"- Stage: `{batch['pitch_pack_plan']['stage']}`")
    lines.append(f"- Email policy: `{batch['pitch_pack_plan']['email_policy']}`")
    lines.append(f"- Contact-form policy: `{batch['pitch_pack_plan']['contact_form_policy']}`")
    for path, count in batch["pitch_pack_plan"]["glm_reference_asset_counts"].items():
        lines.append(f"- `{path}`: `{count}` selected review cards")
    lines.extend(["", "## Operator Review Packs", ""])
    for pack in batch["review_throughput"]["operator_packs"]:
        lines.append(
            f"- `{pack['pack_id']}`: `{pack['card_count']}` cards, "
            f"lane `{pack['review_lane']}`, routes `{pack['primary_route_counts']}`. "
            f"{pack['review_focus']}"
        )
    lines.extend(["", "## Selected Review Cards", ""])
    for entry in batch["review_queue"]:
        lines.append(
            f"- `{entry['lead_id']}` | {entry['business_name']} | {entry['city']} | "
            f"`{entry['review_lane']}` | `{entry['primary_route_type']}` | `{entry['establishment_profile']}`"
        )
    lines.append("")
    return "\n".join(lines)


def _review_wave_markdown(wave: dict[str, Any]) -> str:
    safety = wave["no_send_safety"]
    counts = wave["counts"]
    lines = [
        "# No-Send Pitch-Card Review Wave",
        "",
        f"Generated: {wave['generated_at']}",
        "",
        "Real outbound allowed: `false`.",
        "Email sending, contact-form submission, launch promotion, and ready-for-outreach changes are blocked for this wave.",
        "",
        "## Queue",
        "",
        f"- Openable pitch cards: `{counts['openable_pitch_cards']}`",
        f"- Unreviewed openable cards: `{counts['unreviewed_openable_pitch_cards']}`",
        f"- Approved-route review cards: `{counts['approved_route_review_cards']}`",
        f"- Review batches: `{counts['batch_count']}`",
        f"- Operator packs: `{counts['operator_pack_count']}`",
        f"- Ready for outreach: `{safety['ready_for_outreach']}`",
        f"- Pitch ready: `{safety['pitch_ready']}`",
        f"- Pitch-pack ready no-send: `{safety['pitch_pack_ready_no_send']}`",
        f"- Outreach status new: `{safety['outreach_status_new']}`",
        "",
        "## Wave GLM Briefs",
        "",
    ]
    for brief in wave["glm"]["wave_briefs"]:
        lines.append(
            f"- `{brief['profile_id']}`: `{brief['selected_cards']}` cards, "
            f"routes `{brief['route_counts']}`, assets `{brief['glm_reference_asset_counts']}`. "
            f"{brief['review_focus']}"
        )
    lines.extend(["", "## Wave Pitch-Pack Plan", ""])
    lines.append(f"- Stage: `{wave['pitch_pack_plan']['stage']}`")
    lines.append(f"- Email policy: `{wave['pitch_pack_plan']['email_policy']}`")
    lines.append(f"- Contact-form policy: `{wave['pitch_pack_plan']['contact_form_policy']}`")
    for path, count in wave["pitch_pack_plan"]["glm_reference_asset_counts"].items():
        lines.append(f"- `{path}`: `{count}` review cards")
    lines.extend(["", "## Review Batches", ""])
    for batch in wave["batches"]:
        lines.append(
            f"- `{batch['batch_id']}`: `{batch['card_count']}` cards, "
            f"lanes `{batch['review_lane_counts']}`, profiles `{batch['profile_counts']}`, "
            f"operator packs `{batch['review_throughput']['operator_pack_count']}`"
        )
        for pack in batch["review_throughput"]["operator_packs"]:
            lines.append(
                f"  - `{pack['pack_id']}`: `{pack['card_count']}` cards, "
                f"lane `{pack['review_lane']}`. {pack['review_focus']}"
            )
    lines.append("")
    return "\n".join(lines)
