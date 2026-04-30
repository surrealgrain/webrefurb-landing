from __future__ import annotations

import html as html_lib
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from .business_name import (
    business_name_is_suspicious,
    business_names_match,
    extract_business_name_candidates,
    normalise_business_name,
)
from .contact_crawler import _official_external_url, normalize_website_url
from .html_parser import extract_page_payload


SearchFn = Callable[..., dict[str, Any]]
FetchFn = Callable[..., str]

PORTAL_HOST_SOURCES = {
    "tabelog.com": "tabelog",
    "hotpepper.jp": "hotpepper",
    "gnavi.co.jp": "gurunavi",
    "gurunavi.com": "gurunavi",
    "ramendb.supleks.jp": "ramendb",
    "retty.me": "retty",
    "hitosara.com": "hitosara",
    "paypaygourmet.yahoo.co.jp": "paypay_gourmet",
    "loco.yahoo.co.jp": "yahoo_local",
    "map.yahoo.co.jp": "yahoo_local",
}
SOCIAL_HOST_SOURCES = {
    "instagram.com": "instagram",
    "twitter.com": "x",
    "x.com": "x",
}
BLOCKED_OFFICIAL_HOST_TOKENS = (
    "google.",
    "maps.google.",
    "tripadvisor.",
    "yelp.",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "line.me",
    "lin.ee",
    "youtube.com",
    "tiktok.com",
)
RESERVATION_HOST_TOKENS = (
    "tablecheck.com",
    "ebica.jp",
    "toreta.in",
)
RESERVATION_ROUTE_TOKENS = (
    "reserve",
    "reservation",
    "booking",
    "book-a-table",
    "yoyaku",
    "予約",
)
MENU_TOKENS = (
    "メニュー",
    "お品書き",
    "品書き",
    "menu",
    "飲み放題",
    "コース",
    "券売機",
    "食券",
    "らーめん",
    "ラーメン",
)
ENGLISH_MENU_TOKENS = (
    "英語メニュー",
    "english menu",
    "menus in english",
    "多言語",
    "multilingual",
)
RAMEN_TOKENS = ("ラーメン", "らーめん", "らぁめん", "ramen", "中華そば", "つけ麺")
IZAKAYA_TOKENS = ("居酒屋", "izakaya", "飲み放題", "お品書き", "焼鳥", "焼き鳥")
JP_PREFECTURE_PREFIXES = (
    "東京都", "大阪府", "京都府", "北海道",
    "神奈川県", "千葉県", "埼玉県", "愛知県", "兵庫県", "福岡県",
    "静岡県", "茨城県", "広島県", "宮城県", "長野県", "新潟県",
    "富山県", "石川県", "福井県", "山梨県", "岐阜県", "三重県",
    "滋賀県", "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県",
    "山口県", "徳島県", "香川県", "愛媛県", "高知県",
    "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
)


@dataclass(frozen=True)
class SourceEvidence:
    source_name: str
    source_url: str = ""
    name: str = ""
    address: str = ""
    phone: str = ""
    official_site_candidates: list[str] = field(default_factory=list)
    operator_company_name: str = ""
    operator_company_url: str = ""
    social_links: list[str] = field(default_factory=list)
    menu_evidence_found: bool = False
    english_menu_signal: bool = False
    category_signal: str = ""
    match_strength: str = "weak"
    title: str = ""
    snippet: str = ""
    text_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RestaurantIntel:
    canonical_name: str = ""
    address: str = ""
    phone: str = ""
    verified_by: list[str] = field(default_factory=list)
    source_count: int = 0
    source_evidence: list[SourceEvidence] = field(default_factory=list)
    portal_urls: dict[str, str] = field(default_factory=dict)
    official_site_candidates: list[str] = field(default_factory=list)
    social_links: list[str] = field(default_factory=list)
    operator_company_name: str = ""
    operator_company_url: str = ""
    coverage_signals: dict[str, Any] = field(default_factory=dict)
    coverage_score: int = 0
    evidence_pages: list[dict[str, str]] = field(default_factory=list)

    @property
    def primary_official_site(self) -> str:
        return self.official_site_candidates[0] if self.official_site_candidates else ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source_evidence"] = [item.to_dict() for item in self.source_evidence]
        data["primary_official_site"] = self.primary_official_site
        return data


