from __future__ import annotations

import re
import urllib.parse
from copy import deepcopy
from typing import Any
from pathlib import Path

from .constants import (
    PACKAGE_1_KEY,
    PACKAGE_2_KEY,
    PACKAGE_3_KEY,
    OUTREACH_STATUS_DO_NOT_CONTACT,
    SOLVED_ENGLISH_SUPPORT_TERMS,
    TICKET_MACHINE_ABSENCE_TERMS,
)
from .contact_policy import (
    SUPPORTED_OUTREACH_CONTACT_TYPES,
    contact_should_be_omitted_from_routes,
    contact_form_unsupported_reason,
    normalise_contact_actionability,
)
from .evidence import has_chain_or_franchise_infrastructure, is_chain_business
from .utils import read_json, write_json


TICKET_MACHINE_STATES = {
    "present",
    "absent",
    "unknown",
    "already_english_supported",
}
ENGLISH_MENU_STATES = {
    "missing",
    "weak_partial",
    "image_only",
    "usable_complete",
    "unknown",
}
MENU_COMPLEXITY_STATES = {
    "simple",
    "medium",
    "large_custom_quote",
}
IZAKAYA_RULES_STATES = {
    "none_found",
    "drinks_found",
    "courses_found",
    "nomihodai_found",
    "unknown",
}
READINESS_READY = "ready_for_outreach"
READINESS_MANUAL = "manual_review"
READINESS_DISQUALIFIED = "disqualified"

_JP_PREFECTURE_PREFIXES = (
    "東京都", "大阪府", "京都府", "北海道",
    "神奈川県", "千葉県", "埼玉県", "愛知県", "兵庫県", "福岡県",
    "静岡県", "茨城県", "広島県", "宮城県", "長野県", "新潟県",
    "富山県", "石川県", "福井県", "山梨県", "岐阜県", "三重県",
    "滋賀県", "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県",
    "山口県", "徳島県", "香川県", "愛媛県", "高知県",
    "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
)
_NON_JP_ADDRESS_RE = re.compile(
    r"(?i)\b("
    r"united states|usa|new york|ny\s+\d{5}|jackson heights|roosevelt ave|"
    r"ludlow st|e\s+43rd\s+st|w\s+51st\s+st|california|los angeles|san francisco|"
    r"taiwan|taipei|hong kong|singapore|london|paris|sydney|melbourne"
    r")\b"
)


_LEGACY_PACKAGE_KEYS = {
    "package_A_in_person_48k": PACKAGE_2_KEY,
    "package_A_in_person_45k": PACKAGE_2_KEY,
    "package_A_printed_delivered_45k": PACKAGE_2_KEY,
    "package_B_online_30k": PACKAGE_1_KEY,
    "package_B_remote_30k": PACKAGE_1_KEY,
    "package_C_qr_menu_65k": PACKAGE_3_KEY,
}

_BOILERPLATE_TOKENS = (
    "calendar",
    "header",
    "footer",
    "site header",
    "site footer",
    "tel",
    "tel_string",
    "電話",
    "電話番号",
    "営業時間",
    "アクセス",
    "店舗情報",
    "店舗検索",
    "検索",
    "サイトマップ",
    "会社概要",
    "採用",
    "求人",
    "公式サイトからのご予約",
    "reservation",
    "reserve",
    "copyright",
    "privacy policy",
    "terms of use",
    "javascript",
    "cookie",
)
_CHAIN_SNIPPET_TOKENS = (
    "塚田農場",
    "tsukada nojo",
    "一蘭",
    "ichiran",
    "一風堂",
    "ippudo",
    "鳥貴族",
    "torikizoku",
)
_MENU_LIKE_TOKENS = (
    "ラーメン",
    "らーめん",
    "つけ麺",
    "味玉",
    "餃子",
    "チャーシュー",
    "トッピング",
    "居酒屋",
    "飲み放題",
    "コース",
    "生ビール",
    "ハイボール",
    "日本酒",
    "焼き鳥",
    "刺身",
    "唐揚げ",
    "お品書き",
    "メニュー",
    "ramen",
    "gyoza",
    "beer",
    "sake",
    "nomihodai",
    "course",
)
_BRACKETED_FALLBACK_RE = re.compile(r"\[[^\]]*[\u3040-\u30ff\u3400-\u9fff][^\]]*\]")


