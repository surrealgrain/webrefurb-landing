#!/usr/bin/env python3
"""Bulk lead generation with preview + inline pitch.

Discovers candidates from Tabelog, fetches websites, extracts emails + menu
evidence, generates preview pages with inline pitches, and creates lead
records. Email-only — no form-only leads.

Does NOT send any email or submit any forms.
"""

from __future__ import annotations

import sys
import time
import urllib.parse
from html import escape
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.constants import OUTREACH_STATUS_NEW
from pipeline.contact_crawler import (
    extract_contact_signals,
    is_usable_business_email,
)
from pipeline.directory_discovery import (
    discover_area_candidates,
    DirectoryCandidate,
    _is_chain,
)
from pipeline.evidence import assess_evidence
from pipeline.html_parser import extract_page_payload
from pipeline.preview import build_preview_menu, build_preview_html
from pipeline.pitch import build_pitch
from pipeline.models import EvidenceAssessment, TicketMachineHint
from pipeline.record import (
    persist_lead_record,
    find_existing_lead,
    normalise_lead_contacts,
)
from pipeline.utils import utc_now, slugify, sha256_text, ensure_dir
from scrapling import Fetcher

WEBSITE_TIMEOUT = 10

# Paths to probe when homepage has no email
_CONTACT_PROBE_PATHS = (
    "/contact/", "/contact",
    "/inquiry/", "/inquiry",
    "/otoiawase/", "/otoiawase",
    "/toiawase/", "/toiawase",
    "/mail/", "/mail",
    "/info/", "/info",
    "/access/", "/access",
    "/shop/info/",
    "/about/", "/about",
    "/company/", "/company",
    "/staff/", "/staff",
    "/concept/", "/concept",
    "/storeinfo/", "/storeinfo",
    "/reserve/", "/reserve",
    "/faq/", "/faq",
)
_EXCLUDED_PROBE_TOKENS = (
    "cart", "checkout", "newsletter", "subscribe",
    "recruit", "career", "login", "signup", "account",
    "注文", "採用", "求人", "ログイン",
)


def _extract_area(address: str) -> str:
    if not address:
        return "unknown"
    parts = address.strip().split()
    if len(parts) >= 2:
        return slugify(parts[1].split("-")[0])
    return slugify(address.split(",")[0].split("-")[0])


def _package_for_category(category: str, city: str) -> tuple[str, str]:
    """Return (package_key, reason) based on category and city."""
    if category == "ramen":
        return "package_1_remote_30k", "Ramen shop — online English menu delivery."
    elif category == "izakaya":
        return "package_3_qr_menu_65k", "Izakaya — QR English menu for frequent changes."
    else:
        return "package_2_printed_delivered_45k", "Restaurant — printed English menu kit."


def _build_inline_pitch_html(
    *,
    business_name: str,
    category: str,
    city: str,
    email: str,
    preview_menu_html: str,
    recommended_package: str,
) -> str:
    """Build the inline pitch section embedded in the preview page."""
    # City-specific delivery line
    if city == "Tokyo":
        delivery_line = (
            "東京エリアであれば、 laminated 仕上げをご希望の場合は直接お届けすることも可能です。"
        )
    else:
        delivery_line = "データはメールで納品いたします。印刷・ラミネートをご希望の場合はご相談ください。"

    category_label = {
        "ramen": "ラーメン店",
        "izakaya": "居酒屋",
        "restaurant": "飲食店",
    }.get(category, "飲食店")

    return f"""
<div class="pitch-section">
<h2>ご提案</h2>
<p>{escape(business_name)} 様</p>
<p>
突然のご連絡失礼いたします。<br>
{escape(category_label)}の英語メニュー・注文ガイドの制作を行っております、Chris（クリス）と申します。
</p>
<p>
公開されているメニュー情報を拝見し、海外からのお客様が注文時に迷いやすい箇所があるかもしれないと思いご連絡いたしました。
</p>
<p style="color:var(--accent);font-weight:600;">
下記のような英語メニューのサンプルを、貴店のメニュー写真をもとに作成できます：
</p>
<div class="preview-sample">
{preview_menu_html}
</div>
<p>{delivery_line}</p>
<p>
ご興味がございましたら、現在お使いのメニューや券売機の写真を送っていただければ、貴店の内容に合わせた確認用サンプルを作成いたします。
</p>
<p style="font-size:10pt;color:var(--muted);">
詳細：https://webrefurb.com/ja<br>
ご連絡：{escape(email)}
</p>
<p>
不要なご連絡でしたら「不要」とご返信ください。今後のご連絡は控えます。
</p>
<p>よろしくお願いいたします。<br>Chris（クリス）</p>
</div>
"""