def source_aware_discovery_queries(
    *,
    business_name: str,
    address: str = "",
    phone: str = "",
    category: str = "",
    city: str = "",
    max_queries: int = 14,
) -> list[str]:
    name = normalise_business_name(business_name)
    area = _address_area(address) or city
    category_term = _category_term(category)
    queries: list[str] = []

    if name:
        quoted = f'"{name}"'
        queries.extend([
            f"site:tabelog.com {quoted} {area}".strip(),
            f"site:hotpepper.jp {quoted} {area}".strip(),
            f"site:gnavi.co.jp {quoted} {area}".strip(),
            f"site:gurunavi.com {quoted} {area}".strip(),
        ])
        if _category_key(category) == "ramen":
            queries.append(f"site:ramendb.supleks.jp {quoted} {area}".strip())
        queries.extend([
            f"site:retty.me {quoted} {area}".strip(),
            f"site:hitosara.com {quoted} {area}".strip(),
            f"site:paypaygourmet.yahoo.co.jp {quoted} {area}".strip(),
            f"{quoted} \"公式\"",
            f"{quoted} \"お問い合わせ\"",
            f"{quoted} \"運営会社\"",
            f"{quoted} \"会社概要\"",
            f"{quoted} \"特定商取引法\"",
        ])
        if phone:
            queries.insert(0, f"{quoted} \"{phone}\"")
        if address:
            queries.insert(0, f"{quoted} \"{_address_search_token(address)}\"")
    elif area:
        queries.extend([
            f"site:tabelog.com {category_term} {area} メニュー",
            f"site:hotpepper.jp {category_term} {area} 英語メニュー",
            f"site:gnavi.co.jp {category_term} {area} メニュー",
        ])
        if _category_key(category) == "ramen":
            queries.append(f"site:ramendb.supleks.jp ラーメン {area}")

    return _ordered_unique([query for query in queries if query])[:max_queries]


def contact_discovery_queries(
    *,
    business_name: str,
    operator_company: str = "",
    address: str = "",
    phone: str = "",
    max_queries: int = 10,
) -> list[str]:
    name = normalise_business_name(business_name)
    queries: list[str] = []
    if name:
        quoted = f'"{name}"'
        queries.extend([
            f"{quoted} \"公式\"",
            f"{quoted} \"お問い合わせ\"",
            f"{quoted} \"運営会社\"",
            f"{quoted} \"会社概要\"",
            f"{quoted} \"特定商取引法\"",
        ])
        if address:
            queries.append(f"{quoted} \"{_address_search_token(address)}\"")
        if phone:
            queries.append(f"{quoted} \"{phone}\"")
    if operator_company:
        quoted_op = f'"{operator_company}"'
        queries.extend([
            f"{quoted_op} \"お問い合わせ\"",
            f"{quoted_op} \"飲食店\"",
            f"{quoted_op} \"採用\" \"会社概要\"",
        ])
    return _ordered_unique([query for query in queries if query])[:max_queries]


