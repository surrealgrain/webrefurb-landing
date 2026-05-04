"""Audit persisted lead state for launch-blocking drift."""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from .business_name import business_name_is_suspicious
from .constants import OUTREACH_SAMPLE_BY_ESTABLISHMENT_PROFILE, PACKAGE_1_KEY, PROJECT_ROOT
from .lead_dossier import migrate_lead_record, record_explicitly_not_japan
from .operator_state import apply_operator_state
from .record import authoritative_business_name
from .scoring import recommend_package_details_for_record

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
STALE_FIRST_CONTACT_MARKERS = (
    "突然のご連絡",
    "添付のサンプル",
    "添付ファイル",
    "ラミネート加工",
    "店舗へのお届け",
    "attached sample",
    "attached file",
    "reference file",
    "included file",
)
FIRST_CONTACT_PRICE_RE = re.compile(
    r"(?:¥|JPY\s*)(?:30,?000|45,?000|65,?000)|(?:30,?000|45,?000|65,?000)\s*円",
    re.I,
)
EMAIL_RE = re.compile(r"(?i)^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")
PLACEHOLDER_EMAIL_LOCAL_PARTS = {"test", "example", "sample", "info@example", "none", "unknown", "dummy"}
PLACEHOLDER_EMAIL_DOMAINS = {"example.com", "example.jp", "test.com", "test.jp", "invalid", "localhost"}
TERMINAL_OUTREACH_STATUSES = {"sent", "replied", "converted", "do_not_contact", "bounced", "unsubscribed", "closed"}
REVIEW_OUTREACH_STATUSES = {"new", "draft", "needs_review", "manual_review"}
PACKAGE_DEFAULT_REASONS = (
    "Imported public email lead; start with remote English ordering files until menu scope is reviewed.",
    "Directory pitch-card review candidate.",
    "Organic email pitch-card review candidate.",
)
ENTITY_TITLE_TOKENS = (
    "検索結果",
    "旧Twitter",
    "twitter",
    "グランドオープン",
    "発売",
    "お土産販売",
    "フリー麺ソン",
    "都市伝説",
    "ワークショップ",
    "Workshop",
    "サイト",
    "ホーム ...",
    "通信",
    "オンラインショップ",
    "実行委員会",
    "協会",
    "会社",
    "有限会社",
    "チェーン",
    "まとめ",
    "選",
    "百名店",
    "絶品",
    "待ってでも",
    "新店？",
    "美味しい",
    "めちゃくちゃ",
)
ENTITY_REVIEWER_RE = re.compile(r"^\(?[A-Za-z][A-Za-z0-9_.-]{2,31}\)?$")
ENTITY_ARTICLE_PUNCTUATION_RE = re.compile(r"[『』【】!?！？♪★]")
STATE_REPAIR_TIMESTAMP = "2026-05-04T00:00:00+00:00"


def expected_dark_assets(record: dict[str, Any]) -> list[str]:
    """Return allowed first-contact file attachments for a lead record.

    First-contact outreach uses inline preview images or hosted sample URLs,
    not PDF attachments. Kept for legacy audit/repair callers.
    """
    return []