def _build_full_preview_html(
    *,
    business_name: str,
    category: str,
    city: str,
    email: str,
    assessment: EvidenceAssessment,
    snippets: list[str],
    recommended_package: str,
) -> str | None:
    """Build a complete preview page with menu preview + inline pitch."""
    # Build menu preview
    preview_menu = build_preview_menu(
        assessment=assessment,
        snippets=snippets,
        business_name=business_name,
    )

    ticket_hint = None
    if assessment.machine_evidence_found:
        ticket_hint = TicketMachineHint(has_ticket_machine=True)

    menu_html = build_preview_html(
        preview_menu=preview_menu,
        ticket_machine_hint=ticket_hint,
        business_name=business_name,
    )

    # Extract just the body content from menu_html (strip doctype/wrapper)
    import re
    body_match = re.search(r'<main>(.*?)</main>', menu_html, re.DOTALL)
    menu_body = body_match.group(1) if body_match else ""

    # Build inline pitch
    pitch_html = _build_inline_pitch_html(
        business_name=business_name,
        category=category,
        city=city,
        email=email,
        preview_menu_html=menu_body,
        recommended_package=recommended_package,
    )

    # Build pitch draft for the record
    pitch = build_pitch(
        business_name=business_name,
        category=category,
        preview_menu=preview_menu,
        ticket_machine_hint=ticket_hint,
        recommended_package=recommended_package,
    )

    # Compose full page
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(business_name)} — English Menu Preview</title>
<style>
:root {{ --ink:#f0ebe3; --muted:#a8a29e; --paper:#0f0d0b; --surface:#1c1917; --line:#292524; --accent:#c53d43; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:'Outfit',ui-sans-serif,system-ui,-apple-system,sans-serif; background:var(--paper); color:var(--ink); font-size:12pt; }}
main {{ max-width:720px; margin:0 auto; padding:28px 20px 56px; }}
h1 {{ font-size:24pt; margin:0 0 4px; }}
h2 {{ font-size:16pt; color:var(--accent); margin:24px 0 12px; }}
h3 {{ font-size:13pt; margin:16px 0 8px; }}
.preview-table {{ width:100%; border-collapse:collapse; }}
.preview-table td {{ padding:8px 4px; border-bottom:1px solid var(--line); }}
.preview-table .ja {{ font-weight:600; width:30%; }}
.preview-table .arrow {{ color:var(--accent); text-align:center; width:24px; }}
.preview-table .en {{ width:40%; }}
.preview-table .price {{ text-align:right; white-space:nowrap; }}
.disclaimer {{ margin-top:24px; padding:16px; background:var(--surface); border-radius:8px; color:var(--muted); font-size:10pt; line-height:1.6; border:1px solid var(--line); }}
.pitch-section {{ margin-top:32px; padding:24px; background:var(--surface); border-radius:12px; border:1px solid var(--line); line-height:1.8; }}
.pitch-section p {{ margin:8px 0; }}
.pitch-section .preview-sample {{ margin:16px 0; }}
.empty-proof {{ border:1px solid var(--line); background:var(--surface); border-radius:8px; padding:16px; color:var(--muted); line-height:1.5; }}
</style>
</head>
<body>
<main>
<h1>{escape(business_name)}</h1>
<p style="color:var(--muted)">English Menu Preview (illustrative example)</p>

<h2>Menu Preview</h2>
{menu_body}

<div class="disclaimer">
{escape(preview_menu.disclaimer_ja)}
</div>

{pitch_html}
</main>
</body>
</html>""", pitch


def _build_lead_record(
    *,
    cand: DirectoryCandidate,
    contacts: list[dict],
    primary_contact: dict | None,
    email_val: str,
    assessment: EvidenceAssessment,
    snippets: list[str],
    pitch: dict,
    preview_available: bool,
    city: str,
) -> dict:
    name = cand.name
    website = cand.website
    address = cand.address
    phone = cand.phone
    area = _extract_area(address)
    name_slug = slugify(name)
    short_hash = sha256_text(f"{name}{website}")[:4]
    lead_id = f"wrm-{name_slug}-{area}-{short_hash}"

    category = cand.category or "restaurant"
    primary_cat = {"ramen": "ramen", "izakaya": "izakaya"}.get(category, "restaurant")
    recommended_package, package_reason = _package_for_category(primary_cat, city)

    return {
        "lead_id": lead_id,
        "generated_at": utc_now(),
        "business_name": name,
        "locked_business_name": "",
        "business_name_locked": False,
        "business_name_locked_at": None,
        "business_name_lock_reason": "",
        "website": website,
        "address": address,
        "phone": phone,
        "place_id": "",
        "map_url": "",
        "rating": cand.rating,
        "reviews": cand.review_count,

        "source_query": f"directory_discovery:{cand.source}",
        "source_search_job": {
            "mode": "directory_discovery",
            "city": city,
            "source": cand.source,
            "source_url": cand.source_url,
        },
        "matched_friction_evidence": [],
        "source_urls": {
            "website": website,
            "map_url": "",
            "evidence_urls": [cand.source_url],
        },
        "contacts": contacts,
        "primary_contact": primary_contact,
        "has_supported_contact_route": bool(primary_contact),
        "email": email_val,

        "lead": True,
        "rejection_reason": "",
        "lead_category": f"{primary_cat}_menu_translation",
        "establishment_profile": f"{primary_cat}_generic",
        "establishment_profile_evidence": [],
        "establishment_profile_confidence": "low",
        "establishment_profile_source_urls": [],
        "establishment_profile_override": "",
        "establishment_profile_override_note": "",
        "establishment_profile_override_at": None,

        "english_menu_issue": True,
        "english_menu_issue_evidence": "Assumed English menu gap for non-chain Japanese restaurant.",
        "ticket_machine_state": "unknown",
        "english_menu_state": "unknown",
        "menu_complexity_state": "medium",
        "izakaya_rules_state": "unknown",
        "tourist_exposure_score": 0.5,
        "lead_score_v1": 50,
        "recommended_primary_package": recommended_package,
        "package_recommendation_reason": package_reason,
        "custom_quote_reason": "",

        "evidence_classes": assessment.evidence_classes,
        "evidence_urls": [cand.source_url, website],
        "evidence_snippets": snippets[:20],
        "image_locked_evidence": False,
        "menu_evidence_found": assessment.menu_evidence_found,
        "machine_evidence_found": assessment.machine_evidence_found,
        "course_or_drink_plan_evidence_found": assessment.course_or_drink_plan_evidence_found,
        "evidence_strength_score": assessment.score,
        "lead_evidence_dossier": {},
        "proof_items": [],
        "launch_readiness_status": "ready_for_outreach",
        "launch_readiness_reasons": ["spray_and_pray_volume_strategy"],
        "message_variant": "",
        "launch_batch_id": "",
        "launch_outcome": {},

        "primary_category_v1": primary_cat,

        "pitch_draft": pitch,
        "pitch_available": bool(pitch),

        "production_inputs_needed": ["full_menu_photos"],
        "preview_available": preview_available,
        "preview_path": f"state/previews/{lead_id}/english-menu.html",
        "record_path": f"state/leads/{lead_id}.json",
        "review_status": "pending",

        "outreach_status": OUTREACH_STATUS_NEW,
        "outreach_classification": "spray_and_pray",
        "outreach_assets_selected": [],
        "outreach_asset_template_family": "none_contact_form",
        "outreach_sent_at": None,
        "outreach_draft_body": None,
        "outreach_include_inperson": city == "Tokyo",
        "status_history": [
            {"status": OUTREACH_STATUS_NEW, "timestamp": utc_now()},
        ],
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Bulk lead generation with preview + pitch")
    parser.add_argument("--cities", required=True, help="Comma-separated city list")
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--max-details", type=int, default=2000)
    parser.add_argument("--delay", type=float, default=0.3)
    args = parser.parse_args()

    cities = [c.strip() for c in args.cities.split(",") if c.strip()]

    fetcher = Fetcher()
    leads_created = 0
    candidates_seen = 0
    websites_fetched = 0
    chains_skipped = 0
    fetch_failures = 0
    no_email = 0
    seen_hosts: set[str] = set()
    state_root = PROJECT_ROOT / "state"

    print(f"Bulk Lead Generation (email-only, with preview + pitch)")
    print(f"  Cities: {', '.join(cities)}")
    print(f"  Max pages/area: {args.max_pages}")
    print(f"  Max details/city: {args.max_details}")
    print()

    for city in cities:
        print(f"\n--- Discovering candidates in {city} ---")
        start = time.time()

        try:
            candidates = discover_area_candidates(
                city=city,
                category="all",
                max_pages=args.max_pages,
                max_detail_fetches=args.max_details,
                delay_seconds=args.delay,
            )
        except Exception as exc:
            print(f"  Discovery failed for {city}: {exc}")
            continue

        elapsed = time.time() - start
        print(f"  Found {len(candidates)} candidates in {elapsed:.1f}s")

        for cand in candidates:
            candidates_seen += 1
            name = cand.name
            website = cand.website

            # Dedup by website host
            host = urllib.parse.urlparse(website).netloc.lower().removeprefix("www.")
            if host in seen_hosts:
                continue
            seen_hosts.add(host)

            # Skip chains
            if _is_chain(name):
                chains_skipped += 1
                continue

            # Skip existing leads
            existing = find_existing_lead(
                website=website,
                business_name=name,
                address=cand.address,
                phone=cand.phone,
                state_root=state_root,
            )
            if existing:
                continue

            # Fetch website
            print(f"  [{leads_created}] {name[:30]:<30} {website[:50]}", end="")
            websites_fetched += 1

            try:
                resp = fetcher.get(website, timeout=WEBSITE_TIMEOUT)
                if resp.status != 200:
                    print(f"  HTTP {resp.status}")
                    fetch_failures += 1
                    continue
                html = resp.html_content
            except Exception:
                print(f"  FETCH ERROR")
                fetch_failures += 1
                continue

            # Extract email — MUST have email
            # First check homepage, then probe contact paths
            signals = extract_contact_signals(html)
            usable_emails = [e for e in signals.emails if is_usable_business_email(e)]
            probe_hits = 0

            if not usable_emails:
                # Probe contact paths
                for path in _CONTACT_PROBE_PATHS:
                    if any(t in path.lower() for t in _EXCLUDED_PROBE_TOKENS):
                        continue
                    probe_url = website.rstrip("/") + path
                    try:
                        presp = fetcher.get(probe_url, timeout=6)
                        if presp.status != 200:
                            continue
                        probe_html = presp.html_content
                        probe_hits += 1
                        psig = extract_contact_signals(probe_html)
                        pemails = [e for e in psig.emails if is_usable_business_email(e)]
                        if pemails:
                            usable_emails = pemails
                            # Also accumulate any page text for evidence
                            html += "\n" + (probe_html or "")
                            break
                        if probe_hits >= 4:
                            break  # Don't probe more than 4 pages
                    except Exception:
                        continue

            if not usable_emails:
                print(f"  no email")
                no_email += 1
                continue

            email_val = usable_emails[0]
            print(f"  OK ({email_val})")

            # Build contacts
            contact_records = []
            for email in usable_emails:
                contact_records.append({
                    "type": "email", "value": email,
                    "actionable": True, "confidence": "high",
                    "source": "website", "status": "new",
                })
            normalised = normalise_lead_contacts({"contacts": contact_records})
            primary_contact = next((c for c in normalised if c.get("actionable")), None)

            # Extract evidence from website
            category = cand.category or "restaurant"
            payload = extract_page_payload(website, html)
            assessment = assess_evidence(
                business_name=name,
                website=website,
                category=category,
                payloads=[payload],
            )
            snippets = [s for s in (payload.get("text") or "").split("\n") if s.strip()][:20]

            # Build preview + pitch
            preview_available = False
            pitch: dict = {}
            try:
                result = _build_full_preview_html(
                    business_name=name,
                    category=category,
                    city=city,
                    email=email_val,
                    assessment=assessment,
                    snippets=snippets,
                    recommended_package=_package_for_category(
                        {"ramen": "ramen", "izakaya": "izakaya"}.get(category, "restaurant"),
                        city,
                    )[0],
                )
                if result:
                    preview_html, pitch = result
                    # Save preview to disk
                    area = _extract_area(cand.address)
                    name_slug = slugify(name)
                    short_hash = sha256_text(f"{name}{website}")[:4]
                    lead_id = f"wrm-{name_slug}-{area}-{short_hash}"
                    preview_dir = state_root / "previews" / lead_id
                    ensure_dir(preview_dir)
                    (preview_dir / "english-menu.html").write_text(preview_html, encoding="utf-8")
                    preview_available = True
            except Exception:
                pass  # Preview generation failed, lead still valid without it

            # Build and persist lead record
            record = _build_lead_record(
                cand=cand,
                contacts=normalised,
                primary_contact=primary_contact,
                email_val=email_val,
                assessment=assessment,
                snippets=snippets,
                pitch=pitch,
                preview_available=preview_available,
                city=city,
            )

            try:
                persist_lead_record(record, state_root=state_root)
                leads_created += 1
            except Exception as exc:
                print(f"  PERSIST ERROR: {exc}")

    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"  Candidates discovered:    {candidates_seen}")
    print(f"  Chains skipped:           {chains_skipped}")
    print(f"  Websites fetched:         {websites_fetched}")
    print(f"  Fetch failures:           {fetch_failures}")
    print(f"  No email:                 {no_email}")
    print(f"  Leads created:            {leads_created}")
    print(f"{'='*60}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
