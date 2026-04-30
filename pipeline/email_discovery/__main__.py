"""Run the email discovery pipeline from the command line."""

from __future__ import annotations

import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser(description="WebSerper email discovery")
    parser.add_argument("--input", required=True, help="Input CSV path")
    parser.add_argument("--config", default="email_discovery.yaml", help="Config YAML path")
    parser.add_argument("--dry-run", action="store_true", help="Skip all network requests")
    parser.add_argument("--max-leads", type=int, default=0, help="Limit leads (0=all)")
    parser.add_argument("--output-csv", default=None, help="CSV output path")
    parser.add_argument("--output-jsonl", default=None, help="JSONL output path")
    args = parser.parse_args()

    from .config import load_config
    from .pipeline import discover_emails

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
    print(json.dumps({
        "total": len(results),
        "launch_ready": sum(1 for result in results if result.launch_ready),
        "with_email": sum(1 for result in results if result.best_email),
        "with_contact_form": sum(1 for result in results if result.contact_form_url),
        "avg_score": round(sum(result.confidence_score for result in results) / max(len(results), 1), 1),
        "csv_path": config.persistence.csv_output_path,
        "jsonl_path": config.persistence.jsonl_output_path,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
