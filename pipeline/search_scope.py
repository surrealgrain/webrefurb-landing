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
        return f"ramen and izakaya restaurants {place}"
    return f"{value} restaurants {place}"


def search_jobs_for_scope(*, category: str, city: str, query: str = "") -> list[dict[str, str]]:
    value = normalise_search_category(category)
    place = normalise_search_city(city)
    if value == "all":
        return [
            {"query": f"ramen restaurants {place}", "category": "ramen"},
            {"query": f"izakaya restaurants {place}", "category": "izakaya"},
        ]
    return [{"query": query or search_query_for_scope(category=value, city=place), "category": value}]


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
        "decisions": decisions,
        "searches": results,
    }