def audit_state_leads(*, state_root: str | Path | None = None) -> dict[str, Any]:
    """Audit all lead JSON files and return structured findings."""
    root = Path(state_root) if state_root else STATE_ROOT
    leads_dir = root / "leads"
    findings: list[dict[str, Any]] = []
    readiness_report: list[dict[str, Any]] = []
    checked = 0
    lead_records: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []

    for path in sorted(leads_dir.glob("*.json")):
        checked += 1
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            findings.append(_finding(path, "", "invalid_json", str(exc)))
            continue

        lead_id = str(record.get("lead_id") or path.stem)
        lead_records[lead_id] = record
        records.append(record)
        _audit_binary_lead(record, path, lead_id, findings)
        _audit_business_name(record, path, lead_id, findings)
        _audit_readiness_drift(record, path, lead_id, findings, readiness_report)
        _audit_operator_state_drift(record, path, lead_id, findings)
        _audit_launch_location(record, path, lead_id, findings)
        _audit_outreach_assets(record, path, lead_id, findings)
        _audit_draft_asset_consistency(record, path, lead_id, findings)
        _audit_saved_outreach_copy(record, path, lead_id, findings)
        _audit_current_ready_safety(record, path, lead_id, findings)

    checked += _audit_launch_proof_assets(root / "launch_smoke_tests", lead_records, findings)
    checked += _audit_launch_proof_assets(root / "launch_batches", lead_records, findings)

    return {
        "ok": not findings,
        "checked": checked,
        "findings": findings,
        "readiness_report": readiness_report,
        "state_counts": _lead_state_counts(records),
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
        newly_disqualified = original_status != "disqualified" and new_status == "disqualified"

        quarantine_reasons = _ready_quarantine_reasons(record)
        if quarantine_reasons:
            changes.extend(_quarantine_ready_record(record, quarantine_reasons))
            changes.extend(_invalidate_final_check(root, lead_id, record, "ready_record_requires_regeneration"))

        if _record_contains_stale_first_contact_copy(record):
            _clear_saved_outreach_draft(record)
            changes.append("stale_saved_outreach_copy")
            changes.extend(_invalidate_final_check(root, lead_id, record, "stale_outreach_copy"))
        expected_assets = expected_dark_assets(record)
        if (record.get("outreach_assets_selected") or []) != expected_assets:
            record["outreach_assets_selected"] = expected_assets
            record["outreach_asset_template_family"] = "dark_v4c" if expected_assets else "no_first_contact_attachments"
            changes.append("outreach_assets_selected")

        package_rescored = False
        if _should_rescore_package(record):
            package_details = recommend_package_details_for_record(record)
            if record.get("recommended_primary_package") != package_details["package_key"]:
                record["recommended_primary_package"] = package_details["package_key"]
                changes.append("recommended_primary_package")
                package_rescored = True
            if record.get("package_recommendation_reason") != package_details["recommendation_reason"]:
                record["package_recommendation_reason"] = package_details["recommendation_reason"]
                changes.append("package_recommendation_reason")
                package_rescored = True
            if record.get("custom_quote_reason") != package_details["custom_quote_reason"]:
                record["custom_quote_reason"] = package_details["custom_quote_reason"]
                changes.append("custom_quote_reason")
                package_rescored = True
        if package_rescored:
            cleaned_reasons = [
                reason for reason in _normalise_reasons(record.get("launch_readiness_reasons"))
                if not reason.startswith("package_rescore:")
            ]
            if cleaned_reasons != _normalise_reasons(record.get("launch_readiness_reasons")):
                record["launch_readiness_reasons"] = cleaned_reasons
                changes.append("launch_readiness_reasons")
            record, package_migration_changes = migrate_lead_record(record)
            changes.extend(package_migration_changes)

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

        operator_record = apply_operator_state(record)
        for key in ("operator_state", "operator_reason"):
            if record.get(key) != operator_record.get(key):
                record[key] = operator_record.get(key)
                changes.append(key)

        lead_records[lead_id] = record
        if changes:
            final_status = str(record.get("launch_readiness_status") or "")
            final_reasons = _normalise_reasons(record.get("launch_readiness_reasons"))
            if original_status != final_status or original_reasons != final_reasons:
                readiness_change = _readiness_change_summary(
                    from_status=original_status,
                    from_reasons=original_reasons,
                    to_status=final_status,
                    to_reasons=final_reasons,
                )
            record["state_audit_repaired_at"] = STATE_REPAIR_TIMESTAMP
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


def _invalidate_final_check(root: Path, lead_id: str, record: dict[str, Any], reason: str) -> list[str]:
    changes: list[str] = []
    if record.get("send_ready_checked") is not False:
        record["send_ready_checked"] = False
        changes.append("send_ready_checked")
    if record.get("send_ready_checked_at"):
        record["send_ready_checked_at"] = ""
        changes.append("send_ready_checked_at")
    if record.get("send_ready_checklist"):
        record["send_ready_checklist"] = []
        changes.append("send_ready_checklist")

    previous = record.get("tailoring_audit") if isinstance(record.get("tailoring_audit"), dict) else {}
    invalidated_audit = {
        "passed": False,
        "invalidated_at": STATE_REPAIR_TIMESTAMP,
        "invalidation_reason": reason,
        "previous_input_hash": str(previous.get("input_hash") or ""),
    }
    if record.get("tailoring_audit") != invalidated_audit:
        record["tailoring_audit"] = invalidated_audit
        changes.append("tailoring_audit")

    final_check_dir = root / "final_checks" / lead_id
    if final_check_dir.exists():
        shutil.rmtree(final_check_dir)
        changes.append("final_check_artifacts")
    return changes


def _quarantine_ready_record(record: dict[str, Any], reasons: list[str]) -> list[str]:
    changes: list[str] = []
    existing = [
        reason
        for reason in _normalise_reasons(record.get("launch_readiness_reasons"))
        if reason != "qualified_with_safe_proof_and_contact_route"
    ]
    merged = _ordered_unique([*existing, "manual_review_required", *reasons, "production_readiness_regeneration_required"])
    if record.get("launch_readiness_status") != "manual_review":
        record["launch_readiness_status"] = "manual_review"
        changes.append("launch_readiness_status")
    if record.get("launch_readiness_reasons") != merged:
        record["launch_readiness_reasons"] = merged
        changes.append("launch_readiness_reasons")
    if record.get("manual_review_required") is not True:
        record["manual_review_required"] = True
        changes.append("manual_review_required")
    if str(record.get("outreach_status") or "") not in TERMINAL_OUTREACH_STATUSES:
        if record.get("outreach_status") != "needs_review":
            record["outreach_status"] = "needs_review"
            changes.append("outreach_status")

    dossier = record.get("lead_evidence_dossier")
    if isinstance(dossier, dict):
        if dossier.get("ready_to_contact") is not False:
            dossier["ready_to_contact"] = False
            changes.append("lead_evidence_dossier")
        if dossier.get("readiness_reasons") != merged:
            dossier["readiness_reasons"] = merged
            changes.append("lead_evidence_dossier")
    return changes


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


def _lead_state_counts(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    return {
        "lead": _count(records, lambda record: str(record.get("lead"))),
        "operator_state": _count(records, lambda record: str(record.get("operator_state") or "missing")),
        "launch_readiness_status": _count(records, lambda record: str(record.get("launch_readiness_status") or "missing")),
        "outreach_status": _count(records, lambda record: str(record.get("outreach_status") or "missing")),
        "review_status": _count(records, lambda record: str(record.get("review_status") or "missing")),
        "verification_status": _count(records, lambda record: str(record.get("verification_status") or "missing")),
        "email_verification_status": _count(records, lambda record: str(record.get("email_verification_status") or "missing")),
        "category": _count(records, lambda record: str(record.get("primary_category_v1") or record.get("category") or "missing")),
        "profile": _count(records, lambda record: str(record.get("establishment_profile") or "missing")),
        "package": _count(records, lambda record: str(record.get("recommended_primary_package") or "missing")),
    }


def _count(records: list[dict[str, Any]], key_fn) -> dict[str, int]:
    counts = Counter(key_fn(record) for record in records)
    return dict(sorted(counts.items()))


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


def _audit_operator_state_drift(
    record: dict[str, Any],
    path: Path,
    lead_id: str,
    findings: list[dict[str, Any]],
) -> None:
    migrated, _ = migrate_lead_record(record)
    stored_state = str(record.get("operator_state") or "")
    stored_reason = str(record.get("operator_reason") or "")
    expected_state = str(migrated.get("operator_state") or "")
    expected_reason = str(migrated.get("operator_reason") or "")
    if stored_state != expected_state or stored_reason != expected_reason:
        findings.append(_finding(
            path,
            lead_id,
            "operator_state_drift",
            f"{stored_state or 'missing'} -> {expected_state or 'missing'}: {expected_reason or 'no_reason'}",
        ))
    if record.get("contact_policy_evidence") != migrated.get("contact_policy_evidence"):
        findings.append(_finding(
            path,
            lead_id,
            "contact_policy_evidence_drift",
            "contact policy route evidence must be regenerated from current contact data",
        ))


def _audit_business_name(record: dict[str, Any], path: Path, lead_id: str, findings: list[dict[str, Any]]) -> None:
    business_name = str(record.get("business_name") or "").strip()
    locked_name = str(record.get("locked_business_name") or "").strip()
    authoritative = authoritative_business_name(record)
    quarantined_reject = _is_quarantined_restaurant_email_reject(record)

    if locked_name and business_name and locked_name != business_name:
        findings.append(_finding(
            path,
            lead_id,
            "business_name_diverges_from_locked_name",
            f"business_name={business_name!r} locked_business_name={locked_name!r}",
        ))

    if (
        (business_name_is_suspicious(authoritative) or _entity_quality_flags(record))
        and not quarantined_reject
        and not _has_production_regeneration_quarantine(record)
        and str(record.get("launch_readiness_status") or "") == "ready_for_outreach"
    ):
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


def _is_quarantined_restaurant_email_reject(record: dict[str, Any]) -> bool:
    lead_id = str(record.get("lead_id") or "")
    source_query = str(record.get("source_query") or "")
    source_file = str(record.get("source_file") or "")
    is_restaurant_email_queue = (
        lead_id.startswith("wrm-email-")
        or source_query == "restaurant_email_import"
        or "restaurant_email_leads" in source_file
    )
    if not is_restaurant_email_queue:
        return False
    return (
        str(record.get("verification_status") or "") == "rejected"
        and str(record.get("pitch_readiness_status") or "") in {"rejected", "hard_blocked"}
        and record.get("pitch_ready") is not True
        and str(record.get("launch_readiness_status") or "") != "ready_for_outreach"
    )


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


def _audit_saved_outreach_copy(record: dict[str, Any], path: Path, lead_id: str, findings: list[dict[str, Any]]) -> None:
    markers = _stale_first_contact_markers(record)
    if markers:
        findings.append(_finding(
            path,
            lead_id,
            "stale_outreach_copy_marker",
            f"markers={markers}",
        ))


def _audit_current_ready_safety(record: dict[str, Any], path: Path, lead_id: str, findings: list[dict[str, Any]]) -> None:
    if str(record.get("launch_readiness_status") or "") != "ready_for_outreach":
        return

    entity_flags = _entity_quality_flags(record)
    if entity_flags:
        findings.append(_finding(path, lead_id, "ready_entity_quality_flag", f"flags={entity_flags}"))

    stale_markers = _stale_first_contact_markers(record)
    if stale_markers:
        findings.append(_finding(path, lead_id, "ready_stale_outreach_copy", f"markers={stale_markers}"))

    placeholder_reasons = _placeholder_email_reasons(record)
    if placeholder_reasons:
        findings.append(_finding(path, lead_id, "ready_placeholder_email", f"reasons={placeholder_reasons}"))

    package_reasons = _package_rescore_reasons(record)
    if package_reasons:
        findings.append(_finding(path, lead_id, "ready_package_requires_rescore", f"reasons={package_reasons}"))


def _record_mentions_attached_sample(record: dict[str, Any]) -> bool:
    text = "\n".join(str(record.get(field) or "") for field in CUSTOMER_TEXT_FIELDS).lower()
    return any(marker in text for marker in ATTACHED_SAMPLE_MARKERS)


def _record_contains_stale_first_contact_copy(record: dict[str, Any]) -> bool:
    return bool(_stale_first_contact_markers(record))


def _has_production_regeneration_quarantine(record: dict[str, Any]) -> bool:
    reasons = set(_normalise_reasons(record.get("launch_readiness_reasons")))
    return (
        str(record.get("launch_readiness_status") or "") != "ready_for_outreach"
        and "production_readiness_regeneration_required" in reasons
    )


def _stale_first_contact_markers(record: dict[str, Any]) -> list[str]:
    text = _customer_text(record)
    lowered = text.lower()
    markers = [marker for marker in STALE_FIRST_CONTACT_MARKERS if marker.lower() in lowered]
    if FIRST_CONTACT_PRICE_RE.search(text):
        markers.append("first_contact_pricing_dump")
    return sorted(set(markers))


def _customer_text(record: dict[str, Any]) -> str:
    values = [record.get(field) for field in CUSTOMER_TEXT_FIELDS]
    return "\n".join(_stringify_customer_value(value) for value in values if value is not None)


def _stringify_customer_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "")


def _ready_quarantine_reasons(record: dict[str, Any]) -> list[str]:
    if str(record.get("launch_readiness_status") or "") != "ready_for_outreach":
        return []
    reasons: list[str] = []
    reasons.extend(f"entity_quality:{flag}" for flag in _entity_quality_flags(record))
    reasons.extend(f"stale_copy:{marker}" for marker in _stale_first_contact_markers(record))
    reasons.extend(f"placeholder_email:{reason}" for reason in _placeholder_email_reasons(record))
    reasons.extend(f"package_rescore:{reason}" for reason in _package_rescore_reasons(record))
    return _ordered_unique(reasons)


def _entity_quality_flags(record: dict[str, Any]) -> list[str]:
    name = authoritative_business_name(record)
    cleaned = re.sub(r"\s+", " ", str(name or "")).strip()
    lowered = cleaned.lower()
    flags: list[str] = []

    if business_name_is_suspicious(cleaned):
        flags.append("suspicious_business_name")
    if ENTITY_REVIEWER_RE.fullmatch(cleaned) and not _has_restaurant_name_context(record):
        flags.append("reviewer_username_as_name")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        flags.append("parenthesized_reviewer_username")
    if ENTITY_ARTICLE_PUNCTUATION_RE.search(cleaned) and len(cleaned) > 18:
        flags.append("article_or_review_title")
    if any(token.lower() in lowered for token in (token.lower() for token in ENTITY_TITLE_TOKENS)):
        flags.append("media_blog_pr_or_directory_title")
    if re.search(r"(?i)\b(pr|press|release|blog|guide|ranking|search results)\b", cleaned):
        flags.append("media_blog_pr_or_directory_title")
    if "..." in cleaned or "…" in cleaned:
        flags.append("truncated_page_title")

    return _ordered_unique(flags)


def _has_restaurant_name_context(record: dict[str, Any]) -> bool:
    text = " ".join([
        str(record.get("primary_category_v1") or record.get("category") or ""),
        " ".join(str(item) for item in record.get("evidence_snippets") or []),
        " ".join(str(item) for item in record.get("lead_signals") or []),
    ]).lower()
    return any(token in text for token in ("ramen", "ラーメン", "居酒屋", "izakaya", "酒場", "焼鳥", "焼き鳥"))


def _placeholder_email_reasons(record: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for email in _record_emails(record):
        lowered = email.lower()
        if not EMAIL_RE.fullmatch(lowered):
            reasons.append(f"invalid_email:{email}")
            continue
        local, domain = lowered.rsplit("@", 1)
        if "%" in local or "%22" in lowered:
            reasons.append(f"encoded_or_artifact_email:{email}")
        if local in PLACEHOLDER_EMAIL_LOCAL_PARTS or domain in PLACEHOLDER_EMAIL_DOMAINS:
            reasons.append(f"placeholder_email:{email}")
        if re.fullmatch(r"(.)\1{3,}", local) or re.fullmatch(r"\d{4,}", local):
            reasons.append(f"placeholder_local_part:{email}")
    return _ordered_unique(reasons)


def _record_emails(record: dict[str, Any]) -> list[str]:
    emails = [str(record.get("email") or "").strip()]
    for contact in record.get("contacts") or []:
        if isinstance(contact, dict) and str(contact.get("type") or "").lower() == "email":
            emails.append(str(contact.get("value") or "").strip())
    return [email for email in _ordered_unique(emails) if email]


def _package_rescore_reasons(record: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    package = str(record.get("recommended_primary_package") or "").strip()
    package_reason = str(record.get("package_recommendation_reason") or "").strip()
    if not package or package == "none":
        reasons.append("missing_package_recommendation")
    if not package_reason:
        reasons.append("missing_package_recommendation_reason")
    if package == PACKAGE_1_KEY and package_reason in PACKAGE_DEFAULT_REASONS:
        reasons.append("import_or_directory_default_package_1")
    return reasons


def _should_rescore_package(record: dict[str, Any]) -> bool:
    if record.get("lead") is not True:
        return False
    if record.get("operator_package_override") is True:
        return False
    return True


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


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
