"""Classify discovered emails by type.

Categories:
  - general_business_contact  → info@, shop@, contact@, etc.
  - operator_company_contact  → found on company page, not shop page
  - online_shop_contact       → found on 特商法/online-shop pages
  - media_pr_contact          → press/media specific
  - recruitment_contact       → recruiting-specific
  - reservation_contact       → reservation-only
  - personal_or_unclear       → looks personal (gmail, etc.) or ambiguous
  - low_confidence            → found in low-signal context
  - do_not_contact            → explicitly flagged or in DNC context
"""

from __future__ import annotations

import re
from .models import EmailType
from .email_extractor import ExtractedEmail

# ---------------------------------------------------------------------------
# Local-part classification heuristics
# ---------------------------------------------------------------------------

# Strong business signals
_BUSINESS_LOCALS = {
    "info", "contact", "mail", "email", "shop", "store",
    "cs", "support", "customer", "service", "office",
    "sales", "webmaster", "admin",
}

# Operator/company signals
_COMPANY_LOCALS = {
    "info", "contact", "office", "admin", "sales",
    "business", "corporate", "corp", "hq",
}

# PR/media signals
_PR_LOCALS = {
    "press", "media", "pr", "publicity", "interview",
    "取材", "報道",
}

# Recruitment signals
_RECRUIT_LOCALS = {
    "recruit", "recruitment", "hr", "career", "careers",
    "job", "jobs", "employ", "saiyo", "採用", "求人",
}

# Reservation signals
_RESERVATION_LOCALS = {
    "reserve", "reservation", "booking", "yoyaku", "予約",
}

# Personal-email domains
_PERSONAL_DOMAINS = {
    "gmail.com", "yahoo.co.jp", "yahoo.com", "hotmail.com",
    "outlook.jp", "outlook.com", "icloud.com", "docomo.ne.jp",
    "softbank.ne.jp", "ezweb.ne.jp", "au.com",
    "i.softbank.jp", "y-mobile.ne.jp",
}

# Page-type signals (from source_page_type)
_BUSINESS_PAGE_TYPES = {"contact", "company", "about", "tokushoho", "online_shop"}
_PR_PAGE_TYPES = {"pr", "press", "media"}
_RECRUIT_PAGE_TYPES = {"recruitment", "job", "career"}
_RESERVATION_PAGE_TYPES = {"reservation", "booking"}


def classify_email(
    extracted: ExtractedEmail,
    source_page_type: str = "",
    source_snippet: str = "",
) -> EmailType:
    """Classify a single extracted email.

    Args:
        extracted: The extracted email with context.
        source_page_type: Type of page where found (contact, tokushoho, etc.).
        source_snippet: Surrounding text on the page.

    Returns:
        The most specific EmailType for this email.
    """
    email = extracted.email.lower()
    local = email.split("@")[0]
    domain = email.split("@")[-1]

    # Check for personal domains
    is_personal_domain = domain in _PERSONAL_DOMAINS

    # Check source page type first (strongest signal)
    if source_page_type in _RECRUIT_PAGE_TYPES:
        if local in _RECRUIT_LOCALS:
            return EmailType.RECRUITMENT
        # If it's a general address on a recruitment page, still flag it
        if local in _BUSINESS_LOCALS and not is_personal_domain:
            return EmailType.RECRUITMENT

    if source_page_type in _RESERVATION_PAGE_TYPES:
        if local in _RESERVATION_LOCALS:
            return EmailType.RESERVATION
        # General address on reservation page — could be OK
        if local in _BUSINESS_LOCALS:
            return EmailType.LOW_CONFIDENCE

    if source_page_type in _PR_PAGE_TYPES:
        if local in _PR_LOCALS or local in _BUSINESS_LOCALS:
            return EmailType.MEDIA_PR

    # Online-shop / 特商法 page
    if source_page_type in ("tokushoho", "online_shop"):
        if local in _BUSINESS_LOCALS:
            return EmailType.ONLINE_SHOP
        if is_personal_domain:
            return EmailType.LOW_CONFIDENCE
        return EmailType.ONLINE_SHOP

    # Company page
    if source_page_type in ("company", "operator"):
        if local in _COMPANY_LOCALS:
            return EmailType.OPERATOR_COMPANY
        if is_personal_domain:
            return EmailType.LOW_CONFIDENCE
        return EmailType.OPERATOR_COMPANY

    # Check snippet for context clues
    snippet_lower = (source_snippet or "").lower()
    if any(kw in snippet_lower for kw in ("採用", "求人", "recruit", "career")):
        return EmailType.RECRUITMENT
    if any(kw in snippet_lower for kw in ("予約", "reserve", "booking")):
        return EmailType.RESERVATION

    # Check local part heuristics
    if local in _BUSINESS_LOCALS:
        if source_page_type in _BUSINESS_PAGE_TYPES:
            return EmailType.GENERAL_BUSINESS
        return EmailType.GENERAL_BUSINESS

    if local in _PR_LOCALS:
        return EmailType.MEDIA_PR

    # Personal domain → personal or unclear
    if is_personal_domain:
        # Could be a small owner-operated shop using personal email
        if source_page_type in ("contact", "tokushoho"):
            return EmailType.LOW_CONFIDENCE
        return EmailType.PERSONAL_OR_UNCLEAR

    # Domain matches a known business domain (not personal)
    # but local part is unusual → unclear
    return EmailType.LOW_CONFIDENCE


def rank_emails(
    emails: list[tuple[ExtractedEmail, EmailType]],
) -> list[tuple[ExtractedEmail, EmailType]]:
    """Rank emails by outreach priority.

    Best first: general_business > operator > online_shop > media_pr >
                recruitment > reservation > personal > low_confidence
    """
    priority = {
        EmailType.GENERAL_BUSINESS: 0,
        EmailType.OPERATOR_COMPANY: 1,
        EmailType.ONLINE_SHOP: 2,
        EmailType.MEDIA_PR: 3,
        EmailType.RECRUITMENT: 4,
        EmailType.RESERVATION: 5,
        EmailType.PERSONAL_OR_UNCLEAR: 6,
        EmailType.LOW_CONFIDENCE: 7,
        EmailType.DO_NOT_CONTACT: 99,
    }
    return sorted(emails, key=lambda x: priority.get(x[1], 50))
