from __future__ import annotations

from pipeline.search_scope import (
    canonical_search_category,
    codex_search_jobs_for_scope,
    CODEX_EMAIL_PROVIDERS,
    CODEX_SITE_PLATFORMS,
    merge_search_results,
    search_category_label,
    search_jobs_for_scope,
    search_query_for_scope,
)


def test_only_active_search_categories_have_queries():
    assert search_query_for_scope(category="all", city="Kyoto") == "English QR menu ramen izakaya Kyoto"
    assert search_query_for_scope(category="ramen", city="Kyoto") == "ラーメン 公式 お問い合わせ Kyoto"
    assert search_query_for_scope(category="izakaya", city="Kyoto") == "居酒屋 公式 お問い合わせ Kyoto"
    assert search_query_for_scope(category="tsukemen", city="Kyoto") == ""
    assert canonical_search_category("tsukemen") == "skip"
    assert search_category_label("skip") == "skipped or manual-review restaurants"


def test_all_category_fans_out_to_ramen_and_izakaya_without_subcategory_jobs():
    jobs = search_jobs_for_scope(category="all", city="Kyoto")
    job_ids = {job["job_id"] for job in jobs}

    assert {job["category"] for job in jobs} == {"ramen", "izakaya"}
    assert "ramen_official_contact" in job_ids
    assert "izakaya_official_contact" in job_ids
    assert all("ticket" not in job["job_id"] for job in jobs)
    assert all("nomihodai" not in job["job_id"] for job in jobs)


def test_skip_and_unknown_categories_do_not_create_jobs():
    assert search_jobs_for_scope(category="skip", city="Tokyo") == []
    assert search_jobs_for_scope(category="sushi", city="Tokyo") == []
    assert codex_search_jobs_for_scope(category="sushi", city="Tokyo") == []


def test_non_generic_operator_query_is_preserved_as_custom_search():
    assert search_jobs_for_scope(
        category="ramen",
        city="Kyoto",
        query="英語 QR メニュー 個人店 河原町",
    ) == [{
        "job_id": "operator_custom_query",
        "query": "英語 QR メニュー 個人店 河原町",
        "category": "ramen",
        "purpose": "operator_custom_search",
        "expected_friction": "operator_supplied",
    }]


def test_codex_single_active_category_generates_email_first_jobs():
    jobs = codex_search_jobs_for_scope(category="ramen", city="Tokyo")
    expected_count = (2 * len(CODEX_EMAIL_PROVIDERS)) + len(CODEX_SITE_PLATFORMS)

    assert len(jobs) == expected_count
    assert {job["category"] for job in jobs} == {"ramen"}
    assert all("ラーメン" in job["query"] for job in jobs)


def test_codex_all_category_covers_only_ramen_and_izakaya():
    jobs = codex_search_jobs_for_scope(category="all", city="Tokyo")
    expected_count = 2 * ((2 * len(CODEX_EMAIL_PROVIDERS)) + len(CODEX_SITE_PLATFORMS))

    assert len(jobs) == expected_count
    assert {job["category"] for job in jobs} == {"ramen", "izakaya"}


def test_merge_search_results_sums_all_category_runs():
    merged = merge_search_results(
        [
            {"run_id": "ramen-run", "total_candidates": 20, "leads": 1, "qualified_without_email": 2, "qualified_with_non_email_contact": 1, "qualified_without_supported_contact": 1, "decisions": [{"business_name": "Ramen"}]},
            {"run_id": "izakaya-run", "total_candidates": 18, "leads": 3, "qualified_without_email": 4, "qualified_with_non_email_contact": 2, "qualified_without_supported_contact": 2, "decisions": [{"business_name": "Izakaya"}]},
        ],
        query="English QR menu ramen izakaya Kyoto",
        category="all",
    )

    assert merged["category"] == "all"
    assert merged["total_candidates"] == 38
    assert merged["leads"] == 4
    assert merged["decisions"] == [{"business_name": "Ramen"}, {"business_name": "Izakaya"}]
