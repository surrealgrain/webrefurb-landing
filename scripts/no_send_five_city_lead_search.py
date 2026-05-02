#!/usr/bin/env python3
"""Run the no-send five-city email inventory search.

The runner uses the Codex email-first search jobs and persists only
manual-review-blocked lead inventory. It never sends email or submits forms.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scrapling import Fetcher

from pipeline.contact_crawler import (
    contact_candidate_urls_from_html,
    extract_contact_signals,
    is_usable_business_email,
    normalize_website_url,
)
from pipeline.directory_discovery import (
    DirectoryCandidate,
    crawl_tabelog_listing_page,
    tabelog_sub_area_paths_for_city,
)
from pipeline.evidence import is_chain_business
from pipeline.models import QualificationResult
from pipeline.pitch_cards import apply_pitch_card_state, pitch_card_counts
from pipeline.qualification import qualify_candidate
from pipeline.record import create_lead_record, find_existing_lead, list_leads, normalise_lead_contacts, persist_lead_record
from pipeline.search import codex_search_and_qualify, search_and_qualify
from pipeline.search_scope import codex_search_jobs_for_scope, search_jobs_for_scope
from pipeline.utils import ensure_dir, load_project_env, read_json, utc_now, write_json
from pipeline.constants import (
    LEAD_CATEGORY_IZAKAYA_MENU_TRANSLATION,
    LEAD_CATEGORY_RAMEN_MENU_TRANSLATION,
    PACKAGE_1_KEY,
)

logging.getLogger().setLevel(logging.ERROR)
logging.getLogger("scrapling").setLevel(logging.ERROR)


DEFAULT_CITIES = ("Tokyo", "Osaka", "Kyoto", "Sapporo", "Fukuoka")
DEFAULT_CATEGORIES = (
    "ramen",
    "tsukemen",
    "abura_soba",
    "mazesoba",
    "tantanmen",
    "chuka_soba",
    "izakaya",
    "yakitori",
    "kushiyaki",
    "yakiton",
    "tachinomi",
    "oden",
    "kushikatsu",
    "kushiage",
    "robatayaki",
    "seafood_izakaya",
    "sakaba",
)

CHAIN_REASONS = {
    "chain_business",
    "chain_or_franchise_infrastructure",
    "chain_or_franchise_like_business",
}
INVALID_ARTIFACT_REASONS = {
    "invalid_business_name_detected",
    "invalid_email_artifact",
    "non_restaurant_page_title",
}
DIRECTORY_RECOVERABLE_REASONS = {
    "non_ramen_izakaya_v1",
    "no_menu_or_product_evidence",
    "insufficient_category_evidence",
    "negative_evidence_score",
}
DIRECTORY_HARD_SCOPE_REASONS = {
    "already_has_good_english_menu",
    "already_has_multilingual_ordering_solution",
    "already_solved_solution_check",
    "excluded_business_type_v1",
    "not_in_japan",
    "no_physical_location_evidence",
}

DIRECTORY_CATEGORIES = ("ramen", "izakaya")
CONTACT_PROBE_PATHS = (
    "/contact/",
    "/contact",
    "/contact.html",
    "/contact/index.html",
    "/contact-us/",
    "/contact-us",
    "/inquiry/",
    "/inquiry",
    "/inquiry.html",
    "/inquiry/index.html",
    "/otoiawase/",
    "/otoiawase",
    "/otoiawase.html",
    "/toiawase/",
    "/toiawase",
    "/mail/",
    "/mail",
    "/mailform/",
    "/mailform",
    "/form/",
    "/form",
    "/reservation/",
    "/reserve/",
    "/access/",
    "/info/",
    "/about/",
    "/shop/",
)


def _new_bucket() -> dict[str, Any]:
    return {
        "jobs_attempted": 0,
        "search_failures": 0,
        "candidates_searched": 0,
        "usable_emails_found": 0,
        "new_records_persisted": 0,
        "duplicates_skipped": 0,
        "hard_blocked_chains_operators": 0,
        "hard_blocked_invalid_emails_artifacts": 0,
        "review_blocked_ambiguous_records": 0,
        "reason_counts": Counter(),
    }


def _normalise_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    normalised = dict(bucket)
    normalised["reason_counts"] = dict(bucket.get("reason_counts") or {})
    return normalised


def _update_bucket(bucket: dict[str, Any], result: dict[str, Any]) -> None:
    decisions = list(result.get("decisions") or [])
    bucket["jobs_attempted"] += 1
    bucket["candidates_searched"] += int(result.get("total_candidates") or 0)
    email_hits = sum(1 for decision in decisions if decision.get("email_found") or decision.get("email"))
    bucket["usable_emails_found"] += email_hits or int(result.get("leads") or 0)
    bucket["new_records_persisted"] += int(result.get("leads") or 0)
    bucket["review_blocked_ambiguous_records"] += int(result.get("leads") or 0)
    for decision in decisions:
        reason = str(decision.get("reason") or decision.get("rejection_reason") or "").strip() or "qualified_or_unclassified"
        bucket["reason_counts"][reason] += 1
        if reason == "search_failed":
            bucket["search_failures"] += 1
        if reason == "already_tracked":
            bucket["duplicates_skipped"] += 1
        if reason in CHAIN_REASONS:
            bucket["hard_blocked_chains_operators"] += 1
        if reason in INVALID_ARTIFACT_REASONS:
            bucket["hard_blocked_invalid_emails_artifacts"] += 1


def _run_directory_mode(
    *,
    cities: list[str],
    state_root: Path,
    max_pages: int,
    timeout: int,
    delay: float,
    workers: int,
    resume: bool,
    checkpoint_path: Path,
    summary_path: Path | None,
    target_reviewable_cards: int,
    directory_scope: str = "city",
) -> dict[str, Any]:
    checkpoint = _load_checkpoint(checkpoint_path) if resume else _new_checkpoint()
    dedup = _existing_dedup_keys(state_root)
    records = list_leads(state_root=state_root)
    initial_counts = pitch_card_counts(records)

    started_at = utc_now()
    summary: dict[str, Any] = {
        "started_at": started_at,
        "completed_at": "",
        "engine": "directory",
        "no_send": True,
        "max_candidates": 0,
        "target_reviewable_cards": target_reviewable_cards,
        "directory_scope": directory_scope,
        "initial_pitch_card_counts": initial_counts,
        "final_pitch_card_counts": {},
        "totals": _directory_bucket(),
        "by_city_category": {},
        "exhausted": {},
        "checkpoint_path": str(checkpoint_path),
    }

    for city, area_path in _directory_scope_units(cities, directory_scope):
        for category in DIRECTORY_CATEGORIES:
            key = _directory_scope_key(city=city, category=category, area_path=area_path)
            bucket = summary["by_city_category"].setdefault(key, _directory_bucket())
            for page in range(1, max_pages + 1):
                if _openable_count(state_root) >= target_reviewable_cards:
                    summary["exhausted"][key] = False
                    _save_directory_summary(summary, state_root=state_root, summary_path=summary_path, started_at=started_at)
                    return summary
                if _page_done(checkpoint, key, page):
                    bucket["pages_skipped_resume"] += 1
                    continue

                page_result = crawl_tabelog_listing_page(
                    city=city,
                    category=category,
                    page=page,
                    area_path=area_path or None,
                    timeout=timeout,
                    delay_seconds=delay,
                )
                bucket["pages_searched"] += 1
                summary["totals"]["pages_searched"] += 1
                if page_result.exhausted:
                    summary["exhausted"][key] = True
                    _mark_page_done(checkpoint, key, page)
                    _write_checkpoint(checkpoint_path, checkpoint)
                    break

                candidates = [
                    candidate for candidate in page_result.candidates
                    if not _dedup_candidate(candidate, dedup)
                ]
                duplicate_count = page_result.listing_count - len(candidates)
                bucket["candidates_searched"] += page_result.listing_count
                bucket["duplicates_skipped"] += max(0, duplicate_count)
                summary["totals"]["candidates_searched"] += page_result.listing_count
                summary["totals"]["duplicates_skipped"] += max(0, duplicate_count)

                with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
                    futures = [
                        executor.submit(
                            _process_directory_candidate,
                            candidate,
                            state_root,
                            timeout,
                        )
                        for candidate in candidates
                    ]
                    for future in as_completed(futures):
                        result = future.result()
                        _merge_directory_result(bucket, result)
                        _merge_directory_result(summary["totals"], result)
                        if result.get("record"):
                            _add_dedup_record(result["record"], dedup)

                _mark_page_done(checkpoint, key, page)
                checkpoint["updated_at"] = utc_now()
                _write_checkpoint(checkpoint_path, checkpoint)
                print(json.dumps({
                    "city": city,
                    "category": category,
                    "area_path": area_path or "city_wide",
                    "page": page,
                    **bucket,
                }, ensure_ascii=False))
                sys.stdout.flush()

    _save_directory_summary(summary, state_root=state_root, summary_path=summary_path, started_at=started_at)
    return summary


def _process_directory_candidate(candidate: DirectoryCandidate, state_root: Path, timeout: int) -> dict[str, Any]:
    result = _directory_bucket()
    result["candidates_searched"] = 1
    if is_chain_business(candidate.name):
        result["hard_blocked_chains_operators"] = 1
        return result

    existing = find_existing_lead(
        website=candidate.website,
        business_name=candidate.name,
        address=candidate.address,
        phone=candidate.phone,
        state_root=state_root,
    )
    if existing:
        result["duplicates_skipped"] = 1
        return result

    fetcher = Fetcher()
    try:
        response = fetcher.get(candidate.website, timeout=timeout)
        if response.status != 200:
            result["fetch_failures"] = 1
            return result
        html = response.html_content
    except Exception:
        result["fetch_failures"] = 1
        return result

    usable_emails, email_source_url, contact_form_url, contact_form_signal = _find_candidate_routes(fetcher, candidate.website, html, timeout=timeout)
    if not usable_emails and not contact_form_url:
        result["no_supported_route"] = 1
        return result
    result["usable_routes_found"] = len(usable_emails) if usable_emails else 1

    qualification = qualify_candidate(
        business_name=candidate.name,
        website=candidate.website,
        category=candidate.category or "ramen",
        pages=[{"url": candidate.website, "html": html}],
        rating=candidate.rating,
        reviews=candidate.review_count,
        address=candidate.address,
        phone=candidate.phone,
    )
    recovered_rejection_reason = ""
    if not qualification.lead:
        reason = str(qualification.rejection_reason or "")
        if reason in CHAIN_REASONS:
            result["hard_blocked_chains_operators"] = 1
            return result
        elif reason in INVALID_ARTIFACT_REASONS:
            result["hard_blocked_invalid_emails_artifacts"] = 1
            return result
        elif _directory_rejection_is_recoverable(reason, candidate):
            recovered_rejection_reason = reason
            qualification = _recover_directory_review_qualification(
                candidate=candidate,
                qualification=qualification,
                rejection_reason=reason,
            )
        else:
            result["hard_blocked_scope"] = 1
            return result

    raw_contacts: list[dict[str, Any]] = [
        {
            "type": "email",
            "value": email,
            "href": f"mailto:{email}",
            "label": "Directory-discovered email",
            "source": "directory_official_site_probe",
            "source_url": email_source_url,
            "confidence": "medium",
            "discovered_at": utc_now(),
            "status": "needs_review",
            "actionable": True,
        }
        for email in usable_emails
    ]
    if contact_form_url:
        raw_contacts.append({
            "type": "contact_form",
            "value": contact_form_url,
            "href": contact_form_url,
            "label": "Contact form",
            "source": "directory_official_site_probe",
            "source_url": contact_form_url,
            "confidence": "medium",
            "discovered_at": utc_now(),
            "status": "needs_review",
            "actionable": True,
            "contact_form_profile": "supported_inquiry",
            "required_fields": contact_form_signal.get("required_fields") or [],
            "form_field_names": contact_form_signal.get("form_field_names") or [],
            "form_actions": contact_form_signal.get("form_actions") or [],
        })
    contacts = normalise_lead_contacts({"contacts": raw_contacts})
    record = create_lead_record(
        qualification=qualification,
        preview_html="",
        pitch_draft={},
        contacts=contacts,
        source_query="directory_pitch_card_crawl",
        source_search_job={
            "mode": "directory",
            "source": candidate.source,
            "source_url": candidate.source_url,
            "city": candidate.city,
            "category": candidate.category,
        },
        matched_friction_evidence=[],
        state_root=state_root,
    )
    record.update({
        "city": candidate.city,
        "category": qualification.primary_category_v1,
        "email_source_url": email_source_url if usable_emails else "",
        "email_source": "directory_official_site_probe" if usable_emails else "",
        "contact_form_url": contact_form_url,
        "source_url": candidate.source_url,
        "source_strength": "official_site",
        "source_strength_reason": "Official website from Tabelog detail page.",
        "recovered_directory_rejection_reason": recovered_rejection_reason,
        "manual_review_required": True,
        "inventory_review_status": "review_blocked",
        "inventory_review_reason": "directory_pitch_card_requires_manual_review_before_outreach",
        "candidate_inbox_status": "needs_scope_review" if recovered_rejection_reason else "needs_email_review",
        "pitch_ready": False,
        "pitch_available": True,
        "preview_available": True,
        "outreach_status": "needs_review",
        "outreach_classification": "directory_pitch_card_review",
        "email_verification_status": "needs_review",
        "email_verification_reason": "directory-discovered email needs operator confirmation" if usable_emails else "contact form route needs operator confirmation",
        "name_verification_status": "single_source",
        "name_verification_reason": "directory-discovered name has one source",
        "category_verification_status": "needs_review" if recovered_rejection_reason else "verified",
        "category_verification_reason": (
            f"recoverable directory scope review: {recovered_rejection_reason}"
            if recovered_rejection_reason
            else f"{qualification.primary_category_v1} category from Tabelog/detail-page evidence"
        ),
        "city_verification_status": "verified",
        "city_verification_reason": f"city from directory crawl: {candidate.city}",
        "english_menu_check_status": "no_hard_reject",
        "english_menu_check_reason": "no hard English-menu reject found during crawl",
        "chain_verification_status": "clear",
        "chain_verification_reason": "no chain/franchise reject signal recorded",
        "verification_status": "needs_review",
        "verification_reason": "directory pitch-card candidate requires manual review",
    })
    apply_pitch_card_state(record)
    persist_lead_record(record, state_root=state_root)
    result["new_records_persisted"] = 1
    result["review_blocked_ambiguous_records"] = 1
    result["record"] = record
    return result


def _directory_rejection_is_recoverable(reason: str, candidate: DirectoryCandidate) -> bool:
    """Return True when a no-send card should be saved for operator review."""
    category = str(candidate.category or "").strip().lower()
    if category not in {"ramen", "izakaya"}:
        return False
    if reason in DIRECTORY_HARD_SCOPE_REASONS:
        return False
    return reason in DIRECTORY_RECOVERABLE_REASONS


def _recover_directory_review_qualification(
    *,
    candidate: DirectoryCandidate,
    qualification: QualificationResult,
    rejection_reason: str,
) -> QualificationResult:
    category = str(candidate.category or "").strip().lower()
    if category not in {"ramen", "izakaya"}:
        category = "ramen"
    lead_category = (
        LEAD_CATEGORY_RAMEN_MENU_TRANSLATION
        if category == "ramen"
        else LEAD_CATEGORY_IZAKAYA_MENU_TRANSLATION
    )
    establishment_profile = "ramen_only" if category == "ramen" else "izakaya_food_and_drinks"
    evidence_classes = _ordered_unique([
        *(qualification.evidence_classes or []),
        "directory_supported_route",
        "recoverable_directory_scope_review",
    ])
    evidence_urls = _ordered_unique([
        *(qualification.evidence_urls or []),
        candidate.source_url,
        candidate.website,
    ])
    lead_signals = _ordered_unique([
        *(qualification.lead_signals or []),
        "supported_contact_route_found",
        "directory_category_requires_review",
        "english_menu_gap_unconfirmed",
    ])
    snippets = _ordered_unique([
        *(qualification.evidence_snippets or []),
        f"Tabelog {category} listing supplied official site/contact route; qualification needs manual review: {rejection_reason}",
    ])
    return replace(
        qualification,
        lead=True,
        rejection_reason=None,
        address=candidate.address,
        phone=candidate.phone,
        rating=candidate.rating,
        reviews=candidate.review_count,
        primary_category_v1=category,
        lead_category=lead_category,
        establishment_profile=establishment_profile,
        establishment_profile_evidence=[f"directory_category:{category}", f"recoverable_reason:{rejection_reason}"],
        establishment_profile_confidence="low",
        establishment_profile_source_urls=[candidate.source_url] if candidate.source_url else [],
        lead_signals=lead_signals,
        evidence_classes=evidence_classes,
        evidence_urls=evidence_urls,
        evidence_snippets=snippets[:8],
        english_availability=qualification.english_availability or "unknown",
        english_menu_issue=bool(qualification.english_menu_issue),
        menu_complexity_state="medium" if category == "izakaya" else "simple",
        izakaya_rules_state="unknown" if category == "izakaya" else "none_found",
        launch_readiness_status="manual_review",
        launch_readiness_reasons=[f"recoverable_directory_scope_review:{rejection_reason}", "manual_review_required"],
        recommended_primary_package=qualification.recommended_primary_package or PACKAGE_1_KEY,
        package_recommendation_reason=qualification.package_recommendation_reason or "Directory pitch-card review candidate.",
        decision_reason=f"Recovered for no-send pitch-card review after {rejection_reason}.",
        false_positive_risk="high",
        preview_available=True,
        pitch_available=True,
    )


def _find_candidate_routes(fetcher: Fetcher, website: str, html: str, *, timeout: int) -> tuple[list[str], str, str, dict[str, Any]]:
    signals = extract_contact_signals(html)
    usable = [email for email in signals.emails if is_usable_business_email(email)]
    form_url = website if _supported_form(signals) else ""
    form_signal = _signal_dict(signals) if form_url else {}
    if usable:
        return usable, website, form_url, form_signal

    linked_probe_urls = contact_candidate_urls_from_html(website, html, limit=10)
    path_probe_urls = [
        normalize_website_url(website.rstrip("/") + path)
        for path in CONTACT_PROBE_PATHS
    ]
    for probe_url in _ordered_unique([*linked_probe_urls, *path_probe_urls]):
        if not probe_url:
            continue
        try:
            response = fetcher.get(probe_url, timeout=max(3, min(timeout, 6)))
            if response.status != 200:
                continue
            probe_signals = extract_contact_signals(response.html_content)
        except Exception:
            continue
        usable = [email for email in probe_signals.emails if is_usable_business_email(email)]
        if usable:
            return usable, probe_url, probe_url if _supported_form(probe_signals) else form_url, _signal_dict(probe_signals)
        if not form_url and _supported_form(probe_signals):
            form_url = probe_url
            form_signal = _signal_dict(probe_signals)
    return [], website, form_url, form_signal


def _ordered_unique(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if value in (None, "", []):
            continue
        if value not in result:
            result.append(value)
    return result


def _supported_form(signals: Any) -> bool:
    return bool(getattr(signals, "has_form", False) and getattr(signals, "contact_form_profile", "") == "supported_inquiry")


def _signal_dict(signals: Any) -> dict[str, Any]:
    return {
        "required_fields": list(getattr(signals, "required_fields", []) or []),
        "form_field_names": list(getattr(signals, "form_field_names", []) or []),
        "form_actions": list(getattr(signals, "form_actions", []) or []),
    }


def _directory_bucket() -> dict[str, Any]:
    return {
        "pages_searched": 0,
        "pages_skipped_resume": 0,
        "candidates_searched": 0,
        "usable_routes_found": 0,
        "new_records_persisted": 0,
        "duplicates_skipped": 0,
        "hard_blocked_chains_operators": 0,
        "hard_blocked_invalid_emails_artifacts": 0,
        "hard_blocked_scope": 0,
        "review_blocked_ambiguous_records": 0,
        "fetch_failures": 0,
        "no_supported_route": 0,
    }


def _directory_scope_units(cities: list[str], directory_scope: str) -> list[tuple[str, str]]:
    units: list[tuple[str, str]] = []
    for city in cities:
        if directory_scope in {"city", "both"}:
            units.append((city, ""))
        if directory_scope in {"subarea", "both"}:
            subareas = tabelog_sub_area_paths_for_city(city)
            if subareas:
                units.extend((city, area_path) for area_path in subareas)
            elif directory_scope == "subarea":
                units.append((city, ""))
    return units


def _directory_scope_key(*, city: str, category: str, area_path: str) -> str:
    scope = area_path or "city"
    return f"{city}:{category}:{scope}"


def _merge_directory_result(bucket: dict[str, Any], result: dict[str, Any]) -> None:
    for key in _directory_bucket():
        bucket[key] = int(bucket.get(key) or 0) + int(result.get(key) or 0)


def _load_checkpoint(path: Path) -> dict[str, Any]:
    return read_json(path, default=_new_checkpoint()) or _new_checkpoint()


def _new_checkpoint() -> dict[str, Any]:
    return {"version": 1, "completed_pages": {}, "completed_jobs": [], "updated_at": utc_now()}


def _page_done(checkpoint: dict[str, Any], key: str, page: int) -> bool:
    return int(page) in {int(value) for value in checkpoint.get("completed_pages", {}).get(key, [])}


def _mark_page_done(checkpoint: dict[str, Any], key: str, page: int) -> None:
    pages = set(int(value) for value in checkpoint.setdefault("completed_pages", {}).setdefault(key, []))
    pages.add(int(page))
    checkpoint["completed_pages"][key] = sorted(pages)


def _job_done(checkpoint: dict[str, Any], job_key: str) -> bool:
    return job_key in {str(value) for value in checkpoint.get("completed_jobs", [])}


def _mark_job_done(checkpoint: dict[str, Any], job_key: str) -> None:
    jobs = {str(value) for value in checkpoint.setdefault("completed_jobs", [])}
    jobs.add(job_key)
    checkpoint["completed_jobs"] = sorted(jobs)


def _write_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    write_json(path, checkpoint)


def _save_directory_summary(summary: dict[str, Any], *, state_root: Path, summary_path: Path | None, started_at: str) -> None:
    summary["completed_at"] = utc_now()
    summary["final_pitch_card_counts"] = pitch_card_counts(list_leads(state_root=state_root))
    output = summary_path or state_root / "lead_imports" / f"five_city_directory_pitch_cards_{started_at.replace(':', '').replace('-', '').replace('+00:00', 'z').lower()}.json"
    write_json(output, summary)
    summary["summary_path"] = str(output)


def _openable_count(state_root: Path) -> int:
    return pitch_card_counts(list_leads(state_root=state_root)).get("reviewable_pitch_cards", 0)


def _save_generic_summary(summary: dict[str, Any], *, state_root: Path, output: Path) -> None:
    summary["completed_at"] = utc_now()
    summary["final_pitch_card_counts"] = pitch_card_counts(list_leads(state_root=state_root))
    summary["totals"] = _normalise_bucket(summary["totals"])
    summary["by_city"] = {city: _normalise_bucket(bucket) for city, bucket in summary["by_city"].items()}
    summary["by_city_category"] = {
        key: _normalise_bucket(bucket) for key, bucket in summary["by_city_category"].items()
    }
    ensure_dir(output.parent)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["summary_path"] = str(output)


def _existing_dedup_keys(state_root: Path) -> dict[str, set[str]]:
    keys = {"emails": set(), "hosts": set(), "phones": set(), "name_address": set(), "source_urls": set()}
    for record in list_leads(state_root=state_root):
        _add_dedup_record(record, keys)
    return keys


def _result_is_search_failure(result: dict[str, Any]) -> bool:
    decisions = result.get("decisions") or []
    return bool(decisions) and all(
        str(decision.get("reason") or "") == "search_failed"
        for decision in decisions
        if isinstance(decision, dict)
    )


def _add_dedup_record(record: dict[str, Any], keys: dict[str, set[str]]) -> None:
    email = str(record.get("email") or "").strip().lower()
    if email:
        keys["emails"].add(email)
    host = _host(str(record.get("website") or ""))
    if host:
        keys["hosts"].add(host)
    phone = "".join(ch for ch in str(record.get("phone") or "") if ch.isdigit())
    if phone:
        keys["phones"].add(phone)
    name = "".join(str(record.get("business_name") or "").split()).lower()
    address = "".join(str(record.get("address") or "").split()).lower()
    if name and address:
        keys["name_address"].add(f"{name}|{address}")
    for value in (record.get("source_url"), record.get("codex_tabelog_url")):
        if value:
            keys["source_urls"].add(str(value))
    source_urls = record.get("source_urls") or {}
    if isinstance(source_urls, dict):
        for value in source_urls.values():
            if isinstance(value, str) and value:
                keys["source_urls"].add(value)


def _dedup_candidate(candidate: DirectoryCandidate, keys: dict[str, set[str]]) -> bool:
    host = _host(candidate.website)
    if host and host in keys["hosts"]:
        return True
    phone = "".join(ch for ch in str(candidate.phone or "") if ch.isdigit())
    if phone and phone in keys["phones"]:
        return True
    name = "".join(str(candidate.name or "").split()).lower()
    address = "".join(str(candidate.address or "").split()).lower()
    if name and address and f"{name}|{address}" in keys["name_address"]:
        return True
    if candidate.source_url and candidate.source_url in keys["source_urls"]:
        return True
    return False


def _host(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def main() -> int:
    load_project_env()

    parser = argparse.ArgumentParser(description="No-send five-city restaurant email inventory search")
    parser.add_argument("--cities", default=",".join(DEFAULT_CITIES))
    parser.add_argument("--categories", default=",".join(DEFAULT_CATEGORIES))
    parser.add_argument("--provider", default=os.environ.get("WEBREFURB_SEARCH_PROVIDER") or ("serper" if os.environ.get("SERPER_API_KEY") else "webserper"))
    parser.add_argument(
        "--mode",
        choices=["directory", "maps", "codex-tabelog", "codex-all"],
        default="directory",
        help="directory is the checkpointed Tabelog/official-site crawler; maps uses physical-place searches; codex-tabelog uses Tabelog email jobs; codex-all also includes broad platform jobs.",
    )
    parser.add_argument("--delay", type=float, default=0.05)
    parser.add_argument("--max-jobs", type=int, default=0, help="Debug cap; 0 means all generated jobs")
    parser.add_argument("--max-pages", type=int, default=50, help="Directory mode listing pages per city/category")
    parser.add_argument("--workers", type=int, default=6, help="Directory mode concurrent official-site probes")
    parser.add_argument("--timeout", type=int, default=8, help="Directory mode fetch timeout")
    parser.add_argument(
        "--directory-scope",
        choices=["city", "subarea", "both"],
        default="city",
        help="Directory mode listing scope; subarea scans configured Tabelog area pages under each city.",
    )
    parser.add_argument("--resume", action="store_true", help="Resume from the checkpoint path")
    parser.add_argument("--checkpoint-path", default="", help="Directory mode checkpoint JSON path")
    parser.add_argument("--target-reviewable-cards", type=int, default=300, help="Stop directory mode after this many openable pitch cards")
    parser.add_argument("--state-root", default=str(PROJECT_ROOT / "state"))
    parser.add_argument("--summary-path", default="")
    args = parser.parse_args()

    cities = [city.strip() for city in args.cities.split(",") if city.strip()]
    categories = [category.strip() for category in args.categories.split(",") if category.strip()]
    state_root = Path(args.state_root)
    provider = str(args.provider or "webserper")
    serper_key = os.environ.get("SERPER_API_KEY", "") if provider == "serper" else ""
    checkpoint_path = Path(args.checkpoint_path) if args.checkpoint_path else state_root / "lead_imports" / "five_city_search_checkpoint.json"
    summary_output = (
        Path(args.summary_path)
        if args.summary_path
        else state_root / "lead_imports" / f"five_city_no_send_search_{utc_now().replace(':', '').replace('-', '').replace('+00:00', 'z').lower()}.json"
    )

    if args.mode == "directory":
        result = _run_directory_mode(
            cities=cities,
            state_root=state_root,
            max_pages=args.max_pages,
            timeout=args.timeout,
            delay=args.delay,
            workers=args.workers,
            resume=args.resume,
            checkpoint_path=Path(args.checkpoint_path) if args.checkpoint_path else state_root / "lead_imports" / "five_city_directory_checkpoint.json",
            summary_path=Path(args.summary_path) if args.summary_path else None,
            target_reviewable_cards=args.target_reviewable_cards,
            directory_scope=args.directory_scope,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0

    started_at = utc_now()
    checkpoint = _load_checkpoint(checkpoint_path) if args.resume else _new_checkpoint()
    summary: dict[str, Any] = {
        "started_at": started_at,
        "completed_at": "",
        "provider": provider,
        "engine": args.mode,
        "max_candidates": 0,
        "no_send": True,
        "target_reviewable_cards": args.target_reviewable_cards,
        "initial_pitch_card_counts": pitch_card_counts(list_leads(state_root=state_root)),
        "final_pitch_card_counts": {},
        "checkpoint_path": str(checkpoint_path),
        "cities": cities,
        "categories": categories,
        "totals": _new_bucket(),
        "by_city": {city: _new_bucket() for city in cities},
        "by_city_category": {},
        "errors": [],
    }

    jobs_seen = 0
    for city in cities:
        for category in categories:
            key = f"{city}:{category}"
            bucket = _new_bucket()
            summary["by_city_category"][key] = bucket
            if args.mode == "maps":
                jobs = search_jobs_for_scope(category=category, city=city)
            else:
                jobs = codex_search_jobs_for_scope(category=category, city=city)
                if args.mode == "codex-tabelog":
                    jobs = [job for job in jobs if "_tabelog_" in str(job.get("job_id") or "")]
            for job in jobs:
                if _openable_count(state_root) >= args.target_reviewable_cards:
                    _save_generic_summary(summary, state_root=state_root, output=summary_output)
                    print(json.dumps({"summary_path": str(summary_output), "totals": summary["totals"], "target_reached": True}, ensure_ascii=False))
                    return 0
                if args.max_jobs and jobs_seen >= args.max_jobs:
                    break
                job_key = f"{key}:{job.get('job_id') or job.get('query')}"
                if args.resume and _job_done(checkpoint, job_key):
                    continue
                jobs_seen += 1
                try:
                    if args.mode == "maps":
                        result = search_and_qualify(
                            query=job["query"],
                            category=str(job.get("category") or category),
                            search_job={**job, "city": city, "stratum": key},
                            search_provider=provider,
                            serper_api_key=serper_key,
                            max_candidates=0,
                            state_root=state_root,
                        )
                    else:
                        result = codex_search_and_qualify(
                            query=job["query"],
                            category=category,
                            search_job={**job, "city": city, "stratum": key},
                            search_provider=provider,
                            serper_api_key=serper_key,
                            max_candidates=0,
                            state_root=state_root,
                        )
                except Exception as exc:
                    result = {
                        "total_candidates": 0,
                        "leads": 0,
                        "decisions": [{"lead": False, "reason": "search_failed", "error": str(exc)}],
                    }
                    summary["errors"].append({"city": city, "category": category, "job_id": job.get("job_id"), "error": str(exc)})

                _update_bucket(bucket, result)
                _update_bucket(summary["by_city"][city], result)
                _update_bucket(summary["totals"], result)
                if not _result_is_search_failure(result):
                    _mark_job_done(checkpoint, job_key)
                    checkpoint["updated_at"] = utc_now()
                    _write_checkpoint(checkpoint_path, checkpoint)

                if args.delay > 0:
                    time.sleep(args.delay)
            print(json.dumps({"city": city, "category": category, **_normalise_bucket(bucket)}, ensure_ascii=False))
            sys.stdout.flush()
            if args.max_jobs and jobs_seen >= args.max_jobs:
                break
        if args.max_jobs and jobs_seen >= args.max_jobs:
            break

    _save_generic_summary(summary, state_root=state_root, output=summary_output)
    print(json.dumps({"summary_path": str(summary_output), "totals": summary["totals"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
