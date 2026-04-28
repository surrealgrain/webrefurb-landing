from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .utils import ensure_parent, utc_now


GOOGLE_PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DEFAULT_USER_AGENT = "webrefurb-menu-contact-crawler/0.1"


EMAIL_RE = re.compile(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
LINE_LINK_RE = re.compile(r"(?i)\b(?:https?://)?(?:lin\.ee/[a-z0-9_-]+|line\.me/(?:R/)?ti/p/[a-z0-9@._-]+)\b")
LINE_ID_RE = re.compile(r"(?<![a-z0-9._%+-])@[a-z0-9._-]{3,32}\b", re.IGNORECASE)
INSTAGRAM_RE = re.compile(r"(?i)\b(?:https?://)?(?:www\.)?instagram\.com/([a-z0-9._]{2,30})/?\b")

CONTACT_URL_TOKENS = (
    "contact",
    "contacts",
    "inquiry",
    "otoiawase",
    "toiawase",
    "mail",
    "form",
    "reserve",
    "reservation",
    "yoyaku",
    "company",
    "about",
    "access",
    "お問い合わせ",
    "問合せ",
    "お問合せ",
    "問い合わせ",
    "会社概要",
    "店舗情報",
    "予約",
)
CONTACT_TEXT_TOKENS = (
    "contact",
    "inquiry",
    "mail",
    "reservation",
    "お問い合わせ",
    "問合せ",
    "お問合せ",
    "問い合わせ",
    "会社概要",
    "店舗情報",
    "予約",
)
NON_BUSINESS_EMAIL_PREFIXES = (
    "noreply@",
    "no-reply@",
    "donotreply@",
    "do-not-reply@",
    "support@google.",
)
AGGREGATOR_HOST_TOKENS = (
    "tabelog.com",
    "hotpepper.jp",
    "gnavi.co.jp",
    "retty.me",
    "gurunavi.com",
    "google.com",
    "instagram.com",
    "facebook.com",
    "x.com",
    "twitter.com",
    "line.me",
    "lin.ee",
)
TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "yclid", "mc_cid", "mc_eid"}


@dataclass(frozen=True)
class DiscoveryTarget:
    name: str
    website: str
    category: str
    city: str
    source: str
    source_url: str = ""
    place_id: str = ""
    address: str = ""
    phone: str = ""


@dataclass(frozen=True)
class ContactSignals:
    emails: list[str] = field(default_factory=list)
    line_ids: list[str] = field(default_factory=list)
    line_links: list[str] = field(default_factory=list)
    instagram_handles: list[str] = field(default_factory=list)
    has_form: bool = False
    llm_mock_used: bool = False
    llm_mock_reason: str = ""


@dataclass(frozen=True)
class CrawlResult:
    business_name: str
    business_type: str
    city: str
    website: str
    extracted_email: str
    line_id: str
    line_link: str
    instagram_handle: str
    contact_url: str
    source: str
    source_url: str
    place_id: str = ""
    address: str = ""
    phone: str = ""
    has_contact_form: bool = False
    queued_contact_urls: list[str] = field(default_factory=list)
    all_emails: list[str] = field(default_factory=list)
    llm_mock_used: bool = False
    notes: list[str] = field(default_factory=list)


def normalize_website_url(url: str) -> str:
    """Normalize a website URL enough to dedupe crawl targets without losing path intent."""
    raw = (url or "").strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        raw = f"https:{raw}"
    initial = urllib.parse.urlparse(raw)
    if initial.scheme and initial.scheme not in {"http", "https"}:
        return ""
    if not re.match(r"(?i)^https?://", raw):
        raw = f"https://{raw}"

    parsed = urllib.parse.urlparse(raw)
    scheme = "https"
    host = parsed.netloc.lower()
    if not host:
        return ""
    if host.endswith(":80") or host.endswith(":443"):
        host = host.rsplit(":", 1)[0]
    path = parsed.path or ""
    if path != "/":
        path = path.rstrip("/")
    else:
        path = ""

    query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    kept_pairs = [
        (key, value)
        for key, value in query_pairs
        if key not in TRACKING_QUERY_KEYS and not any(key.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES)
    ]
    query = urllib.parse.urlencode(kept_pairs, doseq=True)
    return urllib.parse.urlunparse((scheme, host, path, "", query, ""))


def _normalized_host(url: str) -> str:
    return urllib.parse.urlparse(normalize_website_url(url)).netloc.removeprefix("www.")


