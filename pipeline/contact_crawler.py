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
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .utils import ensure_parent, utc_now


GOOGLE_PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DEFAULT_USER_AGENT = "webrefurb-menu-contact-crawler/0.1"


EMAIL_RE = re.compile(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
# Patterns to exclude from second-pass contact path probing
_EXCLUDED_CONTACT_PATH_TOKENS = (
    "reserve",
    "reservation",
    "booking",
    "book-a-table",
    "yoyaku",
    "tablecheck",
    "ebica",
    "toreta",
    "order",
    "cart",
    "checkout",
    "newsletter",
    "subscribe",
    "recruit",
    "career",
    "login",
    "signup",
    "account",
    "予約",
    "注文",
    "採用",
    "求人",
    "ログイン",
)
CONTACT_URL_TOKENS = (
    "contact",
    "contacts",
    "inquiry",
    "otoiawase",
    "toiawase",
    "mail",
    "form",
    "company",
    "about",
    "access",
    "お問い合わせ",
    "問合せ",
    "お問合せ",
    "問い合わせ",
    "会社概要",
    "店舗情報",
)
CONTACT_TEXT_TOKENS = (
    "contact",
    "inquiry",
    "mail",
    "お問い合わせ",
    "問合せ",
    "お問合せ",
    "問い合わせ",
    "会社概要",
    "店舗情報",
)
NON_BUSINESS_EMAIL_PREFIXES = (
    "noreply@",
    "no-reply@",
    "donotreply@",
    "do-not-reply@",
    "support@google.",
)
NON_BUSINESS_EMAIL_DOMAIN_TOKENS = (
    "sentry.io",
    "ingest.sentry",
    "sentry.wixpress.com",
    "sentry-next.wixpress.com",
    "wixpress.com",
    "example.com",
    "example.net",
    "example.org",
)
NON_BUSINESS_EMAIL_SUFFIXES = (
    ".avif",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".webp",
)
# Common Japanese contact page paths for second-pass route recovery
CONTACT_PATH_PROBES = (
    "/contact",
    "/inquiry",
    "/otoiawase",
    "/toiawase",
    "/mail",
    "/form",
    "/contact/",
    "/inquiry/",
    "/otoiawase/",
    "/お問い合わせ",
    "/info",
    "/access",
)
# Regex for full-width @ (＠) used in obfuscated Japanese emails
FULLWIDTH_AT_RE = re.compile(r"(?i)\b([a-z0-9._%+-]+)\uff20([a-z0-9.-]+\.[a-z]{2,})\b")
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
    has_form: bool = False
    form_actions: list[str] = field(default_factory=list)
    required_fields: list[str] = field(default_factory=list)
    form_field_names: list[str] = field(default_factory=list)
    contact_form_profile: str = "unknown"
    page_text_hint: str = ""
    llm_mock_used: bool = False
    llm_mock_reason: str = ""


@dataclass(frozen=True)
class CrawlResult:
    business_name: str
    business_type: str
    city: str
    website: str
    extracted_email: str
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


def is_usable_business_email(email: str) -> bool:
    lowered = email.lower()
    if any(lowered.startswith(prefix) for prefix in NON_BUSINESS_EMAIL_PREFIXES):
        return False
    domain = lowered.rsplit("@", 1)[-1]
    if any(lowered.endswith(suffix) or domain.endswith(suffix) for suffix in NON_BUSINESS_EMAIL_SUFFIXES):
        return False
    if any(token in domain for token in NON_BUSINESS_EMAIL_DOMAIN_TOKENS):
        return False
    return not any(token in domain for token in AGGREGATOR_HOST_TOKENS)


def _usable_email(email: str) -> bool:
    return is_usable_business_email(email)


def extract_contact_signals(html: str, text: str = "") -> ContactSignals:
    decoded = urllib.parse.unquote(f"{html or ''}\n{text or ''}")
    # Replace full-width @ with standard @ for email detection
    decoded_for_email = FULLWIDTH_AT_RE.sub(r"\1@\2", decoded)
    emails = _ordered_unique([email.lower() for email in EMAIL_RE.findall(decoded_for_email) if _usable_email(email)])
    literal_or_js_form = bool(re.search(r"(?is)<form\b", html or "")) or _looks_like_javascript_contact_form(html)
    form_actions = _extract_form_actions(html)
    required_fields = _extract_required_form_fields(html)
    form_field_names = _extract_form_field_names(html)
    profile = _classify_contact_form_profile(
        html=html,
        text=text,
        has_form=literal_or_js_form,
        form_actions=form_actions,
        required_fields=required_fields,
        form_field_names=form_field_names,
    )
    has_form = literal_or_js_form and profile != "hidden_only"
    return ContactSignals(
        emails=emails,
        has_form=has_form,
        form_actions=form_actions,
        required_fields=required_fields,
        form_field_names=form_field_names,
        contact_form_profile=profile,
        page_text_hint=_page_text_hint(html=html, text=text),
    )


def _extract_form_actions(html: str) -> list[str]:
    actions: list[str] = []
    for tag in re.findall(r"(?is)<form\b[^>]*>", html or ""):
        match = re.search(r'''(?is)\baction\s*=\s*["']([^"']+)["']''', tag)
        if match:
            actions.append(urllib.parse.unquote(match.group(1)).strip())
    return _ordered_unique([action for action in actions if action])


def _extract_required_form_fields(html: str) -> list[str]:
    fields: list[str] = []
    form_blocks = re.findall(r"(?is)<form\b[^>]*>.*?</form>", html or "")
    if not form_blocks and _looks_like_javascript_contact_form(html):
        form_blocks = [html or ""]
    for block in form_blocks:
        for tag in re.findall(r"(?is)<(?:input|select|textarea)\b[^>]*>", block):
            if not _tag_marks_required(tag):
                continue
            field = _first_attr(tag, ("name", "id", "placeholder", "aria-label", "title"))
            if field:
                fields.append(urllib.parse.unquote(field).strip())
    return _ordered_unique([field for field in fields if field])


def _extract_form_field_names(html: str) -> list[str]:
    fields: list[str] = []
    form_blocks = _form_blocks_for_analysis(html)
    for block in form_blocks:
        for tag in re.findall(r"(?is)<(?:input|select|textarea)\b[^>]*>", block):
            if _tag_is_hidden_field(tag):
                continue
            field = _first_attr(tag, ("name", "id", "placeholder", "aria-label", "title"))
            if field:
                fields.append(urllib.parse.unquote(field).strip())
    return _ordered_unique([field for field in fields if field])


def _form_blocks_for_analysis(html: str) -> list[str]:
    form_blocks = re.findall(r"(?is)<form\b[^>]*>.*?</form>", html or "")
    if not form_blocks and _looks_like_javascript_contact_form(html):
        form_blocks = [html or ""]
    return form_blocks


def _tag_marks_required(tag: str) -> bool:
    if re.search(r"(?is)\brequired\b", tag):
        return True
    if re.search(r'''(?is)\baria-required\s*=\s*["']?true["']?''', tag):
        return True
    class_match = re.search(r'''(?is)\bclass\s*=\s*["']([^"']*)["']''', tag)
    if class_match and "require" in class_match.group(1).lower().split():
        return True
    name = _first_attr(tag, ("name", "id"))
    return bool(re.search(r"(?i)(?:^|_)must(?:$|_)", name or ""))


def _looks_like_javascript_contact_form(html: str) -> bool:
    haystack = html or ""
    if not re.search(r"(?is)<(?:input|textarea|select)\b", haystack):
        return False
    if not _has_visible_user_form_field(haystack):
        return False
    if not re.search(r"(?is)(?:type\s*=\s*['\"]submit['\"]|送信|確認|submit)", haystack):
        return False
    if not re.search(r"(?is)(?:contact|inquiry|お問い合わせ|問合せ|メールアドレス|fc-form|CMS-FORM|mw_wp_form|wpcf7)", haystack):
        return False
    return True


def _classify_contact_form_profile(
    *,
    html: str,
    text: str,
    has_form: bool,
    form_actions: list[str],
    required_fields: list[str],
    form_field_names: list[str],
) -> str:
    if not has_form:
        return "unknown"
    haystack = _form_profile_haystack(
        html=html,
        text=text,
        form_actions=form_actions,
        required_fields=required_fields,
        form_field_names=form_field_names,
    )
    if _form_is_hidden_only(html):
        return "hidden_only"
    required_haystack = " ".join(required_fields).lower()
    if _contains_form_profile_token(required_haystack, _PHONE_FIELD_TOKENS):
        return "phone_required"
    if _contains_form_profile_token(required_haystack, _RESERVATION_REQUIRED_FIELD_TOKENS) or _contains_form_profile_token(haystack, _RESERVATION_FORM_TOKENS):
        return "reservation_only"
    if _contains_form_profile_token(haystack, _NEWSLETTER_FORM_TOKENS):
        return "newsletter"
    if _contains_form_profile_token(haystack, _COMMERCE_FORM_TOKENS):
        return "commerce"
    if _contains_form_profile_token(haystack, _RECRUITING_FORM_TOKENS):
        return "recruiting"
    if _contains_form_profile_token(haystack, _GENERAL_INQUIRY_FORM_TOKENS) and _has_visible_user_form_field(html):
        return "supported_inquiry"
    return "unknown"


_PHONE_FIELD_TOKENS = (
    "tel",
    "telephone",
    "phone",
    "mobile",
    "電話",
    "電話番号",
    "携帯",
)
_RESERVATION_REQUIRED_FIELD_TOKENS = (
    "date",
    "time",
    "datetime",
    "party",
    "people",
    "person",
    "persons",
    "人数",
    "来店日",
    "来店時間",
    "予約日",
    "予約時間",
    "予約人数",
    "コース",
)
_RESERVATION_FORM_TOKENS = (
    "reservation",
    "reserve",
    "booking",
    "book-a-table",
    "tablecheck",
    "yoyaku",
    "ご予約",
    "予約",
    "空席",
    "来店日時",
)
_NEWSLETTER_FORM_TOKENS = (
    "newsletter",
    "subscribe",
    "mailmagazine",
    "mail-magazine",
    "メールマガジン",
    "メルマガ",
    "購読",
)
_COMMERCE_FORM_TOKENS = (
    "checkout",
    "cart",
    "order",
    "takeout",
    "take-out",
    "delivery",
    "注文",
    "購入",
    "テイクアウト",
    "デリバリー",
)
_RECRUITING_FORM_TOKENS = (
    "recruit",
    "career",
    "job",
    "採用",
    "求人",
    "応募",
)
_GENERAL_INQUIRY_FORM_TOKENS = (
    "contact",
    "contacts",
    "inquiry",
    "otoiawase",
    "toiawase",
    "message",
    "お問い合わせ",
    "お問合せ",
    "問い合わせ",
    "問合せ",
    "ご相談",
    "メールアドレス",
    "wpcf7",
    "mw_wp_form",
    "fc-form",
    "cms-form",
)


def _form_profile_haystack(
    *,
    html: str,
    text: str,
    form_actions: list[str],
    required_fields: list[str],
    form_field_names: list[str],
) -> str:
    return urllib.parse.unquote(" ".join([
        html or "",
        text or "",
        " ".join(form_actions),
        " ".join(required_fields),
        " ".join(form_field_names),
    ])).lower()


def _contains_form_profile_token(haystack: str, tokens: tuple[str, ...]) -> bool:
    return any(token.lower() in haystack for token in tokens)


def _form_is_hidden_only(html: str) -> bool:
    blocks = re.findall(r"(?is)<form\b[^>]*>.*?</form>", html or "")
    if not blocks:
        return False
    saw_fields = False
    for block in blocks:
        fields = re.findall(r"(?is)<(?:input|select|textarea)\b[^>]*>", block)
        if not fields:
            continue
        saw_fields = True
        if any(not _tag_is_hidden_field(tag) for tag in fields):
            return False
    return saw_fields


def _has_visible_user_form_field(html: str) -> bool:
    return any(
        not _tag_is_hidden_field(tag)
        for tag in re.findall(r"(?is)<(?:input|select|textarea)\b[^>]*>", html or "")
    )


def _tag_is_hidden_field(tag: str) -> bool:
    if re.search(r'''(?is)\btype\s*=\s*["']?hidden["']?''', tag):
        return True
    if re.search(r"(?is)\bhidden\b", tag):
        return True
    if re.search(r'''(?is)\bstyle\s*=\s*["'][^"']*display\s*:\s*none''', tag):
        return True
    return False


def _page_text_hint(*, html: str, text: str) -> str:
    source = text or re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html or "")
    source = re.sub(r"(?is)<[^>]+>", " ", source)
    return re.sub(r"\s+", " ", urllib.parse.unquote(source)).strip()[:500]


