from __future__ import annotations

from typing import Any


VALID_SEARCH_CATEGORIES = {"all", "ramen", "izakaya"}


def normalise_search_category(category: str) -> str:
    value = (category or "ramen").strip().lower()
    return value if value in VALID_SEARCH_CATEGORIES else "ramen"


def normalise_search_city(city: str) -> str:
    value = (city or "").strip()
    return "Japan" if not value or value.lower() == "all" else value


def search_category_label(category: str) -> str:
    value = normalise_search_category(category)
    if value == "all":
        return "ramen shops and izakayas"
    if value == "izakaya":
        return "izakayas"
    return "ramen shops"


def search_query_for_scope(*, category: str, city: str) -> str:
    value = normalise_search_category(category)
    place = normalise_search_city(city)
    if value == "all":
        return f"ordering-friction ramen izakaya {place}"
    if value == "izakaya":
        return f"飲み放題 コース 居酒屋 {place}"
    return f"券売機 ラーメン {place}"


def _job(
    *,
    job_id: str,
    query: str,
    category: str,
    purpose: str,
    expected_friction: str,
) -> dict[str, str]:
    return {
        "job_id": job_id,
        "query": query,
        "category": category,
        "purpose": purpose,
        "expected_friction": expected_friction,
    }


def _is_old_generic_restaurant_query(query: str, *, category: str, city: str) -> bool:
    cleaned = " ".join(str(query or "").strip().lower().split())
    if not cleaned:
        return False
    place = normalise_search_city(city).lower()
    generic_queries = {
        f"ramen restaurants {place}",
        f"izakaya restaurants {place}",
        f"ramen and izakaya restaurants {place}",
    }
    if category == "all":
        generic_queries.add(f"restaurants {place}")
    return cleaned in generic_queries


def search_jobs_for_scope(*, category: str, city: str, query: str = "") -> list[dict[str, str]]:
    value = normalise_search_category(category)
    place = normalise_search_city(city)
    if query and query != search_query_for_scope(category=value, city=place) and not _is_old_generic_restaurant_query(query, category=value, city=place):
        job_category = "ramen" if value == "all" else value
        return [_job(
            job_id="operator_custom_query",
            query=query,
            category=job_category,
            purpose="operator_custom_search",
            expected_friction="operator_supplied",
        )]
    ramen_jobs = [
        _job(job_id="ramen_ticket_machine", query=f"券売機 ラーメン {place}", category="ramen", purpose="ticket_machine_lookup", expected_friction="ticket_machine"),
        _job(job_id="ramen_meal_ticket", query=f"食券 ラーメン {place}", category="ramen", purpose="ticket_machine_lookup", expected_friction="meal_ticket"),
        _job(job_id="ramen_menu_photo", query=f"ラーメン メニュー 写真 {place}", category="ramen", purpose="menu_photo_lookup", expected_friction="menu_photo"),
        _job(job_id="ramen_ramendb", query=f"site:ramendb.supleks.jp ラーメン {place}", category="ramen", purpose="ramendb_lookup", expected_friction="independent_ramen_listing"),
        _job(job_id="ramen_official_menu", query=f"ラーメン 公式 メニュー {place}", category="ramen", purpose="official_menu_lookup", expected_friction="official_menu"),
        _job(job_id="ramen_english_menu_check", query=f"英語メニュー ラーメン {place}", category="ramen", purpose="english_solution_check", expected_friction="english_menu_check"),
        _job(job_id="ramen_multilingual_qr_check", query=f"多言語 QR ラーメン {place}", category="ramen", purpose="english_solution_check", expected_friction="multilingual_qr_check"),
        _job(job_id="ramen_mobile_order_check", query=f"モバイルオーダー ラーメン {place}", category="ramen", purpose="english_solution_check", expected_friction="mobile_order_check"),
        _job(job_id="ramen_english_ticket_machine_check", query=f"英語 券売機 ラーメン {place}", category="ramen", purpose="english_solution_check", expected_friction="english_ticket_machine_check"),
    ]
    izakaya_jobs = [
        _job(job_id="izakaya_nomihodai_course", query=f"飲み放題 コース 居酒屋 {place}", category="izakaya", purpose="drink_course_lookup", expected_friction="nomihodai_or_course"),
        _job(job_id="izakaya_oshinagaki", query=f"お品書き 居酒屋 {place}", category="izakaya", purpose="menu_lookup", expected_friction="printed_menu"),
        _job(job_id="izakaya_menu_photo", query=f"居酒屋 メニュー 写真 {place}", category="izakaya", purpose="menu_photo_lookup", expected_friction="menu_photo"),
        _job(job_id="izakaya_hotpepper_nomihodai", query=f"site:hotpepper.jp 居酒屋 {place} 飲み放題", category="izakaya", purpose="hotpepper_lookup", expected_friction="nomihodai_or_course"),
        _job(job_id="izakaya_tabelog_menu", query=f"site:tabelog.com 居酒屋 {place} メニュー", category="izakaya", purpose="tabelog_lookup", expected_friction="independent_izakaya_listing"),
        _job(job_id="izakaya_official_menu", query=f"居酒屋 公式 メニュー {place}", category="izakaya", purpose="official_menu_lookup", expected_friction="official_menu"),
        _job(job_id="izakaya_social_menu", query=f"Instagram 居酒屋 メニュー {place}", category="izakaya", purpose="social_menu_lookup", expected_friction="social_menu_photo"),
        _job(job_id="izakaya_english_menu_check", query=f"英語メニュー 居酒屋 {place}", category="izakaya", purpose="english_solution_check", expected_friction="english_menu_check"),
        _job(job_id="izakaya_multilingual_qr_check", query=f"多言語 QR 居酒屋 {place}", category="izakaya", purpose="english_solution_check", expected_friction="multilingual_qr_check"),
        _job(job_id="izakaya_mobile_order_check", query=f"モバイルオーダー 居酒屋 {place}", category="izakaya", purpose="english_solution_check", expected_friction="mobile_order_check"),
    ]
    if value == "all":
        return [*ramen_jobs, *izakaya_jobs]
    return ramen_jobs if value == "ramen" else izakaya_jobs


def merge_search_results(results: list[dict[str, Any]], *, query: str, category: str) -> dict[str, Any]:
    if len(results) == 1:
        merged = dict(results[0])
        merged["category"] = normalise_search_category(category)
        return merged

    decisions: list[dict[str, Any]] = []
    run_ids: list[str] = []
    for result in results:
        run_ids.append(str(result.get("run_id") or ""))
        decisions.extend(result.get("decisions") or [])

    return {
        "run_id": "+".join(run_id for run_id in run_ids if run_id),
        "query": query,
        "category": normalise_search_category(category),
        "total_candidates": sum(int(result.get("total_candidates") or 0) for result in results),
        "leads": sum(int(result.get("leads") or 0) for result in results),
        "qualified_without_email": sum(int(result.get("qualified_without_email") or 0) for result in results),
        "qualified_with_non_email_contact": sum(int(result.get("qualified_with_non_email_contact") or 0) for result in results),
        "qualified_without_supported_contact": sum(int(result.get("qualified_without_supported_contact") or 0) for result in results),
        "decisions": decisions,
        "searches": results,
    }