def _is_same_site(base_url: str, candidate_url: str) -> bool:
    base_host = _normalized_host(base_url)
    candidate_host = _normalized_host(candidate_url)
    return bool(base_host and candidate_host and base_host == candidate_host)


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _usable_email(email: str) -> bool:
    lowered = email.lower()
    if any(lowered.startswith(prefix) for prefix in NON_BUSINESS_EMAIL_PREFIXES):
        return False
    domain = lowered.rsplit("@", 1)[-1]
    return not any(token in domain for token in AGGREGATOR_HOST_TOKENS)


def extract_contact_signals(html: str, text: str = "") -> ContactSignals:
    decoded = urllib.parse.unquote(f"{html or ''}\n{text or ''}")
    emails = _ordered_unique([email.lower() for email in EMAIL_RE.findall(decoded) if _usable_email(email)])
    line_links = _ordered_unique([match.group(0) for match in LINE_LINK_RE.finditer(decoded)])
    line_ids = _ordered_unique([match.group(0) for match in LINE_ID_RE.finditer(decoded) if "@" not in match.group(0)[1:]])
    instagram_handles = _ordered_unique([match.group(1).lower() for match in INSTAGRAM_RE.finditer(decoded)])
    has_form = bool(re.search(r"(?is)<form\b", html or ""))
    return ContactSignals(
        emails=emails,
        line_ids=line_ids,
        line_links=line_links,
        instagram_handles=instagram_handles,
        has_form=has_form,
    )


def mock_llm_parse_contact_points(text: str, *, contact_intent: bool) -> ContactSignals:
    """Phase 3 placeholder for a future local inference endpoint.

    The mock is deliberately conservative: it reuses deterministic regex extraction and records
    that an LLM fallback would have been invoked when the page has contact intent but no regex hit.
    """
    signals = extract_contact_signals("", text)
    if not contact_intent or signals.emails or signals.line_ids or signals.line_links or signals.instagram_handles:
        return signals
    return ContactSignals(
        llm_mock_used=True,
        llm_mock_reason="contact_intent_without_regex_hit",
    )


def contact_candidate_urls(base_url: str, anchors: list[dict[str, str]], *, limit: int = 5) -> list[str]:
    candidates: list[str] = []
    for anchor in anchors:
        href = (anchor.get("href") or "").strip()
        label = (anchor.get("text") or "").strip().lower()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = normalize_website_url(urllib.parse.urljoin(base_url, href))
        if not absolute or not _is_same_site(base_url, absolute):
            continue
        parsed = urllib.parse.urlparse(absolute)
        haystack = " ".join([
            urllib.parse.unquote(parsed.path).lower(),
            urllib.parse.unquote(parsed.query).lower(),
            label,
        ])
        if not any(token.lower() in haystack for token in CONTACT_URL_TOKENS + CONTACT_TEXT_TOKENS):
            continue
        candidates.append(absolute)
    return _ordered_unique(candidates)[:limit]


def _official_external_url(directory_url: str, href: str) -> str:
    raw_href = (href or "").strip()
    if not raw_href or raw_href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return ""
    absolute_raw = urllib.parse.urljoin(directory_url, raw_href)
    redirect_target = _redirect_target_url(absolute_raw)
    absolute = normalize_website_url(redirect_target or absolute_raw)
    if not absolute:
        return ""
    directory_host = _normalized_host(directory_url)
    candidate_host = _normalized_host(absolute)
    if not candidate_host or candidate_host == directory_host:
        return ""
    if any(token in candidate_host for token in AGGREGATOR_HOST_TOKENS):
        return ""
    return absolute


def _redirect_target_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    for key in ("url", "u", "target", "to", "dest", "destination", "redirect", "redirect_url"):
        for value in query.get(key, []):
            decoded = urllib.parse.unquote(value)
            if re.match(r"(?i)^https?://", decoded):
                return decoded
    return ""


async def _http_json_request(url: str, *, payload: dict[str, Any], headers: dict[str, str], timeout_seconds: int) -> dict[str, Any]:
    def _run_request() -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    return await asyncio.to_thread(_run_request)


def _places_payload(query: str, city: str, *, page_size: int) -> dict[str, Any]:
    text_query = f"{query} {city}".strip()
    return {
        "textQuery": text_query,
        "languageCode": "ja",
        "regionCode": "JP",
        "pageSize": max(1, min(page_size, 20)),
    }