def _first_attr(tag: str, names: tuple[str, ...]) -> str:
    for name in names:
        match = re.search(rf'''(?is)\b{name}\s*=\s*["']([^"']+)["']''', tag)
        if match:
            return match.group(1)
    return ""


def mock_llm_parse_contact_points(text: str, *, contact_intent: bool) -> ContactSignals:
    """Phase 3 placeholder for a future local inference endpoint.

    The mock is deliberately conservative: it reuses deterministic regex extraction and records
    that an LLM fallback would have been invoked when the page has contact intent but no regex hit.
    """
    signals = extract_contact_signals("", text)
    if not contact_intent or signals.emails or signals.has_form:
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


class _AnchorCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        label = " ".join(
            value.strip()
            for value in (attrs_dict.get("aria-label", ""), attrs_dict.get("title", ""))
            if value.strip()
        )
        self._current = {"href": attrs_dict.get("href", ""), "text": label}

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        self._current["text"] = " ".join([self._current.get("text", ""), data.strip()]).strip()

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current is None:
            return
        self.anchors.append(self._current)
        self._current = None


def contact_candidate_urls_from_html(base_url: str, html: str, *, limit: int = 5) -> list[str]:
    """Extract same-site contact candidate URLs from static HTML anchors."""
    parser = _AnchorCollector()
    try:
        parser.feed(html or "")
    except Exception:
        return []
    return contact_candidate_urls(base_url, parser.anchors, limit=limit)


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
    if "gnavi" in host or "gurunavi" in host:
        return "gurunavi"
    if "ramendb" in host:
        return "ramendb"
    if "retty" in host:
        return "retty"
    if "hitosara" in host:
        return "hitosara"
    if "paypaygourmet" in host:
        return "paypay_gourmet"
    if "yahoo" in host:
        return "yahoo_local"
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


