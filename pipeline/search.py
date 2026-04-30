from __future__ import annotations

import re
import html as html_lib
import os
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .business_name import business_name_is_suspicious, business_names_match, extract_business_name_candidates, resolve_business_name
from .contact_crawler import extract_contact_signals, is_usable_business_email
from .contact_policy import normalise_contact_actionability
from .constants import DEEP_EMAIL_DISCOVERY_ENABLED
from .utils import utc_now, write_json, ensure_dir
from .qualification import qualify_candidate


# ---------------------------------------------------------------------------
# Cross-job dedup: prevents parallel search jobs from processing the same
# candidate twice.
# ---------------------------------------------------------------------------
_in_flight_keys: set[str] = set()
_in_flight_lock = threading.Lock()


def _try_mark_in_flight(key: str) -> bool:
    with _in_flight_lock:
        if key in _in_flight_keys:
            return False
        _in_flight_keys.add(key)
        return True


def _clear_in_flight(key: str) -> None:
    with _in_flight_lock:
        _in_flight_keys.discard(key)
from .evidence import _count_japanese_chars, has_chain_or_franchise_infrastructure


def _fetch_page(url: str, timeout_seconds: int = 10) -> str:
    """Fetch a URL and return its HTML."""
    request = urllib.request.Request(url, headers={"User-Agent": "webrefurb-menu/1.0"})
    with urllib.request.urlopen(request, timeout=max(3, min(timeout_seconds, 12))) as response:
        return response.read(700_000).decode("utf-8", errors="replace")


