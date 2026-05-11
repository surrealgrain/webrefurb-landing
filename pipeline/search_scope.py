from __future__ import annotations

from typing import Any


SEARCH_CATEGORY_SPECS: dict[str, dict[str, str]] = {
    "ramen": {
        "canonical": "ramen",
        "term": "ラーメン",
        "label": "ramen shops",
        "default_query": "ラーメン 公式 お問い合わせ {place}",
    },
    "izakaya": {
        "canonical": "izakaya",
        "term": "居酒屋",
        "label": "izakayas",
        "default_query": "居酒屋 公式 お問い合わせ {place}",
    },
    "skip": {
        "canonical": "skip",
        "term": "",
        "label": "skipped or manual-review restaurants",
        "default_query": "",
    },
}

VALID_SEARCH_CATEGORIES = {"all", *SEARCH_CATEGORY_SPECS}
RAMEN_FAMILY_CATEGORIES = tuple(
    key for key, spec in SEARCH_CATEGORY_SPECS.items() if spec["canonical"] == "ramen"
)
IZAKAYA_FAMILY_CATEGORIES = tuple(
    key for key, spec in SEARCH_CATEGORY_SPECS.items() if spec["canonical"] == "izakaya"
)

NATIONWIDE_TARGET_CITIES: tuple[dict[str, Any], ...] = (
    {"romaji": "Chiyoda", "ja": "千代田区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_1", "priority": 1},
    {"romaji": "Chuo", "ja": "中央区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_1", "priority": 2},
    {"romaji": "Minato", "ja": "港区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_1", "priority": 3},
    {"romaji": "Shinjuku", "ja": "新宿区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_1", "priority": 4},
    {"romaji": "Shibuya", "ja": "渋谷区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_1", "priority": 5},
    {"romaji": "Taito", "ja": "台東区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_1", "priority": 6},
    {"romaji": "Toshima", "ja": "豊島区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_1", "priority": 7},
    {"romaji": "Sumida", "ja": "墨田区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_1", "priority": 8},
    {"romaji": "Bunkyo", "ja": "文京区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_2", "priority": 9},
    {"romaji": "Koto", "ja": "江東区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_2", "priority": 10},
    {"romaji": "Shinagawa", "ja": "品川区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_2", "priority": 11},
    {"romaji": "Meguro", "ja": "目黒区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_2", "priority": 12},
    {"romaji": "Ota", "ja": "大田区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_2", "priority": 13},
    {"romaji": "Setagaya", "ja": "世田谷区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_2", "priority": 14},
    {"romaji": "Nakano", "ja": "中野区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_3", "priority": 15},
    {"romaji": "Suginami", "ja": "杉並区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_3", "priority": 16},
    {"romaji": "Kita", "ja": "北区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_3", "priority": 17},
    {"romaji": "Arakawa", "ja": "荒川区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_3", "priority": 18},
    {"romaji": "Itabashi", "ja": "板橋区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_3", "priority": 19},
    {"romaji": "Nerima", "ja": "練馬区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_3", "priority": 20},
    {"romaji": "Adachi", "ja": "足立区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_3", "priority": 21},
    {"romaji": "Katsushika", "ja": "葛飾区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_3", "priority": 22},
    {"romaji": "Edogawa", "ja": "江戸川区", "prefecture": "Tokyo", "tourist_volume_tier": "tier_3", "priority": 23},
    {"romaji": "Yokohama", "ja": "横浜市", "prefecture": "Kanagawa", "tourist_volume_tier": "tier_1", "priority": 24},
    {"romaji": "Kawasaki", "ja": "川崎市", "prefecture": "Kanagawa", "tourist_volume_tier": "tier_2", "priority": 25},
    {"romaji": "Saitama", "ja": "さいたま市", "prefecture": "Saitama", "tourist_volume_tier": "tier_2", "priority": 26},
    {"romaji": "Chiba", "ja": "千葉市", "prefecture": "Chiba", "tourist_volume_tier": "tier_2", "priority": 27},
    {"romaji": "Osaka", "ja": "大阪市", "prefecture": "Osaka", "tourist_volume_tier": "tier_1", "priority": 28},
    {"romaji": "Sakai", "ja": "堺市", "prefecture": "Osaka", "tourist_volume_tier": "tier_2", "priority": 29},
    {"romaji": "Toyonaka", "ja": "豊中市", "prefecture": "Osaka", "tourist_volume_tier": "tier_2", "priority": 30},
    {"romaji": "Kyoto", "ja": "京都市", "prefecture": "Kyoto", "tourist_volume_tier": "tier_1", "priority": 31},
    {"romaji": "Fukuoka Hakata", "ja": "福岡市博多区", "prefecture": "Fukuoka", "tourist_volume_tier": "tier_1", "priority": 32},
    {"romaji": "Fukuoka Tenjin", "ja": "福岡市中央区", "prefecture": "Fukuoka", "tourist_volume_tier": "tier_1", "priority": 33},
    {"romaji": "Sapporo", "ja": "札幌市", "prefecture": "Hokkaido", "tourist_volume_tier": "tier_1", "priority": 34},
    {"romaji": "Nagoya", "ja": "名古屋市", "prefecture": "Aichi", "tourist_volume_tier": "tier_1", "priority": 35},
    {"romaji": "Hiroshima", "ja": "広島市", "prefecture": "Hiroshima", "tourist_volume_tier": "tier_2", "priority": 36},
    {"romaji": "Naha", "ja": "那覇市", "prefecture": "Okinawa", "tourist_volume_tier": "tier_1", "priority": 37},
    {"romaji": "Kobe", "ja": "神戸市", "prefecture": "Hyogo", "tourist_volume_tier": "tier_1", "priority": 38},
    {"romaji": "Sendai", "ja": "仙台市", "prefecture": "Miyagi", "tourist_volume_tier": "tier_2", "priority": 39},
    {"romaji": "Nara", "ja": "奈良市", "prefecture": "Nara", "tourist_volume_tier": "tier_2", "priority": 40},
    {"romaji": "Kanazawa", "ja": "金沢市", "prefecture": "Ishikawa", "tourist_volume_tier": "tier_2", "priority": 41},
    {"romaji": "Kamakura", "ja": "鎌倉市", "prefecture": "Kanagawa", "tourist_volume_tier": "tier_3", "priority": 42},
)

