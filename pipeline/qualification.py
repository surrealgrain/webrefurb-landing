from __future__ import annotations

from typing import Any

from .html_parser import extract_page_payload
from .evidence import (
    assess_evidence, is_chain_business, is_excluded_business,
    classify_primary_category, has_public_website, has_social_url_only,
    has_english_intent, looks_high_quality_english, image_locked_evidence,
    _count_japanese_chars, _count_latin_words, _sentences_near,
    _unique_snippets,
)
from .scoring import (
    compute_tourist_exposure_score, compute_lead_score_v1,
    detect_english_menu_issue, recommend_package,
)
from .models import QualificationResult
from .constants import (
    LEAD_CATEGORY_RAMEN_MENU_TRANSLATION,
    LEAD_CATEGORY_RAMEN_MACHINE_MAPPING,
    LEAD_CATEGORY_RAMEN_MENU_AND_MACHINE,
    LEAD_CATEGORY_IZAKAYA_MENU_TRANSLATION,
    LEAD_CATEGORY_IZAKAYA_DRINK_COURSE_GUIDE,
    LEAD_CATEGORY_NONE,
)


def qualify_candidate(
    *,
    business_name: str,
    website: str,
    category: str = "",
    pages: list[dict[str, Any]],
    rating: float | None = None,
    reviews: int | None = None,
    address: str = "",
    phone: str = "",
    place_id: str = "",
    map_url: str = "",
) -> QualificationResult:
    """Main qualification entry point. Binary lead: true or false, never maybe."""

    # Parse pages
    page_payloads = [extract_page_payload(page.get("url") or website, page.get("html") or "") for page in pages]
    combined_text = "\n".join(payload["text"] for payload in page_payloads)

    # Evidence assessment
    assessment = assess_evidence(
        business_name=business_name,
        website=website,
        category=category,
        payloads=page_payloads,
    )

    # --- Rejection gates ---

    # Physical location gate
    physical_location_confirmed = bool(address or phone or place_id or map_url)
    if not physical_location_confirmed:
        return _reject(
            business_name=business_name, website=website, category=category,
            assessment=assessment, rejection_reason="no_physical_location_evidence",
            decision_reason="No physical/visitable location evidence found.",
        )

    # Chain exclusion
    if is_chain_business(business_name):
        return _reject(
            business_name=business_name, website=website, category=category,
            assessment=assessment, rejection_reason="chain_business",
            decision_reason="Rejected: known chain or multi-location brand.",
        )

    # Category gate (ramen or izakaya only)
    primary_category = classify_primary_category(combined_text, category)
    if primary_category == "other":
        return _reject(
            business_name=business_name, website=website, category=category,
            assessment=assessment, rejection_reason="non_ramen_izakaya_v1",
            decision_reason="Rejected: not ramen or izakaya (v1 scope).",
            primary_category_v1="other",
        )

    # Excluded business types
    if is_excluded_business(business_name, category):
        return _reject(
            business_name=business_name, website=website, category=category,
            assessment=assessment, rejection_reason="excluded_business_type_v1",
            decision_reason="Rejected: excluded business type (sushi, yakiniku, kaiseki, cafe, etc.).",
            primary_category_v1=primary_category,
        )

    # Website gate
    if not has_public_website(website):
        return _reject(
            business_name=business_name, website=website, category=category,
            assessment=assessment, rejection_reason="directory_or_social_only",
            decision_reason="Rejected: only directory or social listing found.",
            primary_category_v1=primary_category,
        )

    # Hard reject from evidence
    if assessment.hard_reject_reason:
        return _reject(
            business_name=business_name, website=website, category=category,
            assessment=assessment, rejection_reason=assessment.hard_reject_reason,
            decision_reason=f"Rejected: source is a {assessment.hard_reject_reason}.",
            primary_category_v1=primary_category,
            false_positive_risk="high",
        )

    # Already has good English
    if looks_high_quality_english(page_payloads):
        return _reject(
            business_name=business_name, website=website, category=category,
            assessment=assessment, rejection_reason="already_has_good_english_menu",
            decision_reason="Rejected: clear, usable English menu already available.",
            primary_category_v1=primary_category,
            english_availability="clear_usable",
            false_positive_risk="low",
        )

    # Negative evidence score
    if assessment.score < 0:
        return _reject(
            business_name=business_name, website=website, category=category,
            assessment=assessment, rejection_reason="negative_evidence_score",
            decision_reason="Rejected: evidence strength score is negative.",
            primary_category_v1=primary_category,
        )

    # --- Lead signals ---
    english_intent = has_english_intent(website, page_payloads)
    img_locked = image_locked_evidence(page_payloads)
    text_jp = _count_japanese_chars(combined_text)
    text_en = _count_latin_words(combined_text)

    source_menu_available = assessment.menu_evidence_found or _has_source_menu_content(combined_text, img_locked)

    lead_signals: list[str] = []
    if source_menu_available:
        lead_signals.append("source_menu_available")
    if text_jp >= 12 and text_en < 40 and not english_intent:
        lead_signals.extend(["english_menu_missing", "no_usable_english_menu"])
    if english_intent and _has_purchase_critical_jp(combined_text):
        lead_signals.extend(["english_menu_incomplete", "partial_english_purchase_content"])
    if img_locked:
        lead_signals.append("image_locked_menu")

    # Must have a gap
    if not source_menu_available:
        return _reject(
            business_name=business_name, website=website, category=category,
            assessment=assessment, rejection_reason="no_menu_or_product_evidence",
            decision_reason="Rejected: no usable menu/product evidence found.",
            primary_category_v1=primary_category,
            lead_signals=lead_signals,
        )
    if not lead_signals:
        return _reject(
            business_name=business_name, website=website, category=category,
            assessment=assessment, rejection_reason="no_english_menu_gap",
            decision_reason="Rejected: no missing, incomplete, or image-only English menu gap found.",
            primary_category_v1=primary_category,
        )

    # --- English availability ---
    english_availability = _english_availability(
        english_intent=english_intent,
        img_locked=img_locked,
        source_menu_available=source_menu_available,
        machine_evidence_found=assessment.machine_evidence_found,
    )

    # --- Category-specific decisions ---
    lead_category = LEAD_CATEGORY_NONE
    if primary_category == "ramen":
        lead_category = _ramen_lead_category(assessment, english_availability, source_menu_available)
    elif primary_category == "izakaya":
        lead_category = _izakaya_lead_category(assessment, english_availability, source_menu_available)

    if lead_category == LEAD_CATEGORY_NONE:
        return _reject(
            business_name=business_name, website=website, category=category,
            assessment=assessment, rejection_reason="insufficient_category_evidence",
            decision_reason="Rejected: evidence not strong enough for ramen or izakaya qualification.",
            primary_category_v1=primary_category,
            lead_signals=lead_signals,
        )

    # --- V1 scoring ---
    english_menu_issue, english_menu_issue_evidence = detect_english_menu_issue(
        english_availability=english_availability,
        lead_signals=lead_signals,
        image_locked=img_locked,
    )
    tourist_exposure = compute_tourist_exposure_score(address=address, rating=rating, reviews=reviews)
    lead_score = compute_lead_score_v1(
        category=primary_category,
        english_menu_issue=english_menu_issue,
        tourist_exposure=tourist_exposure,
        rating=rating,
        reviews=reviews,
    )
    package = recommend_package(
        english_menu_issue=english_menu_issue,
        machine_evidence_found=assessment.machine_evidence_found,
        tourist_exposure_score=tourist_exposure,
        lead_score_v1=lead_score,
    )
    (
        establishment_profile,
        establishment_profile_evidence,
        establishment_profile_confidence,
        establishment_profile_source_urls,
    ) = _establishment_profile(
        primary_category=primary_category,
        assessment=assessment,
    )

    # --- Accept ---
    evidence_snippets = _unique_snippets([
        *assessment.snippets,
        *_source_snippets(combined_text, 4),
    ])

    return QualificationResult(
        lead=True,
        rejection_reason=None,
        business_name=business_name,
        website=website,
        category=category,
        address=address,
        phone=phone,
        place_id=place_id,
        map_url=map_url,
        lead_signals=_unique_snippets(lead_signals),
        evidence_classes=assessment.evidence_classes,
        evidence_urls=assessment.evidence_urls,
        evidence_snippets=evidence_snippets[:8],
        image_locked_evidence=img_locked,
        evidence_strength_score=assessment.score,
        menu_evidence_found=assessment.menu_evidence_found,
        machine_evidence_found=assessment.machine_evidence_found,
        course_or_drink_plan_evidence_found=assessment.course_or_drink_plan_evidence_found,
        english_availability=english_availability,
        english_menu_issue=english_menu_issue,
        english_menu_issue_evidence=english_menu_issue_evidence,
        primary_category_v1=primary_category,
        lead_category=lead_category,
        establishment_profile=establishment_profile,
        establishment_profile_evidence=establishment_profile_evidence,
        establishment_profile_confidence=establishment_profile_confidence,
        establishment_profile_source_urls=establishment_profile_source_urls,
        tourist_exposure_score=tourist_exposure,
        lead_score_v1=lead_score,
        recommended_primary_package=package,
        rating=rating,
        reviews=reviews,
        decision_reason=f"Qualified: {primary_category} lead with {english_availability} English availability.",
        false_positive_risk=assessment.false_positive_risk,
        preview_available=True,
        pitch_available=True,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _reject(
    *,
    business_name: str,
    website: str,
    category: str,
    assessment: Any,
    rejection_reason: str,
    decision_reason: str,
    primary_category_v1: str = "other",
    english_availability: str = "unknown",
    false_positive_risk: str = "high",
    lead_signals: list[str] | None = None,
) -> QualificationResult:
    return QualificationResult(
        lead=False,
        rejection_reason=rejection_reason,
        business_name=business_name,
        website=website,
        category=category,
        lead_signals=lead_signals or [],
        evidence_classes=assessment.evidence_classes,
        evidence_urls=assessment.evidence_urls,
        evidence_strength_score=assessment.score,
        menu_evidence_found=assessment.menu_evidence_found,
        machine_evidence_found=assessment.machine_evidence_found,
        course_or_drink_plan_evidence_found=assessment.course_or_drink_plan_evidence_found,
        english_availability=english_availability,
        primary_category_v1=primary_category_v1,
        decision_reason=decision_reason,
        false_positive_risk=false_positive_risk,
    )


def _has_source_menu_content(text: str, img_locked: list[str]) -> bool:
    """Check if there's source language menu content."""
    jp_chars = _count_japanese_chars(text)
    has_menu_tokens = any(token in text for token in ("メニュー", "料理", "品", "商品", "注文", "お品書き"))
    return jp_chars >= 12 and has_menu_tokens or bool(img_locked)


def _has_purchase_critical_jp(text: str) -> bool:
    tokens = {"メニュー", "料理", "品", "商品", "注文", "予約", "持ち帰り", "テイクアウト", "券売機", "食券"}
    return any(token in text for token in tokens)


def _english_availability(
    *,
    english_intent: bool,
    img_locked: list[str],
    source_menu_available: bool,
    machine_evidence_found: bool,
) -> str:
    if img_locked:
        return "image_only"
    if machine_evidence_found and not english_intent:
        return "hard_to_use"
    if source_menu_available and not english_intent:
        return "missing"
    if english_intent:
        return "incomplete"
    return "unknown"


def _source_snippets(text: str, limit: int) -> list[str]:
    import re
    snippets: list[str] = []
    for match in re.finditer(r".{0,24}[\u3040-\u30ff\u3400-\u9fff]{4,}.{0,48}", text or ""):
        snippet = re.sub(r"\s+", " ", match.group(0)).strip()
        if snippet:
            snippets.append(snippet)
        if len(snippets) >= limit:
            break
    return _unique_snippets(snippets)


def _ramen_lead_category(assessment: Any, english_availability: str, source_menu_available: bool) -> str:
    eligible = english_availability in {"missing", "incomplete", "hard_to_use", "image_only", "unknown"}
    if not eligible:
        return LEAD_CATEGORY_NONE
    if assessment.score >= 7 and assessment.menu_evidence_found and assessment.machine_evidence_found:
        return LEAD_CATEGORY_RAMEN_MENU_AND_MACHINE
    if assessment.score >= 7 and assessment.machine_evidence_found:
        return LEAD_CATEGORY_RAMEN_MACHINE_MAPPING
    if assessment.score >= 7 and (assessment.menu_evidence_found or source_menu_available):
        return LEAD_CATEGORY_RAMEN_MENU_TRANSLATION
    return LEAD_CATEGORY_NONE


def _izakaya_lead_category(assessment: Any, english_availability: str, source_menu_available: bool) -> str:
    eligible = english_availability in {"missing", "incomplete", "hard_to_use", "image_only", "unknown"}
    if not eligible:
        return LEAD_CATEGORY_NONE
    if assessment.score >= 7 and assessment.course_or_drink_plan_evidence_found:
        return LEAD_CATEGORY_IZAKAYA_DRINK_COURSE_GUIDE
    if assessment.score >= 7 and (assessment.menu_evidence_found or source_menu_available):
        return LEAD_CATEGORY_IZAKAYA_MENU_TRANSLATION
    return LEAD_CATEGORY_NONE


def _profile_urls(assessment: Any) -> list[str]:
    urls = list(assessment.evidence_urls or [])
    best = str(getattr(assessment, "best_evidence_url", "") or "").strip()
    if best and best not in urls:
        urls.insert(0, best)
    return urls[:4]


def _establishment_profile(*, primary_category: str, assessment: Any) -> tuple[str, list[str], str, list[str]]:
    evidence: list[str] = []
    source_urls = _profile_urls(assessment)
    evidence_classes = set(getattr(assessment, "evidence_classes", []) or [])

    if primary_category == "izakaya":
        evidence.append("primary_category:izakaya")
        if "nomihodai_menu" in evidence_classes or "drink_menu_photo" in evidence_classes:
            evidence.append("drink_focused_menu_evidence")
            return "izakaya_drink_heavy", evidence, "high", source_urls
        if "course_menu" in evidence_classes:
            evidence.append("course_or_drink_plan_evidence")
            return "izakaya_course_heavy", evidence, "high", source_urls
        if assessment.course_or_drink_plan_evidence_found:
            evidence.append("course_or_drink_plan_evidence")
            return "izakaya_food_and_drinks", evidence, "medium", source_urls
        return "izakaya_food_and_drinks", evidence, "medium" if source_urls else "low", source_urls

    if primary_category == "ramen":
        evidence.append("primary_category:ramen")
        if assessment.machine_evidence_found:
            evidence.append("ticket_machine_evidence")
            return "ramen_ticket_machine", evidence, "high", source_urls
        drink_classes = {"drink_menu_photo", "course_menu", "nomihodai_menu"}
        matched_classes = [cls for cls in assessment.evidence_classes if cls in drink_classes]
        if assessment.course_or_drink_plan_evidence_found or matched_classes:
            evidence.extend(matched_classes or ["course_or_drink_plan_evidence"])
            return "ramen_with_drinks", evidence, "medium", source_urls
        return "ramen_only", evidence, "medium" if source_urls else "low", source_urls

    return "unknown", evidence, "low", source_urls
