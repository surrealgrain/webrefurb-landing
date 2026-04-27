from __future__ import annotations

import json
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
            pages = [{"url": website, "html": _fetch_page(website)}]
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
        )

        decisions.append(qualification.to_dict())

        if qualification.lead:
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
            persist_lead_record(record, state_root=state_root)
            results.append(record)

    run_id = f"wrm-search-{utc_now().replace(':', '').replace('-', '').replace('+00:00', 'z').lower()}"
    return {
        "run_id": run_id,
        "query": query,
        "total_candidates": len(raw_places[:max_candidates]),
        "leads": len(results),
        "decisions": decisions,
    }