def collect_restaurant_intel(
    *,
    business_name: str,
    address: str = "",
    phone: str = "",
    category: str = "",
    city: str = "",
    place: dict[str, Any] | None = None,
    initial_website: str = "",
    serper_api_key: str = "",
    search_provider: str | None = None,
    web_search: SearchFn | None = None,
    fetch_page: FetchFn | None = None,
    timeout_seconds: int = 8,
    max_queries: int = 14,
    max_results_per_query: int = 3,
    max_detail_pages: int = 7,
) -> RestaurantIntel:
    web_search = web_search or _empty_search
    fetch_page = fetch_page or _http_fetch_page
    place = place or {}
    canonical_name = normalise_business_name(business_name or str(place.get("title") or place.get("name") or ""))
    canonical_address = str(address or place.get("address") or "").strip()
    canonical_phone = str(phone or place.get("phoneNumber") or "").strip()
    initial = normalize_website_url(initial_website or str(place.get("website") or ""))

    evidence: list[SourceEvidence] = []
    evidence.extend(_evidence_from_place(place=place, business_name=canonical_name, website=initial))

    detail_pages_used = 0
    seen_urls: set[str] = set()
    if initial and (is_portal_url(initial) or is_social_url(initial)):
        item, detail_pages_used = _evidence_from_search_result(
            {"title": canonical_name, "link": initial, "snippet": ""},
            business_name=canonical_name,
            address=canonical_address,
            phone=canonical_phone,
            fetch_page=fetch_page,
            timeout_seconds=timeout_seconds,
            detail_pages_used=detail_pages_used,
            max_detail_pages=max_detail_pages,
        )
        if item:
            evidence.append(item)
            seen_urls.add(item.source_url)

    evidence.extend(_api_evidence(
        business_name=canonical_name,
        address=canonical_address,
        phone=canonical_phone,
        category=category,
        timeout_seconds=timeout_seconds,
    ))

    queries = source_aware_discovery_queries(
        business_name=canonical_name,
        address=canonical_address,
        phone=canonical_phone,
        category=category,
        city=city,
        max_queries=max_queries,
    )
    for query in queries:
        try:
            kwargs = {"query": query, "api_key": serper_api_key, "timeout_seconds": timeout_seconds}
            if search_provider is not None:
                kwargs["provider"] = search_provider
            response = web_search(**kwargs)
        except Exception:
            continue
        for result in (response.get("organic") or [])[:max_results_per_query]:
            link = normalize_website_url(str(result.get("link") or ""))
            if not link or link in seen_urls:
                continue
            seen_urls.add(link)
            item, detail_pages_used = _evidence_from_search_result(
                result,
                business_name=canonical_name,
                address=canonical_address,
                phone=canonical_phone,
                fetch_page=fetch_page,
                timeout_seconds=timeout_seconds,
                detail_pages_used=detail_pages_used,
                max_detail_pages=max_detail_pages,
            )
            if item and _evidence_matches_entity(
                item,
                business_name=canonical_name,
                address=canonical_address,
                phone=canonical_phone,
            ):
                evidence.append(item)

    return _build_intel(
        business_name=canonical_name,
        address=canonical_address,
        phone=canonical_phone,
        initial_website=initial,
        evidence=evidence,
    )


def is_portal_url(url: str) -> bool:
    host = _host(url)
    return any(token in host for token in PORTAL_HOST_SOURCES)


def is_social_url(url: str) -> bool:
    host = _host(url)
    return any(token in host for token in SOCIAL_HOST_SOURCES)


def is_official_candidate_url(url: str) -> bool:
    normalized = normalize_website_url(url)
    if not normalized:
        return False
    parsed = urllib.parse.urlparse(normalized)
    host = parsed.netloc.lower()
    route = urllib.parse.unquote(" ".join([host, parsed.path, parsed.query])).lower()
    if any(token in host for token in (*PORTAL_HOST_SOURCES, *SOCIAL_HOST_SOURCES, *BLOCKED_OFFICIAL_HOST_TOKENS)):
        return False
    if any(token in host for token in RESERVATION_HOST_TOKENS):
        return False
    if any(token in route for token in RESERVATION_ROUTE_TOKENS):
        return False
    if re.search(r"(?i)\.(?:avif|gif|jpe?g|png|svg|webp|pdf)(?:$|[?#])", parsed.path):
        return False
    return True


