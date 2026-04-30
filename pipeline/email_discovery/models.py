"""Data models for the email discovery pipeline."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EmailType(Enum):
    GENERAL_BUSINESS = "general_business_contact"
    OPERATOR_COMPANY = "operator_company_contact"
    ONLINE_SHOP = "online_shop_contact"
    MEDIA_PR = "media_pr_contact"
    RECRUITMENT = "recruitment_contact"
    RESERVATION = "reservation_contact"
    PERSONAL_OR_UNCLEAR = "personal_or_unclear"
    LOW_CONFIDENCE = "low_confidence"
    DO_NOT_CONTACT = "do_not_contact"


class ReasonCode(Enum):
    OFFICIAL_EMAIL_FOUND = "OFFICIAL_EMAIL_FOUND"
    TOKUSHOHO_EMAIL_FOUND = "TOKUSHOHO_EMAIL_FOUND"
    CONTACT_FORM_FOUND = "CONTACT_FORM_FOUND"
    OPERATOR_COMPANY_RESOLVED = "OPERATOR_COMPANY_RESOLVED"
    MENU_FOUND = "MENU_FOUND"
    TOURIST_AREA = "TOURIST_AREA"
    ONLINE_SHOP_DETECTED = "ONLINE_SHOP_DETECTED"
    NO_EMAIL_FOUND = "NO_EMAIL_FOUND"
    ONLY_PHONE_SOCIAL = "ONLY_PHONE_SOCIAL"
    RECRUITING_EMAIL_ONLY = "RECRUITING_EMAIL_ONLY"
    SALES_REFUSAL_WARNING = "SALES_REFUSAL_WARNING"
    GENRE_MISMATCH = "GENRE_MISMATCH"
    POSSIBLY_CLOSED = "POSSIBLY_CLOSED"
    JAPAN_LOCATION_CONFIRMED = "JAPAN_LOCATION_CONFIRMED"
    INDEPENDENT_OR_SMALL_CHAIN = "INDEPENDENT_OR_SMALL_CHAIN"
    RECENT_ACTIVITY = "RECENT_ACTIVITY"


class NextBestAction(Enum):
    SEND_EMAIL = "SEND_PERSONALIZED_EMAIL_WITH_INLINE_MENU_SAMPLE"
    USE_CONTACT_FORM = "USE_OFFICIAL_CONTACT_FORM_WITH_PREVIEW_LINK"
    RESEARCH_OPERATOR = "RESEARCH_OPERATOR_COMPANY"
    SKIP_NO_CONTACT = "SKIP_NO_APPROVED_CONTACT_ROUTE"
    SKIP_DNC = "SKIP_DO_NOT_CONTACT_WARNING"
    SKIP_GENRE = "SKIP_GENRE_MISMATCH"
    SKIP_CLOSED = "SKIP_POSSIBLY_CLOSED"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_japanese(text: str) -> str:
    """Normalize full-width ASCII, katakana, and whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.strip()
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text


def _make_lead_id(shop_name: str, prefecture: str) -> str:
    """Deterministic lead ID from shop name + prefecture."""
    raw = f"{shop_name}|{prefecture}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"LD-{h}"


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

@dataclass
class InputLead:
    """One row from the input CSV."""
    shop_name: str
    genre: str = ""
    address: str = ""
    city: str = ""
    prefecture: str = ""
    phone: str = ""
    portal_url: str = ""
    official_site_url: str = ""
    menu_url: str = ""
    notes: str = ""

    @property
    def normalized_shop_name(self) -> str:
        return _normalize_japanese(self.shop_name)

    @property
    def lead_id(self) -> str:
        return _make_lead_id(self.shop_name, self.prefecture)


# ---------------------------------------------------------------------------
# Discovered email record
# ---------------------------------------------------------------------------

@dataclass
class DiscoveredEmail:
    email: str
    email_type: EmailType = EmailType.LOW_CONFIDENCE
    source_url: str = ""
    source_snippet: str = ""
    source_page_type: str = ""  # e.g. "tokushoho", "contact", "company"
    confidence: float = 0.5
    mx_valid: Optional[bool] = None

    def to_dict(self) -> dict:
        return {
            "email": self.email,
            "email_type": self.email_type.value,
            "source_url": self.source_url,
            "source_snippet": self.source_snippet,
            "source_page_type": self.source_page_type,
            "confidence": round(self.confidence, 3),
            "mx_valid": self.mx_valid,
        }


# ---------------------------------------------------------------------------
# Discovered contact form
# ---------------------------------------------------------------------------

@dataclass
class DiscoveredContactForm:
    url: str
    form_type: str = ""  # "official", "third_party"
    page_title: str = ""
    confidence: float = 0.5
    source_url: str = ""

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "form_type": self.form_type,
            "page_title": self.page_title,
            "confidence": round(self.confidence, 3),
            "source_url": self.source_url,
        }


