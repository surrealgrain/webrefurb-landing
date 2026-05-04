from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contact_crawler import is_usable_business_email
from .constants import (
    LEAD_CATEGORY_IZAKAYA_DRINK_COURSE_GUIDE,
    LEAD_CATEGORY_IZAKAYA_MENU_TRANSLATION,
    LEAD_CATEGORY_RAMEN_MENU_TRANSLATION,
)
from .evidence import chain_or_franchise_signal_reason, is_chain_business
from .outreach import select_outreach_assets
from .record import list_leads, normalise_lead_contacts, persist_lead_record
from .restaurant_lead_verification import verify_restaurant_lead_record
from .scoring import recommend_package_details_for_record
from .utils import ensure_dir, sha256_text, slugify, utc_now, write_json


DEFAULT_RESEARCH_ROOT = Path("/Users/chrisparker/Documents/Codex/2026-05-01/goal-use-computer-mode-with-chrome")
DEFAULT_INPUT_FILES = (
    "restaurant_email_leads.json",
    "restaurant_email_leadsv2.json",
    "restaurant_email_leadsv2_medium_quality.json",
    "restaurant_email_leadsv2_low_quality.json",
    "restaurant_email_leadsv3.json",
    "restaurant_email_leadsv3_medium_quality.json",
    "restaurant_email_leadsv3_low_quality.json",
)

CITY_ORDER = {
    "Tokyo": 0,
    "Osaka": 1,
    "Sapporo": 2,
    "Fukuoka": 3,
    "Kyoto": 4,
}
QUALITY_ORDER = {"v1_clean": 0, "high": 1, "medium": 2, "low": 3}

BAD_EMAIL_FRAGMENTS = (
    "example",
    "sample",
    "tabelog",
    "gnavi",
    "hotpepper",
    "recruit",
    "career",
    "job",
    "press",
    "media",
    "prtimes",
    "noreply",
    "no-reply",
    "support@",
    "info@kakaku",
    "privacy",
    "abuse",
    "postmaster",
    "webmaster",
    "admin@",
    "instagram",
)

BAD_NAME_FRAGMENTS = (
    "レポート",
    "求人",
    "採用",
    "通販",
    "ランキング",
    "まとめ",
)

RAMEN_MENU_TYPES = {
    "ramen",
    "tsukemen",
    "abura_soba",
    "mazesoba",
    "tantanmen",
    "chuka_soba",
}

MENU_TYPE_TOKENS = (
    ("yakitori", ("yakitori", "焼き鳥", "焼鳥", "やきとり")),
    ("kushiyaki", ("kushiyaki", "串焼き")),
    ("yakiton", ("yakiton", "やきとん")),
    ("kushikatsu", ("kushikatsu", "串カツ", "串かつ")),
    ("kushiage", ("kushiage", "串揚げ")),
    ("seafood_izakaya", ("seafood", "海鮮", "魚", "鮮魚")),
    ("oden", ("oden", "おでん")),
    ("tachinomi", ("tachinomi", "立ち飲み", "立飲み")),
    ("robatayaki", ("robatayaki", "炉端焼き", "炉端")),
    ("sakaba", ("sakaba", "酒場")),
    ("tsukemen", ("tsukemen", "つけ麺")),
    ("abura_soba", ("abura", "油そば")),
    ("mazesoba", ("mazesoba", "まぜそば")),
    ("tantanmen", ("tantanmen", "担々麺", "坦々麺")),
    ("chuka_soba", ("chuka", "中華そば")),
)

IZAKAYA_PROFILE_BY_MENU_TYPE = {
    "yakitori": "izakaya_yakitori_kushiyaki",
    "kushiyaki": "izakaya_yakitori_kushiyaki",
    "yakiton": "izakaya_yakitori_kushiyaki",
    "kushikatsu": "izakaya_kushiage",
    "kushiage": "izakaya_kushiage",
    "seafood_izakaya": "izakaya_seafood_sake_oden",
    "oden": "izakaya_seafood_sake_oden",
    "tachinomi": "izakaya_tachinomi",
    "robatayaki": "izakaya_robatayaki",
    "sakaba": "izakaya_food_and_drinks",
    "izakaya": "izakaya_food_and_drinks",
}

