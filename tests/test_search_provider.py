from __future__ import annotations

import json
import urllib.parse

from pipeline import search_provider


def _ddg_result(*, title: str, link: str, snippet: str = "") -> str:
    encoded = urllib.parse.quote(link, safe="")
    return f"""
    <div class="result">
      <a class="result__a" href="//duckduckgo.com/l/?uddg={encoded}">{title}</a>
      <a class="result__snippet">{snippet}</a>
    </div>
    """


def test_duckduckgo_parser_returns_webserper_organic_shape():
    html = _ddg_result(
        title="遥ラーメン 公式サイト",
        link="https://haruka-ramen.example/?utm_source=search",
        snippet="東京都渋谷区神南1-2-3 ラーメン メニュー",
    )

    organic = search_provider._organic_results_from_duckduckgo_html(html)

    assert organic == [{
        "title": "遥ラーメン 公式サイト",
        "link": "https://haruka-ramen.example",
        "snippet": "東京都渋谷区神南1-2-3 ラーメン メニュー",
    }]


def test_duckduckgo_lite_parser_returns_webserper_organic_shape():
    encoded = urllib.parse.quote("https://izakaya-sai.example/", safe="")
    html = f"""
    <table>
      <tr><td><a rel="nofollow" class="result-link" href="//duckduckgo.com/l/?uddg={encoded}">居酒屋 彩 Sai 渋谷【公式】</a></td></tr>
      <tr><td class="result-snippet">東京都渋谷区 居酒屋 お品書き</td></tr>
    </table>
    """

    organic = search_provider._organic_results_from_duckduckgo_html(html)

    assert organic == [{
        "title": "居酒屋 彩 Sai 渋谷【公式】",
        "link": "https://izakaya-sai.example",
        "snippet": "東京都渋谷区 居酒屋 お品書き",
    }]


def test_webserper_organic_search_uses_duckduckgo_but_returns_provider_contract(monkeypatch):
    monkeypatch.setattr(
        search_provider,
        "_http_get_text",
        lambda *_, **__: _ddg_result(
            title="居酒屋みらい お品書き",
            link="https://mirai-izakaya.example/menu",
            snippet="飲み放題 コース 居酒屋",
        ),
    )

    data = search_provider.run_organic_search(
        query="飲み放題 コース 居酒屋 渋谷",
        provider="webserper",
    )

    assert data["searchParameters"]["provider"] == "webserper"
    assert data["organic"][0]["link"] == "https://mirai-izakaya.example/menu"
    assert data["organic"][0]["title"] == "居酒屋みらい お品書き"


def test_webserper_maps_search_enriches_directory_result_to_place(monkeypatch):
    ddg_html = _ddg_result(
        title="遥ラーメン (渋谷/ラーメン) - 食べログ",
        link="https://tabelog.com/tokyo/A1303/A130301/12345678/",
        snippet="渋谷駅近くのラーメン店。",
    )
    directory_html = """
    <html><body>
      <a href="https://tabelog.com/redirect?url=https%3A%2F%2Fharuka-ramen.example%2F%3Futm_source%3Dtabelog">
        公式サイト
      </a>
    </body></html>
    """
    official_html = """
    <html>
      <head><title>遥ラーメン | 公式サイト</title></head>
      <body>
        <h1>遥ラーメン</h1>
        <p>東京都渋谷区神南1-2-3 TEL 03-1234-5678</p>
        <p>ラーメン メニュー 醤油ラーメン 900円 券売機</p>
      </body>
    </html>
    """

    def fake_get(url: str, **_: object) -> str:
        if "duckduckgo.com" in url:
            return ddg_html
        if "tabelog.com" in url:
            return directory_html
        if "haruka-ramen.example" in url:
            return official_html
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(search_provider, "_google_maps_browser_search", lambda **kwargs: [])
    monkeypatch.setattr(search_provider, "_http_get_text", fake_get)

    data = search_provider.run_maps_search(
        query="券売機 ラーメン 渋谷",
        provider="webserper",
    )

    assert data["searchParameters"]["provider"] == "webserper"
    assert len(data["places"]) == 1
    place = data["places"][0]
    assert place["title"] == "遥ラーメン"
    assert place["website"] == "https://haruka-ramen.example"
    assert place["phoneNumber"] == "03-1234-5678"
    assert place["placeId"].startswith("webserper:")
    assert "東京都渋谷区" in place["address"]


