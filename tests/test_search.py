"""Tests for search contact filtering."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.business_name import business_name_is_suspicious, extract_business_name_candidates, resolve_business_name
from pipeline.record import normalise_lead_contacts
from pipeline import search


def _tabelog_result(link: str = "https://tabelog.com/tokyo/A000/A000000/12345678/") -> dict:
    return {"organic": [{"link": link}]}


def _codex_tabelog_profile_html() -> str:
    return """
    <html>
      <head><title>麺屋はるか - 渋谷/ラーメン | 食べログ</title></head>
      <body>
        <h1>麺屋はるか</h1>
        <section>
          <h2>店舗基本情報</h2>
          <table>
            <tr><th>店名</th><td>麺屋はるか</td></tr>
            <tr><th>ジャンル</th><td>ラーメン、つけ麺</td></tr>
            <tr><th>予約・お問い合わせ</th><td>owner＠menya-haruka.jp</td></tr>
            <tr><th>住所</th><td>東京都渋谷区神南1-2-3 大きな地図を見る</td></tr>
            <tr><th>ホームページ</th><td><a href="https://menya-haruka.jp/">公式サイト</a></td></tr>
          </table>
        </section>
        <section><h2>特徴・関連情報</h2></section>
      </body>
    </html>
    """


def test_candidate_window_zero_means_no_cap():
    candidates = [{"name": f"candidate-{idx}"} for idx in range(3)]

    assert search._candidate_window(candidates, 0) == candidates
    assert search._candidate_window(candidates, -1) == candidates
    assert search._candidate_window(candidates, 2) == candidates[:2]


def test_codex_email_text_extractor_normalizes_japanese_obfuscation():
    text = "お問い合わせ: owner＠menya-haruka.jp / info [at] menya-haruka.jp"

    assert search._extract_emails_from_text(text) == [
        "owner@menya-haruka.jp",
        "info@menya-haruka.jp",
    ]


def test_codex_tabelog_parser_extracts_profile_email_and_homepage(monkeypatch):
    url = "https://tabelog.com/tokyo/A000/A000000/12345678/"

    monkeypatch.setattr(search, "_fetch_page", lambda page_url, timeout_seconds=10: _codex_tabelog_profile_html())

    candidates = search._codex_parse_tabelog_profile(url, category="ramen")

    assert candidates == [{
        "name": "麺屋はるか",
        "email": "owner@menya-haruka.jp",
        "website": "https://menya-haruka.jp/",
        "snippet": "ラーメン、つけ麺",
        "source_url": url,
        "email_source_url": url,
        "address": "東京都渋谷区神南1-2-3",
        "city": "Tokyo",
        "tabelog_url": url,
        "profile_html": _codex_tabelog_profile_html(),
        "genre_jp": "ラーメン、つけ麺",
        "category": "ramen",
    }]


def test_codex_tabelog_parser_rejects_english_menu_filter_signal(monkeypatch):
    url = "https://tabelog.com/tokyo/A000/A000000/12345678/"
    html = _codex_tabelog_profile_html().replace(
        "<section><h2>特徴・関連情報</h2></section>",
        "<section><h2>特徴・関連情報</h2><p>サービス | 複数言語メニューあり（英語）</p></section>",
    )

    monkeypatch.setattr(search, "_fetch_page", lambda page_url, timeout_seconds=10: html)

    assert search._codex_parse_tabelog_profile(url, category="ramen") == []


def test_codex_tabelog_parser_rejects_tabelog_checkbox_signal(monkeypatch):
    url = "https://tabelog.com/tokyo/A000/A000000/12345678/"
    html = _codex_tabelog_profile_html().replace(
        "</body>",
        '<input type="checkbox" name="ChkEnglishMenu" value="1"></body>',
    )

    monkeypatch.setattr(search, "_fetch_page", lambda page_url, timeout_seconds=10: html)

    assert search._codex_parse_tabelog_profile(url, category="ramen") == []


def test_codex_search_qualifies_tabelog_profile_with_official_homepage(tmp_path, monkeypatch):
    url = "https://tabelog.com/tokyo/A000/A000000/12345678/"

    def fake_fetch_page(page_url, timeout_seconds=10):
        if "tabelog.com" in page_url:
            return _codex_tabelog_profile_html()
        return """
        <html><head><title>麺屋はるか</title></head><body>
          ラーメン メニュー 醤油ラーメン 900円 塩ラーメン 950円 味玉つけ麺 1050円
          東京都渋谷区神南1-2-3
        </body></html>
        """

    monkeypatch.setattr(search, "run_web_search", lambda **kwargs: _tabelog_result(url))
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)

    result = search.codex_search_and_qualify(
        query='site:tabelog.com/tokyo "@gmail.com" "ジャンル" "ラーメン" "予約可否"',
        category="ramen",
        state_root=tmp_path,
        search_provider="webserper",
    )

    assert result["leads"] == 1
    lead = json.loads(list((tmp_path / "leads").glob("*.json"))[0].read_text(encoding="utf-8"))
    assert lead["business_name"] == "麺屋はるか"
    assert lead["email"] == "owner@menya-haruka.jp"
    assert lead["website"] == "https://menya-haruka.jp/"
    assert lead["codex_tabelog_url"] == url
    assert lead["source_urls"]["tabelog"] == url


def test_extract_contact_email_from_mailto():
    html = '<a href="mailto:owner@example-ramen.jp">お問い合わせ</a>'
    assert search.find_contact_email("https://example-ramen.jp", html) == "owner@example-ramen.jp"


def test_extract_contact_email_skips_sentry_ingest_before_business_email():
    html = """
    <script>dsn="https://abc@o462166.ingest.sentry.io/123"</script>
    <a href="mailto:owner@example-ramen.jp">お問い合わせ</a>
    """

    assert search.find_contact_email("https://example-ramen.jp", html) == "owner@example-ramen.jp"


def test_contact_candidate_urls_add_deterministic_inquiry_paths_and_skip_reservations():
    html = """
    <a href="/reserve">ご予約</a>
    <a href="/booking">Book a table</a>
    """

    urls = search._contact_candidate_urls("https://example-ramen.jp/shop/sangenjaya", html, limit=4)

    assert "https://example-ramen.jp/reserve" not in urls
    assert "https://example-ramen.jp/booking" not in urls
    assert urls[:2] == ["https://example-ramen.jp/contact", "https://example-ramen.jp/contact/"]


def test_normalised_lead_contacts_skip_telemetry_email():
    contacts = normalise_lead_contacts({
        "contacts": [
            {"type": "email", "value": "abc@o462166.ingest.sentry.io", "actionable": True},
            {"type": "contact_form", "value": "https://real-ramen.jp/contact", "actionable": True},
        ],
        "email": "abc@o462166.ingest.sentry.io",
    })

    assert [contact["type"] for contact in contacts] == ["contact_form"]


def test_normalised_lead_contacts_preserve_required_field_metadata_and_block_phone_required_form():
    contacts = normalise_lead_contacts({
        "contacts": [{
            "type": "contact_form",
            "value": "https://real-ramen.jp/contact",
            "actionable": True,
            "has_form": True,
            "required_fields": ["name", "tel", "message"],
            "form_actions": ["/contact"],
        }],
    })

    assert contacts == []


def test_normalised_lead_contacts_block_unverified_contact_form_route():
    contacts = normalise_lead_contacts({
        "contacts": [{
            "type": "contact_form",
            "value": "https://real-ramen.jp/info/",
            "actionable": True,
        }],
    })

    assert contacts[0]["actionable"] is False
    assert contacts[0]["status"] == "reference_only"
    assert contacts[0]["unsupported_reason"] == "unverified_contact_form"


def test_normalised_lead_contacts_allow_verified_contact_form_without_required_fields():
    contacts = normalise_lead_contacts({
        "contacts": [{
            "type": "contact_form",
            "value": "https://real-ramen.jp/contact",
            "actionable": True,
            "has_form": True,
        }],
    })

    assert contacts[0]["actionable"] is True
    assert "unsupported_reason" not in contacts[0]


def test_search_skips_qualified_candidates_without_email(tmp_path, monkeypatch):
    """A qualified lead with no email or phone is still tracked but not persisted.
    The Japan gate requires address or phone; a placeId alone is insufficient."""
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Test Ramen",
            "website": "https://test-ramen.example",
            "address": "東京都渋谷区神南1-2-3",
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
        query="券売機 ラーメン Tokyo",
        serper_api_key="test-key",
        category="ramen",
        search_job={
            "job_id": "ramen_ticket_machine",
            "query": "券売機 ラーメン Tokyo",
            "category": "ramen",
            "purpose": "ticket_machine_lookup",
            "expected_friction": "ticket_machine",
        },
        state_root=tmp_path,
    )

    # Address and phone are reference metadata only; without e-mail or a contact form,
    # the candidate is not persisted for outreach.
    assert result["leads"] == 0
    assert result["qualified_without_supported_contact"] == 1
    assert result["decisions"][0]["lead"] is False


def test_search_deep_email_fallback_can_rescue_supported_contact_route(tmp_path, monkeypatch):
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Test Ramen",
            "website": "https://test-ramen.example",
            "address": "東京都渋谷区神南1-2-3",
            "phoneNumber": "",
            "placeId": "place-deep-email",
            "rating": 4.6,
            "ratingCount": 80,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        if "tabelog.com" in url:
            return "<html><head><title>Test Ramen | 食べログ</title></head><body><h1>Test Ramen</h1></body></html>"
        return "ラーメン メニュー 醤油ラーメン 900円 券売機 東京"

    def fake_deep_enrich(**kwargs):
        assert kwargs["business_name"] == "Test Ramen"
        return [{
            "type": "email",
            "value": "owner@test-ramen.example",
            "label": "general_business_contact",
            "href": "mailto:owner@test-ramen.example",
            "source": "email_discovery",
            "source_url": "https://test-ramen.example/contact",
            "confidence": "high",
            "discovered_at": "2026-04-30T00:00:00+00:00",
            "status": "discovered",
            "actionable": True,
        }]

    from pipeline.email_discovery import bridge

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", lambda **kwargs: _tabelog_result())
    monkeypatch.setattr(search, "DEEP_EMAIL_DISCOVERY_ENABLED", True)
    monkeypatch.setattr(bridge, "enrich_lead_inline", fake_deep_enrich)

    result = search.search_and_qualify(
        query="券売機 ラーメン Tokyo",
        serper_api_key="test-key",
        category="ramen",
        state_root=tmp_path,
    )

    lead = json.loads(list((tmp_path / "leads").glob("*.json"))[0].read_text(encoding="utf-8"))
    assert result["leads"] == 1
    assert result["qualified_without_supported_contact"] == 0
    assert result["qualified_without_email"] == 0
    assert lead["email"] == "owner@test-ramen.example"
    assert "email" in result["decisions"][0]["contact_route_types"]
    assert result["decisions"][0]["primary_contact_type"] == "email"


def test_search_skips_reservation_only_form_as_supported_contact(tmp_path, monkeypatch):
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Reserve Only Ramen",
            "website": "https://reserve-only.example",
            "address": "東京都渋谷区神南1-2-3",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-reserve-only",
            "rating": 4.6,
            "ratingCount": 80,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        if "tabelog.com" in url:
            return "<html><head><title>Reserve Only Ramen | 食べログ</title></head><body><h1>Reserve Only Ramen</h1></body></html>"
        return """<html><body>
        ラーメン メニュー 醤油ラーメン 900円 券売機 東京
        <form action="/reservation"><input name="name" required></form>
        </body></html>"""

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", lambda **kwargs: _tabelog_result())

    result = search.search_and_qualify(
        query="券売機 ラーメン Tokyo",
        serper_api_key="test-key",
        category="ramen",
        state_root=tmp_path,
    )

    assert result["leads"] == 0
    assert result["qualified_without_supported_contact"] == 1
    assert result["decisions"][0]["lead"] is False


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
        query="券売機 ラーメン Tokyo",
        serper_api_key="test-key",
        category="ramen",
        search_job={
            "job_id": "ramen_ticket_machine",
            "query": "券売機 ラーメン Tokyo",
            "category": "ramen",
            "purpose": "ticket_machine_lookup",
            "expected_friction": "ticket_machine",
        },
        state_root=tmp_path,
    )

    paths = list((tmp_path / "leads").glob("*.json"))
    assert result["leads"] == 1
    assert len(paths) == 1
    lead = json.loads(paths[0].read_text(encoding="utf-8"))
    assert lead["email"] == "owner@email-ramen.example"
    assert lead["source_query"] == "券売機 ラーメン Tokyo"
    assert lead["source_search_job"]["job_id"] == "ramen_ticket_machine"
    assert "ticket_machine_evidence" in lead["matched_friction_evidence"]
    assert "search_job:ticket_machine" in lead["matched_friction_evidence"]
    assert lead["outreach_asset_template_family"] == "dark_v4c"
    assert lead["outreach_assets_selected"] == [
        str(Path.cwd() / "assets" / "templates" / "ramen_food_menu.html"),
        str(Path.cwd() / "assets" / "templates" / "ticket_machine_guide.html"),
    ]
    assert lead["package_recommendation_reason"] == "ramen_ticket_machine_needs_counter_ready_mapping"
    assert lead["custom_quote_reason"] == ""
    assert result["decisions"][0]["source_search_job"]["job_id"] == "ramen_ticket_machine"
    assert "ticket_machine_evidence" in result["decisions"][0]["matched_friction_evidence"]


def test_search_expands_portal_website_to_official_site_before_contact_discovery(tmp_path, monkeypatch):
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "麺屋はるか",
            "website": "https://tabelog.com/tokyo/A000/A000000/12345678/",
            "address": "東京都渋谷区神南1-2-3",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-portal-expand",
            "rating": 4.6,
            "ratingCount": 80,
            "link": "https://maps.google.com/?cid=portal-expand",
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        if "tabelog.com" in url:
            return """
            <html><head><title>麺屋はるか | 食べログ</title></head>
            <body>
              <h1>麺屋はるか</h1>
              <p>東京都渋谷区神南1-2-3 TEL 03-1234-5678 ラーメン メニュー</p>
              <a href="/redirect?url=https%3A%2F%2Fmenya-haruka.example.jp%2F">公式サイト</a>
            </body></html>
            """
        return """
        <html><head><title>麺屋はるか | 公式</title></head>
        <body>
          <h1>麺屋はるか</h1>
          <p>東京都渋谷区神南1-2-3 ラーメン メニュー 醤油ラーメン 900円</p>
          <a href="mailto:owner@menya-haruka.example.jp">お問い合わせ</a>
        </body></html>
        """

    def fake_web_search(*, query, **kwargs):
        if "tabelog.com" in query:
            return _tabelog_result()
        if '"公式"' in query:
            return {"organic": [{
                "title": "麺屋はるか 公式",
                "snippet": "東京都渋谷区神南1-2-3 お問い合わせ",
                "link": "https://menya-haruka.example.jp/",
            }]}
        return {"organic": []}

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", fake_web_search)

    result = search.search_and_qualify(
        query="券売機 ラーメン Tokyo",
        serper_api_key="test-key",
        category="ramen",
        state_root=tmp_path,
    )

    lead = json.loads(list((tmp_path / "leads").glob("*.json"))[0].read_text(encoding="utf-8"))
    assert result["leads"] == 1
    assert lead["website"] == "https://menya-haruka.example.jp"
    assert lead["email"] == "owner@menya-haruka.example.jp"
    assert lead["portal_urls"]["tabelog"].startswith("https://tabelog.com/")
    assert lead["official_site_candidates"] == ["https://menya-haruka.example.jp"]
    assert lead["coverage_signals"]["has_official_site"] is True
    assert lead["coverage_signals"]["contact_found"] is True
    assert result["decisions"][0]["source_count"] >= 2


def test_search_uses_business_specific_ticket_machine_evidence(tmp_path, monkeypatch):
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Haruka Ramen",
            "website": "https://ticket-evidence.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-ticket-evidence",
            "rating": 4.6,
            "ratingCount": 80,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        if "tabelog.com" in url:
            return "<html><head><title>Haruka Ramen | 食べログ</title></head><body><h1>Haruka Ramen</h1></body></html>"
        return "<html><head><title>Haruka Ramen</title></head><body>ラーメン メニュー 醤油ラーメン 900円 owner@ticket-evidence.example</body></html>"

    def fake_web_search(*, query, **kwargs):
        if "tabelog.com" in query:
            return _tabelog_result()
        if "券売機" in query or "食券" in query:
            return {"organic": [{
                "title": "Haruka Ramen 券売機",
                "snippet": "Haruka Ramen は入口の券売機で食券を購入。醤油ラーメン、味玉、餃子のメニューがあります。",
                "link": "https://review.example/haruka-ticket-machine",
            }]}
        return {"organic": []}

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", fake_web_search)

    result = search.search_and_qualify(
        query="券売機 ラーメン Tokyo",
        serper_api_key="test-key",
        category="ramen",
        search_job={
            "job_id": "ramen_ticket_machine_tokyo",
            "query": "券売機 ラーメン Tokyo",
            "category": "ramen",
            "purpose": "ticket_machine_lookup",
            "expected_friction": "ticket_machine",
        },
        state_root=tmp_path,
    )

    lead = json.loads(list((tmp_path / "leads").glob("*.json"))[0].read_text(encoding="utf-8"))
    assert result["leads"] == 1
    assert lead["machine_evidence_found"] is True
    assert lead["establishment_profile"] == "ramen_ticket_machine"
    assert lead["lead_evidence_dossier"]["ticket_machine_state"] == "present"
    assert "https://review.example/haruka-ticket-machine" in lead["evidence_urls"]


def test_search_does_not_infer_ticket_machine_from_query_only(tmp_path, monkeypatch):
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Sora Ramen",
            "website": "https://no-ticket-proof.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-no-ticket-proof",
            "rating": 4.5,
            "ratingCount": 52,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        if "tabelog.com" in url:
            return "<html><head><title>Sora Ramen | 食べログ</title></head><body><h1>Sora Ramen</h1></body></html>"
        return "<html><head><title>Sora Ramen</title></head><body>ラーメン メニュー 塩ラーメン 900円 owner@no-ticket-proof.example</body></html>"

    def fake_web_search(*, query, **kwargs):
        if "tabelog.com" in query:
            return _tabelog_result()
        return {"organic": []}

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", fake_web_search)

    result = search.search_and_qualify(
        query="券売機 ラーメン Tokyo",
        serper_api_key="test-key",
        category="ramen",
        search_job={
            "job_id": "ramen_ticket_machine_tokyo",
            "query": "券売機 ラーメン Tokyo",
            "category": "ramen",
            "purpose": "ticket_machine_lookup",
            "expected_friction": "ticket_machine",
        },
        state_root=tmp_path,
    )

    lead = json.loads(list((tmp_path / "leads").glob("*.json"))[0].read_text(encoding="utf-8"))
    assert result["leads"] == 1
    assert lead["machine_evidence_found"] is False
    assert lead["establishment_profile"] == "ramen_only"
    assert lead["lead_evidence_dossier"]["ticket_machine_state"] == "unknown"


def test_search_blocks_chain_infrastructure_found_by_targeted_evidence(tmp_path, monkeypatch):
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "居酒屋みらい",
            "website": "https://chain-evidence.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-chain-evidence",
            "rating": 4.4,
            "ratingCount": 99,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        if "tabelog.com" in url:
            return "<html><head><title>居酒屋みらい | 食べログ</title></head><body><h1>居酒屋みらい</h1></body></html>"
        return "<html><head><title>居酒屋みらい</title></head><body>居酒屋 メニュー 飲み放題 コース 焼き鳥 owner@chain-evidence.example</body></html>"

    def fake_web_search(*, query, **kwargs):
        if "tabelog.com" in query:
            return _tabelog_result()
        if "チェーン" in query:
            return {"organic": [{
                "title": "居酒屋みらい 店舗一覧",
                "snippet": "居酒屋みらいは全国に35店舗を展開する居酒屋チェーンです。",
                "link": "https://chain-evidence.example/shops",
            }]}
        return {"organic": []}

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", fake_web_search)

    result = search.search_and_qualify(
        query="飲み放題 コース 居酒屋 Tokyo",
        serper_api_key="test-key",
        category="izakaya",
        search_job={
            "job_id": "izakaya_course_tokyo",
            "query": "飲み放題 コース 居酒屋 Tokyo",
            "category": "izakaya",
            "purpose": "course_drink_lookup",
            "expected_friction": "drink_or_course_rules",
        },
        state_root=tmp_path,
    )

    assert result["leads"] == 0
    assert result["decisions"][0]["rejection_reason"] == "chain_or_franchise_infrastructure"
    assert not list((tmp_path / "leads").glob("*.json"))


def test_targeted_evidence_rejects_broad_social_discovery_links():
    assert search._blocked_evidence_link("https://www.instagram.com/popular/%E4%BA%AC%E9%83%BD/")
    assert search._blocked_evidence_link("https://www.instagram.com/explore/tags/nomihodai/")
    assert search._blocked_evidence_link("https://www.facebook.com/some-shop")
    assert not search._blocked_evidence_link("https://tabelog.com/tokyo/A000/A000000/12345678/")


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


def test_business_name_resolver_strips_reservation_suffix_from_page_title():
    html = """
    <html>
      <head><title>Nihonshu Genka Sakagura Shinjukukusohonten Reservation</title></head>
      <body><h1>Nihonshu Genka Sakagura Shinjukukusohonten Reservation</h1></body>
    </html>
    """
    name, source = resolve_business_name(source_name="", html=html)
    assert name == "Nihonshu Genka Sakagura Shinjukukusohonten"
    assert source == "page_html"


def test_business_name_detector_flags_contact_route_like_values():
    assert business_name_is_suspicious("Email Route Izakaya") is True
    assert business_name_is_suspicious("owner@email-route-izakaya.test") is True
    assert business_name_is_suspicious("Primary route: Contact Form") is True
    assert business_name_is_suspicious("Visual Email Ramen") is True
    assert business_name_is_suspicious("Visual Phone Ramen") is True
    assert business_name_is_suspicious("Manual Contact Izakaya") is True
    assert business_name_is_suspicious("食べログ") is True
    assert business_name_is_suspicious("Shibuya/Izakaya (Japanese style tavern)") is True
    assert business_name_is_suspicious("Seibu Shinjuku/Izakaya (Japanese style tavern)") is True
    assert business_name_is_suspicious("Ramen restaurant") is True
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
        <form action="/contact">
          <input name="name" required>
          <input name="email" required>
          <textarea name="message" required></textarea>
          <button type="submit">送信</button>
        </form>
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
    assert {contact["type"] for contact in lead["contacts"]} >= {"contact_form", "walk_in", "map_url", "website"}
    assert "phone" not in {contact["type"] for contact in lead["contacts"]}
    assert lead["map_url"] == "https://maps.google.com/?cid=form-ramen"
    for contact in lead["contacts"]:
        assert contact["confidence"] in {"high", "medium", "low"}
        assert contact["discovered_at"]
        assert contact["status"]
        assert "source_url" in contact
    walk_in_contact = next(contact for contact in lead["contacts"] if contact["type"] == "walk_in")
    map_contact = next(contact for contact in lead["contacts"] if contact["type"] == "map_url")
    assert walk_in_contact["source_url"] == "https://maps.google.com/?cid=form-ramen"
    assert walk_in_contact["actionable"] is False
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
        <body><h1>麺屋はるか</h1>ラーメン メニュー 醤油ラーメン 900円 owner@name-fix.example</body></html>
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
    assert result["decisions"][0]["reason"] == "business_name_conflict"


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
        return "<html><body>ラーメン メニュー 醤油ラーメン 900円 confidence-ramen@example.jp</body></html>"

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


def test_search_blocks_google_confidence_override_when_official_name_conflicts(tmp_path, monkeypatch):
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Confidence Ramen",
            "website": "https://confidence-ramen.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-conflict-1",
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

    assert result["leads"] == 0
    assert result["decisions"][0]["reason"] == "business_name_conflict"


def test_search_keeps_single_source_name_review_blocked_when_google_override_missing(tmp_path, monkeypatch):
    """Single-source names can become review-blocked inventory without Google override."""
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "No Phone Ramen",
            "website": "https://nophone-ramen.example",
            "address": "東京都渋谷区神南1-2-3",
            "phoneNumber": "",  # No phone — override should NOT fire
            "placeId": "place-nophone-1",
            "rating": 4.5,
            "ratingCount": 120,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        return (
            "<html><head><title>No Phone Ramen | Official Site</title></head>"
            "<body><h1>No Phone Ramen</h1>ラーメン メニュー 醤油ラーメン 900円 "
            "owner@nophone-ramen.example</body></html>"
        )

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
    assert "google_confidence_override" not in lead["business_name_verified_by"]
    assert lead["business_name_review_status"] == "single_source_needs_review"
    assert lead["manual_review_required"] is True
    assert lead["launch_readiness_status"] == "manual_review"
    assert lead["pitch_ready"] is False
    assert lead["outreach_status"] == "needs_review"


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

    webserper_batch_without_review_count = {
        **strong_place,
        "ratingCount": None,
        "searchProvider": "webserper_google_maps_batch",
        "address": "東京都渋谷区神南1-2-3",
    }
    assert search._google_confidence_override(webserper_batch_without_review_count) is True

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


def test_search_blocks_qualified_lead_when_result_category_mismatches_query(tmp_path, monkeypatch):
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "麺屋はるか",
            "website": "https://category-mismatch.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-mismatch-1",
            "rating": 4.4,
            "ratingCount": 80,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        if "tabelog.com" in url:
            return "<html><head><title>麺屋はるか | 食べログ</title></head><body><h1>麺屋はるか</h1></body></html>"
        return "<html><head><title>麺屋はるか</title></head><body>ラーメン メニュー 醤油ラーメン 900円 owner@example.jp</body></html>"

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", lambda **kwargs: _tabelog_result())

    result = search.search_and_qualify(
        query="izakaya restaurants Tokyo",
        serper_api_key="test-key",
        category="izakaya",
        state_root=tmp_path,
    )

    assert result["leads"] == 0
    assert result["decisions"][0]["reason"] == "search_category_mismatch"


# ---------------------------------------------------------------------------
# Phase 2: Targeted evidence query tests
# ---------------------------------------------------------------------------

def test_targeted_evidence_includes_ticket_machine_for_generic_ramen():
    queries = search._targeted_evidence_queries(
        business_name="麺屋はるか",
        category="ramen",
        search_job={
            "job_id": "ramen_generic",
            "query": "ラーメン Tokyo",
            "category": "ramen",
            "purpose": "operator_custom_search",
            "expected_friction": "operator_supplied",
        },
    )
    assert len(queries) <= 4
    assert any("券売機" in q for q in queries), f"No ticket-machine query in {queries}"
    assert any("メニュー" in q for q in queries), f"No menu query in {queries}"
    assert any("英語メニュー" in q for q in queries), f"No English-solution query in {queries}"
    assert any("チェーン" in q for q in queries), f"No chain query in {queries}"


def test_targeted_evidence_includes_chain_expansion_query():
    queries = search._targeted_evidence_queries(
        business_name="居酒屋かもめ",
        category="izakaya",
        search_job={
            "job_id": "izakaya_generic",
            "query": "居酒屋 Tokyo",
            "category": "izakaya",
        },
    )
    assert len(queries) <= 4
    assert any("チェーン" in q and "展開" in q for q in queries), f"No chain expansion query in {queries}"


def test_targeted_evidence_respects_query_cap():
    queries = search._targeted_evidence_queries(
        business_name="テスト",
        category="ramen",
        search_job={
            "job_id": "test",
            "query": "券売機 ラーメン Tokyo",
            "category": "ramen",
            "purpose": "ticket_machine_lookup",
            "expected_friction": "ticket_machine",
        },
    )
    assert len(queries) <= 4


def test_search_blocks_lead_when_targeted_evidence_finds_existing_english_qr(tmp_path, monkeypatch):
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Solved Ramen",
            "website": "https://solved-ramen.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-solved-qr-1",
            "rating": 4.5,
            "ratingCount": 90,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        if "tabelog.com" in url:
            return "<html><head><title>Solved Ramen | 食べログ</title></head><body><h1>Solved Ramen</h1></body></html>"
        return (
            "<html><head><title>Solved Ramen</title></head>"
            "<body>ラーメン メニュー 醤油ラーメン 900円 owner@solved-ramen.example</body></html>"
        )

    def fake_web_search(*, query, **kwargs):
        if "tabelog.com" in query:
            return _tabelog_result()
        if "英語メニュー" in query:
            return {"organic": [{
                "title": "Solved Ramen English QR",
                "snippet": "Solved Ramen has English menu available and multilingual QR ordering.",
                "link": "https://review.example/solved-english-qr",
            }]}
        return {"organic": []}

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", fake_web_search)

    result = search.search_and_qualify(
        query="ラーメン Tokyo",
        serper_api_key="test-key",
        category="ramen",
        search_job={
            "job_id": "ramen_menu_tokyo",
            "query": "ラーメン メニュー Tokyo",
            "category": "ramen",
            "purpose": "menu_lookup",
            "expected_friction": "official_menu",
        },
        state_root=tmp_path,
    )

    assert result["leads"] == 0
    assert result["decisions"][0]["rejection_reason"] == "already_has_multilingual_ordering_solution"
    assert "already_solved_english_solution" in result["decisions"][0]["matched_friction_evidence"]


def test_solution_check_search_job_cannot_create_launch_lead(tmp_path, monkeypatch):
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Solved Ramen",
            "website": "https://solved-ramen.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-solved-job-1",
            "rating": 4.5,
            "ratingCount": 90,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        if "tabelog.com" in url:
            return "<html><head><title>Solved Ramen | 食べログ</title></head><body><h1>Solved Ramen</h1></body></html>"
        return (
            "<html><head><title>Solved Ramen</title></head>"
            "<body>ラーメン メニュー 醤油ラーメン 900円 owner@solved-ramen.example</body></html>"
        )

    def fake_web_search(*, query, **kwargs):
        if "tabelog.com" in query:
            return _tabelog_result()
        return {"organic": []}

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", fake_web_search)

    result = search.search_and_qualify(
        query="英語メニュー ラーメン Tokyo",
        serper_api_key="test-key",
        category="ramen",
        search_job={
            "job_id": "ramen_english_menu_check",
            "query": "英語メニュー ラーメン Tokyo",
            "category": "ramen",
            "purpose": "english_solution_check",
            "expected_friction": "english_menu_check",
        },
        state_root=tmp_path,
    )

    assert result["leads"] == 0
    assert result["decisions"][0]["reason"] == "already_solved_solution_check"
    assert result["decisions"][0]["english_menu_state"] == "usable_complete"


# ---------------------------------------------------------------------------
# Phase 3: Integration tests for recall diversity
# ---------------------------------------------------------------------------

def test_search_discovers_ticket_machine_from_generic_ramen_query(tmp_path, monkeypatch):
    """A generic ramen search (no ticket-machine keywords) should still
    discover ticket-machine evidence via targeted evidence queries."""
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Sora Ramen",
            "website": "https://generic-ramen.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-generic-ticket-1",
            "rating": 4.5,
            "ratingCount": 52,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        if "tabelog.com" in url:
            return "<html><head><title>Sora Ramen | 食べログ</title></head><body><h1>Sora Ramen</h1></body></html>"
        return (
            "<html><head><title>Sora Ramen</title></head>"
            "<body>ラーメン メニュー 塩ラーメン 900円 owner@generic-ramen.example</body></html>"
        )

    def fake_web_search(*, query, **kwargs):
        if "tabelog.com" in query:
            return _tabelog_result()
        if "券売機" in query:
            return {"organic": [{
                "title": "Sora Ramen 券売機",
                "snippet": "Sora Ramen は入口の券売機で食券を購入。塩ラーメン、味玉。",
                "link": "https://review.example/sora-ticket-machine",
            }]}
        return {"organic": []}

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", fake_web_search)

    result = search.search_and_qualify(
        query="ラーメン Tokyo",
        serper_api_key="test-key",
        category="ramen",
        search_job={
            "job_id": "ramen_generic_tokyo",
            "query": "ラーメン Tokyo",
            "category": "ramen",
            "purpose": "operator_custom_search",
            "expected_friction": "operator_supplied",
        },
        state_root=tmp_path,
    )

    assert result["leads"] == 1
    lead = json.loads(list((tmp_path / "leads").glob("*.json"))[0].read_text(encoding="utf-8"))
    assert lead["machine_evidence_found"] is True
    assert lead["establishment_profile"] == "ramen_ticket_machine"


def test_search_qualifies_plain_ramen_menu_only_lead(tmp_path, monkeypatch):
    """A generic ramen search should qualify a plain ramen shop with
    menu evidence but no ticket machine (the most common scenario)."""
    def fake_run_search(*, query, api_key, gl="jp", timeout_seconds=10):
        return [{
            "title": "Simple Ramen",
            "website": "https://simple-ramen.example",
            "address": "Tokyo",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-simple-1",
            "rating": 4.5,
            "ratingCount": 52,
        }]

    def fake_fetch_page(url, timeout_seconds=10):
        if "tabelog.com" in url:
            return "<html><head><title>Simple Ramen | 食べログ</title></head><body><h1>Simple Ramen</h1></body></html>"
        return (
            "<html><head><title>Simple Ramen</title></head>"
            "<body>ラーメン メニュー 醤油ラーメン 900円 owner@simple-ramen.example</body></html>"
        )

    def fake_web_search(*, query, **kwargs):
        if "tabelog.com" in query:
            return _tabelog_result()
        return {"organic": []}

    monkeypatch.setattr(search, "run_search", fake_run_search)
    monkeypatch.setattr(search, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(search, "run_web_search", fake_web_search)

    result = search.search_and_qualify(
        query="ラーメン Tokyo",
        serper_api_key="test-key",
        category="ramen",
        search_job={
            "job_id": "ramen_generic_tokyo",
            "query": "ラーメン Tokyo",
            "category": "ramen",
            "purpose": "operator_custom_search",
            "expected_friction": "operator_supplied",
        },
        state_root=tmp_path,
    )

    assert result["leads"] == 1
    lead = json.loads(list((tmp_path / "leads").glob("*.json"))[0].read_text(encoding="utf-8"))
    assert lead["machine_evidence_found"] is False
    assert lead["establishment_profile"] == "ramen_only"
