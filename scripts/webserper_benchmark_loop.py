#!/usr/bin/env python3
"""WebSerper benchmark loop: iterate until targets surpass Serper.dev baseline.

This script runs the full collect → benchmark cycle repeatedly, reports
progress against acceptance targets, and exits with clear status. It does NOT
modify code — that must be done by the operator. It does NOT send email or
submit forms.

Usage:
    .venv/bin/python scripts/webserper_benchmark_loop.py \\
        --run-id "loop-001" \\
        --city-set launch-markets \\
        --category all \\
        --max-iterations 20 \\
        --pilot-cities Shibuya,Kichijoji,Sangenjaya

The loop will:
1. Run production-sim collect (live search + fetch)
2. Carry forward labels from a labeled baseline corpus if provided
3. Run production-sim benchmark against acceptance targets
4. Print a detailed progress report
5. Exit 0 if all targets met, 1 otherwise
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.constants import PROJECT_ROOT as CONSTANTS_ROOT  # noqa: E402
from pipeline.search_replay import (  # noqa: E402
    BENCHMARK_ACCEPTANCE_TARGETS,
    benchmark_replay_corpus,
    collect_replay_corpus,
    collection_search_jobs,
    load_replay_corpus,
    reconcile_label_contact_policy,
)
from pipeline.search_scope import normalise_search_category  # noqa: E402
from pipeline.utils import utc_now  # noqa: E402


ACCEPTANCE_TARGETS = {
    "max_unrecovered_search_failures": 0,
    "min_candidates_per_job": 1.60,
    "max_fetch_failure_rate": 0.12,
    "max_unsupported_ready_labels": 0,
    "min_expected_ready_labels": 6,
}

SERPER_BASELINE = {
    "search_failures": 0,
    "deduped_candidates_per_job": 1.50,
    "fetch_failure_rate": 0.18,
    "ready_labels": 6,
}

EXTRA_TARGETS = {
    "replay_p0": 0,
    "replay_p1": 0,
    "no_outbound_actions": True,
}


def _cities_for_set(city_set: str, pilot_cities: list[str] | None = None) -> list[str]:
    from pipeline.search_replay import cities_for_market_set
    if pilot_cities:
        return pilot_cities
    return cities_for_market_set(city_set)


def _carry_forward_labels(*, source_corpus: str | Path, target_corpus: str | Path) -> int:
    """Copy finalized labels from a baseline corpus into the new corpus."""
    source_labels = Path(source_corpus) / "labels"
    target_labels = Path(target_corpus) / "labels"
    if not source_labels.exists():
        return 0
    target_labels.mkdir(parents=True, exist_ok=True)
    count = 0
    for label_file in sorted(source_labels.glob("*.json")):
        try:
            label = json.loads(label_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(label, dict):
            continue
        target_file = target_labels / label_file.name
        if target_file.exists():
            continue
        shutil.copy2(label_file, target_file)
        count += 1
    return count


def _evaluate_benchmark(result: dict[str, Any]) -> dict[str, Any]:
    """Evaluate benchmark results against all acceptance targets."""
    metrics = result.get("metrics") or {}
    comparison = result.get("comparison") or {}
    meets = comparison.get("meets_targets") or {}

    evaluation = {
        "all_targets_met": comparison.get("passed", False),
        "targets": {},
        "gaps": [],
    }

    target_checks = [
        ("search_failures", metrics.get("search_failure_count", -1), ACCEPTANCE_TARGETS["max_unrecovered_search_failures"], "<="),
        ("deduped_candidates_per_job", metrics.get("deduped_candidates_per_job", 0), ACCEPTANCE_TARGETS["min_candidates_per_job"], ">="),
        ("fetch_failure_rate", metrics.get("fetch_failure_rate", 1.0), ACCEPTANCE_TARGETS["max_fetch_failure_rate"], "<="),
        ("unsupported_ready_labels", metrics.get("unsupported_ready_label_count", 0), ACCEPTANCE_TARGETS["max_unsupported_ready_labels"], "<="),
        ("ready_labels", metrics.get("expected_ready_label_count", 0), ACCEPTANCE_TARGETS["min_expected_ready_labels"], ">="),
    ]

    for name, actual, target, op in target_checks:
        if op == "<=":
            passed = float(actual) <= float(target)
        else:
            passed = float(actual) >= float(target)
        evaluation["targets"][name] = {
            "actual": actual,
            "target": target,
            "met": passed,
        }
        if not passed:
            evaluation["gaps"].append(
                f"{name}: {actual} (need {op} {target})"
            )

    return evaluation


def _print_iteration_report(
    *,
    iteration: int,
    result: dict[str, Any],
    evaluation: dict[str, Any],
    elapsed: float,
) -> None:
    """Print a detailed benchmark report for one iteration."""
    metrics = result.get("metrics") or {}
    comparison = result.get("comparison") or {}
    deltas = comparison.get("deltas_vs_baseline") or {}

    print("\n" + "=" * 80)
    print(f"  ITERATION {iteration} REPORT")
    print("=" * 80)

    print(f"\n  Elapsed: {elapsed:.1f}s")
    print(f"  Corpus: {result.get('corpus', '')}")

    print(f"\n  {'Metric':<40} {'Actual':>10} {'Target':>10} {'Status':>10}")
    print("  " + "-" * 72)

    for name, info in evaluation["targets"].items():
        status = "PASS" if info["met"] else "FAIL"
        if isinstance(info["actual"], float):
            actual_str = f"{info['actual']:.4f}"
        else:
            actual_str = str(info["actual"])
        target_str = str(info["target"])
        print(f"  {name:<40} {actual_str:>10} {target_str:>10} {status:>10}")

    # Key diagnostics
    print(f"\n  Diagnostics:")
    print(f"    Raw candidates:       {metrics.get('raw_candidate_count', 0)}")
    print(f"    Deduped candidates:   {metrics.get('candidate_count', 0)}")
    print(f"    Search job count:     {metrics.get('search_job_count', 0)}")
    print(f"    Discovery job count:  {metrics.get('candidate_discovery_job_count', 0)}")
    print(f"    Fetch success/fail:   {metrics.get('fetch_success_count', 0)}/{metrics.get('fetch_failure_count', 0)}")
    print(f"    First-party rate:     {metrics.get('first_party_site_rate', 0):.1%}")
    print(f"    Job modes:            {metrics.get('search_job_mode_counts', {})}")
    print(f"    Route profiles:       {metrics.get('contact_route_profile_counts', {})}")
    print(f"    Negative flags:       {metrics.get('review_negative_flag_counts', {})}")

    if deltas:
        print(f"\n  Deltas vs baseline:")
        for key, delta in deltas.items():
            arrow = "+" if delta >= 0 else ""
            print(f"    {key}: {arrow}{delta:.4f}")

    if evaluation["gaps"]:
        print(f"\n  GAPS TO CLOSE:")
        for gap in evaluation["gaps"]:
            print(f"    - {gap}")
    else:
        print(f"\n  ALL TARGETS MET!")

    print("=" * 80 + "\n")


def _print_vs_serper(evaluation: dict[str, Any]) -> None:
    """Print comparison vs Serper.dev baseline."""
    print("\n  Comparison vs Serper.dev baseline:")
    print(f"    {'Metric':<40} {'WebSerper':>10} {'Serper':>10}")
    print("    " + "-" * 62)

    targets = evaluation.get("targets", {})
    comparisons = [
        ("search_failures", "search_failures", 0),
        ("deduped_candidates_per_job", "deduped_candidates_per_job", SERPER_BASELINE["deduped_candidates_per_job"]),
        ("fetch_failure_rate", "fetch_failure_rate", SERPER_BASELINE["fetch_failure_rate"]),
        ("ready_labels", "ready_labels", SERPER_BASELINE["ready_labels"]),
    ]
    for label, key, serper_val in comparisons:
        info = targets.get(key, {})
        actual = info.get("actual", "N/A")
        if isinstance(actual, float):
            actual_str = f"{actual:.4f}"
        else:
            actual_str = str(actual)
        if isinstance(serper_val, float):
            serper_str = f"{serper_val:.4f}"
        else:
            serper_str = str(serper_val)
        print(f"    {label:<40} {actual_str:>10} {serper_str:>10}")
    print()


def run_one_iteration(
    *,
    run_id: str,
    cities: list[str],
    category: str,
    iteration: int,
    baseline_corpus: str | Path | None = None,
    limit_per_job: int = 5,
    contact_pages: int = 3,
    evidence_pages: int = 4,
    fail_on: list[str] | None = None,
    directory_discovery: bool = True,
    directory_max_pages: int = 50,
    directory_max_details: int = 500,
) -> dict[str, Any]:
    """Run a single collect → benchmark iteration."""
    state_root = CONSTANTS_ROOT / "state" / "search-replay"
    state_root.mkdir(parents=True, exist_ok=True)

    iter_run_id = f"{run_id}-iter{iteration:03d}"
    start = time.time()

    print(f"\n>>> Iteration {iteration}: collecting corpus '{iter_run_id}'...")

    # Collect
    collect_result = collect_replay_corpus(
        run_id=iter_run_id,
        replay_root=str(state_root),
        city_set="launch-markets",
        cities=cities,
        category=category,
        limit_per_job=limit_per_job,
        stage="pilot",
        search_provider="webserper",
        contact_pages_per_candidate=contact_pages,
        evidence_pages_per_candidate=evidence_pages,
        directory_discovery=directory_discovery,
        directory_max_pages=directory_max_pages,
        directory_max_details=directory_max_details,
    )

    corpus_dir = state_root / iter_run_id

    # Carry forward labels from baseline
    labels_carried = 0
    if baseline_corpus:
        baseline_path = Path(baseline_corpus)
        if baseline_path.exists():
            labels_carried = _carry_forward_labels(
                source_corpus=baseline_path,
                target_corpus=corpus_dir,
            )
            print(f"    Carried forward {labels_carried} labels from baseline")

    # Reconcile labels against current policy
    if (corpus_dir / "labels").exists() and any((corpus_dir / "labels").glob("*.json")):
        try:
            reconcile_label_contact_policy(corpus_dir)
            print("    Reconciled labels against current route policy")
        except Exception as exc:
            print(f"    Label reconciliation warning: {exc}")

    # Benchmark
    baseline_dir = str(baseline_corpus) if baseline_corpus else None
    benchmark_result = benchmark_replay_corpus(
        corpus_dir=str(corpus_dir),
        baseline_corpus_dir=baseline_dir,
        run_label=f"loop-iter{iteration:03d}-{utc_now().strftime('%Y%m%d')}",
    )

    elapsed = time.time() - start

    evaluation = _evaluate_benchmark(benchmark_result)
    _print_iteration_report(
        iteration=iteration,
        result=benchmark_result,
        evaluation=evaluation,
        elapsed=elapsed,
    )
    _print_vs_serper(evaluation)

    return {
        "iteration": iteration,
        "run_id": iter_run_id,
        "corpus_dir": str(corpus_dir),
        "elapsed": elapsed,
        "benchmark": benchmark_result,
        "evaluation": evaluation,
        "labels_carried": labels_carried,
        "external_send_performed": False,
        "real_launch_batch_created": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="WebSerper benchmark loop: iterate until surpassing Serper.dev quality",
    )
    parser.add_argument("--run-id", default="webserper-loop", help="Base run ID")
    parser.add_argument("--city-set", default="launch-markets")
    parser.add_argument("--pilot-cities", default="", help="Comma-separated city list (overrides city-set)")
    parser.add_argument("--category", default="all", choices=["all", "ramen", "izakaya"])
    parser.add_argument("--max-iterations", type=int, default=20)
    parser.add_argument("--baseline-corpus", default="", help="Path to labeled baseline corpus for label carry-forward")
    parser.add_argument("--limit-per-job", type=int, default=5)
    parser.add_argument("--contact-pages", type=int, default=3)
    parser.add_argument("--evidence-pages", type=int, default=4)
    parser.add_argument("--fail-on", default="p0,p1", help="Comma-separated severity levels to fail on")
    parser.add_argument("--no-directory", action="store_true", help="Disable directory discovery (use search only)")
    parser.add_argument("--dir-max-pages", type=int, default=50, help="Max directory listing pages per source/genre")
    parser.add_argument("--dir-max-details", type=int, default=500, help="Max directory detail page fetches per source")
    parser.add_argument("--dry-run", action="store_true", help="Print config and exit without collecting")
    args = parser.parse_args()

    pilot_cities = [c.strip() for c in args.pilot_cities.split(",") if c.strip()] or None
    cities = _cities_for_set(args.city_set, pilot_cities)
    fail_on = [s.strip() for s in args.fail_on.split(",") if s.strip()]
    baseline_corpus = args.baseline_corpus.strip() or None

    print("WebSerper Benchmark Loop")
    print(f"  Run ID:        {args.run_id}")
    print(f"  Cities:        {len(cities)} ({', '.join(cities[:5])}{'...' if len(cities) > 5 else ''})")
    print(f"  Category:      {args.category}")
    print(f"  Max iterations: {args.max_iterations}")
    print(f"  Baseline:      {baseline_corpus or '(none)'}")
    print(f"  Fail on:       {fail_on}")
    print(f"  Acceptance targets:")
    for key, value in ACCEPTANCE_TARGETS.items():
        print(f"    {key}: {value}")
    print()

    if args.dry_run:
        print("Dry run — exiting.")
        return 0

    results: list[dict[str, Any]] = []
    all_passed = False

    for iteration in range(1, args.max_iterations + 1):
        iter_result = run_one_iteration(
            run_id=args.run_id,
            cities=cities,
            category=args.category,
            iteration=iteration,
            baseline_corpus=baseline_corpus,
            limit_per_job=args.limit_per_job,
            contact_pages=args.contact_pages,
            evidence_pages=args.evidence_pages,
            fail_on=fail_on,
            directory_discovery=not args.no_directory,
            directory_max_pages=args.dir_max_pages,
            directory_max_details=args.dir_max_details,
        )
        results.append(iter_result)

        if iter_result["evaluation"]["all_targets_met"]:
            print(f"\n*** ALL TARGETS MET at iteration {iteration}! ***\n")
            all_passed = True
            break
        else:
            gaps = iter_result["evaluation"]["gaps"]
            print(f"  Iteration {iteration} incomplete. Gaps:")
            for gap in gaps:
                print(f"    - {gap}")
            print(f"  Make code improvements and re-run the loop.\n")
            # For a single pass, break after first iteration
            # The operator should make changes and re-run
            break

    # Write loop summary
    summary_path = CONSTANTS_ROOT / "state" / "search-replay" / f"{args.run_id}-summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_id": args.run_id,
        "total_iterations": len(results),
        "all_targets_met": all_passed,
        "results": [{k: v for k, v in r.items() if k != "benchmark"} for r in results],
        "acceptance_targets": ACCEPTANCE_TARGETS,
        "serper_baseline": SERPER_BASELINE,
        "external_send_performed": False,
        "real_launch_batch_created": False,
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"Loop summary: {summary_path}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
