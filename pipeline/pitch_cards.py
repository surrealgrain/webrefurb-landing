from __future__ import annotations

import re
from collections import Counter
from typing import Any


PITCH_CARD_REVIEWABLE = "reviewable"
PITCH_CARD_NEEDS_EMAIL_REVIEW = "needs_email_review"
PITCH_CARD_NEEDS_NAME_REVIEW = "needs_name_review"
PITCH_CARD_NEEDS_SCOPE_REVIEW = "needs_scope_review"
PITCH_CARD_HARD_BLOCKED = "hard_blocked"
PITCH_CARD_UNSUPPORTED_ROUTE = "unsupported_route"

OPENABLE_PITCH_CARD_STATUSES = {
    PITCH_CARD_REVIEWABLE,
    PITCH_CARD_NEEDS_EMAIL_REVIEW,
    PITCH_CARD_NEEDS_NAME_REVIEW,
    PITCH_CARD_NEEDS_SCOPE_REVIEW,
}

PITCH_CARD_STATUS_LABELS = {
    PITCH_CARD_REVIEWABLE: "Reviewable",
    PITCH_CARD_NEEDS_EMAIL_REVIEW: "Needs Email Review",
    PITCH_CARD_NEEDS_NAME_REVIEW: "Needs Name Review",
    PITCH_CARD_NEEDS_SCOPE_REVIEW: "Needs Scope Review",
    PITCH_CARD_HARD_BLOCKED: "Hard Blocked",
    PITCH_CARD_UNSUPPORTED_ROUTE: "Unsupported Route",
}

_TERMINAL_UNSENDABLE_STATUSES = {"do_not_contact", "invalid", "rejected"}
_SUPPORTED_ROUTE_TYPES = {"email", "contact_form"}

_EMAIL_ARTIFACT_TOKENS = (
    "invalid",
    "artifact",
    "blocked",
    "placeholder",
    "institutional",
    "not a usable business email",
    "missing direct email",
)
_NAME_ARTIFACT_TOKENS = (
    "contact-derived",
    "unsafe",
    "malformed",
    "malformed extraction artifact",
)
_SCOPE_HARD_TOKENS = (
    "manually rejected",
    "sushi",
    "yakiniku",
    "kaiseki",
    "cafe",
)
_ENGLISH_SOLVED_TOKENS = (
    "english-menu hard reject",
    "already_has_good_english_menu",
    "already has good english",
    "already_has_multilingual_ordering_solution",
    "multilingual",
    "clear usable",
)
_CHAIN_TOKENS = (
    "chain",
    "franchise",
    "multi-branch",
    "multi-location",
    "operator",
)
_OPPORTUNISTIC_BAD_EMAIL_TOKENS = (
    "xxx",
    "example",
    "domain.com",
    "sample.com",
    "000000",
    "firebase-adminsdk",
    "sentry",
    "wixpress",
    "gamil.com",
    "itsari.aleise",
    "oostende.cultuurstad",
)
_OPPORTUNISTIC_DIRECTORY_TITLE_TOKENS = (
    "おすすめ",
    "ランキング",
    "まとめ",
    "店舗紹介",
    "一覧",
    "20選",
    "ベスト",
    "特集",
    "完全ガイド",
    "県民が選んだ",
    "食べログ",
    "ぐるなび",
    "ホットペッパー",
)
_OPPORTUNISTIC_DIRECTORY_HOST_TOKENS = (
    "timeout.jp",
    "crossroadfukuoka.jp",
    "hamoni.jp",
    "macaro-ni.jp",
    "retty.me",
    "youtube.com",
    "youtu.be",
    "prtimes.jp",
    "value-press.com",
    "ameblo.jp",
    "news.infoseek.co.jp",
)
_OPPORTUNISTIC_WRONG_CATEGORY_NAME_TOKENS = (
    "551",
    "蓬莱",
    "寿司",
    "寿し",
    "鮨",
    "焼肉",
    "ホルモン",
    "牛タン",
    "ビストロ",
    "ラウンジ",
    "肉屋",
    "天然牧草牛",
)


def apply_pitch_card_state(record: dict[str, Any]) -> dict[str, Any]:
    """Attach the no-send dashboard pitch-card state to a lead record."""
    status, reasons = assess_pitch_card_state(record)
    record["pitch_card_status"] = status
    record["pitch_card_reasons"] = reasons
    record["pitch_card_openable"] = status in OPENABLE_PITCH_CARD_STATUSES
    record["pitch_card_label"] = PITCH_CARD_STATUS_LABELS.get(status, status.replace("_", " ").title())
    record["opportunistic_pitch_candidate"] = is_opportunistic_pitch_candidate(record)
    return record


