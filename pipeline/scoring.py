from __future__ import annotations

from .constants import (
    PACKAGE_1_KEY, PACKAGE_2_KEY, PACKAGE_3_KEY, PACKAGE_A_KEY, PACKAGE_B_KEY,
    LEAD_CATEGORY_RAMEN_MENU_TRANSLATION,
    LEAD_CATEGORY_RAMEN_MACHINE_MAPPING,
    LEAD_CATEGORY_RAMEN_MENU_AND_MACHINE,
    LEAD_CATEGORY_IZAKAYA_MENU_TRANSLATION,
    LEAD_CATEGORY_IZAKAYA_DRINK_COURSE_GUIDE,
    JP_AREAS,
)
from .geo import nearest_city_distance, nearest_hotspot_distance


# Known high-tourist areas for exposure scoring (string-based fallback)
_TOURIST_HOTSPOTS = frozenset({
    "shibuya", "shinjuku", "asakusa", "akihabara", "ginza",
    "harajuku", "roppongi", "ueno", "ikebukuro",
    "gion", "arashiyama", "kawaramachi",
    "dotonbori", "namba", "shinsaibashi",
    "kanazawa", "hakone", "kamakura", "nikko",
    "hiroshima", "nara",
})


def _hotspot_score_from_coordinates(lat: float, lng: float) -> float:
    """Score 0.0-0.5 based on Haversine distance to nearest tourist hotspot."""
    dist_km, _ = nearest_hotspot_distance(lat, lng)
    if dist_km <= 0.5:
        return 0.5
    if dist_km <= 1.0:
        return 0.4
    if dist_km <= 2.0:
        return 0.3
    if dist_km <= 5.0:
        return 0.2
    return 0.0


def _city_score_from_coordinates(lat: float, lng: float) -> float:
    """Score 0.0-0.3 based on Haversine distance to nearest major city centre."""
    dist_km, _ = nearest_city_distance(lat, lng)
    if dist_km <= 2.0:
        return 0.3
    if dist_km <= 5.0:
        return 0.2
    if dist_km <= 10.0:
        return 0.1
    return 0.0


def compute_tourist_exposure_score(
    *,
    address: str = "",
    rating: float | None = None,
    reviews: int | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> float:
    """Compute 0.0-1.0 score for tourist exposure potential."""
    score = 0.0

    if latitude is not None and longitude is not None:
        # Coordinate-based scoring (preferred)
        score += _hotspot_score_from_coordinates(latitude, longitude)
        score += _city_score_from_coordinates(latitude, longitude)
    else:
        # String-based fallback (lower max bonus to reflect lower accuracy)
        address_lower = address.lower()
        for area in _TOURIST_HOTSPOTS:
            if area in address_lower:
                score += 0.3
                break
        for city in ("tokyo", "kyoto", "osaka", "fukuoka", "sapporo"):
            if city in address_lower:
                score += 0.2
                break

    # Review count as popularity proxy (0.0-0.2)
    if reviews:
        if reviews >= 500:
            score += 0.2
        elif reviews >= 200:
            score += 0.15
        elif reviews >= 100:
            score += 0.1
        elif reviews >= 50:
            score += 0.05

    return min(1.0, score)


def compute_lead_score_v1(
    *,
    category: str,
    english_menu_issue: bool,
    tourist_exposure: float,
    rating: float | None = None,
    reviews: int | None = None,
) -> int:
    """Compute 0-100 lead quality score."""
    score = 0

    # Category match (0-30)
    if category == "ramen":
        score += 30
    elif category == "izakaya":
        score += 25

    # English menu issue (0-20)
    if english_menu_issue:
        score += 20

    # Tourist exposure (0-20)
    score += int(tourist_exposure * 20)

    # Rating (0-15)
    if rating is not None:
        if rating >= 4.5:
            score += 15
        elif rating >= 4.0:
            score += 12
        elif rating >= 3.5:
            score += 8

    # Reviews (0-15)
    if reviews is not None:
        if reviews >= 500:
            score += 15
        elif reviews >= 200:
            score += 12
        elif reviews >= 100:
            score += 10
        elif reviews >= 50:
            score += 7

    return min(100, score)


def detect_english_menu_issue(
    *,
    english_availability: str,
    lead_signals: list[str],
    image_locked: list[str],
) -> tuple[bool, list[str]]:
    """Detect if there's an English menu gap. Returns (has_issue, evidence_strings)."""
    evidence: list[str] = []
    has_issue = False

    if english_availability in ("missing", "incomplete", "hard_to_use", "image_only"):
        has_issue = True
        evidence.append(f"english_availability={english_availability}")

    if "english_menu_missing" in lead_signals or "no_usable_english_menu" in lead_signals:
        has_issue = True
        evidence.append("no_usable_english_menu")

    if "english_menu_incomplete" in lead_signals or "partial_english_purchase_content" in lead_signals:
        has_issue = True
        evidence.append("partial_english_only")

    if image_locked:
        has_issue = True
        evidence.append("image_locked_menu_content")

    return has_issue, evidence


def recommend_package(
    *,
    category: str = "",
    english_menu_issue: bool,
    machine_evidence_found: bool,
    menu_complexity_state: str = "simple",
    izakaya_rules_state: str = "none_found",
    tourist_exposure_score: float,
    lead_score_v1: int,
) -> str:
    """Recommend the best default package by ordering friction and scope."""
    if not english_menu_issue:
        return "none"

    if menu_complexity_state == "large_custom_quote":
        return "custom_quote"

    if category == "izakaya" and izakaya_rules_state in {"drinks_found", "courses_found", "nomihodai_found"}:
        if izakaya_rules_state in {"courses_found", "nomihodai_found"}:
            return PACKAGE_3_KEY
        return PACKAGE_2_KEY

    if machine_evidence_found:
        return PACKAGE_2_KEY

    if tourist_exposure_score >= 0.65 or lead_score_v1 >= 70:
        return PACKAGE_2_KEY

    return PACKAGE_1_KEY
