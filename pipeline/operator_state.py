from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from .business_name import business_name_is_suspicious
from .constants import EXCLUDED_BUSINESS_TOKENS, JP_AREAS, PACKAGE_REGISTRY


OPERATOR_READY = "ready"
OPERATOR_REVIEW = "review"
OPERATOR_SKIP = "skip"
OPERATOR_DONE = "done"

READINESS_READY = "ready_for_outreach"
READINESS_MANUAL = "manual_review"
READINESS_DISQUALIFIED = "disqualified"

DONE_OUTREACH_STATUSES = {
    "sent",
    "contacted_form",
    "replied",
    "converted",
    "bounced",
    "invalid",
    "unsubscribed",
    "closed",
}
SKIP_OUTREACH_STATUSES = {
    "do_not_contact",
    "rejected",
    "skipped",
}
PUBLIC_EMAIL_SOURCE_HINTS = {
    "official_site",
    "shop_site",
    "restaurant_site",
    "tabelog",
    "hotpepper",
    "google_business",
    "public_listing",
    "legacy_record",
    "manual_review",
}
EMAIL_REFUSAL_TOKENS = (
    "営業メール",
    "営業目的",
    "広告",
    "宣伝",
    "勧誘",
    "セールス",
    "お断り",
    "sales",
    "advertising",
    "solicitation",
    "no sales",
    "do not send",
)
PLACEHOLDER_EMAIL_DOMAINS = {"example.com", "example.jp", "test.com", "test.jp", "invalid", "localhost"}
PLACEHOLDER_EMAIL_LOCAL_RE = re.compile(r"(?i)^(test|example|sample|dummy|none|unknown)$|^x{4,}$|^\d{4,}$")
EMAIL_RE = re.compile(r"(?i)^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")
JP_PREFECTURES = (
    "東京都", "大阪府", "京都府", "北海道",
    "神奈川県", "千葉県", "埼玉県", "愛知県", "兵庫県", "福岡県",
    "静岡県", "茨城県", "広島県", "宮城県", "長野県", "新潟県",
    "富山県", "石川県", "福井県", "山梨県", "岐阜県", "三重県",
    "滋賀県", "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県",
    "山口県", "徳島県", "香川県", "愛媛県", "高知県",
    "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
)
NON_JP_LOCATION_RE = re.compile(
    r"(?i)\b("
    r"united states|usa|new york|ny\s+\d{5}|jackson heights|roosevelt ave|"
    r"california|los angeles|san francisco|taiwan|taipei|hong kong|singapore|"
    r"london|paris|sydney|melbourne"
    r")\b"
)

INTERNAL_REASON_TO_OPERATOR_REASON = {
    "not_a_binary_true_lead": "Skipped because this record is not a qualified ramen or izakaya lead.",
    "outside_v1_category": "Skipped because it is outside ramen or izakaya.",
    "not_in_japan": "Skipped because no Japan shop location is supported.",
    "chain_or_franchise_like_business": "Skipped because it looks like a chain or franchise operator.",
    "chain_or_franchise_infrastructure": "Skipped because it looks like a chain or franchise operator.",
    "already_has_usable_english_solution": "Skipped because the shop already appears to have usable English ordering support.",
    "multilingual_qr_or_ordering_solution_present": "Skipped because the shop already appears to have multilingual ordering support.",
    "no_supported_contact_route": "Add a usable business email or real contact form.",
    "hosted_sample_publish_failed": "Publish the hosted sample before using the contact form route.",
    "no_customer_safe_proof_item": "Add one customer-safe proof item from the shop menu or ordering flow.",
    "saved_preview_or_pitch_contains_blocked_content": "Regenerate the pitch because saved customer copy is not safe.",
    "large_menu_requires_custom_quote": "Review the menu scope and decide whether this needs a custom quote.",
    "restaurant_email_verification_not_promoted": "Promote the verified restaurant email lead before outreach.",
    "restaurant_email_verification_rejected": "Skipped because the restaurant email route was rejected.",
    "restaurant_email_verification_needs_review": "Review the restaurant email verification before outreach.",
    "manual_review_required": "Complete the manual review decision before outreach.",
    "portal_only_without_official_site": "Confirm the restaurant identity beyond a portal listing.",
    "weak_source_coverage": "Confirm the restaurant identity with stronger Japan source evidence.",
    "no_official_site_confirmed": "Confirm whether the shop has an official site or reliable listing.",
    "weak_entity_resolution": "Confirm the restaurant name, address, or phone from another source.",
    "low_source_coverage_score": "Confirm this is the right restaurant before outreach.",
    "production_readiness_regeneration_required": "Regenerate this record through the current production checks.",
}