def assess_pitch_card_state(record: dict[str, Any]) -> tuple[str, list[str]]:
    """Classify a record for no-send dashboard pitch review.

    This is intentionally separate from launch readiness. A lead can be
    pitch-card-openable while still manual-review blocked and unsendable.
    """
    reasons: list[str] = []

    if record.get("lead") is not True:
        return PITCH_CARD_HARD_BLOCKED, ["record is not a binary lead"]

    if str(record.get("operator_review_outcome") or "") == "reject" or str(record.get("review_status") or "") == "rejected":
        return PITCH_CARD_HARD_BLOCKED, ["operator rejected during manual review"]

    outreach_status = str(record.get("outreach_status") or "").strip()
    if outreach_status in _TERMINAL_UNSENDABLE_STATUSES:
        return PITCH_CARD_HARD_BLOCKED, [f"terminal outreach status: {outreach_status}"]

    hard_reasons = _hard_block_reasons(record)
    if hard_reasons:
        return PITCH_CARD_HARD_BLOCKED, hard_reasons

    if not _has_supported_route(record):
        return PITCH_CARD_UNSUPPORTED_ROUTE, ["no supported email or contact-form route"]

    has_email_route = _has_email_route(record)
    email_status = str(record.get("email_verification_status") or "").strip()
    email_reason = str(record.get("email_verification_reason") or "").strip()
    if has_email_route and email_status in {"", "needs_review"}:
        reasons.append(email_reason or "email needs review")
        return PITCH_CARD_NEEDS_EMAIL_REVIEW, _compact(reasons)

    name_status = str(record.get("name_verification_status") or "").strip()
    name_reason = str(record.get("name_verification_reason") or "").strip()
    if name_status in {"", "single_source", "needs_review", "rejected"}:
        reasons.append(name_reason or "business name needs review")
        return PITCH_CARD_NEEDS_NAME_REVIEW, _compact(reasons)

    if _needs_scope_review(record):
        return PITCH_CARD_NEEDS_SCOPE_REVIEW, _scope_review_reasons(record)

    if str(record.get("pitch_readiness_status") or "") == "needs_scope_review":
        return PITCH_CARD_NEEDS_SCOPE_REVIEW, _compact(record.get("pitch_readiness_reasons") or ["scope needs review"])

    return PITCH_CARD_REVIEWABLE, ["supported route and no hard pitch-card block"]


def pitch_card_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str((record.get("pitch_card_status") or assess_pitch_card_state(record)[0])) for record in records)
    openable = sum(counts[status] for status in OPENABLE_PITCH_CARD_STATUSES)
    return {
        "reviewable_pitch_cards": openable,
        "opportunistic_pitch_candidates": sum(1 for record in records if is_opportunistic_pitch_candidate(record)),
        "needs_review": counts[PITCH_CARD_NEEDS_EMAIL_REVIEW] + counts[PITCH_CARD_NEEDS_NAME_REVIEW] + counts[PITCH_CARD_NEEDS_SCOPE_REVIEW],
        "hard_blocked": counts[PITCH_CARD_HARD_BLOCKED],
        "unsupported_route": counts[PITCH_CARD_UNSUPPORTED_ROUTE],
        "ready_for_outreach": sum(1 for record in records if record.get("launch_readiness_status") == "ready_for_outreach"),
        **dict(counts),
    }


def is_pitch_card_openable(record: dict[str, Any]) -> bool:
    status = str(record.get("pitch_card_status") or assess_pitch_card_state(record)[0])
    return status in OPENABLE_PITCH_CARD_STATUSES


def is_opportunistic_pitch_candidate(record: dict[str, Any]) -> bool:
    """Lower-friction volume lane for no-send pitch prep.

    This deliberately ignores unknown English-menu status, weak source coverage,
    and missing proof snippets. It only removes records that are bad targets or
    unsafe to contact.
    """
    if record.get("lead") is not True:
        return False
    if str(record.get("outreach_status") or "").strip() in _TERMINAL_UNSENDABLE_STATUSES:
        return False
    if _hard_block_reasons(record):
        return False
    category = str(record.get("primary_category_v1") or record.get("category") or record.get("type_of_restaurant") or "").strip()
    if category not in {"ramen", "izakaya"}:
        return False
    if not _has_supported_route(record):
        return False
    if _has_bad_opportunistic_email(record):
        return False
    if _looks_like_directory_title(record):
        return False
    if _looks_like_wrong_category_name(record):
        return False
    if _looks_like_chain_or_unsafe_name(record):
        return False
    return True


