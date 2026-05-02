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
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.search import codex_search_and_qualify, search_and_qualify
from pipeline.search_scope import codex_search_jobs_for_scope, search_jobs_for_scope
from pipeline.utils import ensure_dir, load_project_env, utc_now

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


def main() -> int:
    load_project_env()

    parser = argparse.ArgumentParser(description="No-send five-city restaurant email inventory search")
    parser.add_argument("--cities", default=",".join(DEFAULT_CITIES))
    parser.add_argument("--categories", default=",".join(DEFAULT_CATEGORIES))
    parser.add_argument("--provider", default=os.environ.get("WEBREFURB_SEARCH_PROVIDER") or ("serper" if os.environ.get("SERPER_API_KEY") else "webserper"))
    parser.add_argument(
        "--mode",
        choices=["maps", "codex-tabelog", "codex-all"],
        default="maps",
        help="maps uses physical-place searches; codex-tabelog uses Tabelog email jobs; codex-all also includes broad platform jobs.",
    )
    parser.add_argument("--delay", type=float, default=0.05)
    parser.add_argument("--max-jobs", type=int, default=0, help="Debug cap; 0 means all generated jobs")
    parser.add_argument("--state-root", default=str(PROJECT_ROOT / "state"))
    parser.add_argument("--summary-path", default="")
    args = parser.parse_args()

    cities = [city.strip() for city in args.cities.split(",") if city.strip()]
    categories = [category.strip() for category in args.categories.split(",") if category.strip()]
    state_root = Path(args.state_root)
    provider = str(args.provider or "webserper")
    serper_key = os.environ.get("SERPER_API_KEY", "") if provider == "serper" else ""

    started_at = utc_now()
    summary: dict[str, Any] = {
        "started_at": started_at,
        "completed_at": "",
        "provider": provider,
        "engine": args.mode,
        "max_candidates": 0,
        "no_send": True,
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
                if args.max_jobs and jobs_seen >= args.max_jobs:
                    break
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

                if args.delay > 0:
                    time.sleep(args.delay)
            print(json.dumps({"city": city, "category": category, **_normalise_bucket(bucket)}, ensure_ascii=False))
            sys.stdout.flush()
            if args.max_jobs and jobs_seen >= args.max_jobs:
                break
        if args.max_jobs and jobs_seen >= args.max_jobs:
            break

    summary["completed_at"] = utc_now()
    summary["totals"] = _normalise_bucket(summary["totals"])
    summary["by_city"] = {city: _normalise_bucket(bucket) for city, bucket in summary["by_city"].items()}
    summary["by_city_category"] = {
        key: _normalise_bucket(bucket) for key, bucket in summary["by_city_category"].items()
    }

    output = Path(args.summary_path) if args.summary_path else state_root / "lead_imports" / f"five_city_no_send_search_{started_at.replace(':', '').replace('-', '').replace('+00:00', 'z').lower()}.json"
    ensure_dir(output.parent)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary_path": str(output), "totals": summary["totals"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
