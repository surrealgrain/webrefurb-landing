from __future__ import annotations

import pytest

from pipeline.search_scope import (
    merge_search_results,
    search_category_label,
    search_jobs_for_scope,
    search_query_for_scope,
)


@pytest.mark.parametrize(
    ("category", "city", "expected_query", "expected_label"),
    [
        ("all", "all", "ordering-friction ramen izakaya Japan", "ramen shops and izakayas"),
        ("all", "Kyoto", "ordering-friction ramen izakaya Kyoto", "ramen shops and izakayas"),
        ("ramen", "all", "券売機 ラーメン Japan", "ramen shops"),
        ("ramen", "Kyoto", "券売機 ラーメン Kyoto", "ramen shops"),
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
    assert "site:ramendb.supleks.jp ラーメン Kyoto" in queries
    assert "ラーメン 公式 メニュー Kyoto" in queries
    assert "飲み放題 コース 居酒屋 Kyoto" in queries
    assert "お品書き 居酒屋 Kyoto" in queries
    assert "居酒屋 メニュー 写真 Kyoto" in queries
    assert "site:hotpepper.jp 居酒屋 Kyoto 飲み放題" in queries
    assert "site:tabelog.com 居酒屋 Kyoto メニュー" in queries
    assert "居酒屋 公式 メニュー Kyoto" in queries
    assert {"ramen_multilingual_qr_check", "ramen_mobile_order_check", "ramen_english_ticket_machine_check"} <= job_ids
    assert {"izakaya_multilingual_qr_check", "izakaya_mobile_order_check"} <= job_ids
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
