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

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
