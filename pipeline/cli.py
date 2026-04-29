from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .utils import load_project_env, slugify


def main() -> None:
    load_project_env()

    parser = argparse.ArgumentParser(description="WebRefurbMenu pipeline CLI")
    sub = parser.add_subparsers(dest="command")

    # search
    search_cmd = sub.add_parser("search", help="Search and qualify leads")
    search_cmd.add_argument("--query", required=True)
    search_cmd.add_argument("--api-key", default="")
    search_cmd.add_argument("--category", default="ramen")

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
        help="Category to discover; repeat for both ramen and izakaya",
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

    smoke_cmd = sub.add_parser("launch-smoke", help="Create a no-send launch rehearsal from ready leads")
    smoke_cmd.add_argument("--lead-id", action="append", required=True, help="Lead ID to include; repeat 5-10 times")
    smoke_cmd.add_argument("--state-root", default=None, help="Override state root")
    smoke_cmd.add_argument("--notes", default="", help="Operator notes for the rehearsal")
    smoke_cmd.add_argument("--scenario", default="real_world_no_send", help="Smoke-test scenario label")

    args = parser.parse_args()

    if args.command == "search":
        from .search import search_and_qualify
        result = search_and_qualify(
            query=args.query,
            serper_api_key=args.api_key,
            category=args.category,
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
            "results_with_line": result["results_with_line"],
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

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
