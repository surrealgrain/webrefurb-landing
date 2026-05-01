from __future__ import annotations

import concurrent.futures
import re
import urllib.parse
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from .constants import (
    PACKAGE_1_KEY,
    PACKAGE_2_KEY,
    PACKAGE_3_KEY,
    PROJECT_ROOT,
)
from .lead_dossier import ensure_lead_dossier
from .models import QualificationResult
from .outreach import classify_business, select_outreach_assets
from .pitch import build_pitch
from .preview import build_preview_html, build_preview_menu
from .record import create_lead_record, find_existing_lead, persist_lead_record
from .utils import ensure_dir, read_json, sha256_text, slugify, utc_now, write_json


CANDIDATE_STATES = {
    "imported",
    "needs_scope_review",
    "needs_enrichment",
    "pitch_ready",
    "approved_for_lead_queue",
    "promoted",
    "rejected",
}

MENU_TYPES = {
    "ramen_standard",
    "ramen_izakaya_hybrid",
    "izakaya_general",
    "izakaya_yakitori_kushiyaki",
    "izakaya_kushiage",
    "izakaya_seafood_sake_oden",
    "izakaya_drink_heavy_sake_beer",
    "needs_scope_review",
}

MENU_TYPE_LABELS = {
    "ramen_standard": "Ramen English Menu",
    "ramen_izakaya_hybrid": "Ramen + Izakaya Ordering Guide",
    "izakaya_general": "Izakaya Food + Drinks Menu",
    "izakaya_yakitori_kushiyaki": "Yakitori / Kushiyaki Izakaya Menu",
    "izakaya_kushiage": "Kushiage Izakaya Menu",
    "izakaya_seafood_sake_oden": "Seafood / Sake / Oden Izakaya Menu",
    "izakaya_drink_heavy_sake_beer": "Drink-Heavy Izakaya Menu",
    "needs_scope_review": "Scope Review Needed",
}

_IMPORT_ENTRY_RE = re.compile(
    r"Restaurant name:\s*(?P<name>.*?)\n"
    r"Website:\s*(?P<website>.*?)\n"
    r"Type of restaurant:\s*(?P<kind>.*?)\n"
    r"E-mail:\s*(?P<email>[^\n]+)",
    re.S,
)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PRICE_TOKENS = ("¥30,000", "¥45,000", "¥65,000", "30000", "45000", "65000")
_FORBIDDEN_COPY_TOKENS = (
    "ai",
    "artificial intelligence",
    "automation",
    "automated",
    "internal tool",
    "machine learning",
    "llm",
    "gpt",
)


def parse_manual_leads_markdown(path: str | Path) -> list[dict[str, str]]:
    """Parse the operator-provided Markdown lead list."""
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    entries: list[dict[str, str]] = []
    for index, match in enumerate(_IMPORT_ENTRY_RE.finditer(text), start=1):
        entries.append({
            "row_number": str(index),
            "restaurant_name": _clean_text(match.group("name")),
            "website": _clean_text(match.group("website")),
            "raw_restaurant_type": _clean_text(match.group("kind")),
            "email": _clean_text(match.group("email")).lower(),
        })
    return entries


def import_manual_email_leads(
    *,
    input_path: str | Path,
    state_root: str | Path | None = None,
    persist: bool = True,
    enrich: bool = False,
    max_workers: int = 6,
    import_id: str = "",
) -> dict[str, Any]:
    """Create a manual candidate import with pitch packs for every entry."""
    root = Path(state_root) if state_root else PROJECT_ROOT / "state"
    source = Path(input_path)
    rows = parse_manual_leads_markdown(source)
    content_hash = sha256_text(source.read_text(encoding="utf-8"))[:12]
    resolved_import_id = import_id or f"manual-email-leads-{content_hash}"

    candidates = [
        _candidate_from_row(row, import_id=resolved_import_id, source_path=source)
        for row in rows
    ]
    _apply_duplicate_flags(candidates)

    if enrich and candidates:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
            candidates = list(pool.map(_enrich_candidate_safely, candidates))

    candidates = [_with_pitch_pack(candidate) for candidate in candidates]
    summary = _import_summary(candidates, import_id=resolved_import_id, input_path=source)
    decisions = [_candidate_decision(candidate) for candidate in candidates]

    if persist:
        import_dir = _import_dir(root, resolved_import_id)
        ensure_dir(import_dir)
        write_json(import_dir / "candidates.json", candidates)
        write_json(import_dir / "summary.json", summary)
        write_json(import_dir / "decisions.json", decisions)

    return {
        "import_id": resolved_import_id,
        "input_path": str(source),
        "candidate_count": len(candidates),
        "summary": summary,
        "candidates": candidates,
        "decisions": decisions,
        "persisted": bool(persist),
    }