_EMAIL_RE = re.compile(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
_CONTACT_LINK_RE = re.compile(r'''(?is)<a[^>]+href=["']([^"']+)["'][^>]*>''')
_CONTACT_PATH_TOKENS = (
    "contact",
    "inquiry",
    "mail",
    "toiawase",
    "%E5%95%8F%E3%81%84%E5%90%88%E3%82%8F%E3%81%9B",  # 問い合わせ
)
_IGNORED_EMAIL_PREFIXES = ("noreply@", "no-reply@", "donotreply@", "do-not-reply@")


def _extract_contact_email(html: str) -> str:
    """Return the first usable business email from a page."""
    decoded = urllib.parse.unquote(html or "")
    for match in _EMAIL_RE.finditer(decoded):
        email = match.group(0).strip().lower()
        if email.startswith(_IGNORED_EMAIL_PREFIXES):
            continue
        if not is_usable_business_email(email):
            continue
        return email
    return ""


def _contact_candidate_urls(base_url: str, html: str, *, limit: int = 3) -> list[str]:
    """Find likely same-site contact pages from anchor hrefs."""
    base_parts = urllib.parse.urlparse(base_url)
    base_host = base_parts.netloc.lower().removeprefix("www.")
    urls: list[str] = []
    seen: set[str] = set()

    for href in _CONTACT_LINK_RE.findall(html or ""):
        href = href.strip()
        if not href or href.startswith(("#", "tel:", "javascript:")):
            continue
        absolute = urllib.parse.urljoin(base_url, href)
        parsed = urllib.parse.urlparse(absolute)
        host = parsed.netloc.lower().removeprefix("www.")
        if host and base_host and host != base_host:
            continue
        haystack = urllib.parse.quote(parsed.path.lower(), safe="/%") + " " + parsed.query.lower()
        if not any(token in haystack for token in _CONTACT_PATH_TOKENS):
            continue
        cleaned = urllib.parse.urlunparse(parsed._replace(fragment=""))
        if cleaned in seen or cleaned == base_url:
            continue
        seen.add(cleaned)
        urls.append(cleaned)
        if len(urls) >= limit:
            break

    return urls


def find_contact_email(website: str, html: str, *, timeout_seconds: int = 8) -> str:
    """Find a business email on the main page or a likely contact page."""
    email = _extract_contact_email(html)
    if email:
        return email

    for url in _contact_candidate_urls(website, html):
        try:
            email = _extract_contact_email(_fetch_page(url, timeout_seconds=timeout_seconds))
        except Exception:
            continue
        if email:
            return email

    return ""


def _append_contact_route(
    contacts: list[dict[str, Any]],
    seen: set[tuple[str, str]],
    *,
    contact_type: str,
    value: str,
    label: str = "",
    href: str = "",
    source: str = "",
    source_url: str = "",
    confidence: str = "medium",
    discovered_at: str = "",
    status: str = "",
    actionable: bool = True,
    metadata: dict[str, Any] | None = None,
) -> None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return
    if contact_type == "email":
        normalized = cleaned.lower()
    elif contact_type == "phone":
        normalized = re.sub(r"\D", "", cleaned)
    else:
        normalized = cleaned.lower()
    if not normalized:
        return
    key = (contact_type, normalized)
    if key in seen:
        return
    seen.add(key)
    contact = {
        "type": contact_type,
        "value": cleaned,
        "label": label or cleaned,
        "href": href.strip(),
        "source": source,
        "source_url": source_url,
        "confidence": confidence if confidence in {"high", "medium", "low"} else "medium",
        "discovered_at": str(discovered_at or "").strip(),
        "status": str(status or "").strip() or ("discovered" if actionable else "reference_only"),
        "actionable": actionable,
    }
    for key, value in (metadata or {}).items():
        if value not in (None, "", []):
            contact[key] = value
    contacts.append(normalise_contact_actionability(contact))


def discover_contact_routes(
    website: str,
    html: str,
    *,
    phone: str = "",
    address: str = "",
    map_url: str = "",
    timeout_seconds: int = 8,
) -> list[dict[str, Any]]:
    contacts: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    discovered_at = utc_now()

    _append_contact_route(
        contacts,
        seen,
        contact_type="website",
        value=website,
        label="Official website",
        href=website,
        source="homepage",
        source_url=website,
        confidence="high",
        discovered_at=discovered_at,
        actionable=False,
    )
    if phone:
        digits = re.sub(r"\D", "", phone)
        _append_contact_route(
            contacts,
            seen,
            contact_type="phone",
            value=phone,
            href=f"tel:{digits}" if digits else "",
            source="maps_listing",
            source_url=map_url or website,
            confidence="high",
            discovered_at=discovered_at,
            actionable=False,
        )
    if address:
        _append_contact_route(
            contacts,
            seen,
            contact_type="walk_in",
            value=address,
            label="Walk-in route",
            source="maps_listing",
            source_url=map_url or website,
            confidence="high",
            discovered_at=discovered_at,
            actionable=False,
        )
    if map_url:
        _append_contact_route(
            contacts,
            seen,
            contact_type="map_url",
            value=map_url,
            label="Map listing",
            href=map_url,
            source="maps_listing",
            source_url=map_url,
            confidence="high",
            discovered_at=discovered_at,
            actionable=False,
        )

    pages: list[tuple[str, str, str]] = [("homepage", website, html)]
    for url in _contact_candidate_urls(website, html):
        try:
            pages.append(("contact_page", url, _fetch_page(url, timeout_seconds=timeout_seconds)))
        except Exception:
            continue

    for source, source_url, page_html in pages:
        signals = extract_contact_signals(page_html)
        for email in signals.emails:
            _append_contact_route(
                contacts,
                seen,
                contact_type="email",
                value=email,
                href=f"mailto:{email}",
                source=source,
                source_url=source_url,
                confidence="high",
                discovered_at=discovered_at,
                actionable=True,
            )
        if signals.has_form:
            _append_contact_route(
                contacts,
                seen,
                contact_type="contact_form",
                value=source_url,
                label="Contact form",
                href=source_url,
                source=source,
                source_url=source_url,
                confidence="medium",
                discovered_at=discovered_at,
                actionable=True,
                metadata={
                    "form_actions": signals.form_actions,
                    "required_fields": signals.required_fields,
                },
            )

    priority = {
        "email": 0,
        "contact_form": 1,
        "walk_in": 2,
        "phone": 3,
        "map_url": 6,
        "website": 7,
    }
    contacts.sort(key=lambda contact: (priority.get(contact.get("type", ""), 99), str(contact.get("label") or "").lower()))
    return contacts


def _merge_contact_routes(
    existing: list[dict[str, Any]],
    additions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for contact in [*existing, *additions]:
        contact_type = str(contact.get("type") or "").strip().lower()
        value = str(contact.get("value") or "").strip()
        if contact_type == "email":
            normalized = value.lower()
        elif contact_type == "phone":
            normalized = re.sub(r"\D", "", value)
        else:
            normalized = value.lower()
        if not contact_type or not normalized:
            continue
        key = (contact_type, normalized)
        if key in seen:
            continue
        seen.add(key)
        merged.append(normalise_contact_actionability(contact))
    return merged


def run_search(
    *,
    query: str,
    api_key: str,
    gl: str = "jp",
    timeout_seconds: int = 10,
    provider: str | None = None,
) -> list[dict[str, Any]]:
    """Run a provider-backed Maps-like search and return raw places."""
    from .search_provider import run_maps_search

    data = run_maps_search(
        query=query,
        api_key=api_key,
        gl=gl,
        timeout_seconds=timeout_seconds,
        provider=provider,
    )
    return data.get("places") or []


def run_web_search(
    *,
    query: str,
    api_key: str,
    gl: str = "jp",
    timeout_seconds: int = 10,
    provider: str | None = None,
) -> dict[str, Any]:
    from .search_provider import run_organic_search

    return run_organic_search(
        query=query,
        api_key=api_key,
        gl=gl,
        timeout_seconds=timeout_seconds,
        provider=provider,
    )


def _address_search_token(address: str) -> str:
    first_part = str(address or "").split(",")[0].strip()
    return first_part or str(address or "").strip()


def _normalize_domain(url: str) -> str:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    return (parsed.netloc.lower().removeprefix("www.") or "")


def _find_tabelog_candidate_url(
    *,
    business_name: str,
    address: str,
    api_key: str,
    timeout_seconds: int = 10,
    search_provider: str | None = None,
) -> str:
    query_parts = [f"site:tabelog.com {business_name}"]
    address_token = _address_search_token(address)
    if address_token:
        query_parts.append(address_token)
    query = " ".join(part for part in query_parts if part).strip()
    try:
        kwargs = {"query": query, "api_key": api_key, "timeout_seconds": timeout_seconds}
        if search_provider is not None:
            kwargs["provider"] = search_provider
        data = run_web_search(**kwargs)
    except Exception:
        return ""

    for result in data.get("organic") or []:
        link = str(result.get("link") or "").strip()
        if "tabelog.com" in link:
            return link
    return ""


def _find_ramendb_candidate_url(
    *,
    business_name: str,
    address: str,
    api_key: str,
    timeout_seconds: int = 10,
    search_provider: str | None = None,
) -> str:
    """Find a RamenDB (ramendb.supleks.jp) listing for the business."""
    query_parts = [f"site:ramendb.supleks.jp {business_name}"]
    address_token = _address_search_token(address)
    if address_token:
        query_parts.append(address_token)
    query = " ".join(part for part in query_parts if part).strip()
    try:
        kwargs = {"query": query, "api_key": api_key, "timeout_seconds": timeout_seconds}
        if search_provider is not None:
            kwargs["provider"] = search_provider
        data = run_web_search(**kwargs)
    except Exception:
        return ""

    for result in data.get("organic") or []:
        link = str(result.get("link") or "").strip()
        if "ramendb.supleks.jp" in link:
            return link
    return ""


def _google_confidence_override(place: dict[str, Any]) -> bool:
    """Accept a place on Google Maps signals alone when no second source agrees.

    Requires strong evidence: high rating, many reviews, phone, place ID, and a
    working website.  This prevents tiny or dubious listings from slipping through
    while rescuing legitimate shops that simply lack a Tabelog/official-site match.
    """
    try:
        rating = float(place.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    try:
        reviews = int(place.get("ratingCount") or place.get("reviews") or 0)
    except (TypeError, ValueError):
        reviews = 0
    webserper_maps_batch = str(place.get("searchProvider") or "") == "webserper_google_maps_batch"
    has_review_confidence = reviews >= 50 or (webserper_maps_batch and place.get("address"))
    return bool(
        place.get("placeId")
        and rating >= 4.0
        and has_review_confidence
        and place.get("phoneNumber")
        and place.get("website")
    )


def _has_verified_name_conflict(*, source_candidate: str, official_name: str) -> bool:
    """Return True when two usable first-party names disagree.

    Google confidence is useful for rescuing sparse independent shops, but it
    should not override a concrete mismatch between the Maps title and the
    restaurant's own page title/H1.
    """
    if not source_candidate or not official_name:
        return False
    if business_name_is_suspicious(source_candidate) or business_name_is_suspicious(official_name):
        return False
    return not business_names_match(source_candidate, official_name)


def _normalise_search_job(query: str, category: str, search_job: dict[str, Any] | None) -> dict[str, str]:
    job = search_job or {}
    return {
        "job_id": str(job.get("job_id") or "operator_custom_query"),
        "query": str(job.get("query") or query),
        "category": str(job.get("category") or category),
        "purpose": str(job.get("purpose") or "operator_custom_search"),
        "expected_friction": str(job.get("expected_friction") or "operator_supplied"),
    }


def _matched_friction_evidence(decision: dict[str, Any], search_job: dict[str, str]) -> list[str]:
    matches: list[str] = []
    classes = set(decision.get("evidence_classes") or [])
    reason = str(decision.get("reason") or decision.get("rejection_reason") or "")
    job_id = str(search_job.get("job_id") or "")
    expected = str(search_job.get("expected_friction") or "")

    if decision.get("machine_evidence_found") or decision.get("ticket_machine_state") == "present":
        matches.append("ticket_machine_evidence")
    if decision.get("ticket_machine_state") == "absent" or "ticket_machine_absence_evidence" in set(decision.get("evidence_classes") or []):
        matches.append("ticket_machine_absence_evidence")
    if decision.get("menu_evidence_found") or classes.intersection({
        "official_html_menu",
        "official_pdf_menu",
        "official_menu_image",
        "review_menu_photo",
        "drink_menu_photo",
        "printed_menu_photo",
        "wall_menu_photo",
        "handwritten_menu_photo",
    }):
        matches.append("menu_evidence")
    if decision.get("course_or_drink_plan_evidence_found") or classes.intersection({"nomihodai_menu", "course_menu", "drink_menu_photo"}):
        matches.append("drink_or_course_friction")
    if reason in {"already_has_good_english_menu", "already_has_multilingual_ordering_solution"}:
        matches.append("already_solved_english_solution")
    if decision.get("recommended_primary_package") == "package_1_remote_30k" and decision.get("primary_category_v1") == "ramen" and not decision.get("machine_evidence_found"):
        matches.append("simple_menu_package_fit")
    if job_id.startswith("ramen_ramendb"):
        matches.append("ramendb_lookup_source")
    if "tabelog" in job_id or "hotpepper" in job_id:
        matches.append("directory_menu_lookup_source")
    if expected and expected not in {"operator_supplied", "english_menu_check", "multilingual_qr_check", "mobile_order_check", "english_ticket_machine_check"}:
        matches.append(f"search_job:{expected}")

    return list(dict.fromkeys(matches))


def _search_job_marks_existing_solution(search_job: dict[str, str]) -> bool:
    haystack = " ".join([
        str(search_job.get("job_id") or ""),
        str(search_job.get("purpose") or ""),
        str(search_job.get("expected_friction") or ""),
    ])
    return any(token in haystack for token in (
        "english_menu_check",
        "english_solution_check",
        "english_ticket_machine_check",
        "mobile_order_check",
        "mobile_order_solution_check",
        "multilingual_qr_check",
        "multilingual_solution_check",
        "ticket_machine_solution_check",
    ))


def _add_search_context(decision: dict[str, Any], *, query: str, search_job: dict[str, str]) -> dict[str, Any]:
    decision.setdefault("source_query", query)
    decision.setdefault("source_search_job", search_job)
    decision.setdefault("matched_friction_evidence", _matched_friction_evidence(decision, search_job))
    return decision


def verify_business_name(
    *,
    source_name: str,
    website: str,
    html: str,
    address: str,
    serper_api_key: str,
    timeout_seconds: int = 8,
    category: str = "",
    search_provider: str | None = None,
) -> dict[str, Any]:
    resolved_name, resolved_source = resolve_business_name(source_name=source_name, html=html)
    source_candidate = str(source_name or "").strip()
    official_candidates = [candidate for candidate in extract_business_name_candidates(html) if not business_name_is_suspicious(candidate)]
    official_name = official_candidates[0] if official_candidates else ""
    name_conflict = _has_verified_name_conflict(
        source_candidate=source_candidate,
        official_name=official_name,
    )
    verified_by: list[str] = []
    use_external_name_lookup = not _skip_local_external_name_lookup(search_provider)

    tabelog_url = _find_tabelog_candidate_url(
        business_name=resolved_name or source_candidate,
        address=address,
        api_key=serper_api_key,
        timeout_seconds=timeout_seconds,
        search_provider=search_provider,
    ) if (use_external_name_lookup and (resolved_name or source_candidate)) else ""
    tabelog_name = ""
    if tabelog_url:
        try:
            tabelog_html = _fetch_page(tabelog_url, timeout_seconds=timeout_seconds)
            tabelog_candidates = [
                candidate for candidate in extract_business_name_candidates(tabelog_html)
                if not business_name_is_suspicious(candidate)
            ]
            tabelog_name = tabelog_candidates[0] if tabelog_candidates else ""
        except Exception:
            tabelog_name = ""

    # RamenDB lookup (ramen category only)
    ramendb_url = ""
    ramendb_name = ""
    if use_external_name_lookup and category == "ramen" and (resolved_name or source_candidate):
        ramendb_url = _find_ramendb_candidate_url(
            business_name=resolved_name or source_candidate,
            address=address,
            api_key=serper_api_key,
            timeout_seconds=timeout_seconds,
            search_provider=search_provider,
        )
        if ramendb_url:
            try:
                ramendb_html = _fetch_page(ramendb_url, timeout_seconds=timeout_seconds)
                ramendb_candidates = [
                    candidate for candidate in extract_business_name_candidates(ramendb_html)
                    if not business_name_is_suspicious(candidate)
                ]
                ramendb_name = ramendb_candidates[0] if ramendb_candidates else ""
            except Exception:
                ramendb_name = ""

    if tabelog_name:
        if source_candidate and not business_name_is_suspicious(source_candidate) and business_names_match(source_candidate, tabelog_name):
            verified_by = ["tabelog", "google"]
            resolved_name = tabelog_name
            resolved_source = "tabelog"
        elif official_name and business_names_match(official_name, tabelog_name):
            verified_by = ["tabelog", "official_site"]
            resolved_name = tabelog_name
            resolved_source = "tabelog"
    elif ramendb_name:
        if source_candidate and not business_name_is_suspicious(source_candidate) and business_names_match(source_candidate, ramendb_name):
            verified_by = ["ramendb", "google"]
            resolved_name = ramendb_name
            resolved_source = "ramendb"
        elif official_name and business_names_match(official_name, ramendb_name):
            verified_by = ["ramendb", "official_site"]
            resolved_name = ramendb_name
            resolved_source = "ramendb"
    elif source_candidate and not business_name_is_suspicious(source_candidate) and official_name and business_names_match(source_candidate, official_name):
        verified_by = ["google", "official_site"]
        resolved_name = official_name

    if not verified_by and official_name and resolved_source == "page_html":
        resolved_name = official_name

    return {
        "business_name": resolved_name,
        "business_name_source": resolved_source,
        "verified_by": verified_by,
        "tabelog_url": tabelog_url,
        "tabelog_name": tabelog_name,
        "ramendb_url": ramendb_url,
        "ramendb_name": ramendb_name,
        "official_name": official_name,
        "source_candidate": source_candidate,
        "name_conflict": name_conflict,
    }


def _skip_local_external_name_lookup(search_provider: str | None) -> bool:
    provider = str(search_provider or "").strip().lower()
    if provider not in {"webserper", "web-serper", "web_serper", "local", "duckduckgo", "ddg", "webrefurb"}:
        return False
    return os.environ.get("WEBREFURB_LOCAL_ENABLE_ORGANIC_VERIFY", "").strip().lower() not in {"1", "true", "yes", "on"}


def _targeted_evidence_queries(
    *,
    business_name: str,
    category: str,
    search_job: dict[str, str],
) -> list[str]:
    name = str(business_name or "").strip()
    if not name:
        return []
    category_value = str(category or "").strip().lower()
    expected = str(search_job.get("expected_friction") or "").lower()
    purpose = str(search_job.get("purpose") or "").lower()
    source_query = str(search_job.get("query") or "").lower()

    queries: list[str] = []
    wants_ticket_lookup = (
        category_value == "ramen"
        and (
            "ticket" in expected
            or "machine" in expected
            or "ticket" in purpose
            or "machine" in purpose
            or "券売機" in source_query
            or "食券" in source_query
        )
    )
    if category_value == "ramen":
        if wants_ticket_lookup:
            queries.extend([
                f'"{name}" 券売機 食券',
                f'"{name}" メニュー ラーメン',
                f'"{name}" 英語メニュー 多言語 QR',
            ])
        else:
            queries.extend([
                f'"{name}" メニュー ラーメン',
                f'"{name}" 券売機 食券',
                f'"{name}" 英語メニュー 多言語 QR',
            ])

    if category_value == "izakaya":
        queries.extend([
            f'"{name}" 飲み放題 コース',
            f'"{name}" お品書き メニュー',
            f'"{name}" 英語メニュー 多言語 QRオーダー',
        ])

    queries.append(f'"{name}" チェーン 展開 フランチャイズ')
    return list(dict.fromkeys(queries))[:4]


def _result_text(result: dict[str, Any]) -> str:
    return " ".join(str(result.get(key) or "") for key in ("title", "snippet", "link"))


def _blocked_evidence_link(link: str) -> bool:
    parsed = urllib.parse.urlparse(str(link or ""))
    host = parsed.netloc.lower().removeprefix("www.")
    return any(domain in host for domain in (
        "instagram.com", "facebook.com", "twitter.com", "x.com",
        "youtube.com", "tiktok.com", "pinterest.com",
    ))


def _business_result_matches_name(text: str, business_name: str) -> bool:
    from .business_name import business_names_match
    lowered = text.lower()
    name_parts = [p for p in re.split(r"[\s\u3000|－\-\u2010\u2011\u2012\u2013\u2014\u2015]+", business_name) if p]
    if any(part.lower() in lowered for part in name_parts):
        return True
    return False


def _result_has_qualification_signal(text: str, category: str) -> bool:
    from .constants import (
        TICKET_MACHINE_TERMS, RAMEN_MENU_TERMS, IZAKAYA_MENU_TERMS,
        TICKET_MACHINE_ABSENCE_TERMS, SOLVED_ENGLISH_SUPPORT_TERMS,
    )
    lowered = text.lower()
    if any(term.lower() in lowered for term in SOLVED_ENGLISH_SUPPORT_TERMS):
        return True
    if any(term.lower() in lowered for term in TICKET_MACHINE_ABSENCE_TERMS):
        return True
    if category == "ramen":
        if any(term in lowered for term in TICKET_MACHINE_TERMS):
            return True
        if any(term.lower() in lowered for term in RAMEN_MENU_TERMS):
            return True
    if category == "izakaya" and any(term.lower() in lowered for term in IZAKAYA_MENU_TERMS):
        return True
    if has_chain_or_franchise_infrastructure(text):
        return True
    return False


def _collect_targeted_evidence_pages(
    *,
    business_name: str,
    category: str,
    search_job: dict[str, str],
    serper_api_key: str,
    timeout_seconds: int = 8,
    search_provider: str | None = None,
) -> list[dict[str, str]]:
    pages: list[dict[str, str]] = []
    seen_links: set[str] = set()
    for evidence_query in _targeted_evidence_queries(
        business_name=business_name,
        category=category,
        search_job=search_job,
    ):
        try:
            kwargs = {"query": evidence_query, "api_key": serper_api_key, "timeout_seconds": timeout_seconds}
            if search_provider is not None:
                kwargs["provider"] = search_provider
            data = run_web_search(**kwargs)
        except Exception:
            continue
        for result in data.get("organic") or []:
            link = str(result.get("link") or "").strip()
            text = _result_text(result)
            if not link or link in seen_links:
                continue
            if _blocked_evidence_link(link):
                continue
            if not _business_result_matches_name(text, business_name):
                continue
            if not _result_has_qualification_signal(text, category):
                continue
            seen_links.add(link)
            title = html_lib.escape(str(result.get("title") or "Search evidence"))
            snippet = html_lib.escape(str(result.get("snippet") or ""))
            pages.append({
                "url": link,
                "html": f"<html><body><h1>{title}</h1><p>{snippet}</p></body></html>",
            })
            if len(pages) >= 2:
                return pages
    return pages


def search_and_qualify(
    *,
    query: str,
    serper_api_key: str,
    category: str = "ramen",
    state_root: Path | None = None,
    max_candidates: int = 24,
    search_job: dict[str, Any] | None = None,
    search_provider: str | None = None,
) -> dict[str, Any]:
    """Search, fetch pages, qualify each candidate, persist leads."""
    if state_root is None:
        state_root = Path(__file__).resolve().parent.parent / "state"

    source_search_job = _normalise_search_job(query, category, search_job)
    search_kwargs = {"query": query, "api_key": serper_api_key}
    if search_provider is not None:
        search_kwargs["provider"] = search_provider
    raw_places = run_search(**search_kwargs)
    results: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    qualified_without_email = 0
    qualified_with_non_email_contact = 0
    qualified_without_supported_contact = 0

    for place in raw_places[:max_candidates]:
        website = str(place.get("website") or "").strip()
        source_name = str(place.get("title") or place.get("name") or "").strip()
        if not website or not source_name:
            continue

        # Extract coordinates from Maps-like provider responses.
        position = place.get("position") or {}
        place_lat = position.get("lat") if isinstance(position, dict) else None
        place_lng = position.get("lng") if isinstance(position, dict) else None
        if place_lat is None:
            place_lat = place.get("latitude")
        if place_lng is None:
            place_lng = place.get("longitude")

        # Skip if already tracked as a lead (any status)
        from .record import find_existing_lead
        existing = find_existing_lead(
            business_name=source_name,
            website=website,
            phone=str(place.get("phoneNumber", "")),
            place_id=str(place.get("placeId", "")),
            address=str(place.get("address", "")),
            state_root=state_root,
        )
        if existing:
            decisions.append({
                "business_name": source_name,
                "lead": False,
                "reason": "already_tracked",
                "existing_lead_id": existing.get("lead_id"),
                "existing_status": existing.get("outreach_status"),
            })
            continue

        # Cross-job dedup: skip if another parallel job is already processing
        dedup_key = str(place.get("placeId") or "") or _normalize_domain(website)
        if not _try_mark_in_flight(dedup_key):
            decisions.append({
                "business_name": source_name,
                "lead": False,
                "reason": "already_tracked",
            })
            continue

        try:
            try:
                website_html = _fetch_page(website)
                pages = [{"url": website, "html": website_html}]
                if place.get("localEvidenceHtml"):
                    pages.append({
                        "url": str(place.get("link") or place.get("mapUrl") or website),
                        "html": str(place.get("localEvidenceHtml") or ""),
                    })
            except Exception as exc:
                decisions.append({"business_name": source_name, "lead": False, "reason": "fetch_failed", "error": str(exc)})
                continue

            name_check = verify_business_name(
                source_name=source_name,
                website=website,
                html=website_html,
                address=str(place.get("address", "")),
                serper_api_key=serper_api_key,
                category=category,
                search_provider=search_provider,
            )
            business_name = str(name_check.get("business_name") or "")
            business_name_source = str(name_check.get("business_name_source") or "")
            verified_by = list(name_check.get("verified_by") or [])
            if business_name_is_suspicious(business_name):
                decisions.append({
                    "business_name": source_name,
                    "lead": False,
                    "reason": "invalid_business_name_detected",
                    "business_name_source": business_name_source,
                })
                continue
            if len(verified_by) < 2:
                # Allow through when Google Maps signals are strong enough on their own
                if _google_confidence_override(place) and not bool(name_check.get("name_conflict")):
                    verified_by = verified_by + ["google_confidence_override"]
                else:
                    decisions.append({
                        "business_name": business_name or source_name,
                        "lead": False,
                        "reason": "business_name_conflict" if name_check.get("name_conflict") else "business_name_unverified",
                        "business_name_source": business_name_source,
                        "business_name_verified_by": verified_by,
                        "official_name": name_check.get("official_name", ""),
                    })
                    continue

            pages.extend(_collect_targeted_evidence_pages(
                business_name=business_name,
                category=category,
                search_job=source_search_job,
                serper_api_key=serper_api_key,
                search_provider=search_provider,
            ))

            qualification = qualify_candidate(
                business_name=business_name,
                website=website,
                category=category,
                pages=pages,
                rating=place.get("rating"),
                reviews=place.get("ratingCount") or place.get("reviews"),
                address=place.get("address", ""),
                phone=place.get("phoneNumber", ""),
                place_id=place.get("placeId", ""),
                map_url=str(place.get("link") or place.get("mapUrl") or ""),
                latitude=place_lat,
                longitude=place_lng,
            )

            decision = qualification.to_dict()
            decision["business_name_source"] = business_name_source
            decision["business_name_verified_by"] = verified_by
            if qualification.lead and category in {"ramen", "izakaya"} and qualification.primary_category_v1 != category:
                decision["lead"] = False
                decision["reason"] = "search_category_mismatch"
                decision["requested_category"] = category
                decisions.append(decision)
                continue
            if qualification.lead and _search_job_marks_existing_solution(source_search_job):
                decision["lead"] = False
                decision["reason"] = "already_solved_solution_check"
                decision["rejection_reason"] = "already_solved_solution_check"
                decision["english_availability"] = "clear_usable"
                decision["english_menu_state"] = "usable_complete"
                decisions.append(decision)
                continue

            if qualification.lead:
                contact_routes = discover_contact_routes(
                    website,
                    website_html,
                    phone=str(place.get("phoneNumber", "")),
                    address=str(place.get("address", "")),
                    map_url=str(place.get("link") or place.get("mapUrl") or ""),
                )
                actionable_routes = [route for route in contact_routes if route.get("actionable")]
                email_contact = next((route for route in contact_routes if route.get("type") == "email"), None)

                if not actionable_routes:
                    if DEEP_EMAIL_DISCOVERY_ENABLED:
                        from .email_discovery.bridge import enrich_lead_inline

                        deeper_routes = enrich_lead_inline(
                            business_name=business_name,
                            website=website,
                            html=website_html,
                            address=str(place.get("address", "")),
                            phone=str(place.get("phoneNumber", "")),
                            genre=qualification.primary_category_v1 or category,
                        )
                        if deeper_routes:
                            contact_routes = _merge_contact_routes(contact_routes, deeper_routes)
                            actionable_routes = [route for route in contact_routes if route.get("actionable")]
                            email_contact = next((route for route in contact_routes if route.get("type") == "email"), None)

                decision["contact_route_types"] = [str(route.get("type") or "") for route in contact_routes]
                decision["primary_contact_type"] = actionable_routes[0]["type"] if actionable_routes else ""

                if not email_contact:
                    qualified_without_email += 1
                if not actionable_routes:
                    qualified_without_supported_contact += 1
                    decision["lead"] = False
                    decision["reason"] = "no_supported_contact_route_found"
                    decisions.append(decision)
                    continue
                if not email_contact:
                    qualified_with_non_email_contact += 1

                from .preview import build_preview_menu, build_preview_html
                from .pitch import build_pitch
                from .record import create_lead_record, persist_lead_record

                preview_menu = build_preview_menu(
                    assessment=qualification,
                    snippets=qualification.evidence_snippets,
                    business_name=business_name,
                )
                preview_html = build_preview_html(
                    preview_menu=preview_menu,
                    ticket_machine_hint=None,
                    business_name=business_name,
                )
                pitch = build_pitch(
                    business_name=business_name,
                    category=qualification.primary_category_v1,
                    preview_menu=preview_menu,
                    ticket_machine_hint=None,
                    recommended_package=qualification.recommended_primary_package,
                )
                record = create_lead_record(
                    qualification=qualification,
                    preview_html=preview_html,
                    pitch_draft=pitch,
                    contacts=contact_routes,
                    source_query=query,
                    source_search_job=source_search_job,
                    matched_friction_evidence=_matched_friction_evidence(decision, source_search_job),
                    state_root=state_root,
                )
                record["business_name_source"] = business_name_source
                record["business_name_verified_by"] = verified_by
                if name_check.get("tabelog_url"):
                    record["business_name_tabelog_url"] = name_check["tabelog_url"]
                if name_check.get("ramendb_url"):
                    record["business_name_ramendb_url"] = name_check["ramendb_url"]
                persist_lead_record(record, state_root=state_root)
                results.append(record)
                decision["email_found"] = bool(email_contact)
                decision["lead_id"] = record["lead_id"]

            decisions.append(decision)
        finally:
            _clear_in_flight(dedup_key)

    run_id = f"wrm-search-{utc_now().replace(':', '').replace('-', '').replace('+00:00', 'z').lower()}"
    decisions = [
        _add_search_context(decision, query=query, search_job=source_search_job)
        for decision in decisions
    ]

    return {
        "run_id": run_id,
        "query": query,
        "search_provider": search_provider or "",
        "search_job": source_search_job,
        "total_candidates": len(raw_places[:max_candidates]),
        "leads": len(results),
        "qualified_without_email": qualified_without_email,
        "qualified_with_non_email_contact": qualified_with_non_email_contact,
        "qualified_without_supported_contact": qualified_without_supported_contact,
        "decisions": decisions,
    }