def coverage_score(signals: dict[str, Any]) -> int:
    score = min(int(signals.get("source_count") or 0), 4) * 12
    if signals.get("has_official_site"):
        score += 22
    if signals.get("has_portal_menu"):
        score += 10
    if signals.get("operator_found"):
        score += 10
    if signals.get("contact_found"):
        score += 20
    if signals.get("matching_phone_or_address"):
        score += 10
    if signals.get("portal_only"):
        score -= 12
    return max(0, min(100, score))


def coverage_with_contact(intel: dict[str, Any] | RestaurantIntel, *, contact_found: bool) -> dict[str, Any]:
    data = intel.to_dict() if isinstance(intel, RestaurantIntel) else dict(intel or {})
    signals = dict(data.get("coverage_signals") or {})
    signals["contact_found"] = bool(contact_found)
    signals["portal_only"] = bool(
        signals.get("portal_only")
        and not contact_found
        and not signals.get("has_official_site")
    )
    return {
        "coverage_signals": signals,
        "coverage_score": coverage_score(signals),
    }


def _build_intel(
    *,
    business_name: str,
    address: str,
    phone: str,
    initial_website: str,
    evidence: list[SourceEvidence],
) -> RestaurantIntel:
    official_candidates = _ordered_unique([
        *([initial_website] if is_official_candidate_url(initial_website) else []),
        *[url for item in evidence for url in item.official_site_candidates],
    ])
    social_links = _ordered_unique([url for item in evidence for url in item.social_links])
    portal_urls: dict[str, str] = {}
    for item in evidence:
        if item.source_name in SOCIAL_HOST_SOURCES.values():
            continue
        if item.source_name in {"google_maps", "official_site", "official_search", "hotpepper_api", "yahoo_local_api"}:
            continue
        if item.source_url and item.source_name not in portal_urls:
            portal_urls[item.source_name] = item.source_url

    verified_by = _verified_sources(evidence)
    operator_item = next((item for item in evidence if item.operator_company_name), None)
    matching_phone_or_address = any(item.match_strength in {"phone", "address"} for item in evidence)
    coverage = {
        "source_count": len(verified_by),
        "has_official_site": bool(official_candidates),
        "has_portal_menu": any(
            item.menu_evidence_found and item.source_name in PORTAL_HOST_SOURCES.values()
            for item in evidence
        ),
        "has_english_menu_signal": any(item.english_menu_signal for item in evidence),
        "operator_found": bool(operator_item),
        "contact_found": False,
        "portal_only": bool(portal_urls and not official_candidates),
        "matching_phone_or_address": matching_phone_or_address,
    }

    return RestaurantIntel(
        canonical_name=_best_canonical_name(business_name, evidence),
        address=address,
        phone=phone,
        verified_by=verified_by,
        source_count=len(verified_by),
        source_evidence=evidence,
        portal_urls=portal_urls,
        official_site_candidates=official_candidates,
        social_links=social_links,
        operator_company_name=operator_item.operator_company_name if operator_item else "",
        operator_company_url=operator_item.operator_company_url if operator_item else "",
        coverage_signals=coverage,
        coverage_score=coverage_score(coverage),
        evidence_pages=_evidence_pages(evidence),
    )


def _evidence_from_place(*, place: dict[str, Any], business_name: str, website: str) -> list[SourceEvidence]:
    if not place:
        return []
    source_url = str(place.get("link") or place.get("mapUrl") or "")
    official = [website] if is_official_candidate_url(website) else []
    title = str(place.get("title") or place.get("name") or business_name)
    return [SourceEvidence(
        source_name="google_maps",
        source_url=source_url,
        name=title,
        address=str(place.get("address") or ""),
        phone=str(place.get("phoneNumber") or ""),
        official_site_candidates=official,
        category_signal=_category_from_text(" ".join(str(item) for item in place.get("types") or [])),
        match_strength="phone" if place.get("phoneNumber") else "address" if place.get("address") else "name",
        title=title,
        snippet=str(place.get("type") or ""),
        text_hint=str(place.get("localEvidenceHtml") or "")[:500],
    )]