def list_candidate_imports(*, state_root: str | Path | None = None) -> list[dict[str, Any]]:
    root = Path(state_root) if state_root else PROJECT_ROOT / "state"
    imports_root = root / "manual_imports"
    if not imports_root.exists():
        return []
    imports: list[dict[str, Any]] = []
    for path in sorted(imports_root.iterdir()):
        if not path.is_dir():
            continue
        summary = read_json(path / "summary.json", default={}) or {}
        if summary:
            imports.append(summary)
    return imports


def list_candidates(
    *,
    state_root: str | Path | None = None,
    import_id: str = "",
) -> list[dict[str, Any]]:
    root = Path(state_root) if state_root else PROJECT_ROOT / "state"
    imports_root = root / "manual_imports"
    candidates: list[dict[str, Any]] = []
    if import_id:
        candidates.extend(read_json(_import_dir(root, import_id) / "candidates.json", default=[]) or [])
    elif imports_root.exists():
        for path in sorted(imports_root.iterdir()):
            if path.is_dir():
                candidates.extend(read_json(path / "candidates.json", default=[]) or [])
    return sorted(candidates, key=lambda item: (str(item.get("candidate_state") or ""), -int(item.get("pitch_quality_score") or 0), str(item.get("business_name") or "")))


def load_candidate(
    candidate_id: str,
    *,
    state_root: str | Path | None = None,
) -> dict[str, Any] | None:
    for candidate in list_candidates(state_root=state_root):
        if candidate.get("candidate_id") == candidate_id:
            return candidate
    return None


