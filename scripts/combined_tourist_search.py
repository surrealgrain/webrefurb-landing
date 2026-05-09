#!/usr/bin/env python3
"""Combined restaurant lead search — ALL tools together.

Discovery: Google Maps (webserper Playwright)
Email finding (all used in parallel):
  1. SearXNG organic search (Google + Brave + Startpage)
  2. curl_cffi async deep page probing with TLS impersonation
  3. Tokushoho page detection + structured parsing
  4. Full email extraction pipeline (mailto, Japanese prefix, fullwidth, bracket, star)
Categories: ramen, izakaya, sushi
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.search_provider import run_maps_search, run_organic_search
from pipeline.email_discovery.email_extractor import extract_emails, extract_emails_from_page
from pipeline.email_discovery.tokushoho import find_tokushoho_links, is_tokushoho_page, parse_tokushoho_page
from pipeline.qr_menu_detection import has_qr_menu_signals
from curl_cffi.requests import AsyncSession
from concurrent.futures import ThreadPoolExecutor

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
OUTPUT_FILE = STATE_DIR / "combined_tourist_leads.json"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TIER1_CITIES = [
    ("渋谷区", "Shibuya", "Tokyo"),
    ("新宿区", "Shinjuku", "Tokyo"),
    ("台東区", "Taito/Asakusa", "Tokyo"),
    ("港区", "Minato", "Tokyo"),
    ("千代田区", "Chiyoda", "Tokyo"),
    ("中央区", "Chuo/Ginza", "Tokyo"),
    ("大阪市", "Osaka", "Osaka"),
    ("京都市", "Kyoto", "Kyoto"),
    ("福岡市博多区", "Fukuoka/Hakata", "Fukuoka"),
    ("札幌市", "Sapporo", "Hokkaido"),
    ("横浜市", "Yokohama", "Kanagawa"),
    ("名古屋市", "Nagoya", "Aichi"),
    ("神戸市", "Kobe", "Hyogo"),
    ("那覇市", "Naha", "Okinawa"),
]

SEARCH_QUERIES = ["ramen {ja}", "izakaya {ja}", "sushi {ja}"]
MAX_PLACES = 6

CHAINS = (
    "一蘭", "一風堂", "天下一品", "幸楽苑", "くるま", "スガキヤ",
    "丸亀製麺", "はなまるうどん", "吉野家", "松屋", "すき家",
    "王将", "餃子の", "日高屋", "山崎", "サイゼリや",
    "鳥貴族", "白木屋", "笑笑", "和民", "魚民",
    "ゴーゴーカレー", "ペッパーランチ", "ロッテリア",
    "バーミヤン", "ココス", "ガスト", "ジョナサン",
    "デニーズ", "ジョリーパスタ", "はま寿司", "くら寿司", "スシロー",
    "かっぱ寿司", "元祖寿司", "魚べい", "スシロー",
)

# Deep probe paths
DEEP_PATHS = [
    "/contact/", "/tokushoho/", "/info/", "/legal/",
    "/特定商取引/", "/inquiry/", "/company/", "/about/",
]

SENTRY_DOMAINS = ("sentry.wixpress.com", "sentry-next.wixpress.com", "sentry.io")
THIRD_PARTY_DOMAINS = ("catchtable.net", "example.com", "sample.com")


def is_chain(name: str) -> bool:
    return any(c in name for c in CHAINS)


def clean_emails(raw: list[str]) -> list[str]:
    clean = []
    for e in raw:
        e_lower = e.lower()
        if any(d in e_lower for d in SENTRY_DOMAINS):
            continue
        if any(d in e_lower for d in THIRD_PARTY_DOMAINS):
            continue
        if len(e.split("@")[0]) < 2:
            continue
        clean.append(e_lower)
    return clean


def _strip_html(html: str) -> str:
    text = re.sub(r"<(?:script|style)[^>]*>.*?</(?:script|style)>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Strategy 1: SearXNG organic search for emails
# ---------------------------------------------------------------------------
def find_emails_searxng(business_name: str, city_ja: str) -> list[dict]:
    results = []
    queries = [
        f'"{business_name}" メール お問い合わせ {city_ja}',
        f'"{business_name}" 特定商取引法',
    ]
    for q in queries:
        try:
            result = run_organic_search(query=q, provider="searxng", timeout_seconds=10)
            for item in result.get("organic", []):
                text = f"{item.get('title', '')} {item.get('snippet', '')}"
                link = item.get("link", "")
                emails = extract_emails(text=text, html="", source_url=link)
                for e in emails:
                    results.append({"email": e.email, "source": "searxng_organic", "url": link})
        except Exception:
            continue
    return results


# ---------------------------------------------------------------------------
# Strategy 2: curl_cffi async deep page probing
# ---------------------------------------------------------------------------
async def scrape_site_async(url: str, session: AsyncSession) -> tuple[str, list[dict]]:
    """Async scrape: homepage + tokushoho links + deep probing, all in parallel."""
    emails: list[dict] = []
    seen: set[str] = set()
    homepage_html = ""

    # Build all URLs to fetch in parallel
    fetch_urls = [url]  # homepage first
    path_map = {url: "homepage"}

    for path in DEEP_PATHS:
        probe_url = urllib.parse.urljoin(url, path)
        fetch_urls.append(probe_url)
        path_map[probe_url] = path

    # Fetch all pages in parallel
    tasks = [session.get(u, timeout=10) for u in fetch_urls]
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    # Process homepage first
    if not isinstance(responses[0], Exception) and responses[0].status_code == 200:
        homepage_html = responses[0].text

        # Extract emails from homepage
        extracted = extract_emails(html=homepage_html, text="", source_url=url)
        for e in extracted:
            if e.email.lower() not in seen:
                seen.add(e.email.lower())
                emails.append({"email": e.email, "source": "curl_cffi_homepage", "url": url})

        # Find tokushoho links on homepage
        tokushoho_links = find_tokushoho_links(homepage_html, base_url=url)
        for link in tokushoho_links:
            full_url = urllib.parse.urljoin(url, link)
            if full_url not in path_map:
                try:
                    resp = await session.get(full_url, timeout=8)
                    if resp.status_code == 200:
                        _process_page(resp.text, full_url, seen, emails, is_tokusho=True)
                except Exception:
                    pass

    # Process deep pages
    for i, resp in enumerate(responses[1:], start=1):
        fetch_url = fetch_urls[i]
        if isinstance(resp, Exception) or resp.status_code != 200:
            continue
        path = path_map[fetch_url]
        _process_page(resp.text, fetch_url, seen, emails, path=path)

    return homepage_html, emails


def _process_page(html: str, url: str, seen: set, emails: list, path: str = "", is_tokusho: bool = False):
    """Extract emails from a single page."""
    text = _strip_html(html)

    # Check if tokushoho page
    if is_tokusho or is_tokushoho_page(url, text=text):
        parsed = parse_tokushoho_page(url=url, html=html, text=text)
        if parsed.is_tokushoho:
            if parsed.email and parsed.email.lower() not in seen:
                seen.add(parsed.email.lower())
                emails.append({"email": parsed.email, "source": "tokushoho_structured", "url": url})
            for raw in (parsed.raw_emails or []):
                email = raw.get("email", "")
                if email and email.lower() not in seen:
                    seen.add(email.lower())
                    emails.append({"email": email, "source": "tokushoho_extracted", "url": url})
            return

    # Standard email extraction
    extracted = extract_emails(text=text, html=html, source_url=url)
    for e in extracted:
        if e.email.lower() not in seen:
            seen.add(e.email.lower())
            src = f"curl_cffi_deep:{path}" if path else "curl_cffi_page"
            emails.append({"email": e.email, "source": src, "url": url})


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
async def main():
    leads: list[dict] = []
    all_emails_found = 0
    stats = {"maps_searches": 0, "places_found": 0, "searxng_queries": 0,
             "site_scrapes": 0, "tokushoho_hits": 0}

    async with AsyncSession(impersonate="chrome") as session:
        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=2)

        for city_ja, city_en, prefecture in TIER1_CITIES:
            print(f"\n{'='*60}")
            print(f"  {city_ja} ({city_en}, {prefecture})")
            print(f"{'='*60}")

            for query_template in SEARCH_QUERIES:
                query = query_template.format(ja=city_ja)
                category = query_template.split()[0]
                print(f"\n  Maps: {query}")

                try:
                    maps_result = await loop.run_in_executor(executor, lambda q=query: run_maps_search(query=q))
                    stats["maps_searches"] += 1
                except Exception as exc:
                    print(f"    Maps failed: {exc}")
                    continue

                places = maps_result.get("places", [])[:MAX_PLACES]
                stats["places_found"] += len(places)
                print(f"    {len(places)} places")

                for place in places:
                    name = str(place.get("title") or place.get("name") or "").strip()
                    if not name or is_chain(name):
                        continue

                    address = str(place.get("address", ""))
                    rating = place.get("rating", "")
                    website = str(place.get("website") or "").strip()
                    phone = str(place.get("phoneNumber") or place.get("phone") or "")

                    try:
                        if float(rating) < 3.5:
                            continue
                    except (ValueError, TypeError):
                        pass

                    lead = {
                        "name": name,
                        "category": category,
                        "city_ja": city_ja,
                        "city_en": city_en,
                        "prefecture": prefecture,
                        "address": address,
                        "rating": rating,
                        "website": website,
                        "phone": phone,
                        "emails": [],
                        "email_details": [],
                        "has_qr_menu": None,
                        "qr_checked": False,
                        "tools_used": [],
                    }

                    # --- Strategy 1: SearXNG organic search ---
                    if website:
                        searxng_results = await loop.run_in_executor(
                            executor, lambda n=name, c=city_ja: find_emails_searxng(n, c))
                        stats["searxng_queries"] += 2
                        if searxng_results:
                            lead["tools_used"].append("searxng_organic")
                            for r in searxng_results:
                                if r.get("email"):
                                    lead["email_details"].append(r)

                    # --- Strategy 2: curl_cffi async deep probing ---
                    if website:
                        homepage_html, site_emails = await scrape_site_async(website, session)
                        stats["site_scrapes"] += 1

                        if site_emails:
                            lead["tools_used"].append("curl_cffi_deep")
                            lead["email_details"].extend(site_emails)

                        tokushoho_count = sum(1 for d in site_emails if "tokushoho" in d.get("source", ""))
                        if tokushoho_count:
                            stats["tokushoho_hits"] += tokushoho_count
                            lead["tools_used"].append("tokushoho")

                        if homepage_html:
                            lead["has_qr_menu"] = has_qr_menu_signals(homepage_html)
                            lead["qr_checked"] = True

                    # --- Deduplicate and clean ---
                    seen: set[str] = set()
                    for detail in lead["email_details"]:
                        addr = detail.get("email", "").lower()
                        if addr and addr not in seen:
                            seen.add(addr)
                            lead["emails"].append(addr)

                    lead["emails"] = clean_emails(lead["emails"])
                    if lead["emails"]:
                        all_emails_found += len(lead["emails"])

                    leads.append(lead)

                    sources = set(d.get("source", "") for d in lead["email_details"] if d.get("email"))
                    src_tag = f" via {','.join(sources)}" if sources else ""
                    qr_tag = " [QR]" if lead.get("has_qr_menu") else ""
                    mark = "+" if lead["emails"] else " "
                    print(f"    {mark} {name[:32]:32s} | {rating} | {len(lead['emails'])} emails{qr_tag}{src_tag}")

                    time.sleep(0.2)

    # ---------------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------------
    with_email = [l for l in leads if l["emails"]]
    no_qr = [l for l in with_email if not l.get("has_qr_menu")]

    by_email: dict[str, dict] = {}
    for lead in no_qr:
        for email in lead["emails"]:
            if email not in by_email:
                by_email[email] = lead
    unique_leads = list(by_email.values())

    print(f"\n{'='*60}")
    print(f"RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Cities:                {len(TIER1_CITIES)}")
    print(f"Places discovered:     {stats['places_found']}")
    print(f"Total leads:           {len(leads)}")
    print(f"With emails:           {len(with_email)}")
    print(f"Unique emails:         {all_emails_found}")
    print(f"Without QR menu:       {len(no_qr)}")
    print(f"Sendable targets:      {len(unique_leads)}")
    print(f"SearXNG queries:       {stats['searxng_queries']}")
    print(f"Site scrapes:          {stats['site_scrapes']}")
    print(f"Tokushoho hits:        {stats['tokushoho_hits']}")
    print(f"{'='*60}")

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "stats": stats,
        "summary": {
            "cities_searched": len(TIER1_CITIES),
            "total_places": len(leads),
            "with_email": len(with_email),
            "total_emails": all_emails_found,
            "without_qr_menu": len(no_qr),
            "unique_sendable_targets": len(unique_leads),
        },
        "leads": leads,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {OUTPUT_FILE}")

    print(f"\n--- SENDABLE TARGETS (email + no QR menu) ---")
    for lead in sorted(unique_leads, key=lambda x: float(x.get("rating") or 0), reverse=True):
        sources = [d.get("source", "") for d in lead.get("email_details", [])
                    if d.get("email", "").lower() in lead["emails"]]
        src = max(set(sources), key=sources.count) if sources else ""
        print(f"  {lead['name'][:35]:35s} | {lead['city_en']:15s} | {lead['rating']} | {', '.join(lead['emails'])} ({src})")


if __name__ == "__main__":
    asyncio.run(main())
