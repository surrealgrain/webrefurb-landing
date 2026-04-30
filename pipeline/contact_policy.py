from __future__ import annotations

from copy import deepcopy
from typing import Any
import urllib.parse


SUPPORTED_OUTREACH_CONTACT_TYPES = {"email", "contact_form"}
POLICY_UNSUPPORTED_REASONS = {
    "phone_required",
    "unverified_contact_form",
    "reservation_or_booking_form",
    "recruiting_form",
    "commerce_or_order_form",
    "newsletter_form",
    "hidden_only_form",
    "account_or_login_form",
    "social_profile_not_contact_form",
}
OMITTED_ROUTE_TYPES = {"phone", "line", "instagram"}
OMITTED_UNSUPPORTED_FORM_REASONS = {
    "phone_required",
    "reservation_or_booking_form",
    "recruiting_form",
    "commerce_or_order_form",
    "newsletter_form",
    "hidden_only_form",
    "account_or_login_form",
    "social_profile_not_contact_form",
}

PHONE_REQUIRED_TOKENS = (
    "phone_required",
    "requires_phone",
)
RESERVATION_FORM_TOKENS = (
    "reservation",
    "reserve",
    "booking",
    "book-a-table",
    "tablecheck",
    "yoyaku",
    "予約",
    "ご予約",
    "空席",
)
RECRUIT_FORM_TOKENS = (
    "recruit",
    "career",
    "careers",
    "job",
    "jobs",
    "採用",
    "求人",
    "応募",
)
COMMERCE_FORM_TOKENS = (
    "checkout",
    "cart",
    "order-form",
    "takeout",
    "take-out",
    "delivery",
    "ec-order",
    "購入",
    "注文",
    "テイクアウト",
    "デリバリー",
)
ACCOUNT_FORM_TOKENS = (
    "login",
    "log-in",
    "signin",
    "sign-in",
    "signup",
    "sign-up",
    "account",
    "会員登録",
    "ログイン",
)
SOCIAL_ROUTE_TOKENS = (
    "instagram.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "line.me",
    "lin.ee",
)
CONTACT_ROUTE_TOKENS = (
    "contact",
    "inquiry",
    "otoiawase",
    "toiawase",
    "お問い合わせ",
    "問合せ",
)


def contact_form_unsupported_reason(contact: dict[str, Any], *, sender_phone_available: bool = False) -> str:
    """Return why a contact form cannot be used for outreach, or empty string."""
    if str(contact.get("type") or "").strip().lower() != "contact_form":
        return ""
    if _contact_has_social_host(contact):
        return "social_profile_not_contact_form"
    profile = str(contact.get("contact_form_profile") or "").strip().lower()
    if profile == "hidden_only":
        return "hidden_only_form"
    if profile == "reservation_only":
        return "reservation_or_booking_form"
    if profile == "phone_required" and not sender_phone_available:
        return "phone_required"
    if profile == "newsletter":
        return "newsletter_form"
    if profile == "commerce":
        return "commerce_or_order_form"
    if profile == "recruiting":
        return "recruiting_form"
    if profile == "unknown":
        return "unverified_contact_form"
    if not _contact_form_has_verified_form(contact):
        return "unverified_contact_form"
    if _contact_form_requires_phone(contact) and not sender_phone_available:
        return "phone_required"

    route_haystack = _contact_route_haystack(contact)
    if _contains_any(route_haystack, RESERVATION_FORM_TOKENS):
        return "reservation_or_booking_form"
    if _contains_any(route_haystack, RECRUIT_FORM_TOKENS):
        return "recruiting_form"
    if _contains_any(route_haystack, COMMERCE_FORM_TOKENS):
        return "commerce_or_order_form"
    if _contains_any(route_haystack, ACCOUNT_FORM_TOKENS):
        return "account_or_login_form"
    return ""


def _contact_form_has_verified_form(contact: dict[str, Any]) -> bool:
    profile = str(contact.get("contact_form_profile") or "").strip().lower()
    if profile == "supported_inquiry":
        return True
    if profile in {"hidden_only", "reservation_only", "phone_required", "newsletter", "commerce", "recruiting", "unknown"}:
        return False
    if contact.get("has_form") is True:
        return True
    for key in ("required_fields", "form_actions", "form_field_names"):
        value = contact.get(key)
        if isinstance(value, list) and value:
            return True
        if isinstance(value, str) and value.strip():
            return True
    route_haystack = _contact_route_haystack(contact)
    if _contains_any(route_haystack, CONTACT_ROUTE_TOKENS):
        return True
    return False


def contact_is_supported_for_outreach(contact: dict[str, Any], *, sender_phone_available: bool = False) -> bool:
    contact_type = str(contact.get("type") or "").strip().lower()
    if contact_type not in SUPPORTED_OUTREACH_CONTACT_TYPES:
        return False
    if contact_type == "contact_form" and contact_form_unsupported_reason(
        contact,
        sender_phone_available=sender_phone_available,
    ):
        return False
    return bool(contact.get("actionable"))


