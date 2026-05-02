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
from .evidence import _count_japanese_chars, has_chain_or_franchise_infrastructure, is_chain_business
from .html_parser import extract_page_payload
from .japan_restaurant_intel import (
    collect_restaurant_intel,
    coverage_with_contact,
    is_official_candidate_url,
)
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


def _fetch_page(url: str, timeout_seconds: int = 10) -> str:
    """Fetch a URL and return its HTML using Scrapling (TLS fingerprint)."""
    from scrapling import Fetcher
    try:
        resp = Fetcher().get(url, timeout=max(3, min(timeout_seconds, 12)))
        if resp.status == 200:
            return resp.html_content or ""
    except Exception:
        pass
    # Fallback to urllib for non-200 or Scrapling errors
    request = urllib.request.Request(url, headers={"User-Agent": "webrefurb-menu/1.0"})
    with urllib.request.urlopen(request, timeout=max(3, min(timeout_seconds, 12))) as response:
        return response.read(700_000).decode("utf-8", errors="replace")


_EMAIL_RE = re.compile(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
_CONTACT_LINK_RE = re.compile(r'''(?is)<a[^>]+href=["']([^"']+)["'][^>]*>''')
_CONTACT_PATH_TOKENS = (
    "contact",
    "inquiry",
    "mail",
    "form",
    "toiawase",
    "otoiawase",
    "%E5%95%8F%E3%81%84%E5%90%88%E3%82%8F%E3%81%9B",  # 問い合わせ
)
_BLOCKED_CONTACT_PATH_TOKENS = (
    "reserve",
    "reservation",
    "booking",
    "book-a-table",
    "yoyaku",
    "%E4%BA%88%E7%B4%84",  # 予約
)
_DETERMINISTIC_CONTACT_PATHS = (
    "/contact",
    "/contact/",
    "/inquiry",
    "/inquiry/",
    "/otoiawase",
    "/otoiawase/",
    "/toiawase",
    "/toiawase/",
    "/mail",
    "/mail/",
    "/form",
    "/form/",
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

    def add_candidate(candidate_url: str) -> None:
        if len(urls) >= limit:
            return
        parsed = urllib.parse.urlparse(candidate_url)
        host = parsed.netloc.lower().removeprefix("www.")
        if host and base_host and host != base_host:
            return
        haystack = urllib.parse.quote(parsed.path.lower(), safe="/%") + " " + parsed.query.lower()
        if any(token in haystack for token in _BLOCKED_CONTACT_PATH_TOKENS):
            return
        if not any(token in haystack for token in _CONTACT_PATH_TOKENS):
            return
        cleaned = urllib.parse.urlunparse(parsed._replace(fragment=""))
        if cleaned in seen or cleaned == base_url:
            return
        seen.add(cleaned)
        urls.append(cleaned)

    for href in _CONTACT_LINK_RE.findall(html or ""):
        href = href.strip()
        if not href or href.startswith(("#", "tel:", "javascript:")):
            continue
        absolute = urllib.parse.urljoin(base_url, href)
        add_candidate(absolute)
        if len(urls) >= limit:
            break

    if len(urls) < limit and base_parts.scheme and base_parts.netloc:
        origin = urllib.parse.urlunparse((base_parts.scheme, base_parts.netloc, "", "", "", ""))
        for path in _DETERMINISTIC_CONTACT_PATHS:
            add_candidate(urllib.parse.urljoin(origin, path))
            if len(urls) >= limit:
                break

    if len(urls) < limit and base_parts.path and base_parts.path not in {"", "/"}:
        base_dir = base_url.rstrip("/") + "/"
        for path in ("contact", "inquiry", "otoiawase", "toiawase", "mail", "form"):
            add_candidate(urllib.parse.urljoin(base_dir, path))
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
        if signals.has_form and signals.contact_form_profile == "supported_inquiry":
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
                    "has_form": True,
                    "form_actions": signals.form_actions,
                    "required_fields": signals.required_fields,
                    "form_field_names": signals.form_field_names,
                    "contact_form_profile": signals.contact_form_profile,
                    "page_text_hint": signals.page_text_hint,
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


def _merge_verified_sources(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for source in group or []:
            cleaned = str(source or "").strip()
            key = cleaned.lower()
            if cleaned and key not in seen:
                seen.add(key)
                merged.append(cleaned)
    return merged


def _discover_contacts_from_official_candidates(
    *,
    candidates: list[str],
    primary_website: str,
    phone: str,
    address: str,
    map_url: str,
    timeout_seconds: int = 8,
) -> list[dict[str, Any]]:
    contacts: list[dict[str, Any]] = []
    primary_host = _normalize_domain(primary_website)
    seen_hosts = {primary_host} if primary_host else set()
    for candidate in candidates[:4]:
        if not is_official_candidate_url(candidate):
            continue
        host = _normalize_domain(candidate)
        if not host or host in seen_hosts:
            continue
        seen_hosts.add(host)
        try:
            html = _fetch_page(candidate, timeout_seconds=timeout_seconds)
        except Exception:
            continue
        contacts = _merge_contact_routes(
            contacts,
            discover_contact_routes(
                candidate,
                html,
                phone=phone,
                address=address,
                map_url=map_url,
                timeout_seconds=timeout_seconds,
            ),
        )
    return contacts


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
    normalised = {
        "job_id": str(job.get("job_id") or "operator_custom_query"),
        "query": str(job.get("query") or query),
        "category": str(job.get("category") or category),
        "purpose": str(job.get("purpose") or "operator_custom_search"),
        "expected_friction": str(job.get("expected_friction") or "operator_supplied"),
    }
    for key in ("city", "stratum", "job_mode", "engine_policy"):
        if job.get(key):
            normalised[key] = str(job.get(key))
    return normalised


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
    if any(source in job_id for source in ("tabelog", "hotpepper", "gurunavi", "gnavi", "retty", "hitosara", "paypay")):
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
    decision.setdefault("inventory_review_status", _inventory_review_status(decision))
    return decision


def _candidate_window(candidates: list[Any], max_candidates: int) -> list[Any]:
    if max_candidates and max_candidates > 0:
        return candidates[:max_candidates]
    return candidates


def _inventory_review_status(decision: dict[str, Any]) -> str:
    reason = str(decision.get("reason") or decision.get("rejection_reason") or "").strip()
    if decision.get("lead") is True:
        return "qualified_with_supported_contact"
    if reason in {
        "already_tracked",
        "no_supported_contact_route_found",
        "business_name_unverified",
        "business_name_conflict",
        "fetch_failed",
        "no_official_site_found",
    }:
        return "review_blocked"
    if reason in {
        "already_has_good_english_menu",
        "already_has_multilingual_ordering_solution",
        "already_solved_solution_check",
    }:
        return "solved_english_or_ordering"
    if reason in {
        "chain_business",
        "chain_or_franchise_infrastructure",
        "excluded_business_type_v1",
        "non_ramen_izakaya_v1",
        "search_category_mismatch",
        "invalid_business_name_detected",
    }:
        return "hard_invalid"
    if reason in {
        "no_menu_or_product_evidence",
        "insufficient_category_evidence",
        "directory_or_social_only",
        "negative_evidence_score",
    }:
        return "weak_or_incomplete_evidence"
    return "needs_review"


def _source_strength_label(record: dict[str, Any]) -> str:
    signals = record.get("coverage_signals") if isinstance(record.get("coverage_signals"), dict) else {}
    email_source_url = str(record.get("email_source_url") or "").strip()
    email_source = str(record.get("email_source") or "").strip()
    if signals.get("has_official_site") and email_source_url and urllib.parse.urlparse(email_source_url).netloc:
        return "official_site"
    if email_source in {"codex_organic_search", "search_result", "website"}:
        return "restaurant_owned_or_search_result"
    if signals.get("portal_only"):
        return "directory"
    if signals.get("has_official_site"):
        return "official_site"
    return "weak_source"


def _mark_inventory_review_blocked(
    record: dict[str, Any],
    *,
    city: str = "",
    category: str = "",
    email_source_url: str = "",
    email_source: str = "",
) -> dict[str, Any]:
    """Keep no-send search inventory out of the launch-ready queue."""
    record["manual_review_required"] = True
    record["inventory_review_status"] = "review_blocked"
    record["inventory_review_reason"] = "search_inventory_requires_manual_review_before_outreach"
    record["candidate_inbox_status"] = "review_blocked"
    record["pitch_ready"] = False
    record["outreach_status"] = "needs_review"
    record["review_status"] = "pending"
    if city:
        record["city"] = city
    if category:
        record["category"] = category
    if email_source_url:
        record["email_source_url"] = email_source_url
    if email_source:
        record["email_source"] = email_source
    record["source_url"] = str(record.get("source_url") or record.get("website") or "")
    record["source_strength"] = _source_strength_label(record)
    history = record.setdefault("status_history", [])
    if isinstance(history, list) and not any(item.get("status") == "needs_review" for item in history if isinstance(item, dict)):
        history.append({"status": "needs_review", "timestamp": utc_now()})
    return record


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

    candidate_places = _candidate_window(raw_places, max_candidates)
    for place in candidate_places:
        website = str(place.get("website") or "").strip()
        source_name = str(place.get("title") or place.get("name") or "").strip()
        if not source_name:
            continue
        place_address = str(place.get("address", ""))
        place_phone = str(place.get("phoneNumber", ""))
        place_map_url = str(place.get("link") or place.get("mapUrl") or "")

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
            phone=place_phone,
            place_id=str(place.get("placeId", "")),
            address=place_address,
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
        dedup_key = str(place.get("placeId") or "") or _normalize_domain(website) or f"{source_name}:{place_address}"
        if not _try_mark_in_flight(dedup_key):
            decisions.append({
                "business_name": source_name,
                "lead": False,
                "reason": "already_tracked",
            })
            continue

        try:
            intel = collect_restaurant_intel(
                business_name=source_name,
                address=place_address,
                phone=place_phone,
                category=category,
                place=place,
                initial_website=website,
                serper_api_key=serper_api_key,
                search_provider=search_provider,
                web_search=run_web_search,
                fetch_page=_fetch_page,
            )
            intel_dict = intel.to_dict()
            if (not website or not is_official_candidate_url(website)) and intel.primary_official_site:
                website = intel.primary_official_site

            if not website:
                decisions.append({
                    "business_name": source_name,
                    "lead": False,
                    "reason": "no_official_site_found",
                    "japan_intel": intel_dict,
                    "source_count": intel.source_count,
                    "coverage_signals": intel.coverage_signals,
                    "coverage_score": intel.coverage_score,
                })
                continue

            try:
                website_html = ""
                fetched_website = website
                fetch_errors: list[str] = []
                for candidate_website in dict.fromkeys([website, *intel.official_site_candidates]):
                    if not candidate_website:
                        continue
                    try:
                        website_html = _fetch_page(candidate_website)
                        fetched_website = candidate_website
                        break
                    except Exception as exc:
                        fetch_errors.append(f"{candidate_website}:{type(exc).__name__}")
                if not website_html:
                    raise RuntimeError("; ".join(fetch_errors) or "fetch_failed")
                website = fetched_website
                pages = [{"url": website, "html": website_html}]
                if place.get("localEvidenceHtml"):
                    pages.append({
                        "url": place_map_url or website,
                        "html": str(place.get("localEvidenceHtml") or ""),
                    })
            except Exception as exc:
                decisions.append({
                    "business_name": source_name,
                    "lead": False,
                    "reason": "fetch_failed",
                    "error": str(exc),
                    "japan_intel": intel_dict,
                    "source_count": intel.source_count,
                    "coverage_signals": intel.coverage_signals,
                    "coverage_score": intel.coverage_score,
                })
                continue

            name_check = verify_business_name(
                source_name=source_name,
                website=website,
                html=website_html,
                address=place_address,
                serper_api_key=serper_api_key,
                category=category,
                search_provider=search_provider,
            )
            business_name = str(name_check.get("business_name") or intel.canonical_name or "")
            business_name_source = str(name_check.get("business_name_source") or "")
            verified_by = _merge_verified_sources(list(name_check.get("verified_by") or []), intel.verified_by)
            if business_name_is_suspicious(business_name):
                decisions.append({
                    "business_name": source_name,
                    "lead": False,
                    "reason": "invalid_business_name_detected",
                    "business_name_source": business_name_source,
                    "japan_intel": intel_dict,
                    "source_count": intel.source_count,
                    "coverage_signals": intel.coverage_signals,
                    "coverage_score": intel.coverage_score,
                })
                continue
            if name_check.get("name_conflict"):
                decisions.append({
                    "business_name": business_name or source_name,
                    "lead": False,
                    "reason": "business_name_conflict",
                    "business_name_source": business_name_source,
                    "business_name_verified_by": verified_by,
                    "official_name": name_check.get("official_name", ""),
                    "japan_intel": intel_dict,
                    "source_count": intel.source_count,
                    "coverage_signals": intel.coverage_signals,
                    "coverage_score": intel.coverage_score,
                })
                continue
            if len(verified_by) < 2:
                # Allow through when Google Maps signals are strong enough on their own
                if _google_confidence_override(place) and not bool(name_check.get("name_conflict")):
                    verified_by = verified_by + ["google_confidence_override"]
                    name_review_status = "google_confidence_override"
                else:
                    verified_by = verified_by or ["single_source_search_result"]
                    name_review_status = "single_source_needs_review"
            else:
                name_review_status = "multi_source_verified"

            pages.extend(intel.evidence_pages)
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
                address=place_address,
                phone=place_phone,
                place_id=place.get("placeId", ""),
                map_url=place_map_url,
                latitude=place_lat,
                longitude=place_lng,
            )

            decision = qualification.to_dict()
            if qualification.rejection_reason:
                decision.setdefault("reason", qualification.rejection_reason)
            decision["business_name_source"] = business_name_source
            decision["business_name_verified_by"] = verified_by
            decision["business_name_review_status"] = name_review_status
            decision["japan_intel"] = intel_dict
            decision["source_count"] = intel.source_count
            decision["coverage_signals"] = intel.coverage_signals
            decision["coverage_score"] = intel.coverage_score
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
                    phone=place_phone,
                    address=place_address,
                    map_url=place_map_url,
                )
                contact_routes = _merge_contact_routes(
                    contact_routes,
                    _discover_contacts_from_official_candidates(
                        candidates=[
                            *intel.official_site_candidates,
                            *([intel.operator_company_url] if intel.operator_company_url else []),
                        ],
                        primary_website=website,
                        phone=place_phone,
                        address=place_address,
                        map_url=place_map_url,
                    ),
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
                            address=place_address,
                            phone=place_phone,
                            genre=qualification.primary_category_v1 or category,
                        )
                        if deeper_routes:
                            contact_routes = _merge_contact_routes(contact_routes, deeper_routes)
                            actionable_routes = [route for route in contact_routes if route.get("actionable")]
                            email_contact = next((route for route in contact_routes if route.get("type") == "email"), None)

                decision["contact_route_types"] = [str(route.get("type") or "") for route in contact_routes]
                decision["primary_contact_type"] = actionable_routes[0]["type"] if actionable_routes else ""
                coverage = coverage_with_contact(intel_dict, contact_found=bool(actionable_routes))
                decision["coverage_signals"] = coverage["coverage_signals"]
                decision["coverage_score"] = coverage["coverage_score"]

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
                record["business_name_review_status"] = name_review_status
                if name_check.get("tabelog_url"):
                    record["business_name_tabelog_url"] = name_check["tabelog_url"]
                if name_check.get("ramendb_url"):
                    record["business_name_ramendb_url"] = name_check["ramendb_url"]
                record["japan_intel"] = intel_dict
                record["source_count"] = intel.source_count
                record["source_coverage_score"] = coverage["coverage_score"]
                record["coverage_signals"] = coverage["coverage_signals"]
                email_source_url = str((email_contact or {}).get("source_url") or website)
                email_source = str((email_contact or {}).get("source") or "")
                _mark_inventory_review_blocked(
                    record,
                    city=str(source_search_job.get("city") or ""),
                    category=str(source_search_job.get("category") or qualification.primary_category_v1 or category),
                    email_source_url=email_source_url,
                    email_source=email_source,
                )
                record["portal_urls"] = intel.portal_urls
                record["official_site_candidates"] = intel.official_site_candidates
                record["social_links"] = intel.social_links
                record["operator_company_name"] = intel.operator_company_name
                record["operator_company_url"] = intel.operator_company_url
                if intel.portal_urls:
                    source_urls = record.setdefault("source_urls", {})
                    source_urls["portal_urls"] = intel.portal_urls
                if intel.official_site_candidates:
                    source_urls = record.setdefault("source_urls", {})
                    source_urls["official_site_candidates"] = intel.official_site_candidates
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
        "total_candidates": len(candidate_places),
        "leads": len(results),
        "qualified_without_email": qualified_without_email,
        "qualified_with_non_email_contact": qualified_with_non_email_contact,
        "qualified_without_supported_contact": qualified_without_supported_contact,
        "decisions": decisions,
    }