def _evidence_from_search_result(
    result: dict[str, Any],
    *,
    business_name: str,
    address: str,
    phone: str,
    fetch_page: FetchFn,
    timeout_seconds: int,
    detail_pages_used: int,
    max_detail_pages: int,
) -> tuple[SourceEvidence | None, int]:
    link = normalize_website_url(str(result.get("link") or ""))
    if not link:
        return None, detail_pages_used
    source = _source_name(link)
    if not source and not is_official_candidate_url(link):
        return None, detail_pages_used
    if is_social_url(link):
        return SourceEvidence(
            source_name=source,
            source_url=link,
            name=_name_from_title(str(result.get("title") or "")),
            social_links=[link],
            menu_evidence_found=_has_menu_signal(_result_text(result)),
            english_menu_signal=_has_english_signal(_result_text(result)),
            match_strength="name",
            title=str(result.get("title") or ""),
            snippet=str(result.get("snippet") or ""),
        ), detail_pages_used

    html = ""
    text = _result_text(result)
    if detail_pages_used < max_detail_pages:
        try:
            html = fetch_page(link, timeout_seconds=timeout_seconds)
            detail_pages_used += 1
        except Exception:
            html = ""
    payload = extract_page_payload(link, html)
    page_text = str(payload.get("text") or "")
    links = list(payload.get("links") or [])
    combined = " ".join([text, page_text])
    name = _best_name_from_sources(html=html, fallback=_name_from_title(str(result.get("title") or "")))
    official_candidates = _official_candidates_from_links(link, links)
    if is_official_candidate_url(link) and not source:
        source = "official_search"
        official_candidates = _ordered_unique([link, *official_candidates])
    social_links = _social_links_from_links(links, base_url=link)
    operator_name, operator_url = _operator_from_text(combined)
    match_strength = _match_strength(
        candidate_name=name,
        candidate_address=_extract_japan_address(combined),
        candidate_phone=_extract_japanese_phone(combined),
        business_name=business_name,
        address=address,
        phone=phone,
    )
    return SourceEvidence(
        source_name=source or "official_search",
        source_url=link,
        name=name,
        address=_extract_japan_address(combined),
        phone=_extract_japanese_phone(combined),
        official_site_candidates=official_candidates,
        operator_company_name=operator_name,
        operator_company_url=operator_url,
        social_links=social_links,
        menu_evidence_found=_has_menu_signal(combined),
        english_menu_signal=_has_english_signal(combined),
        category_signal=_category_from_text(combined),
        match_strength=match_strength,
        title=str(result.get("title") or ""),
        snippet=str(result.get("snippet") or ""),
        text_hint=re.sub(r"\s+", " ", combined).strip()[:700],
    ), detail_pages_used


def _api_evidence(
    *,
    business_name: str,
    address: str,
    phone: str,
    category: str,
    timeout_seconds: int,
) -> list[SourceEvidence]:
    evidence: list[SourceEvidence] = []
    hotpepper_key = os.environ.get("HOTPEPPER_API_KEY") or os.environ.get("RECRUIT_HOTPEPPER_API_KEY")
    if hotpepper_key:
        evidence.extend(_hotpepper_api_evidence(
            api_key=hotpepper_key,
            business_name=business_name,
            address=address,
            phone=phone,
            category=category,
            timeout_seconds=timeout_seconds,
        ))
    yahoo_key = os.environ.get("YAHOO_LOCAL_SEARCH_API_KEY") or os.environ.get("YAHOO_JAPAN_APP_ID")
    if yahoo_key:
        evidence.extend(_yahoo_local_api_evidence(
            api_key=yahoo_key,
            business_name=business_name,
            address=address,
            phone=phone,
            category=category,
            timeout_seconds=timeout_seconds,
        ))
    return evidence