async def recover_contact_routes(
    target: DiscoveryTarget,
    *,
    context: Any,
    max_probes: int = 6,
    navigation_timeout_ms: int = 15_000,
) -> CrawlResult | None:
    """Second-pass route recovery for website_only first-party candidates.

    Probes deterministic contact paths (/contact, /inquiry, /otoiawase, etc.)
    and parses footer/nav links to find hidden contact routes.
    Returns None if no usable contact is found.
    """
    base_url = target.website
    if not base_url:
        return None

    all_signals = ContactSignals()
    contact_url = base_url
    notes: list[str] = []

    # Phase 1: Parse homepage for footer/nav contact links
    homepage = await context.new_page()
    homepage.set_default_navigation_timeout(navigation_timeout_ms)
    try:
        await homepage.goto(base_url, wait_until="domcontentloaded")
        await homepage.wait_for_load_state("networkidle", timeout=5_000)
        html = await homepage.content()
        text = await homepage.locator("body").inner_text(timeout=2_000) if await homepage.locator("body").count() else ""

        # Check homepage itself for contact signals
        all_signals = _merge_signals(all_signals, extract_contact_signals(html, text))

        # Extract footer/nav links that might be contact pages
        anchors = await homepage.evaluate(
            """() => {
                const links = Array.from(document.querySelectorAll('a'));
                return links.map((a) => ({
                    href: a.href || "",
                    text: (a.innerText || a.textContent || "").trim()
                }));
            }"""
        )
        candidate_urls = contact_candidate_urls(base_url, anchors, limit=10)

        # Also build deterministic path probes
        probe_urls: list[str] = []
        for path in CONTACT_PATH_PROBES:
            probe_url = normalize_website_url(urllib.parse.urljoin(base_url, path))
            if probe_url and _is_same_site(base_url, probe_url):
                probe_urls.append(probe_url)

        # Combine: anchor-based first, then deterministic probes
        urls_to_try = _ordered_unique([*candidate_urls, *probe_urls])[:max_probes]
    except Exception as exc:
        notes.append(f"recovery_homepage_failed:{type(exc).__name__}")
        await homepage.close()
        return None
    finally:
        await homepage.close()

    if all_signals.emails and _usable_email(all_signals.emails[0]):
        return CrawlResult(
            business_name=target.name,
            business_type=target.category,
            city=target.city,
            website=target.website,
            extracted_email=all_signals.emails[0],
            contact_url=base_url,
            source=target.source,
            source_url=target.source_url,
            place_id=target.place_id,
            address=target.address,
            phone=target.phone,
            has_contact_form=_signals_have_supported_contact_form(all_signals),
            queued_contact_urls=urls_to_try if 'urls_to_try' in dir() else [],
            all_emails=all_signals.emails,
            notes=notes,
        )

    # Phase 2: Probe candidate URLs
    for url in urls_to_try:
        # Skip reservation/booking/order paths
        url_lower = urllib.parse.unquote(url).lower()
        if any(token in url_lower for token in _EXCLUDED_CONTACT_PATH_TOKENS):
            continue

        page = await context.new_page()
        page.set_default_navigation_timeout(navigation_timeout_ms)
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle", timeout=5_000)
            page_html = await page.content()
            page_text = await page.locator("body").inner_text(timeout=2_000) if await page.locator("body").count() else ""
            signals = extract_contact_signals(page_html, page_text)
            all_signals = _merge_signals(all_signals, signals)
            if signals.emails or _signals_have_supported_contact_form(signals):
                contact_url = url
            if all_signals.emails:
                break
        except Exception as exc:
            notes.append(f"recovery_probe_failed:{url}:{type(exc).__name__}")
        finally:
            await page.close()

    has_email = bool(all_signals.emails) and _usable_email(all_signals.emails[0])
    has_form = _signals_have_supported_contact_form(all_signals)
    if not has_email and not has_form:
        return None

    return CrawlResult(
        business_name=target.name,
        business_type=target.category,
        city=target.city,
        website=target.website,
        extracted_email=all_signals.emails[0] if has_email else "",
        contact_url=contact_url if (has_email or has_form) else "",
        source=target.source,
        source_url=target.source_url,
        place_id=target.place_id,
        address=target.address,
        phone=target.phone,
        has_contact_form=has_form,
        queued_contact_urls=urls_to_try if 'urls_to_try' in dir() else [],
        all_emails=all_signals.emails,
        notes=notes,
    )