NATIONWIDE_RESULT_LIMIT_PER_QUERY = 20
NATIONWIDE_PREFILTER_RULES = (
    "supported_category_only",
    "physical_address_required",
    "minimum_10_google_reviews",
    "exclude_50_plus_location_chains",
    "dedupe_existing_place_id",
    "evidence_classifier_must_not_skip",
)


def normalise_search_category(category: str) -> str:
    value = (category or "ramen").strip().lower()
    return value if value in VALID_SEARCH_CATEGORIES else "skip"


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
        return "supported ramen and izakaya shops"
    return SEARCH_CATEGORY_SPECS[value]["label"]


def search_query_for_scope(*, category: str, city: str) -> str:
    value = normalise_search_category(category)
    place = normalise_search_city(city)
    if value == "all":
        return f"English QR menu ramen izakaya {place}"
    if value == "skip":
        return ""
    return SEARCH_CATEGORY_SPECS[value]["default_query"].format(place=place)


def nationwide_target_cities() -> list[dict[str, Any]]:
    return [dict(city) for city in sorted(NATIONWIDE_TARGET_CITIES, key=lambda item: int(item["priority"]))]


def nationwide_search_queries_for_city(city: dict[str, Any]) -> list[str]:
    ja = str(city["ja"])
    romaji = str(city["romaji"])
    return [
        f"ラーメン店 {ja}",
        f"居酒屋 {ja}",
        f"ramen shop {romaji}",
        f"izakaya {romaji}",
        f"English menu ramen {romaji}",
        f"English menu izakaya {romaji}",
    ]


def nationwide_search_jobs() -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for city in nationwide_target_cities():
        for index, query in enumerate(nationwide_search_queries_for_city(city), start=1):
            jobs.append({
                "job_id": f"nationwide_{int(city['priority']):03d}_{index:02d}",
                "query": query,
                "city_ja": city["ja"],
                "city_romaji": city["romaji"],
                "prefecture": city["prefecture"],
                "tourist_volume_tier": city["tourist_volume_tier"],
                "priority": city["priority"],
                "max_results": NATIONWIDE_RESULT_LIMIT_PER_QUERY,
                "prefilter_rules": list(NATIONWIDE_PREFILTER_RULES),
                "external_send_allowed": False,
            })
    return jobs


