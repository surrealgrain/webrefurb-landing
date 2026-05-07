from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .utils import load_project_env, slugify, utc_now


def main() -> None:
    load_project_env()

    parser = argparse.ArgumentParser(description="WebRefurbMenu pipeline CLI")
    sub = parser.add_subparsers(dest="command")

    # search
    search_cmd = sub.add_parser("search", help="Search and qualify leads")
    search_cmd.add_argument("--query", required=True)
    search_cmd.add_argument("--api-key", default="")
    search_cmd.add_argument("--search-provider", default=None, choices=["webserper", "serper", "local"], help="Search provider; defaults to WEBREFURB_SEARCH_PROVIDER or WebSerper")
    search_cmd.add_argument("--category", default="ramen")
    search_cmd.add_argument("--max-candidates", type=int, default=0, help="Max candidates to process; 0 means no cap")

    # manual-add
    manual_cmd = sub.add_parser("manual-add", help="Manually add a business")
    manual_cmd.add_argument("--name", required=True)
    manual_cmd.add_argument("--website", required=True)
    manual_cmd.add_argument("--category", default="ramen")
    manual_cmd.add_argument("--address", default="")
    manual_cmd.add_argument("--phone", default="")

    # list-leads
    sub.add_parser("list-leads", help="List all leads")

    # render
    render_cmd = sub.add_parser("render", help="Render menu HTML from template + JSON")
    render_cmd.add_argument("--content", default=None, help="Path to menu_content.json")
    render_cmd.add_argument("--template", default=None, help="Path to template HTML")
    render_cmd.add_argument("--output", default=None, help="Output HTML path (default: stdout)")

    # outreach
    outreach_cmd = sub.add_parser("outreach", help="Generate cold outreach package")
    outreach_cmd.add_argument("--lead-id", default=None, help="Lead ID to generate outreach for")
    outreach_cmd.add_argument("--name", default=None, help="Business name (inline mode)")
    outreach_cmd.add_argument("--website", default=None, help="Business website (inline mode)")
    outreach_cmd.add_argument("--category", default="ramen", help="Business category")
    outreach_cmd.add_argument("--address", default="")
    outreach_cmd.add_argument("--no-inperson", action="store_true", help="Omit in-person delivery line")

    # contact-crawl
    contact_cmd = sub.add_parser("contact-crawl", help="Discover Japanese ramen/izakaya sites and crawl contact points")
    contact_cmd.add_argument("--city", required=True, help="Target city or ward, e.g. Fukuoka or 福岡")
    contact_cmd.add_argument(
        "--category",
        action="append",
        choices=["ラーメン", "居酒屋", "ramen", "izakaya"],
        default=[],
        help="Category to discover; repeat for ramen and izakaya",
    )
    contact_cmd.add_argument("--places-api-key", default=None, help="Google Places API key; defaults to GOOGLE_PLACES_API_KEY")
    contact_cmd.add_argument("--directory-url", action="append", default=[], help="Tabelog/HotPepper category URL to crawl")
    contact_cmd.add_argument("--max-places", type=int, default=20, help="Max Google Places results per category")
    contact_cmd.add_argument("--max-directory-detail-pages", type=int, default=12)
    contact_cmd.add_argument("--concurrency", type=int, default=4)
    contact_cmd.add_argument("--output-json", default=None, help="Write full JSON output to this path")
    contact_cmd.add_argument("--output-csv", default=None, help="Write lead CSV output to this path")

    # build (Mode B)
    build_cmd = sub.add_parser("build", help="Custom menu build from owner data")
    build_cmd.add_argument("--name", required=True, help="Restaurant name")
    build_cmd.add_argument("--menu-text", default="", help="Menu items as text")
    build_cmd.add_argument("--menu-photo", action="append", default=[], help="Menu photo path (repeatable)")
    build_cmd.add_argument("--ticket-photo", default=None, help="Ticket machine photo path")
    build_cmd.add_argument("--notes", default="", help="Additional notes")
    build_cmd.add_argument("--output", default=None, help="Output directory")

    backup_cmd = sub.add_parser("backup-state", help="Archive operational state directories")
    backup_cmd.add_argument("--state-root", default=None, help="Override state root")
    backup_cmd.add_argument("--output", default=None, help="Write backup ZIP to this path")

    harden_cmd = sub.add_parser("harden-state", help="Migrate lead records through launch-readiness gates")
    harden_cmd.add_argument("--state-root", default=None, help="Override state root")

    audit_cmd = sub.add_parser("audit-state", help="Audit persisted lead state for stale assets and name drift")
    audit_cmd.add_argument("--state-root", default=None, help="Override state root")
    audit_cmd.add_argument("--repair", action="store_true", help="Repair deterministic state drift before auditing")

    reclassify_cmd = sub.add_parser("reclassify", help="Reclassify all leads to 2-category model (ramen / izakaya)")
    reclassify_cmd.add_argument("--state-root", default=None, help="Override state root")
    reclassify_cmd.add_argument("--apply", action="store_true", help="Persist changes; default is dry-run")

    validate_emails_cmd = sub.add_parser("validate-emails", help="MX-validate all lead email addresses")
    validate_emails_cmd.add_argument("--state-root", default=None, help="Override state root")
    validate_emails_cmd.add_argument("--apply", action="store_true", help="Persist results; default is dry-run")

    verify_restaurant_cmd = sub.add_parser("verify-restaurant-leads", help="Run the no-send restaurant email lead verification pass")
    verify_restaurant_cmd.add_argument("--state-root", default=None, help="Override state root")
    verify_restaurant_cmd.add_argument("--dry-run", action="store_true", help="Report verification results without writing lead records")
    verify_restaurant_cmd.add_argument("--summary-path", default=None, help="Write verification summary JSON to this path")

    smoke_cmd = sub.add_parser("launch-smoke", help="Create a no-send launch rehearsal from ready leads")
    smoke_cmd.add_argument("--lead-id", action="append", required=True, help="Lead ID to include; repeat 5-10 times")
    smoke_cmd.add_argument("--state-root", default=None, help="Override state root")
    smoke_cmd.add_argument("--notes", default="", help="Operator notes for the rehearsal")
    smoke_cmd.add_argument("--scenario", default="real_world_no_send", help="Smoke-test scenario label")

    launch_decision_cmd = sub.add_parser("launch-decision", help="Write a no-send next-batch decision brief")
    launch_decision_cmd.add_argument("--state-root", default=None, help="Override state root")
    launch_decision_cmd.add_argument("--output-dir", default=None, help="Decision artifact output directory")
    launch_decision_cmd.add_argument("--label", default="batch3-no-send", help="Artifact filename label")

    review_batch_cmd = sub.add_parser("review-batch", help="Write a no-send pitch-card review batch brief")
    review_batch_cmd.add_argument("--state-root", default=None, help="Override state root")
    review_batch_cmd.add_argument("--output-dir", default=None, help="Review artifact output directory")
    review_batch_cmd.add_argument("--label", default="pitch-card-review", help="Artifact filename label")
    review_batch_cmd.add_argument("--batch-size", type=int, default=120, help="Number of unreviewed cards to include")

    review_wave_cmd = sub.add_parser("review-wave", help="Write no-send pitch-card review waves for all unreviewed cards")
    review_wave_cmd.add_argument("--state-root", default=None, help="Override state root")
    review_wave_cmd.add_argument("--output-dir", default=None, help="Review artifact output directory")
    review_wave_cmd.add_argument("--label", default="pitch-card-review-wave", help="Artifact filename label")
    review_wave_cmd.add_argument("--batch-size", type=int, default=120, help="Number of unreviewed cards per wave batch")

    enrichment_cmd = sub.add_parser("needs-more-info-enrichment", help="Write no-send enrichment batches for reviewed needs_more_info cards")
    enrichment_cmd.add_argument("--state-root", default=None, help="Override state root")
    enrichment_cmd.add_argument("--output-dir", default=None, help="Review artifact output directory")
    enrichment_cmd.add_argument("--label", default="needs-more-info-enrichment", help="Artifact filename label")
    enrichment_cmd.add_argument("--batch-size", type=int, default=80, help="Number of needs_more_info cards per enrichment batch")

    execution_plan_cmd = sub.add_parser("restaurant-execution-plan", help="Write the no-send restaurant lead execution-plan completion artifact")
    execution_plan_cmd.add_argument("--state-root", default=None, help="Override state root")
    execution_plan_cmd.add_argument("--output-dir", default=None, help="Execution-plan artifact output directory")
    execution_plan_cmd.add_argument("--label", default="restaurant-lead-execution-plan", help="Artifact filename label")
    execution_plan_cmd.add_argument("--batch-size", type=int, default=120, help="Number of unreviewed cards per review-wave batch")
    execution_plan_cmd.add_argument("--representative-count", type=int, default=5, help="Representative examples per GLM profile")

    run8_cmd = sub.add_parser("run8-readiness", help="Run no-send Run 8 browser/export/rehearsal verification")
    run8_cmd.add_argument("--state-root", default=None, help="Override state root")
    run8_cmd.add_argument("--docs-root", default=None, help="Override static docs root")
    run8_cmd.add_argument("--run-id", default=None, help="Stable run ID")
    run8_cmd.add_argument("--skip-screenshots", action="store_true", help="Skip browser screenshot capture")

    sim_cmd = sub.add_parser("production-sim", help="Run no-send production simulation replay")
    sim_sub = sim_cmd.add_subparsers(dest="production_sim_command")
    sim_collect = sim_sub.add_parser("collect", help="Collect a no-send pilot/broad search replay corpus")
    sim_collect.add_argument("--run-id", default=None, help="Stable run ID")
    sim_collect.add_argument("--city-set", default="launch-markets", help="Market set, e.g. launch-markets")
    sim_collect.add_argument("--city", action="append", default=[], help="Override city/market; repeatable")
    sim_collect.add_argument("--category", choices=["all", "ramen", "izakaya"], default="all")
    sim_collect.add_argument("--limit-per-job", type=int, default=5)
    sim_collect.add_argument("--stage", choices=["pilot", "broad", "extended"], default="pilot")
    sim_collect.add_argument("--api-key", default=None, help="Serper.dev API key; only used with --search-provider serper")
    sim_collect.add_argument("--search-provider", default=None, choices=["webserper", "serper", "local"], help="Search provider; defaults to WEBREFURB_SEARCH_PROVIDER or WebSerper")
    sim_collect.add_argument("--output-root", default=None, help="Production-sim report output root")
    sim_collect.add_argument("--replay-root", default=None, help="Search replay artifact root")
    sim_collect.add_argument("--screenshot-root", default=None, help="Screenshot artifact root")
    sim_collect.add_argument("--fetch-timeout-seconds", type=int, default=8)
    sim_collect.add_argument("--contact-pages-per-candidate", type=int, default=2)
    sim_collect.add_argument("--evidence-pages-per-candidate", type=int, default=2)
    sim_collect.add_argument("--offline-fixture", default=None, help="JSON fixture for mocked search/fetch collection")
    sim_collect.add_argument("--fail-on", default="p0,p1", help="Comma-separated severities that return non-zero")
    sim_replay = sim_sub.add_parser("replay", help="Replay a deterministic production-simulation corpus")
    sim_replay.add_argument("--corpus", default=None, help="Replay corpus directory")
    sim_replay.add_argument("--run-id", default=None, help="Stable run ID")
    sim_replay.add_argument("--output-root", default=None, help="Production-sim output root")
    sim_replay.add_argument("--replay-root", default=None, help="Search replay artifact root")
    sim_replay.add_argument("--screenshot-root", default=None, help="Screenshot artifact root")
    sim_replay.add_argument("--screenshots", action="store_true", help="Capture dashboard screenshots with Playwright")
    sim_replay.add_argument("--dashboard-port", type=int, default=0, help="Dashboard port, or 0 for any free port")
    sim_replay.add_argument("--fail-on", default="p0,p1", help="Comma-separated severities that return non-zero")
    sim_label = sim_sub.add_parser("label", help="Create a stratified draft-label workflow for a collected corpus")
    sim_label.add_argument("--corpus", required=True, help="Search replay corpus directory")
    sim_label.add_argument("--sample", choices=["stratified"], default="stratified")
    sim_label.add_argument("--sample-size", type=int, default=120)
    sim_label.add_argument("--seed", default="production-sim-labeling-v1")
    sim_label.add_argument("--output-root", default=None, help="Production-sim output root")
    sim_label.add_argument("--fail-on", default="p0,p1", help="Comma-separated severities that return non-zero")
    sim_report = sim_sub.add_parser("report", help="Check an existing production-sim report")
    sim_report.add_argument("--run", required=True, help="Run ID or report directory")
    sim_report.add_argument("--fail-on", default="p0,p1", help="Comma-separated severities that return non-zero")
    sim_reconcile = sim_sub.add_parser("reconcile-label-policy", help="Reconcile replay labels to current outreach route policy")
    sim_reconcile.add_argument("--corpus", required=True, help="Search replay corpus directory")
    sim_benchmark = sim_sub.add_parser("benchmark", help="Benchmark a collected WebSerper replay corpus")
    sim_benchmark.add_argument("--corpus", required=True, help="Search replay corpus directory")
    sim_benchmark.add_argument("--baseline-corpus", default=None, help="Optional baseline replay corpus directory")
    sim_benchmark.add_argument("--run-label", default="", help="Report label")
    sim_benchmark.add_argument("--output-dir", default=None, help="Benchmark artifact output directory")
    sim_recommend = sim_sub.add_parser("recommend", help="Run no-send smoke and write controlled-launch recommendation")
    sim_recommend.add_argument("--run", required=True, help="Run ID or report directory")
    sim_recommend.add_argument("--lead-id", action="append", required=True, help="Lead ID for the no-send smoke; repeat 5-10 times")
    sim_recommend.add_argument("--skip-live-url-check", action="store_true", help="Skip live source URL checks")
    sim_recommend.add_argument("--fail-on", default="p0,p1", help="Comma-separated severities that return non-zero")

    # discover (email discovery pipeline)
    discover_cmd = sub.add_parser("discover", help="Run email discovery and lead qualification pipeline")
    discover_cmd.add_argument("--input", required=True, help="Input CSV path with lead data")
    discover_cmd.add_argument("--config", default="email_discovery.yaml", help="Config YAML path")
    discover_cmd.add_argument("--dry-run", action="store_true", help="Skip all network requests")
    discover_cmd.add_argument("--max-leads", type=int, default=0, help="Limit number of leads (0=all)")
    discover_cmd.add_argument("--output-csv", default=None, help="CSV output path")
    discover_cmd.add_argument("--output-jsonl", default=None, help="JSONL output path")

    # enrich existing lead records with deeper email discovery
    enrich_cmd = sub.add_parser("enrich", help="Enrich persisted leads with WebSerper email discovery")
    enrich_target = enrich_cmd.add_mutually_exclusive_group(required=True)
    enrich_target.add_argument("--lead-id", default=None, help="Lead ID to enrich")
    enrich_target.add_argument("--all", action="store_true", help="Enrich all persisted leads")
    enrich_cmd.add_argument("--config", default="email_discovery.yaml", help="Email discovery config YAML path")
    enrich_cmd.add_argument("--dry-run", action="store_true", help="Do not persist updated lead records")
    enrich_cmd.add_argument("--no-contact", action="store_true", help="Only enrich leads without an email contact")
    enrich_cmd.add_argument("--score-below", type=float, default=None, help="Only enrich leads with score below this value")
    enrich_cmd.add_argument("--max-leads", type=int, default=0, help="Limit number of selected leads (0=all)")
    enrich_cmd.add_argument("--state-root", default=None, help="Override state root")

    sample_cmd = sub.add_parser("hosted-sample", help="Publish hosted menu sample pages for leads")
    sample_target = sample_cmd.add_mutually_exclusive_group(required=True)
    sample_target.add_argument("--lead-id", default=None, help="Lead ID to prepare")
    sample_target.add_argument("--all", action="store_true", help="Prepare all qualified persisted leads")
    sample_cmd.add_argument("--dry-run", action="store_true", help="Show URL and contact-form text without writing files or leads")
    sample_cmd.add_argument("--state-root", default=None, help="Override state root")
    sample_cmd.add_argument("--docs-root", default=None, help="Override static docs root")
    sample_cmd.add_argument("--public-base-url", default=None, help="Public site base URL; defaults to https://webrefurb.com")
    sample_cmd.add_argument("--max-leads", type=int, default=0, help="Limit selected leads when using --all")

    args = parser.parse_args()

    if args.command == "search":
        from .search import search_and_qualify
        result = search_and_qualify(
            query=args.query,
            serper_api_key=args.api_key,
            category=args.category,
            search_provider=args.search_provider,
            max_candidates=args.max_candidates,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "manual-add":
        from .search import _fetch_page
        from .qualification import qualify_candidate
        from .preview import build_preview_menu, build_preview_html
        from .pitch import build_pitch
        from .record import create_lead_record, persist_lead_record

        try:
            html = _fetch_page(args.website)
        except Exception as exc:
            print(json.dumps({"error": f"fetch_failed: {exc}"}))
            sys.exit(1)

        pages = [{"url": args.website, "html": html}]
        qualification = qualify_candidate(
            business_name=args.name,
            website=args.website,
            category=args.category,
            pages=pages,
            address=args.address,
            phone=args.phone,
        )

        if qualification.lead:
            preview_menu = build_preview_menu(
                assessment=qualification,
                snippets=qualification.evidence_snippets,
                business_name=args.name,
            )
            preview_html = build_preview_html(
                preview_menu=preview_menu,
                ticket_machine_hint=None,
                business_name=args.name,
            )
            pitch = build_pitch(
                business_name=args.name,
                category=qualification.primary_category_v1,
                preview_menu=preview_menu,
                ticket_machine_hint=None,
                recommended_package=qualification.recommended_primary_package,
            )
            record = create_lead_record(
                qualification=qualification,
                preview_html=preview_html,
                pitch_draft=pitch,
                source_query="manual_add",
            )
            persist_lead_record(record)
            print(json.dumps(record, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(qualification.to_dict(), indent=2, ensure_ascii=False))

    elif args.command == "list-leads":
        from .record import list_leads
        leads = list_leads()
        print(json.dumps(leads, indent=2, ensure_ascii=False))

    elif args.command == "render":
        from .render import render
        html = render(content_path=args.content, template_path=args.template)
        if args.output:
            from pathlib import Path as _P
            _P(args.output).parent.mkdir(parents=True, exist_ok=True)
            _P(args.output).write_text(html, encoding="utf-8")
            print(f"Written to {args.output}")
        else:
            print(html)

    elif args.command == "outreach":
        from .outreach import classify_business, select_outreach_assets, build_outreach_email
        from .qualification import qualify_candidate
        from .search import _fetch_page
        from .record import load_lead, persist_lead_record

        include_inperson = not args.no_inperson

        if args.lead_id:
            # Load existing lead
            record = load_lead(args.lead_id)
            if not record:
                print(json.dumps({"error": f"Lead not found: {args.lead_id}"}))
                sys.exit(1)
            business_name = record["business_name"]
            classification = record.get("outreach_classification")
            if not classification:
                # Re-derive from stored qualification data
                from .models import QualificationResult
                q = QualificationResult(
                    lead=record["lead"],
                    rejection_reason=record.get("rejection_reason"),
                    business_name=business_name,
                    menu_evidence_found=record.get("menu_evidence_found", True),
                    machine_evidence_found=record.get("machine_evidence_found", False),
                )
                classification = classify_business(q)
        elif args.name and args.website:
            # Inline classification
            try:
                html = _fetch_page(args.website)
            except Exception as exc:
                print(json.dumps({"error": f"fetch_failed: {exc}"}))
                sys.exit(1)
            pages = [{"url": args.website, "html": html}]
            qualification = qualify_candidate(
                business_name=args.name,
                website=args.website,
                category=args.category,
                pages=pages,
                address=args.address,
            )
            business_name = args.name
            classification = classify_business(qualification)
        else:
            print("Error: provide --lead-id or both --name and --website")
            sys.exit(1)

        assets = select_outreach_assets(classification)
        email = build_outreach_email(
            business_name=business_name,
            classification=classification,
            include_inperson_line=include_inperson,
        )

        print(json.dumps({
            "business_name": business_name,
            "classification": classification,
            "assets": [str(p) for p in assets],
            "subject": email["subject"],
            "body": email["body"],
        }, indent=2, ensure_ascii=False))

    elif args.command == "contact-crawl":
        import asyncio
        from pathlib import Path as _P

        from .contact_crawler import default_places_api_key, run_contact_pipeline, write_results_csv
        from .utils import write_json

        categories = args.category or ["ラーメン", "居酒屋"]
        api_key = args.places_api_key if args.places_api_key is not None else default_places_api_key()
        result = asyncio.run(run_contact_pipeline(
            city=args.city,
            categories=categories,
            places_api_key=api_key,
            directory_urls=args.directory_url,
            max_places_per_category=args.max_places,
            max_directory_detail_pages=args.max_directory_detail_pages,
            concurrency=args.concurrency,
        ))

        if args.output_json:
            write_json(_P(args.output_json), result)
        if args.output_csv:
            write_results_csv(_P(args.output_csv), result["results"])
        print(json.dumps({
            "run_id": result["run_id"],
            "city": result["city"],
            "categories": result["categories"],
            "discovered_targets": result["discovered_targets"],
            "results_with_email": result["results_with_email"],
            "results_with_form_only": result["results_with_form_only"],
            "output_json": args.output_json,
            "output_csv": args.output_csv,
        }, indent=2, ensure_ascii=False))

    elif args.command == "build":
        from .custom_build import run_custom_build, CustomBuildInput
        from pathlib import Path as _P

        output_dir = _P(args.output) if args.output else _P("state/builds") / slugify(args.name)

        build_input = CustomBuildInput(
            restaurant_name=args.name,
            menu_items_text=args.menu_text,
            menu_photo_paths=args.menu_photo,
            ticket_machine_photo_path=args.ticket_photo,
            notes=args.notes,
        )

        try:
            result = run_custom_build(build_input, output_dir=output_dir)
            print(json.dumps({
                "status": "completed",
                "output_dir": str(result.output_dir),
                "food_pdf": str(result.food_pdf) if result.food_pdf else None,
                "drinks_pdf": str(result.drinks_pdf) if result.drinks_pdf else None,
                "combined_pdf": str(result.combined_pdf) if result.combined_pdf else None,
                "ticket_machine_pdf": str(result.ticket_machine_pdf) if result.ticket_machine_pdf else None,
                "menu_json": str(result.menu_json) if result.menu_json else None,
            }, indent=2, ensure_ascii=False))
        except Exception as exc:
            print(json.dumps({"error": str(exc)}, indent=2, ensure_ascii=False))
            sys.exit(1)

    elif args.command == "backup-state":
        from pathlib import Path as _P

        from .backup import backup_state

        result = backup_state(
            state_root=_P(args.state_root) if args.state_root else None,
            output_path=_P(args.output) if args.output else None,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "harden-state":
        from pathlib import Path as _P

        from .lead_dossier import migrate_state_leads

        result = migrate_state_leads(
            state_root=_P(args.state_root) if args.state_root else _P(__file__).resolve().parent.parent / "state",
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "audit-state":
        from pathlib import Path as _P

        from .state_audit import audit_state_leads, repair_state_leads

        state_root = _P(args.state_root) if args.state_root else _P(__file__).resolve().parent.parent / "state"
        result = repair_state_leads(state_root=state_root) if args.repair else audit_state_leads(state_root=state_root)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if not result["ok"]:
            sys.exit(1)

    elif args.command == "reclassify":
        from pathlib import Path as _P

        from .lead_dossier import reclassify_state_leads

        state_root = _P(args.state_root) if args.state_root else _P(__file__).resolve().parent.parent / "state"
        result = reclassify_state_leads(
            state_root=state_root,
            dry_run=not args.apply,
        )
        print(json.dumps({
            "dry_run": result["dry_run"],
            "no_send": result["no_send"],
            "reclassified_count": result["reclassified_count"],
            "skipped": result["skipped"],
            "unchanged": result["unchanged"],
        }, indent=2, ensure_ascii=False))

    elif args.command == "validate-emails":
        from pathlib import Path as _P

        from .lead_dossier import validate_lead_emails

        state_root = _P(args.state_root) if args.state_root else _P(__file__).resolve().parent.parent / "state"
        result = validate_lead_emails(
            state_root=state_root,
            dry_run=not args.apply,
        )
        print(json.dumps({
            "dry_run": result["dry_run"],
            "no_send": result["no_send"],
            "validated_count": result["validated_count"],
            "valid_count": result["valid_count"],
            "invalid_count": result["invalid_count"],
            "no_email_count": result["no_email_count"],
            "skipped_sent": result["skipped_sent"],
        }, indent=2, ensure_ascii=False))

    elif args.command == "verify-restaurant-leads":
        from pathlib import Path as _P

        from .restaurant_lead_verification import verify_restaurant_lead_queue

        state_root = _P(args.state_root) if args.state_root else _P(__file__).resolve().parent.parent / "state"
        summary_path = _P(args.summary_path) if args.summary_path else state_root / "lead_imports" / f"restaurant_lead_verification_{slugify(utc_now())}.json"
        result = verify_restaurant_lead_queue(
            state_root=state_root,
            dry_run=bool(args.dry_run),
            summary_path=summary_path,
        )
        print(json.dumps({
            "summary_path": str(summary_path),
            **result,
        }, indent=2, ensure_ascii=False))

    elif args.command == "launch-smoke":
        from pathlib import Path as _P

        from .launch_smoke import create_launch_smoke_test

        result = create_launch_smoke_test(
            lead_ids=args.lead_id,
            state_root=_P(args.state_root) if args.state_root else _P(__file__).resolve().parent.parent / "state",
            notes=args.notes,
            scenario=args.scenario,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "launch-decision":
        from pathlib import Path as _P

        from .launch_decision import write_no_send_batch_decision_brief

        result = write_no_send_batch_decision_brief(
            state_root=_P(args.state_root) if args.state_root else _P(__file__).resolve().parent.parent / "state",
            output_dir=_P(args.output_dir) if args.output_dir else None,
            label=str(args.label or "batch3-no-send"),
        )
        print(json.dumps({
            "recommendation": result["recommendation"],
            "real_outbound_allowed": result["real_outbound_allowed"],
            "aggregate": result["aggregate"],
            "candidate_pool": {
                "eligible_count": result["candidate_pool"]["eligible_count"],
                "candidate_set_complete": result["candidate_pool"]["candidate_set_complete"],
                "required_mix": result["candidate_pool"]["required_mix"],
            },
            "artifact_paths": result["artifact_paths"],
        }, indent=2, ensure_ascii=False))

    elif args.command == "review-batch":
        from pathlib import Path as _P

        from .review_batches import write_no_send_review_batch_brief

        result = write_no_send_review_batch_brief(
            state_root=_P(args.state_root) if args.state_root else _P(__file__).resolve().parent.parent / "state",
            output_dir=_P(args.output_dir) if args.output_dir else None,
            label=str(args.label or "pitch-card-review"),
            batch_size=int(args.batch_size),
        )
        print(json.dumps({
            "scope": result["scope"],
            "batch_size": result["batch_size"],
            "no_send_safety": result["no_send_safety"],
            "counts": {
                "records": result["counts"]["records"],
                "openable_pitch_cards": result["counts"]["openable_pitch_cards"],
                "unreviewed_openable_pitch_cards": result["counts"]["unreviewed_openable_pitch_cards"],
                "selected_review_queue": result["counts"]["selected_review_queue"],
                "pitch_card_counts": result["counts"]["pitch_card_counts"],
                "review_lane_counts": result["counts"]["review_lane_counts"],
                "profile_counts": result["counts"]["profile_counts"],
            },
            "glm": {
                "selected_batch_briefs": len(result["glm"]["selected_batch_briefs"]),
            },
            "pitch_pack_plan": {
                "selected_cards": result["pitch_pack_plan"]["selected_cards"],
                "stage": result["pitch_pack_plan"]["stage"],
                "email_policy": result["pitch_pack_plan"]["email_policy"],
                "contact_form_policy": result["pitch_pack_plan"]["contact_form_policy"],
                "attachment_policy_counts": result["pitch_pack_plan"]["attachment_policy_counts"],
                "glm_reference_asset_counts": result["pitch_pack_plan"]["glm_reference_asset_counts"],
            },
            "review_throughput": {
                "operator_pack_count": result["review_throughput"]["operator_pack_count"],
                "operator_pack_size": result["review_throughput"]["operator_pack_size"],
                "allowed_operator_outcomes": result["review_throughput"]["allowed_operator_outcomes"],
                "forbidden_actions": result["review_throughput"]["forbidden_actions"],
                "required_state": result["review_throughput"]["required_state"],
            },
            "artifact_paths": result["artifact_paths"],
        }, indent=2, ensure_ascii=False))

    elif args.command == "review-wave":
        from pathlib import Path as _P

        from .review_batches import write_no_send_review_wave_brief

        result = write_no_send_review_wave_brief(
            state_root=_P(args.state_root) if args.state_root else _P(__file__).resolve().parent.parent / "state",
            output_dir=_P(args.output_dir) if args.output_dir else None,
            label=str(args.label or "pitch-card-review-wave"),
            batch_size=int(args.batch_size),
        )
        print(json.dumps({
            "scope": result["scope"],
            "batch_size": result["batch_size"],
            "no_send_safety": result["no_send_safety"],
            "counts": {
                "records": result["counts"]["records"],
                "openable_pitch_cards": result["counts"]["openable_pitch_cards"],
                "unreviewed_openable_pitch_cards": result["counts"]["unreviewed_openable_pitch_cards"],
                "approved_route_review_cards": result["counts"]["approved_route_review_cards"],
                "batch_count": result["counts"]["batch_count"],
                "operator_pack_count": result["counts"]["operator_pack_count"],
                "pitch_card_counts": result["counts"]["pitch_card_counts"],
                "review_lane_counts": result["counts"]["review_lane_counts"],
                "profile_counts": result["counts"]["profile_counts"],
            },
            "glm": {
                "wave_briefs": len(result["glm"]["wave_briefs"]),
            },
            "pitch_pack_plan": {
                "selected_cards": result["pitch_pack_plan"]["selected_cards"],
                "stage": result["pitch_pack_plan"]["stage"],
                "email_policy": result["pitch_pack_plan"]["email_policy"],
                "contact_form_policy": result["pitch_pack_plan"]["contact_form_policy"],
                "attachment_policy_counts": result["pitch_pack_plan"]["attachment_policy_counts"],
                "glm_reference_asset_counts": result["pitch_pack_plan"]["glm_reference_asset_counts"],
            },
            "review_throughput": {
                "operator_pack_count": result["review_throughput"]["operator_pack_count"],
                "operator_pack_size": result["review_throughput"]["operator_pack_size"],
                "allowed_operator_outcomes": result["review_throughput"]["allowed_operator_outcomes"],
                "forbidden_actions": result["review_throughput"]["forbidden_actions"],
                "required_state": result["review_throughput"]["required_state"],
            },
            "batches": [
                {
                    "batch_id": batch["batch_id"],
                    "card_count": batch["card_count"],
                    "review_lane_counts": batch["review_lane_counts"],
                    "operator_pack_count": batch["review_throughput"]["operator_pack_count"],
                }
                for batch in result["batches"]
            ],
            "artifact_paths": result["artifact_paths"],
        }, indent=2, ensure_ascii=False))

    elif args.command == "needs-more-info-enrichment":
        from pathlib import Path as _P

        from .review_enrichment import write_needs_more_info_enrichment_plan

        result = write_needs_more_info_enrichment_plan(
            state_root=_P(args.state_root) if args.state_root else _P(__file__).resolve().parent.parent / "state",
            output_dir=_P(args.output_dir) if args.output_dir else None,
            label=str(args.label or "needs-more-info-enrichment"),
            batch_size=int(args.batch_size),
        )
        print(json.dumps({
            "scope": result["scope"],
            "batch_size": result["batch_size"],
            "no_send_safety": result["no_send_safety"],
            "counts": result["counts"],
            "allowed_enrichment_outcomes": result["allowed_enrichment_outcomes"],
            "forbidden_actions": result["forbidden_actions"],
            "required_state": result["required_state"],
            "batches": [
                {
                    "batch_id": batch["batch_id"],
                    "card_count": batch["card_count"],
                    "enrichment_lane_counts": batch["enrichment_lane_counts"],
                    "operator_pack_count": batch["operator_pack_count"],
                }
                for batch in result["batches"]
            ],
            "artifact_paths": result["artifact_paths"],
        }, indent=2, ensure_ascii=False))

    elif args.command == "restaurant-execution-plan":
        from pathlib import Path as _P

        from .restaurant_execution_plan import write_restaurant_execution_plan

        result = write_restaurant_execution_plan(
            state_root=_P(args.state_root) if args.state_root else _P(__file__).resolve().parent.parent / "state",
            output_dir=_P(args.output_dir) if args.output_dir else None,
            label=str(args.label or "restaurant-lead-execution-plan"),
            batch_size=int(args.batch_size),
            representative_count=int(args.representative_count),
        )
        print(json.dumps({
            "scope": result["scope"],
            "finished_until_external_gate": result["finished_until_external_gate"],
            "external_gates": result["external_gates"],
            "no_send_safety": result["no_send_safety"],
            "queue": result["queue"],
            "needs_more_info_enrichment": result["needs_more_info_enrichment"],
            "phase_status": [
                {"phase": item["phase"], "status": item["status"]}
                for item in result["phase_status"]
            ],
            "glm_design_requests": [
                {
                    "profile_id": item["profile_id"],
                    "selected_cards": item["selected_cards"],
                    "request_status": item["request_status"],
                    "request_glm_now": item["request_glm_now"],
                }
                for item in result["glm_design_requests"]
            ],
            "promotion_gate_preview": {
                "live_promotion_allowed": result["promotion_gate_preview"]["live_promotion_allowed"],
                "candidate_count": result["promotion_gate_preview"]["candidate_count"],
                "blocker_counts": result["promotion_gate_preview"]["blocker_counts"],
            },
            "inline_pitch_pack_plan": {
                "draft_generation_allowed": result["inline_pitch_pack_plan"]["draft_generation_allowed"],
                "planned_cards": result["inline_pitch_pack_plan"]["planned_cards"],
                "glm_reference_asset_counts": result["inline_pitch_pack_plan"]["glm_reference_asset_counts"],
            },
            "artifact_paths": result["artifact_paths"],
        }, indent=2, ensure_ascii=False))

    elif args.command == "run8-readiness":
        from pathlib import Path as _P

        from .constants import PROJECT_ROOT
        from .run8_readiness import run_run8_readiness

        result = run_run8_readiness(
            state_root=_P(args.state_root) if args.state_root else PROJECT_ROOT / "state",
            docs_root=_P(args.docs_root) if args.docs_root else PROJECT_ROOT / "docs",
            capture_screenshots=not bool(args.skip_screenshots),
            run_id=args.run_id,
        )
        print(json.dumps({
            "run_id": result["run_id"],
            "ok_until_send_gate": result["ok_until_send_gate"],
            "controlled_launch_selection_allowed": result["controlled_launch_selection_allowed"],
            "blockers": result["blockers"],
            "report_path": result["report_path"],
            "screenshot_dir": result["screenshots"].get("screenshot_dir", ""),
            "export_qa_reports": {
                key: value.get("export_qa_report_path", "")
                for key, value in result["artifacts"]["exports"].items()
            },
            "external_send_performed": result["external_send_performed"],
            "real_launch_batch_created": result["real_launch_batch_created"],
        }, indent=2, ensure_ascii=False))

    elif args.command == "production-sim":
        from pathlib import Path as _P

        from .production_sim import (
            DEFAULT_CORPUS,
            DEFAULT_OUTPUT_ROOT,
            DEFAULT_REPLAY_ROOT,
            DEFAULT_SCREENSHOT_ROOT,
            collect_corpus,
            load_report,
            prepare_labeling_workflow,
            recommend_controlled_launch,
            report_fails_on,
            run_replay,
        )
        from .search_provider import search_provider_requires_api_key
        from .search_replay import benchmark_replay_corpus, fixture_collect_adapters, reconcile_label_contact_policy

        fail_on = {item.strip().upper() for item in str(getattr(args, "fail_on", "") or "").split(",") if item.strip()}
        if args.production_sim_command == "collect":
            maps_search_fn = web_search_fn = fetch_page_fn = None
            if args.offline_fixture:
                maps_search_fn, web_search_fn, fetch_page_fn = fixture_collect_adapters(_P(args.offline_fixture))
            result = collect_corpus(
                run_id=args.run_id,
                city_set=args.city_set,
                cities=list(args.city or []) or None,
                category=args.category,
                limit_per_job=int(args.limit_per_job or 5),
                stage=args.stage,
                serper_api_key=(
                    str(args.api_key or os.environ.get("SERPER_API_KEY", ""))
                    if search_provider_requires_api_key(args.search_provider)
                    else str(args.api_key or "")
                ),
                search_provider=args.search_provider,
                output_root=_P(args.output_root) if args.output_root else DEFAULT_OUTPUT_ROOT,
                replay_root=_P(args.replay_root) if args.replay_root else DEFAULT_REPLAY_ROOT,
                screenshot_root=_P(args.screenshot_root) if args.screenshot_root else DEFAULT_SCREENSHOT_ROOT,
                fetch_timeout_seconds=int(args.fetch_timeout_seconds if args.fetch_timeout_seconds is not None else 8),
                contact_pages_per_candidate=int(args.contact_pages_per_candidate if args.contact_pages_per_candidate is not None else 2),
                evidence_pages_per_candidate=int(args.evidence_pages_per_candidate if args.evidence_pages_per_candidate is not None else 2),
                maps_search_fn=maps_search_fn,
                web_search_fn=web_search_fn,
                fetch_page_fn=fetch_page_fn,
            )
            print(json.dumps({
                "run_id": result["run_id"],
                "production_ready": result["production_ready"],
                "p0": result["p0"],
                "p1": result["p1"],
                "p2": result["p2"],
                "candidate_count": result["candidate_count"],
                "labeled_count": result["labeled_count"],
                "collection_manifest_path": result["collection_manifest_path"],
                "report_path": result["report_path"],
                "external_send_performed": result["external_send_performed"],
                "real_launch_batch_created": result["real_launch_batch_created"],
            }, indent=2, ensure_ascii=False))
            if report_fails_on(result, fail_on):
                sys.exit(1)
        elif args.production_sim_command == "replay":
            result = run_replay(
                corpus_dir=_P(args.corpus) if args.corpus else DEFAULT_CORPUS,
                run_id=args.run_id,
                output_root=_P(args.output_root) if args.output_root else DEFAULT_OUTPUT_ROOT,
                replay_root=_P(args.replay_root) if args.replay_root else DEFAULT_REPLAY_ROOT,
                screenshot_root=_P(args.screenshot_root) if args.screenshot_root else DEFAULT_SCREENSHOT_ROOT,
                screenshots=bool(args.screenshots),
                dashboard_port=int(args.dashboard_port or 0),
            )
            print(json.dumps({
                "run_id": result["run_id"],
                "production_ready": result["production_ready"],
                "p0": result["p0"],
                "p1": result["p1"],
                "p2": result["p2"],
                "report_path": result["report_path"],
                "screenshots_dir": result["screenshots_dir"],
                "external_send_performed": result["external_send_performed"],
                "real_launch_batch_created": result["real_launch_batch_created"],
            }, indent=2, ensure_ascii=False))
            if report_fails_on(result, fail_on):
                sys.exit(1)
        elif args.production_sim_command == "label":
            result = prepare_labeling_workflow(
                corpus_dir=_P(args.corpus),
                sample_size=int(args.sample_size or 120),
                seed=str(args.seed or "production-sim-labeling-v1"),
                output_root=_P(args.output_root) if args.output_root else DEFAULT_OUTPUT_ROOT,
            )
            print(json.dumps({
                "run_id": result["run_id"],
                "production_ready": result["production_ready"],
                "p0": result["p0"],
                "p1": result["p1"],
                "p2": result["p2"],
                "candidate_count": result["candidate_count"],
                "labeled_count": result["labeled_count"],
                "labeling_sample_count": result["labeling_sample_count"],
                "draft_label_count": result["draft_label_count"],
                "labeling_sample_path": result["labeling_sample_path"],
                "labeling_review_queue_path": result["labeling_review_queue_path"],
                "labeling_review_shortlist_path": result["labeling_review_shortlist_path"],
                "offline_replay_ready": result["offline_replay_ready"],
                "dashboard_verification_ready": result["dashboard_verification_ready"],
                "external_send_performed": result["external_send_performed"],
                "real_launch_batch_created": result["real_launch_batch_created"],
            }, indent=2, ensure_ascii=False))
            if report_fails_on(result, fail_on):
                sys.exit(1)
        elif args.production_sim_command == "report":
            run_path = _P(args.run)
            if not run_path.exists():
                run_path = DEFAULT_OUTPUT_ROOT / args.run
            result = load_report(run_path)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            if report_fails_on(result, fail_on):
                sys.exit(1)
        elif args.production_sim_command == "reconcile-label-policy":
            result = reconcile_label_contact_policy(_P(args.corpus))
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.production_sim_command == "benchmark":
            result = benchmark_replay_corpus(
                corpus_dir=_P(args.corpus),
                baseline_corpus_dir=_P(args.baseline_corpus) if args.baseline_corpus else None,
                run_label=str(args.run_label or ""),
                output_dir=_P(args.output_dir) if args.output_dir else None,
            )
            print(json.dumps({
                "run_label": result["run_label"],
                "corpus": result["corpus"],
                "passed": result["comparison"]["passed"],
                "meets_targets": result["comparison"]["meets_targets"],
                "metrics": {
                    "search_failure_count": result["metrics"]["search_failure_count"],
                    "deduped_candidates_per_job": result["metrics"]["deduped_candidates_per_job"],
                    "fetch_failure_rate": result["metrics"]["fetch_failure_rate"],
                    "first_party_site_rate": result["metrics"]["first_party_site_rate"],
                    "expected_ready_label_count": result["metrics"]["expected_ready_label_count"],
                    "unsupported_ready_label_count": result["metrics"]["unsupported_ready_label_count"],
                },
                "report_path": result["report_path"],
                "report_markdown_path": result["report_markdown_path"],
                "external_send_performed": result["external_send_performed"],
                "real_launch_batch_created": result["real_launch_batch_created"],
            }, indent=2, ensure_ascii=False))
        elif args.production_sim_command == "recommend":
            result = recommend_controlled_launch(
                run=args.run,
                lead_ids=list(args.lead_id or []),
                check_live_urls=not bool(args.skip_live_url_check),
            )
            print(json.dumps({
                "run_id": result["run_id"],
                "production_ready": result["production_ready"],
                "controlled_launch_recommendation": result["controlled_launch_recommendation"],
                "p0": result["p0"],
                "p1": result["p1"],
                "p2": result["p2"],
                "no_send_smoke": result["no_send_smoke"],
                "report_path": result["report_path"],
                "external_send_performed": result["external_send_performed"],
                "real_launch_batch_created": result["real_launch_batch_created"],
            }, indent=2, ensure_ascii=False))
            if report_fails_on(result, fail_on):
                sys.exit(1)
        else:
            sim_cmd.print_help()

    elif args.command == "discover":
        from .email_discovery import discover_emails, load_config
        from .email_discovery.config import DiscoveryConfig, PersistenceConfig

        config = load_config(args.config)
        if args.dry_run:
            config.dry_run = True
        if args.max_leads:
            config.max_leads = args.max_leads
        if args.output_csv:
            config.persistence.csv_output_path = args.output_csv
        if args.output_jsonl:
            config.persistence.jsonl_output_path = args.output_jsonl

        results = discover_emails(input_csv=args.input, config=config)
        summary = {
            "total": len(results),
            "launch_ready": sum(1 for r in results if r.launch_ready),
            "with_email": sum(1 for r in results if r.best_email),
            "with_contact_form": sum(1 for r in results if r.contact_form_url),
            "avg_score": round(sum(r.confidence_score for r in results) / max(len(results), 1), 1),
            "csv_path": config.persistence.csv_output_path,
            "jsonl_path": config.persistence.jsonl_output_path,
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))

    elif args.command == "enrich":
        from pathlib import Path as _P

        from .email_discovery.bridge import enrich_lead
        from .email_discovery.config import load_config
        from .lead_dossier import ensure_lead_dossier
        from .record import list_leads, load_lead, normalise_lead_contacts, persist_lead_record

        state_root = _P(args.state_root) if args.state_root else None
        if args.lead_id:
            lead = load_lead(args.lead_id, state_root=state_root)
            if not lead:
                print(json.dumps({"error": f"Lead not found: {args.lead_id}"}, ensure_ascii=False))
                sys.exit(1)
            leads = [lead]
        else:
            leads = list_leads(state_root=state_root)

        def has_email_contact(lead_record: dict) -> bool:
            return any(
                contact.get("type") == "email" and contact.get("actionable")
                for contact in normalise_lead_contacts(lead_record)
            )

        def lead_score(lead_record: dict) -> float:
            value = lead_record.get("email_discovery_score")
            if value in (None, ""):
                value = lead_record.get("lead_score_v1", 0)
            try:
                return float(value or 0)
            except (TypeError, ValueError):
                return 0.0

        selected = []
        skipped = []
        for lead in leads:
            lead_id = lead.get("lead_id", "")
            if args.no_contact and has_email_contact(lead):
                skipped.append({"lead_id": lead_id, "reason": "email_contact_exists"})
                continue
            if args.score_below is not None and lead_score(lead) >= float(args.score_below):
                skipped.append({"lead_id": lead_id, "reason": "score_not_below_threshold"})
                continue
            selected.append(lead)
            if args.max_leads and len(selected) >= args.max_leads:
                break

        config = load_config(args.config)
        if args.dry_run:
            config.dry_run = True
        results = []
        errors = []
        for lead in selected:
            lead_id = str(lead.get("lead_id") or "")
            before_contacts = len(normalise_lead_contacts(lead))
            try:
                updated = ensure_lead_dossier(enrich_lead(lead, config=config))
                path = None
                if not args.dry_run:
                    path = persist_lead_record(updated, state_root=state_root)
                after_contacts = len(normalise_lead_contacts(updated))
                results.append({
                    "lead_id": lead_id,
                    "business_name": updated.get("business_name", ""),
                    "email": updated.get("email", ""),
                    "primary_contact_type": (updated.get("primary_contact") or {}).get("type", ""),
                    "contacts_added": max(0, after_contacts - before_contacts),
                    "email_discovery_score": updated.get("email_discovery_score", 0),
                    "persisted": not args.dry_run,
                    "path": str(path) if path else "",
                })
            except Exception as exc:
                errors.append({"lead_id": lead_id, "error": str(exc)})

        summary = {
            "total_considered": len(leads),
            "selected": len(selected),
            "enriched": len(results),
            "skipped": len(skipped),
            "dry_run": bool(args.dry_run),
            "results": results,
            "errors": errors,
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        if errors:
            sys.exit(1)

    elif args.command == "hosted-sample":
        from pathlib import Path as _P

        from .hosted_sample import default_sample_docs_root, ensure_hosted_menu_sample
        from .models import QualificationResult
        from .outreach import build_manual_outreach_message, classify_business
        from .record import authoritative_business_name, get_primary_contact, list_leads, load_lead, persist_lead_record

        state_root = _P(args.state_root) if args.state_root else _P(__file__).resolve().parent.parent / "state"
        docs_root = _P(args.docs_root) if args.docs_root else default_sample_docs_root(state_root=state_root)
        if args.lead_id:
            lead = load_lead(args.lead_id, state_root=state_root)
            if not lead:
                print(json.dumps({"error": f"Lead not found: {args.lead_id}"}, ensure_ascii=False))
                sys.exit(1)
            leads = [lead]
        else:
            leads = [lead for lead in list_leads(state_root=state_root) if lead.get("lead") is True]
            if args.max_leads:
                leads = leads[: int(args.max_leads)]

        results = []
        errors = []
        for lead in leads:
            lead_id = str(lead.get("lead_id") or "")
            business_name = authoritative_business_name(lead)
            classification = str(lead.get("outreach_classification") or "") or classify_business(QualificationResult(
                lead=lead.get("lead") is True,
                rejection_reason=lead.get("rejection_reason"),
                business_name=business_name,
                menu_evidence_found=lead.get("menu_evidence_found", True),
                machine_evidence_found=lead.get("machine_evidence_found", False),
            ))
            profile = _cli_effective_profile(lead)
            updated, sample = ensure_hosted_menu_sample(
                lead,
                docs_root=docs_root,
                state_root=state_root,
                base_url=args.public_base_url,
                dry_run=bool(args.dry_run),
            )
            primary_contact = get_primary_contact(updated) or {}
            primary_contact_type = str(primary_contact.get("type") or "")
            draft = build_manual_outreach_message(
                business_name=business_name,
                classification=classification,
                channel="contact_form",
                establishment_profile=profile,
                include_inperson_line=updated.get("outreach_include_inperson", True),
                lead_dossier=updated.get("lead_evidence_dossier") or {},
                sample_menu_url=str(sample.get("sample_menu_url") or ""),
            )
            if primary_contact_type == "contact_form":
                updated["outreach_classification"] = classification
                updated["outreach_assets_selected"] = []
                updated["outreach_asset_template_family"] = "no_first_contact_attachments"
                updated["message_variant"] = f"contact_form:{classification}:{profile}"
                updated["outreach_draft_subject"] = ""
                updated["outreach_draft_body"] = draft["body"]
                updated["outreach_draft_english_body"] = draft["english_body"]
                updated["outreach_draft_manually_edited"] = False
                updated["outreach_draft_edited_at"] = ""
                if not sample.get("ok"):
                    updated["contact_form_outreach_ready"] = False
                    reasons = list(updated.get("launch_readiness_reasons") or [])
                    if "hosted_sample_publish_failed" not in reasons:
                        reasons.append("hosted_sample_publish_failed")
                    updated["launch_readiness_status"] = "manual_review"
                    updated["launch_readiness_reasons"] = reasons

            if not args.dry_run:
                persist_lead_record(updated, state_root=state_root)

            sample_public = {key: value for key, value in sample.items() if key != "html"}
            result_item = {
                **sample_public,
                "lead_id": lead_id,
                "business_name": business_name,
                "primary_contact_type": primary_contact_type,
                "contact_form_outreach_text": draft["body"],
                "persisted": not bool(args.dry_run),
            }
            results.append(result_item)
            if not sample.get("ok"):
                errors.append({"lead_id": lead_id, "error": sample.get("error") or "publish_failed"})

        summary = {
            "selected": len(leads),
            "published": sum(1 for item in results if item.get("published")),
            "dry_run": bool(args.dry_run),
            "docs_root": str(docs_root),
            "results": results,
            "errors": errors,
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        if errors:
            sys.exit(1)

    else:
        parser.print_help()


def _cli_effective_profile(lead: dict) -> str:
    profile = str(lead.get("establishment_profile") or "").strip()
    if profile:
        return profile
    category = str(lead.get("primary_category_v1") or "").strip()
    if category == "izakaya":
        return "izakaya_food_and_drinks"
    return "ramen_only"


if __name__ == "__main__":
    main()
