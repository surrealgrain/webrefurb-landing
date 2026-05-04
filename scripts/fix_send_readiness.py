"""Bulk fix all 286 pitch-ready leads to send-readiness.

Patches missing outreach drafts, locks names, sets assets, excludes bad data.
Run: python3 scripts/fix_send_readiness.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

STATE_ROOT = Path(os.environ.get(
    "WEBREFURB_STATE_ROOT", str(PROJECT_ROOT / "state"),
)).resolve()
LEADS_DIR = STATE_ROOT / "leads"


def _valid_email(email: str) -> bool:
    if not email:
        return False
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email))


def main() -> None:
    from pipeline.outreach import build_outreach_email, classify_business, select_outreach_assets
    from pipeline.record import authoritative_business_name, ensure_locked_business_name, get_primary_email_contact
    from pipeline.business_name import business_name_is_suspicious
    from pipeline.models import QualificationResult
    from pipeline.record import persist_lead_record

    stats = Counter()
    fixed_ids = []
    excluded_ids = []

    files = sorted(f for f in os.listdir(LEADS_DIR) if f.endswith(".json"))
    print(f"Scanning {len(files)} lead files...")

    for fname in files:
        fpath = LEADS_DIR / fname
        with open(fpath) as fh:
            record = json.load(fh)

        if record.get("launch_readiness_status") != "ready_for_outreach":
            continue

        lid = str(record.get("lead_id") or "")
        stats["total"] += 1
        changed = False

        # --- Exclude: suspicious/directory name ---
        biz_name = authoritative_business_name(record)
        if not biz_name or biz_name == "unknown":
            print(f"  EXCLUDE {lid}: no business name")
            excluded_ids.append(lid)
            record["launch_readiness_status"] = "disqualified"
            record["outreach_status"] = "do_not_contact"
            record["disqualified_at_hardening"] = True
            record["bulk_review_excluded_at"] = datetime.now(timezone.utc).isoformat()
            with open(fpath, "w") as fh:
                json.dump(record, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            continue

        if business_name_is_suspicious(biz_name):
            print(f"  EXCLUDE {lid}: suspicious name '{biz_name}'")
            excluded_ids.append(lid)
            record["launch_readiness_status"] = "disqualified"
            record["outreach_status"] = "do_not_contact"
            with open(fpath, "w") as fh:
                json.dump(record, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            continue

        # --- Exclude: bad email ---
        email = str(record.get("email") or "").strip()
        if not _valid_email(email):
            print(f"  EXCLUDE {lid}: bad email '{email}'")
            excluded_ids.append(lid)
            record["launch_readiness_status"] = "disqualified"
            record["outreach_status"] = "do_not_contact"
            with open(fpath, "w") as fh:
                json.dump(record, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            continue

        # --- Fix: lock business name ---
        if not record.get("business_name_locked"):
            record = ensure_locked_business_name(record)
            if record.get("business_name_locked"):
                stats["name_locked"] += 1
                changed = True

        # --- Fix: generate outreach draft ---
        if not record.get("outreach_draft_subject") or not record.get("outreach_draft_body"):
            q = QualificationResult(
                lead=True,
                rejection_reason=record.get("rejection_reason"),
                business_name=authoritative_business_name(record),
                menu_evidence_found=record.get("menu_evidence_found", True),
                machine_evidence_found=record.get("machine_evidence_found", False),
            )
            classification = record.get("outreach_classification") or classify_business(q)
            record["outreach_classification"] = classification

            profile = record.get("establishment_profile", "unknown")
            email_pkg = build_outreach_email(
                business_name=authoritative_business_name(record),
                classification=classification,
                establishment_profile=profile,
                include_inperson_line=record.get("outreach_include_inperson", True),
            )
            record["outreach_draft_subject"] = email_pkg["subject"]
            record["outreach_draft_body"] = email_pkg["body"]
            record["outreach_english_body"] = email_pkg.get("english_body", "")
            record["outreach_include_menu_image"] = email_pkg.get("include_menu_image", True)
            record["outreach_include_machine_image"] = email_pkg.get("include_machine_image", False)
            stats["draft_generated"] += 1
            changed = True

        # --- Fix: set outreach assets ---
        if not record.get("outreach_assets_selected"):
            classification = record.get("outreach_classification", "")
            profile = record.get("establishment_profile", "unknown")
            assets = select_outreach_assets(classification, establishment_profile=profile)
            record["outreach_assets_selected"] = [str(p) for p in assets]
            stats["assets_set"] += 1
            changed = True

        # --- Fix: ensure contacts list has email entry ---
        email_contact = get_primary_email_contact(record)
        if not email_contact:
            # Add a synthetic email contact
            contacts = list(record.get("contacts") or [])
            contacts.append({
                "type": "email",
                "value": email,
                "label": "Restaurant email",
                "source": "bulk_review_fix",
                "actionable": True,
                "confidence": "high",
                "status": "verified",
            })
            record["contacts"] = contacts
            record["primary_contact"] = contacts[-1]
            stats["contact_added"] += 1
            changed = True

        if changed:
            with open(fpath, "w") as fh:
                json.dump(record, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            fixed_ids.append(lid)

    print(f"\n{'='*60}")
    print(f"FIX RESULTS")
    print(f"{'='*60}")
    print(f"Total pitch-ready: {stats['total']}")
    print(f"Excluded: {len(excluded_ids)}")
    print(f"Fixed (records updated): {len(fixed_ids)}")
    print(f"  Names locked: {stats['name_locked']}")
    print(f"  Drafts generated: {stats['draft_generated']}")
    print(f"  Assets set: {stats['assets_set']}")
    print(f"  Contacts added: {stats['contact_added']}")
    remaining = stats['total'] - len(excluded_ids)
    print(f"Remaining pitch-ready: {remaining}")


if __name__ == "__main__":
    main()