def search_category_metadata() -> dict[str, dict[str, str]]:
    """Return dashboard-safe category metadata from the Python source of truth."""
    return {
        "all": {
            "canonical": "all",
            "term": "",
            "label": search_category_label("all"),
            "default_query": "English QR menu ramen izakaya {place}",
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
    if value == "skip":
        return []
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
        _job(job_id="ramen_menu_photo", query=f"ラーメン メニュー 写真 {place}", category="ramen", purpose="menu_photo_lookup", expected_friction="menu_photo"),
        _job(job_id="ramen_official_contact", query=f"ラーメン 公式 お問い合わせ {place}", category="ramen", purpose="official_contact_lookup", expected_friction="official_contact"),
        _job(job_id="ramen_official_email", query=f"ラーメン 公式 メール {place}", category="ramen", purpose="official_email_lookup", expected_friction="official_email"),
        _job(job_id="ramen_area_discovery", query=f"ラーメン 店 {place}", category="ramen", purpose="area_discovery", expected_friction="area_search"),
        _job(job_id="ramen_official_menu", query=f"ラーメン 公式 メニュー {place}", category="ramen", purpose="official_menu_lookup", expected_friction="official_menu"),
        _job(job_id="ramen_official_menu_photo", query=f"ラーメン 公式 メニュー 写真 {place}", category="ramen", purpose="official_menu_photo_lookup", expected_friction="official_menu_photo"),
    ]
    izakaya_jobs = [
        _job(job_id="izakaya_oshinagaki", query=f"お品書き 居酒屋 {place}", category="izakaya", purpose="menu_lookup", expected_friction="menu_source"),
        _job(job_id="izakaya_menu_photo", query=f"居酒屋 メニュー 写真 {place}", category="izakaya", purpose="menu_photo_lookup", expected_friction="menu_photo"),
        _job(job_id="izakaya_hotpepper_menu", query=f"site:hotpepper.jp 居酒屋 メニュー {place}", category="izakaya", purpose="hotpepper_menu_check", expected_friction="directory_menu"),
        _job(job_id="izakaya_tabelog_menu", query=f"site:tabelog.com 居酒屋 メニュー {place}", category="izakaya", purpose="tabelog_menu_check", expected_friction="directory_menu"),
        _job(job_id="izakaya_official_contact", query=f"居酒屋 公式 お問い合わせ {place}", category="izakaya", purpose="official_contact_lookup", expected_friction="official_contact"),
        _job(job_id="izakaya_area_discovery", query=f"居酒屋 店 {place}", category="izakaya", purpose="area_discovery", expected_friction="area_search"),
        _job(job_id="izakaya_official_menu", query=f"居酒屋 公式 メニュー {place}", category="izakaya", purpose="official_menu_lookup", expected_friction="official_menu"),
        _job(job_id="izakaya_official_social_menu", query=f"居酒屋 公式 SNS メニュー {place}", category="izakaya", purpose="official_social_menu_check", expected_friction="official_social_menu"),
    ]
    if value == "all":
        return [*ramen_jobs, *izakaya_jobs]
    if value == "ramen":
        return ramen_jobs
    if value == "izakaya":
        return izakaya_jobs
    return _category_family_jobs(category=value, city=place)


def _category_family_jobs(*, category: str, city: str) -> list[dict[str, str]]:
    spec = SEARCH_CATEGORY_SPECS[normalise_search_category(category)]
    canonical = spec["canonical"]
    if canonical == "skip":
        return []
    term = spec["term"]
    slug = normalise_search_category(category)
    jobs = [
        _job(job_id=f"{slug}_official_email", query=f"{term} 公式 メール {city}", category=canonical, purpose="official_email_lookup", expected_friction="official_email"),
        _job(job_id=f"{slug}_official_contact", query=f"{term} 公式 お問い合わせ {city}", category=canonical, purpose="official_contact_lookup", expected_friction="official_contact"),
        _job(job_id=f"{slug}_menu_photo", query=f"{term} メニュー 写真 {city}", category=canonical, purpose="menu_photo_lookup", expected_friction="menu_photo"),
        _job(job_id=f"{slug}_official_menu", query=f"{term} 公式 メニュー {city}", category=canonical, purpose="official_menu_lookup", expected_friction="official_menu"),
        _job(job_id=f"{slug}_area_discovery", query=f"{term} 店 {city}", category=canonical, purpose="area_discovery", expected_friction="area_search"),
    ]
    if canonical == "izakaya":
        jobs.insert(0, _job(job_id=f"{slug}_oshinagaki", query=f"お品書き {term} {city}", category=canonical, purpose="menu_lookup", expected_friction="menu_source"))
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

    Active categories are intentionally limited to ramen and izakaya. Unknown
    categories normalize to skip and produce no outbound discovery jobs.
    """
    value = normalise_search_category(category)
    place = normalise_search_city(city)

    if value == "all":
        jobs: list[dict[str, str]] = []
        for spec_key, spec in SEARCH_CATEGORY_SPECS.items():
            if spec["canonical"] == "skip":
                continue
            jobs.extend(_codex_jobs_for_term(
                term=spec["term"], canonical=spec["canonical"],
                slug=spec_key, city=place,
            ))
        return jobs

    if value == "skip":
        return []

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
