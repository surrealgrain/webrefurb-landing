#!/usr/bin/env python3
"""Search tourist-heavy cities for ramen/izakaya leads using SearXNG + Google Maps."""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.search_provider import run_maps_search, run_organic_search
from pipeline.email_discovery.email_extractor import extract_emails
from pipeline.qr_menu_detection import has_qr_menu_signals

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
OUTPUT_FILE = STATE_DIR / "searxng_tourist_leads.json"

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

MAX_PLACES_PER_QUERY = 8

SEARCH_QUERIES_PER_CITY = [
    "ramen {ja}",
    "izakaya {ja}",
]

CHAINS = (
    "一蘭", "一風堂", "天下一品", "幸楽苑", "くるま", "スガキヤ",
    "丸亀製麺", "はなまるうどん", "吉野家", "松屋", "すき家",
    "王将", "餃子の", "日高屋", "山崎", "サイゼリや",
    "鳥貴族", "白木屋", "笑笑", "和民", "魚民", "笑笑",
    "ゴーゴーカレー", "ペッパーランチ", "ロッテリア",
    "バーミヤン", "ココス", "ガスト", "ジョナサン",
    "デニーズ", "ジョリーパスタ", "はま寿司", "くら寿司", "スシロー",
)


def is_chain(name: str) -> bool:
    return any(c in name for c in CHAINS)


def find_emails_via_searxng(business_name: str, city_ja: str) -> list[str]:
    """Use SearXNG to search for the restaurant's email."""
    queries = [
        f'"{business_name}" メール お問い合わせ {city_ja}',
        f'"{business_name}" email contact {city_ja}',
        f'"{business_name}" 特定商取引法',
    ]
    found: list[str] = []
    seen: set[str] = set()
    for q in queries:
        try:
            result = run_organic_search(query=q, provider="searxng", timeout_seconds=15)
            for item in result.get("organic", []):
                text = f"{item.get('title', '')} {item.get('snippet', '')}"
                urls = [item.get("link", "")]
                emails = extract_emails(text=text, html="", source_url=urls[0])
                for e in emails:
                    addr = e.email.lower()
                    if addr not in seen:
                        seen.add(addr)
                        found.append(addr)
        except Exception:
            continue
    return found


def scrape_website_emails(url: str) -> list[str]:
    """Scrape a website directly for email addresses."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; bot)",
            "Accept": "text/html",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return []
    emails = extract_emails(text="", html=html, source_url=url)
    seen: set[str] = set()
    result: list[str] = []
    for e in emails:
        addr = e.email.lower()
        if addr not in seen:
            seen.add(addr)
            result.append(addr)
    return result


def main():
    leads: list[dict] = []
    all_emails_found = 0

    for city_ja, city_en, prefecture in TIER1_CITIES:
        print(f"\n=== {city_ja} ({city_en}, {prefecture}) ===")

        for query_template in SEARCH_QUERIES_PER_CITY:
            query = query_template.format(ja=city_ja)
            category = "ramen" if "ramen" in query_template else "izakaya"
            print(f"  Searching: {query}")

            try:
                maps_result = run_maps_search(query=query)
            except Exception as exc:
                print(f"    Maps search failed: {exc}")
                continue

            places = maps_result.get("places", [])[:MAX_PLACES_PER_QUERY]
            print(f"    Found {len(places)} places")

            for place in places:
                name = str(place.get("title") or place.get("name") or "").strip()
                if not name or is_chain(name):
                    continue

                address = str(place.get("address", ""))
                rating = place.get("rating", "")
                rating_count = place.get("ratingCount") or place.get("user_ratings_total", 0)
                website = str(place.get("website") or "").strip()

                # Skip low-rating places
                try:
                    if float(rating) < 3.5:
                        continue
                except (ValueError, TypeError):
                    pass

                # Skip if too few reviews (only filter when data is available)
                try:
                    rc_val = int(rating_count)
                    if rc_val > 0 and rc_val < 10:
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
                    "rating_count": int(rating_count) if rating_count else 0,
                    "website": website,
                    "phone": str(place.get("phoneNumber") or place.get("phone") or ""),
                    "emails": [],
                    "email_sources": [],
                    "has_qr_menu": None,
                    "notes": [],
                }

                # Check for QR menu signals on website
                if website:
                    try:
                        req = urllib.request.Request(website, headers={
                            "User-Agent": "Mozilla/5.0 (compatible; bot)",
                            "Accept": "text/html",
                        })
                        with urllib.request.urlopen(req, timeout=8) as resp:
                            html = resp.read().decode("utf-8", errors="replace")
                        lead["has_qr_menu"] = has_qr_menu_signals(html)
                        if lead["has_qr_menu"]:
                            lead["notes"].append("QR menu detected on website — already has digital menu")
                    except Exception:
                        pass

                # Email discovery: SearXNG search first
                search_emails = find_emails_via_searxng(name, city_ja)
                if search_emails:
                    lead["emails"].extend(search_emails)
                    lead["email_sources"].extend([f"searxng:{e}" for e in search_emails])

                # Email discovery: scrape website as fallback
                if website and len(lead["emails"]) < 2:
                    site_emails = scrape_website_emails(website)
                    for e in site_emails:
                        if e not in lead["emails"]:
                            lead["emails"].append(e)
                            lead["email_sources"].append(f"website:{website}")

                if lead["emails"]:
                    all_emails_found += len(lead["emails"])

                leads.append(lead)
                status = "✓" if lead["emails"] else "·"
                qr_note = " [QR]" if lead.get("has_qr_menu") else ""
                print(f"    {status} {name[:30]:30s} | {rating} | emails={len(lead['emails'])}{qr_note}")

                time.sleep(0.5)  # be polite

            time.sleep(1)

    # Summary
    with_email = [l for l in leads if l["emails"]]
    no_qr = [l for l in with_email if not l.get("has_qr_menu")]

    print(f"\n{'='*60}")
    print(f"Total places: {len(leads)}")
    print(f"With emails: {len(with_email)} ({all_emails_found} total email addresses)")
    print(f"Without QR menu: {len(no_qr)} (best targets)")
    print(f"{'='*60}")

    # Save results
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "summary": {
            "total_places": len(leads),
            "with_email": len(with_email),
            "total_emails": all_emails_found,
            "without_qr_menu": len(no_qr),
            "cities_searched": len(TIER1_CITIES),
        },
        "leads": leads,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to {OUTPUT_FILE}")

    # Print top leads
    print("\n--- TOP LEADS (email + no QR menu) ---")
    for lead in sorted(no_qr, key=lambda x: float(x.get("rating") or 0), reverse=True)[:20]:
        print(f"  {lead['name'][:35]:35s} | {lead['city_en']:15s} | {lead['rating']} | {', '.join(lead['emails'])}")


if __name__ == "__main__":
    main()