def _hotpepper_api_evidence(
    *,
    api_key: str,
    business_name: str,
    address: str,
    phone: str,
    category: str,
    timeout_seconds: int,
) -> list[SourceEvidence]:
    params = {
        "key": api_key,
        "format": "json",
        "count": "5",
        "keyword": " ".join(part for part in [business_name, _category_term(category), _address_area(address)] if part),
    }
    if phone:
        params["tel"] = phone
    data = _json_get("https://webservice.recruit.co.jp/hotpepper/gourmet/v1/", params, timeout_seconds)
    shops = ((data.get("results") or {}).get("shop") or []) if isinstance(data, dict) else []
    return [
        SourceEvidence(
            source_name="hotpepper_api",
            source_url=str((shop.get("urls") or {}).get("pc") or ""),
            name=str(shop.get("name") or ""),
            address=str(shop.get("address") or ""),
            phone=str(shop.get("tel") or ""),
            menu_evidence_found=True,
            category_signal=_category_from_text(" ".join(str(shop.get(key) or "") for key in ("genre", "catch", "name"))),
            match_strength=_match_strength(
                candidate_name=str(shop.get("name") or ""),
                candidate_address=str(shop.get("address") or ""),
                candidate_phone=str(shop.get("tel") or ""),
                business_name=business_name,
                address=address,
                phone=phone,
            ),
            title=str(shop.get("name") or ""),
            snippet=str(shop.get("catch") or ""),
        )
        for shop in shops
    ]


def _yahoo_local_api_evidence(
    *,
    api_key: str,
    business_name: str,
    address: str,
    phone: str,
    category: str,
    timeout_seconds: int,
) -> list[SourceEvidence]:
    params = {
        "appid": api_key,
        "output": "json",
        "results": "5",
        "query": " ".join(part for part in [business_name, _category_term(category), _address_area(address)] if part),
    }
    data = _json_get("https://map.yahooapis.jp/search/local/V1/localSearch", params, timeout_seconds)
    features = data.get("Feature") or [] if isinstance(data, dict) else []
    evidence: list[SourceEvidence] = []
    for feature in features:
        prop = feature.get("Property") or {}
        name = str(feature.get("Name") or "")
        feature_phone = str(prop.get("Tel1") or prop.get("Phone") or "")
        feature_address = str(prop.get("Address") or "")
        evidence.append(SourceEvidence(
            source_name="yahoo_local_api",
            source_url=str(prop.get("DetailUrl") or ""),
            name=name,
            address=feature_address,
            phone=feature_phone,
            category_signal=_category_from_text(" ".join([name, str(prop.get("Genre") or "")])),
            match_strength=_match_strength(
                candidate_name=name,
                candidate_address=feature_address,
                candidate_phone=feature_phone,
                business_name=business_name,
                address=address,
                phone=phone,
            ),
            title=name,
            snippet=feature_address,
        ))
    return evidence


def _evidence_matches_entity(
    evidence: SourceEvidence,
    *,
    business_name: str,
    address: str,
    phone: str,
) -> bool:
    if evidence.source_name in {"google_maps", "official_search"}:
        return evidence.match_strength in {"phone", "address", "name"}
    if evidence.match_strength in {"phone", "address"}:
        return True
    if evidence.match_strength == "name" and evidence.source_name not in SOCIAL_HOST_SOURCES.values():
        return True
    if evidence.source_name in SOCIAL_HOST_SOURCES.values():
        return bool(evidence.menu_evidence_found and business_names_match(business_name, evidence.name))
    return False


def _verified_sources(evidence: list[SourceEvidence]) -> list[str]:
    sources: list[str] = []
    for item in evidence:
        if item.match_strength not in {"phone", "address", "name"}:
            continue
        if item.source_name in SOCIAL_HOST_SOURCES.values():
            continue
        source = "google" if item.source_name == "google_maps" else item.source_name
        if source == "official_search":
            source = "official_site"
        sources.append(source)
    return _ordered_unique(sources)


