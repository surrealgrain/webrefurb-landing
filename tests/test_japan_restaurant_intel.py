from __future__ import annotations

from pipeline.japan_restaurant_intel import (
    collect_restaurant_intel,
    contact_discovery_queries,
    coverage_with_contact,
    source_aware_discovery_queries,
)
from pipeline.sources.types import normalize_tabelog


def test_source_aware_queries_cover_japan_portals_and_contact_terms():
    queries = source_aware_discovery_queries(
        business_name="麺屋はるか",
        address="東京都渋谷区神南1-2-3",
        phone="03-1234-5678",
        category="ramen",
        max_queries=20,
    )

    assert any("site:tabelog.com" in query for query in queries)
    assert any("site:hotpepper.jp" in query for query in queries)
    assert any("site:ramendb.supleks.jp" in query for query in queries)
    assert any('"03-1234-5678"' in query for query in queries)
    assert any('"公式"' in query for query in queries)


def test_contact_queries_include_operator_company_route():
    queries = contact_discovery_queries(
        business_name="居酒屋かもめ",
        operator_company="株式会社かもめフーズ",
        address="東京都新宿区西新宿1-2-3",
    )

    assert '"居酒屋かもめ" "お問い合わせ"' in queries
    assert '"株式会社かもめフーズ" "お問い合わせ"' in queries
    assert any("会社概要" in query for query in queries)


def test_collect_restaurant_intel_expands_portals_to_official_site():
    def fake_web_search(*, query, **kwargs):
        if "site:tabelog.com" in query:
            return {"organic": [{
                "title": "麺屋はるか | 食べログ",
                "snippet": "東京都渋谷区神南1-2-3 03-1234-5678 ラーメン メニュー",
                "link": "https://tabelog.com/tokyo/A000/A000000/12345678/",
            }]}
        if "site:hotpepper.jp" in query:
            return {"organic": [{
                "title": "麺屋はるか | ホットペッパー",
                "snippet": "東京都渋谷区神南1-2-3 03-1234-5678 英語メニュー",
                "link": "https://www.hotpepper.jp/strJ000000001/",
            }]}
        if '"公式"' in query:
            return {"organic": [{
                "title": "麺屋はるか 公式サイト",
                "snippet": "東京都渋谷区神南1-2-3 お問い合わせ",
                "link": "https://menya-haruka.example.jp/",
            }]}
        return {"organic": []}

    def fake_fetch_page(url, timeout_seconds=8):
        if "tabelog.com" in url:
            return """
            <html><body>
              <h1>麺屋はるか</h1>
              <p>東京都渋谷区神南1-2-3 TEL 03-1234-5678 ラーメン メニュー</p>
              <a href="/redirect?url=https%3A%2F%2Fmenya-haruka.example.jp%2F">公式サイト</a>
              <a href="https://www.instagram.com/menya_haruka/">Instagram</a>
            </body></html>
            """
        if "hotpepper.jp" in url:
            return """
            <html><body>
              <h1>麺屋はるか</h1>
              <p>東京都渋谷区神南1-2-3 03-1234-5678 英語メニュー</p>
            </body></html>
            """
        return """
        <html><body>
          <h1>麺屋はるか</h1>
          <p>東京都渋谷区神南1-2-3 お問い合わせ ramen@example.jp</p>
        </body></html>
        """

    intel = collect_restaurant_intel(
        business_name="麺屋はるか",
        address="東京都渋谷区神南1-2-3",
        phone="03-1234-5678",
        category="ramen",
        place={
            "title": "麺屋はるか",
            "address": "東京都渋谷区神南1-2-3",
            "phoneNumber": "03-1234-5678",
            "placeId": "place-1",
            "link": "https://maps.google.com/?cid=1",
        },
        web_search=fake_web_search,
        fetch_page=fake_fetch_page,
    )

    assert intel.primary_official_site == "https://menya-haruka.example.jp"
    assert {"google", "tabelog", "hotpepper", "official_site"} <= set(intel.verified_by)
    assert intel.portal_urls["tabelog"].startswith("https://tabelog.com/")
    assert intel.coverage_signals["has_portal_menu"] is True
    assert intel.coverage_signals["has_english_menu_signal"] is True
    assert intel.social_links == ["https://www.instagram.com/menya_haruka"]
    assert coverage_with_contact(intel, contact_found=True)["coverage_score"] > intel.coverage_score


def test_tabelog_adapter_extracts_official_social_and_menu_signals():
    result = normalize_tabelog(
        """
        <html><body>
          <h1>麺屋はるか</h1>
          <p>東京都渋谷区神南1-2-3 TEL 03-1234-5678 メニュー</p>
          <a href="/redirect?url=https%3A%2F%2Fmenya-haruka.example.jp%2F">公式</a>
          <a href="https://x.com/menya_haruka">X</a>
        </body></html>
        """,
        "https://tabelog.com/tokyo/A000/A000000/12345678/",
    )

    assert result.source_name == "tabelog"
    assert result.name == "麺屋はるか"
    assert result.official_site_url == "https://menya-haruka.example.jp"
    assert result.social_links == ["https://x.com/menya_haruka"]
    assert result.menu_evidence_found is True
