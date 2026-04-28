"""Tests for search contact filtering."""

from __future__ import annotations

import json

from pipeline import search


def test_extract_contact_email_from_mailto():
    html = '<a href="mailto:owner@example-ramen.jp">お問い合わせ</a>'
    assert search.find_contact_email("https://example-ramen.jp", html) == "owner@example-ramen.jp"


def test_search_skips_qualified_candidates_without_email(tmp_path, monkeypatch):
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Test Ramen",
            "website": "https://test-ramen.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-1",
            "rating": 4.6,
            "ratingCount": 80,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        return "ラーメン メニュー 醤油ラーメン 900円 券売機 東京"

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)

    result = search.search_and_qualify(
        query="ramen restaurants Tokyo",
        serper_api_key="test-key",
        category="ramen",
        state_root=tmp_path,
    )

    assert result["leads"] == 0
    assert result["qualified_without_email"] == 1
    assert result["decisions"][0]["reason"] == "no_business_email_found"
    assert not list((tmp_path / "leads").glob("*.json"))


def test_search_persists_email_reachable_lead(tmp_path, monkeypatch):
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Email Ramen",
            "website": "https://email-ramen.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-2",
            "rating": 4.6,
            "ratingCount": 80,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        return "ラーメン メニュー 醤油ラーメン 900円 券売機 Tokyo owner@email-ramen.example"

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)

    result = search.search_and_qualify(
        query="ramen restaurants Tokyo",
        serper_api_key="test-key",
        category="ramen",
        state_root=tmp_path,
    )

    paths = list((tmp_path / "leads").glob("*.json"))
    assert result["leads"] == 1
    assert len(paths) == 1
    lead = json.loads(paths[0].read_text(encoding="utf-8"))
    assert lead["email"] == "owner@email-ramen.example"
