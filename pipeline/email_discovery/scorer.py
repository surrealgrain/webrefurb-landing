"""Lead scoring: 0-100 confidence score for launch readiness.

Scoring dimensions:
  1. Genre fit (ramen/izakaya confirmed)
  2. Location (Japan confirmed, tourist area)
  3. Email quality (type, source, confidence)
  4. Contact availability (email, contact form)
  5. Menu presence (critical for our service)
  6. Operator resolution (company behind shop)
  7. Online shop presence (indicates digital sophistication)
  8. Compliance (refusal warnings are negative)
  9. Activity signals (recent updates, not closed)
"""

from __future__ import annotations

from .models import EnrichedLead, EmailType, ReasonCode
from .config import DiscoveryConfig


# ---------------------------------------------------------------------------
# Scoring weights
# ---------------------------------------------------------------------------

# Each dimension is scored 0-1, then weighted
_WEIGHTS = {
    "genre_fit": 20.0,
    "location": 10.0,
    "email_quality": 25.0,
    "contact_availability": 15.0,
    "menu_presence": 10.0,
    "operator_resolution": 5.0,
    "online_shop": 5.0,
    "compliance": 5.0,
    "activity": 5.0,
}

# Email type → quality multiplier
_EMAIL_TYPE_MULTIPLIERS = {
    EmailType.GENERAL_BUSINESS: 1.0,
    EmailType.OPERATOR_COMPANY: 0.85,
    EmailType.ONLINE_SHOP: 0.75,
    EmailType.MEDIA_PR: 0.6,
    EmailType.RECRUITMENT: 0.3,
    EmailType.RESERVATION: 0.15,
    EmailType.PERSONAL_OR_UNCLEAR: 0.2,
    EmailType.LOW_CONFIDENCE: 0.1,
    EmailType.DO_NOT_CONTACT: 0.0,
}

# Email source → quality bonus
_SOURCE_BONUSES = {
    "official_website": 0.15,
    "company_page": 0.10,
    "tokushoho": 0.12,
    "online_shop": 0.08,
    "pr_page": 0.05,
    "search_result": 0.02,
    "unknown": 0.0,
}


# ---------------------------------------------------------------------------
# Dimension scorers
# ---------------------------------------------------------------------------

def _score_genre(lead: EnrichedLead) -> tuple[float, list[str]]:
    """Score genre fit. Max 1.0."""
    reasons: list[str] = []

    if not lead.genre:
        return 0.2, reasons

    if lead.genre_confidence >= 0.8:
        reasons.append(ReasonCode.JAPAN_LOCATION_CONFIRMED.value)
        return 1.0, reasons
    elif lead.genre_confidence >= 0.6:
        return 0.7, reasons
    elif lead.genre_confidence > 0:
        return 0.4, reasons

    return 0.2, reasons


def _score_location(lead: EnrichedLead) -> tuple[float, list[str]]:
    """Score location signals. Max 1.0."""
    reasons: list[str] = []
    score = 0.0

    if lead.prefecture or lead.address:
        score += 0.5
        reasons.append(ReasonCode.JAPAN_LOCATION_CONFIRMED.value)

    if lead.tourist_area_signal:
        score += 0.5
        reasons.append(ReasonCode.TOURIST_AREA.value)

    return min(score, 1.0), reasons


def _score_email_quality(lead: EnrichedLead) -> tuple[float, list[str]]:
    """Score email quality based on type and source. Max 1.0."""
    reasons: list[str] = []

    if not lead.best_email:
        return 0.0, reasons

    # Parse email type
    try:
        email_type = EmailType(lead.best_email_type)
    except ValueError:
        email_type = EmailType.LOW_CONFIDENCE

    quality = _EMAIL_TYPE_MULTIPLIERS.get(email_type, 0.1)

    # Source bonus
    if "tokushoho" in lead.email_source_url.lower():
        quality += _SOURCE_BONUSES["tokushoho"]
        reasons.append(ReasonCode.TOKUSHOHO_EMAIL_FOUND.value)
    elif "company" in lead.email_source_url.lower():
        quality += _SOURCE_BONUSES["company_page"]
    elif lead.official_site_url and lead.email_source_url.startswith(lead.official_site_url):
        quality += _SOURCE_BONUSES["official_website"]
        reasons.append(ReasonCode.OFFICIAL_EMAIL_FOUND.value)

    return min(quality, 1.0), reasons


