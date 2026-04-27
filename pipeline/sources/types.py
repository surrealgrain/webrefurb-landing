from __future__ import annotations

from typing import Any

from ..models import NormalizedSourceResult


def normalize_tabelog(html: str, url: str) -> NormalizedSourceResult:
    """Extract structured data from a Tabelog page."""
    # Stub: real implementation would parse the HTML
    return NormalizedSourceResult(
        source_name="tabelog",
        source_url=url,
    )


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
    return NormalizedSourceResult(
        source_name="gurunavi",
        source_url=url,
    )


def normalize_hotpepper(html: str, url: str) -> NormalizedSourceResult:
    """Extract structured data from a Hot Pepper page."""
    return NormalizedSourceResult(
        source_name="hotpepper",
        source_url=url,
    )
