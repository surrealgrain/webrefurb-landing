from __future__ import annotations

from typing import Any

from ..business_name import extract_business_name_candidates
from ..html_parser import extract_page_payload
from ..japan_restaurant_intel import (
    _category_from_text,
    _extract_japan_address,
    _extract_japanese_phone,
    _has_english_signal,
    _has_menu_signal,
    _official_candidates_from_links,
    _operator_from_text,
    _social_links_from_links,
)
from ..models import NormalizedSourceResult


def _normalize_portal_html(*, source_name: str, html: str, url: str) -> NormalizedSourceResult:
    payload = extract_page_payload(url, html)
    text = str(payload.get("text") or "")
    links = list(payload.get("links") or [])
    candidates = extract_business_name_candidates(html)
    name = candidates[0] if candidates else ""
    official_candidates = _official_candidates_from_links(url, links)
    operator_name, operator_url = _operator_from_text(text)
    return NormalizedSourceResult(
        source_name=source_name,
        source_url=url,
        name=name,
        official_site_url=official_candidates[0] if official_candidates else "",
        official_site_candidates=official_candidates,
        operator_company_name=operator_name,
        operator_company_url=operator_url,
        social_links=_social_links_from_links(links, base_url=url),
        menu_evidence_found=_has_menu_signal(text),
        english_menu_signal=_has_english_signal(text),
        category=_category_from_text(text),
        address=_extract_japan_address(text),
        phone=_extract_japanese_phone(text),
    )


def normalize_tabelog(html: str, url: str) -> NormalizedSourceResult:
    """Extract structured data from a Tabelog page."""
    return _normalize_portal_html(source_name="tabelog", html=html, url=url)


def normalize_google_maps(data: dict[str, Any], url: str) -> NormalizedSourceResult:
    """Extract structured data from a Google Maps place result."""
    return NormalizedSourceResult(
        source_name="google_maps",
        source_url=url,
        rating=data.get("rating"),
        review_count=data.get("ratingCount") or data.get("reviews"),
        address=data.get("address", ""),
        phone=data.get("phoneNumber", ""),
        place_id=data.get("placeId", ""),
    )


def normalize_gurunavi(html: str, url: str) -> NormalizedSourceResult:
    """Extract structured data from a Gurunavi page."""
    return _normalize_portal_html(source_name="gurunavi", html=html, url=url)


def normalize_hotpepper(html: str, url: str) -> NormalizedSourceResult:
    """Extract structured data from a Hot Pepper page."""
    return _normalize_portal_html(source_name="hotpepper", html=html, url=url)
