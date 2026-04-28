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
            "link": "https://maps.google.com/?cid=form-ramen",
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
    assert {contact["type"] for contact in lead["contacts"]} >= {"contact_form", "instagram", "phone", "walk_in", "map_url", "website"}
    assert lead["map_url"] == "https://maps.google.com/?cid=form-ramen"
    for contact in lead["contacts"]:
        assert contact["confidence"] in {"high", "medium", "low"}
        assert contact["discovered_at"]
        assert contact["status"]
        assert "source_url" in contact
    phone_contact = next(contact for contact in lead["contacts"] if contact["type"] == "phone")
    walk_in_contact = next(contact for contact in lead["contacts"] if contact["type"] == "walk_in")
    map_contact = next(contact for contact in lead["contacts"] if contact["type"] == "map_url")
    assert phone_contact["source_url"] == "https://maps.google.com/?cid=form-ramen"
    assert walk_in_contact["source_url"] == "https://maps.google.com/?cid=form-ramen"
    assert map_contact["href"] == "https://maps.google.com/?cid=form-ramen"
    assert map_contact["actionable"] is False


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
    """Weak Google signals (low reviews) should still block when no 2-source match."""
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Solo Ramen",
            "website": "https://solo-ramen.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-6",
            "rating": 4.6,
            "ratingCount": 10,  # Below the 50-review threshold
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


def test_search_allows_lead_with_google_confidence_override(tmp_path, monkeypatch):
    """Strong Google signals (rating 4.0+, 50+ reviews, phone, website) should
    allow through even when no second source agrees on the business name."""
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Confidence Ramen",
            "website": "https://confidence-ramen.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-conf-1",
            "rating": 4.5,
            "ratingCount": 120,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        return "<html><head><title>Different Name Ramen | Official Site</title></head><body><h1>Different Name Ramen</h1>ラーメン メニュー 醤油ラーメン 900円 confidence-ramen@example.jp</body></html>"

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", lambda **kwargs: {"organic": []})

    result = search.search_and_qualify(
        query="ramen restaurants Tokyo",
        serper_api_key="test-key",
        category="ramen",
        state_root=tmp_path,
    )

    assert result["leads"] == 1
    lead = json.loads(list((tmp_path / "leads").glob("*.json"))[0].read_text(encoding="utf-8"))
    assert "google_confidence_override" in lead["business_name_verified_by"]


def test_search_blocks_lead_when_google_confidence_override_conditions_not_met(tmp_path, monkeypatch):
    """Google confidence override should not fire when phone is missing."""
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "No Phone Ramen",
            "website": "https://nophone-ramen.example",
            "address": "Tokyo",
            "phoneNumber": "",  # No phone — override should NOT fire
            "placeId": "place-nophone-1",
            "rating": 4.5,
            "ratingCount": 120,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        return "<html><head><title>Different Name | Official Site</title></head><body><h1>Different Name</h1>ラーメン メニュー 醤油ラーメン 900円</body></html>"

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


def test_google_confidence_override_helper():
    """Unit test for the _google_confidence_override helper itself."""
    strong_place = {
        "placeId": "abc123",
        "rating": 4.3,
        "ratingCount": 80,
        "phoneNumber": "03-1234-5678",
        "website": "https://example.com",
    }
    assert search._google_confidence_override(strong_place) is True

    # Missing phone
    no_phone = {**strong_place, "phoneNumber": ""}
    assert search._google_confidence_override(no_phone) is False

    # Rating too low
    low_rating = {**strong_place, "rating": 3.8}
    assert search._google_confidence_override(low_rating) is False

    # Not enough reviews
    few_reviews = {**strong_place, "ratingCount": 30}
    assert search._google_confidence_override(few_reviews) is False

    # Missing placeId
    no_place_id = {**strong_place, "placeId": ""}
    assert search._google_confidence_override(no_place_id) is False


def _ramendb_result(link: str = "https://ramendb.supleks.jp/shop/12345") -> dict:
    return {"organic": [{"link": link}]}


def test_search_verifies_ramen_with_ramendb_when_tabelog_not_found(tmp_path, monkeypatch):
    """Ramen shops can be verified by Google + RamenDB when Tabelog has no match."""
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "麺屋ラーメン",
            "website": "https://ramendb-ramen.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-rdb-1",
            "rating": 4.4,
            "ratingCount": 60,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        if "ramendb.supleks.jp" in url:
            return "<html><head><title>麺屋ラーメン | ラーメンデータベース</title></head><body><h1>麺屋ラーメン</h1></body></html>"
        return "<html><head><title>麺屋ラーメン | Official Site</title></head><body><h1>麺屋ラーメン</h1>ラーメン メニュー 900円 ramendb-test@example.jp</body></html>"

    def fake_web_search(*, query, **kwargs):
        # Tabelog: no results; RamenDB: returns a match
        if "tabelog.com" in query:
            return {"organic": []}
        if "ramendb.supleks.jp" in query:
            return _ramendb_result()
        return {"organic": []}

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", fake_web_search)

    result = search.search_and_qualify(
        query="ramen restaurants Tokyo",
        serper_api_key="test-key",
        category="ramen",
        state_root=tmp_path,
    )

    assert result["leads"] == 1
    lead = json.loads(list((tmp_path / "leads").glob("*.json"))[0].read_text(encoding="utf-8"))
    assert "ramendb" in lead["business_name_verified_by"]
    assert "business_name_ramendb_url" in lead
    assert "ramendb.supleks.jp" in lead["business_name_ramendb_url"]


def test_search_does_not_call_ramendb_for_izakaya(tmp_path, monkeypatch):
    """RamenDB lookup should not fire for izakaya category."""
    web_search_calls = []

    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "居酒屋かもめ",
            "website": "https://izakaya-kamome.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-iz-1",
            "rating": 4.4,
            "ratingCount": 60,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        if "tabelog.com" in url:
            return "<html><head><title>居酒屋かもめ | 食べログ</title></head><body><h1>居酒屋かもめ</h1></body></html>"
        return "<html><head><title>居酒屋かもめ</title></head><body>居酒屋 メニュー 日本酒 500円 izakaya@example.jp</body></html>"

    def fake_web_search(*, query, **kwargs):
        web_search_calls.append(query)
        if "tabelog.com" in query:
            return _tabelog_result()
        return {"organic": []}

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", fake_web_search)

    result = search.search_and_qualify(
        query="izakaya restaurants Tokyo",
        serper_api_key="test-key",
        category="izakaya",
        state_root=tmp_path,
    )

    # Should have a lead (verified by tabelog + google)
    assert result["leads"] == 1
    # No RamenDB search should have been made
    ramendb_calls = [q for q in web_search_calls if "ramendb" in q]
    assert ramendb_calls == []