PROFILE_LABELS = {
    "ramen_only": "Ramen Only",
    "izakaya_food_and_drinks": "Izakaya Food And Drinks",
    "izakaya_yakitori_kushiyaki": "Yakitori / Kushiyaki",
    "izakaya_kushiage": "Kushikatsu / Kushiage",
    "izakaya_seafood_sake_oden": "Seafood / Sake / Oden",
    "izakaya_tachinomi": "Tachinomi",
    "izakaya_robatayaki": "Robatayaki",
}


@dataclass(frozen=True)
class ImportResult:
    imported: list[dict[str, Any]]
    skipped: list[dict[str, str]]
    duplicates: list[dict[str, str]]

    def summary(self) -> dict[str, Any]:
        by_tier: dict[str, int] = {}
        by_profile: dict[str, int] = {}
        for record in self.imported:
            by_tier[str(record.get("quality_tier") or "unknown")] = by_tier.get(str(record.get("quality_tier") or "unknown"), 0) + 1
            by_profile[str(record.get("establishment_profile") or "unknown")] = by_profile.get(str(record.get("establishment_profile") or "unknown"), 0) + 1
        return {
            "imported": len(self.imported),
            "skipped": len(self.skipped),
            "duplicates": len(self.duplicates),
            "by_quality_tier": dict(sorted(by_tier.items(), key=lambda item: QUALITY_ORDER.get(item[0], 99))),
            "by_establishment_profile": dict(sorted(by_profile.items())),
        }


def normalize_email(value: str) -> str:
    cleaned = str(value or "").strip().lower()
    cleaned = cleaned.strip(" \t\r\n<>[](){}.,;:'\"")
    cleaned = re.sub(r"^mailto:", "", cleaned)
    cleaned = cleaned.split("?", 1)[0].strip()
    return cleaned.strip(" \t\r\n<>[](){}.,;:'\"")


def lead_input_paths(research_root: Path = DEFAULT_RESEARCH_ROOT) -> list[Path]:
    return [research_root / filename for filename in DEFAULT_INPUT_FILES]


def load_email_leads(paths: list[Path]) -> list[dict[str, Any]]:
    loaded: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            loaded.append(_normalise_source_lead(item, path))
    return loaded


def _normalise_source_lead(item: dict[str, Any], path: Path) -> dict[str, Any]:
    lead = {**item, "_source_file": str(path)}
    filename = path.name
    type_text = str(lead.get("type") or lead.get("category") or lead.get("type_of_restaurant") or "").strip()
    lowered_type = type_text.lower()

    if not lead.get("restaurant_name") and lead.get("name"):
        lead["restaurant_name"] = lead.get("name")
    if not lead.get("normalized_email") and lead.get("email"):
        lead["normalized_email"] = normalize_email(str(lead.get("email") or ""))
    if not lead.get("website") and lead.get("source_url"):
        lead["website"] = lead.get("source_url")
    if not lead.get("source_url") and lead.get("website"):
        lead["source_url"] = lead.get("website")
    if not lead.get("email_source_url"):
        lead["email_source_url"] = lead.get("source_url") or lead.get("website") or ""

    inferred_menu_type = _infer_menu_type(type_text, str(lead.get("type_of_restaurant") or ""))

    if not lead.get("type_of_restaurant"):
        if "izakaya" in lowered_type or "居酒屋" in type_text:
            lead["type_of_restaurant"] = "izakaya"
        elif "ramen" in lowered_type or "ラーメン" in type_text or "らーめん" in type_text:
            lead["type_of_restaurant"] = "ramen"
        elif inferred_menu_type in RAMEN_MENU_TYPES:
            lead["type_of_restaurant"] = "ramen"
        elif inferred_menu_type in IZAKAYA_PROFILE_BY_MENU_TYPE:
            lead["type_of_restaurant"] = "izakaya"

    if not lead.get("menu_type"):
        lead["menu_type"] = inferred_menu_type or _infer_menu_type(type_text, str(lead.get("type_of_restaurant") or ""))

    if not lead.get("quality_tier"):
        lead["quality_tier"] = "v1_clean" if filename == "restaurant_email_leads.json" else "high"
    if "lead" not in lead:
        lead["lead"] = True
    if not lead.get("source_import"):
        lead["source_import"] = {"round": "v1_clean" if filename == "restaurant_email_leads.json" else "restaurant_email_import"}
    if not lead.get("discovery_source"):
        lead["discovery_source"] = "v1_clean_import" if filename == "restaurant_email_leads.json" else "restaurant_email_import"
    if not lead.get("category_confidence"):
        lead["category_confidence"] = "high" if lead.get("quality_tier") in {"v1_clean", "high"} else "medium"
    if not lead.get("validation_notes"):
        lead["validation_notes"] = "Imported from the existing cleaned restaurant email lead corpus."
    lead.setdefault("rejection_flags", [])
    return lead


