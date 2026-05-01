from __future__ import annotations

import pytest

from pipeline.search_scope import (
    canonical_search_category,
    codex_search_jobs_for_scope,
    CODEX_EMAIL_PROVIDERS,
    CODEX_EXCLUDE,
    CODEX_SITE_PLATFORMS,
    CODEX_TABELOG_CITY_SITES,
    merge_search_results,
    search_category_label,
    search_jobs_for_scope,
    search_query_for_scope,
)


@pytest.mark.parametrize(
    ("category", "city", "expected_query", "expected_label"),
    [
        ("all", "all", "ordering-friction ramen izakaya yakitori tachinomi oden Japan", "supported ramen and izakaya-family shops"),
        ("all", "Kyoto", "ordering-friction ramen izakaya yakitori tachinomi oden Kyoto", "supported ramen and izakaya-family shops"),
        ("ramen", "all", "券売機 ラーメン Japan", "ramen shops"),
        ("ramen", "Kyoto", "券売機 ラーメン Kyoto", "ramen shops"),
        ("tsukemen", "Kyoto", "つけ麺 公式 メール Kyoto", "tsukemen shops"),
        ("yakitori", "Kyoto", "焼き鳥 公式 メール Kyoto", "yakitori shops"),
        ("tachinomi", "Osaka", "立ち飲み 公式 メール Osaka", "tachinomi shops"),
        ("izakaya", "all", "飲み放題 コース 居酒屋 Japan", "izakayas"),
        ("izakaya", "Kyoto", "飲み放題 コース 居酒屋 Kyoto", "izakayas"),
    ],
)
def test_search_scope_query_and_label(category, city, expected_query, expected_label):
    assert search_query_for_scope(category=category, city=city) == expected_query
    assert search_category_label(category) == expected_label


def test_all_category_fans_out_to_ramen_and_izakaya_for_specific_city():
    jobs = search_jobs_for_scope(category="all", city="Kyoto")
    queries = {job["query"] for job in jobs}
    job_ids = {job["job_id"] for job in jobs}

    assert "券売機 ラーメン Kyoto" in queries
    assert "食券 ラーメン Kyoto" in queries
    assert "ラーメン メニュー 写真 Kyoto" in queries
    assert "ラーメン 公式 お問い合わせ Kyoto" in queries
    assert "ラーメン 公式 メール Kyoto" in queries
    assert "ラーメン 公式 メニュー Kyoto" in queries
    assert "飲み放題 コース 居酒屋 Kyoto" in queries
    assert "お品書き 居酒屋 Kyoto" in queries
    assert "居酒屋 メニュー 写真 Kyoto" in queries
    assert "居酒屋 公式 お問い合わせ Kyoto" in queries
    assert "居酒屋 公式 メニュー Kyoto" in queries
    assert {"ramen_ticket_machine", "ramen_meal_ticket", "ramen_official_menu", "ramen_official_contact"} <= job_ids
    assert {"izakaya_nomihodai_course", "izakaya_oshinagaki", "izakaya_official_menu", "izakaya_official_contact"} <= job_ids
    # Negative-check jobs are NOT included — qualification detects these from page content
    assert "ramen_english_menu_check" not in job_ids
    assert "izakaya_multilingual_qr_check" not in job_ids
    assert all(job["purpose"] for job in jobs)
    assert all(job["expected_friction"] for job in jobs)


def test_specific_category_limits_to_that_category_and_city():
    ramen_jobs = search_jobs_for_scope(
        category="ramen",
        city="Kyoto",
    )
    assert {job["category"] for job in ramen_jobs} == {"ramen"}

    izakaya_jobs = search_jobs_for_scope(
        category="izakaya",
        city="Kyoto",
    )
    assert {job["category"] for job in izakaya_jobs} == {"izakaya"}


def test_adjacent_search_categories_map_to_existing_template_families():
    assert canonical_search_category("tsukemen") == "ramen"
    assert canonical_search_category("yakitori") == "izakaya"

    tsukemen_jobs = search_jobs_for_scope(category="tsukemen", city="Tokyo")
    yakitori_jobs = search_jobs_for_scope(category="yakitori", city="Tokyo")

    assert {job["category"] for job in tsukemen_jobs} == {"ramen"}
    assert {job["category"] for job in yakitori_jobs} == {"izakaya"}
    assert any("つけ麺" in job["query"] for job in tsukemen_jobs)
    assert any("焼き鳥" in job["query"] for job in yakitori_jobs)
    assert any(job["purpose"] == "official_email_lookup" for job in yakitori_jobs)


def test_old_generic_restaurant_queries_do_not_override_friction_first_jobs():
    jobs = search_jobs_for_scope(
        category="ramen",
        city="Kyoto",
        query="ramen restaurants Kyoto",
    )

    assert len(jobs) > 1
    assert jobs[0]["query"] == "券売機 ラーメン Kyoto"
    assert all(job["job_id"] != "operator_custom_query" for job in jobs)


def test_non_generic_operator_query_is_preserved_as_custom_search():
    assert search_jobs_for_scope(
        category="ramen",
        city="Kyoto",
        query="券売機 個人店 河原町",
    ) == [{
        "job_id": "operator_custom_query",
        "query": "券売機 個人店 河原町",
        "category": "ramen",
        "purpose": "operator_custom_search",
        "expected_friction": "operator_supplied",
    }]