# ---------------------------------------------------------------------------
# Operator company resolution
# ---------------------------------------------------------------------------

@dataclass
class OperatorCompany:
    name: str = ""
    url: str = ""
    email: str = ""
    source_url: str = ""
    source_type: str = ""  # "tokushoho", "recruitment", "pr", "directory"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "url": self.url,
            "email": self.email,
            "source_url": self.source_url,
            "source_type": self.source_type,
        }


# ---------------------------------------------------------------------------
# Enriched lead output
# ---------------------------------------------------------------------------

@dataclass
class EnrichedLead:
    lead_id: str = ""
    shop_name: str = ""
    normalized_shop_name: str = ""
    genre: str = ""
    genre_confidence: float = 0.0
    address: str = ""
    prefecture: str = ""
    city: str = ""
    phone: str = ""
    official_site_url: str = ""
    operator_company_name: str = ""
    operator_company_url: str = ""
    best_email: str = ""
    best_email_type: str = ""
    all_emails: list[DiscoveredEmail] = field(default_factory=list)
    contact_form_url: str = ""
    contact_forms: list[DiscoveredContactForm] = field(default_factory=list)
    email_source_url: str = ""
    email_source_snippet: str = ""
    no_sales_warning: bool = False
    menu_url: str = ""
    menu_detected: bool = False
    tourist_area_signal: bool = False
    online_shop_detected: bool = False
    tokushoho_page_url: str = ""
    recruitment_page_url: str = ""
    pr_page_url: str = ""
    launch_ready: bool = False
    confidence_score: float = 0.0
    reason_codes: list[str] = field(default_factory=list)
    next_best_action: str = ""
    operator_company: Optional[OperatorCompany] = None
    crawl_timestamp: str = ""
    raw_search_results: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "lead_id": self.lead_id,
            "shop_name": self.shop_name,
            "normalized_shop_name": self.normalized_shop_name,
            "genre": self.genre,
            "genre_confidence": round(self.genre_confidence, 3),
            "address": self.address,
            "prefecture": self.prefecture,
            "city": self.city,
            "phone": self.phone,
            "official_site_url": self.official_site_url,
            "operator_company_name": self.operator_company_name,
            "operator_company_url": self.operator_company_url,
            "best_email": self.best_email,
            "best_email_type": self.best_email_type,
            "all_emails_found": [e.to_dict() for e in self.all_emails],
            "contact_form_url": self.contact_form_url,
            "email_source_url": self.email_source_url,
            "email_source_snippet": self.email_source_snippet,
            "no_sales_warning_detected": self.no_sales_warning,
            "menu_url": self.menu_url,
            "menu_detected_boolean": self.menu_detected,
            "tourist_area_signal": self.tourist_area_signal,
            "online_shop_detected": self.online_shop_detected,
            "tokushoho_page_url": self.tokushoho_page_url,
            "recruitment_page_url": self.recruitment_page_url,
            "pr_page_url": self.pr_page_url,
            "launch_ready_boolean": self.launch_ready,
            "confidence_score": round(self.confidence_score, 1),
            "reason_codes": sorted(set(self.reason_codes)),
            "next_best_action": self.next_best_action,
            "crawl_timestamp": self.crawl_timestamp,
        }
        if self.operator_company:
            d["operator_company"] = self.operator_company.to_dict()
        return d

    def to_csv_row(self) -> dict:
        """Flat dict suitable for CSV output."""
        return {
            "lead_id": self.lead_id,
            "shop_name": self.shop_name,
            "normalized_shop_name": self.normalized_shop_name,
            "genre": self.genre,
            "genre_confidence": round(self.genre_confidence, 3),
            "address": self.address,
            "prefecture": self.prefecture,
            "city": self.city,
            "phone": self.phone,
            "official_site_url": self.official_site_url,
            "operator_company_name": self.operator_company_name,
            "operator_company_url": self.operator_company_url,
            "best_email": self.best_email,
            "best_email_type": self.best_email_type,
            "all_emails": "; ".join(e.email for e in self.all_emails),
            "contact_form_url": self.contact_form_url,
            "email_source_url": self.email_source_url,
            "email_source_snippet": self.email_source_snippet[:200],
            "no_sales_warning_detected": self.no_sales_warning,
            "menu_url": self.menu_url,
            "menu_detected": self.menu_detected,
            "tourist_area_signal": self.tourist_area_signal,
            "online_shop_detected": self.online_shop_detected,
            "tokushoho_page_url": self.tokushoho_page_url,
            "recruitment_page_url": self.recruitment_page_url,
            "pr_page_url": self.pr_page_url,
            "launch_ready": self.launch_ready,
            "confidence_score": round(self.confidence_score, 1),
            "reason_codes": "|".join(sorted(set(self.reason_codes))),
            "next_best_action": self.next_best_action,
            "crawl_timestamp": self.crawl_timestamp,
        }