def _infer_menu_type(type_text: str, top_level_type: str) -> str:
    haystack = f"{type_text} {top_level_type}".lower()
    for menu_type, tokens in MENU_TYPE_TOKENS:
        if any(token.lower() in haystack or token in type_text for token in tokens):
            return menu_type
    if str(top_level_type).lower() == "izakaya":
        return "izakaya"
    if str(top_level_type).lower() == "ramen":
        return "ramen"
    return ""


def sort_email_leads(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        leads,
        key=lambda lead: (
            QUALITY_ORDER.get(str(lead.get("quality_tier") or "").lower(), 99),
            CITY_ORDER.get(str(lead.get("city") or ""), 99),
            str(lead.get("type_of_restaurant") or ""),
            str(lead.get("menu_type") or ""),
            str(lead.get("restaurant_name") or ""),
            normalize_email(str(lead.get("normalized_email") or lead.get("email") or "")),
        ),
    )


def establishment_profile_for(email_lead: dict[str, Any]) -> str:
    top_level_type = str(email_lead.get("type_of_restaurant") or "").strip().lower()
    menu_type = str(email_lead.get("menu_type") or "").strip().lower()
    if top_level_type == "ramen" or menu_type in RAMEN_MENU_TYPES:
        return "ramen_only"
    if top_level_type == "izakaya":
        return IZAKAYA_PROFILE_BY_MENU_TYPE.get(menu_type, "izakaya_food_and_drinks")
    return "unknown"


def template_assignment(email_lead: dict[str, Any]) -> dict[str, Any]:
    profile = establishment_profile_for(email_lead)
    family = "izakaya" if profile.startswith("izakaya") else "ramen" if profile.startswith("ramen") else "manual_review"
    assets = select_outreach_assets("menu_machine_unconfirmed", establishment_profile=profile)
    return {
        "template_locked": True,
        "template_owner": "GLM",
        "template_edit_policy": "locked_glm_seedstyle_only",
        "template_family": family,
        "template_profile_id": profile,
        "template_profile_label": PROFILE_LABELS.get(profile, profile.replace("_", " ").title()),
        "outreach_assets_selected": [str(path) for path in assets],
        "outreach_asset_template_family": "glm_locked_seedstyle" if assets else "none",
    }


def _city_address_hint(city: str) -> str:
    jp_by_city = {
        "Tokyo": "東京都",
        "Osaka": "大阪府大阪市",
        "Sapporo": "北海道札幌市",
        "Fukuoka": "福岡県福岡市",
        "Kyoto": "京都府京都市",
    }
    return jp_by_city.get(city, city)


