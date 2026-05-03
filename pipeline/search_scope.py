from __future__ import annotations

from typing import Any


SEARCH_CATEGORY_SPECS: dict[str, dict[str, str]] = {
    "ramen": {
        "canonical": "ramen",
        "term": "ラーメン",
        "label": "ramen shops",
        "default_query": "券売機 ラーメン {place}",
    },
    "tsukemen": {
        "canonical": "ramen",
        "term": "つけ麺",
        "label": "tsukemen shops",
        "default_query": "つけ麺 公式 メール {place}",
    },
    "abura_soba": {
        "canonical": "ramen",
        "term": "油そば",
        "label": "abura soba shops",
        "default_query": "油そば 公式 メール {place}",
    },
    "mazesoba": {
        "canonical": "ramen",
        "term": "まぜそば",
        "label": "mazesoba shops",
        "default_query": "まぜそば 公式 メール {place}",
    },
    "tantanmen": {
        "canonical": "ramen",
        "term": "担々麺",
        "label": "tantanmen shops",
        "default_query": "担々麺 公式 メール {place}",
    },
    "chuka_soba": {
        "canonical": "ramen",
        "term": "中華そば",
        "label": "chuka soba shops",
        "default_query": "中華そば 公式 メール {place}",
    },
    "izakaya": {
        "canonical": "izakaya",
        "term": "居酒屋",
        "label": "izakayas",
        "default_query": "飲み放題 コース 居酒屋 {place}",
    },
    "yakitori": {
        "canonical": "izakaya",
        "term": "焼き鳥",
        "label": "yakitori shops",
        "default_query": "焼き鳥 公式 メール {place}",
    },
    "kushiyaki": {
        "canonical": "izakaya",
        "term": "串焼き",
        "label": "kushiyaki shops",
        "default_query": "串焼き 公式 メール {place}",
    },
    "yakiton": {
        "canonical": "izakaya",
        "term": "やきとん",
        "label": "yakiton shops",
        "default_query": "やきとん 公式 メール {place}",
    },
    "tachinomi": {
        "canonical": "izakaya",
        "term": "立ち飲み",
        "label": "tachinomi shops",
        "default_query": "立ち飲み 公式 メール {place}",
    },
    "oden": {
        "canonical": "izakaya",
        "term": "おでん",
        "label": "oden shops",
        "default_query": "おでん 公式 メール {place}",
    },
    "kushikatsu": {
        "canonical": "izakaya",
        "term": "串カツ",
        "label": "kushikatsu shops",
        "default_query": "串カツ 公式 メール {place}",
    },
    "kushiage": {
        "canonical": "izakaya",
        "term": "串揚げ",
        "label": "kushiage shops",
        "default_query": "串揚げ 公式 メール {place}",
    },
    "robatayaki": {
        "canonical": "izakaya",
        "term": "炉端焼き",
        "label": "robatayaki shops",
        "default_query": "炉端焼き 公式 メール {place}",
    },
    "seafood_izakaya": {
        "canonical": "izakaya",
        "term": "海鮮居酒屋",
        "label": "seafood izakayas",
        "default_query": "海鮮居酒屋 公式 メール {place}",
    },
    "sakaba": {
        "canonical": "izakaya",
        "term": "酒場",
        "label": "sakaba",
        "default_query": "酒場 公式 メール {place}",
    },
}

VALID_SEARCH_CATEGORIES = {"all", *SEARCH_CATEGORY_SPECS}
RAMEN_FAMILY_CATEGORIES = tuple(
    key for key, spec in SEARCH_CATEGORY_SPECS.items() if spec["canonical"] == "ramen"
)
IZAKAYA_FAMILY_CATEGORIES = tuple(
    key for key, spec in SEARCH_CATEGORY_SPECS.items() if spec["canonical"] == "izakaya"
)


def normalise_search_category(category: str) -> str:
    value = (category or "ramen").strip().lower()
    return value if value in VALID_SEARCH_CATEGORIES else "ramen"


def canonical_search_category(category: str) -> str:
    value = normalise_search_category(category)
    if value == "all":
        return "all"
    return SEARCH_CATEGORY_SPECS[value]["canonical"]


def normalise_search_city(city: str) -> str:
    value = (city or "").strip()
    return "Japan" if not value or value.lower() == "all" else value


def search_category_label(category: str) -> str:
    value = normalise_search_category(category)
    if value == "all":
        return "supported ramen and izakaya-family shops"
    return SEARCH_CATEGORY_SPECS[value]["label"]


def search_query_for_scope(*, category: str, city: str) -> str:
    value = normalise_search_category(category)
    place = normalise_search_city(city)
    if value == "all":
        return f"ordering-friction ramen izakaya yakitori tachinomi oden {place}"
    return SEARCH_CATEGORY_SPECS[value]["default_query"].format(place=place)


