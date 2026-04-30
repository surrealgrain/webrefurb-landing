"""Output writer: CSV and JSONL export for enriched leads."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import EnrichedLead

# CSV column order
CSV_COLUMNS = [
    "lead_id",
    "shop_name",
    "normalized_shop_name",
    "genre",
    "genre_confidence",
    "address",
    "prefecture",
    "city",
    "phone",
    "official_site_url",
    "operator_company_name",
    "operator_company_url",
    "best_email",
    "best_email_type",
    "all_emails",
    "contact_form_url",
    "email_source_url",
    "email_source_snippet",
    "no_sales_warning_detected",
    "menu_url",
    "menu_detected",
    "tourist_area_signal",
    "online_shop_detected",
    "tokushoho_page_url",
    "recruitment_page_url",
    "pr_page_url",
    "launch_ready",
    "confidence_score",
    "reason_codes",
    "next_best_action",
    "crawl_timestamp",
]


def write_csv(leads: list[EnrichedLead], path: str) -> str:
    """Write enriched leads to CSV.

    Returns the output path.
    """
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for lead in leads:
            writer.writerow(lead.to_csv_row())

    return str(out_path)


def write_jsonl(leads: list[EnrichedLead], path: str) -> str:
    """Write enriched leads to JSONL (one JSON object per line).

    Returns the output path.
    """
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        for lead in leads:
            f.write(json.dumps(lead.to_dict(), ensure_ascii=False) + "\n")

    return str(out_path)


def write_outputs(
    leads: list[EnrichedLead],
    csv_path: str = "state/email_discovery_output.csv",
    jsonl_path: str = "state/email_discovery_output.jsonl",
) -> dict[str, str]:
    """Write both CSV and JSONL outputs.

    Returns dict with paths.
    """
    paths = {}
    paths["csv"] = write_csv(leads, csv_path)
    paths["jsonl"] = write_jsonl(leads, jsonl_path)
    return paths
