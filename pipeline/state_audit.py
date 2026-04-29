"""Audit persisted lead state for launch-blocking drift."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .business_name import business_name_is_suspicious
from .constants import PROJECT_ROOT
from .record import authoritative_business_name

STATE_ROOT = PROJECT_ROOT / "state"
TEMPLATES_ROOT = PROJECT_ROOT / "assets" / "templates"
RAMEN_MENU_TEMPLATE = TEMPLATES_ROOT / "ramen_food_menu.html"
IZAKAYA_MENU_TEMPLATE = TEMPLATES_ROOT / "izakaya_food_menu.html"
TICKET_MACHINE_TEMPLATE = TEMPLATES_ROOT / "ticket_machine_guide.html"

BLOCKED_ASSET_PATTERNS = (
    "state/builds",
    "phase10-sample-",
    "glm_menu_template",
    "ticket_machine_guide_template",
    "food_menu_print_ready",
    "restaurant_menu_print_ready",
    "locked_food_menu",
    "locked_drinks_menu",
    "p1-single-section",
    "p1-two-section",
    "p1-split-food-drinks",
    "p1-smoke",
    "cream",
)
CUSTOMER_TEXT_FIELDS = (
    "outreach_draft_body",
    "outreach_draft_english_body",
    "outreach_draft_subject",
    "pitch_draft",
    "shop_preview_html",
    "preview_html",
)
DNC_STATUSES = {"do_not_contact", "disqualified"}


def expected_dark_assets(record: dict[str, Any]) -> list[str]:
    """Return the only allowed outreach sample assets for a lead record."""
    status = str(record.get("outreach_status") or "").lower()
    readiness = str(record.get("launch_readiness_status") or "").lower()
    if status in DNC_STATUSES or readiness == "disqualified" or record.get("lead") is False:
        return []

    profile = str(record.get("establishment_profile") or "").lower()
    category = str(record.get("primary_category_v1") or record.get("category") or "").lower()
    classification = str(record.get("outreach_classification") or "").lower()
    has_machine = (
        record.get("machine_evidence_found") is True
        or "ticket_machine" in profile
        or classification in {"menu_and_machine", "machine_only"}
    )

    if classification == "machine_only":
        assets = [TICKET_MACHINE_TEMPLATE]
    elif "izakaya" in profile or category == "izakaya":
        assets = [IZAKAYA_MENU_TEMPLATE]
    else:
        assets = [RAMEN_MENU_TEMPLATE]

    if has_machine and TICKET_MACHINE_TEMPLATE not in assets:
        assets.append(TICKET_MACHINE_TEMPLATE)

    return [str(path) for path in assets]


def audit_state_leads(*, state_root: str | Path | None = None) -> dict[str, Any]:
    """Audit all lead JSON files and return structured findings."""
    root = Path(state_root) if state_root else STATE_ROOT
    leads_dir = root / "leads"
    findings: list[dict[str, Any]] = []
    checked = 0

    for path in sorted(leads_dir.glob("*.json")):
        checked += 1
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            findings.append(_finding(path, "", "invalid_json", str(exc)))
            continue

        lead_id = str(record.get("lead_id") or path.stem)
        _audit_binary_lead(record, path, lead_id, findings)
        _audit_business_name(record, path, lead_id, findings)
        _audit_outreach_assets(record, path, lead_id, findings)

    return {
        "ok": not findings,
        "checked": checked,
        "findings": findings,
    }


def repair_state_leads(*, state_root: str | Path | None = None) -> dict[str, Any]:
    """Repair deterministic state drift, then return a fresh audit result."""
    root = Path(state_root) if state_root else STATE_ROOT
    leads_dir = root / "leads"
    repaired: list[dict[str, Any]] = []

    for path in sorted(leads_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        lead_id = str(record.get("lead_id") or path.stem)
        changes: list[str] = []
        expected_assets = expected_dark_assets(record)
        if (record.get("outreach_assets_selected") or []) != expected_assets:
            record["outreach_assets_selected"] = expected_assets
            record["outreach_asset_template_family"] = "dark_v4c" if expected_assets else "none_do_not_contact"
            changes.append("outreach_assets_selected")

        business_name = str(record.get("business_name") or "").strip()
        locked_name = str(record.get("locked_business_name") or "").strip()
        if locked_name and business_name and locked_name != business_name and not business_name_is_suspicious(locked_name):
            record["business_name"] = locked_name
            for field in CUSTOMER_TEXT_FIELDS:
                record[field] = _replace_text_value(record.get(field), business_name, locked_name)
            changes.append("business_name")
            changes.append("customer_text_name_references")

        if changes:
            record["state_audit_repaired_at"] = "2026-04-29T00:00:00+00:00"
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            repaired.append({"lead_id": lead_id, "file": str(path), "changes": sorted(set(changes))})

    audit = audit_state_leads(state_root=root)
    audit["repaired"] = repaired
    return audit


def _replace_text_value(value: Any, old: str, new: str) -> Any:
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, list):
        return [_replace_text_value(item, old, new) for item in value]
    if isinstance(value, dict):
        return {key: _replace_text_value(item, old, new) for key, item in value.items()}
    return value


def _audit_binary_lead(record: dict[str, Any], path: Path, lead_id: str, findings: list[dict[str, Any]]) -> None:
    if record.get("lead") not in {True, False}:
        findings.append(_finding(path, lead_id, "lead_not_binary", "`lead` must be strictly true or false"))


def _audit_business_name(record: dict[str, Any], path: Path, lead_id: str, findings: list[dict[str, Any]]) -> None:
    business_name = str(record.get("business_name") or "").strip()
    locked_name = str(record.get("locked_business_name") or "").strip()
    authoritative = authoritative_business_name(record)

    if locked_name and business_name and locked_name != business_name:
        findings.append(_finding(
            path,
            lead_id,
            "business_name_diverges_from_locked_name",
            f"business_name={business_name!r} locked_business_name={locked_name!r}",
        ))

    if business_name_is_suspicious(authoritative):
        findings.append(_finding(
            path,
            lead_id,
            "authoritative_business_name_suspicious",
            f"authoritative_business_name={authoritative!r}",
        ))

    if locked_name and business_name and locked_name != business_name:
        for field in CUSTOMER_TEXT_FIELDS:
            value = json.dumps(record.get(field), ensure_ascii=False)
            if business_name and business_name in value:
                findings.append(_finding(
                    path,
                    lead_id,
                    "poisoned_name_in_customer_text",
                    f"{field} contains stale business_name={business_name!r}",
                ))


def _audit_outreach_assets(record: dict[str, Any], path: Path, lead_id: str, findings: list[dict[str, Any]]) -> None:
    assets = [str(asset) for asset in record.get("outreach_assets_selected") or []]
    expected = expected_dark_assets(record)

    if assets != expected:
        findings.append(_finding(
            path,
            lead_id,
            "outreach_assets_do_not_match_dark_profile",
            f"expected={expected} actual={assets}",
        ))

    for asset in assets:
        lower = asset.lower()
        blocked = [pattern for pattern in BLOCKED_ASSET_PATTERNS if pattern in lower]
        if blocked:
            findings.append(_finding(
                path,
                lead_id,
                "legacy_or_cream_asset_reference",
                f"asset={asset!r} matched={blocked}",
            ))
        if "assets/templates" not in asset:
            findings.append(_finding(
                path,
                lead_id,
                "asset_not_from_dark_template_directory",
                f"asset={asset!r}",
            ))
        if not Path(asset).exists():
            findings.append(_finding(path, lead_id, "asset_file_missing", f"asset={asset!r}"))


def _finding(path: Path, lead_id: str, code: str, detail: str) -> dict[str, Any]:
    return {
        "lead_id": lead_id,
        "file": str(path),
        "code": code,
        "detail": detail,
    }
