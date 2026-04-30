"""Detect official contact forms on websites.

Identifies contact forms by:
  - Page title / URL path containing Japanese contact terms
  - HTML form elements with relevant field names
  - Distinguishes official forms from third-party reservation/booking forms
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from html.parser import HTMLParser

from .models import DiscoveredContactForm

# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

# Page title / URL path signals for OFFICIAL contact forms
OFFICIAL_FORM_TITLE_TERMS = [
    "お問い合わせ", "contact", "inquiry", "enquiry",
    "法人のお問い合わせ", "業務提携", "取材のお問い合わせ",
    "お問合せ", "ご連絡",
]

# URL path signals
OFFICIAL_FORM_URL_PATTERNS = [
    r"contact", r"inquiry", r"toiawase", r"toiawase_form",
    r"お問い合わせ", r"form", r"inquiry",
]

# Third-party form indicators (lower priority)
THIRD_PARTY_FORM_DOMAINS = [
    "form.run", "formrun.com", "google.com/forms",
    "wufoo.com", "typeform.com", "surveymonkey.com",
    "paypal.com", "stripe.com",
]

# Form field name signals for official contact
OFFICIAL_FIELD_NAMES = [
    "name", "email", "message", "company", "tel",
    "お名前", "メール", "メッセージ", "会社名", "電話",
    "氏名", "内容", "件名",
]

# Reservation form signals (NOT what we want)
RESERVATION_FORM_SIGNALS = [
    "予約", "reserve", "booking", "人数", "時間", "date", "time",
    "人数", "席", "コース",
    "人数", "来店日", "来店時間",
]

# Recruitment form signals (NOT what we want)
RECRUITMENT_FORM_SIGNALS = [
    "採用", "求人", "recruit", "career", "履歴書", "職務経歴書",
    "応募", "職種",
]


@dataclass
class FormDetection:
    """Result of contact form analysis for one page."""
    is_contact_form: bool = False
    form_type: str = ""  # "official", "third_party", "reservation", "recruitment"
    confidence: float = 0.0
    page_title: str = ""
    form_action: str = ""
    field_names: list[str] = None

    def __post_init__(self):
        if self.field_names is None:
            self.field_names = []


# ---------------------------------------------------------------------------
# Form parser
# ---------------------------------------------------------------------------

class _FormHTMLParser(HTMLParser):
    """Extract form elements and their fields from HTML."""

    def __init__(self):
        super().__init__()
        self.forms: list[dict] = []
        self._current_form: Optional[dict] = None
        self.title: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str]]):
        attr_dict = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag == "form":
            self._current_form = {
                "action": attr_dict.get("action", ""),
                "method": attr_dict.get("method", "get").lower(),
                "fields": [],
                "id": attr_dict.get("id", ""),
                "class": attr_dict.get("class", ""),
            }
        if tag in ("input", "textarea", "select") and self._current_form is not None:
            name = attr_dict.get("name", attr_dict.get("id", ""))
            type_ = attr_dict.get("type", tag)
            if name:
                self._current_form["fields"].append({"name": name, "type": type_})

    def handle_endtag(self, tag: str):
        if tag == "form" and self._current_form is not None:
            self.forms.append(self._current_form)
            self._current_form = None

    def handle_data(self, data: str):
        if hasattr(self, "_in_title") and self._in_title:
            self.title = data.strip()
            self._in_title = False


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _is_official_title(title: str) -> bool:
    title_lower = title.lower()
    return any(term.lower() in title_lower for term in OFFICIAL_FORM_TITLE_TERMS)


def _is_official_url(url: str) -> bool:
    url_lower = url.lower()
    return any(re.search(p, url_lower) for p in OFFICIAL_FORM_URL_PATTERNS)


def _is_third_party_action(action: str) -> bool:
    action_lower = action.lower()
    return any(domain in action_lower for domain in THIRD_PARTY_FORM_DOMAINS)


def _has_reservation_fields(fields: list[dict]) -> bool:
    all_text = " ".join(f["name"].lower() for f in fields)
    return any(sig in all_text for sig in RESERVATION_FORM_SIGNALS)


def _has_recruitment_fields(fields: list[dict]) -> bool:
    all_text = " ".join(f["name"].lower() for f in fields)
    return any(sig in all_text for sig in RECRUITMENT_FORM_SIGNALS)


def _has_contact_fields(fields: list[dict]) -> bool:
    all_text = " ".join(f["name"].lower() for f in fields)
    return any(sig in all_text for sig in OFFICIAL_FIELD_NAMES)


def detect_contact_form(
    url: str,
    html: str = "",
    page_title: str = "",
) -> FormDetection:
    """Analyze a page for contact form presence.

    Args:
        url: Page URL.
        html: Raw HTML of the page.
        page_title: Page title (if already extracted).

    Returns:
        FormDetection with classification.
    """
    result = FormDetection()

    # Parse HTML for forms
    parser = _FormHTMLParser()
    if html:
        try:
            parser.feed(html)
        except Exception:
            pass

    title = page_title or parser.title
    result.page_title = title

    # Check page title signals
    title_official = _is_official_title(title)
    url_official = _is_official_url(url)

    if not title_official and not url_official and not parser.forms:
        return result

    # Analyze each form
    best_form = None
    best_confidence = 0.0
    best_type = ""

    for form in parser.forms:
        confidence = 0.0
        form_type = ""

        # Check for reservation signals (negative)
        if _has_reservation_fields(form["fields"]):
            # It's a reservation form, not what we want
            continue

        # Check for recruitment signals (negative)
        if _has_recruitment_fields(form["fields"]):
            continue

        # Positive signals
        if title_official:
            confidence += 0.3
        if url_official:
            confidence += 0.2
        if _has_contact_fields(form["fields"]):
            confidence += 0.3
        if form["method"] == "post":
            confidence += 0.1

        # Third-party vs official
        if _is_third_party_action(form["action"]):
            form_type = "third_party"
            confidence -= 0.1
        else:
            form_type = "official"

        if confidence > best_confidence:
            best_confidence = confidence
            best_form = form
            best_type = form_type

    if best_form and best_confidence > 0.3:
        result.is_contact_form = True
        result.form_type = best_type
        result.confidence = min(best_confidence, 1.0)
        result.form_action = best_form.get("action", "")
        result.field_names = [f["name"] for f in best_form.get("fields", [])]

    return result


def detect_contact_forms_from_links(
    links: list[str],
    page_title: str = "",
    current_url: str = "",
) -> list[DiscoveredContactForm]:
    """Identify likely contact-form URLs from a list of links.

    Used when we have the link list from a page but haven't crawled the form pages yet.
    """
    results: list[DiscoveredContactForm] = []

    for link in links:
        link_lower = link.lower()
        is_contact = any(term in link_lower for term in OFFICIAL_FORM_URL_PATTERNS)
        if is_contact:
            form_type = "third_party" if any(d in link_lower for d in THIRD_PARTY_FORM_DOMAINS) else "official"
            results.append(DiscoveredContactForm(
                url=link,
                form_type=form_type,
                page_title=page_title,
                confidence=0.4,  # URL-only detection is lower confidence
                source_url=current_url,
            ))

    return results