def search_category_metadata() -> dict[str, dict[str, str]]:
    """Return dashboard-safe category metadata from the Python source of truth."""
    return {
        "all": {
            "canonical": "all",
            "term": "",
            "label": search_category_label("all"),
            "default_query": "ordering-friction ramen izakaya yakitori tachinomi oden {place}",
        },
        **{
            key: {
                "canonical": spec["canonical"],
                "term": spec["term"],
                "label": spec["label"],
                "default_query": spec["default_query"],
            }
            for key, spec in SEARCH_CATEGORY_SPECS.items()
        },
    }


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
        job_category = "ramen" if value == "all" else canonical_search_category(value)
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
        _job(job_id="ramen_official_contact", query=f"ラーメン 公式 お問い合わせ {place}", category="ramen", purpose="official_contact_lookup", expected_friction="official_contact"),
        _job(job_id="ramen_official_email", query=f"ラーメン 公式 メール {place}", category="ramen", purpose="official_email_lookup", expected_friction="official_email"),
        _job(job_id="ramen_area_discovery", query=f"ラーメン 店 {place}", category="ramen", purpose="area_discovery", expected_friction="area_search"),
        _job(job_id="ramen_official_menu", query=f"ラーメン 公式 メニュー {place}", category="ramen", purpose="official_menu_lookup", expected_friction="official_menu"),
    ]
    izakaya_jobs = [
        _job(job_id="izakaya_nomihodai_course", query=f"飲み放題 コース 居酒屋 {place}", category="izakaya", purpose="drink_course_lookup", expected_friction="nomihodai_or_course"),
        _job(job_id="izakaya_oshinagaki", query=f"お品書き 居酒屋 {place}", category="izakaya", purpose="menu_lookup", expected_friction="printed_menu"),
        _job(job_id="izakaya_menu_photo", query=f"居酒屋 メニュー 写真 {place}", category="izakaya", purpose="menu_photo_lookup", expected_friction="menu_photo"),
        _job(job_id="izakaya_official_contact", query=f"居酒屋 公式 お問い合わせ {place}", category="izakaya", purpose="official_contact_lookup", expected_friction="official_contact"),
        _job(job_id="izakaya_area_discovery", query=f"居酒屋 店 {place}", category="izakaya", purpose="area_discovery", expected_friction="area_search"),
        _job(job_id="izakaya_official_menu", query=f"居酒屋 公式 メニュー {place}", category="izakaya", purpose="official_menu_lookup", expected_friction="official_menu"),
    ]
    if value == "all":
        adjacent_jobs: list[dict[str, str]] = []
        for adjacent in (
            "tsukemen", "abura_soba", "mazesoba", "yakitori", "tachinomi",
            "oden", "kushikatsu", "robatayaki", "seafood_izakaya",
        ):
            adjacent_jobs.extend(_category_family_jobs(category=adjacent, city=place))
        return [*ramen_jobs, *izakaya_jobs, *adjacent_jobs]
    if value == "ramen":
        return ramen_jobs
    if value == "izakaya":
        return izakaya_jobs
    return _category_family_jobs(category=value, city=place)


def _category_family_jobs(*, category: str, city: str) -> list[dict[str, str]]:
    spec = SEARCH_CATEGORY_SPECS[normalise_search_category(category)]
    canonical = spec["canonical"]
    term = spec["term"]
    slug = normalise_search_category(category)
    jobs = [
        _job(job_id=f"{slug}_official_email", query=f"{term} 公式 メール {city}", category=canonical, purpose="official_email_lookup", expected_friction="official_email"),
        _job(job_id=f"{slug}_official_contact", query=f"{term} 公式 お問い合わせ {city}", category=canonical, purpose="official_contact_lookup", expected_friction="official_contact"),
        _job(job_id=f"{slug}_menu_photo", query=f"{term} メニュー 写真 {city}", category=canonical, purpose="menu_photo_lookup", expected_friction="menu_photo"),
        _job(job_id=f"{slug}_official_menu", query=f"{term} 公式 メニュー {city}", category=canonical, purpose="official_menu_lookup", expected_friction="official_menu"),
        _job(job_id=f"{slug}_area_discovery", query=f"{term} 店 {city}", category=canonical, purpose="area_discovery", expected_friction="area_search"),
    ]
    if canonical == "ramen":
        jobs.insert(0, _job(job_id=f"{slug}_ticket_machine", query=f"券売機 {term} {city}", category=canonical, purpose="ticket_machine_lookup", expected_friction="ticket_machine"))
        jobs.insert(1, _job(job_id=f"{slug}_meal_ticket", query=f"食券 {term} {city}", category=canonical, purpose="ticket_machine_lookup", expected_friction="meal_ticket"))
    else:
        jobs.insert(0, _job(job_id=f"{slug}_oshinagaki", query=f"お品書き {term} {city}", category=canonical, purpose="menu_lookup", expected_friction="printed_menu"))
        jobs.insert(1, _job(job_id=f"{slug}_drinks", query=f"{term} ドリンク メニュー {city}", category=canonical, purpose="drink_menu_lookup", expected_friction="drink_menu"))
    return jobs


