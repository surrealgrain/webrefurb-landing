from __future__ import annotations

from typing import Any

from .constants import (
    ENGLISH_QR_MENU_KEY,
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
    print_yourself_fit: bool = False,
    counter_ready_need: bool = False,
    stable_table_menus: bool = False,
    frequent_updates_expected: bool | None = None,
    tourist_exposure_score: float,
    lead_score_v1: int,
) -> str:
    """Recommend the best default package by ordering friction and scope."""
    return recommend_package_details(
        category=category,
        english_menu_issue=english_menu_issue,
        machine_evidence_found=machine_evidence_found,
        menu_complexity_state=menu_complexity_state,
        izakaya_rules_state=izakaya_rules_state,
        print_yourself_fit=print_yourself_fit,
        counter_ready_need=counter_ready_need,
        stable_table_menus=stable_table_menus,
        frequent_updates_expected=frequent_updates_expected,
        tourist_exposure_score=tourist_exposure_score,
        lead_score_v1=lead_score_v1,
    )["package_key"]


def recommend_package_details(
    *,
    category: str = "",
    english_menu_issue: bool,
    machine_evidence_found: bool,
    menu_complexity_state: str = "simple",
    izakaya_rules_state: str = "none_found",
    print_yourself_fit: bool = False,
    counter_ready_need: bool = False,
    stable_table_menus: bool = False,
    frequent_updates_expected: bool | None = None,
    tourist_exposure_score: float,
    lead_score_v1: int,
) -> dict[str, str]:
    """Recommend the single active product plus audit-required reason fields."""
    category = str(category or "").strip().lower()
    if not english_menu_issue:
        return {
            "package_key": "none",
            "recommendation_reason": "no_english_qr_menu_gap",
            "custom_quote_reason": "",
        }

    if category not in {"ramen", "izakaya"}:
        return {
            "package_key": "skip",
            "recommendation_reason": "unsupported_restaurant_category_outside_active_scope",
            "custom_quote_reason": "",
        }

    return {
        "package_key": ENGLISH_QR_MENU_KEY,
        "recommendation_reason": f"{category}_english_qr_menu_show_staff_list_fit",
        "custom_quote_reason": "",
    }


def recommend_package_details_for_record(record: dict[str, Any]) -> dict[str, str]:
    """Re-score a persisted/imported lead through the current package rules."""
    category = str(record.get("primary_category_v1") or record.get("category") or "").strip().lower()
    if category not in {"ramen", "izakaya"}:
        text = _record_text(record)
        if "居酒屋" in text or "izakaya" in text:
            category = "izakaya"
        elif "ラーメン" in text or "ramen" in text:
            category = "ramen"
        else:
            category = "skip"

    menu_complexity_state = str(record.get("menu_complexity_state") or "").strip() or (
        "medium" if category == "izakaya" else "simple"
    )
    izakaya_rules_state = str(record.get("izakaya_rules_state") or "").strip() or "none_found"
    if category == "izakaya" and izakaya_rules_state in {"", "unknown", "none_found"}:
        izakaya_rules_state = _infer_izakaya_rules_state(record)

    return recommend_package_details(
        category=category,
        english_menu_issue=_effective_english_menu_issue_for_record(record),
        machine_evidence_found=bool(record.get("machine_evidence_found") or _has_any_token(record, ("券売機", "食券", "ticket_machine"))),
        menu_complexity_state=menu_complexity_state,
        izakaya_rules_state=izakaya_rules_state,
        print_yourself_fit=_has_any_token(record, ("print_yourself", "print yourself", "店内印刷", "自店で印刷")),
        counter_ready_need=bool(record.get("counter_ready_need")) or _has_any_token(record, ("counter_ready", "counter-ready", "券売機横", "ordering guide")),
        stable_table_menus=_has_any_token(record, ("stable_table_menu", "stable table", "卓上メニュー", "定番メニュー")),
        frequent_updates_expected=(
            bool(record.get("frequent_updates_expected"))
            or bool(record.get("course_or_drink_plan_evidence_found"))
            or izakaya_rules_state in {"courses_found", "nomihodai_found"}
        ),
        tourist_exposure_score=_float_value(record.get("tourist_exposure_score")),
        lead_score_v1=_int_value(record.get("lead_score_v1")),
    )


def _effective_english_menu_issue_for_record(record: dict[str, Any]) -> bool:
    """Treat unknown English support as a package opportunity for valid leads.

    Explicitly usable English ordering support is still a disqualifying signal
    elsewhere. For persisted lead repair, a false boolean often means "not
    proven from available public evidence", not "already solved".
    """
    availability = str(record.get("english_availability") or "").strip()
    reasons = {str(reason) for reason in record.get("launch_readiness_reasons") or []}
    if (
        availability in {"clear_usable", "usable_complete"}
        or record.get("rejection_reason") == "already_has_good_english_menu"
        or "already_has_usable_english_solution" in reasons
        or "multilingual_qr_or_ordering_solution_present" in reasons
    ):
        return False
    if record.get("english_menu_issue") is True:
        return True
    if record.get("lead") is True:
        return True
    return bool(record.get("english_menu_issue", True))


def _record_text(record: dict[str, Any]) -> str:
    values: list[str] = []
    for key in (
        "business_name",
        "category",
        "primary_category_v1",
        "lead_category",
        "establishment_profile",
        "menu_type",
        "package_recommendation_reason",
    ):
        values.append(str(record.get(key) or ""))
    for key in ("lead_signals", "evidence_classes", "evidence_snippets", "matched_friction_evidence"):
        raw = record.get(key)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw)
        elif raw:
            values.append(str(raw))
    dossier = record.get("lead_evidence_dossier")
    if isinstance(dossier, dict):
        values.extend(str(value) for value in dossier.values() if isinstance(value, (str, int, float, bool)))
    return " ".join(values).lower()


def _has_any_token(record: dict[str, Any], tokens: tuple[str, ...]) -> bool:
    text = _record_text(record)
    return any(token.lower() in text for token in tokens)


def _infer_izakaya_rules_state(record: dict[str, Any]) -> str:
    text = _record_text(record)
    if any(token in text for token in ("飲み放題", "nomihodai", "all-you-can-drink")):
        return "nomihodai_found"
    if any(token in text for token in ("コース", "course", "宴会")):
        return "courses_found"
    if any(token in text for token in ("ドリンク", "drink", "beer", "sake", "日本酒")):
        return "drinks_found"
    return "unknown"


def _float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