def _score_contact_availability(lead: EnrichedLead) -> tuple[float, list[str]]:
    """Score contact availability. Max 1.0."""
    reasons: list[str] = []
    score = 0.0

    if lead.best_email:
        score += 0.7
    if lead.contact_form_url:
        score += 0.3
        reasons.append(ReasonCode.CONTACT_FORM_FOUND.value)

    return min(score, 1.0), reasons


def _score_menu(lead: EnrichedLead) -> tuple[float, list[str]]:
    """Score menu presence. Max 1.0."""
    reasons: list[str] = []

    if lead.menu_detected:
        reasons.append(ReasonCode.MENU_FOUND.value)
        return 1.0, reasons
    if lead.menu_url:
        reasons.append(ReasonCode.MENU_FOUND.value)
        return 0.8, reasons

    return 0.0, reasons


def _score_operator(lead: EnrichedLead) -> tuple[float, list[str]]:
    """Score operator company resolution. Max 1.0."""
    reasons: list[str] = []

    if lead.operator_company_name:
        reasons.append(ReasonCode.OPERATOR_COMPANY_RESOLVED.value)
        if lead.operator_company_url:
            return 1.0, reasons
        return 0.6, reasons

    return 0.0, reasons


def _score_online_shop(lead: EnrichedLead) -> tuple[float, list[str]]:
    """Score online shop presence. Max 1.0."""
    reasons: list[str] = []

    if lead.online_shop_detected:
        reasons.append(ReasonCode.ONLINE_SHOP_DETECTED.value)
        return 1.0, reasons

    return 0.0, reasons


def _score_compliance(lead: EnrichedLead) -> tuple[float, list[str]]:
    """Score compliance. Max 1.0. Refusal = 0."""
    reasons: list[str] = []

    if lead.no_sales_warning:
        reasons.append(ReasonCode.SALES_REFUSAL_WARNING.value)
        return 0.0, reasons

    return 1.0, reasons


def _score_activity(lead: EnrichedLead) -> tuple[float, list[str]]:
    """Score activity signals. Max 1.0."""
    reasons: list[str] = []

    # Basic heuristic: if we found an active website, that's a positive
    if lead.official_site_url:
        reasons.append(ReasonCode.RECENT_ACTIVITY.value)
        return 0.8, reasons

    return 0.3, reasons


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------

def score_lead(lead: EnrichedLead, config: DiscoveryConfig | None = None) -> float:
    """Score a lead from 0-100.

    Also populates lead.reason_codes with human-readable codes.
    """
    scorers = [
        ("genre_fit", _score_genre),
        ("location", _score_location),
        ("email_quality", _score_email_quality),
        ("contact_availability", _score_contact_availability),
        ("menu_presence", _score_menu),
        ("operator_resolution", _score_operator),
        ("online_shop", _score_online_shop),
        ("compliance", _score_compliance),
        ("activity", _score_activity),
    ]

    total_weight = sum(_WEIGHTS[dim] for dim, _ in scorers)
    weighted_score = 0.0
    all_reasons: list[str] = []

    for dim, scorer in scorers:
        dim_score, reasons = scorer(lead)
        weight = _WEIGHTS[dim]
        weighted_score += dim_score * weight
        all_reasons.extend(reasons)

    # Normalize to 0-100
    raw_score = (weighted_score / total_weight) * 100

    # Add negative signals
    if not lead.best_email and not lead.contact_form_url:
        all_reasons.append(ReasonCode.NO_EMAIL_FOUND.value)
        all_reasons.append(ReasonCode.ONLY_PHONE_SOCIAL.value)
        raw_score *= 0.3  # Heavy penalty

    if lead.no_sales_warning:
        raw_score *= 0.1  # Near-zero

    lead.confidence_score = round(min(max(raw_score, 0), 100), 1)
    lead.reason_codes = list(set(all_reasons))

    return lead.confidence_score
