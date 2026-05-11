"""Lead quality helpers used by audits, dashboard summaries, and tests."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from .constants import ACTIVE_LEAD_CATEGORIES, ENGLISH_QR_MENU_KEY
from .contact_policy import contact_is_supported_for_outreach, normalise_contact_actionability


STALE_LEAD_DAYS = 45


def lead_quality_summary(record: dict[str, Any], *, now: str | None = None) -> dict[str, Any]:
    """Return internal lead quality signals without changing the record."""
    category = str(record.get("category") or record.get("primary_category_v1") or "").strip().lower()
    contacts = [normalise_contact_actionability(contact) for contact in record.get("contacts") or [] if isinstance(contact, dict)]
    actionable_contacts = [contact for contact in contacts if contact_is_supported_for_outreach(contact)]
    positives: list[str] = []
    negatives: list[str] = []
    missing: list[str] = []
    if category in {"ramen", "izakaya"}:
        positives.append(f"active_category:{category}")
    elif category == "skip":
        negatives.append("skip_category")
    elif category:
        negatives.append(f"unsupported_category:{category}")
    else:
        missing.append("category")
    if record.get("recommended_primary_package") == ENGLISH_QR_MENU_KEY:
        positives.append("active_product")
    else:
        negatives.append("active_product_missing")
    if actionable_contacts:
        positives.append("approved_contact_route")
    else:
        missing.append("approved_contact_route")
    if lead_is_stale(record, now=now):
        negatives.append("stale_lead_requires_reverification")
    return {
        "supported": category in ACTIVE_LEAD_CATEGORIES and category != "skip",
        "duplicate_key": duplicate_key(record),
        "stale": lead_is_stale(record, now=now),
        "positive_signals": positives,
        "negative_signals": negatives,
        "missing_data": missing,
        "actionable_contact_count": len(actionable_contacts),
    }


def duplicate_key(record: dict[str, Any]) -> str:
    """Build a stable duplicate key from domain/email/name signals."""
    email = str(record.get("email") or "").strip().lower()
    if email and "@" in email:
        return f"email:{email}"
    for contact in record.get("contacts") or []:
        if not isinstance(contact, dict):
            continue
        if str(contact.get("type") or "").lower() == "email":
            value = str(contact.get("value") or "").strip().lower()
            if value and "@" in value:
                return f"email:{value}"
    domain = _domain_from_record(record)
    if domain:
        return f"domain:{domain}"
    name = normalise_business_name_key(str(record.get("business_name") or record.get("name") or ""))
    city = normalise_business_name_key(str(record.get("city") or record.get("area") or ""))
    return f"name:{city}:{name}" if name else ""


def normalise_business_name_key(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[（）()［］\\[\\]【】]", " ", value)
    value = re.sub(r"\b(branch|shop|store|ten|honten|main store)\b", " ", value)
    value = re.sub(r"(本店|支店|店|店舗)$", "", value)
    value = re.sub(r"[^0-9a-zぁ-んァ-ン一-龥ー]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-")


def lead_is_stale(record: dict[str, Any], *, now: str | None = None, max_age_days: int = STALE_LEAD_DAYS) -> bool:
    stamp = str(record.get("verified_at") or record.get("updated_at") or record.get("created_at") or "")
    if not stamp:
        return True
    try:
        value = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        current = datetime.fromisoformat((now or datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00"))
    except ValueError:
        return True
    return current - value > timedelta(days=max_age_days)


def _domain_from_record(record: dict[str, Any]) -> str:
    for key in ("website", "url", "source_url", "contact_url"):
        domain = _domain(str(record.get(key) or ""))
        if domain:
            return domain
    for contact in record.get("contacts") or []:
        if not isinstance(contact, dict):
            continue
        domain = _domain(str(contact.get("value") or contact.get("href") or contact.get("source_url") or ""))
        if domain:
            return domain
    return ""


def _domain(value: str) -> str:
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    parsed = urlparse(value)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host