def test_google_maps_detail_extraction_returns_webserper_place_contract():
    class FakeLocator:
        def inner_text(self, timeout: int = 0) -> str:
            return (
                "遥ラーメン\n"
                "4.3\n"
                "(123)\n"
                "ラーメン屋\n"
                "住所: 東京都渋谷区神南1-2-3\n"
                "電話番号: 03-1234-5678\n"
                "券売機 メニュー"
            )

    class FakePage:
        url = "https://www.google.com/maps/place/test/@35.661,139.699,17z/data=!19sChIJlocal123!3d35.661!4d139.699"

        def goto(self, url: str, wait_until: str = "", timeout: int = 0) -> None:
            self.url = FakePage.url

        def wait_for_timeout(self, timeout: int) -> None:
            return None

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator()

        def evaluate(self, script: str) -> list[dict[str, str]]:
            return [
                {"data": "address", "aria": "住所: 東京都渋谷区神南1-2-3", "href": "", "text": ""},
                {"data": "authority", "aria": "", "href": "https://haruka-ramen.example/?utm_source=maps", "text": "Website"},
                {"data": "phone:tel:03-1234-5678", "aria": "電話番号: 03-1234-5678", "href": "", "text": ""},
            ]

    place = search_provider._extract_google_maps_place(
        FakePage(),
        {"title": "遥ラーメン", "href": "https://www.google.com/maps/place/test/@35.661,139.699,17z/data=!19sChIJlocal123!3d35.661!4d139.699"},
        query="券売機 ラーメン 渋谷",
    )

    assert place is not None
    assert place["title"] == "遥ラーメン"
    assert place["website"] == "https://haruka-ramen.example"
    assert place["phoneNumber"] == "03-1234-5678"
    assert place["position"] == {"lat": 35.661, "lng": 139.699}
    assert place["rating"] == 4.3
    assert place["ratingCount"] == 123
    assert place["placeId"] == "ChIJlocal123"
    assert "券売機" in place["localEvidenceHtml"]


def test_google_maps_batch_payload_parser_returns_webserper_maps_contract():
    record = [None] * 228
    record[2] = ["〒150-0043 東京都渋谷区道玄坂２丁目６−１５ ユニ道玄坂 ４F"]
    record[4] = [None, None, None, None, None, None, None, 4.7]
    record[7] = ["https://www.hotpepper.jp/strJ003736326/?utm_source=maps", "hotpepper.jp"]
    record[9] = [None, None, 35.6590732, 139.6984933]
    record[10] = "0x60188dfa4984941b:0xd5caf7b58dfabdd"
    record[11] = "【全品3,300円食べ飲み放題】居酒屋均タロー渋谷店"
    record[13] = ["居酒屋"]
    record[18] = "〒150-0043 東京都渋谷区道玄坂２丁目６−１５ ユニ道玄坂 ４F 【全品3,300円食べ飲み放題】居酒屋均タロー渋谷店"
    record[39] = "〒150-0043 東京都渋谷区道玄坂２丁目６−１５ ユニ道玄坂 ４F"
    record[78] = "ChIJG5SESfqNGGAR3avfWHuvXA0"
    record[88] = ["食べ飲み放題の居酒屋"]
    record[178] = [["03-6455-1167", [["03-6455-1167", 1], ["+81 3-6455-1167", 2]]]]
    record[227] = [["0x60188dfa4984941b:0xd5caf7b58dfabdd", None, None, "/g/11ldgsskv6", "ChIJG5SESfqNGGAR3avfWHuvXA0"]]
    payload = ")]}'\n" + json.dumps([["query"], [[None, record], [None, record]]], ensure_ascii=False)

    places = search_provider._places_from_google_maps_search_payload(payload)

    assert len(places) == 1
    place = places[0]
    assert place["position"] == 1
    assert place["title"] == "【全品3,300円食べ飲み放題】居酒屋均タロー渋谷店"
    assert place["website"] == "https://www.hotpepper.jp/strJ003736326"
    assert place["phoneNumber"] == "03-6455-1167"
    assert place["latitude"] == 35.6590732
    assert place["longitude"] == 139.6984933
    assert place["placeId"] == "ChIJG5SESfqNGGAR3avfWHuvXA0"
    assert place["cid"] == str(int("d5caf7b58dfabdd", 16))
    assert "query_place_id=ChIJG5SESfqNGGAR3avfWHuvXA0" in place["mapUrl"]


def test_serper_provider_still_requires_key():
    assert search_provider.search_provider_requires_api_key("serper") is True
    assert search_provider.search_provider_requires_api_key("webserper") is False
    assert search_provider.configured_search_provider(None) == "webserper"


def test_local_provider_blocks_media_urls_and_directory_navigation_addresses():
    assert search_provider._blocked_candidate_url("https://tblg.k-img.com/restaurant/photo.jpg") is True
    assert search_provider._blocked_place_host("corporate.kakaku.com") is True
    assert search_provider._extract_japan_address("東京都の施設一覧をもっと見る") == ""
    assert search_provider._extract_japan_address("東京都渋谷区神南1-2-3 TEL 03-1234-5678") == "東京都渋谷区神南1-2-3"


def test_local_maps_queries_are_webrefurb_specific_not_general_serp():
    ramen_queries = search_provider._local_maps_queries("券売機 ラーメン Shibuya")
    izakaya_queries = search_provider._local_maps_queries("飲み放題 コース 居酒屋 Shibuya")

    assert "ラーメン 渋谷 公式サイト 東京都渋谷区 TEL" in ramen_queries
    assert "ラーメン 渋谷 メニュー 公式" in ramen_queries
    assert "居酒屋 渋谷 公式サイト 東京都渋谷区 お品書き" in izakaya_queries
    assert "居酒屋 渋谷 飲み放題 コース 公式" in izakaya_queries