# ---------------------------------------------------------------------------
# Codex email-first search query generation
# ---------------------------------------------------------------------------

CODEX_EMAIL_PROVIDERS: tuple[str, ...] = (
    "gmail.com", "yahoo.co.jp", "icloud.com", "i.softbank.jp",
    "ezweb.ne.jp", "docomo.ne.jp", "hotmail.com", "outlook.jp",
    "me.com", "biglobe.ne.jp",
)

CODEX_SITE_PLATFORMS: tuple[str, ...] = (
    "ameblo.jp", "jimdosite.com", "wixsite.com", "peraichi.com",
    "fc2.com", "hpblog.jp", "hatenablog.com", "line.blog.jp",
)

CODEX_TABELOG_CITY_SITES: dict[str, str] = {
    "tokyo": "tabelog.com/tokyo",
    "osaka": "tabelog.com/osaka",
    "kyoto": "tabelog.com/kyoto",
    "sapporo": "tabelog.com/hokkaido/A0101",
    "fukuoka": "tabelog.com/fukuoka/A4001",
}

CODEX_EXCLUDE = "-求人 -採用 -通販 -チェーン -ホットペッパー -採用情報 -求人情報 -英語メニューあり -複数言語メニュー"


def _codex_city_sites(city: str) -> list[tuple[str, str]]:
    value = normalise_search_city(city).strip().lower()
    if value == "japan":
        return list(CODEX_TABELOG_CITY_SITES.items())
    if value in CODEX_TABELOG_CITY_SITES:
        return [(value, CODEX_TABELOG_CITY_SITES[value])]
    return [(value, "tabelog.com")]


def _codex_jobs_for_term(
    *, term: str, canonical: str, slug: str, city: str,
) -> list[dict[str, str]]:
    """Generate Codex email-provider and site-specific search jobs for one term."""
    jobs: list[dict[str, str]] = []
    place = normalise_search_city(city)
    for city_key, site in _codex_city_sites(place):
        for provider in CODEX_EMAIL_PROVIDERS:
            provider_slug = provider.replace(".", "_")
            jobs.append(_job(
                job_id=f"codex_{slug}_{city_key}_tabelog_genre_{provider_slug}",
                query=f'site:{site} "@{provider}" "ジャンル" "{term}" "予約可否" {CODEX_EXCLUDE}',
                category=canonical,
                purpose="codex_tabelog_email_genre",
                expected_friction="codex_tabelog_email_discovery",
            ))
            jobs.append(_job(
                job_id=f"codex_{slug}_{city_key}_tabelog_address_{provider_slug}",
                query=f'site:{site} "@{provider}" "{term}" "住所" {CODEX_EXCLUDE}',
                category=canonical,
                purpose="codex_tabelog_email_address",
                expected_friction="codex_tabelog_email_discovery",
            ))
    for platform in CODEX_SITE_PLATFORMS:
        platform_slug = platform.replace(".", "_")
        jobs.append(_job(
            job_id=f"codex_{slug}_site_{platform_slug}",
            query=f"{term} site:{platform} {place} メール お問い合わせ {CODEX_EXCLUDE}",
            category=canonical,
            purpose="codex_site_specific",
            expected_friction="codex_site_discovery",
        ))
    return jobs


def codex_search_jobs_for_scope(*, category: str, city: str) -> list[dict[str, str]]:
    """Generate Codex email-first search jobs for the given category and city.

    Each subcategory's Japanese term is drawn from ``SEARCH_CATEGORY_SPECS`` so
    that selecting e.g. "yakitori" produces queries with ``焼き鳥`` while the
    job's ``category`` field is the canonical ``izakaya``.
    """
    value = normalise_search_category(category)
    place = normalise_search_city(city)

    if value == "all":
        jobs: list[dict[str, str]] = []
        for spec_key, spec in SEARCH_CATEGORY_SPECS.items():
            jobs.extend(_codex_jobs_for_term(
                term=spec["term"], canonical=spec["canonical"],
                slug=spec_key, city=place,
            ))
        return jobs

    spec = SEARCH_CATEGORY_SPECS[value]
    return _codex_jobs_for_term(
        term=spec["term"], canonical=spec["canonical"],
        slug=value, city=place,
    )


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
