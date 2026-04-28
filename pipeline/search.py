from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

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

    for place in raw_places[:max_candidates]:
        website = str(place.get("website") or "").strip()
        business_name = str(place.get("title") or place.get("name") or "").strip()
        if not website or not business_name:
            continue

        # Skip if already tracked as a lead (any status)
        from .record import find_existing_lead
        existing = find_existing_lead(
            business_name=business_name,
            website=website,
            phone=str(place.get("phoneNumber", "")),
            place_id=str(place.get("placeId", "")),
            address=str(place.get("address", "")),
            state_root=state_root,
        )
        if existing:
            decisions.append({
                "business_name": business_name,
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
            decisions.append({"business_name": business_name, "lead": False, "reason": "fetch_failed", "error": str(exc)})
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
        )

        decision = qualification.to_dict()

        if qualification.lead:
            contact_email = find_contact_email(website, website_html)
            if not contact_email:
                qualified_without_email += 1
                decision["lead"] = False
                decision["reason"] = "no_business_email_found"
                decisions.append(decision)
                continue

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
                source_query=query,
                state_root=state_root,
            )
            record["email"] = contact_email
            persist_lead_record(record, state_root=state_root)
            results.append(record)
            decision["email_found"] = True

        decisions.append(decision)

    run_id = f"wrm-search-{utc_now().replace(':', '').replace('-', '').replace('+00:00', 'z').lower()}"
    return {
        "run_id": run_id,
        "query": query,
        "total_candidates": len(raw_places[:max_candidates]),
        "leads": len(results),
        "qualified_without_email": qualified_without_email,
        "decisions": decisions,
    }
