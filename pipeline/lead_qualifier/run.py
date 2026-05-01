#!/usr/bin/env python
"""CLI entry point for the lead qualification system.

Usage:
    python -m pipeline.lead_qualifier.run --city Tokyo --category ramen
    python -m pipeline.lead_qualifier.run --city Tokyo --dry-run
    python -m pipeline.lead_qualifier.run --city Osaka --output-json /tmp/queue.json
"""

from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Menu-first, pain-signal-first lead qualification queue",
    )
    parser.add_argument("--city", required=True, help="Target city (e.g. Tokyo, Osaka)")
    parser.add_argument(
        "--category", choices=["all", "ramen", "izakaya"], default="all",
    )
    parser.add_argument("--max-candidates", type=int, default=200)
    parser.add_argument("--max-review-scrapes", type=int, default=100)
    parser.add_argument("--max-contact-crawls", type=int, default=50)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-pain-score", type=int, default=10)

    args = parser.parse_args()

    # Load .env if present
    try:
        from pipeline.utils import load_project_env
        load_project_env()
    except Exception:
        pass

    from .queue import run_qualification_queue

    results = run_qualification_queue(
        city=args.city,
        category=args.category,
        max_candidates=args.max_candidates,
        max_review_scrapes=args.max_review_scrapes,
        max_contact_crawls=args.max_contact_crawls,
        delay_seconds=args.delay,
        output_json=args.output_json,
        dry_run=args.dry_run,
        min_pain_score=args.min_pain_score,
    )

    # Print summary
    summary = {
        "total_qualified": len(results),
        "with_email": sum(1 for r in results if r.contact_emails),
        "with_contact_form": sum(1 for r in results if r.has_contact_form),
        "with_pain_signals": sum(1 for r in results if r.pain_assessment and r.pain_assessment.has_pain_signals),
        "avg_pain_score": round(
            sum(r.pain_assessment.pain_score for r in results if r.pain_assessment) /
            max(sum(1 for r in results if r.pain_assessment), 1), 1
        ),
        "city": args.city,
        "category": args.category,
        "dry_run": args.dry_run,
    }
    if args.output_json:
        summary["output_json"] = args.output_json

    print(json.dumps(summary, indent=2, ensure_ascii=False))

    # Print top 10 leads
    for entry in results[:10]:
        pain = entry.pain_assessment.pain_score if entry.pain_assessment else 0
        contact = "email" if entry.contact_emails else ("form" if entry.has_contact_form else "none")
        print(
            f"  #{entry.outreach_priority} {entry.business_name} "
            f"| pain={pain} | evidence={entry.evidence_score} "
            f"| composite={entry.composite_score:.1f} | contact={contact}"
        )


if __name__ == "__main__":
    main()