async def discover_google_places(
    *,
    api_key: str,
    city: str,
    categories: list[str],
    page_size: int = 20,
    timeout_seconds: int = 15,
) -> list[DiscoveryTarget]:
    """Phase 1.1: query Google Places Text Search and return places with websites."""
    if not api_key:
        return []

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": ",".join([
            "places.id",
            "places.displayName",
            "places.websiteUri",
            "places.formattedAddress",
            "places.nationalPhoneNumber",
            "places.googleMapsUri",
        ]),
    }
    discovered: list[DiscoveryTarget] = []
    for category in categories:
        payload = _places_payload(category, city, page_size=page_size)
        try:
            data = await _http_json_request(
                GOOGLE_PLACES_TEXT_SEARCH_URL,
                payload=payload,
                headers=headers,
                timeout_seconds=timeout_seconds,
            )
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            continue

        for place in data.get("places") or []:
            website = normalize_website_url(str(place.get("websiteUri") or ""))
            if not website:
                continue
            name_payload = place.get("displayName") or {}
            name = str(name_payload.get("text") or "").strip()
            discovered.append(DiscoveryTarget(
                name=name,
                website=website,
                category=category,
                city=city,
                source="google_places",
                source_url=str(place.get("googleMapsUri") or ""),
                place_id=str(place.get("id") or ""),
                address=str(place.get("formattedAddress") or ""),
                phone=str(place.get("nationalPhoneNumber") or ""),
            ))
    return discovered


async def discover_directory_urls(
    *,
    directory_urls: list[str],
    city: str,
    category: str,
    max_detail_pages: int = 12,
    navigation_timeout_ms: int = 20_000,
) -> list[DiscoveryTarget]:
    """Phase 1.2: lightly crawl directory pages and extract likely official websites."""
    if not directory_urls:
        return []

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=DEFAULT_USER_AGENT, locale="ja-JP")
        try:
            results: list[DiscoveryTarget] = []
            for directory_url in directory_urls:
                page = await context.new_page()
                page.set_default_navigation_timeout(navigation_timeout_ms)
                try:
                    await page.goto(directory_url, wait_until="domcontentloaded")
                    await page.wait_for_load_state("networkidle", timeout=5_000)
                except Exception:
                    await page.close()
                    continue

                page_targets, detail_urls = await _extract_directory_page_targets(
                    page,
                    directory_url=directory_url,
                    city=city,
                    category=category,
                )
                results.extend(page_targets)
                await page.close()

                for detail_url in detail_urls[:max_detail_pages]:
                    detail_page = await context.new_page()
                    detail_page.set_default_navigation_timeout(navigation_timeout_ms)
                    try:
                        await detail_page.goto(detail_url, wait_until="domcontentloaded")
                        await detail_page.wait_for_load_state("networkidle", timeout=5_000)
                        detail_targets, _ = await _extract_directory_page_targets(
                            detail_page,
                            directory_url=detail_url,
                            city=city,
                            category=category,
                        )
                        results.extend(detail_targets)
                    except Exception:
                        pass
                    finally:
                        await detail_page.close()
            return dedupe_targets(results)
        finally:
            await browser.close()


async def _extract_directory_page_targets(page: Any, *, directory_url: str, city: str, category: str) -> tuple[list[DiscoveryTarget], list[str]]:
    anchors = await page.evaluate(
        """() => Array.from(document.links).map((a) => ({
            href: a.href || "",
            text: (a.innerText || a.textContent || "").trim(),
            aria: a.getAttribute("aria-label") || ""
        }))"""
    )
    title = (await page.title()).strip()
    targets: list[DiscoveryTarget] = []
    detail_urls: list[str] = []
    directory_host = _normalized_host(directory_url)

    for anchor in anchors:
        href = str(anchor.get("href") or "")
        text = " ".join([str(anchor.get("text") or ""), str(anchor.get("aria") or "")]).strip()
        official = _official_external_url(directory_url, href)
        if official:
            targets.append(DiscoveryTarget(
                name=text or title,
                website=official,
                category=category,
                city=city,
                source=_directory_source_name(directory_url),
                source_url=directory_url,
            ))
            continue

        normalized = normalize_website_url(href)
        if not normalized:
            continue
        parsed = urllib.parse.urlparse(normalized)
        if parsed.netloc.removeprefix("www.") != directory_host:
            continue
        detail_haystack = f"{urllib.parse.unquote(parsed.path).lower()} {text.lower()}"
        if any(skip in detail_haystack for skip in ("login", "reserve", "map", "photo", "review", "coupon")):
            continue
        if any(token in detail_haystack for token in ("rst", "restaurant", "shop", "strj", "detail", "izakaya", "ramen")):
            detail_urls.append(normalized)

    return dedupe_targets(targets), _ordered_unique(detail_urls)


