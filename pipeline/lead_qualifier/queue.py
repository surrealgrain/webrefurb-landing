"""Three-phase lead qualification orchestrator.

Phase 1 — Menu Evidence:  directory_discovery → website crawl → evidence assessment
Phase 2 — Pain Signals:   review scraper → bilingual keyword analysis
Phase 3 — Contact:         email / contact form discovery (only for qualified leads)

Outputs a ranked outreach queue of QualifiedLeadEntry objects.

Reuses existing pipeline modules but does not modify them.
"""

from __future__ import annotations

import json
import time
from typing import Any

from .models import (
    PainSignalAssessment,
    QualifiedLeadEntry,
    ReviewScrapeResult,
)
from .pain_signals import assess_pain_signals
from .review_scraper import scrape_google_reviews


# ---------------------------------------------------------------------------
# Composite scoring weights
# ---------------------------------------------------------------------------
WEIGHT_PAIN = 0.40
WEIGHT_EVIDENCE = 0.25
WEIGHT_TOURIST = 0.20
WEIGHT_CONTACT = 0.15


def run_qualification_queue(
    *,
    city: str = "Tokyo",
    category: str = "all",
    max_candidates: int = 200,
    max_review_scrapes: int = 100,
    max_contact_crawls: int = 50,
    delay_seconds: float = 0.5,
    output_json: str | None = None,
    dry_run: bool = False,
    min_pain_score: int = 10,
) -> list[QualifiedLeadEntry]:
    """Run the full three-phase qualification queue.

    Returns a list of QualifiedLeadEntry sorted by composite_score descending.
    """
    if dry_run:
        return _dry_run_sample(city, category)

    # Phase 1: Discover candidates + menu evidence
    phase1 = _phase1_menu_evidence(
        city=city, category=category, max_candidates=max_candidates,
        delay_seconds=delay_seconds,
    )
    print(f"[queue] Phase 1: {len(phase1)} candidates with menu evidence")

    # Phase 2: Pain signal analysis via Google reviews
    phase2 = _phase2_pain_signals(
        phase1, max_scrapes=max_review_scrapes,
        min_pain_score=min_pain_score, delay_seconds=delay_seconds,
    )
    print(f"[queue] Phase 2: {len(phase2)} candidates with pain signals")

    # Phase 3: Contact discovery
    phase3 = _phase3_contact_discovery(
        phase2, max_crawls=max_contact_crawls, delay_seconds=delay_seconds,
    )
    print(f"[queue] Phase 3: {len(phase3)} candidates with contact info")

    # Rank the outreach queue
    ranked = _rank_outreach_queue(phase3)

    # Output
    if output_json:
        _write_json_output(ranked, output_json)

    return ranked


# ---------------------------------------------------------------------------
# Phase 1: Menu Evidence
# ---------------------------------------------------------------------------

def _phase1_menu_evidence(
    *,
    city: str,
    category: str,
    max_candidates: int,
    delay_seconds: float,
) -> list[QualifiedLeadEntry]:
    """Discover candidates from Tabelog, crawl websites, assess menu evidence."""
    from ..directory_discovery import discover_area_candidates
    from ..evidence import assess_evidence, classify_primary_category, is_chain_business
    from ..html_parser import extract_page_payload

    # Pull candidates from directory_discovery
    candidates = discover_area_candidates(
        city=city, category=category, max_pages=50,
        delay_seconds=delay_seconds,
    )

    # Pre-filter: only keep candidates Tabelog tagged as ramen or izakaya
    candidates = [
        c for c in candidates
        if c.category in ("ramen", "izakaya")
    ]
    candidates = candidates[:max_candidates]

    results: list[QualifiedLeadEntry] = []
    for cand in candidates:
        try:
            # Skip chains
            if is_chain_business(cand.name):
                continue

            # Skip if no website
            if not cand.website:
                continue

            # Fetch website
            website_html = _fetch_website_html(cand.website)
            if not website_html:
                continue

            # Extract payload + assess evidence
            payload = extract_page_payload(cand.website, website_html)
            evidence = assess_evidence(
                business_name=cand.name,
                website=cand.website,
                category=cand.category or category,
                payloads=[payload],
            )

            # Filter: must have menu or machine evidence
            if not evidence.menu_evidence_found and not evidence.machine_evidence_found:
                continue

            # Category: trust Tabelog genre tag first, fall back to text classification
            if cand.category in ("ramen", "izakaya"):
                primary = cand.category
            else:
                primary = classify_primary_category(
                    payload.get("text", ""), cand.category or category
                )
                if primary not in ("ramen", "izakaya"):
                    continue

            entry = QualifiedLeadEntry(
                business_name=cand.name,
                website=cand.website,
                address=cand.address,
                phone=cand.phone,
                category=primary,
                city=city,
                source=cand.source or "tabelog",
                source_url=cand.source_url,
                rating=cand.rating,
                review_count=cand.review_count,
                menu_evidence_found=evidence.menu_evidence_found,
                machine_evidence_found=evidence.machine_evidence_found,
                evidence_score=evidence.score,
                evidence_classes=evidence.evidence_classes,
                evidence_urls=evidence.evidence_urls,
                english_availability=_infer_english_availability(evidence),
                qualification_phases_passed=["menu_evidence"],
            )
            results.append(entry)

        except Exception:
            continue

        time.sleep(delay_seconds)

    return results


