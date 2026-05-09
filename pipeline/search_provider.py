from __future__ import annotations

import hashlib
import html as html_lib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

from .business_name import business_name_is_suspicious, extract_business_name_candidates, normalise_business_name
from .contact_crawler import _official_external_url, normalize_website_url
from .evidence import has_chain_or_franchise_infrastructure, is_chain_business
from .html_parser import extract_page_payload


WEB_SERPER_PROVIDER = "webserper"
SERPER_DEV_PROVIDER = "serper"
SEARXNG_PROVIDER = "searxng"
DEFAULT_SEARCH_PROVIDER = WEB_SERPER_PROVIDER
SEARCH_PROVIDER_ENV = "WEBREFURB_SEARCH_PROVIDER"
WEB_SERPER_PROVIDER_ALIASES = {"webserper", "web-serper", "web_serper", "local", "duckduckgo", "ddg", "webrefurb"}
SERPER_PROVIDER_ALIASES = {"serper", "serper.dev", "google-serper", "google_serper"}
SEARXNG_PROVIDER_ALIASES = {"searxng", "searx", "sear-x"}
SEARXNG_BASE_URL = os.environ.get("SEARXNG_BASE_URL", "http://127.0.0.1:8888")
DIRECTORY_HOST_TOKENS = (
    "tabelog.com",
    "hotpepper.jp",
    "ramendb.supleks.jp",
    "gnavi.co.jp",
    "gurunavi.com",
    "gorp.jp",
    "r.gnavi.co.jp",
    "retty.me",
    "hitosara.com",
    "paypaygourmet.yahoo.co.jp",
)
BLOCKED_PLACE_HOST_TOKENS = (
    "google.",
    "maps.google.",
    "search.yahoo.co.jp",
    "map.yahoo.co.jp",
    "instagram.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "tiktok.com",
    "pinterest.com",
    "mixi.jp",
    "line.me",
    "lin.ee",
    "tripadvisor.",
    "yelp.",
    "k-img.com",
    "kakaku.com",
    "app.link",
    "maps.gmfoods",
    "uber.com",
    "ubereats.com",
    "wolt.com",
    "demae-can.com",
    "出前館",
)
RESERVATION_ROUTE_HOST_TOKENS = (
    "tablecheck.com",
    "ebica.jp",
    "toreta.in",
    "yoyaku",
    "reserve",
    "reservation",
    "point.recruit.co.jp",
    "maps.gmfoods",
)
RESERVATION_ROUTE_PATH_TOKENS = (
    "reserve",
    "reservation",
    "booking",
    "book-a-table",
    "yoyaku",
    "予約",
    "shop-list",
    "store-list",
    "shoplist",
)
VENDOR_OR_ARTICLE_HOST_TOKENS = (
    "kenbaiki",
    "ticket-machine",
    "register",
    "selfregister",
    "change-machine",
    "bizcan",
    "cookpit",
    "activitv",
    "hpplus.jp",
    "nonno",
    "tokyoramenoftheyear.com",
)
VENDOR_OR_ARTICLE_TEXT_TOKENS = (
    "おすすめ",
    "選",
    "比較",
    "解説",
    "補助金",
    "導入",
    "ランキング",
    "まとめ",
    "ガイド",
    "column",
    "best ",
    "guide",
)
JP_PREFECTURE_PREFIXES = (
    "東京都", "大阪府", "京都府", "北海道",
    "神奈川県", "千葉県", "埼玉県", "愛知県", "兵庫県", "福岡県",
    "静岡県", "茨城県", "広島県", "宮城県", "長野県", "新潟県",
    "富山県", "石川県", "福井県", "山梨県", "岐阜県", "三重県",
    "滋賀県", "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県",
    "山口県", "徳島県", "香川県", "愛媛県", "高知県",
    "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
)
RAMEN_TOKENS = (
    "ラーメン", "らーめん", "らぁめん", "拉麺", "ramen",
    "中華そば", "中華蕎麦", "つけ麺", "油そば", "まぜそば",
    "abura soba", "mazesoba", "chuka soba",
)
SOBA_TOKENS = ("そば", "蕎麦", "手打ちそば", "手打ち蕎麦", "soba")
IZAKAYA_TOKENS = ("居酒屋", "izakaya", "飲み放題", "お品書き", "コース", "焼鳥", "焼き鳥")
MEDIA_PATH_RE = re.compile(r"(?i)\.(?:avif|gif|jpe?g|png|svg|webp)(?:$|[?#])")
CITY_ALIASES = {
    "tokyo": "東京",
    "shibuya": "渋谷",
    "shinjuku": "新宿",
    "ueno": "上野",
    "sangenjaya": "三軒茶屋",
    "sangen-jaya": "三軒茶屋",
    "kichijoji": "吉祥寺",
    "kagurazaka": "神楽坂",
    "jinbocho": "神保町",
    "jim bocho": "神保町",
    "kyoto": "京都",
    "gion": "祇園",
    "osaka": "大阪",
    "namba": "難波",
    "nara": "奈良",
    "kanazawa": "金沢",
    "hakone": "箱根",
    "sapporo": "札幌",
    "fukuoka": "福岡",
    "hiroshima": "広島",
    "okinawa": "沖縄",
    "kamakura": "鎌倉",
    "kobe": "神戸",
    "nagoya": "名古屋",
}
AREA_HINTS = {
    "渋谷": "東京都渋谷区",
    "Shibuya": "東京都渋谷区",
    "新宿": "東京都新宿区",
    "Shinjuku": "東京都新宿区",
    "上野": "東京都台東区",
    "Ueno": "東京都台東区",
    "三軒茶屋": "東京都世田谷区",
    "Sangenjaya": "東京都世田谷区",
    "Sangen-Jaya": "東京都世田谷区",
    "吉祥寺": "東京都武蔵野市",
    "Kichijoji": "東京都武蔵野市",
    "神楽坂": "東京都新宿区",
    "Kagurazaka": "東京都新宿区",
    "神保町": "東京都千代田区",
    "Jinbocho": "東京都千代田区",
    "祇園": "京都市東山区",
    "Gion": "京都市東山区",
    "難波": "大阪市中央区",
    "Namba": "大阪市中央区",
}


class SearchProviderError(RuntimeError):
    """Raised when a configured search provider cannot complete a request."""


def configured_search_provider(provider: str | None = None) -> str:
    value = str(provider or os.environ.get(SEARCH_PROVIDER_ENV) or DEFAULT_SEARCH_PROVIDER).strip().lower()
    if value in SERPER_PROVIDER_ALIASES:
        return SERPER_DEV_PROVIDER
    if value in SEARXNG_PROVIDER_ALIASES:
        return SEARXNG_PROVIDER
    if value in WEB_SERPER_PROVIDER_ALIASES:
        return WEB_SERPER_PROVIDER
    raise SearchProviderError(f"unsupported search provider: {value}")


def search_provider_requires_api_key(provider: str | None = None) -> bool:
    return configured_search_provider(provider) == SERPER_DEV_PROVIDER