async def crawl_target_contacts(
    target: DiscoveryTarget,
    *,
    context: Any,
    max_contact_pages: int = 5,
    navigation_timeout_ms: int = 20_000,
) -> CrawlResult:
    """Phase 2: deep crawl a single domain for email, contact forms, and contact URLs."""
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
                    if signals.emails or _signals_have_supported_contact_form(signals):
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
            contact_url=contact_url if (all_signals.emails or _signals_have_supported_contact_form(all_signals)) else "",
            source=target.source,
            source_url=target.source_url,
            place_id=target.place_id,
            address=target.address,
            phone=target.phone,
            has_contact_form=_signals_have_supported_contact_form(all_signals),
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
        "results_with_form_only": sum(1 for result in crawl_results if result.has_contact_form and not result.extracted_email),
        "targets": [asdict(target) for target in targets],
        "results": [asdict(result) for result in crawl_results],
    }


def _merge_signals(left: ContactSignals, right: ContactSignals) -> ContactSignals:
    return ContactSignals(
        emails=_ordered_unique([*left.emails, *right.emails]),
        has_form=left.has_form or right.has_form,
        form_actions=_ordered_unique([*left.form_actions, *right.form_actions]),
        required_fields=_ordered_unique([*left.required_fields, *right.required_fields]),
        form_field_names=_ordered_unique([*left.form_field_names, *right.form_field_names]),
        contact_form_profile=_preferred_contact_form_profile(left.contact_form_profile, right.contact_form_profile),
        page_text_hint=(left.page_text_hint or right.page_text_hint),
        llm_mock_used=left.llm_mock_used or right.llm_mock_used,
        llm_mock_reason=left.llm_mock_reason or right.llm_mock_reason,
    )


def _signals_have_supported_contact_form(signals: ContactSignals) -> bool:
    return bool(signals.has_form and signals.contact_form_profile == "supported_inquiry")


def _preferred_contact_form_profile(left: str, right: str) -> str:
    priority = {
        "supported_inquiry": 0,
        "phone_required": 1,
        "reservation_only": 2,
        "commerce": 3,
        "recruiting": 4,
        "newsletter": 5,
        "hidden_only": 6,
        "unknown": 7,
        "": 8,
    }
    return min((str(left or ""), str(right or "")), key=lambda value: priority.get(value, 9)) or "unknown"


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
                "Contact URL": result.get("contact_url", ""),
                "Website": result.get("website", ""),
                "Source": result.get("source", ""),
                "Source URL": result.get("source_url", ""),
                "Has Contact Form": "true" if result.get("has_contact_form") else "false",
            })


def default_places_api_key() -> str:
    return os.environ.get("GOOGLE_PLACES_API_KEY", "")
