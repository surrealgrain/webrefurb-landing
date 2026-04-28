"""Tests for search contact filtering."""

from __future__ import annotations

import json

from pipeline.business_name import business_name_is_suspicious, extract_business_name_candidates, resolve_business_name
from pipeline import search


def _tabelog_result(link: str = "https://tabelog.com/tokyo/A000/A000000/12345678/") -> dict:
    return {"organic": [{"link": link}]}


def test_extract_contact_email_from_mailto():
    html = '<a href="mailto:owner@example-ramen.jp">お問い合わせ</a>'
    assert search.find_contact_email("https://example-ramen.jp", html) == "owner@example-ramen.jp"


def test_search_skips_qualified_candidates_without_email(tmp_path, monkeypatch):
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Test Ramen",
            "website": "https://test-ramen.example",
            "address": "",
            "phoneNumber": "",
            "placeId": "place-1",
            "rating": 4.6,
            "ratingCount": 80,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        if "tabelog.com" in url:
            return "<html><head><title>Test Ramen | 食べログ</title></head><body><h1>Test Ramen</h1></body></html>"
        return "ラーメン メニュー 醤油ラーメン 900円 券売機 東京"

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", lambda **kwargs: _tabelog_result())

    result = search.search_and_qualify(
        query="ramen restaurants Tokyo",
        serper_api_key="test-key",
        category="ramen",
        state_root=tmp_path,
    )

    assert result["leads"] == 0
    assert result["qualified_without_email"] == 1
    assert result["qualified_without_supported_contact"] == 1
    assert result["decisions"][0]["reason"] == "no_supported_contact_route_found"
    assert not list((tmp_path / "leads").glob("*.json"))


def test_search_persists_email_reachable_lead(tmp_path, monkeypatch):
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Haruka Ramen",
            "website": "https://email-ramen.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-2",
            "rating": 4.6,
            "ratingCount": 80,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        if "tabelog.com" in url:
            return "<html><head><title>Haruka Ramen | 食べログ</title></head><body><h1>Haruka Ramen</h1></body></html>"
        return "ラーメン メニュー 醤油ラーメン 900円 券売機 Tokyo owner@email-ramen.example"

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", lambda **kwargs: _tabelog_result())

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


def test_business_name_resolver_prefers_page_name_over_contact_like_source():
    html = """
    <html>
      <head><title>麺屋はるか | Official Site</title></head>
      <body><h1>麺屋はるか</h1></body>
    </html>
    """
    name, source = resolve_business_name(source_name="Email Route Izakaya", html=html)
    assert name == "麺屋はるか"
    assert source == "page_html"


def test_business_name_detector_flags_contact_route_like_values():
    assert business_name_is_suspicious("Email Route Izakaya") is True
    assert business_name_is_suspicious("owner@email-route-izakaya.test") is True
    assert business_name_is_suspicious("Primary route: Contact Form") is True
    assert business_name_is_suspicious("Visual Email Ramen") is True
    assert business_name_is_suspicious("Visual Phone Ramen") is True
    assert business_name_is_suspicious("Manual Contact Izakaya") is True
    assert business_name_is_suspicious("麺屋はるか") is False


def test_extract_business_name_candidates_reads_title_and_h1():
    html = """
    <html>
      <head><title>居酒屋かもめ | Official Site</title></head>
      <body><h1>居酒屋かもめ</h1></body>
    </html>
    """
    candidates = extract_business_name_candidates(html)
    assert "居酒屋かもめ" in candidates


def test_search_persists_non_email_lead_with_supported_contact_route(tmp_path, monkeypatch):
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Sakura Ramen",
            "website": "https://form-ramen.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-3",
            "rating": 4.6,
            "ratingCount": 80,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        if "tabelog.com" in url:
            return "<html><head><title>Sakura Ramen | 食べログ</title></head><body><h1>Sakura Ramen</h1></body></html>"
        return """<html><body>
        ラーメン メニュー 醤油ラーメン 900円 券売機 Tokyo
        <form action="/contact"></form>
        <a href="https://www.instagram.com/form_ramen/">Instagram</a>
        </body></html>"""

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", lambda **kwargs: _tabelog_result())

    result = search.search_and_qualify(
        query="ramen restaurants Tokyo",
        serper_api_key="test-key",
        category="ramen",
        state_root=tmp_path,
    )

    paths = list((tmp_path / "leads").glob("*.json"))
    assert result["leads"] == 1
    assert result["qualified_without_email"] == 1
    assert result["qualified_with_non_email_contact"] == 1
    assert len(paths) == 1
    lead = json.loads(paths[0].read_text(encoding="utf-8"))
    assert lead["email"] == ""
    assert lead["has_supported_contact_route"] is True
    assert lead["primary_contact"]["type"] == "contact_form"
    assert {contact["type"] for contact in lead["contacts"]} >= {"contact_form", "instagram", "phone", "walk_in", "website"}


def test_search_uses_page_name_when_source_name_is_contact_like(tmp_path, monkeypatch):
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Email Route Izakaya",
            "website": "https://name-fix.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-4",
            "rating": 4.6,
            "ratingCount": 80,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        if "tabelog.com" in url:
            return "<html><head><title>麺屋はるか | 食べログ</title></head><body><h1>麺屋はるか</h1></body></html>"
        return """
        <html><head><title>麺屋はるか | Official Site</title></head>
        <body><h1>麺屋はるか</h1>ラーメン メニュー 醤油ラーメン 900円</body></html>
        """

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", lambda **kwargs: _tabelog_result())

    result = search.search_and_qualify(
        query="ramen restaurants Tokyo",
        serper_api_key="test-key",
        category="ramen",
        state_root=tmp_path,
    )

    paths = list((tmp_path / "leads").glob("*.json"))
    assert result["leads"] == 1
    lead = json.loads(paths[0].read_text(encoding="utf-8"))
    assert lead["business_name"] == "麺屋はるか"


def test_search_blocks_lead_when_only_business_name_is_contact_like(tmp_path, monkeypatch):
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "owner@email-route-izakaya.test",
            "website": "https://name-block.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-5",
            "rating": 4.6,
            "ratingCount": 80,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        return "<html><body><p>ラーメン メニュー 醤油ラーメン 900円</p></body></html>"

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", lambda **kwargs: {"organic": []})

    result = search.search_and_qualify(
        query="ramen restaurants Tokyo",
        serper_api_key="test-key",
        category="ramen",
        state_root=tmp_path,
    )

    assert result["leads"] == 0
    assert result["decisions"][0]["reason"] == "invalid_business_name_detected"


def test_search_blocks_lead_when_name_has_no_two_source_match(tmp_path, monkeypatch):
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Solo Ramen",
            "website": "https://solo-ramen.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-6",
            "rating": 4.6,
            "ratingCount": 80,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        return "<html><head><title>Different Ramen | Official Site</title></head><body><h1>Different Ramen</h1>ラーメン メニュー 醤油ラーメン 900円</body></html>"

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", lambda **kwargs: {"organic": []})

    result = search.search_and_qualify(
        query="ramen restaurants Tokyo",
        serper_api_key="test-key",
        category="ramen",
        state_root=tmp_path,
    )

    assert result["leads"] == 0
    assert result["decisions"][0]["reason"] == "business_name_unverified"