def _evidence_pages(evidence: list[SourceEvidence]) -> list[dict[str, str]]:
    pages: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in evidence:
        if not item.source_url or item.source_url in seen:
            continue
        if not (item.menu_evidence_found or item.english_menu_signal or item.category_signal):
            continue
        seen.add(item.source_url)
        title = html_lib.escape(item.title or item.name or item.source_name)
        body = html_lib.escape(" ".join(part for part in [item.snippet, item.text_hint] if part)[:1500])
        pages.append({
            "url": item.source_url,
            "html": f"<html><body><h1>{title}</h1><p>{body}</p></body></html>",
        })
        if len(pages) >= 5:
            break
    return pages


def _best_canonical_name(business_name: str, evidence: list[SourceEvidence]) -> str:
    if business_name and not business_name_is_suspicious(business_name):
        return business_name
    for item in evidence:
        if item.name and not business_name_is_suspicious(item.name):
            return item.name
    return business_name


def _official_candidates_from_links(page_url: str, links: list[dict[str, str]]) -> list[str]:
    candidates: list[str] = []
    for link in links:
        official = _official_external_url(page_url, str(link.get("href") or ""))
        if is_official_candidate_url(official):
            candidates.append(official)
    return _ordered_unique(candidates)[:4]


def _social_links_from_links(links: list[dict[str, str]], *, base_url: str) -> list[str]:
    urls: list[str] = []
    for link in links:
        href = urllib.parse.urljoin(base_url, str(link.get("href") or ""))
        normalized = normalize_website_url(href)
        if normalized and is_social_url(normalized):
            urls.append(normalized)
    return _ordered_unique(urls)[:5]


def _operator_from_text(text: str) -> tuple[str, str]:
    name = ""
    for pattern in (
        r"運営会社[：:]\s*((?:株式会社|有限会社|合同会社).{2,40}?)(?:\s|$)",
        r"会社名[：:]\s*((?:株式会社|有限会社|合同会社).{2,40}?)(?:\s|$)",
        r"販売業者[：:]\s*((?:株式会社|有限会社|合同会社).{2,40}?)(?:\s|$)",
        r"((?:株式会社|有限会社|合同会社).{2,30}?)(?:\s|$)",
    ):
        match = re.search(pattern, text or "")
        if match:
            name = re.sub(r"\s+", " ", match.group(1)).strip(" 　。、,.")
            break
    url = ""
    if name:
        nearby = text[max(0, text.find(name) - 200):text.find(name) + 500] if name in text else text
        url_match = re.search(r"https?://[a-zA-Z0-9._\-]+\.[a-zA-Z]{2,}[^\s<>()\"']*", nearby)
        if url_match and is_official_candidate_url(url_match.group(0)):
            url = normalize_website_url(url_match.group(0))
    return name, url


def _best_name_from_sources(*, html: str, fallback: str) -> str:
    for candidate in extract_business_name_candidates(html):
        if not business_name_is_suspicious(candidate):
            return candidate
    return fallback


def _match_strength(
    *,
    candidate_name: str,
    candidate_address: str,
    candidate_phone: str,
    business_name: str,
    address: str,
    phone: str,
) -> str:
    if phone and candidate_phone and _phone_key(phone) == _phone_key(candidate_phone):
        return "phone"
    if address and candidate_address and _addresses_match(address, candidate_address):
        return "address"
    if business_name and candidate_name and business_names_match(business_name, candidate_name):
        return "name"
    return "weak"


def _addresses_match(left: str, right: str) -> bool:
    left_key = _address_key(left)
    right_key = _address_key(right)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    shorter, longer = sorted((left_key, right_key), key=len)
    return len(shorter) >= 8 and shorter in longer


def _address_key(value: str) -> str:
    return re.sub(r"[\s　,，。〒\-ー丁目番地号F階/]+", "", str(value or "").lower())