# ---------------------------------------------------------------------------
# Codex email-first search pipeline
# ---------------------------------------------------------------------------

def _extract_emails_from_text(text: str) -> list[str]:
    """Extract all usable business emails from arbitrary text."""
    normalized = html_lib.unescape(str(text or ""))
    normalized = urllib.parse.unquote(normalized)
    normalized = normalized.replace("＠", "@")
    normalized = re.sub(
        r"([A-Za-z0-9._%+-]+)\s*(?:\[at\]|\(at\)|【at】| at |アットマーク|アット|★|☆|●|■|◆|\(a\))\s*([A-Za-z0-9.-]+\.[A-Za-z]{2,})",
        r"\1@\2",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\s*@\s*", "@", normalized)
    return [
        email.lower()
        for email in (m.group(0) for m in _EMAIL_RE.finditer(normalized))
        if is_usable_business_email(email.lower())
    ]


_CODEX_TABELOG_URL_RE = re.compile(
    r"https?://tabelog[.]com/(?:tokyo|osaka|kyoto|hokkaido|fukuoka)/(?:[^/\s)]+/){1,5}[0-9]{7,8}/"
)
_CODEX_STALE_TABELOG_MARKERS = (
    "掲載保留",
    "閉店",
    "移転前の店舗情報",
    "リニューアル前の店舗情報",
    "休業中",
)
_CODEX_NON_TARGET_CUISINE_TERMS = (
    "タイ料理", "イタリアン", "フレンチ", "スペイン料理", "韓国料理",
    "ネパール料理", "インド料理", "カレー", "カフェ",
)
_CODEX_TARGET_GENRE_TERMS = (
    "居酒屋", "ラーメン", "つけ麺", "油そば", "中華そば", "焼き鳥",
    "鳥料理", "やきとん", "串焼き", "串揚げ", "もつ焼き", "もつ鍋",
    "おでん", "日本酒バー", "焼酎バー", "立ち飲み", "海鮮", "沖縄料理",
    "ろばた", "炉端",
)


def _codex_normalize_tabelog_url(url: str) -> str:
    match = _CODEX_TABELOG_URL_RE.search(str(url or ""))
    return match.group(0) if match else ""


def _codex_tabelog_urls_from_organic_results(organic_results: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for result in organic_results:
        haystack = " ".join(str(result.get(key) or "") for key in ("link", "title", "snippet"))
        for match in _CODEX_TABELOG_URL_RE.finditer(haystack):
            url = _codex_normalize_tabelog_url(match.group(0))
            if url and url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def _codex_compact_lines(value: str) -> str:
    return " ".join(line.strip() for line in str(value or "").splitlines() if line.strip())


def _codex_between(text: str, start: str, end: str) -> str:
    i = text.find(start)
    if i < 0:
        return ""
    i += len(start)
    j = text.find(end, i)
    return text[i:j if j >= 0 else None]


def _codex_field_after(text: str, start: str, end_markers: list[str]) -> str:
    i = text.find(start)
    if i < 0:
        return ""
    i += len(start)
    ends = [text.find(marker, i) for marker in end_markers]
    ends = [value for value in ends if value >= 0]
    j = min(ends) if ends else len(text)
    return text[i:j]


def _codex_clean_name(name: str) -> str:
    name = re.sub(r"\s*受賞・選出歴.*$", "", str(name or ""))
    return re.sub(r"\s+", " ", name).strip()


def _codex_city_for_address(address: str) -> str:
    city_terms = {
        "Tokyo": ("東京都",),
        "Osaka": ("大阪府大阪市", "大阪市"),
        "Kyoto": ("京都府京都市", "京都市"),
        "Sapporo": ("北海道札幌市", "札幌市"),
        "Fukuoka": ("福岡県福岡市", "福岡市"),
    }
    for city, terms in city_terms.items():
        if any(term in address for term in terms):
            return city
    return ""


def _codex_has_obvious_english_menu(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(marker in lowered for marker in (
        "english menu",
        "menu english",
        "英語メニュー",
        "英語のメニュー",
        "英語版メニュー",
    ))


def _codex_has_tabelog_english_menu_signal(html: str, text: str) -> bool:
    haystack = f"{html or ''}\n{text or ''}"
    compact = re.sub(r"\s+", "", html_lib.unescape(haystack))
    return any(marker in compact for marker in (
        "ChkEnglishMenu",
        "英語メニューあり",
        "複数言語メニューあり（英語）",
        "複数言語メニューあり(英語)",
        "多言語メニューあり（英語）",
        "多言語メニューあり(英語)",
    ))


def _codex_html_title(html: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html or "")
    if not match:
        return ""
    return _codex_compact_lines(re.sub(r"(?is)<[^>]+>", " ", html_lib.unescape(match.group(1))))


def _codex_homepage_links_from_tabelog(html: str, page_url: str) -> list[str]:
    blocks = [match.group(0) for match in re.finditer(r"(?is)<tr\b[^>]*>.*?ホームページ.*?</tr>", html or "")]
    if not blocks:
        blocks = [match.group(0) for match in re.finditer(r"(?is)ホームページ.{0,2000}", html or "")]

    links: list[str] = []
    for block in blocks:
        links.extend(re.findall(r'''(?is)<a\b[^>]+href=["']([^"']+)["']''', block))
    if not links:
        payload = extract_page_payload(page_url, html or "")
        links.extend(
            str(link.get("href") or "")
            for link in payload.get("links", [])
            if any(token in str(link.get("text") or "") for token in ("公式", "ホームページ", "HP"))
        )

    official_links: list[str] = []
    for raw_href in links:
        href = urllib.parse.urljoin(page_url, str(raw_href or "").strip())
        parsed = urllib.parse.urlparse(href)
        if parsed.scheme not in {"http", "https"}:
            continue
        host = parsed.netloc.lower().removeprefix("www.")
        if any(blocked in host for blocked in (
            "tabelog.com", "hotpepper.jp", "gnavi.co.jp", "instagram.com",
            "facebook.com", "x.com", "twitter.com", "line.me",
        )):
            continue
        official_links.append(urllib.parse.urlunparse((
            parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, "",
        )))
    return list(dict.fromkeys(official_links))


def _codex_parse_tabelog_profile(url: str, *, category: str) -> list[dict[str, str]]:
    """Parse a Tabelog profile the same way the v1 email collector did."""
    try:
        html = _fetch_page(url, timeout_seconds=10)
    except Exception:
        return []
    if not html or "食べログ" not in html:
        return []
    payload = extract_page_payload(url, html)
    text = str(payload.get("text") or "")
    top = text[:3500]
    if any(marker in top[:1800] for marker in _CODEX_STALE_TABELOG_MARKERS):
        return []
    if _codex_has_tabelog_english_menu_signal(html, text):
        return []
    if _codex_has_obvious_english_menu(text):
        return []

    info_start = text.find("店舗基本情報")
    if info_start < 0:
        return []
    end_candidates = [
        value for value in (
            text.find("特徴・関連情報", info_start),
            text.find("席・設備", info_start),
        )
        if value > info_start
    ]
    info_end = min(end_candidates) if end_candidates else len(text)
    info = text[info_start:info_end]
    full_info_end = text.find("初投稿者", info_start)
    full_info = text[info_start:full_info_end if full_info_end > info_start else len(text)]

    title = _codex_html_title(html)
    name = _codex_clean_name(_codex_compact_lines(_codex_between(info, "店名", "ジャンル")))
    genre = _codex_compact_lines(_codex_field_after(info, "ジャンル", ["予約・", "お問い合わせ", "住所", "交通手段"]))
    address = _codex_compact_lines(_codex_between(info, "住所", "大きな地図"))
    if not name or not genre or not address:
        return []
    if name.startswith(("移転 ", "リニューアル ", "閉店 ")):
        return []
    if not any(term in genre for term in _CODEX_TARGET_GENRE_TERMS):
        return []
    if any(term in f"{genre} {name}" for term in _CODEX_NON_TARGET_CUISINE_TERMS):
        return []
    if is_chain_business(name) or has_chain_or_franchise_infrastructure(f"{name} {title}"):
        return []
    city = _codex_city_for_address(address)
    if not city:
        return []

    emails = _extract_emails_from_text(full_info)
    if not emails:
        return []
    homepage_links = _codex_homepage_links_from_tabelog(html, url)
    website = homepage_links[0] if homepage_links else url
    candidates: list[dict[str, str]] = []
    for email in emails:
        candidates.append({
            "name": name,
            "email": email,
            "website": website,
            "snippet": genre,
            "source_url": url,
            "email_source_url": url,
            "address": address,
            "city": city,
            "tabelog_url": url,
            "profile_html": html,
            "genre_jp": genre,
            "category": category,
        })
    return candidates


def _extract_emails_from_organic_results(
    organic_results: list[dict[str, Any]],
    *,
    category: str,
    max_page_fetches: int = 6,
) -> list[dict[str, str]]:
    """Extract (name, email, website) candidates from organic search results.

    Tabelog profile links are parsed first because the v1 collector's strongest
    yield came from Yahoo/Tabelog profile pages with public emails. Generic
    organic snippets/pages are still scanned as a fallback for official sites.
    """
    candidates: list[dict[str, str]] = []
    seen_emails: set[str] = set()
    page_fetches = 0

    for url in _codex_tabelog_urls_from_organic_results(organic_results):
        for candidate in _codex_parse_tabelog_profile(url, category=category):
            email = str(candidate.get("email") or "").strip().lower()
            if not email or email in seen_emails:
                continue
            seen_emails.add(email)
            candidates.append(candidate)

    for result in organic_results:
        title = str(result.get("title") or "").strip()
        link = str(result.get("link") or "").strip()
        snippet = str(result.get("snippet") or "").strip()

        if not title or not link:
            continue
        if _codex_normalize_tabelog_url(link):
            continue

        # Try snippet first (fast path)
        emails = _extract_emails_from_text(snippet)

        # Fallback: fetch the page
        if not emails and page_fetches < max_page_fetches:
            try:
                page_html = _fetch_page(link, timeout_seconds=8)
                emails = _extract_emails_from_text(page_html)
                page_fetches += 1
            except Exception:
                pass

        for email in emails:
            if email in seen_emails:
                continue
            seen_emails.add(email)
            candidates.append({
                "name": title,
                "email": email,
                "website": link,
                "snippet": snippet,
                "source_url": link,
                "email_source_url": link,
            })

    return candidates


def codex_search_and_qualify(
    *,
    query: str,
    category: str = "ramen",
    state_root: Path | None = None,
    max_candidates: int = 24,
    search_job: dict[str, Any] | None = None,
    search_provider: str | None = None,
    serper_api_key: str = "",
    **_kwargs: Any,
) -> dict[str, Any]:
    """Codex email-first search: run organic search, extract emails, qualify."""
    from .search_scope import canonical_search_category
    from .record import find_existing_lead, create_lead_record, persist_lead_record
    from .preview import build_preview_menu, build_preview_html
    from .pitch import build_pitch

    if state_root is None:
        state_root = Path(__file__).resolve().parent.parent / "state"

    canonical = canonical_search_category(category)
    source_search_job = _normalise_search_job(query, canonical, search_job)

    # --- organic search ---
    try:
        organic_response = run_web_search(
            query=query, api_key=serper_api_key, gl="jp",
            timeout_seconds=10, provider=search_provider,
        )
    except Exception as exc:
        run_id = f"wrm-codex-{utc_now().replace(':', '').replace('-', '').replace('+00:00', 'z').lower()}"
        return {
            "run_id": run_id, "query": query, "search_provider": search_provider or "",
            "search_job": source_search_job, "total_candidates": 0, "leads": 0,
            "qualified_without_email": 0, "qualified_with_non_email_contact": 0,
            "qualified_without_supported_contact": 0,
            "decisions": [{"lead": False, "reason": "search_failed", "error": str(exc)}],
        }

    organic_results: list[dict[str, Any]] = organic_response.get("organic") or []
    candidates = _extract_emails_from_organic_results(organic_results, category=canonical)

    results: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    qualified_without_email = 0
    qualified_with_non_email_contact = 0
    qualified_without_supported_contact = 0

    candidate_window = _candidate_window(candidates, max_candidates)
    for candidate in candidate_window:
        source_name = candidate["name"]
        source_email = candidate["email"]
        source_website = candidate["website"]
        source_address = candidate.get("address", "")
        source_email_url = candidate.get("email_source_url") or candidate.get("source_url") or source_website

        # --- chain check ---
        if is_chain_business(source_name):
            decisions.append({
                "business_name": source_name, "lead": False,
                "reason": "chain_business", "email": source_email,
            })
            continue

        # --- dedup ---
        existing = find_existing_lead(
            business_name=source_name, website=source_website,
            phone="", place_id="", address="", state_root=state_root,
        )
        if existing:
            decisions.append({
                "business_name": source_name, "lead": False,
                "reason": "already_tracked",
                "existing_lead_id": existing.get("lead_id"),
            })
            continue

        dedup_key = source_email or _normalize_domain(source_website) or source_name
        if not _try_mark_in_flight(dedup_key):
            decisions.append({
                "business_name": source_name, "lead": False,
                "reason": "already_tracked",
            })
            continue

        try:
            # --- fetch website ---
            profile_html = str(candidate.get("profile_html") or "")
            pages: list[dict[str, str]] = []
            website_html = ""
            try:
                website_html = _fetch_page(source_website, timeout_seconds=10)
            except Exception as exc:
                if not profile_html:
                    decisions.append({
                        "business_name": source_name, "lead": False,
                        "reason": "fetch_failed", "error": str(exc),
                        "email": source_email,
                    })
                    continue

            website = source_website
            if website_html:
                pages.append({"url": website, "html": website_html})
            if profile_html and candidate.get("tabelog_url") != website:
                pages.append({"url": str(candidate.get("tabelog_url") or ""), "html": profile_html})
            elif profile_html and not pages:
                pages.append({"url": website, "html": profile_html})

            # --- qualify ---
            qualification = qualify_candidate(
                business_name=source_name,
                website=website,
                category=canonical,
                pages=pages,
                address=source_address,
            )

            decision = qualification.to_dict()
            if qualification.rejection_reason:
                decision.setdefault("reason", qualification.rejection_reason)
            decision["email"] = source_email
            decision["codex_source"] = True

            if qualification.lead and canonical in {"ramen", "izakaya"} and qualification.primary_category_v1 != canonical:
                decision["lead"] = False
                decision["reason"] = "search_category_mismatch"
                decision["requested_category"] = canonical
                decisions.append(decision)
                continue

            if qualification.lead:
                # --- contact routes ---
                contact_routes = discover_contact_routes(website, website_html)

                # Pre-populate the Codex-found email as a high-confidence route
                codex_email_route: dict[str, Any] = {
                    "type": "email",
                    "value": source_email,
                    "href": f"mailto:{source_email}",
                    "label": "Email (Codex)",
                    "source": "codex_organic_search",
                    "source_url": source_email_url,
                    "confidence": "high",
                    "discovered_at": utc_now(),
                    "actionable": True,
                }
                contact_routes = _merge_contact_routes([codex_email_route], contact_routes)

                actionable_routes = [r for r in contact_routes if r.get("actionable")]
                email_contact = next((r for r in contact_routes if r.get("type") == "email"), None)

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

                decision["contact_route_types"] = [str(r.get("type") or "") for r in contact_routes]
                decision["primary_contact_type"] = actionable_routes[0]["type"] if actionable_routes else ""

                # --- build preview & pitch ---
                preview_menu = build_preview_menu(
                    assessment=qualification,
                    snippets=qualification.evidence_snippets,
                    business_name=source_name,
                )
                preview_html = build_preview_html(
                    preview_menu=preview_menu,
                    ticket_machine_hint=None,
                    business_name=source_name,
                )
                pitch = build_pitch(
                    business_name=source_name,
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
                record["business_name_source"] = "codex_organic_search"
                record["business_name_verified_by"] = ["codex_organic_search", "website_fetch"]
                record["codex_source"] = True
                record["codex_email"] = source_email
                _mark_inventory_review_blocked(
                    record,
                    city=str(source_search_job.get("city") or ""),
                    category=str(source_search_job.get("category") or qualification.primary_category_v1 or canonical),
                    email_source_url=source_email_url,
                    email_source="codex_organic_search",
                )
                if candidate.get("tabelog_url"):
                    record["codex_tabelog_url"] = candidate.get("tabelog_url")
                    source_urls = record.setdefault("source_urls", {})
                    source_urls["tabelog"] = candidate.get("tabelog_url")
                persist_lead_record(record, state_root=state_root)
                results.append(record)
                decision["email_found"] = bool(email_contact)
                decision["lead_id"] = record["lead_id"]

            decisions.append(decision)
        finally:
            _clear_in_flight(dedup_key)

    run_id = f"wrm-codex-{utc_now().replace(':', '').replace('-', '').replace('+00:00', 'z').lower()}"
    decisions = [
        _add_search_context(d, query=query, search_job=source_search_job)
        for d in decisions
    ]

    return {
        "run_id": run_id,
        "query": query,
        "search_provider": search_provider or "",
        "search_job": source_search_job,
        "total_candidates": len(candidate_window),
        "leads": len(results),
        "qualified_without_email": qualified_without_email,
        "qualified_with_non_email_contact": qualified_with_non_email_contact,
        "qualified_without_supported_contact": qualified_without_supported_contact,
        "decisions": decisions,
    }