def apply_operator_state(record: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(record)
    decision = compute_operator_state(updated)
    updated["operator_state"] = decision["operator_state"]
    updated["operator_reason"] = decision["operator_reason"]
    return updated


def compute_operator_state(record: dict[str, Any]) -> dict[str, str]:
    """Return the operator-facing state and one plain-language reason."""
    outreach_status = _normalised(record.get("outreach_status"))
    readiness = _normalised(record.get("launch_readiness_status"))
    reasons = [str(reason) for reason in record.get("launch_readiness_reasons") or [] if str(reason).strip()]

    if outreach_status in DONE_OUTREACH_STATUSES:
        return _decision(OPERATOR_DONE, _done_reason(outreach_status))

    explicit_skip = _explicit_skip_reason(record, readiness, reasons)
    if explicit_skip:
        return _decision(OPERATOR_SKIP, explicit_skip)

    if outreach_status in SKIP_OUTREACH_STATUSES:
        return _decision(OPERATOR_SKIP, _skip_reason_for_outreach_status(outreach_status))

    review_reason = _operator_review_reason(record, readiness, reasons)
    if review_reason:
        return _decision(OPERATOR_REVIEW, review_reason)

    if readiness == READINESS_READY:
        route = _primary_supported_route(record)
        if route == "contact_form":
            return _decision(OPERATOR_READY, "Ready for contact-form outreach review.")
        return _decision(OPERATOR_READY, "Ready for email outreach.")

    return _decision(OPERATOR_REVIEW, "Review this record before outreach.")


def build_contact_policy_evidence(record: dict[str, Any]) -> dict[str, Any]:
    decisions = [_contact_decision(contact) for contact in record.get("contacts") or [] if isinstance(contact, dict)]
    primary = record.get("primary_contact")
    primary_decision = _contact_decision(primary) if isinstance(primary, dict) else {}
    if primary_decision and not any(
        item.get("type") == primary_decision.get("type")
        and str(item.get("value") or "").lower() == str(primary_decision.get("value") or "").lower()
        for item in decisions
    ):
        decisions.append(primary_decision)
    if record.get("email") and not any(
        item.get("type") == "email" and str(item.get("value") or "").lower() == str(record.get("email") or "").strip().lower()
        for item in decisions
    ):
        decisions.append(_contact_decision({
            "type": "email",
            "value": record.get("email"),
            "source": "legacy_record",
            "source_url": record.get("website") or record.get("map_url") or "",
            "actionable": True,
        }))

    usable = [item for item in decisions if item.get("decision") == "usable"]
    return {
        "primary_route": primary_decision or (usable[0] if usable else {}),
        "routes": decisions,
        "usable_route_count": len(usable),
    }


def _operator_review_reason(record: dict[str, Any], readiness: str, reasons: list[str]) -> str:
    contact_block = _contact_policy_block_reason(record)
    if contact_block and contact_block.startswith("review:"):
        return contact_block.removeprefix("review:")

    if business_name_is_suspicious(str(record.get("business_name") or "")):
        return "Fix the restaurant name before outreach."
    if not _has_japan_physical_location_evidence(record):
        return "Confirm this shop has a physical location in Japan."
    if _chain_status(record) == "needs_review":
        return "Confirm this is not a chain or multi-location operator."
    if not _has_package_recommendation(record):
        return "Choose a recommended package before outreach."

    for reason in reasons:
        mapped = _plain_reason_for_internal_reason(reason)
        if mapped:
            return mapped

    if readiness == READINESS_MANUAL:
        return "Complete the manual review decision before outreach."
    if readiness != READINESS_READY:
        return "Review this record before outreach."
    return ""


def _explicit_skip_reason(record: dict[str, Any], readiness: str, reasons: list[str]) -> str:
    if record.get("lead") is not True:
        return "Skipped because this record is not a qualified ramen or izakaya lead."
    if _explicit_non_japan(record):
        return "Skipped because no Japan shop location is supported."
    category = _record_category(record)
    if category not in {"ramen", "izakaya"} or _has_excluded_category_text(record):
        return "Skipped because it is outside ramen or izakaya."
    if _chain_status(record) == "rejected":
        return "Skipped because it looks like a chain or franchise operator."
    if _active_business_status(record) == "closed":
        return "Skipped because the shop appears to be closed."

    contact_block = _contact_policy_block_reason(record)
    if contact_block and contact_block.startswith("skip:"):
        return contact_block.removeprefix("skip:")

    if readiness == READINESS_DISQUALIFIED:
        for reason in reasons:
            mapped = _plain_reason_for_internal_reason(reason)
            if mapped:
                return mapped
        return "Skipped because it does not meet the launch criteria."
    return ""


def _contact_policy_block_reason(record: dict[str, Any]) -> str:
    evidence = record.get("contact_policy_evidence") if isinstance(record.get("contact_policy_evidence"), dict) else {}
    if not evidence:
        evidence = build_contact_policy_evidence(record)
    usable = [item for item in evidence.get("routes") or [] if item.get("decision") == "usable"]
    if usable:
        return ""

    blockers = {str(item.get("reason") or "") for item in evidence.get("routes") or []}
    if "email_sales_or_ad_refusal" in blockers:
        return "skip:Skipped because the listed email route blocks sales or advertising contact."
    if any(reason.startswith("email_placeholder") or reason == "email_invalid" for reason in blockers):
        return "skip:Skipped because the saved email route is a placeholder or invalid."
    if "contact_form_not_real_inquiry" in blockers:
        return "skip:Skipped because the saved contact form is not a real inquiry form."
    if "unsupported_route" in blockers:
        return "review:Add a usable business email or real contact form."
    if not evidence.get("routes"):
        return "review:Add a usable business email or real contact form."
    return "review:Add a usable business email or real contact form."


def _contact_decision(contact: dict[str, Any]) -> dict[str, Any]:
    contact_type = _normalised(contact.get("type"))
    value = str(contact.get("value") or contact.get("href") or "").strip()
    reason = ""
    decision = "reference_only"
    if contact_type == "email":
        reason = _email_unsupported_reason(contact)
        decision = "blocked" if reason else "usable"
    elif contact_type == "contact_form":
        unsupported = str(contact.get("unsupported_reason") or "").strip()
        if unsupported:
            reason = "contact_form_not_real_inquiry"
            decision = "blocked"
        elif contact.get("actionable") is False:
            reason = "contact_form_not_real_inquiry"
            decision = "blocked"
        else:
            decision = "usable"
    elif contact_type:
        reason = "unsupported_route"
    else:
        reason = "missing_route_type"

    return {
        "type": contact_type or "unknown",
        "value": value,
        "source": str(contact.get("source") or ""),
        "source_url": str(contact.get("source_url") or ""),
        "actionable": bool(contact.get("actionable")),
        "decision": decision,
        "reason": reason,
    }


def _email_unsupported_reason(contact: dict[str, Any]) -> str:
    value = str(contact.get("value") or contact.get("href") or "").strip().removeprefix("mailto:")
    lowered = value.lower()
    if not EMAIL_RE.fullmatch(lowered):
        return "email_invalid"
    local, domain = lowered.rsplit("@", 1)
    if "%" in local or "%22" in lowered:
        return "email_placeholder_artifact"
    if domain in PLACEHOLDER_EMAIL_DOMAINS or PLACEHOLDER_EMAIL_LOCAL_RE.fullmatch(local):
        return "email_placeholder"
    haystack = " ".join(
        str(contact.get(key) or "")
        for key in ("label", "source", "source_url", "page_title", "page_text_hint", "unsupported_reason", "failure_reason")
    ).lower()
    if any(token.lower() in haystack for token in EMAIL_REFUSAL_TOKENS):
        return "email_sales_or_ad_refusal"
    return ""


def _plain_reason_for_internal_reason(reason: str) -> str:
    cleaned = str(reason or "").strip()
    if cleaned.startswith("entity_quality:"):
        return "Fix the restaurant name before outreach."
    if cleaned.startswith("stale_copy:"):
        return "Regenerate the pitch with current first-contact copy."
    if cleaned.startswith("placeholder_email:"):
        return "Skipped because the saved email route is a placeholder or invalid."
    if cleaned.startswith("package_rescore:"):
        return "Review the recommended package before generating outreach."
    if cleaned.startswith("recoverable_organic_scope_review:"):
        return "Review the restaurant category and evidence before outreach."
    return INTERNAL_REASON_TO_OPERATOR_REASON.get(cleaned, "")


def _primary_supported_route(record: dict[str, Any]) -> str:
    evidence = record.get("contact_policy_evidence") if isinstance(record.get("contact_policy_evidence"), dict) else {}
    if not evidence:
        evidence = build_contact_policy_evidence(record)
    for item in evidence.get("routes") or []:
        if item.get("decision") == "usable" and item.get("type") in {"email", "contact_form"}:
            return str(item.get("type") or "")
    return ""


def _has_package_recommendation(record: dict[str, Any]) -> bool:
    package_key = str(record.get("recommended_primary_package") or "").strip()
    if package_key == "custom_quote":
        return bool(str(record.get("custom_quote_reason") or "").strip())
    return bool(package_key in PACKAGE_REGISTRY and str(record.get("package_recommendation_reason") or "").strip())


def _record_category(record: dict[str, Any]) -> str:
    stored = _normalised(record.get("primary_category_v1") or record.get("category"))
    if stored in {"ramen", "izakaya"}:
        return stored
    text = _record_text(record).lower()
    if "居酒屋" in text or "izakaya" in text:
        return "izakaya"
    if "ラーメン" in text or "らーめん" in text or "ramen" in text:
        return "ramen"
    return stored or "other"


def _has_excluded_category_text(record: dict[str, Any]) -> bool:
    text = " ".join([
        str(record.get("category") or ""),
        str(record.get("primary_category_v1") or ""),
        str(record.get("business_name") or ""),
    ]).lower()
    return any(token.lower() in text for token in EXCLUDED_BUSINESS_TOKENS)


def _chain_status(record: dict[str, Any]) -> str:
    status = _normalised(record.get("chain_verification_status"))
    if status in {"rejected", "reject", "chain_rejected"}:
        return "rejected"
    if status in {"needs_review", "review"}:
        return "needs_review"
    if any(reason in set(record.get("launch_readiness_reasons") or []) for reason in ("chain_or_franchise_like_business", "chain_or_franchise_infrastructure")):
        return "rejected"
    return ""


def _active_business_status(record: dict[str, Any]) -> str:
    haystack = " ".join([
        str(record.get("business_status") or ""),
        str(record.get("active_business_status") or ""),
        str(record.get("verification_reason") or ""),
        " ".join(str(item) for item in record.get("evidence_snippets") or []),
    ]).lower()
    if any(token in haystack for token in ("permanently_closed", "closed_permanently", "閉店", "閉業", "営業終了")):
        return "closed"
    return ""


def _has_japan_physical_location_evidence(record: dict[str, Any]) -> bool:
    if _explicit_non_japan(record):
        return False
    text = " ".join([
        str(record.get("address") or ""),
        str(record.get("phone") or ""),
        str(record.get("map_url") or ""),
        str(record.get("city") or ""),
        " ".join(str(url) for url in record.get("evidence_urls") or []),
    ])
    if not text.strip():
        return False
    if "Japan" in text or "日本" in text or "〒" in text:
        return True
    if any(pref in text for pref in JP_PREFECTURES):
        return True
    if any(str(area).lower() in text.lower() for area in JP_AREAS):
        return True
    if re.search(r"(?:\+81[-\s]?|^0)[1-9]\d{0,3}[-\s]?\d{1,4}", text):
        return True
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff].{0,16}(?:区|市|町|村)", text):
        return True
    if any(host in text.lower() for host in ("tabelog.com", "hotpepper.jp", "ramendb.supleks.jp")):
        return True
    return False


