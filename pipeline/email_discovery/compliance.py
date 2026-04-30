"""Compliance filter: detect refusal warnings and do-not-contact signals.

Scans page text for Japanese phrases indicating that the business
refuses sales/marketing emails. Also flags reservation-only and
recruitment-only addresses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Refusal phrases — any match means DO NOT CONTACT
# ---------------------------------------------------------------------------

REFUSAL_PHRASES = [
    "営業メールお断り",
    "営業目的のメールはご遠慮ください",
    "営業・勧誘のご連絡はお断り",
    "広告メール禁止",
    "セールスお断り",
    "勧誘お断り",
    "迷惑メール対策",
    "無断営業禁止",
    "当サイトおよび店舗への営業・勧誘は固くお断り",
    "営業・勧誘・スパムメールはお断り",
    "営業目的のお電話・メールはお断り",
    "営業・勧誘は一切お断り",
    "同業他社の営業はご遠慮",
    "業者様の営業はお断り",
    "営業活動を目的とした",
]

# Reservation-only phrases — flag as low-priority
RESERVATION_ONLY_PHRASES = [
    "予約専用",
    "ご予約のみ",
    "予約受付専用",
    "予約以外のお問い合わせは",
]

# Recruitment-only phrases — flag as recruitment context
RECRUITMENT_ONLY_PHRASES = [
    "採用専用",
    "求人のみ",
    "採用に関するお問い合わせのみ",
    "採用担当",
    "人事部宛",
]

# Closure indicators
CLOSURE_PHRASES = [
    "閉店", "閉業", "休業中", "閉店しました",
    "営業終了", "感激屋閉店", "永年のお愛顧",
    "令和.*?閉店", "令和.*?休業",
]


@dataclass
class ComplianceResult:
    """Result of compliance check on a page."""
    has_refusal_warning: bool = False
    is_reservation_only: bool = False
    is_recruitment_only: bool = False
    appears_closed: bool = False
    matched_refusal_phrases: list[str] = None
    matched_reservation_phrases: list[str] = None
    matched_recruitment_phrases: list[str] = None
    matched_closure_phrases: list[str] = None

    def __post_init__(self):
        if self.matched_refusal_phrases is None:
            self.matched_refusal_phrases = []
        if self.matched_reservation_phrases is None:
            self.matched_reservation_phrases = []
        if self.matched_recruitment_phrases is None:
            self.matched_recruitment_phrases = []
        if self.matched_closure_phrases is None:
            self.matched_closure_phrases = []

    @property
    def should_skip(self) -> bool:
        """True if the page has a clear refusal warning."""
        return self.has_refusal_warning

    @property
    def is_problematic(self) -> bool:
        """True if any compliance issue was detected."""
        return (
            self.has_refusal_warning
            or self.is_reservation_only
            or self.is_recruitment_only
            or self.appears_closed
        )


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def check_compliance(text: str) -> ComplianceResult:
    """Check page text for compliance issues.

    Args:
        text: Page visible text content.

    Returns:
        ComplianceResult with any detected issues.
    """
    if not text:
        return ComplianceResult()

    result = ComplianceResult()

    # Check refusal phrases
    for phrase in REFUSAL_PHRASES:
        if phrase in text:
            result.has_refusal_warning = True
            result.matched_refusal_phrases.append(phrase)

    # Check reservation-only
    for phrase in RESERVATION_ONLY_PHRASES:
        if phrase in text:
            result.is_reservation_only = True
            result.matched_reservation_phrases.append(phrase)

    # Check recruitment-only
    for phrase in RECRUITMENT_ONLY_PHRASES:
        if phrase in text:
            result.is_recruitment_only = True
            result.matched_recruitment_phrases.append(phrase)

    # Check closure indicators
    for phrase in CLOSURE_PHRASES:
        if re.search(phrase, text):
            result.appears_closed = True
            result.matched_closure_phrases.append(phrase)

    return result


def is_email_safe_to_contact(
    email: str,
    page_text: str,
    email_context: str = "",
) -> tuple[bool, str]:
    """Check if a specific email is safe to use for outreach.

    Returns:
        (is_safe, reason) — reason is empty if safe.
    """
    combined = f"{page_text}\n{email_context}"

    result = check_compliance(combined)

    if result.has_refusal_warning:
        return False, f"Refusal warning: {', '.join(result.matched_refusal_phrases)}"

    if result.appears_closed:
        return False, f"Appears closed: {', '.join(result.matched_closure_phrases)}"

    return True, ""