def map_legacy_package_key(value: str) -> str:
    key = str(value or "").strip()
    return _LEGACY_PACKAGE_KEYS.get(key, key)


def bracketed_fallback_found(text: str) -> bool:
    return bool(_BRACKETED_FALLBACK_RE.search(str(text or "")))


def snippet_rejection_reason(snippet: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(snippet or "")).strip()
    lowered = cleaned.lower()
    if not cleaned:
        return "empty_snippet"
    if bracketed_fallback_found(cleaned):
        return "bracketed_fallback_translation"
    if any(token in lowered for token in _BOILERPLATE_TOKENS):
        return "boilerplate_or_reservation_text"
    if any(token.lower() in lowered for token in _CHAIN_SNIPPET_TOKENS):
        return "chain_or_unrelated_brand_text"
    if has_chain_or_franchise_infrastructure(cleaned):
        return "chain_or_unrelated_brand_text"
    if len(cleaned) > 220:
        return "snippet_too_long_for_customer_preview"
    if not any(token.lower() in lowered for token in _MENU_LIKE_TOKENS):
        return "not_menu_or_ordering_evidence"
    return ""


def safe_customer_snippets(snippets: list[str]) -> list[str]:
    safe: list[str] = []
    seen: set[str] = set()
    for snippet in snippets:
        cleaned = re.sub(r"\s+", " ", str(snippet or "")).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        if not snippet_rejection_reason(cleaned):
            safe.append(cleaned)
    return safe


def build_proof_items(record: dict[str, Any]) -> list[dict[str, Any]]:
    urls = list(record.get("evidence_urls") or [])
    source_urls = record.get("source_urls") or {}
    if isinstance(source_urls, dict):
        urls.extend(source_urls.get("evidence_urls") or [])
    snippets = list(record.get("evidence_snippets") or [])
    count = max(len(urls), len(snippets), 1 if urls or snippets else 0)
    proof_items: list[dict[str, Any]] = []

    for idx in range(count):
        url = str(urls[idx] if idx < len(urls) else urls[0] if urls else "").strip()
        snippet = str(snippets[idx] if idx < len(snippets) else "").strip()
        rejection = snippet_rejection_reason(snippet) if snippet else "missing_customer_visible_snippet"
        proof_items.append({
            "source_type": _source_type_for_url(url),
            "url": url,
            "snippet": snippet,
            "screenshot_path": "",
            "operator_visible": bool(url or snippet),
            "customer_preview_eligible": not rejection,
            "rejection_reason": rejection,
        })

    return proof_items


def build_lead_evidence_dossier(record: dict[str, Any]) -> dict[str, Any]:
    category = _record_category(record)
    proof_items = build_proof_items(record)
    ticket_state = _ticket_machine_state(record)
    english_state = _english_menu_state(record)
    complexity_state = _menu_complexity_state({**record, "primary_category_v1": category})
    izakaya_state = _izakaya_rules_state({**record, "primary_category_v1": category})

    return {
        "ticket_machine_state": ticket_state,
        "english_menu_state": english_state,
        "menu_complexity_state": complexity_state,
        "izakaya_rules_state": izakaya_state,
        "proof_items": proof_items,
        "proof_strength": _proof_strength(proof_items),
        "ready_to_contact": False,
        "readiness_reasons": [],
    }


