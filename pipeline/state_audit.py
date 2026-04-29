"""Audit persisted lead state for launch-blocking drift."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .business_name import business_name_is_suspicious
from .constants import PROJECT_ROOT
from .lead_dossier import migrate_lead_record, record_explicitly_not_japan
from .record import authoritative_business_name

STATE_ROOT = PROJECT_ROOT / "state"
TEMPLATES_ROOT = PROJECT_ROOT / "assets" / "templates"
RAMEN_MENU_TEMPLATE = TEMPLATES_ROOT / "ramen_food_menu.html"
IZAKAYA_MENU_TEMPLATE = TEMPLATES_ROOT / "izakaya_food_menu.html"
IZAKAYA_FOOD_DRINKS_TEMPLATE = TEMPLATES_ROOT / "izakaya_food_drinks_menu.html"
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
ATTACHED_SAMPLE_MARKERS = (
    "添付のサンプル",
    "添付ファイル",
    "attached sample",
    "attached file",
    "reference file",
    "included file",
)


def expected_dark_assets(record: dict[str, Any]) -> list[str]:
    """Return the only allowed outreach sample assets for a lead record."""
    status = str(record.get("outreach_status") or "").lower()
    readiness = str(record.get("launch_readiness_status") or "").lower()
    if status in DNC_STATUSES or readiness == "disqualified" or record.get("lead") is False:
        return []
    if _primary_contact_type(record) == "contact_form":
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
        assets = [IZAKAYA_FOOD_DRINKS_TEMPLATE]
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
    readiness_report: list[dict[str, Any]] = []
    checked = 0
    lead_records: dict[str, dict[str, Any]] = {}

    for path in sorted(leads_dir.glob("*.json")):
        checked += 1
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            findings.append(_finding(path, "", "invalid_json", str(exc)))
            continue

        lead_id = str(record.get("lead_id") or path.stem)
        lead_records[lead_id] = record
        _audit_binary_lead(record, path, lead_id, findings)
        _audit_business_name(record, path, lead_id, findings)
        _audit_readiness_drift(record, path, lead_id, findings, readiness_report)
        _audit_launch_location(record, path, lead_id, findings)
        _audit_outreach_assets(record, path, lead_id, findings)
        _audit_draft_asset_consistency(record, path, lead_id, findings)

    checked += _audit_launch_proof_assets(root / "launch_smoke_tests", lead_records, findings)
    checked += _audit_launch_proof_assets(root / "launch_batches", lead_records, findings)

    return {
        "ok": not findings,
        "checked": checked,
        "findings": findings,
        "readiness_report": readiness_report,
    }


def repair_state_leads(*, state_root: str | Path | None = None) -> dict[str, Any]:
    """Repair deterministic state drift, then return a fresh audit result."""
    root = Path(state_root) if state_root else STATE_ROOT
    leads_dir = root / "leads"
    repaired: list[dict[str, Any]] = []
    lead_records: dict[str, dict[str, Any]] = {}

    for path in sorted(leads_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        lead_id = str(record.get("lead_id") or path.stem)
        original_status = str(record.get("launch_readiness_status") or "")
        original_reasons = _normalise_reasons(record.get("launch_readiness_reasons"))
        changes: list[str] = []
        readiness_change: dict[str, Any] | None = None

        migrated, migration_changes = migrate_lead_record(record)
        if migration_changes:
            changes.extend(migration_changes)
        record = migrated
        new_status = str(record.get("launch_readiness_status") or "")
        new_reasons = _normalise_reasons(record.get("launch_readiness_reasons"))
        if original_status != new_status or original_reasons != new_reasons:
            readiness_change = _readiness_change_summary(
                from_status=original_status,
                from_reasons=original_reasons,
                to_status=new_status,
                to_reasons=new_reasons,
            )

        newly_disqualified = original_status != "disqualified" and new_status == "disqualified"
        expected_assets = expected_dark_assets(record)
        if (record.get("outreach_assets_selected") or []) != expected_assets:
            record["outreach_assets_selected"] = expected_assets
            record["outreach_asset_template_family"] = "dark_v4c" if expected_assets else "none_do_not_contact"
            changes.append("outreach_assets_selected")

        if newly_disqualified:
            _clear_saved_outreach_draft(record)
            changes.append("disqualified_saved_draft")
        elif not expected_assets and _record_mentions_attached_sample(record):
            record["outreach_draft_body"] = None
            record["outreach_draft_english_body"] = None
            record["outreach_draft_subject"] = None
            record["outreach_draft_manually_edited"] = False
            record["outreach_draft_edited_at"] = None
            changes.append("incompatible_saved_draft")

        if record_explicitly_not_japan(record):
            reasons = list(record.get("launch_readiness_reasons") or [])
            if "not_in_japan" not in reasons:
                reasons.append("not_in_japan")
            if record.get("launch_readiness_status") != "disqualified":
                record["launch_readiness_status"] = "disqualified"
                changes.append("launch_readiness_status")
            if record.get("launch_readiness_reasons") != reasons:
                record["launch_readiness_reasons"] = reasons
                changes.append("launch_readiness_reasons")
            if record.get("outreach_status") not in {"sent", "replied", "converted", "do_not_contact"}:
                record["outreach_status"] = "do_not_contact"
                changes.append("outreach_status")
            if record.get("outreach_assets_selected"):
                record["outreach_assets_selected"] = []
                record["outreach_asset_template_family"] = "none_do_not_contact"
                changes.append("outreach_assets_selected")
            dossier = record.get("lead_evidence_dossier")
            if isinstance(dossier, dict):
                if dossier.get("ready_to_contact") is not False:
                    dossier["ready_to_contact"] = False
                    changes.append("lead_evidence_dossier")
                if dossier.get("readiness_reasons") != reasons:
                    dossier["readiness_reasons"] = reasons
                    changes.append("lead_evidence_dossier")

        business_name = str(record.get("business_name") or "").strip()
        locked_name = str(record.get("locked_business_name") or "").strip()
        if locked_name and business_name and locked_name != business_name and not business_name_is_suspicious(locked_name):
            record["business_name"] = locked_name
            for field in CUSTOMER_TEXT_FIELDS:
                record[field] = _replace_text_value(record.get(field), business_name, locked_name)
            changes.append("business_name")
            changes.append("customer_text_name_references")

        lead_records[lead_id] = record
        if changes:
            record["state_audit_repaired_at"] = "2026-04-29T00:00:00+00:00"
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            item = {"lead_id": lead_id, "file": str(path), "changes": sorted(set(changes))}
            if readiness_change:
                item["readiness_change"] = readiness_change
            repaired.append(item)

    repaired.extend(_repair_launch_proof_assets(root / "launch_smoke_tests", lead_records))
    repaired.extend(_repair_launch_proof_assets(root / "launch_batches", lead_records))

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


def _clear_saved_outreach_draft(record: dict[str, Any]) -> None:
    record["outreach_draft_body"] = None
    record["outreach_draft_english_body"] = None
    record["outreach_draft_subject"] = None
    record["outreach_draft_manually_edited"] = False
    record["outreach_draft_edited_at"] = None


def _normalise_reasons(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(reason) for reason in value]
    if value:
        return [str(value)]
    return []


def _readiness_change_summary(
    *,
    from_status: str,
    from_reasons: list[str],
    to_status: str,
    to_reasons: list[str],
) -> dict[str, Any]:
    return {
        "from_status": from_status,
        "from_reasons": from_reasons,
        "to_status": to_status,
        "to_reasons": to_reasons,
        "summary": f"{from_status or 'unset'} -> {to_status or 'unset'}: {', '.join(to_reasons) or 'no_reasons'}",
    }


def _audit_binary_lead(record: dict[str, Any], path: Path, lead_id: str, findings: list[dict[str, Any]]) -> None:
    if record.get("lead") not in {True, False}:
        findings.append(_finding(path, lead_id, "lead_not_binary", "`lead` must be strictly true or false"))


def _audit_readiness_drift(
    record: dict[str, Any],
    path: Path,
    lead_id: str,
    findings: list[dict[str, Any]],
    readiness_report: list[dict[str, Any]],
) -> None:
    migrated, _ = migrate_lead_record(record)
    stored_status = str(record.get("launch_readiness_status") or "")
    stored_reasons = _normalise_reasons(record.get("launch_readiness_reasons"))
    expected_status = str(migrated.get("launch_readiness_status") or "")
    expected_reasons = _normalise_reasons(migrated.get("launch_readiness_reasons"))
    if stored_status == expected_status and stored_reasons == expected_reasons:
        return

    change = _readiness_change_summary(
        from_status=stored_status,
        from_reasons=stored_reasons,
        to_status=expected_status,
        to_reasons=expected_reasons,
    )
    readiness_report.append({"lead_id": lead_id, **change})
    findings.append(_finding(
        path,
        lead_id,
        "launch_readiness_drift",
        change["summary"],
    ))


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


def _audit_launch_location(record: dict[str, Any], path: Path, lead_id: str, findings: list[dict[str, Any]]) -> None:
    if record.get("lead") is not True:
        return
    if record_explicitly_not_japan(record) and record.get("launch_readiness_status") == "ready_for_outreach":
        findings.append(_finding(
            path,
            lead_id,
            "ready_lead_not_in_japan",
            "Japan-only product cannot launch outreach for a non-Japan address",
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


def _audit_draft_asset_consistency(record: dict[str, Any], path: Path, lead_id: str, findings: list[dict[str, Any]]) -> None:
    assets = [str(asset) for asset in record.get("outreach_assets_selected") or []]
    profile = str(record.get("establishment_profile") or "").lower()
    category = str(record.get("primary_category_v1") or record.get("category") or "").lower()

    if not assets and _record_mentions_attached_sample(record):
        findings.append(_finding(
            path,
            lead_id,
            "draft_mentions_attachment_without_assets",
            "saved outreach draft references an attached/reference sample but no sample assets are selected",
        ))

    if "izakaya" in profile or category == "izakaya":
        food_only = str(IZAKAYA_MENU_TEMPLATE)
        if food_only in assets:
            findings.append(_finding(
                path,
                lead_id,
                "izakaya_food_drinks_claim_uses_food_only_template",
                f"asset={food_only!r}; use {str(IZAKAYA_FOOD_DRINKS_TEMPLATE)!r}",
            ))


def _record_mentions_attached_sample(record: dict[str, Any]) -> bool:
    text = "\n".join(str(record.get(field) or "") for field in CUSTOMER_TEXT_FIELDS).lower()
    return any(marker in text for marker in ATTACHED_SAMPLE_MARKERS)


def _primary_contact_type(record: dict[str, Any]) -> str:
    contacts = record.get("contacts") or []
    if not isinstance(contacts, list):
        return ""
    for contact in contacts:
        if isinstance(contact, dict) and contact.get("actionable") is True:
            return str(contact.get("type") or "").strip().lower()
    return ""


def _audit_launch_proof_assets(
    directory: Path,
    lead_records: dict[str, dict[str, Any]],
    findings: list[dict[str, Any]],
) -> int:
    checked = 0
    for path in sorted(directory.glob("*.json")):
        checked += 1
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            findings.append(_finding(path, "", "invalid_json", str(exc)))
            continue
        for lead in record.get("leads") or []:
            lead_id = str(lead.get("lead_id") or "")
            proof_asset = str(lead.get("proof_asset") or "")
            expected = _expected_primary_proof_asset(lead_records, lead_id)
            if proof_asset != expected:
                findings.append(_finding(
                    path,
                    lead_id,
                    "launch_proof_asset_does_not_match_dark_profile",
                    f"expected={expected!r} actual={proof_asset!r}",
                ))
            if proof_asset:
                _audit_asset_value(path, lead_id, proof_asset, findings)
    return checked


def _repair_launch_proof_assets(directory: Path, lead_records: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    repaired: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        changed_leads: list[str] = []
        for lead in record.get("leads") or []:
            lead_id = str(lead.get("lead_id") or "")
            expected = _expected_primary_proof_asset(lead_records, lead_id)
            if lead.get("proof_asset") != expected:
                lead["proof_asset"] = expected
                changed_leads.append(lead_id)
        if changed_leads:
            record["state_audit_repaired_at"] = "2026-04-29T00:00:00+00:00"
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            repaired.append({
                "lead_id": ",".join(changed_leads),
                "file": str(path),
                "changes": ["launch_proof_asset"],
            })
    return repaired


def _expected_primary_proof_asset(lead_records: dict[str, dict[str, Any]], lead_id: str) -> str:
    lead = lead_records.get(lead_id) or {}
    assets = expected_dark_assets(lead)
    return assets[0] if assets else ""


def _audit_asset_value(path: Path, lead_id: str, asset: str, findings: list[dict[str, Any]]) -> None:
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