def test_merge_search_results_sums_all_category_runs():
    merged = merge_search_results(
        [
            {
                "run_id": "ramen-run",
                "total_candidates": 20,
                "leads": 1,
                "qualified_without_email": 2,
                "qualified_with_non_email_contact": 1,
                "qualified_without_supported_contact": 1,
                "decisions": [{"business_name": "Ramen"}],
            },
            {
                "run_id": "izakaya-run",
                "total_candidates": 18,
                "leads": 3,
                "qualified_without_email": 4,
                "qualified_with_non_email_contact": 2,
                "qualified_without_supported_contact": 2,
                "decisions": [{"business_name": "Izakaya"}],
            },
        ],
        query="ramen and izakaya restaurants Kyoto",
        category="all",
    )

    assert merged["category"] == "all"
    assert merged["total_candidates"] == 38
    assert merged["leads"] == 4
    assert merged["qualified_without_email"] == 6
    assert merged["qualified_with_non_email_contact"] == 3
    assert merged["qualified_without_supported_contact"] == 3
    assert merged["decisions"] == [{"business_name": "Ramen"}, {"business_name": "Izakaya"}]


# ---------------------------------------------------------------------------
# Codex email-first search query generation tests
# ---------------------------------------------------------------------------

def test_codex_single_category_generates_correct_job_count():
    jobs = codex_search_jobs_for_scope(category="yakitori", city="Tokyo")
    expected_count = (2 * len(CODEX_EMAIL_PROVIDERS)) + len(CODEX_SITE_PLATFORMS)
    assert len(jobs) == expected_count


def test_codex_all_category_covers_all_specs():
    jobs = codex_search_jobs_for_scope(category="all", city="Tokyo")
    from pipeline.search_scope import SEARCH_CATEGORY_SPECS
    expected_count = len(SEARCH_CATEGORY_SPECS) * (
        (2 * len(CODEX_EMAIL_PROVIDERS)) + len(CODEX_SITE_PLATFORMS)
    )
    assert len(jobs) == expected_count


def test_codex_all_japan_fans_out_to_supported_tabelog_city_sites():
    jobs = codex_search_jobs_for_scope(category="ramen", city="all")
    expected_count = (
        (2 * len(CODEX_EMAIL_PROVIDERS) * len(CODEX_TABELOG_CITY_SITES))
        + len(CODEX_SITE_PLATFORMS)
    )
    assert len(jobs) == expected_count
    covered_sites = {
        site for site in CODEX_TABELOG_CITY_SITES.values()
        if any(site in job["query"] for job in jobs)
    }
    assert covered_sites == set(CODEX_TABELOG_CITY_SITES.values())


def test_codex_queries_contain_exclude_operators():
    jobs = codex_search_jobs_for_scope(category="ramen", city="Tokyo")
    for job in jobs:
        assert CODEX_EXCLUDE in job["query"], f"Missing exclude operators in: {job['query']}"


def test_codex_email_provider_queries_contain_at_sign():
    jobs = codex_search_jobs_for_scope(category="ramen", city="Tokyo")
    email_jobs = [j for j in jobs if j["purpose"].startswith("codex_tabelog_email_")]
    assert len(email_jobs) == 2 * len(CODEX_EMAIL_PROVIDERS)
    for job in email_jobs:
        assert "@" in job["query"], f"Missing @ in email-provider query: {job['query']}"
        assert "site:tabelog.com/tokyo" in job["query"], f"Missing Tabelog city scope: {job['query']}"
        assert ('"ジャンル"' in job["query"] or '"住所"' in job["query"]), f"Missing v1 Tabelog profile term: {job['query']}"


def test_codex_site_specific_queries_contain_site_operator():
    jobs = codex_search_jobs_for_scope(category="ramen", city="Tokyo")
    site_jobs = [j for j in jobs if j["purpose"] == "codex_site_specific"]
    assert len(site_jobs) == len(CODEX_SITE_PLATFORMS)
    for job in site_jobs:
        assert "site:" in job["query"], f"Missing site: in site-specific query: {job['query']}"


def test_codex_subcategory_maps_to_canonical_category():
    yakitori_jobs = codex_search_jobs_for_scope(category="yakitori", city="Tokyo")
    assert {j["category"] for j in yakitori_jobs} == {"izakaya"}

    tsukemen_jobs = codex_search_jobs_for_scope(category="tsukemen", city="Tokyo")
    assert {j["category"] for j in tsukemen_jobs} == {"ramen"}


def test_codex_subcategory_uses_correct_japanese_term():
    jobs = codex_search_jobs_for_scope(category="yakitori", city="Tokyo")
    assert all("焼き鳥" in j["query"] for j in jobs)

    jobs = codex_search_jobs_for_scope(category="tsukemen", city="Tokyo")
    assert all("つけ麺" in j["query"] for j in jobs)


def test_codex_job_ids_are_unique():
    jobs = codex_search_jobs_for_scope(category="all", city="Tokyo")
    job_ids = [j["job_id"] for j in jobs]
    assert len(job_ids) == len(set(job_ids))


def test_codex_queries_include_city():
    jobs = codex_search_jobs_for_scope(category="ramen", city="Osaka")
    for job in jobs:
        assert ("Osaka" in job["query"] or "tabelog.com/osaka" in job["query"]), f"Missing city in: {job['query']}"