def assess_launch_readiness(record: dict[str, Any]) -> tuple[str, list[str]]:
    dossier = dict(record.get("lead_evidence_dossier") or build_lead_evidence_dossier(record))
    proof_items = list(record.get("proof_items") or dossier.get("proof_items") or [])
    reasons: list[str] = []
    category = _record_category(record)

    if record.get("lead") is not True:
        reasons.append("not_a_binary_true_lead")
    if category not in {"ramen", "izakaya"}:
        reasons.append("outside_v1_category")
    if record_explicitly_not_japan(record):
        reasons.append("not_in_japan")
    if is_chain_business(str(record.get("business_name") or "")) or _record_has_chain_infrastructure(record, proof_items):
        reasons.append("chain_or_franchise_like_business")
    if dossier.get("english_menu_state") == "usable_complete":
        reasons.append("already_has_usable_english_solution")
    if _has_multilingual_solution(record):
        reasons.append("multilingual_qr_or_ordering_solution_present")

    disqualifiers = {
        "not_a_binary_true_lead",
        "outside_v1_category",
        "not_in_japan",
        "chain_or_franchise_like_business",
        "already_has_usable_english_solution",
        "multilingual_qr_or_ordering_solution_present",
    }
    if any(reason in disqualifiers for reason in reasons):
        return READINESS_DISQUALIFIED, reasons

    if not _has_supported_contact(record):
        reasons.append("no_supported_contact_route")
    if (
        _primary_supported_contact_type(record) == "contact_form"
        and str(record.get("hosted_menu_sample_status") or "") == "publish_failed"
    ):
        reasons.append("hosted_sample_publish_failed")
    if not any(item.get("customer_preview_eligible") for item in proof_items):
        reasons.append("no_customer_safe_proof_item")
    if _record_contains_bad_preview(record) or record.get("legacy_pitch_blocked_reason"):
        reasons.append("saved_preview_or_pitch_contains_blocked_content")
    if dossier.get("menu_complexity_state") == "large_custom_quote":
        reasons.append("large_menu_requires_custom_quote")

    if reasons:
        return READINESS_MANUAL, reasons
    return READINESS_READY, ["qualified_with_safe_proof_and_contact_route"]


def record_explicitly_not_japan(record: dict[str, Any]) -> bool:
    """Return True for persisted leads whose saved location is clearly outside Japan."""
    address = str(record.get("address") or "").strip()
    if not address:
        return False
    combined = " ".join([
        address,
        str(record.get("phone") or ""),
        str(record.get("map_url") or ""),
    ])
    if _has_japan_location_evidence(combined):
        return False
    return bool(_NON_JP_ADDRESS_RE.search(combined))


def _has_japan_location_evidence(text: str) -> bool:
    if not text:
        return False
    if "Japan" in text or "日本" in text or "〒" in text:
        return True
    if any(pref in text for pref in _JP_PREFECTURE_PREFIXES):
        return True
    if re.search(r"(?:\+81[-\s]?|^0)[1-9]\d{0,3}[-\s]?\d{1,4}", text):
        return True
    return False