def _directory_source_name(url: str) -> str:
    host = _normalized_host(url)
    if "tabelog" in host:
        return "tabelog"
    if "hotpepper" in host:
        return "hotpepper"
    return host or "directory"


def dedupe_targets(targets: list[DiscoveryTarget]) -> list[DiscoveryTarget]:
    deduped: dict[str, DiscoveryTarget] = {}
    for target in targets:
        website = normalize_website_url(target.website)
        if not website:
            continue
        host = _normalized_host(website)
        key = host or website
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = DiscoveryTarget(**{**asdict(target), "website": website})
            continue
        if existing.source != target.source and target.source not in existing.source.split("+"):
            deduped[key] = DiscoveryTarget(**{
                **asdict(existing),
                "source": f"{existing.source}+{target.source}",
                "source_url": existing.source_url or target.source_url,
                "place_id": existing.place_id or target.place_id,
                "address": existing.address or target.address,
                "phone": existing.phone or target.phone,
            })
    return list(deduped.values())


async def crawl_target_contacts(
    target: DiscoveryTarget,
    *,
    context: Any,
    max_contact_pages: int = 5,
    navigation_timeout_ms: int = 20_000,
) -> CrawlResult:
    """Phase 2: deep crawl a single domain for email, LINE, forms, and contact URLs."""
    homepage = await context.new_page()
    homepage.set_default_navigation_timeout(navigation_timeout_ms)
    notes: list[str] = []
    queued_urls: list[str] = []
    all_signals = ContactSignals()
    contact_url = target.website

    try:
        try:
            await homepage.goto(target.website, wait_until="domcontentloaded")
            await homepage.wait_for_load_state("networkidle", timeout=5_000)
        except Exception as exc:
            notes.append(f"homepage_fetch_failed:{type(exc).__name__}")
            return CrawlResult(
                business_name=target.name,
                business_type=target.category,
                city=target.city,
                website=target.website,
                extracted_email="",
                line_id="",
                line_link="",
                instagram_handle="",
                contact_url="",
                source=target.source,
                source_url=target.source_url,
                place_id=target.place_id,
                address=target.address,
                phone=target.phone,
                notes=notes,
            )

        html = await homepage.content()
        text = await homepage.locator("body").inner_text(timeout=2_000) if await homepage.locator("body").count() else ""
        all_signals = _merge_signals(all_signals, extract_contact_signals(html, text))

        anchors = await homepage.evaluate(
            """() => Array.from(document.links).map((a) => ({
                href: a.href || "",
                text: (a.innerText || a.textContent || "").trim()
            }))"""
        )
        queued_urls = contact_candidate_urls(target.website, anchors, limit=max_contact_pages)

        if not all_signals.emails:
            for url in queued_urls:
                page = await context.new_page()
                page.set_default_navigation_timeout(navigation_timeout_ms)
                try:
                    await page.goto(url, wait_until="domcontentloaded")
                    await page.wait_for_load_state("networkidle", timeout=5_000)
                    page_html = await page.content()
                    page_text = await page.locator("body").inner_text(timeout=2_000) if await page.locator("body").count() else ""
                    signals = extract_contact_signals(page_html, page_text)
                    contact_intent = _has_contact_intent(url, page_text)
                    if not signals.emails and contact_intent:
                        signals = _merge_signals(signals, mock_llm_parse_contact_points(page_text, contact_intent=True))
                    all_signals = _merge_signals(all_signals, signals)
                    if signals.emails or signals.line_ids or signals.line_links or signals.has_form:
                        contact_url = url
                    if all_signals.emails:
                        break
                except Exception as exc:
                    notes.append(f"contact_page_failed:{url}:{type(exc).__name__}")
                finally:
                    await page.close()

        if not all_signals.emails and not all_signals.llm_mock_used:
            fallback = mock_llm_parse_contact_points(text, contact_intent=_has_contact_intent(target.website, text))
            all_signals = _merge_signals(all_signals, fallback)

        return CrawlResult(
            business_name=target.name,
            business_type=target.category,
            city=target.city,
            website=target.website,
            extracted_email=all_signals.emails[0] if all_signals.emails else "",
            line_id=all_signals.line_ids[0] if all_signals.line_ids else "",
            line_link=all_signals.line_links[0] if all_signals.line_links else "",
            instagram_handle=all_signals.instagram_handles[0] if all_signals.instagram_handles else "",
            contact_url=contact_url if (all_signals.emails or all_signals.line_ids or all_signals.line_links or all_signals.has_form) else "",
            source=target.source,
            source_url=target.source_url,
            place_id=target.place_id,
            address=target.address,
            phone=target.phone,
            has_contact_form=all_signals.has_form,
            queued_contact_urls=queued_urls,
            all_emails=all_signals.emails,
            llm_mock_used=all_signals.llm_mock_used,
            notes=notes,
        )
    finally:
        await homepage.close()