def _business_name_fallback(email_lead: dict[str, Any]) -> tuple[str, list[str]]:
    flags: list[str] = []
    name = str(email_lead.get("restaurant_name") or "").strip()
    if name:
        return name, flags
    website = str(email_lead.get("website") or email_lead.get("source_url") or "").strip()
    host = re.sub(r"^https?://", "", website).split("/", 1)[0].removeprefix("www.")
    fallback = host.split(".", 1)[0].replace("-", " ").title() if host else "Imported Restaurant"
    flags.append("needs_business_name_review")
    return fallback, flags


def skip_reason(email_lead: dict[str, Any]) -> str:
    email = normalize_email(str(email_lead.get("normalized_email") or email_lead.get("email") or ""))
    if not email:
        return "missing_email"
    if any(fragment in email for fragment in BAD_EMAIL_FRAGMENTS):
        return "bad_email_fragment"
    if not is_usable_business_email(email):
        return "unusable_business_email"

    city = str(email_lead.get("city") or "").strip()
    if city not in CITY_ORDER:
        return "outside_target_city"

    top_level_type = str(email_lead.get("type_of_restaurant") or "").strip().lower()
    if top_level_type not in {"ramen", "izakaya"}:
        return "unsupported_restaurant_type"

    profile = establishment_profile_for(email_lead)
    if profile == "unknown":
        return "unsupported_menu_type"

    name = str(email_lead.get("restaurant_name") or "").strip()
    if name and any(fragment in name for fragment in BAD_NAME_FRAGMENTS):
        return "review_artifact_name"
    if name and is_chain_business(name):
        return "chain_or_branch_artifact"
    chain_reason = chain_or_franchise_signal_reason(
        " ".join([
            name,
            str(email_lead.get("validation_notes") or ""),
            str(email_lead.get("source_url") or ""),
            str(email_lead.get("website") or ""),
        ]),
        business_name=name,
    )
    if chain_reason:
        return f"chain_or_franchise_signal:{chain_reason}"
    return ""