def _explicit_non_japan(record: dict[str, Any]) -> bool:
    text = " ".join([
        str(record.get("address") or ""),
        str(record.get("phone") or ""),
        str(record.get("map_url") or ""),
    ])
    if not text.strip():
        return False
    if _has_japan_physical_location_evidence_text(text):
        return False
    return bool(NON_JP_LOCATION_RE.search(text))


def _has_japan_physical_location_evidence_text(text: str) -> bool:
    if "Japan" in text or "日本" in text or "〒" in text:
        return True
    if any(pref in text for pref in JP_PREFECTURES):
        return True
    if re.search(r"(?:\+81[-\s]?|^0)[1-9]\d{0,3}[-\s]?\d{1,4}", text):
        return True
    return False


def _record_text(record: dict[str, Any]) -> str:
    fields = [
        str(record.get("business_name") or ""),
        str(record.get("category") or ""),
        str(record.get("primary_category_v1") or ""),
        " ".join(str(item) for item in record.get("evidence_snippets") or []),
        " ".join(str(item) for item in record.get("evidence_classes") or []),
    ]
    return " ".join(fields)


def _done_reason(outreach_status: str) -> str:
    if outreach_status == "sent":
        return "Done because the first outreach was sent."
    if outreach_status == "contacted_form":
        return "Done because the contact form outreach was recorded."
    if outreach_status == "replied":
        return "Done because the shop replied."
    if outreach_status == "converted":
        return "Done because the shop converted."
    if outreach_status in {"bounced", "invalid"}:
        return "Done because the contact route bounced or became invalid."
    if outreach_status == "unsubscribed":
        return "Done because the shop unsubscribed."
    if outreach_status == "closed":
        return "Done because the opportunity was closed."
    return "Done because this record has a terminal outcome."


def _skip_reason_for_outreach_status(outreach_status: str) -> str:
    if outreach_status == "do_not_contact":
        return "Skipped because this shop is marked do not contact."
    if outreach_status == "rejected":
        return "Skipped because this record was rejected in review."
    return "Skipped because this record is not an outreach candidate."


def _decision(state: str, reason: str) -> dict[str, str]:
    return {"operator_state": state, "operator_reason": reason or "Review this record before outreach."}


def _normalised(value: Any) -> str:
    return str(value or "").strip().lower()
