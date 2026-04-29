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
    assert search_jobs_for_scope(category="all", city="Kyoto") == [
        {"query": "券売機 ラーメン Kyoto", "category": "ramen"},
        {"query": "食券 ラーメン Kyoto", "category": "ramen"},
        {"query": "ラーメン メニュー 写真 Kyoto", "category": "ramen"},
        {"query": "site:ramendb.supleks.jp ラーメン Kyoto", "category": "ramen"},
        {"query": "英語メニュー ラーメン Kyoto", "category": "ramen"},
        {"query": "飲み放題 コース 居酒屋 Kyoto", "category": "izakaya"},
        {"query": "お品書き 居酒屋 Kyoto", "category": "izakaya"},
        {"query": "居酒屋 メニュー 写真 Kyoto", "category": "izakaya"},
        {"query": "site:hotpepper.jp 居酒屋 Kyoto 飲み放題", "category": "izakaya"},
        {"query": "英語メニュー 居酒屋 Kyoto", "category": "izakaya"},
    ]


def test_specific_category_limits_to_that_category_and_city():
    assert search_jobs_for_scope(
        category="ramen",
        city="Kyoto",
        query="ramen restaurants Kyoto",
    ) == [{"query": "ramen restaurants Kyoto", "category": "ramen"}]

    assert search_jobs_for_scope(
        category="izakaya",
        city="Kyoto",
        query="izakaya restaurants Kyoto",
    ) == [{"query": "izakaya restaurants Kyoto", "category": "izakaya"}]


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