# ---------------------------------------------------------------------------
# Phase 2: Pain Signal Analysis
# ---------------------------------------------------------------------------

def _phase2_pain_signals(
    leads: list[QualifiedLeadEntry],
    *,
    max_scrapes: int,
    min_pain_score: int,
    delay_seconds: float,
) -> list[QualifiedLeadEntry]:
    """Scrape Google reviews + assess pain signals."""
    qualified: list[QualifiedLeadEntry] = []
    scrapes_done = 0

    for lead in leads:
        if scrapes_done >= max_scrapes:
            break

        try:
            # Scrape reviews
            review_result = scrape_google_reviews(
                business_name=lead.business_name,
                address=lead.address,
                city=lead.city,
                max_reviews=50,
            )
            scrapes_done += 1

            # Assess pain signals
            website_text = _fetch_website_text(lead.website)
            pain = assess_pain_signals(
                business_name=lead.business_name,
                website_text=website_text,
                review_scrape_result=review_result,
                evidence_classes=lead.evidence_classes,
                english_availability=lead.english_availability,
                machine_evidence_found=lead.machine_evidence_found,
            )

            # Filter by pain threshold
            if not pain.has_pain_signals or pain.pain_score < min_pain_score:
                continue

            updated = _update_entry(
                lead,
                pain_assessment=pain,
                review_scrape_result=review_result,
                qualification_phases_passed=lead.qualification_phases_passed + ["pain_signals"],
            )
            qualified.append(updated)

        except Exception:
            continue

        time.sleep(delay_seconds)

    return qualified


# ---------------------------------------------------------------------------
# Phase 3: Contact Discovery
# ---------------------------------------------------------------------------

def _phase3_contact_discovery(
    leads: list[QualifiedLeadEntry],
    *,
    max_crawls: int,
    delay_seconds: float,
) -> list[QualifiedLeadEntry]:
    """Discover contact info for qualified leads.

    Uses extract_contact_signals (synchronous, HTML-based) instead of the
    async Playwright-based recover_contact_routes. Probes the homepage and
    common contact paths (/contact, /inquiry, /otoiawase).
    """
    from ..contact_crawler import (
        contact_candidate_urls,
        extract_contact_signals,
        is_usable_business_email,
    )

    results: list[QualifiedLeadEntry] = []
    crawls_done = 0

    for lead in leads:
        emails: list[str] = []
        has_form = False
        form_url = ""

        if crawls_done < max_crawls and lead.website:
            try:
                # Phase 1: Check homepage
                homepage_html = _fetch_website_html(lead.website)
                if homepage_html:
                    signals = extract_contact_signals(homepage_html)
                    emails = [
                        e for e in signals.emails
                        if is_usable_business_email(e)
                    ]
                    if signals.has_form:
                        has_form = True
                        form_url = lead.website

                    # Phase 2: Probe contact paths from homepage links
                    if not emails and not has_form:
                        from ..html_parser import extract_page_payload
                        homepage_payload = extract_page_payload(lead.website, homepage_html)
                        candidate_urls = contact_candidate_urls(
                            lead.website, homepage_payload.get("links", [])
                        )
                        for contact_url in candidate_urls[:3]:
                            contact_html = _fetch_website_html(contact_url)
                            if contact_html:
                                contact_signals = extract_contact_signals(contact_html)
                                if not emails:
                                    emails = [
                                        e for e in contact_signals.emails
                                        if is_usable_business_email(e)
                                    ]
                                if not has_form and contact_signals.has_form:
                                    has_form = True
                                    form_url = contact_url
                                if emails:
                                    break

                crawls_done += 1
            except Exception:
                pass

        updated = _update_entry(
            lead,
            contact_emails=emails,
            has_contact_form=has_form,
            contact_form_url=form_url,
            qualification_phases_passed=lead.qualification_phases_passed + ["contact_discovery" if emails or has_form else "contact_skipped"],
        )
        results.append(updated)

        time.sleep(delay_seconds)

    return results


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def _rank_outreach_queue(leads: list[QualifiedLeadEntry]) -> list[QualifiedLeadEntry]:
    """Rank leads by composite score and assign outreach priority."""
    from ..scoring import compute_tourist_exposure_score

    scored: list[QualifiedLeadEntry] = []
    for lead in leads:
        try:
            tourist = compute_tourist_exposure_score(
                address=lead.address,
                rating=lead.rating,
                reviews=lead.review_count,
            )
        except Exception:
            tourist = 0.0

        pain_score = (lead.pain_assessment.pain_score if lead.pain_assessment else 0) / 100.0
        evidence_score = lead.evidence_score / 100.0
        contact_score = _contact_quality_score(lead) / 100.0

        composite = (
            WEIGHT_PAIN * pain_score
            + WEIGHT_EVIDENCE * evidence_score
            + WEIGHT_TOURIST * tourist
            + WEIGHT_CONTACT * contact_score
        ) * 100

        updated = _update_entry(
            lead,
            composite_score=composite,
            tourist_exposure=tourist,
            qualification_phases_passed=lead.qualification_phases_passed,
        )
        scored.append(updated)

    # Sort descending by composite score
    scored.sort(key=lambda e: e.composite_score, reverse=True)

    # Assign priority
    final: list[QualifiedLeadEntry] = []
    for i, entry in enumerate(scored):
        final.append(_update_entry(entry, outreach_priority=i + 1))

    return final