def _phone_key(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _result_text(result: dict[str, Any]) -> str:
    return " ".join(str(result.get(key) or "") for key in ("title", "snippet", "link"))


def _has_menu_signal(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(token.lower() in lowered for token in MENU_TOKENS)


def _has_english_signal(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(token.lower() in lowered for token in ENGLISH_MENU_TOKENS)


def _category_from_text(text: str) -> str:
    lowered = str(text or "").lower()
    if any(token.lower() in lowered for token in RAMEN_TOKENS):
        return "ramen"
    if any(token.lower() in lowered for token in IZAKAYA_TOKENS):
        return "izakaya"
    return ""


def _category_key(category: str) -> str:
    lowered = str(category or "").lower()
    if lowered == "ramen" or any(token.lower() in lowered for token in RAMEN_TOKENS):
        return "ramen"
    if lowered == "izakaya" or any(token.lower() in lowered for token in IZAKAYA_TOKENS):
        return "izakaya"
    return ""


def _category_term(category: str) -> str:
    return "居酒屋" if _category_key(category) == "izakaya" else "ラーメン"


def _source_name(url: str) -> str:
    host = _host(url)
    for token, source in {**PORTAL_HOST_SOURCES, **SOCIAL_HOST_SOURCES}.items():
        if token in host:
            return source
    return ""


def _host(url: str) -> str:
    return urllib.parse.urlparse(normalize_website_url(url)).netloc.lower().removeprefix("www.")


def _name_from_title(title: str) -> str:
    cleaned = html_lib.unescape(str(title or ""))
    cleaned = re.split(r"\s*(?:[|｜/（）()]|-|–|—)", cleaned, maxsplit=1)[0]
    return normalise_business_name(cleaned)


def _extract_japan_address(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "")
    pref_pattern = "|".join(re.escape(pref) for pref in JP_PREFECTURE_PREFIXES)
    match = re.search(rf"(?:〒\s?\d{{3}}-?\d{{4}}\s*)?(?:{pref_pattern})[^\s<>{{}}]{{4,90}}", cleaned)
    if not match:
        return ""
    address = match.group(0).strip(" 　,，。|｜")
    address = re.split(r"(?:TEL|Tel|tel|電話|営業時間|定休日|アクセス|Map|MAP)", address, maxsplit=1)[0]
    return address.strip(" 　,，。|｜")


def _extract_japanese_phone(text: str) -> str:
    for pattern in (
        r"(?:\+81[-\s]?\d{1,4}[-\s]\d{1,4}[-\s]\d{3,4})",
        r"(?:0\d{1,4}[-\s]\d{1,4}[-\s]\d{3,4})",
        r"(?:0\d{9,10})",
    ):
        match = re.search(pattern, text or "")
        if match:
            phone = match.group(0).strip()
            digits = _phone_key(phone)
            if phone.startswith("+81") or len(digits) in {10, 11}:
                return phone
    return ""


def _address_area(address: str) -> str:
    if not address:
        return ""
    match = re.match(r"(..[都道府県])?\s*(.{1,8}?[区市町村])", address)
    if match:
        return "".join(part for part in match.groups() if part)
    return str(address).split(",")[0].strip()[:10]


def _address_search_token(address: str) -> str:
    return _address_area(address) or str(address or "").split(",")[0].strip()


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _json_get(url: str, params: dict[str, str], timeout_seconds: int) -> dict[str, Any]:
    full_url = url + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(full_url, headers={
        "User-Agent": "webrefurb-menu-source-adapter/0.1",
        "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
    })
    try:
        with urllib.request.urlopen(request, timeout=max(3, min(timeout_seconds, 15))) as response:
            return json.loads(response.read(1_000_000).decode("utf-8"))
    except Exception:
        return {}


def _http_fetch_page(url: str, timeout_seconds: int = 8) -> str:
    request = urllib.request.Request(url, headers={
        "User-Agent": "webrefurb-menu-source-adapter/0.1",
        "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
    })
    with urllib.request.urlopen(request, timeout=max(3, min(timeout_seconds, 15))) as response:
        return response.read(700_000).decode("utf-8", errors="replace")


def _empty_search(**_: Any) -> dict[str, Any]:
    return {"organic": []}