def normalise_contact_actionability(
    contact: dict[str, Any],
    *,
    sender_phone_available: bool = False,
) -> dict[str, Any]:
    """Apply outreach route policy to one contact record without losing metadata."""
    updated = deepcopy(contact)
    contact_type = str(updated.get("type") or "").strip().lower()
    unsupported_reason = ""
    if contact_type not in SUPPORTED_OUTREACH_CONTACT_TYPES:
        unsupported_reason = f"unsupported_route:{contact_type or 'unknown'}"
    elif contact_type == "contact_form":
        unsupported_reason = contact_form_unsupported_reason(
            updated,
            sender_phone_available=sender_phone_available,
        )

    if unsupported_reason:
        updated["actionable"] = False
        updated["unsupported_reason"] = unsupported_reason
        if not str(updated.get("status") or "").strip() or updated.get("status") == "discovered":
            updated["status"] = "reference_only"
    elif str(updated.get("unsupported_reason") or "") in POLICY_UNSUPPORTED_REASONS:
        updated.pop("unsupported_reason", None)
        updated["actionable"] = True
        if updated.get("status") == "reference_only":
            updated["status"] = "discovered"
    elif "actionable" not in updated:
        updated["actionable"] = True
    return updated


def contact_should_be_omitted_from_routes(
    contact: dict[str, Any],
    *,
    sender_phone_available: bool = False,
) -> bool:
    """Return True for route records the product should not surface at all."""
    contact_type = str(contact.get("type") or "").strip().lower()
    if contact_type in OMITTED_ROUTE_TYPES:
        return True
    if contact_type == "contact_form":
        reason = contact_form_unsupported_reason(contact, sender_phone_available=sender_phone_available)
        return reason in OMITTED_UNSUPPORTED_FORM_REASONS
    return False


def _contact_form_requires_phone(contact: dict[str, Any]) -> bool:
    if any(contact.get(key) is True for key in ("requires_phone", "phone_required", "requires_phone_number")):
        return True
    if _required_field_requires_phone(contact):
        return True
    return _contains_any(_explicit_phone_required_haystack(contact), PHONE_REQUIRED_TOKENS)


def _explicit_phone_required_haystack(contact: dict[str, Any]) -> str:
    return " ".join(str(contact.get(key) or "") for key in (
        "requires_phone",
        "phone_required",
        "requires_phone_number",
        "unsupported_reason",
        "failure_reason",
    )).lower()


def _required_field_requires_phone(contact: dict[str, Any]) -> bool:
    fields: list[str] = []
    for key in ("required_fields", "form_field_names"):
        value = contact.get(key)
        if isinstance(value, list):
            fields.extend(str(item or "").strip().lower() for item in value)
        else:
            fields.append(str(value or "").strip().lower())
    return any(
        field in {"tel", "telephone", "phone", "phone_number", "phone-number", "電話", "電話番号"}
        or "phone" in field
        or "電話" in field
        for field in fields
        if field
    )


def _contact_haystack(contact: dict[str, Any]) -> str:
    fields: list[str] = []
    for key in (
        "value",
        "href",
        "label",
        "source",
        "source_url",
        "failure_reason",
        "unsupported_reason",
        "page_title",
        "page_text_hint",
        "contact_form_profile",
    ):
        fields.append(str(contact.get(key) or ""))
    for key in ("required_fields", "form_actions", "form_field_names"):
        value = contact.get(key)
        if isinstance(value, list):
            fields.extend(str(item or "") for item in value)
        else:
            fields.append(str(value or ""))
    return " ".join(fields).lower()


def _contact_route_haystack(contact: dict[str, Any]) -> str:
    fields: list[str] = []
    for key in ("value", "href", "source_url"):
        fields.append(_url_route_text(str(contact.get(key) or "")))
    for key in ("label", "form_actions", "page_title", "page_text_hint"):
        value = contact.get(key)
        if isinstance(value, list):
            fields.extend(_url_route_text(str(item or "")) for item in value)
        else:
            fields.append(_url_route_text(str(value or "")))
    return " ".join(fields).lower()


def _url_route_text(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme and parsed.netloc:
        return " ".join([parsed.path, parsed.params, parsed.query, parsed.fragment])
    return cleaned


def _contact_has_social_host(contact: dict[str, Any]) -> bool:
    for key in ("value", "href", "source_url"):
        parsed = urllib.parse.urlparse(str(contact.get(key) or ""))
        host = parsed.netloc.lower()
        if any(token in host for token in SOCIAL_ROUTE_TOKENS):
            return True
    return False


def _contains_any(haystack: str, tokens: tuple[str, ...]) -> bool:
    return any(token.lower() in haystack for token in tokens)