def _contact_quality_score(lead: QualifiedLeadEntry) -> float:
    """Contact quality: email=100, contact_form=60, none=0."""
    if lead.contact_emails:
        return 100.0
    if lead.has_contact_form:
        return 60.0
    return 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_website_html(url: str) -> str:
    """Fetch website HTML using Scrapling Fetcher."""
    if not url:
        return ""
    try:
        from scrapling import Fetcher
        fetcher = Fetcher(auto_match=False)
        response = fetcher.get(url, timeout=10)
        if not response or response.status != 200:
            return ""
        content = response.html_content
        return content if content else ""
    except Exception:
        return ""


def _fetch_website_text(url: str) -> str:
    """Fetch website and return visible text only."""
    html = _fetch_website_html(url)
    if not html:
        return ""
    # Strip HTML tags roughly — good enough for keyword scanning
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:5000]  # Cap for performance


def _infer_english_availability(evidence: Any) -> str:
    """Infer english_availability string from an EvidenceAssessment."""
    classes = evidence.evidence_classes or []
    if any("english" in c.lower() for c in classes):
        if "english_menu_present" in classes or "clear_english" in classes:
            return "clear_usable"
        return "incomplete"
    if "image_locked_menu" in classes:
        return "image_only"
    return "missing"


def _update_entry(entry: QualifiedLeadEntry, **overrides: Any) -> QualifiedLeadEntry:
    """Create a new QualifiedLeadEntry with updated fields."""
    data = {
        "business_name": entry.business_name,
        "website": entry.website,
        "address": entry.address,
        "phone": entry.phone,
        "category": entry.category,
        "city": entry.city,
        "source": entry.source,
        "source_url": entry.source_url,
        "rating": entry.rating,
        "review_count": entry.review_count,
        "menu_evidence_found": entry.menu_evidence_found,
        "machine_evidence_found": entry.machine_evidence_found,
        "evidence_score": entry.evidence_score,
        "evidence_classes": entry.evidence_classes,
        "evidence_urls": entry.evidence_urls,
        "english_availability": entry.english_availability,
        "pain_assessment": entry.pain_assessment,
        "review_scrape_result": entry.review_scrape_result,
        "contact_emails": entry.contact_emails,
        "has_contact_form": entry.has_contact_form,
        "contact_form_url": entry.contact_form_url,
        "composite_score": entry.composite_score,
        "tourist_exposure": entry.tourist_exposure,
        "recommended_package": entry.recommended_package,
        "outreach_priority": entry.outreach_priority,
        "qualification_phases_passed": entry.qualification_phases_passed,
        "rejection_reason": entry.rejection_reason,
    }
    data.update(overrides)
    return QualifiedLeadEntry(**data)


def _write_json_output(leads: list[QualifiedLeadEntry], path: str) -> None:
    """Write qualified leads to JSON file."""
    data = [lead.to_dict() for lead in leads]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def _dry_run_sample(city: str, category: str) -> list[QualifiedLeadEntry]:
    """Return sample structure for dry run."""
    return [
        QualifiedLeadEntry(
            business_name="(dry run sample)",
            website="https://example.com",
            city=city,
            category=category,
            qualification_phases_passed=["dry_run"],
        )
    ]