def _searxng_available() -> bool:
    """Check if the local SearXNG instance is reachable."""
    try:
        req = urllib.request.Request(f"{SEARXNG_BASE_URL}/search?q=test&format=json", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def run_maps_search(
    *,
    query: str,
    api_key: str = "",
    gl: str = "jp",
    timeout_seconds: int = 10,
    provider: str | None = None,
) -> dict[str, Any]:
    provider_name = configured_search_provider(provider)
    if provider_name == SERPER_DEV_PROVIDER:
        return _serper_maps_search(query=query, api_key=api_key, gl=gl, timeout_seconds=timeout_seconds)
    if provider_name == SEARXNG_PROVIDER:
        return _webserper_maps_search(query=query, gl=gl, timeout_seconds=timeout_seconds)
    return _webserper_maps_search(query=query, gl=gl, timeout_seconds=timeout_seconds)


def run_organic_search(
    *,
    query: str,
    api_key: str = "",
    gl: str = "jp",
    timeout_seconds: int = 10,
    provider: str | None = None,
) -> dict[str, Any]:
    provider_name = configured_search_provider(provider)
    if provider_name == SERPER_DEV_PROVIDER:
        return _serper_organic_search(query=query, api_key=api_key, gl=gl, timeout_seconds=timeout_seconds)
    if provider_name == SEARXNG_PROVIDER:
        return _searxng_organic_search(query=query, gl=gl, timeout_seconds=timeout_seconds)
    return _webserper_organic_search(query=query, gl=gl, timeout_seconds=timeout_seconds)


def _serper_maps_search(*, query: str, api_key: str, gl: str, timeout_seconds: int) -> dict[str, Any]:
    if not api_key:
        raise SearchProviderError("Serper Maps search requires SERPER_API_KEY or --api-key")
    payload = json.dumps({"q": query, "gl": gl}).encode("utf-8")
    request = urllib.request.Request("https://google.serper.dev/maps", data=payload, headers={
        "Content-Type": "application/json",
        "X-API-KEY": api_key,
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = _http_error_body(exc)
        suffix = f": {body}" if body else ""
        raise SearchProviderError(f"Serper Maps search HTTP {exc.code}{suffix}") from exc


def _serper_organic_search(*, query: str, api_key: str, gl: str, timeout_seconds: int) -> dict[str, Any]:
    if not api_key:
        raise SearchProviderError("Serper organic search requires SERPER_API_KEY or --api-key")
    payload = json.dumps({"q": query, "gl": gl}).encode("utf-8")
    request = urllib.request.Request("https://google.serper.dev/search", data=payload, headers={
        "Content-Type": "application/json",
        "X-API-KEY": api_key,
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = _http_error_body(exc)
        suffix = f": {body}" if body else ""
        raise SearchProviderError(f"Serper organic search HTTP {exc.code}{suffix}") from exc


def _searxng_organic_search(
    *,
    query: str,
    gl: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Search via local SearXNG instance (aggregates Google, DDG, Brave, etc.)."""
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "language": "ja" if gl == "jp" else "en",
    })
    url = f"{SEARXNG_BASE_URL}/search?{params}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise SearchProviderError(f"SearXNG search failed: {exc}") from exc

    organic: list[dict[str, str]] = []
    seen_links: set[str] = set()
    for result in data.get("results", []):
        link = normalize_website_url(str(result.get("url") or ""))
        if not link or link in seen_links:
            continue
        host = _host(link)
        if _blocked_place_host(host) or _blocked_candidate_url(link):
            continue
        seen_links.add(link)
        organic.append({
            "title": str(result.get("title", "")),
            "snippet": str(result.get("content", "")),
            "link": link,
            "sourceEngine": str(result.get("engine", "searxng")),
        })

    return {
        "searchParameters": {
            "q": query,
            "gl": gl,
            "engine": "searxng",
            "provider": SEARXNG_PROVIDER,
        },
        "organic": organic,
    }


def _webserper_organic_search(
    *,
    query: str,
    gl: str,
    timeout_seconds: int,
    engines: tuple[str, ...] = ("yahoo_japan", "duckduckgo_lite"),
) -> dict[str, Any]:
    organic: list[dict[str, str]] = []
    seen_links: set[str] = set()
    source_runs: list[dict[str, Any]] = []

    engine_specs = {
        "yahoo_japan": (
            lambda: _yahoo_japan_html(query=query, gl=gl, timeout_seconds=timeout_seconds),
            _organic_results_from_yahoo_japan_html,
        ),
        "duckduckgo_lite": (
            lambda: _duckduckgo_html(query=query, gl=gl, timeout_seconds=timeout_seconds),
            _organic_results_from_duckduckgo_html,
        ),
    }
    selected_engines = tuple(engine for engine in engines if engine in engine_specs) or ("yahoo_japan", "duckduckgo_lite")
    for engine in selected_engines:
        fetcher, parser = engine_specs[engine]
        results, source_run = _organic_source_results(engine=engine, fetcher=fetcher, parser=parser)
        source_runs.append(source_run)
        for result in results:
            link = normalize_website_url(str(result.get("link") or ""))
            if not link or link in seen_links:
                continue
            host = _host(link)
            if _blocked_place_host(host) or _blocked_candidate_url(link):
                continue
            seen_links.add(link)
            organic.append({**result, "link": link, "sourceEngine": engine})

    if not organic and source_runs and all(source.get("error") for source in source_runs):
        errors = "; ".join(f"{source['engine']}={source.get('error')}" for source in source_runs)
        raise SearchProviderError(f"WebSerper organic search failed across all engines: {errors}")

    organic.sort(key=lambda result: (-_organic_result_score(result, query), str(result.get("link") or "")))
    engine_label = "+".join(selected_engines)
    return {
        "searchParameters": {
            "q": query,
            "gl": gl,
            "engine": engine_label,
            "engines": list(selected_engines),
            "provider": WEB_SERPER_PROVIDER,
            "sourceRuns": source_runs,
        },
        "organic": organic,
    }


def _webserper_maps_search(*, query: str, gl: str, timeout_seconds: int) -> dict[str, Any]:
    source_runs: list[dict[str, Any]] = []
    query_mode = _query_discovery_mode(query)
    if query_mode == "directory_extraction":
        places = _organic_places_for_queries(
            query=query,
            queries=_directory_extraction_queries(query),
            gl=gl,
            timeout_seconds=timeout_seconds,
            source_runs=source_runs,
            organic_engines=("yahoo_japan",),
        )
        return _webserper_maps_payload(
            query=query,
            gl=gl,
            places=places,
            source_runs=source_runs,
            engine="official_site_directory_extract",
            fallback_engine="yahoo_japan+duckduckgo_lite",
        )

    browser_places, browser_run = _google_maps_places_with_retry(query=query, gl=gl, timeout_seconds=timeout_seconds)
    source_runs.append(browser_run)
    if browser_places:
        browser_places = _first_party_google_maps_places(
            browser_places,
            query=query,
            gl=gl,
            timeout_seconds=timeout_seconds,
        )
    if browser_places:
        organic_places: list[dict[str, Any]] = []
        if _query_should_merge_organic_discovery(query):
            organic_places = _organic_places_for_queries(
                query=query,
                queries=_official_discovery_queries(query),
                gl=gl,
                timeout_seconds=timeout_seconds,
                source_runs=source_runs,
            )
        merged_places = _merge_places_by_site_or_name([*browser_places, *organic_places])
        engine = "google_maps_batch_browser" if str(browser_places[0].get("searchProvider") or "") == "webserper_google_maps_batch" else "google_maps_browser"
        return {
            "searchParameters": {
                "q": query,
                "gl": gl,
                "engine": engine,
                "organic_merge_engine": "yahoo_japan+duckduckgo_lite" if organic_places else "",
                "provider": WEB_SERPER_PROVIDER,
                "sourceRuns": source_runs,
            },
            "places": merged_places[:_local_place_limit()],
        }

    places = _organic_places_for_queries(
        query=query,
        queries=_local_maps_queries(query),
        gl=gl,
        timeout_seconds=timeout_seconds,
        source_runs=source_runs,
    )
    if len(places) >= _local_place_limit():
        return _webserper_maps_payload(query=query, gl=gl, places=places, source_runs=source_runs)

    if not places and source_runs and all(run.get("error") for run in source_runs):
        errors = "; ".join(f"{run['engine']}={run.get('error')}" for run in source_runs)
        raise SearchProviderError(f"WebSerper maps search failed across all engines: {errors}")
    return _webserper_maps_payload(query=query, gl=gl, places=places, source_runs=source_runs)


def _organic_source_results(
    *,
    engine: str,
    fetcher: Any,
    parser: Any,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    attempts = _search_retry_attempts()
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            html = fetcher()
            results = parser(html)
            return results, {
                "engine": engine,
                "attempt_count": attempt,
                "recovered_by_retry": attempt > 1,
                "result_count": len(results),
            }
        except Exception as exc:
            last_error = exc
            if attempt < attempts and _is_retryable_search_error(exc):
                time.sleep(min(0.25 * attempt, 1.0))
                continue
            break
    return [], {
        "engine": engine,
        "attempt_count": attempt,
        "recovered_by_retry": False,
        "result_count": 0,
        "error_type": type(last_error).__name__ if last_error else "",
        "error": str(last_error or ""),
    }


def _google_maps_places_with_retry(*, query: str, gl: str, timeout_seconds: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    attempts = _search_retry_attempts()
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            places = _google_maps_browser_search(query=query, gl=gl, timeout_seconds=timeout_seconds)
            return places, {
                "engine": "google_maps_browser",
                "attempt_count": attempt,
                "recovered_by_retry": attempt > 1,
                "result_count": len(places),
                "fallback_engine": "" if places else "official_site_organic",
            }
        except Exception as exc:
            last_error = exc
            if attempt < attempts and _is_retryable_search_error(exc):
                time.sleep(min(0.25 * attempt, 1.0))
                continue
            break
    return [], {
        "engine": "google_maps_browser",
        "attempt_count": attempt,
        "recovered_by_retry": False,
        "result_count": 0,
        "fallback_engine": "official_site_organic",
        "error_type": type(last_error).__name__ if last_error else "",
        "error": str(last_error or ""),
    }


def _is_retryable_search_error(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError) and exc.code in {429, 500, 502, 503, 504}:
        return True
    return isinstance(exc, (TimeoutError, urllib.error.URLError)) or "timeout" in type(exc).__name__.lower()


def _search_retry_attempts() -> int:
    return _env_int("WEBREFURB_SEARCH_RETRY_ATTEMPTS", default=2, minimum=1, maximum=4)


def _google_maps_browser_search(*, query: str, gl: str, timeout_seconds: int) -> list[dict[str, Any]]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return []

    places: list[dict[str, Any]] = []
    search_payloads: list[str] = []
    seen: set[str] = set()
    browser = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                locale="ja-JP",
                geolocation={"latitude": 35.658, "longitude": 139.701},
                permissions=["geolocation"],
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
                ),
            )
            page = context.new_page()
            page.set_default_timeout(max(5_000, min(timeout_seconds * 1000, 20_000)))

            def collect_search_payload(response: Any) -> None:
                try:
                    if "google.com/search?tbm=map" in str(response.url):
                        search_payloads.append(response.text())
                except Exception:
                    return

            page.on("response", collect_search_payload)
            url = "https://www.google.com/maps/search/" + urllib.parse.quote(query) + "?hl=ja&gl=jp"
            page.goto(url, wait_until="domcontentloaded", timeout=max(10_000, min(timeout_seconds * 1000, 30_000)))
            page.wait_for_timeout(_maps_batch_wait_ms())
            for payload in search_payloads:
                batch_places = _places_from_google_maps_search_payload(payload)
                if batch_places:
                    context.close()
                    return batch_places[:_local_place_limit()]

            cards = _maps_result_cards(page)
            for card in cards[:_local_place_limit()]:
                key = card.get("href") or card.get("title") or ""
                if not key or key in seen:
                    continue
                seen.add(key)
                place = _extract_google_maps_place(page, card, query=query)
                if place:
                    place["positionRank"] = len(places) + 1
                    places.append(place)
            context.close()
    except Exception:
        return places
    finally:
        try:
            if browser:
                browser.close()
        except Exception:
            pass
    return places


def _maps_batch_wait_ms() -> int:
    return _env_int("WEBREFURB_LOCAL_MAPS_BATCH_WAIT_MS", default=3_500, minimum=1_000, maximum=10_000)


def _maps_wait_ms() -> int:
    return _env_int("WEBREFURB_LOCAL_MAPS_WAIT_MS", default=5_000, minimum=1_000, maximum=15_000)


def _places_from_google_maps_search_payload(payload: str) -> list[dict[str, Any]]:
    try:
        source = str(payload or "")
        if source.startswith(")]}'"):
            source = source.split("\n", 1)[1] if "\n" in source else source[4:]
        data = json.loads(source)
    except Exception:
        return []

    entries = _google_maps_place_entries(data)
    places: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        place = _place_from_google_maps_record(entry, position=len(places) + 1)
        if not place:
            continue
        dedup_key = str(place.get("placeId") or place.get("cid") or place.get("title") or "")
        if not dedup_key or dedup_key in seen:
            continue
        seen.add(dedup_key)
        places.append(place)
        if len(places) >= _local_place_limit():
            break
    return places


def _google_maps_place_entries(data: Any) -> list[list[Any]]:
    groups: list[list[list[Any]]] = []

    def is_place_record(value: Any) -> bool:
        return (
            isinstance(value, list)
            and len(value) > 80
            and isinstance(_nested(value, 11), str)
            and isinstance(_nested(value, 9), list)
            and (isinstance(_nested(value, 10), str) or isinstance(_nested(value, 78), str))
        )

    def walk(value: Any) -> None:
        if not isinstance(value, list):
            return
        group: list[list[Any]] = []
        for item in value:
            candidate = item[1] if isinstance(item, list) and len(item) > 1 else item
            if is_place_record(candidate):
                group.append(candidate)
        if group:
            groups.append(group)
        for item in value:
            walk(item)

    walk(data)
    if not groups:
        return []
    return max(groups, key=len)


def _place_from_google_maps_record(record: list[Any], *, position: int) -> dict[str, Any] | None:
    title = _string_at(record, 11)
    if not title:
        return None

    coords = _list_at(record, 9)
    latitude = _float_at(coords, 2)
    longitude = _float_at(coords, 3)
    rating = _float_at(_list_at(record, 4), 7)
    rating_count = _rating_count_from_maps_record(record)
    website = normalize_website_url(_string_at(_list_at(record, 7), 0))
    phone = _string_at(_nested(record, 178, 0), 0)
    cid_hex = _string_at(record, 10) or _string_at(_nested(record, 227, 0), 0)
    cid = _google_maps_decimal_cid(cid_hex)
    place_id = _string_at(record, 78) or _string_at(_nested(record, 227, 0), 4)
    types = [str(item) for item in (_list_at(record, 13) or []) if isinstance(item, str)]
    address = _string_at(record, 39) or _extract_japan_address(_string_at(record, 18))
    if not address:
        address = _string_at(_nested(record, 2), 0)
    description = _string_at(_nested(record, 88), 0)
    map_url = _google_maps_place_url(title=title, place_id=place_id, cid=cid_hex)

    place = {
        "position": position,
        "title": title,
        "name": title,
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
        "rating": rating,
        "ratingCount": rating_count,
        "type": types[0] if types else "",
        "types": types,
        "website": website,
        "phoneNumber": phone,
        "cid": cid or cid_hex,
        "placeId": place_id or f"local:{hashlib.sha1((cid_hex or title).encode('utf-8')).hexdigest()[:16]}",
        "link": map_url,
        "mapUrl": map_url,
        "searchProvider": "webserper_google_maps_batch",
        "localEvidenceHtml": _maps_evidence_html(
            name=title,
            map_url=map_url,
            text=_maps_record_evidence_text(
                title=title,
                rating=rating,
                rating_count=rating_count,
                types=types,
                address=address,
                phone=phone,
                website=website,
                description=description,
            ),
        ),
    }
    return place


def _maps_record_evidence_text(
    *,
    title: str,
    rating: float | None,
    rating_count: int | None,
    types: list[str],
    address: str,
    phone: str,
    website: str,
    description: str,
) -> str:
    lines = [
        title,
        f"rating: {rating}" if rating is not None else "",
        f"reviews: {rating_count}" if rating_count is not None else "",
        " / ".join(types),
        address,
        phone,
        website,
        description,
    ]
    return "\n".join(line for line in lines if line)


def _rating_count_from_maps_record(record: list[Any]) -> int | None:
    # The Maps batch result often omits public review counts in Japanese local
    # packs. Keep this isolated so we can support the field when it appears
    # without confusing unrelated counters for Google review volume.
    for path in ((52,), (52, 3), (4, 8)):
        value = _nested(record, *path)
        parsed = _int_from_value(value)
        if parsed is not None and parsed >= 0:
            return parsed
    return None


def _google_maps_place_url(*, title: str, place_id: str, cid: str) -> str:
    if place_id:
        return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(title) + "&query_place_id=" + urllib.parse.quote(place_id)
    if cid:
        return "https://www.google.com/maps?cid=" + urllib.parse.quote(_google_maps_decimal_cid(cid) or cid)
    return "https://www.google.com/maps/search/" + urllib.parse.quote(title)


def _google_maps_decimal_cid(cid: str) -> str:
    raw = str(cid or "")
    if ":" in raw:
        raw = raw.rsplit(":", 1)[-1]
    try:
        return str(int(raw, 16)) if raw.startswith("0x") else raw
    except ValueError:
        return ""


def _nested(value: Any, *path: int) -> Any:
    current = value
    for index in path:
        if not isinstance(current, list) or index >= len(current):
            return None
        current = current[index]
    return current


def _list_at(value: Any, index: int) -> list[Any]:
    item = _nested(value, index)
    return item if isinstance(item, list) else []


def _string_at(value: Any, index: int) -> str:
    item = _nested(value, index)
    return str(item).strip() if isinstance(item, str) else ""


def _float_at(value: Any, index: int) -> float | None:
    item = _nested(value, index)
    if isinstance(item, (int, float)):
        return float(item)
    return None


def _int_from_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        return int(cleaned) if cleaned.isdigit() else None
    return None


def _maps_result_cards(page: Any) -> list[dict[str, str]]:
    try:
        cards = page.evaluate(
            """() => Array.from(document.querySelectorAll('a.hfpxzc')).map((a) => ({
                title: a.getAttribute('aria-label') || '',
                href: a.href || ''
            })).filter((item) => item.title && item.href)"""
        )
    except Exception:
        return []
    if not isinstance(cards, list):
        return []
    return [
        {"title": str(card.get("title") or ""), "href": str(card.get("href") or "")}
        for card in cards
        if isinstance(card, dict)
    ]


def _extract_google_maps_place(page: Any, card: dict[str, str], *, query: str) -> dict[str, Any] | None:
    href = str(card.get("href") or "")
    title = str(card.get("title") or "").strip()
    if not href or not title:
        return None
    try:
        page.goto(href, wait_until="domcontentloaded", timeout=20_000)
        page.wait_for_timeout(max(1_500, min(_maps_wait_ms(), 5_000)))
        text = page.locator("body").inner_text(timeout=5_000)
        elements = page.evaluate(
            """() => Array.from(document.querySelectorAll('a,button')).map((el) => ({
                tag: el.tagName,
                href: el.href || '',
                text: (el.innerText || el.textContent || '').trim(),
                aria: el.getAttribute('aria-label') || '',
                data: el.getAttribute('data-item-id') || ''
            }))"""
        )
    except Exception:
        return None

    details = _maps_detail_fields(elements if isinstance(elements, list) else [])
    name = _maps_detail_name(text, title)
    address = details.get("address") or _extract_japan_address(text)
    website = normalize_website_url(details.get("website") or "")
    phone = details.get("phone") or _extract_japanese_phone(text)
    rating, rating_count = _maps_rating(text, name)
    detail_url = page.url or href
    latitude, longitude = _maps_coordinates(detail_url)
    if latitude is None or longitude is None:
        latitude, longitude = _maps_coordinates(href)
    place_id = _maps_place_id(href) or _maps_place_id(detail_url)
    cid = _maps_cid(href) or _maps_cid(detail_url)
    if not website:
        website = _official_site_for_maps_place(name=name, address=address, query=query, timeout_seconds=8)
    if not website:
        return None

    return {
        "title": name or title,
        "name": name or title,
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
        "position": {"lat": latitude, "lng": longitude} if latitude is not None and longitude is not None else {},
        "rating": rating,
        "ratingCount": rating_count,
        "type": _maps_place_type(text),
        "types": [_maps_place_type(text)] if _maps_place_type(text) else [],
        "website": website,
        "phoneNumber": phone,
        "cid": cid,
        "placeId": place_id or f"local:{hashlib.sha1((page.url or href).encode('utf-8')).hexdigest()[:16]}",
        "link": detail_url,
        "mapUrl": detail_url,
        "searchProvider": "webserper_google_maps_browser",
        "localEvidenceHtml": _maps_evidence_html(name=name or title, map_url=detail_url, text=text),
    }


def _maps_detail_fields(elements: list[Any]) -> dict[str, str]:
    details = {"address": "", "website": "", "phone": ""}
    for item in elements:
        if not isinstance(item, dict):
            continue
        data = str(item.get("data") or "")
        aria = str(item.get("aria") or "")
        href = str(item.get("href") or "")
        text = str(item.get("text") or "")
        if data == "address" and not details["address"]:
            details["address"] = _clean_maps_labeled_value(aria, "住所:") or _extract_japan_address(text)
        elif data == "authority" and not details["website"]:
            details["website"] = href
        elif data.startswith("phone:") and not details["phone"]:
            details["phone"] = _clean_maps_labeled_value(aria, "電話番号:") or _extract_japanese_phone(text)
    return details


def _clean_maps_labeled_value(value: str, label: str) -> str:
    cleaned = str(value or "").strip()
    if cleaned.startswith(label):
        cleaned = cleaned[len(label):].strip()
    return cleaned.strip(" 　")


def _maps_detail_name(text: str, fallback: str) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if line == fallback:
            following = "\n".join(lines[index:index + 5])
            if re.search(r"\n[0-5](?:\.\d)?\n\([0-9,]+\)", following):
                return fallback
    return fallback


def _maps_rating(text: str, name: str) -> tuple[float | None, int | None]:
    if name:
        pattern = re.compile(rf"{re.escape(name)}\s*\n([0-5](?:\.\d)?)\s*\n\(([0-9,]+)\)")
        match = pattern.search(text or "")
        if match:
            return float(match.group(1)), int(match.group(2).replace(",", ""))
    match = re.search(r"\n([0-5](?:\.\d)?)\s*\n\(([0-9,]+)\)", text or "")
    if match:
        return float(match.group(1)), int(match.group(2).replace(",", ""))
    return None, None


def _maps_coordinates(url: str) -> tuple[float | None, float | None]:
    match = re.search(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)", url or "")
    if match:
        return float(match.group(1)), float(match.group(2))
    match = re.search(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", url or "")
    if match:
        return float(match.group(1)), float(match.group(2))
    return None, None


def _maps_place_id(url: str) -> str:
    match = re.search(r"!19s([^!?&]+)", url or "")
    if match:
        return urllib.parse.unquote(match.group(1))
    return ""


def _maps_cid(url: str) -> str:
    match = re.search(r"!1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)", url or "")
    return match.group(1) if match else ""


def _maps_place_type(text: str) -> str:
    for line in [line.strip() for line in str(text or "").splitlines() if line.strip()]:
        if line in {"ラーメン屋", "居酒屋", "和食店", "レストラン"}:
            return line
    return ""


def _official_site_for_maps_place(*, name: str, address: str, query: str, timeout_seconds: int) -> str:
    if not name:
        return ""
    search_query = " ".join(part for part in [f'"{name}"', "公式", _address_search_hint(address), query] if part)
    try:
        data = _webserper_organic_search(query=search_query, gl="jp", timeout_seconds=timeout_seconds)
    except Exception:
        return ""
    for result in data.get("organic") or []:
        link = normalize_website_url(str(result.get("link") or ""))
        host = _host(link)
        if not link or not host:
            continue
        if _blocked_place_host(host) or _blocked_candidate_url(link):
            continue
        if any(token in host for token in DIRECTORY_HOST_TOKENS):
            continue
        if _looks_like_vendor_or_article(result, host):
            continue
        return link
    return ""


def _first_party_google_maps_places(
    places: list[dict[str, Any]],
    *,
    query: str,
    gl: str,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    first_party: list[dict[str, Any]] = []
    seen_hosts: set[str] = set()
    for place in places:
        updated = dict(place)
        website = normalize_website_url(str(updated.get("website") or ""))
        host = _host(website)
        needs_official_lookup = (
            not website
            or not host
            or _blocked_place_host(host)
            or any(token in host for token in DIRECTORY_HOST_TOKENS)
            or _blocked_candidate_url(website)
        )
        if needs_official_lookup:
            official = ""
            if website and any(token in host for token in DIRECTORY_HOST_TOKENS):
                try:
                    directory_html = _http_get_text(website, timeout_seconds=timeout_seconds, max_bytes=500_000)
                except Exception:
                    directory_html = ""
                urls = _official_urls_from_directory_html(website, directory_html)
                official = urls[0] if urls else ""
            website = normalize_website_url(official)
            host = _host(website)
            if website:
                updated["website"] = website
                updated["websiteSource"] = "directory_external_url"
        if not website or not host or host in seen_hosts:
            continue
        if _blocked_place_host(host) or _blocked_candidate_url(website):
            continue
        if any(token in host for token in DIRECTORY_HOST_TOKENS):
            continue
        seen_hosts.add(host)
        first_party.append(updated)
        if len(first_party) >= _local_place_limit():
            break
    return first_party


def _address_search_hint(address: str) -> str:
    match = re.search(r"(東京都[^ 　,，。]+|大阪府[^ 　,，。]+|京都府[^ 　,，。]+|北海道[^ 　,，。]+|[^\s]+県[^ 　,，。]+)", address or "")
    return match.group(1) if match else ""


def _maps_evidence_html(*, name: str, map_url: str, text: str) -> str:
    escaped_name = html_lib.escape(name or "Google Maps evidence")
    escaped_text = html_lib.escape("\n".join((text or "").splitlines()[:180]))
    return f"<html><body><h1>{escaped_name}</h1><p>Source: {html_lib.escape(map_url)}</p><pre>{escaped_text}</pre></body></html>"


def _webserper_maps_payload(
    *,
    query: str,
    gl: str,
    places: list[dict[str, Any]],
    source_runs: list[dict[str, Any]] | None = None,
    engine: str = "official_site_organic_plus_page_extract",
    fallback_engine: str = "yahoo_japan+duckduckgo_lite",
) -> dict[str, Any]:
    return {
        "searchParameters": {
            "q": query,
            "gl": gl,
            "engine": engine,
            "fallback_engine": fallback_engine,
            "provider": WEB_SERPER_PROVIDER,
            "sourceRuns": source_runs or [],
        },
        "places": places,
    }


def _query_discovery_mode(query: str) -> str:
    lowered = str(query or "").lower()
    if "site:" in lowered and any(token in lowered for token in DIRECTORY_HOST_TOKENS):
        return "directory_extraction"
    return "maps_plus_official"


def _query_should_merge_organic_discovery(query: str) -> bool:
    lowered = str(query or "").lower()
    return (
        "公式" in query
        or "official" in lowered
        or "お問い合わせ" in query
        or "メール" in query
        or "店" in query
    )


def _directory_extraction_queries(query: str) -> list[str]:
    queries = _localized_query_variants(query)
    lowered = str(query or "").lower()
    if "ramendb" in lowered:
        for place in _place_terms_from_query(query):
            queries.append(f"ラーメンデータベース {place} ラーメン 公式")
    if "tabelog" in lowered:
        for place in _place_terms_from_query(query):
            category = "ラーメン" if _query_targets_ramen(query) else "そば" if _query_targets_soba(query) else "居酒屋"
            queries.append(f"食べログ {place} {category} メニュー 公式")
    if "hotpepper" in lowered:
        for place in _place_terms_from_query(query):
            category = "ラーメン" if _query_targets_ramen(query) else "そば" if _query_targets_soba(query) else "居酒屋"
            queries.append(f"ホットペッパー {place} {category} メニュー 公式")
    if "gnavi" in lowered or "gurunavi" in lowered:
        for place in _place_terms_from_query(query):
            queries.append(f"ぐるなび {place} 居酒屋 メニュー 公式")
    return [item for item in dict.fromkeys(queries) if item][:3]


def _official_discovery_queries(query: str) -> list[str]:
    variants = _localized_query_variants(query)
    for place in _place_terms_from_query(query):
        area = _area_hint(place)
        if _query_targets_ramen(query):
            variants.extend([
                " ".join(part for part in [place, "ラーメン", "公式", "お問い合わせ", area] if part),
                " ".join(part for part in [place, "ラーメン", "公式", "メール", area] if part),
                " ".join(part for part in [place, "ラーメン", "公式", "contact", area] if part),
            ])
        if _query_targets_soba(query):
            variants.extend([
                " ".join(part for part in [place, "そば", "公式", "お問い合わせ", area] if part),
                " ".join(part for part in [place, "そば", "公式", "メール", area] if part),
                " ".join(part for part in [place, "そば", "公式", "contact", area] if part),
            ])
        if _query_targets_izakaya(query):
            variants.extend([
                " ".join(part for part in [place, "居酒屋", "公式", "お問い合わせ", area] if part),
                " ".join(part for part in [place, "居酒屋", "お品書き", "問い合わせ", area] if part),
                " ".join(part for part in [place, "居酒屋", "公式", "contact", area] if part),
            ])
    return [item for item in dict.fromkeys(variants) if item]


def _localized_query_variants(query: str) -> list[str]:
    cleaned = " ".join(str(query or "").split())
    variants = [cleaned] if cleaned else []
    for latin, japanese in CITY_ALIASES.items():
        pattern = re.compile(re.escape(latin), re.I)
        if pattern.search(cleaned):
            variants.append(pattern.sub(japanese, cleaned))
    return [item for item in dict.fromkeys(variants) if item]


def _organic_places_for_queries(
    *,
    query: str,
    queries: list[str],
    gl: str,
    timeout_seconds: int,
    source_runs: list[dict[str, Any]],
    organic_engines: tuple[str, ...] = ("yahoo_japan", "duckduckgo_lite"),
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen_links: set[str] = set()
    for local_query in queries:
        try:
            organic_response = _webserper_organic_search(
                query=local_query,
                gl=gl,
                timeout_seconds=timeout_seconds,
                engines=organic_engines,
            )
        except Exception as exc:
            source_runs.append({
                "engine": "official_site_organic",
                "query": local_query,
                "attempt_count": 1,
                "recovered_by_retry": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
            continue
        source_runs.append({
            "engine": "official_site_organic",
            "query": local_query,
            "attempt_count": 1,
            "recovered_by_retry": any(
                bool(source.get("recovered_by_retry"))
                for source in (organic_response.get("searchParameters") or {}).get("sourceRuns") or []
            ),
            "fallback_engine": "+".join(organic_engines),
            "source_runs": (organic_response.get("searchParameters") or {}).get("sourceRuns") or [],
            "result_count": len(organic_response.get("organic") or []),
        })
        for result in organic_response.get("organic") or []:
            link = str(result.get("link") or "")
            if link and link not in seen_links:
                seen_links.add(link)
                results.append(result)
    results.sort(key=lambda result: (-_organic_result_score(result, query), str(result.get("link") or "")))

    places: list[dict[str, Any]] = []
    seen_hosts: set[str] = set()
    for result in results[: _local_result_limit()]:
        for candidate in _candidate_inputs_for_result(result, timeout_seconds=timeout_seconds, gl=gl):
            website = str(candidate.get("website") or "")
            host = _host(website)
            if not host or host in seen_hosts:
                continue
            seen_hosts.add(host)
            place = _place_from_website_result(
                website=website,
                source_url=str(candidate.get("source_url") or website),
                result=result,
                query=query,
                seed_name=str(candidate.get("name") or ""),
                seed_address=str(candidate.get("address") or ""),
                seed_phone=str(candidate.get("phone") or ""),
                timeout_seconds=timeout_seconds,
            )
            if place:
                places.append(place)
            if len(places) >= _local_place_limit():
                return places
    return places


def _merge_places_by_site_or_name(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for place in places:
        website = normalize_website_url(str(place.get("website") or ""))
        host = _host(website)
        name = normalise_business_name(str(place.get("name") or place.get("title") or ""))
        key = f"host:{host}" if host else f"name:{name}"
        if not key or key in seen:
            continue
        seen.add(key)
        updated = dict(place)
        if website:
            updated["website"] = website
        merged.append(updated)
    return merged


def _local_maps_queries(query: str) -> list[str]:
    cleaned = " ".join(str(query or "").split())
    queries: list[str] = []
    for place in _place_terms_from_query(cleaned):
        area = _area_hint(place)
        if _query_targets_ramen(cleaned):
            queries.extend([
                " ".join(part for part in ["ラーメン", place, "公式サイト", area, "TEL"] if part),
                f"ラーメン {place} メニュー 公式",
                f"券売機 ラーメン {place} 公式",
            ])
        if _query_targets_izakaya(cleaned):
            queries.extend([
                " ".join(part for part in ["居酒屋", place, "公式サイト", area, "お品書き"] if part),
                f"居酒屋 {place} 飲み放題 コース 公式",
                f"居酒屋 {place} メニュー 公式",
            ])
    queries.append(cleaned)
    if "公式" not in cleaned:
        queries.append(f"{cleaned} 公式")
    if not any(token in cleaned.lower() for token in ("site:", "official")):
        queries.append(f"{cleaned} 店舗 公式")
    return [item for item in dict.fromkeys(queries) if item]


def _query_targets_ramen(query: str) -> bool:
    lowered = str(query or "").lower()
    return any(token.lower() in lowered for token in RAMEN_TOKENS)


def _query_targets_soba(query: str) -> bool:
    return False


def _query_targets_izakaya(query: str) -> bool:
    lowered = str(query or "").lower()
    return any(token.lower() in lowered for token in IZAKAYA_TOKENS)


def _place_terms_from_query(query: str) -> list[str]:
    lowered = str(query or "").lower()
    places: list[str] = []
    for latin, japanese in CITY_ALIASES.items():
        if latin in lowered or japanese in query:
            places.extend([japanese, latin.title()])
            break
    if not places and ("japan" in lowered or "日本" in query):
        places.extend(["渋谷", "京都", "難波"])
    return list(dict.fromkeys(place for place in places if place))


def _area_hint(place: str) -> str:
    return AREA_HINTS.get(place, "")


def _candidate_inputs_for_result(result: dict[str, Any], *, timeout_seconds: int, gl: str) -> list[dict[str, str]]:
    link = normalize_website_url(str(result.get("link") or ""))
    if not link:
        return []
    host = _host(link)
    if any(token in host for token in DIRECTORY_HOST_TOKENS):
        directory_html = ""
        try:
            directory_html = _http_get_text(link, timeout_seconds=timeout_seconds, max_bytes=500_000)
        except Exception:
            directory_html = ""
        hints = _directory_hints(result=result, html=directory_html)
        official_urls = _official_urls_from_directory_html(link, directory_html)
        if not official_urls and hints.get("name"):
            official_urls = _official_urls_from_name_hint(
                name=str(hints.get("name") or ""),
                category_query=" ".join(str(result.get(key) or "") for key in ("title", "snippet")),
                gl=gl,
                timeout_seconds=timeout_seconds,
            )
        return [
            {
                "website": url,
                "source_url": link,
                "name": str(hints.get("name") or ""),
                "address": str(hints.get("address") or ""),
                "phone": str(hints.get("phone") or ""),
            }
            for url in official_urls
        ]
    if _blocked_place_host(host) or _blocked_candidate_url(link) or _looks_like_vendor_or_article(result, host):
        return []
    return [{"website": link, "source_url": link}]


def _organic_result_score(result: dict[str, Any], query: str) -> int:
    link = normalize_website_url(str(result.get("link") or ""))
    host = _host(link)
    haystack = " ".join(str(result.get(key) or "") for key in ("title", "snippet", "link")).lower()
    score = 0
    if not link or not host:
        return -100
    if _blocked_place_host(host) or _blocked_candidate_url(link):
        score -= 80
    if any(token in host for token in DIRECTORY_HOST_TOKENS):
        score -= 30
    else:
        score += 25
    if any(token in haystack for token in ("公式", "公式サイト", "official", "ホームページ")):
        score += 30
    if any(token in haystack for token in ("menu", "メニュー", "お品書き", "contact", "お問い合わせ", "access", "アクセス")):
        score += 10
    query_lower = str(query or "").lower()
    if _query_targets_ramen(query_lower) and any(token.lower() in haystack for token in RAMEN_TOKENS):
        score += 10
    if _query_targets_soba(query_lower) and any(token.lower() in haystack for token in SOBA_TOKENS):
        score += 10
    if _query_targets_izakaya(query_lower) and any(token.lower() in haystack for token in IZAKAYA_TOKENS):
        score += 10
    if _looks_like_vendor_or_article(result, host):
        score -= 50
    return score


def _official_urls_from_directory_html(url: str, page_html: str) -> list[str]:
    hrefs = re.findall(r'''(?is)<a\b[^>]+href=["']([^"']+)["']''', page_html or "")
    urls: list[str] = []
    seen: set[str] = set()
    for href in hrefs:
        official = _official_external_url(url, href)
        if not official:
            continue
        host = _host(official)
        if not host or _blocked_place_host(host) or _blocked_candidate_url(official):
            continue
        if official not in seen:
            seen.add(official)
            urls.append(official)
    return urls[:3]


def _official_urls_from_name_hint(*, name: str, category_query: str, gl: str, timeout_seconds: int) -> list[str]:
    query = f'"{name}" 公式 {category_query}'.strip()
    try:
        data = _webserper_organic_search(query=query, gl=gl, timeout_seconds=timeout_seconds)
    except Exception:
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for result in data.get("organic") or []:
        link = normalize_website_url(str(result.get("link") or ""))
        host = _host(link)
        if not link or not host or host in seen:
            continue
        if any(token in host for token in DIRECTORY_HOST_TOKENS):
            continue
        if _blocked_place_host(host) or _blocked_candidate_url(link) or _looks_like_vendor_or_article(result, host):
            continue
        seen.add(host)
        urls.append(link)
        if len(urls) >= 2:
            break
    return urls


def _directory_hints(*, result: dict[str, Any], html: str) -> dict[str, str]:
    title = html_lib.unescape(str(result.get("title") or ""))
    name = re.split(r"\s*(?:\(|（| - |｜|\|)", title, maxsplit=1)[0].strip()
    if business_name_is_suspicious(name):
        name = ""
    text = " ".join([
        str(result.get("snippet") or ""),
        str(extract_page_payload(str(result.get("link") or ""), html).get("text") or ""),
    ])
    return {
        "name": name,
        "address": _extract_japan_address(text),
        "phone": _extract_japanese_phone(text),
    }


def _place_from_website_result(
    *,
    website: str,
    source_url: str,
    result: dict[str, Any],
    query: str,
    timeout_seconds: int,
    seed_name: str = "",
    seed_address: str = "",
    seed_phone: str = "",
) -> dict[str, Any] | None:
    try:
        page_html = _http_get_text(website, timeout_seconds=timeout_seconds, max_bytes=700_000)
    except Exception:
        return None

    payload = extract_page_payload(website, page_html)
    text = " ".join([
        str(result.get("title") or ""),
        str(result.get("snippet") or ""),
        str(payload.get("text") or ""),
    ])
    if not _looks_like_supported_category(text, query):
        return None

    name = _best_business_name(result=result, html=page_html, seed_name=seed_name)
    if business_name_is_suspicious(name):
        return None
    if is_chain_business(name) or has_chain_or_franchise_infrastructure(text, business_name=name):
        return None

    address = _extract_japan_address(text) or seed_address
    phone = _extract_japanese_phone(text) or seed_phone
    if not address and not phone:
        return None

    place_id = f"webserper:{hashlib.sha1(website.encode('utf-8')).hexdigest()[:16]}"
    return {
        "title": name,
        "name": name,
        "website": website,
        "address": address,
        "phoneNumber": phone,
        "placeId": place_id,
        "link": source_url or website,
        "mapUrl": source_url or website,
        "position": {},
        "searchProvider": WEB_SERPER_PROVIDER,
        "sourceTitle": str(result.get("title") or ""),
        "sourceSnippet": str(result.get("snippet") or ""),
        "sourceOrganicLink": str(result.get("link") or ""),
    }


def _best_business_name(*, result: dict[str, Any], html: str, seed_name: str = "") -> str:
    if seed_name and not business_name_is_suspicious(seed_name):
        return seed_name
    result_name = _name_from_result_title(str(result.get("title") or ""))
    for candidate in extract_business_name_candidates(html):
        if len(candidate) > 40 and result_name and not business_name_is_suspicious(result_name):
            return result_name
        if not business_name_is_suspicious(candidate):
            return candidate
    return result_name


def _name_from_result_title(title: str) -> str:
    cleaned = html_lib.unescape(title)
    cleaned = re.split(r"\s*(?:-|｜|\||/|【公式】|\[公式\])", cleaned, maxsplit=1)[0].strip()
    cleaned = re.sub(r"^[\[【]公式[\]】]\s*", "", cleaned).strip()
    return normalise_business_name(cleaned)


def _looks_like_supported_category(text: str, query: str) -> bool:
    haystack = f"{text or ''} {query or ''}".lower()
    query_haystack = str(query or "").lower()
    if any(token.lower() in query_haystack for token in RAMEN_TOKENS):
        return any(token.lower() in haystack for token in RAMEN_TOKENS)
    if any(token.lower() in query_haystack for token in IZAKAYA_TOKENS):
        return any(token.lower() in haystack for token in IZAKAYA_TOKENS)
    return any(token.lower() in haystack for token in (*RAMEN_TOKENS, *IZAKAYA_TOKENS))


def _blocked_place_host(host: str) -> bool:
    return any(token in host for token in BLOCKED_PLACE_HOST_TOKENS)


def _blocked_candidate_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(str(url or ""))
    if MEDIA_PATH_RE.search(parsed.path):
        return True
    host = parsed.netloc.lower()
    route = urllib.parse.unquote(" ".join([host, parsed.path, parsed.query])).lower()
    if any(token in host for token in RESERVATION_ROUTE_HOST_TOKENS):
        return True
    return any(token.lower() in route for token in RESERVATION_ROUTE_PATH_TOKENS)


def _looks_like_vendor_or_article(result: dict[str, Any], host: str) -> bool:
    if any(token in host for token in VENDOR_OR_ARTICLE_HOST_TOKENS):
        return True
    haystack = " ".join(str(result.get(key) or "") for key in ("title", "snippet", "link")).lower()
    if any(token.lower() in haystack for token in VENDOR_OR_ARTICLE_TEXT_TOKENS):
        return True
    path = urllib.parse.urlparse(str(result.get("link") or "")).path.lower()
    return any(token in path for token in ("/column", "/blog", "/news", "/article", "/lifestyle", "/travel"))


def _extract_japan_address(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "")
    pref_pattern = "|".join(re.escape(pref) for pref in JP_PREFECTURE_PREFIXES)
    match = re.search(rf"(?:〒\s?\d{{3}}-?\d{{4}}\s*)?(?:{pref_pattern})[^\s<>{{}}]{{4,80}}", cleaned)
    if not match:
        return ""
    address = match.group(0).strip(" 　,，。|｜")
    address = re.split(r"(?:TEL|Tel|tel|電話|営業時間|定休日|アクセス|Map|MAP)", address, maxsplit=1)[0]
    address = address.strip(" 　,，。|｜")
    if any(token in address for token in ("施設一覧", "ランキング", "もっと見る", "検索結果")):
        return ""
    if not re.search(r"[0-9０-９]|区|市|町|村|郡|丁目|番地", address):
        return ""
    return address


def _extract_japanese_phone(text: str) -> str:
    patterns = (
        r"(?:\+81[-\s]?\d{1,4}[-\s]\d{1,4}[-\s]\d{3,4})",
        r"(?:0\d{1,4}[-\s]\d{1,4}[-\s]\d{3,4})",
        r"(?:0\d{9,10})",
    )
    for pattern in patterns:
        match = re.search(pattern, text or "")
        if match:
            phone = match.group(0).strip()
            digits = re.sub(r"\D", "", phone)
            if phone.startswith("+81"):
                return phone
            if len(digits) in {10, 11}:
                return phone
    return ""


def _duckduckgo_html(*, query: str, gl: str, timeout_seconds: int) -> str:
    region = "jp-jp" if str(gl or "").lower() == "jp" else ""
    params = {"q": query}
    if region:
        params["kl"] = region
    url = "https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode(params)
    return _http_get_text(url, timeout_seconds=timeout_seconds, max_bytes=1_000_000)


def _yahoo_japan_html(*, query: str, gl: str, timeout_seconds: int) -> str:
    params = {"p": query, "ei": "UTF-8"}
    if str(gl or "").lower() == "jp":
        params["fr"] = "top_ga1_sa"
    url = "https://search.yahoo.co.jp/search?" + urllib.parse.urlencode(params)
    return _http_get_text(url, timeout_seconds=timeout_seconds, max_bytes=1_000_000)


def _http_get_text(url: str, *, timeout_seconds: int, max_bytes: int = 700_000) -> str:
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
        "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
    })
    with urllib.request.urlopen(request, timeout=max(3, min(timeout_seconds, 20))) as response:
        return response.read(max_bytes).decode("utf-8", errors="replace")


class _DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._current: dict[str, str] = {}
        self._capture: str = ""
        self._buffer: list[str] = []
        self._emitted: set[str] = set()
        self.results: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        classes = attrs_dict.get("class", "")
        if "result__a" in classes or "result-link" in classes:
            self._emit_current()
            self._current = {"link": _decode_duckduckgo_link(attrs_dict.get("href", ""))}
            self._capture = "title"
            self._buffer = []
            return
        if ("result__snippet" in classes or "result-snippet" in classes) and self._current:
            self._capture = "snippet"
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._capture:
            return
        if tag.lower() not in {"a", "div", "span", "td"}:
            return
        value = re.sub(r"\s+", " ", " ".join(self._buffer)).strip()
        if value:
            self._current[self._capture] = html_lib.unescape(value)
        self._capture = ""
        self._buffer = []

    def _emit_current(self) -> None:
        link = normalize_website_url(self._current.get("link", ""))
        title = self._current.get("title", "").strip()
        if not link or not title or link in self._emitted:
            self._current = {}
            return
        self._emitted.add(link)
        self.results.append({
            "title": title,
            "link": link,
            "snippet": self._current.get("snippet", "").strip(),
        })
        self._current = {}

    def finish(self) -> list[dict[str, str]]:
        self._emit_current()
        return self.results


def _organic_results_from_duckduckgo_html(source: str) -> list[dict[str, str]]:
    parser = _DuckDuckGoParser()
    try:
        parser.feed(source or "")
    except Exception:
        return []
    return parser.finish()


class _YahooJapanParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_item = False
        self._item_depth = 0
        self._current: dict[str, str] = {}
        self._capture = ""
        self._buffer: list[str] = []
        self._emitted: set[str] = set()
        self.results: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag == "li":
            if not self._in_item:
                self._emit_current()
                self._current = {}
                self._in_item = True
                self._item_depth = 1
            else:
                self._item_depth += 1
            return
        if not self._in_item:
            return
        if tag == "a" and not self._current.get("link"):
            link = _decode_yahoo_japan_link(attrs_dict.get("href", ""))
            host = _host(normalize_website_url(link))
            if link and host and not _blocked_yahoo_result_host(host):
                self._current["link"] = link
                self._capture = "title"
                self._buffer = []
            return
        if tag in {"div", "p", "span"} and self._current.get("link") and not self._current.get("snippet") and self._capture != "title":
            self._capture = "snippet"
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._capture and tag in {"a", "div", "p", "span"}:
            value = re.sub(r"\s+", " ", " ".join(self._buffer)).strip()
            if value:
                self._current[self._capture] = html_lib.unescape(value)
            self._capture = ""
            self._buffer = []
        if tag == "li" and self._in_item:
            self._item_depth -= 1
            if self._item_depth <= 0:
                self._emit_current()
                self._in_item = False
                self._item_depth = 0

    def _emit_current(self) -> None:
        link = normalize_website_url(self._current.get("link", ""))
        title = self._current.get("title", "").strip()
        host = _host(link)
        if not link or not title or link in self._emitted or _blocked_yahoo_result_host(host):
            self._current = {}
            return
        self._emitted.add(link)
        self.results.append({
            "title": title,
            "link": link,
            "snippet": self._current.get("snippet", "").strip(),
        })
        self._current = {}

    def finish(self) -> list[dict[str, str]]:
        self._emit_current()
        return self.results


def _organic_results_from_yahoo_japan_html(source: str) -> list[dict[str, str]]:
    parser = _YahooJapanParser()
    try:
        parser.feed(source or "")
    except Exception:
        return []
    return parser.finish()


def _decode_duckduckgo_link(href: str) -> str:
    raw = html_lib.unescape(str(href or "").strip())
    if raw.startswith("//"):
        raw = f"https:{raw}"
    parsed = urllib.parse.urlparse(raw)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return urllib.parse.unquote(target)
    return raw


def _decode_yahoo_japan_link(href: str) -> str:
    raw = html_lib.unescape(str(href or "").strip())
    if raw.startswith("//"):
        raw = f"https:{raw}"
    parsed = urllib.parse.urlparse(raw)
    if not parsed.netloc:
        return raw
    if "search.yahoo.co.jp" not in parsed.netloc and "r.search.yahoo.co.jp" not in parsed.netloc:
        return raw
    query = urllib.parse.parse_qs(parsed.query)
    for key in ("u", "url", "RU"):
        target = query.get(key, [""])[0]
        if target:
            return urllib.parse.unquote(target)
    match = re.search(r"/RU=([^/]+)", parsed.path)
    if match:
        return urllib.parse.unquote(match.group(1))
    return ""


def _blocked_yahoo_result_host(host: str) -> bool:
    if not host:
        return True
    return any(token in host for token in (
        "yahoo.co.jp",
        "search.yahoo.",
        "r.search.yahoo.",
        "help.yahoo.",
    ))


def _host(url: str) -> str:
    return urllib.parse.urlparse(str(url or "")).netloc.lower().removeprefix("www.")


def _local_result_limit() -> int:
    return _env_int("WEBREFURB_LOCAL_SEARCH_RESULT_LIMIT", default=30, minimum=1, maximum=60)


def _local_place_limit() -> int:
    return _env_int("WEBREFURB_LOCAL_SEARCH_PLACE_LIMIT", default=24, minimum=1, maximum=40)


def _env_int(name: str, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, "") or default)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _http_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""
    return body.strip()