def update_candidate(
    candidate_id: str,
    updates: dict[str, Any],
    *,
    state_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(state_root) if state_root else PROJECT_ROOT / "state"
    candidate = load_candidate(candidate_id, state_root=root)
    if not candidate:
        raise ValueError(f"candidate_not_found:{candidate_id}")
    import_id = str(candidate.get("import_id") or "")
    candidates = read_json(_import_dir(root, import_id) / "candidates.json", default=[]) or []
    allowed = {
        "candidate_state",
        "menu_type",
        "operator_review_note",
        "operator_scope_reviewed",
    }
    updated: dict[str, Any] | None = None
    for item in candidates:
        if item.get("candidate_id") != candidate_id:
            continue
        for key, value in updates.items():
            if key not in allowed:
                continue
            if key == "candidate_state" and value not in CANDIDATE_STATES:
                continue
            if key == "menu_type" and value not in MENU_TYPES:
                continue
            item[key] = value
        item["updated_at"] = utc_now()
        if item.get("menu_type") != candidate.get("menu_type"):
            item.update(_state_for_candidate(item))
            item = _with_pitch_pack(item)
        updated = item
        break
    if not updated:
        raise ValueError(f"candidate_not_found:{candidate_id}")
    write_json(_import_dir(root, import_id) / "candidates.json", candidates)
    write_json(_import_dir(root, import_id) / "summary.json", _import_summary(candidates, import_id=import_id, input_path=Path(str(candidate.get("source_import", {}).get("input_path") or ""))))
    write_json(_import_dir(root, import_id) / "decisions.json", [_candidate_decision(item) for item in candidates])
    return updated


def approve_candidate_for_lead_queue(
    candidate_id: str,
    *,
    state_root: str | Path | None = None,
    note: str = "",
) -> dict[str, Any]:
    return update_candidate(
        candidate_id,
        {
            "candidate_state": "approved_for_lead_queue",
            "operator_scope_reviewed": True,
            "operator_review_note": note,
        },
        state_root=state_root,
    )


def promote_candidate_to_lead(
    candidate_id: str,
    *,
    state_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(state_root) if state_root else PROJECT_ROOT / "state"
    candidate = load_candidate(candidate_id, state_root=root)
    if not candidate:
        raise ValueError(f"candidate_not_found:{candidate_id}")
    if candidate.get("candidate_state") not in {"approved_for_lead_queue", "pitch_ready"}:
        raise ValueError(f"candidate_not_approved:{candidate_id}")
    if candidate.get("menu_type") == "needs_scope_review" and not candidate.get("operator_scope_reviewed"):
        raise ValueError(f"candidate_scope_review_required:{candidate_id}")
    if candidate.get("email_contact", {}).get("valid") is not True:
        raise ValueError(f"candidate_email_invalid:{candidate_id}")

    existing = find_existing_lead(
        business_name=str(candidate.get("business_name") or ""),
        website=str(candidate.get("website") or ""),
        address=str(candidate.get("area_hint") or ""),
        state_root=root,
    )
    if existing:
        candidate["promoted_lead_id"] = existing.get("lead_id", "")
        update_candidate(candidate_id, {"candidate_state": "promoted"}, state_root=root)
        return existing

    qualification = _qualification_from_candidate(candidate)
    preview_menu = build_preview_menu(
        assessment=qualification,
        snippets=qualification.evidence_snippets,
        business_name=qualification.business_name,
    )
    preview_html = build_preview_html(
        preview_menu=preview_menu,
        ticket_machine_hint=None,
        business_name=qualification.business_name,
    )
    pitch = build_pitch(
        business_name=qualification.business_name,
        category=qualification.primary_category_v1,
        preview_menu=preview_menu,
        ticket_machine_hint=None,
        recommended_package=qualification.recommended_primary_package,
    )
    email = str(candidate.get("email") or "")
    contacts = [{
        "type": "email",
        "value": email,
        "label": "Imported business email",
        "href": f"mailto:{email}",
        "source": "manual_email_import",
        "source_url": str(candidate.get("website") or ""),
        "confidence": "high",
        "discovered_at": str(candidate.get("imported_at") or utc_now()),
        "status": "operator_provided",
        "actionable": True,
    }]
    record = create_lead_record(
        qualification=qualification,
        preview_html=preview_html,
        pitch_draft=pitch,
        contacts=contacts,
        source_query="manual_email_import",
        source_search_job={
            "job_id": "manual_email_import",
            "query": str(candidate.get("source_import", {}).get("input_path") or ""),
            "category": qualification.primary_category_v1,
            "purpose": "operator_supplied_email_candidate",
            "expected_friction": str(candidate.get("menu_type") or ""),
        },
        matched_friction_evidence=list(candidate.get("matched_friction_evidence") or []),
        state_root=root,
    )
    pitch_pack = dict(candidate.get("pitch_pack") or {})
    record.update({
        "manual_candidate_id": candidate_id,
        "manual_import_id": candidate.get("import_id", ""),
        "source_import": candidate.get("source_import", {}),
        "menu_type": candidate.get("menu_type", ""),
        "menu_type_label": candidate.get("menu_type_label", ""),
        "operator_attested_english_menu_state": "missing",
        "business_name_verified_by": ["manual_import", "operator_review"],
        "locked_business_name": candidate.get("business_name", ""),
        "business_name_locked": True,
        "business_name_locked_at": utc_now(),
        "business_name_lock_reason": "manual_import_operator_review",
        "pitch_context": candidate.get("pitch_context", {}),
        "pitch_quality_score": candidate.get("pitch_quality_score", 0),
        "outreach_draft_subject": pitch_pack.get("subject", ""),
        "outreach_draft_body": pitch_pack.get("body_ja", ""),
        "outreach_draft_english_body": pitch_pack.get("body_en", ""),
        "outreach_draft_manually_edited": False,
        "outreach_draft_edited_at": "",
        "message_variant": f"email:{record.get('outreach_classification', '')}:{record.get('establishment_profile', '')}:{candidate.get('menu_type', '')}",
    })
    record["outreach_status"] = "draft"
    record = ensure_lead_dossier(record)
    persist_lead_record(record, state_root=root)

    _mark_candidate_promoted(candidate_id, import_id=str(candidate.get("import_id") or ""), lead_id=str(record.get("lead_id") or ""), state_root=root)
    return record


def _candidate_from_row(row: dict[str, str], *, import_id: str, source_path: Path) -> dict[str, Any]:
    name = row["restaurant_name"]
    raw_type = row["raw_restaurant_type"]
    website = _normalise_url(row["website"])
    email = row["email"]
    menu_type = infer_menu_type(raw_type=raw_type, business_name=name)
    primary_category = _primary_category_for_menu_type(menu_type)
    scope_risk_reasons = scope_risks(raw_type=raw_type, business_name=name, menu_type=menu_type)
    candidate_id = _candidate_id(import_id=import_id, name=name, website=website, email=email)
    candidate = {
        "candidate_id": candidate_id,
        "import_id": import_id,
        "row_number": int(row["row_number"]),
        "imported_at": utc_now(),
        "updated_at": utc_now(),
        "business_name": name,
        "website": website,
        "email": email,
        "email_contact": _email_contact(email),
        "raw_restaurant_type": raw_type,
        "primary_category_v1": primary_category,
        "menu_type": menu_type,
        "menu_type_label": MENU_TYPE_LABELS[menu_type],
        "operator_attested_english_menu_state": "missing",
        "scope_risk_reasons": scope_risk_reasons,
        "duplicate_warnings": [],
        "area_hint": _area_hint(raw_type),
        "source_import": {
            "input_path": str(source_path),
            "row_number": int(row["row_number"]),
            "source_kind": "manual_email_markdown",
        },
        "pitch_context": {},
        "pitch_pack": {},
        "pitch_quality_score": 0,
        "matched_friction_evidence": [],
        "operator_scope_reviewed": False,
        "operator_review_note": "",
        "promoted_lead_id": "",
    }
    candidate.update(_state_for_candidate(candidate))
    return candidate


def infer_menu_type(*, raw_type: str, business_name: str = "") -> str:
    text = f"{raw_type} {business_name}".lower()
    has_ramen = _contains_any(text, (
        "ramen", "ラーメン", "らーめん", "中華そば", "chuka soba",
        "tsukemen", "つけ麺", "abura soba", "油そば", "mazesoba", "まぜそば",
        "tantanmen", "tan tan men", "担々麺",
    ))
    has_izakaya = _contains_any(text, ("izakaya", "居酒屋", "酒場", "sakaba", "飲み屋"))
    if has_ramen and has_izakaya:
        return "ramen_izakaya_hybrid"
    if has_ramen:
        return "ramen_standard"
    if _contains_any(text, ("yakitori", "焼き鳥", "焼鳥", "やきとり", "kushiyaki", "串焼き", "yakiton", "やきとん", "鶏料理")):
        return "izakaya_yakitori_kushiyaki"
    if _contains_any(text, ("kushiage", "kushikatsu", "串揚げ", "串カツ", "串かつ", "串丸")):
        return "izakaya_kushiage"
    if _contains_any(text, ("seafood izakaya", "海鮮居酒屋", "robatayaki", "炉端焼き")):
        return "izakaya_seafood_sake_oden"
    if has_izakaya and _contains_any(text, ("seafood", "海鮮", "鮮魚", "魚", "sake bar", "日本酒", "酒蔵", "oden", "おでん")):
        return "izakaya_seafood_sake_oden"
    if _contains_any(text, ("tachinomi", "立ち飲み", "立呑み", "立飲み")):
        return "izakaya_drink_heavy_sake_beer"
    if has_izakaya and _contains_any(text, ("beer", "ビール", "sake", "日本酒", "bar")):
        return "izakaya_drink_heavy_sake_beer"
    if has_izakaya:
        return "izakaya_general"
    return "needs_scope_review"


def scope_risks(*, raw_type: str, business_name: str, menu_type: str) -> list[str]:
    text = f"{raw_type} {business_name}".lower()
    risks: list[str] = []
    if menu_type == "needs_scope_review":
        risks.append("not_clearly_ramen_or_izakaya")
    risky_tokens = {
        "sushi_or_sashimi_specialist": ("sushi", "寿司", "鮨", "寿し"),
        "yakiniku_or_korean": ("yakiniku", "焼肉", "韓国"),
        "chinese_specialist": ("chinese", "中国料理"),
        "hotel_or_chain_operator": ("hotel", "ホテル", "marche.co.jp", "umenohana.co.jp"),
        "generic_seafood_without_izakaya": ("seafood",),
        "non_v1_japanese_cuisine": ("日本料理", "kaiseki", "懐石"),
    }
    for reason, tokens in risky_tokens.items():
        if any(token in text for token in tokens):
            if reason != "generic_seafood_without_izakaya" or "izakaya" not in text and "居酒屋" not in text:
                risks.append(reason)
    return list(dict.fromkeys(risks))


def _with_pitch_pack(candidate: dict[str, Any]) -> dict[str, Any]:
    context = _pitch_context(candidate)
    pitch_pack = build_candidate_pitch(candidate, context=context)
    updated = dict(candidate)
    updated["pitch_context"] = context
    updated["pitch_pack"] = pitch_pack
    updated["pitch_quality_score"] = _pitch_quality_score(updated)
    if updated["candidate_state"] in {"imported", "needs_enrichment"} and updated["email_contact"].get("valid") and updated["menu_type"] != "needs_scope_review":
        updated["candidate_state"] = "pitch_ready"
    return updated


def build_candidate_pitch(candidate: dict[str, Any], *, context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context or _pitch_context(candidate)
    business_name = str(candidate.get("business_name") or "")
    menu_type = str(candidate.get("menu_type") or "needs_scope_review")
    label = MENU_TYPE_LABELS.get(menu_type, "English Menu Sample")
    diagnosis_ja = context["diagnosis_ja"]
    diagnosis_en = context["diagnosis_en"]
    subject = f"英語注文ガイド制作のご提案（{business_name}様）"
    body_ja = _join_paragraphs([
        f"{business_name} ご担当者様",
        "突然のご連絡にて失礼いたします。飲食店向けの英語メニュー制作を行っております、Chris（クリス）と申します。",
        diagnosis_ja,
        f"仕上がりの方向性が分かるよう、{label}の小さなサンプルを作成しました。添付ではなく、このメール内の画像でご確認いただけます。",
        "実際に制作する場合は、公開情報ではなく貴店からいただく最新のメニュー写真をもとに、内容を確認しながら作成します。",
        "ご興味がございましたら、現在お使いのメニュー写真をお送りいただけましたら、貴店向けの確認用サンプルをお作りいたします。",
        "送信者：Chris（クリス） / WebRefurb",
        "連絡先：chris@webrefurb.com / https://webrefurb.com/ja",
        "今後このようなご連絡が不要でしたら、お手数ですが「不要」とご返信ください。",
        "どうぞよろしくお願いいたします。",
        "Chris（クリス）",
    ])
    body_en = _join_paragraphs([
        f"Dear {business_name} team,",
        "I hope you do not mind my sudden message. My name is Chris, and I create English menus for restaurants.",
        diagnosis_en,
        f"I prepared a small {label} visual so you can see the direction. It is shown inline in the email, not as a file attachment.",
        "For actual production, I would use current menu photos from your restaurant and prepare the English version for your review.",
        "If you are interested, please send photos of your current menu and I will create a review sample for your shop.",
        "Sender: Chris / WebRefurb. Contact: chris@webrefurb.com / https://webrefurb.com/ja. If this is not relevant, please reply and I will not contact you again.",
        "Thank you for your consideration.",
        "Chris",
    ])
    _assert_safe_pitch(body_ja + "\n" + body_en + "\n" + subject)
    return {
        "subject": subject,
        "body_ja": body_ja,
        "body_en": body_en,
        "strategy": "diagnosis_led_inline_sample",
        "menu_type": menu_type,
        "menu_type_label": label,
        "menu_template_path": _menu_template_for_menu_type(menu_type),
        "include_menu_image": menu_type != "needs_scope_review",
        "include_machine_image": False,
        "proof_summary": context.get("proof_summary", ""),
        "risk_flags": list(candidate.get("scope_risk_reasons") or []) + list(candidate.get("duplicate_warnings") or []),
    }


def _pitch_context(candidate: dict[str, Any]) -> dict[str, Any]:
    menu_type = str(candidate.get("menu_type") or "")
    business_name = str(candidate.get("business_name") or "")
    raw_type = str(candidate.get("raw_restaurant_type") or "")
    evidence_snippets = list(candidate.get("evidence_snippets") or [])
    evidence_urls = list(candidate.get("evidence_urls") or [])
    if menu_type.startswith("ramen"):
        diagnosis_ja = "貴店の公開メニュー情報を拝見し、海外からのお客様がラーメンの種類、トッピング、セット内容を注文前に確認しやすくなる余地があると感じました。"
        diagnosis_en = "I reviewed your public menu information and noticed that overseas guests may benefit from clearer English guidance for ramen types, toppings, and set options."
        proof = "ramen_menu_attestation"
        snippets = evidence_snippets or ["ラーメン メニュー トッピング 英語メニュー未確認"]
    elif menu_type == "izakaya_yakitori_kushiyaki":
        diagnosis_ja = "焼き鳥や串焼きは部位名や味付けが分かると注文しやすくなるため、英語で整理したメニューが海外のお客様に役立つ可能性があります。"
        diagnosis_en = "For yakitori and kushiyaki, guests often need help understanding cuts, seasoning, and ordering units, so a clear English menu can make ordering easier."
        proof = "yakitori_kushiyaki_menu_attestation"
        snippets = evidence_snippets or ["居酒屋 焼き鳥 串焼き メニュー 英語メニュー未確認"]
    elif menu_type == "izakaya_kushiage":
        diagnosis_ja = "串揚げは具材や本数、セット内容が英語で分かると、海外のお客様が卓上で選びやすくなります。"
        diagnosis_en = "For kushiage, clear English labels for ingredients, portions, and sets help overseas guests choose at the table."
        proof = "kushiage_menu_attestation"
        snippets = evidence_snippets or ["居酒屋 串揚げ メニュー 英語メニュー未確認"]
    elif menu_type == "izakaya_seafood_sake_oden":
        diagnosis_ja = "魚料理、日本酒、おでんなどは内容や注文単位が伝わりにくいことがあるため、英語で整理するとスタッフの説明負担を減らせます。"
        diagnosis_en = "Seafood, sake, and oden menus can be hard to understand without context, so organizing them in English can reduce repeated staff explanations."
        proof = "seafood_sake_oden_menu_attestation"
        snippets = evidence_snippets or ["居酒屋 海鮮 日本酒 おでん メニュー 英語メニュー未確認"]
    elif menu_type == "izakaya_drink_heavy_sake_beer":
        diagnosis_ja = "ドリンク、日本酒、ビール、飲み方の説明が英語でまとまっていると、海外のお客様が注文前に判断しやすくなります。"
        diagnosis_en = "For drink-heavy shops, English structure for drinks, sake, beer, and ordering notes helps overseas guests decide before asking staff."
        proof = "drink_menu_attestation"
        snippets = evidence_snippets or ["居酒屋 ドリンク 日本酒 ビール メニュー 英語メニュー未確認"]
    elif menu_type.startswith("izakaya"):
        diagnosis_ja = "料理、ドリンク、コース内容が英語で整理されていると、海外のお客様が卓上で判断しやすくなり、スタッフの個別説明も減らせます。"
        diagnosis_en = "When food, drinks, and course details are organized in English, overseas guests can decide at the table and staff spend less time explaining items one by one."
        proof = "izakaya_menu_attestation"
        snippets = evidence_snippets or ["居酒屋 メニュー ドリンク コース 英語メニュー未確認"]
    else:
        diagnosis_ja = "公開情報だけではラーメン・居酒屋向けの制作対象か確認が必要ですが、英語メニューの必要性があれば小さな確認用サンプルから進められます。"
        diagnosis_en = "The shop fit still needs review, but if English menu support is useful, I would start with a small review sample."
        proof = "scope_review_required"
        snippets = evidence_snippets or []
    return {
        "business_name": business_name,
        "raw_restaurant_type": raw_type,
        "diagnosis_ja": diagnosis_ja,
        "diagnosis_en": diagnosis_en,
        "evidence_snippets": snippets[:6],
        "evidence_urls": evidence_urls or [str(candidate.get("website") or "")],
        "proof_summary": proof,
    }


def _qualification_from_candidate(candidate: dict[str, Any]) -> QualificationResult:
    menu_type = str(candidate.get("menu_type") or "")
    category = _primary_category_for_menu_type(menu_type)
    profile = _establishment_profile_for_menu_type(menu_type)
    snippets = list((candidate.get("pitch_context") or {}).get("evidence_snippets") or [])
    urls = list((candidate.get("pitch_context") or {}).get("evidence_urls") or [candidate.get("website", "")])
    has_menu = menu_type != "needs_scope_review"
    lead_category = "ramen_menu_translation" if category == "ramen" else "izakaya_drink_course_guide" if category == "izakaya" else "none"
    package = _recommended_package_for_menu_type(menu_type)
    return QualificationResult(
        lead=True,
        rejection_reason=None,
        business_name=str(candidate.get("business_name") or ""),
        website=str(candidate.get("website") or ""),
        category=category,
        address=str(candidate.get("area_hint") or ""),
        lead_signals=["operator_attested_no_english_menu", "source_menu_available"],
        evidence_classes=[_evidence_class_for_menu_type(menu_type)],
        evidence_urls=[url for url in urls if url],
        evidence_snippets=snippets,
        evidence_strength_score=8 if has_menu else 3,
        menu_evidence_found=has_menu,
        machine_evidence_found=False,
        course_or_drink_plan_evidence_found=category == "izakaya",
        english_availability="missing",
        english_menu_issue=True,
        english_menu_issue_evidence=["operator_attested_no_english_menu"],
        ticket_machine_state="unknown" if category == "ramen" else "absent",
        english_menu_state="missing",
        menu_complexity_state="medium" if category == "izakaya" else "simple",
        izakaya_rules_state=_izakaya_rules_state_for_menu_type(menu_type),
        primary_category_v1=category,
        lead_category=lead_category,
        establishment_profile=profile,
        establishment_profile_evidence=[f"manual_import_menu_type:{menu_type}", f"raw_type:{candidate.get('raw_restaurant_type', '')}"],
        establishment_profile_confidence="medium",
        establishment_profile_source_urls=[str(candidate.get("website") or "")],
        lead_score_v1=int(candidate.get("pitch_quality_score") or 60),
        recommended_primary_package=package,
        package_recommendation_reason=_package_reason_for_menu_type(menu_type),
        decision_reason="Qualified by operator-provided email lead list with no-English-menu attestation.",
        false_positive_risk="medium" if candidate.get("scope_risk_reasons") else "low",
        preview_available=True,
        pitch_available=True,
    )


def _enrich_candidate_safely(candidate: dict[str, Any]) -> dict[str, Any]:
    try:
        return enrich_candidate(candidate)
    except Exception as exc:
        updated = dict(candidate)
        updated["enrichment_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        if updated.get("candidate_state") == "imported":
            updated["candidate_state"] = "needs_enrichment"
        return updated


def enrich_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Fetch the supplied URL and extract lightweight pitch evidence."""
    from .html_parser import extract_page_payload
    from .search import _fetch_page

    website = str(candidate.get("website") or "")
    if not website or _blocked_fetch_url(website):
        return candidate
    html = _fetch_page(website, timeout_seconds=8)
    payload = extract_page_payload(website, html)
    text = str(payload.get("text") or "")
    snippets = _menu_snippets(text, menu_type=str(candidate.get("menu_type") or ""))
    updated = dict(candidate)
    if snippets:
        updated["evidence_snippets"] = snippets
        updated["evidence_urls"] = [website]
        updated["matched_friction_evidence"] = list(dict.fromkeys([*updated.get("matched_friction_evidence", []), "fetched_public_menu_context"]))
    updated["enriched_at"] = utc_now()
    return updated


def _menu_snippets(text: str, *, menu_type: str) -> list[str]:
    tokens = ("ラーメン", "メニュー", "お品書き", "飲み放題", "コース", "焼き鳥", "串揚げ", "日本酒", "ビール", "ドリンク")
    snippets: list[str] = []
    compact = re.sub(r"\s+", " ", text or "")
    for match in re.finditer(r".{0,32}(" + "|".join(re.escape(token) for token in tokens) + r").{0,72}", compact):
        snippet = match.group(0).strip()
        if snippet and snippet not in snippets:
            snippets.append(snippet[:180])
        if len(snippets) >= 4:
            break
    return snippets


def _blocked_fetch_url(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return any(token in host for token in ("youtube.com", "facebook.com", "instagram.com", "linktr.ee", "lit.link"))


def _apply_duplicate_flags(candidates: list[dict[str, Any]]) -> None:
    email_counts: dict[str, int] = {}
    host_counts: dict[str, int] = {}
    for candidate in candidates:
        email_counts[candidate["email"]] = email_counts.get(candidate["email"], 0) + 1
        host = _host(candidate.get("website", ""))
        if host:
            host_counts[host] = host_counts.get(host, 0) + 1
    operator_hosts = {"marche.co.jp", "umenohana.co.jp", "motu-ooyama.com"}
    for candidate in candidates:
        warnings = list(candidate.get("duplicate_warnings") or [])
        if email_counts.get(candidate["email"], 0) > 1:
            warnings.append("duplicate_email_in_import")
            candidate["candidate_state"] = "needs_scope_review"
        host = _host(candidate.get("website", ""))
        if host and host_counts.get(host, 0) > 1:
            warnings.append("repeated_website_or_operator_domain")
        if host in operator_hosts:
            warnings.append("chain_or_operator_domain_review")
            candidate["candidate_state"] = "needs_scope_review"
        candidate["duplicate_warnings"] = list(dict.fromkeys(warnings))


def _state_for_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    if candidate.get("email_contact", {}).get("valid") is not True:
        return {"candidate_state": "rejected", "next_best_action": "fix_or_skip_invalid_email"}
    if candidate.get("menu_type") == "needs_scope_review" or candidate.get("scope_risk_reasons"):
        return {"candidate_state": "needs_scope_review", "next_best_action": "operator_scope_review"}
    return {"candidate_state": "pitch_ready", "next_best_action": "review_pitch_pack"}


def _pitch_quality_score(candidate: dict[str, Any]) -> int:
    score = 45
    if candidate.get("email_contact", {}).get("valid"):
        score += 15
    if candidate.get("menu_type") != "needs_scope_review":
        score += 15
    if candidate.get("website"):
        score += 10
    if (candidate.get("pitch_context") or {}).get("evidence_snippets"):
        score += 10
    if candidate.get("scope_risk_reasons"):
        score -= 20
    if candidate.get("duplicate_warnings"):
        score -= 10
    return max(0, min(100, score))


def _import_summary(candidates: list[dict[str, Any]], *, import_id: str, input_path: Path) -> dict[str, Any]:
    state_counts: dict[str, int] = {}
    menu_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    for candidate in candidates:
        state_counts[str(candidate.get("candidate_state") or "")] = state_counts.get(str(candidate.get("candidate_state") or ""), 0) + 1
        menu_counts[str(candidate.get("menu_type") or "")] = menu_counts.get(str(candidate.get("menu_type") or ""), 0) + 1
        category_counts[str(candidate.get("primary_category_v1") or "")] = category_counts.get(str(candidate.get("primary_category_v1") or ""), 0) + 1
    return {
        "import_id": import_id,
        "input_path": str(input_path),
        "created_at": utc_now(),
        "candidate_count": len(candidates),
        "state_counts": state_counts,
        "menu_type_counts": menu_counts,
        "category_counts": category_counts,
        "valid_email_count": sum(1 for candidate in candidates if candidate.get("email_contact", {}).get("valid")),
        "pitch_ready_count": sum(1 for candidate in candidates if candidate.get("candidate_state") == "pitch_ready"),
        "scope_review_count": sum(1 for candidate in candidates if candidate.get("candidate_state") == "needs_scope_review"),
    }


def _candidate_decision(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": candidate.get("candidate_id"),
        "business_name": candidate.get("business_name"),
        "candidate_state": candidate.get("candidate_state"),
        "menu_type": candidate.get("menu_type"),
        "primary_category_v1": candidate.get("primary_category_v1"),
        "email_valid": candidate.get("email_contact", {}).get("valid"),
        "pitch_quality_score": candidate.get("pitch_quality_score"),
        "scope_risk_reasons": candidate.get("scope_risk_reasons") or [],
        "duplicate_warnings": candidate.get("duplicate_warnings") or [],
        "next_best_action": candidate.get("next_best_action"),
    }


def _mark_candidate_promoted(candidate_id: str, *, import_id: str, lead_id: str, state_root: Path) -> None:
    path = _import_dir(state_root, import_id) / "candidates.json"
    candidates = read_json(path, default=[]) or []
    for candidate in candidates:
        if candidate.get("candidate_id") == candidate_id:
            candidate["candidate_state"] = "promoted"
            candidate["promoted_lead_id"] = lead_id
            candidate["updated_at"] = utc_now()
            break
    write_json(path, candidates)
    write_json(_import_dir(state_root, import_id) / "summary.json", _import_summary(candidates, import_id=import_id, input_path=Path(str(candidates[0].get("source_import", {}).get("input_path") or "")) if candidates else Path("")))
    write_json(_import_dir(state_root, import_id) / "decisions.json", [_candidate_decision(item) for item in candidates])


def _menu_template_for_menu_type(menu_type: str) -> str:
    templates = PROJECT_ROOT / "assets" / "templates"
    if menu_type.startswith("ramen"):
        return str(templates / "ramen_food_menu.html")
    if menu_type == "izakaya_drink_heavy_sake_beer":
        return str(templates / "izakaya_drinks_menu.html")
    if menu_type.startswith("izakaya"):
        return str(templates / "izakaya_food_drinks_menu.html")
    return ""


def _establishment_profile_for_menu_type(menu_type: str) -> str:
    if menu_type == "ramen_izakaya_hybrid":
        return "ramen_with_drinks"
    if menu_type.startswith("ramen"):
        return "ramen_only"
    if menu_type == "izakaya_drink_heavy_sake_beer":
        return "izakaya_drink_heavy"
    if menu_type in {"izakaya_seafood_sake_oden", "izakaya_general"}:
        return "izakaya_food_and_drinks"
    if menu_type.startswith("izakaya"):
        return "izakaya_course_heavy"
    return "unknown"


def _recommended_package_for_menu_type(menu_type: str) -> str:
    if menu_type == "ramen_standard":
        return PACKAGE_1_KEY
    if menu_type.startswith("izakaya") or menu_type == "ramen_izakaya_hybrid":
        return PACKAGE_2_KEY
    return PACKAGE_3_KEY


def _package_reason_for_menu_type(menu_type: str) -> str:
    if menu_type == "ramen_standard":
        return "simple_ramen_menu_fits_english_ordering_files"
    if menu_type.startswith("izakaya"):
        return "izakaya_table_menu_benefits_from_printed_food_drink_guide"
    if menu_type == "ramen_izakaya_hybrid":
        return "hybrid_menu_needs_counter_ready_food_drink_guide"
    return "manual_scope_review_required"


def _evidence_class_for_menu_type(menu_type: str) -> str:
    if menu_type.startswith("ramen"):
        return "ramen_menu"
    if menu_type == "izakaya_drink_heavy_sake_beer":
        return "drink_menu_photo"
    if menu_type.startswith("izakaya"):
        return "izakaya_menu"
    return "operator_attestation"


def _izakaya_rules_state_for_menu_type(menu_type: str) -> str:
    if menu_type == "izakaya_drink_heavy_sake_beer":
        return "drinks_found"
    if menu_type.startswith("izakaya"):
        return "courses_found"
    return "none_found"


def _primary_category_for_menu_type(menu_type: str) -> str:
    if menu_type.startswith("ramen"):
        return "ramen"
    if menu_type.startswith("izakaya"):
        return "izakaya"
    return "other"


def _candidate_id(*, import_id: str, name: str, website: str, email: str) -> str:
    return f"wrm-cand-{slugify(name)[:36]}-{sha256_text(import_id + name + website + email)[:8]}"


def _email_contact(email: str) -> dict[str, Any]:
    _, parsed = parseaddr(email.strip())
    valid = bool(parsed and parsed == email.strip() and _EMAIL_RE.fullmatch(parsed))
    flags: list[str] = []
    local = parsed.split("@", 1)[0] if parsed else ""
    if local in {"recruit", "recruiting", "jobs", "saiyo"}:
        flags.append("recruiting_address_review")
    if parsed.endswith(("@gmail.com", "@yahoo.co.jp", "@icloud.com", "@i.softbank.jp")):
        flags.append("personal_or_mobile_domain_review")
    return {
        "type": "email",
        "value": email,
        "valid": valid,
        "flags": flags,
        "href": f"mailto:{email}" if valid else "",
        "source": "manual_email_import",
        "actionable": valid,
    }


def _area_hint(raw_type: str) -> str:
    if "," not in raw_type:
        return ""
    return raw_type.rsplit(",", 1)[-1].strip()


def _normalise_url(value: str) -> str:
    url = str(value or "").strip()
    if url and not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _host(url: str) -> str:
    return urllib.parse.urlparse(str(url or "")).netloc.lower().removeprefix("www.")


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token.lower() in text for token in tokens)


def _assert_safe_pitch(text: str) -> None:
    lowered = text.lower()
    for token in _FORBIDDEN_COPY_TOKENS:
        if token in lowered:
            raise ValueError(f"forbidden_pitch_token:{token}")
    for token in _PRICE_TOKENS:
        if token in text:
            raise ValueError(f"forbidden_pitch_price:{token}")


def _join_paragraphs(parts: list[str]) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def _import_dir(state_root: Path, import_id: str) -> Path:
    return state_root / "manual_imports" / import_id