def _hard_block_reasons(record: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    rejection_reason = str(record.get("rejection_reason") or "")
    verification_reason = str(record.get("verification_reason") or "")

    chain_reason = " ".join([rejection_reason, verification_reason]).lower()
    if str(record.get("chain_verification_status") or "") == "rejected" or _contains_any(chain_reason, _CHAIN_TOKENS):
        reasons.append(str(record.get("chain_verification_reason") or "chain/operator hard block"))

    category_reason = " ".join([
        str(record.get("category_verification_reason") or ""),
        rejection_reason,
        verification_reason,
    ]).lower()
    if (
        str(record.get("category_verification_status") or "") == "rejected"
        and _contains_any(category_reason, _SCOPE_HARD_TOKENS)
    ):
        reasons.append(str(record.get("category_verification_reason") or "outside ramen/izakaya scope"))

    english_reason = " ".join([
        str(record.get("english_menu_check_reason") or ""),
        rejection_reason,
        verification_reason,
        str(record.get("english_availability") or ""),
    ]).lower()
    if str(record.get("english_menu_check_status") or "") == "rejected" or _contains_any(english_reason, _ENGLISH_SOLVED_TOKENS):
        reasons.append(str(record.get("english_menu_check_reason") or "confirmed English/multilingual solution"))

    email_reason = str(record.get("email_verification_reason") or "").lower()
    if str(record.get("email_verification_status") or "") == "rejected" and _contains_any(email_reason, _EMAIL_ARTIFACT_TOKENS):
        reasons.append(str(record.get("email_verification_reason") or "invalid email artifact"))

    name_reason = str(record.get("name_verification_reason") or "").lower()
    if str(record.get("name_verification_status") or "") == "rejected" and _contains_any(name_reason, _NAME_ARTIFACT_TOKENS):
        reasons.append(str(record.get("name_verification_reason") or "unsafe business name"))

    if record.get("manual_review_required") is True and str(record.get("inventory_review_reason") or "").lower() in {"hard_blocked", "invalid_email_artifact"}:
        reasons.append(str(record.get("inventory_review_reason")))

    return _compact(reasons)


def _needs_scope_review(record: dict[str, Any]) -> bool:
    if str(record.get("city_verification_status") or "") == "needs_review":
        return True
    if str(record.get("category_verification_status") or "") in {"needs_review", "rejected"}:
        return True
    if str(record.get("chain_verification_status") or "") == "needs_review":
        return True
    if str(record.get("source_strength") or "") in {"directory", "weak_source"}:
        return True
    if str(record.get("primary_category_v1") or record.get("category") or "") in {"", "other", "restaurant", "general_japanese_review"}:
        return True
    return False


def _scope_review_reasons(record: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field in (
        "city_verification_reason",
        "category_verification_reason",
        "chain_verification_reason",
        "source_strength_reason",
    ):
        value = str(record.get(field) or "").strip()
        if value:
            reasons.append(value)
    if not reasons:
        reasons.append("scope needs review")
    return _compact(reasons)


def _has_supported_route(record: dict[str, Any]) -> bool:
    if _has_email_route(record):
        return True
    for contact in record.get("contacts") or []:
        if not isinstance(contact, dict):
            continue
        contact_type = str(contact.get("type") or "").strip()
        if contact_type != "contact_form":
            continue
        if contact.get("actionable") is False:
            continue
        return True
    return False


def _has_email_route(record: dict[str, Any]) -> bool:
    email = str(record.get("email") or "").strip()
    if email and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return True
    for contact in record.get("contacts") or []:
        if not isinstance(contact, dict):
            continue
        contact_type = str(contact.get("type") or "").strip()
        if contact_type != "email" or contact.get("actionable") is False:
            continue
        value = str(contact.get("value") or "").strip()
        if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            return True
    return False


def _has_bad_opportunistic_email(record: dict[str, Any]) -> bool:
    emails: list[str] = []
    if record.get("email"):
        emails.append(str(record.get("email") or "").strip().lower())
    for contact in record.get("contacts") or []:
        if not isinstance(contact, dict) or str(contact.get("type") or "") != "email":
            continue
        emails.append(str(contact.get("value") or "").strip().lower())
    if not emails:
        return False
    return all(any(token in email for token in _OPPORTUNISTIC_BAD_EMAIL_TOKENS) for email in emails)


def _looks_like_directory_title(record: dict[str, Any]) -> bool:
    name = str(record.get("business_name") or "")
    website = str(record.get("website") or "").lower()
    return (
        any(token in name for token in _OPPORTUNISTIC_DIRECTORY_TITLE_TOKENS)
        or any(token in website for token in _OPPORTUNISTIC_DIRECTORY_HOST_TOKENS)
    )


def _looks_like_chain_or_unsafe_name(record: dict[str, Any]) -> bool:
    name = str(record.get("business_name") or "")
    try:
        from .business_name import business_name_is_suspicious
        from .evidence import has_chain_or_franchise_infrastructure, is_chain_business
    except Exception:
        return False
    if business_name_is_suspicious(name) or is_chain_business(name):
        return True
    return has_chain_or_franchise_infrastructure(" ".join([
        name,
        str(record.get("website") or ""),
        " ".join(str(item or "") for item in record.get("evidence_snippets") or []),
    ]))


def _looks_like_wrong_category_name(record: dict[str, Any]) -> bool:
    name = str(record.get("business_name") or "")
    return any(token in name for token in _OPPORTUNISTIC_WRONG_CATEGORY_NAME_TOKENS)


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in tokens)


def _compact(values: Any) -> list[str]:
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result[:4]