async def crawl_contacts(
    targets: list[DiscoveryTarget],
    *,
    concurrency: int = 4,
    max_contact_pages: int = 5,
    navigation_timeout_ms: int = 20_000,
) -> list[CrawlResult]:
    """Phase 2 batch runner."""
    if not targets:
        return []

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=DEFAULT_USER_AGENT, locale="ja-JP")
        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def _run(target: DiscoveryTarget) -> CrawlResult:
            async with semaphore:
                return await crawl_target_contacts(
                    target,
                    context=context,
                    max_contact_pages=max_contact_pages,
                    navigation_timeout_ms=navigation_timeout_ms,
                )

        try:
            return await asyncio.gather(*[_run(target) for target in targets])
        finally:
            await browser.close()


async def run_contact_pipeline(
    *,
    city: str,
    categories: list[str],
    places_api_key: str = "",
    directory_urls: list[str] | None = None,
    max_places_per_category: int = 20,
    max_directory_detail_pages: int = 12,
    concurrency: int = 4,
) -> dict[str, Any]:
    """Run Phase 1 discovery plus Phase 2 deep crawl, with Phase 3 mocked extraction."""
    directory_urls = directory_urls or []
    places_task = discover_google_places(
        api_key=places_api_key,
        city=city,
        categories=categories,
        page_size=max_places_per_category,
    )
    directory_tasks = [
        discover_directory_urls(
            directory_urls=directory_urls,
            city=city,
            category=category,
            max_detail_pages=max_directory_detail_pages,
        )
        for category in categories
    ]
    discovery_groups = await asyncio.gather(places_task, *directory_tasks)
    targets = dedupe_targets([target for group in discovery_groups for target in group])
    crawl_results = await crawl_contacts(targets, concurrency=concurrency)
    return {
        "run_id": f"wrm-contact-{utc_now().replace(':', '').replace('-', '').replace('+00:00', 'z').lower()}",
        "city": city,
        "categories": categories,
        "discovered_targets": len(targets),
        "results_with_email": sum(1 for result in crawl_results if result.extracted_email),
        "results_with_line": sum(1 for result in crawl_results if result.line_id or result.line_link),
        "results_with_form_only": sum(1 for result in crawl_results if result.has_contact_form and not result.extracted_email),
        "targets": [asdict(target) for target in targets],
        "results": [asdict(result) for result in crawl_results],
    }


def _merge_signals(left: ContactSignals, right: ContactSignals) -> ContactSignals:
    return ContactSignals(
        emails=_ordered_unique([*left.emails, *right.emails]),
        line_ids=_ordered_unique([*left.line_ids, *right.line_ids]),
        line_links=_ordered_unique([*left.line_links, *right.line_links]),
        instagram_handles=_ordered_unique([*left.instagram_handles, *right.instagram_handles]),
        has_form=left.has_form or right.has_form,
        llm_mock_used=left.llm_mock_used or right.llm_mock_used,
        llm_mock_reason=left.llm_mock_reason or right.llm_mock_reason,
    )


def _has_contact_intent(url: str, text: str) -> bool:
    haystack = f"{urllib.parse.unquote(url).lower()} {(text or '').lower()}"
    return any(token.lower() in haystack for token in CONTACT_URL_TOKENS + CONTACT_TEXT_TOKENS)


def write_results_csv(path: Path, results: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    fieldnames = [
        "Business Name",
        "Type",
        "City",
        "Extracted Email",
        "LINE ID",
        "LINE Link",
        "Instagram",
        "Contact URL",
        "Website",
        "Source",
        "Source URL",
        "Has Contact Form",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow({
                "Business Name": result.get("business_name", ""),
                "Type": result.get("business_type", ""),
                "City": result.get("city", ""),
                "Extracted Email": result.get("extracted_email", ""),
                "LINE ID": result.get("line_id", ""),
                "LINE Link": result.get("line_link", ""),
                "Instagram": result.get("instagram_handle", ""),
                "Contact URL": result.get("contact_url", ""),
                "Website": result.get("website", ""),
                "Source": result.get("source", ""),
                "Source URL": result.get("source_url", ""),
                "Has Contact Form": "true" if result.get("has_contact_form") else "false",
            })


def default_places_api_key() -> str:
    return os.environ.get("GOOGLE_PLACES_API_KEY", "")
