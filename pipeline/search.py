from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .business_name import business_name_is_suspicious, business_names_match, extract_business_name_candidates, resolve_business_name
from .contact_crawler import extract_contact_signals
from .utils import utc_now, write_json, ensure_dir
from .qualification import qualify_candidate
from .evidence import _count_japanese_chars


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
    contacts.append({
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
    })


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
            actionable=True,
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
            actionable=True,
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
            )
        for line_link in signals.line_links:
            href = line_link if line_link.startswith(("http://", "https://")) else f"https://{line_link}"
            _append_contact_route(
                contacts,
                seen,
                contact_type="line",
                value=line_link,
                label="LINE",
                href=href,
                source=source,
                source_url=source_url,
                confidence="high",
                discovered_at=discovered_at,
                actionable=True,
            )
        for line_id in signals.line_ids:
            _append_contact_route(
                contacts,
                seen,
                contact_type="line",
                value=line_id,
                label=f"LINE {line_id}",
                source=source,
                source_url=source_url,
                confidence="medium",
                discovered_at=discovered_at,
                actionable=True,
            )
        for handle in signals.instagram_handles:
            _append_contact_route(
                contacts,
                seen,
                contact_type="instagram",
                value=f"@{handle}",
                label=f"Instagram @{handle}",
                href=f"https://www.instagram.com/{handle}/",
                source=source,
                source_url=source_url,
                confidence="high",
                discovered_at=discovered_at,
                actionable=True,
            )

    priority = {
        "email": 0,
        "contact_form": 1,
        "line": 2,
        "instagram": 3,
        "phone": 4,
        "walk_in": 5,
        "map_url": 6,
        "website": 7,
    }
    contacts.sort(key=lambda contact: (priority.get(contact.get("type", ""), 99), str(contact.get("label") or "").lower()))
    return contacts


def run_search(
    *,
    query: str,
    api_key: str,
    gl: str = "jp",
    timeout_seconds: int = 10,
) -> list[dict[str, Any]]:
    """Run a Serper Maps search and return raw places."""
    url = "https://google.serper.dev/maps"
    payload = json.dumps({"q": query, "gl": gl}).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "X-API-KEY": api_key,
    })
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data.get("places") or []


def run_web_search(
    *,
    query: str,
    api_key: str,
    gl: str = "jp",
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query, "gl": gl}).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "X-API-KEY": api_key,
    })
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _address_search_token(address: str) -> str:
    first_part = str(address or "").split(",")[0].strip()
    return first_part or str(address or "").strip()


def _find_tabelog_candidate_url(
    *,
    business_name: str,
    address: str,
    api_key: str,
    timeout_seconds: int = 10,
) -> str:
    query_parts = [f"site:tabelog.com {business_name}"]
    address_token = _address_search_token(address)
    if address_token:
        query_parts.append(address_token)
    query = " ".join(part for part in query_parts if part).strip()
    try:
        data = run_web_search(query=query, api_key=api_key, timeout_seconds=timeout_seconds)
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
) -> str:
    """Find a RamenDB (ramendb.supleks.jp) listing for the business."""
    query_parts = [f"site:ramendb.supleks.jp {business_name}"]
    address_token = _address_search_token(address)
    if address_token:
        query_parts.append(address_token)
    query = " ".join(part for part in query_parts if part).strip()
    try:
        data = run_web_search(query=query, api_key=api_key, timeout_seconds=timeout_seconds)
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
    return bool(
        place.get("placeId")
        and rating >= 4.0
        and reviews >= 50
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


def verify_business_name(
    *,
    source_name: str,
    website: str,
    html: str,
    address: str,
    serper_api_key: str,
    timeout_seconds: int = 8,
    category: str = "",
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

    tabelog_url = _find_tabelog_candidate_url(
        business_name=resolved_name or source_candidate,
        address=address,
        api_key=serper_api_key,
        timeout_seconds=timeout_seconds,
    ) if (resolved_name or source_candidate) else ""
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
    if category == "ramen" and (resolved_name or source_candidate):
        ramendb_url = _find_ramendb_candidate_url(
            business_name=resolved_name or source_candidate,
            address=address,
            api_key=serper_api_key,
            timeout_seconds=timeout_seconds,
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


def search_and_qualify(
    *,
    query: str,
    serper_api_key: str,
    category: str = "ramen",
    state_root: Path | None = None,
    max_candidates: int = 24,
) -> dict[str, Any]:
    """Search, fetch pages, qualify each candidate, persist leads."""
    if state_root is None:
        state_root = Path(__file__).resolve().parent.parent / "state"

    raw_places = run_search(query=query, api_key=serper_api_key)
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

        # Extract coordinates from Serper Maps response
        position = place.get("position") or {}
        place_lat = position.get("lat") if isinstance(position, dict) else None
        place_lng = position.get("lng") if isinstance(position, dict) else None

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

        try:
            website_html = _fetch_page(website)
            pages = [{"url": website, "html": website_html}]
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

    run_id = f"wrm-search-{utc_now().replace(':', '').replace('-', '').replace('+00:00', 'z').lower()}"
    return {
        "run_id": run_id,
        "query": query,
        "total_candidates": len(raw_places[:max_candidates]),
        "leads": len(results),
        "qualified_without_email": qualified_without_email,
        "qualified_with_non_email_contact": qualified_with_non_email_contact,
        "qualified_without_supported_contact": qualified_without_supported_contact,
        "decisions": decisions,
    }