def queue_record_from_email_lead(email_lead: dict[str, Any]) -> dict[str, Any]:
    email = normalize_email(str(email_lead.get("normalized_email") or email_lead.get("email") or ""))
    quality_tier = str(email_lead.get("quality_tier") or "medium").strip().lower()
    source_round = str((email_lead.get("source_import") or {}).get("round") or "restaurant_email_import")
    business_name, import_flags = _business_name_fallback(email_lead)
    city = str(email_lead.get("city") or "").strip()
    restaurant_type = str(email_lead.get("type_of_restaurant") or "").strip().lower()
    menu_type = str(email_lead.get("menu_type") or restaurant_type).strip().lower()
    profile = establishment_profile_for(email_lead)
    source_url = str(email_lead.get("source_url") or email_lead.get("website") or "").strip()
    email_source_url = str(email_lead.get("email_source_url") or source_url).strip()
    website = str(email_lead.get("website") or source_url).strip()
    validation_notes = str(email_lead.get("validation_notes") or "").strip()
    evidence_urls = [url for url in [source_url, email_source_url, website] if url]
    evidence_urls = list(dict.fromkeys(evidence_urls))
    confidence = "high" if quality_tier == "high" else "medium" if quality_tier == "medium" else "low"
    top_level_category = "izakaya" if restaurant_type == "izakaya" else "ramen"
    lead_id = f"wrm-email-{slugify(source_round)}-{slugify(email.split('@', 1)[0])}-{sha256_text(email)[:8]}"
    now = utc_now()
    original_rejection_flags = [str(flag) for flag in email_lead.get("rejection_flags") or [] if str(flag).strip()]
    needs_scope_review = quality_tier != "high" or bool(original_rejection_flags) or bool(import_flags)
    lead_category = (
        LEAD_CATEGORY_RAMEN_MENU_TRANSLATION
        if top_level_category == "ramen"
        else LEAD_CATEGORY_IZAKAYA_DRINK_COURSE_GUIDE
        if profile in {"izakaya_seafood_sake_oden", "izakaya_tachinomi", "izakaya_robatayaki"}
        else LEAD_CATEGORY_IZAKAYA_MENU_TRANSLATION
    )

    contacts = normalise_lead_contacts({
        "generated_at": now,
        "website": website,
        "email": email,
        "contacts": [{
            "type": "email",
            "value": email,
            "href": f"mailto:{email}",
            "source": "restaurant_email_import",
            "source_url": email_source_url,
            "confidence": confidence,
            "discovered_at": now,
            "actionable": True,
        }],
    })
    primary_contact = next((contact for contact in contacts if contact.get("actionable")), None)
    assignment = template_assignment(email_lead)

    record = {
        "lead_id": lead_id,
        "generated_at": now,
        "business_name": business_name,
        "locked_business_name": business_name,
        "business_name_locked": True,
        "business_name_locked_at": now,
        "business_name_lock_reason": "restaurant_email_import_source_name",
        "website": website,
        "address": _city_address_hint(city),
        "phone": "",
        "place_id": "",
        "map_url": "",
        "rating": None,
        "reviews": None,
        "source_query": "restaurant_email_import",
        "source_search_job": {
            "source_import": email_lead.get("source_import") or {},
            "source_file": email_lead.get("_source_file", ""),
            "discovery_source": email_lead.get("discovery_source", ""),
        },
        "source_import": email_lead.get("source_import") or {},
        "source_file": email_lead.get("_source_file", ""),
        "source_lead_value": email_lead.get("lead"),
        "source_quality_tier": quality_tier,
        "quality_tier": quality_tier,
        "candidate_inbox_status": "needs_scope_review" if needs_scope_review else "review_blocked",
        "needs_scope_review": True,
        "pitch_ready": False,
        "v1_excluded": True,
        "email_source_url": email_source_url,
        "source_urls": {
            "website": website,
            "map_url": "",
            "evidence_urls": evidence_urls,
        },
        "contacts": contacts,
        "primary_contact": primary_contact,
        "has_supported_contact_route": bool(primary_contact),
        "email": email,
        "lead": True,
        "rejection_reason": None,
        "source_rejection_flags": original_rejection_flags,
        "import_review_flags": import_flags,
        "lead_category": lead_category,
        "establishment_profile": profile,
        "establishment_profile_evidence": [
            f"imported menu_type={menu_type}",
            f"imported type_of_restaurant={restaurant_type}",
        ],
        "establishment_profile_confidence": str(email_lead.get("category_confidence") or confidence),
        "establishment_profile_source_urls": evidence_urls,
        "establishment_profile_override": "",
        "establishment_profile_override_note": "",
        "establishment_profile_override_at": None,
        "english_menu_issue": True,
        "english_menu_issue_evidence": ["No hard English-menu reject was present in the source lead file."],
        "ticket_machine_state": "unknown",
        "english_menu_state": "unknown",
        "menu_complexity_state": "simple",
        "izakaya_rules_state": "unknown" if top_level_category == "izakaya" else "none_found",
        "tourist_exposure_score": 0.0,
        "lead_score_v1": 80 if quality_tier == "high" else 55 if quality_tier == "medium" else 40,
        "recommended_primary_package": "",
        "package_recommendation_reason": "",
        "custom_quote_reason": "",
        "evidence_classes": ["public_email_import", f"{top_level_category}_category_match"],
        "evidence_urls": evidence_urls,
        "evidence_snippets": [validation_notes] if validation_notes else [],
        "matched_friction_evidence": [validation_notes] if validation_notes else [],
        "image_locked_evidence": [],
        "menu_evidence_found": True,
        "machine_evidence_found": False,
        "course_or_drink_plan_evidence_found": top_level_category == "izakaya",
        "evidence_strength_score": 70 if quality_tier == "high" else 45 if quality_tier == "medium" else 30,
        "lead_evidence_dossier": {},
        "proof_items": [],
        "coverage_signals": {
            "has_official_site": str(email_lead.get("discovery_source") or "").endswith("owned_page_email"),
            "matching_phone_or_address": False,
            "portal_only": False,
            "source_count": 1,
        },
        "source_count": 1,
        "source_coverage_score": 45 if quality_tier == "high" else 30,
        "business_name_verified_by": ["restaurant_email_import"],
        "message_variant": "",
        "launch_batch_id": "",
        "launch_outcome": {},
        "primary_category_v1": top_level_category,
        "type_of_restaurant": restaurant_type,
        "menu_type": menu_type,
        "city": city,
        "pitch_draft": {},
        "production_inputs_needed": ["full_menu_photos"],
        "preview_available": True,
        "pitch_available": False,
        "preview_path": f"state/previews/{lead_id}/english-menu.html",
        "record_path": f"state/leads/{lead_id}.json",
        "review_status": "pending",
        "outreach_status": "needs_review",
        "outreach_classification": "menu_machine_unconfirmed",
        "outreach_sent_at": None,
        "outreach_draft_body": None,
        "outreach_include_inperson": True,
        "status_history": [{"status": "needs_review", "timestamp": now}],
        **assignment,
    }
    package_details = recommend_package_details_for_record(record)
    record["recommended_primary_package"] = package_details["package_key"]
    record["package_recommendation_reason"] = package_details["recommendation_reason"]
    record["custom_quote_reason"] = package_details["custom_quote_reason"]
    return verify_restaurant_lead_record(record, checked_at=now)