def ensure_lead_dossier(record: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(record)
    _migrate_package_fields(updated)
    _normalise_contact_actionability(updated)
    category = _record_category(updated)
    if category in {"ramen", "izakaya"} and not updated.get("primary_category_v1"):
        updated["primary_category_v1"] = category

    dossier = build_lead_evidence_dossier(updated)
    status, reasons = assess_launch_readiness({**updated, "lead_evidence_dossier": dossier, "proof_items": dossier["proof_items"]})
    dossier["ready_to_contact"] = status == READINESS_READY
    dossier["readiness_reasons"] = reasons

    updated["lead_evidence_dossier"] = dossier
    updated["proof_items"] = dossier["proof_items"]
    updated["launch_readiness_status"] = status
    updated["launch_readiness_reasons"] = reasons
    updated["has_supported_contact_route"] = _has_supported_contact(updated)
    updated.setdefault("message_variant", "")
    updated.setdefault("launch_batch_id", "")
    updated.setdefault("launch_outcome", {})

    if status == READINESS_DISQUALIFIED and updated.get("outreach_status") not in {"sent", "replied", "converted"}:
        updated["outreach_status"] = OUTREACH_STATUS_DO_NOT_CONTACT
        updated["disqualified_at_hardening"] = True

    return updated


def migrate_lead_record(record: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    before = deepcopy(record)
    after = ensure_lead_dossier(record)
    changes: list[str] = []

    for key in (
        "recommended_primary_package",
        "lead_evidence_dossier",
        "proof_items",
        "launch_readiness_status",
        "launch_readiness_reasons",
        "outreach_status",
        "pitch_draft",
        "pitch_available",
        "preview_available",
        "preview_blocked_reason",
        "legacy_pitch_draft",
        "legacy_pitch_blocked_reason",
        "contacts",
        "primary_contact",
        "has_supported_contact_route",
    ):
        if before.get(key) != after.get(key):
            changes.append(key)

    return after, changes


def migrate_state_leads(*, state_root: Path) -> dict[str, Any]:
    leads_dir = state_root / "leads"
    changed: list[dict[str, Any]] = []
    unchanged = 0
    if not leads_dir.exists():
        return {"changed": changed, "unchanged": unchanged}

    for path in sorted(leads_dir.glob("wrm-*.json")):
        record = read_json(path)
        if not record:
            continue
        migrated, changes = migrate_lead_record(record)
        if changes:
            write_json(path, migrated)
            changed.append({
                "lead_id": migrated.get("lead_id"),
                "changes": changes,
                "launch_readiness_status": migrated.get("launch_readiness_status"),
                "launch_readiness_reasons": migrated.get("launch_readiness_reasons") or [],
            })
        else:
            unchanged += 1

    return {"changed": changed, "unchanged": unchanged}


def _migrate_package_fields(record: dict[str, Any]) -> None:
    package = str(record.get("recommended_primary_package") or "")
    mapped = map_legacy_package_key(package)
    if package and mapped != package:
        record["recommended_primary_package"] = mapped
        record["legacy_recommended_primary_package"] = package
    pitch = record.get("pitch_draft")
    if pitch and bracketed_fallback_found(str(pitch)):
        record["legacy_pitch_blocked_reason"] = "bracketed_fallback_translation"
        record.setdefault("legacy_pitch_draft", pitch)
        record["pitch_draft"] = None
        record["pitch_available"] = False
        record["preview_available"] = False
        record["preview_blocked_reason"] = "legacy_pitch_contains_bracketed_fallback"


def _ticket_machine_state(record: dict[str, Any]) -> str:
    evidence = " ".join([
        str(record.get("english_availability") or ""),
        " ".join(record.get("lead_signals") or []),
        " ".join(record.get("evidence_classes") or []),
        " ".join(record.get("evidence_snippets") or []),
    ]).lower()
    if record.get("machine_evidence_found"):
        if any(token in evidence for token in ("english ticket", "multilingual ticket", "多言語券売機", "英語券売機")):
            return "already_english_supported"
        return "present"
    if "ticket_machine_absence_evidence" in evidence or any(token.lower() in evidence for token in TICKET_MACHINE_ABSENCE_TERMS):
        return "absent"
    if _record_category(record) == "izakaya":
        return "absent"
    return "unknown"


def _record_has_chain_infrastructure(record: dict[str, Any], proof_items: list[dict[str, Any]] | None = None) -> bool:
    parts: list[str] = [
        str(record.get("business_name") or ""),
        str(record.get("website") or ""),
        str(record.get("source_query") or ""),
    ]
    parts.extend(str(item) for item in record.get("evidence_snippets") or [])
    parts.extend(str(item) for item in record.get("evidence_urls") or [])
    source_urls = record.get("source_urls") or {}
    if isinstance(source_urls, dict):
        parts.extend(str(item) for item in source_urls.get("evidence_urls") or [])
    for item in proof_items or []:
        parts.append(str(item.get("snippet") or ""))
        parts.append(str(item.get("url") or ""))
    return has_chain_or_franchise_infrastructure(" ".join(parts))


def _english_menu_state(record: dict[str, Any]) -> str:
    raw = str(record.get("english_availability") or "").strip()
    if record.get("rejection_reason") == "already_has_good_english_menu":
        return "usable_complete"
    if raw in {"clear_usable", "usable_complete"}:
        return "usable_complete"
    if raw == "image_only":
        return "image_only"
    if raw == "incomplete":
        return "weak_partial"
    if raw in {"missing", "hard_to_use"}:
        return "missing"
    if record.get("english_menu_issue") is True:
        return "missing"
    return "unknown"


def _menu_complexity_state(record: dict[str, Any]) -> str:
    existing = str(record.get("menu_complexity_state") or "").strip()
    if existing in MENU_COMPLEXITY_STATES:
        return existing
    triggers = record.get("custom_quote_triggers") or []
    if triggers:
        return "large_custom_quote"
    snippets = " ".join(record.get("evidence_snippets") or [])
    if any(token in snippets for token in ("100品", "百種類", "大型", "複数メニュー", "宴会メニュー多数")):
        return "large_custom_quote"
    if _record_category(record) == "izakaya" or record.get("course_or_drink_plan_evidence_found"):
        return "medium"
    return "simple"


def _izakaya_rules_state(record: dict[str, Any]) -> str:
    if _record_category(record) != "izakaya":
        return "none_found"
    classes = set(record.get("evidence_classes") or [])
    snippets = " ".join(record.get("evidence_snippets") or [])
    if "nomihodai_menu" in classes or "飲み放題" in snippets or "nomihodai" in snippets.lower():
        return "nomihodai_found"
    if "course_menu" in classes or "コース" in snippets:
        return "courses_found"
    if "drink_menu_photo" in classes or any(token in snippets for token in ("生ビール", "ハイボール", "日本酒", "ドリンク")):
        return "drinks_found"
    if record.get("course_or_drink_plan_evidence_found"):
        return "courses_found"
    return "unknown"


def _source_type_for_url(url: str) -> str:
    host = urllib.parse.urlparse(url if url.startswith(("http://", "https://")) else f"https://{url}").netloc.lower()
    if "tabelog" in host:
        return "tabelog"
    if "hotpepper" in host:
        return "hotpepper"
    if "ramendb" in host:
        return "ramendb"
    if "instagram" in host:
        return "instagram"
    if "google" in host or "maps" in host:
        return "google_business"
    if host:
        return "official_or_shop_site"
    return "unknown"


def _proof_strength(proof_items: list[dict[str, Any]]) -> str:
    if any(item.get("customer_preview_eligible") and item.get("url") for item in proof_items):
        return "gold"
    if any(item.get("operator_visible") for item in proof_items):
        return "operator_only"
    return "none"


def _has_supported_contact(record: dict[str, Any]) -> bool:
    return bool(_primary_supported_contact_type(record))


def _primary_supported_contact_type(record: dict[str, Any]) -> str:
    contacts = record.get("contacts") or []
    for contact in contacts:
        if not isinstance(contact, dict):
            continue
        contact_type = str(contact.get("type") or "")
        if (
            contact.get("actionable")
            and contact_type in SUPPORTED_OUTREACH_CONTACT_TYPES
            and not contact_form_unsupported_reason(contact)
        ):
            return contact_type
    return "email" if record.get("email") else ""


def _normalise_contact_actionability(record: dict[str, Any]) -> None:
    contacts = record.get("contacts")
    if not isinstance(contacts, list):
        return

    first_supported: dict[str, Any] | None = None
    filtered_contacts: list[dict[str, Any]] = []
    for index, contact in enumerate(contacts):
        if not isinstance(contact, dict):
            continue
        contact = normalise_contact_actionability(contact)
        if contact_should_be_omitted_from_routes(contact):
            continue
        filtered_contacts.append(contact)
        if not contact.get("actionable"):
            continue
        if contact.get("actionable") is not False and first_supported is None:
            first_supported = contact
    record["contacts"] = filtered_contacts

    primary = record.get("primary_contact")
    if isinstance(primary, dict):
        primary = normalise_contact_actionability(primary)
        if contact_should_be_omitted_from_routes(primary):
            record["primary_contact"] = deepcopy(first_supported) if first_supported is not None else None
            return
        record["primary_contact"] = primary
        if not primary.get("actionable"):
            if first_supported is not None:
                record["primary_contact"] = deepcopy(first_supported)
    elif first_supported is not None:
        record["primary_contact"] = deepcopy(first_supported)


def _has_multilingual_solution(record: dict[str, Any]) -> bool:
    haystack = " ".join([
        str(record.get("english_availability") or ""),
        " ".join(record.get("evidence_classes") or []),
        " ".join(record.get("evidence_snippets") or []),
    ]).lower()
    return any(token.lower() in haystack for token in SOLVED_ENGLISH_SUPPORT_TERMS)


def _record_contains_bad_preview(record: dict[str, Any]) -> bool:
    text = " ".join([
        str(record.get("pitch_draft") or ""),
        str(record.get("outreach_draft_body") or ""),
        str(record.get("shop_preview_html") or ""),
    ])
    return bracketed_fallback_found(text)


def _record_category(record: dict[str, Any]) -> str:
    stored = str(record.get("primary_category_v1") or "").strip().lower()
    if stored in {"ramen", "izakaya"}:
        return stored
    haystack = " ".join([
        str(record.get("business_name") or ""),
        str(record.get("category") or ""),
        " ".join(record.get("evidence_snippets") or []),
        " ".join(record.get("evidence_classes") or []),
    ]).lower()
    if "izakaya" in haystack or "居酒屋" in haystack:
        return "izakaya"
    if "ramen" in haystack or "ラーメン" in haystack or "らーめん" in haystack:
        return "ramen"
    return stored or "other"
