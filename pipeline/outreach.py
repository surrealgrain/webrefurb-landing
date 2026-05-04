"""Mode A: Cold outreach pipeline.

Situation-based templates keyed on what evidence we found at each shop:
  ramen_menu, ramen_menu_and_machine, izakaya_menu, izakaya_nomihodai, machine_only.

Design: lead with their actual menu evidence, one-word CTA (「希望」),
no PDF attachments on first contact, full business signature.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .email_templates import (
    SUBJECT_MENU,
    SUBJECT_MACHINE,
    SUBJECT_NOMIHODAI,
    CONTACT_FORM_BODY,
    OPT_OUT_JA,
    OPT_OUT_EN,
    SIGNATURE_FULL,
    SENDER_NAME,
    SENDER_EMAIL,
    SITE_URL,
    SUBJECT_BY_TEMPLATE,
    build_menu_topic_phrase,
    build_evidence_line_ja,
    build_benefit_line_ja,
    build_cta_ja,
    build_graceful_exit_ja,
)
from .constants import (
    GENERIC_MACHINE_PDF,
    GENERIC_MENU_PDF,
    OUTREACH_SAMPLE_IZAKAYA_FOOD_DRINKS_PDF,
    OUTREACH_SAMPLE_BY_ESTABLISHMENT_PROFILE,
    OUTREACH_SAMPLE_RAMEN_DRINKS_PDF,
    OUTREACH_SAMPLE_RAMEN_ONE_PAGE_PDF,
    OUTREACH_SAMPLE_RAMEN_SIDES_PDF,
)
from .models import QualificationResult

SUPPORTED_MANUAL_CHANNELS = {"contact_form"}

MANUAL_CHANNEL_LABELS = {
    "contact_form": "Contact Form Message",
}


# ---------------------------------------------------------------------------
# Situation determination
# ---------------------------------------------------------------------------

def _determine_situation(classification: str, establishment_profile: str) -> str:
    """Map classification + profile to one of 5 outreach situations."""
    if classification == "machine_only":
        return "machine_only"
    if classification == "menu_and_machine":
        return "ramen_menu_and_machine"
    if establishment_profile in {"izakaya_drink_heavy", "izakaya_course_heavy"}:
        return "izakaya_nomihodai"
    if establishment_profile.startswith("izakaya"):
        return "izakaya_menu"
    if establishment_profile.startswith("ramen"):
        return "ramen_menu"
    # Unknown establishment — default to ramen (primary business)
    return "ramen_menu"


# ---------------------------------------------------------------------------
# Situation templates (Japanese + English)
# ---------------------------------------------------------------------------

_SITUATIONS = {
    "ramen_menu": {
        "subject": SUBJECT_MENU,
        "genre_intro_ja": "ラーメン店向けに英語メニュー制作を行っております、WebRefurbのChris（クリス）と申します。",
        "genre_intro_en": "My name is Chris from WebRefurb. I create English menus for ramen restaurants.",
        "evidence_ja": "公開されている貴店メニューを拝見し、ラーメンの種類・トッピング・セット内容などについて、海外のお客様にも内容が伝わりやすい英語表記をご提案できればと思い、ご連絡いたしました。",
        "evidence_en": "After reviewing your public menu, I believe I can prepare English display labels that help overseas guests easily understand the ramen types, toppings, and set contents.",
        "benefit_ja": "英語表記がメニュー内容や注文方法に対応していると、お客様が注文前に判断しやすくなり、スタッフの方へのご質問を減らすことにもつながります。",
        "benefit_en": "When English labels connect to the actual menu items and ordering steps, customers can decide before ordering, reducing the need to ask staff questions.",
        "cta_ja": "ご希望でしたら、公開されているメニュー情報をもとに、1ページ分の確認用サンプルを無料でお作りします。\nこのメールに「希望」とだけご返信いただければ結構です。",
        "cta_en": "If you are interested, I can prepare a one-page review sample based on your public menu, free of charge.\nSimply reply to this email with 「希望」 (interested).",
        "graceful_exit_ja": "すでに十分な英語メニューをご用意済みでしたら、ご放念ください。",
        "graceful_exit_en": "If you already have a sufficient English menu, please disregard this message.",
    },
    "ramen_menu_and_machine": {
        "subject": SUBJECT_MACHINE,
        "genre_intro_ja": "ラーメン店向けに英語メニュー・英語注文ガイド制作を行っております、WebRefurbのChris（クリス）と申します。",
        "genre_intro_en": "My name is Chris from WebRefurb. I create English menus and ordering guides for ramen restaurants.",
        "evidence_ja": "公開されている貴店のメニューと券売機の表示を拝見し、海外のお客様が注文前に確認しやすい英語表記をご提案できればと思い、ご連絡いたしました。",
        "evidence_en": "After reviewing your public menu and ticket machine display, I believe I can prepare English labels that help overseas guests order with confidence.",
        "benefit_ja": "ラーメンの種類、トッピング、セット内容、券売機ボタンの表記が英語で対応していると、初めて来店される海外のお客様でも券売機前で迷いにくくなります。",
        "benefit_en": "When ramen types, toppings, set contents, and ticket machine buttons are clearly labeled in English, first-time overseas visitors can order from the machine with confidence.",
        "cta_ja": "ご希望でしたら、公開されているメニュー情報をもとに、1ページ分の確認用サンプルを無料でお作りします。\nこのメールに「希望」とだけご返信いただければ結構です。\n\n実際に制作する際は、最新のメニューや券売機のお写真を確認してから進めます。",
        "cta_en": "If you are interested, I can prepare a one-page review sample based on your public menu.\nSimply reply with 「希望」 (interested).\n\nWhen proceeding with the actual order, I would confirm using your latest menu and machine photos.",
        "graceful_exit_ja": "",
        "graceful_exit_en": "",
    },
    "izakaya_menu": {
        "subject": SUBJECT_MENU,
        "genre_intro_ja": "居酒屋向けに英語メニュー制作を行っております、WebRefurbのChris（クリス）と申します。",
        "genre_intro_en": "My name is Chris from WebRefurb. I create English menus for izakaya restaurants.",
        "evidence_ja": "公開されている貴店メニューを拝見し、料理・ドリンク・コース内容などについて、海外のお客様にも内容が伝わりやすい英語表記をご提案できればと思い、ご連絡いたしました。",
        "evidence_en": "After reviewing your public menu, I believe I can prepare English display labels that help overseas guests easily understand the food, drinks, and course options.",
        "benefit_ja": "料理、ドリンク、コース内容が英語で整理されていると、海外のお客様が卓上で判断しやすくなり、スタッフの方へのご質問も減らしやすくなります。",
        "benefit_en": "When food, drinks, and course details are organized in English, overseas guests can decide at the table, reducing the need to ask staff questions.",
        "cta_ja": "ご希望でしたら、公開されているメニュー情報をもとに、1ページ分の確認用サンプルを無料でお作りします。\nこのメールに「希望」とだけご返信いただければ結構です。",
        "cta_en": "If you are interested, I can prepare a one-page review sample based on your public menu, free of charge.\nSimply reply with 「希望」 (interested).",
        "graceful_exit_ja": "すでに十分な英語メニューをご用意済みでしたら、ご放念ください。",
        "graceful_exit_en": "If you already have a sufficient English menu, please disregard this message.",
    },
    "izakaya_nomihodai": {
        "subject": SUBJECT_NOMIHODAI,
        "genre_intro_ja": "居酒屋向けに英語メニュー制作を行っております、WebRefurbのChris（クリス）と申します。",
        "genre_intro_en": "My name is Chris from WebRefurb. I create English menus for izakaya restaurants.",
        "evidence_ja": "公開されている貴店メニューを拝見し、料理・ドリンク・飲み放題・コース内容などについて、海外のお客様にも内容が伝わりやすい英語表記をご提案できればと思い、ご連絡いたしました。",
        "evidence_en": "After reviewing your public menu — including food, drinks, nomihodai, and course content — I believe I can prepare English display labels that help overseas guests understand the full offering.",
        "benefit_ja": "飲み放題のルール、ラストオーダー、コース内容、追加料金などが英語で整理されていると、海外のお客様が卓上で判断しやすくなり、スタッフの方への個別のご質問を減らすことにもつながります。",
        "benefit_en": "When nomihodai rules, last order times, course contents, and additional charges are clearly organized in English, overseas guests can decide at the table, and staff spend less time answering individual questions.",
        "cta_ja": "ご希望でしたら、公開されているメニュー情報をもとに、1ページ分の確認用サンプルを無料でお作りします。\nこのメールに「希望」とだけご返信いただければ結構です。",
        "cta_en": "If you are interested, I can prepare a one-page review sample based on your public menu, free of charge.\nSimply reply with 「希望」 (interested).",
        "graceful_exit_ja": "すでに十分な英語メニューをご用意済みでしたら、ご放念ください。",
        "graceful_exit_en": "If you already have a sufficient English menu, please disregard this message.",
    },
    "machine_only": {
        "subject": SUBJECT_MACHINE,
        "genre_intro_ja": "ラーメン店向けに英語メニュー・英語注文ガイド制作を行っております、WebRefurbのChris（クリス）と申します。",
        "genre_intro_en": "My name is Chris from WebRefurb. I create English menus and ordering guides for ramen restaurants.",
        "evidence_ja": "公開されている貴店の券売機の表示を拝見し、海外のお客様が注文前に確認しやすい英語注文ガイドをご提案できればと思い、ご連絡いたしました。",
        "evidence_en": "After reviewing your public ticket machine display, I believe I can prepare an English ordering guide that helps overseas guests order with confidence.",
        "benefit_ja": "券売機のボタン内容や購入手順が英語で分かると、混雑時でもお客様が自分で注文しやすくなります。",
        "benefit_en": "When ticket machine buttons and purchase steps are labeled in English, customers can order on their own even during busy periods.",
        "cta_ja": "ご希望でしたら、券売機横に置ける1ページ分の確認用サンプルを無料でお作りします。\nこのメールに「希望」とだけご返信いただければ結構です。\n\n実際に制作する際は、最新の券売機写真やメニュー写真を確認してから進めます。",
        "cta_en": "If you are interested, I can prepare a one-page sample that can be placed next to the ticket machine.\nSimply reply with 「希望」 (interested).\n\nWhen proceeding with the actual order, I would confirm using your latest machine and menu photos.",
        "graceful_exit_ja": "",
        "graceful_exit_en": "",
    },
}


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_business(qualification: QualificationResult) -> str:
    """Classify what outreach assets a business needs.

    Returns one of: "menu_only", "menu_and_machine",
    "menu_machine_unconfirmed", "machine_only".
    """
    has_menu = qualification.menu_evidence_found
    has_machine = qualification.machine_evidence_found

    if has_menu and has_machine:
        return "menu_and_machine"
    if has_menu and not has_machine:
        return "menu_machine_unconfirmed"
    if not has_menu and has_machine:
        return "machine_only"
    return "menu_only"


# ---------------------------------------------------------------------------
# Asset selection
# ---------------------------------------------------------------------------

def select_outreach_assets(
    classification: str,
    contact_type: str = "email",
    establishment_profile: str = "unknown",
) -> list[Path]:
    """Return PDF samples for the given classification and profile.

    First-contact emails no longer attach PDFs — only inline preview images.
    This function returns an empty list.  It remains for backward compatibility
    and can be re-enabled for post-reply follow-ups.
    """
    return []


def describe_outreach_assets(
    assets: list[Path],
    *,
    classification: str,
    establishment_profile: str = "unknown",
) -> dict[str, Any]:
    """Return operator-facing labels and rationale for selected sample files."""
    situation = _determine_situation(classification, establishment_profile)
    profile_plan = _profile_asset_plan(situation)
    menu_sample = _menu_sample_for_profile(establishment_profile, classification)
    described_assets: list[dict[str, str]] = []

    for path in assets:
        if path == GENERIC_MACHINE_PDF:
            described_assets.append(
                {
                    "path": str(path),
                    "label": "Ticket Machine Guide Sample",
                    "kind": "machine",
                }
            )
        elif menu_sample is not None and path == menu_sample:
            described_assets.append(
                {
                    "path": str(path),
                    "label": profile_plan["menu_label"],
                    "kind": "menu",
                }
            )
        else:
            described_assets.append(
                {
                    "path": str(path),
                    "label": "English Menu Sample",
                    "kind": "menu",
                }
            )

    return {
        "strategy_label": profile_plan["strategy_label"],
        "strategy_note": profile_plan["strategy_note"],
        "assets": described_assets,
    }


# ---------------------------------------------------------------------------
# Email builder
# ---------------------------------------------------------------------------

def build_outreach_email(
    *,
    business_name: str,
    classification: str,
    establishment_profile: str = "unknown",
    include_inperson_line: bool = False,
    city: str = "",
    lead_dossier: dict[str, Any] | None = None,
) -> dict[str, str | bool]:
    """Build a cold outreach email from locked situation templates.

    Returns {"subject": str, "body": str, "english_body": str,
    "include_menu_image": bool, "include_machine_image": bool}.
    Never calls any LLM or translation layer.
    """
    situation = _determine_situation(classification, establishment_profile)
    tmpl = _SITUATIONS[situation]

    subject = tmpl["subject"]
    observation = _shop_observation(lead_dossier or {})

    # -- Japanese body -------------------------------------------------------
    body = _join_paragraphs([
        f"{business_name} ご担当者様",
        "初めてご連絡いたします。",
        tmpl["genre_intro_ja"],
        tmpl["evidence_ja"],
        observation["ja"],
        tmpl["benefit_ja"],
        tmpl["cta_ja"],
        tmpl.get("graceful_exit_ja") or "",
        OPT_OUT_JA,
        "どうぞよろしくお願いいたします。",
        SIGNATURE_FULL,
    ])

    # -- English body --------------------------------------------------------
    english_body = _join_paragraphs([
        f"Dear {business_name} team,",
        "I hope you do not mind my reaching out.",
        tmpl["genre_intro_en"],
        tmpl["evidence_en"],
        observation["en"],
        tmpl["benefit_en"],
        tmpl["cta_en"],
        tmpl.get("graceful_exit_en") or "",
        OPT_OUT_EN,
        "Thank you for your consideration.",
        SENDER_NAME,
    ])

    return {
        "subject": subject,
        "body": body,
        "english_body": english_body,
        "include_menu_image": situation != "machine_only",
        "include_machine_image": situation
            in ("ramen_menu_and_machine", "machine_only"),
    }


# ---------------------------------------------------------------------------
# Evidence-gated email builder
# ---------------------------------------------------------------------------

def build_evidence_gated_email(
    classification: dict[str, Any],
) -> dict[str, str | bool] | None:
    """Build an outreach email from an evidence-gated classification.

    Uses the classification object from ``evidence_classifier.classify_lead``
    to dynamically assemble email content.  Every claim is backed by evidence.

    Returns None if selected_template is "skip".
    """
    template = classification["selected_template"]
    if template == "skip":
        return None

    allowed = classification["allowed_claims"]
    business_name = classification["business_name"] or "テスト"
    restaurant_type = classification["restaurant_type"]
    topics = classification["observed_menu_topics"]

    # -- Subject ------------------------------------------------------------
    subject = SUBJECT_BY_TEMPLATE.get(template, SUBJECT_MENU)

    # -- Genre intro --------------------------------------------------------
    if restaurant_type == "ramen":
        if template in (
            "ramen_menu_plus_ticket_machine",
            "ramen_ticket_machine_only",
            "ramen_needs_ticket_machine_photo",
        ):
            genre_intro = (
                "ラーメン店向けに英語メニュー・英語注文ガイド制作を行っております、"
                "WebRefurbのChris（クリス）と申します。"
            )
        else:
            genre_intro = (
                "ラーメン店向けに英語メニュー制作を行っております、"
                "WebRefurbのChris（クリス）と申します。"
            )
    else:
        genre_intro = (
            "居酒屋向けに英語メニュー制作を行っております、"
            "WebRefurbのChris（クリス）と申します。"
        )

    # -- Evidence line (dynamic) --------------------------------------------
    if "mention_public_menu" in allowed:
        topic_phrase = build_menu_topic_phrase(topics, restaurant_type)
        evidence_line = build_evidence_line_ja(
            public_menu_found=True,
            menu_topic_phrase=topic_phrase,
            restaurant_type=restaurant_type,
        )
    else:
        evidence_line = ""

    # -- Benefit line (dynamic) ---------------------------------------------
    benefit_line = build_benefit_line_ja(
        restaurant_type=restaurant_type,
        observed_topics=topics,
        allowed_claims=allowed,
        template=template,
    )

    # -- CTA (dynamic) ------------------------------------------------------
    needs_photo = template.endswith("_needs_menu_photo") or template.endswith("_needs_ticket_machine_photo")
    cta = build_cta_ja(
        public_menu_usable=classification["public_menu_usable_for_sample"],
        ticket_machine_content_usable=classification["ticket_machine_content_usable"],
        needs_photo=needs_photo,
        has_ticket_machine="mention_ticket_machine" in allowed,
        template=template,
    )

    # -- Graceful exit ------------------------------------------------------
    graceful = build_graceful_exit_ja(
        classification["existing_english_menu_quality"]
    )

    # -- Assemble body ------------------------------------------------------
    parts = [
        f"{business_name} ご担当者様",
        "初めてご連絡いたします。",
        genre_intro,
    ]
    if evidence_line:
        parts.append(evidence_line)
    if benefit_line:
        parts.append(benefit_line)
    parts.append(cta)
    if graceful:
        parts.append(graceful)
    parts.extend([
        OPT_OUT_JA,
        "どうぞよろしくお願いいたします。",
        SENDER_NAME,
    ])

    body = _join_paragraphs([p for p in parts if p])

    # -- English body (simplified mirror) -----------------------------------
    en_parts = [
        f"Dear {business_name} team,",
        "I hope you do not mind my reaching out.",
        f"My name is Chris from WebRefurb. I create English menus for {'ramen shops' if restaurant_type == 'ramen' else 'izakaya'}.",
    ]
    if evidence_line:
        en_parts.append(
            "After reviewing your public menu, I believe I can prepare "
            "English display labels that help overseas guests easily "
            "understand the offerings."
        )
    if benefit_line:
        en_parts.append(
            "Clear English labels help customers decide before ordering, "
            "reducing the need to ask staff questions."
        )
    en_parts.append(
        "Simply reply with 「希望」 (interested) and I will prepare "
        "a one-page sample for your review."
    )
    if graceful:
        en_parts.append(
            "If you already have a sufficient English menu, "
            "please disregard this message."
        )
    en_parts.extend([
        OPT_OUT_EN,
        "Thank you for your consideration.",
        SENDER_NAME,
    ])

    english_body = _join_paragraphs([p for p in en_parts if p])

    # -- Image flags --------------------------------------------------------
    include_menu = template not in (
        "ramen_ticket_machine_only", "ramen_needs_ticket_machine_photo",
    )
    include_machine = template in (
        "ramen_menu_plus_ticket_machine", "ramen_ticket_machine_only",
        "ramen_needs_ticket_machine_photo",
    )

    return {
        "subject": subject,
        "body": body,
        "english_body": english_body,
        "include_menu_image": include_menu and classification["public_menu_usable_for_sample"],
        "include_machine_image": include_machine,
        "classification": classification,
    }


def build_contact_form_pitch(*, sample_menu_url: str = "", sender_name: str = "Chris（クリス）") -> dict[str, str]:
    """Return the locked contact-form pitch body.

    Contact forms cannot receive attachments, so this is intentionally separate
    from the normal e-mail outreach package.
    """
    return {
        "body": _contact_form_body(sample_menu_url=sample_menu_url, sender_name=sender_name),
        "channel": "form",
    }


# ---------------------------------------------------------------------------
# Manual channel builders
# ---------------------------------------------------------------------------

def build_manual_outreach_message(
    *,
    business_name: str,
    classification: str,
    channel: str,
    establishment_profile: str = "unknown",
    include_inperson_line: bool = False,
    lead_dossier: dict[str, Any] | None = None,
    sample_menu_url: str = "",
    sender_name: str = "Chris（クリス）",
    city: str = "",
) -> dict[str, str | bool]:
    """Build a route-specific manual outreach draft for non-email channels."""
    if channel not in SUPPORTED_MANUAL_CHANNELS:
        raise ValueError(f"Unsupported manual outreach channel: {channel}")

    include_menu_image = False
    include_machine_image = False

    if channel == "contact_form":
        body = _contact_form_body(sample_menu_url=sample_menu_url, sender_name=sender_name)
        english_body = _join_paragraphs([
            "Hello,",
            f"This is {sender_name} from WebRefurb.",
            "I reviewed your public menu information and would like to share an English menu sample.",
            f"You can view it here: {sample_menu_url}" if sample_menu_url else "",
            "If you are interested, please reply through this contact form.",
            "No reply is needed if this is not relevant.",
            sender_name,
        ])
    else:
        raise ValueError(f"Unsupported manual outreach channel: {channel}")

    return {
        "subject": "",
        "body": body,
        "english_body": english_body,
        "include_menu_image": include_menu_image,
        "include_machine_image": include_machine_image,
        "channel": channel,
        "channel_label": MANUAL_CHANNEL_LABELS[channel],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _contact_form_body(*, sample_menu_url: str = "", sender_name: str = "Chris（クリス）") -> str:
    if not sample_menu_url:
        return CONTACT_FORM_BODY

    return _join_paragraphs([
        "お問い合わせフォームより失礼いたします。",
        f"WebRefurbの{sender_name}です。ラーメン店・居酒屋向けに英語メニュー制作を行っております。",
        "公開されているメニュー情報を拝見し、海外のお客様にも内容が伝わりやすい英語メニュー表記の確認用サンプルを1ページ作成しました。",
        f"添付ではなく、こちらのページからご確認いただけます：\n{sample_menu_url}",
        "ご興味がございましたら、chris@webrefurb.com まで「希望」とご連絡いただけますと幸いです。\n不要でしたらご返信不要です。",
        "どうぞよろしくお願いいたします。",
        sender_name,
    ])


def _shop_observation(lead_dossier: dict[str, Any]) -> dict[str, str]:
    proof_items = lead_dossier.get("proof_items") if isinstance(lead_dossier, dict) else []
    if not isinstance(proof_items, list):
        proof_items = []
    for item in proof_items:
        if not isinstance(item, dict) or item.get("customer_preview_eligible") is not True:
            continue
        snippet = _safe_observation_snippet(str(item.get("snippet") or ""))
        if snippet:
            return {
                "ja": f"公開情報では「{snippet}」などのメニュー・注文情報を確認しました。",
                "en": f"I saw public menu or ordering details such as \"{snippet}\".",
            }
    return {"ja": "", "en": ""}


def _safe_observation_snippet(value: str) -> str:
    cleaned = " ".join(str(value or "").split())
    if not cleaned:
        return ""
    blocked = ("求人", "採用", "予約", "ログイン", "javascript", "cookie", "電話番号", "copyright")
    lowered = cleaned.lower()
    if any(token.lower() in lowered for token in blocked):
        return ""
    return cleaned[:80]


def _menu_sample_for_profile(establishment_profile: str, classification: str) -> Path | None:
    if classification == "machine_only":
        return None

    profile_assets = {
        "ramen_only": OUTREACH_SAMPLE_RAMEN_ONE_PAGE_PDF,
        "ramen_with_sides_add_ons": OUTREACH_SAMPLE_RAMEN_SIDES_PDF,
        "ramen_with_drinks": OUTREACH_SAMPLE_RAMEN_DRINKS_PDF,
        "ramen_ticket_machine": OUTREACH_SAMPLE_RAMEN_DRINKS_PDF,
        "izakaya_food_and_drinks": OUTREACH_SAMPLE_IZAKAYA_FOOD_DRINKS_PDF,
        "izakaya_drink_heavy": OUTREACH_SAMPLE_IZAKAYA_FOOD_DRINKS_PDF,
        "izakaya_course_heavy": OUTREACH_SAMPLE_IZAKAYA_FOOD_DRINKS_PDF,
        **OUTREACH_SAMPLE_BY_ESTABLISHMENT_PROFILE,
    }
    candidate = profile_assets.get(establishment_profile, GENERIC_MENU_PDF)
    return candidate if candidate.exists() else GENERIC_MENU_PDF


def _profile_asset_plan(situation: str) -> dict[str, str]:
    plans = {
        "ramen_menu": {
            "strategy_label": "Ramen menu sample set",
            "strategy_note": "Selected a ramen-focused sample because this lead has menu evidence without ticket machine evidence.",
            "menu_label": "Ramen Menu Sample",
        },
        "ramen_menu_and_machine": {
            "strategy_label": "Ramen menu + ticket machine sample set",
            "strategy_note": "Selected menu plus ticket-machine proof because this lead has evidence that guests need both menu and ordering guidance.",
            "menu_label": "Ramen Menu + Machine Guide Sample",
        },
        "izakaya_menu": {
            "strategy_label": "Izakaya sample set",
            "strategy_note": "Selected a food-and-drinks sample because this lead looks like an izakaya where both sections matter in the customer experience.",
            "menu_label": "Izakaya Food + Drinks Sample",
        },
        "izakaya_nomihodai": {
            "strategy_label": "Izakaya nomihodai sample set",
            "strategy_note": "Selected a nomihodai/course sample because this izakaya has drink-heavy or course-heavy evidence.",
            "menu_label": "Izakaya Nomihodai Sample",
        },
        "machine_only": {
            "strategy_label": "Ticket machine sample set",
            "strategy_note": "Selected because this lead only has ticket-machine ordering evidence, so the outreach stays focused on ordering guidance.",
            "menu_label": "English Menu Sample",
        },
    }
    return plans[situation]


def _join_paragraphs(paragraphs: list[str]) -> str:
    return "\n\n".join(p.strip() for p in paragraphs if p and p.strip())