def existing_email_index(state_root: Path) -> set[str]:
    emails: set[str] = set()
    for lead in list_leads(state_root=state_root):
        for contact in normalise_lead_contacts(lead):
            if contact.get("type") == "email":
                email = normalize_email(str(contact.get("value") or ""))
                if email:
                    emails.add(email)
        email = normalize_email(str(lead.get("email") or ""))
        if email:
            emails.add(email)
    return emails


def import_email_leads(paths: list[Path], *, state_root: Path, dry_run: bool = False, summary_path: Path | None = None) -> ImportResult:
    ensure_dir(state_root / "leads")
    imported: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    duplicates: list[dict[str, str]] = []
    existing_emails = existing_email_index(state_root)
    seen_this_import: set[str] = set()

    for email_lead in sort_email_leads(load_email_leads(paths)):
        email = normalize_email(str(email_lead.get("normalized_email") or email_lead.get("email") or ""))
        reason = skip_reason(email_lead)
        if reason:
            skipped.append({"email": email, "reason": reason, "source_file": str(email_lead.get("_source_file") or "")})
            continue
        if email in existing_emails or email in seen_this_import:
            duplicates.append({"email": email, "reason": "duplicate_email", "source_file": str(email_lead.get("_source_file") or "")})
            continue
        record = queue_record_from_email_lead(email_lead)
        imported.append(record)
        seen_this_import.add(email)
        if not dry_run:
            persist_lead_record(record, state_root=state_root)

    result = ImportResult(imported=imported, skipped=skipped, duplicates=duplicates)
    if summary_path is not None:
        write_json(summary_path, {
            "generated_at": utc_now(),
            "dry_run": dry_run,
            "input_files": [str(path) for path in paths],
            "summary": result.summary(),
            "skipped": skipped,
            "duplicates": duplicates,
            "imported_lead_ids": [record.get("lead_id") for record in imported],
        })
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import restaurant email lead JSON into the dashboard lead queue.")
    parser.add_argument("--state-root", type=Path, default=Path(__file__).resolve().parent.parent / "state")
    parser.add_argument("--research-root", type=Path, default=DEFAULT_RESEARCH_ROOT)
    parser.add_argument("--input", action="append", type=Path, default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summary-path", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    paths = args.input or lead_input_paths(args.research_root)
    summary_path = args.summary_path or args.state_root / "lead_imports" / f"restaurant_email_import_{utc_now().replace(':', '').replace('+', 'Z')}.json"
    result = import_email_leads(paths, state_root=args.state_root, dry_run=args.dry_run, summary_path=summary_path)
    print(json.dumps({"summary": result.summary(), "summary_path": str(summary_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
