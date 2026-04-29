"""Mode A: Cold outreach pipeline.

Five situation-based templates keyed on the physical ordering problem:
  ramen_menu, ramen_menu_and_machine, izakaya_menu, machine_only, unknown.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .email_templates import (
    SUBJECT,
    MACHINE_ONLY_SUBJECT,
    LINE_INPERSON,
    CONTACT_FORM_BODY,
)
from .constants import (
    GENERIC_MACHINE_PDF,
    GENERIC_MENU_PDF,
    OUTREACH_SAMPLE_IZAKAYA_FOOD_DRINKS_PDF,
    OUTREACH_SAMPLE_RAMEN_DRINKS_PDF,
    OUTREACH_SAMPLE_RAMEN_ONE_PAGE_PDF,
    OUTREACH_SAMPLE_RAMEN_SIDES_PDF,
)
from .models import QualificationResult

SUPPORTED_MANUAL_CHANNELS = {"contact_form", "line", "instagram", "phone", "walk_in"}

MANUAL_CHANNEL_LABELS = {
    "contact_form": "Contact Form Message",
    "line": "LINE Message",
    "instagram": "Instagram DM",
    "phone": "Phone Script",
    "walk_in": "Walk-in Script",
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
    if establishment_profile.startswith("izakaya"):
        return "izakaya_menu"
    if establishment_profile.startswith("ramen"):
        return "ramen_menu"
    return "unknown"


# ---------------------------------------------------------------------------
# Situation templates (Japanese + English)
# ---------------------------------------------------------------------------

_SITUATIONS = {
    "ramen_menu": {
        "intro_ja": "飲食店向けの英語メニュー制作を行っております、Chris（クリス）と申します。",
        "intro_en": "My name is Chris, and I create English menus for restaurants.",
        "focus_ja": (
            "海外からのお客様にも、ラーメンの種類・トッピング・セットメニューが伝わる英語メニューをお作りしております。\n"
            "英語メニューがあれば、混雑時でもお客様ご自身で内容をご確認・ご注文いただけるため、スタッフのご負担も減ります。"
        ),
        "focus_en": (
            "I create English menus that clearly convey ramen types, toppings, and set menus to overseas customers.\n"
            "With an English menu, customers can check the menu and order on their own even during busy hours, reducing the burden on your staff."
        ),
        "sample_ja": (
            "添付のサンプルは仕上がりのイメージをご覧いただくためのものです。\n"
            "実際は貴店のメニューに合わせて制作いたします。"
        ),
        "sample_en": (
            "The attached sample is intended to show the design and finished style.\n"
            "When creating the actual version, I would prepare it to match your restaurant's menu content."
        ),
        "photo_ja": "現在お使いのメニューのお写真をお送りいただけましたら、ご確認用のサンプルをお作りいたします。",
        "photo_en": "If you are interested, please send photos of your current menu. I will create a sample for your review.",
    },
    "ramen_menu_and_machine": {
        "intro_ja": "飲食店向けの英語メニュー制作を行っております、Chris（クリス）と申します。",
        "intro_en": "My name is Chris, and I create English menus for restaurants.",
        "focus_ja": (
            "海外からのお客様にも、ラーメンの種類・トッピング・セットメニューが伝わる英語メニューと、券売機の操作ガイドをお作りしております。\n"
            "メニューと券売機ガイドが揃えば、混雑時でもお客様が迷わずご注文いただけるようになります。"
        ),
        "focus_en": (
            "I create English menus that clearly convey ramen types, toppings, and set menus, plus English ticket machine guides.\n"
            "With both a menu and machine guide, customers can order without hesitation even during peak hours."
        ),
        "sample_ja": (
            "添付のサンプルは仕上がりのイメージをご覧いただくためのものです。\n"
            "実際は貴店のメニューと券売機に合わせて制作いたします。"
        ),
        "sample_en": (
            "The attached sample is intended to show the design and finished style.\n"
            "When creating the actual version, I would prepare it to match your restaurant's menu and ticket machine."
        ),
        "photo_ja": "現在お使いのメニューや券売機のお写真をお送りいただけましたら、ご確認用のサンプルをお作りいたします。",
        "photo_en": "If you are interested, please send photos of your current menu and ticket machine. I will create a sample for your review.",
    },
    "izakaya_menu": {
        "intro_ja": "飲食店向けの英語メニュー制作を行っております、Chris（クリス）と申します。",
        "intro_en": "My name is Chris, and I create English menus for restaurants.",
        "focus_ja": (
            "海外からのお客様にも、料理やドリンクの内容、コースや飲み放題のルールが伝わる英語メニューをお作りしております。\n"
            "食材の英語表記もありますので、アレルギーや苦手な食材の確認もお客様ご自身でできます。スタッフの方が個別にご説明する手間も省けます。"
        ),
        "focus_en": (
            "I create English menus that clearly convey food and drink details, course options, and nomihodai rules to overseas customers.\n"
            "Ingredient labels in English help customers check for allergies and preferences on their own, reducing the time staff spend explaining individually."
        ),
        "sample_ja": (
            "添付のサンプルは仕上がりのイメージをご覧いただくためのものです。\n"
            "実際は貴店のメニューに合わせて制作いたします。"
        ),
        "sample_en": (
            "The attached sample is intended to show the design and finished style.\n"
            "When creating the actual version, I would prepare it to match your restaurant's menu content."
        ),
        "photo_ja": "現在お使いのメニューのお写真をお送りいただけましたら、ご確認用のサンプルをお作りいたします。",
        "photo_en": "If you are interested, please send photos of your current menu. I will create a sample for your review.",
    },
    "machine_only": {
        "intro_ja": "飲食店向けの英語メニューや注文ガイド制作を行っております、Chris（クリス）と申します。",
        "intro_en": "My name is Chris, and I create English menus and ordering guides for restaurants.",
        "focus_ja": (
            "海外からのお客様にもラーメン屋さんの券売機操作が分かるよう、英語の注文ガイドをお作りしております。\n"
            "注文ガイドがあれば、混雑時でもお客様ご自身で券売機からご注文いただけるようになります。"
        ),
        "focus_en": (
            "I create English ordering guides that help overseas customers understand ramen shop ticket machine operations.\n"
            "With an ordering guide, customers can order from the ticket machine themselves, even during busy hours."
        ),
        "sample_ja": (
            "添付のサンプルは仕上がりのイメージをご覧いただくためのものです。\n"
            "実際は貴店の券売機に合わせて制作いたします。"
        ),
        "sample_en": (
            "The attached sample is intended to show the finished style for an ordering guide.\n"
            "When creating the actual version, I would prepare it to match your restaurant's ticket machine."
        ),
        "photo_ja": "現在お使いの券売機のお写真をお送りいただけましたら、ご確認用のサンプルをお作りいたします。",
        "photo_en": "If you are interested, please send photos of your current ticket machine. I will create a sample for your review.",
    },
    "unknown": {
        "intro_ja": "飲食店向けの英語メニュー制作を行っております、Chris（クリス）と申します。",
        "intro_en": "My name is Chris, and I create English menus for restaurants.",
        "focus_ja": "海外からのお客様へのご案内が少しでもスムーズになるよう、英語メニュー制作をお手伝いしております。",
        "focus_en": "I help make guidance for overseas customers smoother with English menu support.",
        "sample_ja": (
            "添付のサンプルは仕上がりのイメージをご覧いただくためのものです。\n"
            "実際は貴店のメニューに合わせて制作いたします。"
        ),
        "sample_en": (
            "The attached sample is intended to show the design and finished style.\n"
            "When creating the actual version, I would prepare it to match your restaurant's menu content."
        ),
        "photo_ja": "現在お使いのメニューのお写真をお送りいただけましたら、ご確認用のサンプルをお作りいたします。",
        "photo_en": "If you are interested, please send photos of your current menu. I will create a sample for your review.",
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
    # Default: no specific evidence but still a qualified lead.
    # Treat as menu-only outreach since menus are almost universal.
    return "menu_only"


# ---------------------------------------------------------------------------
# Asset selection
# ---------------------------------------------------------------------------

def select_outreach_assets(
    classification: str,
    contact_type: str = "email",
    establishment_profile: str = "unknown",
) -> list[Path]:
    """Return the PDF samples for the given classification and profile."""
    if contact_type == "contact_form":
        return []

    assets: list[Path] = []
    menu_sample = _menu_sample_for_profile(establishment_profile, classification)
    if menu_sample is not None:
        assets.append(menu_sample)

    if classification in {"menu_and_machine", "machine_only"}:
        assets.append(GENERIC_MACHINE_PDF)
    return assets


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
    include_inperson_line: bool = True,
    lead_dossier: dict[str, Any] | None = None,
) -> dict[str, str | bool]:
    """Build a diagnosis-led cold outreach email from locked templates.

    Returns {"subject": str, "body": str, "english_body": str,
    "include_menu_image": bool, "include_machine_image": bool}.
    Never calls any LLM or translation layer.
    """
    situation = _determine_situation(classification, establishment_profile)
    tmpl = _SITUATIONS[situation]
    diagnosis_ja, diagnosis_en = _diagnosis_blocks(
        situation=situation,
        establishment_profile=establishment_profile,
        lead_dossier=lead_dossier or {},
    )

    subject = (
        MACHINE_ONLY_SUBJECT if situation == "machine_only" else SUBJECT
    ).replace("{店名}", business_name)

    body = _join_paragraphs([
        f"{business_name} ご担当者様",
        "突然のご連絡にて失礼いたします。",
        tmpl["intro_ja"],
        diagnosis_ja,
        tmpl["sample_ja"],
        tmpl["photo_ja"],
        LINE_INPERSON if include_inperson_line else "",
        "送信者：Chris（クリス） / WebRefurb",
        "今後このようなご連絡が不要でしたら、お手数ですが「不要」とご返信ください。",
        "ご検討いただけますと幸いです。",
        "どうぞよろしくお願いいたします。",
        "Chris（クリス）",
    ])

    english_body = _join_paragraphs([
        f"Dear {business_name} team,",
        "I hope you do not mind my sudden message.",
        tmpl["intro_en"],
        diagnosis_en,
        tmpl["sample_en"],
        tmpl["photo_en"],
        "Lamination and direct delivery to your restaurant are also available."
        if include_inperson_line else "",
        "Sender: Chris / WebRefurb. If this is not relevant, please reply and I will not contact you again.",
        "Thank you for your consideration.",
        "I look forward to hearing from you.",
        "Chris",
    ])

    return {
        "subject": subject,
        "body": body,
        "english_body": english_body,
        "include_menu_image": situation != "machine_only",
        "include_machine_image": situation
            in ("ramen_menu_and_machine", "machine_only"),
    }


def build_contact_form_pitch() -> dict[str, str]:
    """Return the locked contact-form pitch body.

    Contact forms cannot receive attachments, so this is intentionally separate
    from the normal e-mail outreach package.
    """
    return {
        "body": CONTACT_FORM_BODY,
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
    include_inperson_line: bool = True,
    lead_dossier: dict[str, Any] | None = None,
) -> dict[str, str | bool]:
    """Build a route-specific manual outreach draft for non-email channels."""
    if channel not in SUPPORTED_MANUAL_CHANNELS:
        raise ValueError(f"Unsupported manual outreach channel: {channel}")

    situation = _determine_situation(classification, establishment_profile)
    tmpl = _SITUATIONS[situation]
    diagnosis_ja, diagnosis_en = _diagnosis_blocks(
        situation=situation,
        establishment_profile=establishment_profile,
        lead_dossier=lead_dossier or {},
    )

    support_line_jp = LINE_INPERSON if include_inperson_line else ""
    support_line_en = (
        "I can also handle lamination and delivery to your restaurant."
        if include_inperson_line else ""
    )
    phone_photo_line_ja = _phone_photo_request_jp(str(tmpl["photo_ja"]))
    include_menu_image = situation != "machine_only"
    include_machine_image = situation in ("ramen_menu_and_machine", "machine_only")

    if channel == "contact_form":
        include_menu_image = False
        include_machine_image = False
        body = CONTACT_FORM_BODY
        english_body = _join_paragraphs([
            "Hello,",
            "My name is Chris, and I create English menus and ordering guides for restaurants.",
            diagnosis_en,
            "I can prepare print-ready data, laminated copies, and restaurant delivery to match your current setup." if include_inperson_line else "I can prepare print-ready data to match your current setup.",
            tmpl["photo_en"],
            "Details: https://webrefurb.com/ja",
            "You can reply to chris@webrefurb.com.",
            "If this is not relevant, please reply and I will not contact you again.",
            "Thank you for your time.",
            "Chris",
        ])
    elif channel == "line":
        body = _join_paragraphs([
            f"{business_name} ご担当者様",
            f"突然のご連絡失礼いたします。{tmpl['intro_ja']}",
            diagnosis_ja,
            tmpl["sample_ja"],
            tmpl["photo_ja"],
            support_line_jp,
            "詳しくはこちらです。https://webrefurb.com/ja",
            "不要なご連絡でしたら「不要」とご返信ください。",
            "ご興味がございましたら、そのままご返信ください。",
            "Chris（クリス）",
        ])
        english_body = _join_paragraphs([
            f"Hello {business_name} team,",
            tmpl["intro_en"],
            diagnosis_en,
            tmpl["sample_en"],
            tmpl["photo_en"],
            support_line_en,
            "Details: https://webrefurb.com/ja",
            "If this is not relevant, please reply and I will not contact you again.",
            "If you are interested, please reply here.",
            "Chris",
        ])
    elif channel == "instagram":
        body = _join_paragraphs([
            f"{business_name} ご担当者様",
            f"突然のDM失礼いたします。{tmpl['intro_ja']}",
            diagnosis_ja,
            tmpl["sample_ja"],
            tmpl["photo_ja"],
            support_line_jp,
            "不要なご連絡でしたら「不要」とご返信ください。",
            "ご興味がございましたら、DMでご返信いただけますと幸いです。",
            "詳細: https://webrefurb.com/ja",
            "Chris（クリス）",
        ])
        english_body = _join_paragraphs([
            f"Hello {business_name} team,",
            tmpl["intro_en"],
            diagnosis_en,
            tmpl["sample_en"],
            tmpl["photo_en"],
            support_line_en,
            "If this is not relevant, please reply and I will not contact you again.",
            "If you are interested, please reply by DM.",
            "Details: https://webrefurb.com/ja",
            "Chris",
        ])
    elif channel == "phone":
        body = _join_paragraphs([
            f"お忙しいところ失礼いたします。{tmpl['intro_ja']}",
            diagnosis_ja,
            tmpl["sample_ja"],
            phone_photo_line_ja,
            support_line_jp,
            "詳細は https://webrefurb.com/ja でもご覧いただけます。",
            "ありがとうございました。",
        ])
        english_body = _join_paragraphs([
            "Hello, this is Chris. " + tmpl["intro_en"],
            diagnosis_en,
            tmpl["sample_en"],
            tmpl["photo_en"].replace("please send photos of", "could you send photos of"),
            support_line_en,
            "You can also see details at https://webrefurb.com/ja.",
            "Thank you for your time.",
        ])
    else:  # walk_in
        body = _join_paragraphs([
            f"こんにちは。{tmpl['intro_ja']}",
            diagnosis_ja,
            tmpl["sample_ja"],
            tmpl["photo_ja"].replace("お送りいただけましたら、ご確認用のサンプルをお作りいたします。", "もしご興味があれば、お写真を見せていただけますでしょうか。"),
            support_line_jp,
            "詳しくは https://webrefurb.com/ja をご覧ください。",
            "どうぞよろしくお願いいたします。",
        ])
        english_body = _join_paragraphs([
            "Hello, " + tmpl["intro_en"],
            diagnosis_en,
            tmpl["sample_en"],
            tmpl["photo_en"].replace("please send photos of your current", "could you show me photos of your current"),
            support_line_en,
            "Please see https://webrefurb.com/ja for details.",
            "Thank you very much.",
        ])

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

def _phone_photo_request_jp(photo_line: str) -> str:
    """Convert the written photo request into a natural phone-script ask."""
    cleaned = str(photo_line or "").strip()
    prefix = cleaned.split("のお写真をお送りいただけましたら", 1)[0]
    if prefix:
        return f"{prefix}のお写真を、メールかLINEでお送りいただけますでしょうか。確認用のサンプルをお作りいたします。"
    return "現在お使いのメニューのお写真を、メールかLINEでお送りいただけますでしょうか。確認用のサンプルをお作りいたします。"


def _diagnosis_blocks(
    *,
    situation: str,
    establishment_profile: str,
    lead_dossier: dict[str, Any],
) -> tuple[str, str]:
    ticket_state = str(lead_dossier.get("ticket_machine_state") or "unknown")
    english_state = str(lead_dossier.get("english_menu_state") or "unknown")
    izakaya_state = str(lead_dossier.get("izakaya_rules_state") or "unknown")

    why_ja = "貴店の公開メニューや店舗情報を拝見し、海外からのお客様が注文時に迷いやすい箇所があるかもしれないと思いご連絡しました。"
    why_en = "I reviewed your public menu and shop information and noticed there may be ordering points that are difficult for overseas guests."

    if situation == "machine_only":
        friction_ja = "特に券売機のボタン内容や購入手順が英語で分かると、混雑時でもお客様が自分で注文しやすくなります。"
        friction_en = "In particular, English guidance for ticket machine buttons and the purchase flow can help guests order on their own during busy periods."
    elif situation == "ramen_menu_and_machine":
        friction_ja = "ラーメンの種類、トッピング、セット、券売機のボタン対応が英語でつながると、注文前の確認がかなりスムーズになります。"
        friction_en = "Connecting ramen types, toppings, sets, and ticket-machine buttons in English makes the pre-order decision much smoother."
    elif situation == "izakaya_menu":
        if izakaya_state == "nomihodai_found" or establishment_profile in {"izakaya_drink_heavy", "izakaya_course_heavy"}:
            friction_ja = "料理・ドリンクだけでなく、飲み放題やコースのルールが英語で分かると、スタッフの個別説明を減らせます。"
            friction_en = "When drinks, food, nomihodai, and course rules are clear in English, staff spend less time explaining them one by one."
        else:
            friction_ja = "料理、ドリンク、コース内容が英語で整理されていると、海外のお客様が卓上で判断しやすくなります。"
            friction_en = "Clear English structure for food, drinks, and course details helps overseas guests decide at the table."
    else:
        friction_ja = "メニュー内容や注文方法が英語で整理されていると、お客様がスタッフに聞く前に自分で判断しやすくなります。"
        friction_en = "When menu content and ordering steps are organized in English, guests can decide before asking staff for help."

    if ticket_state == "unknown" and establishment_profile.startswith("ramen"):
        check_ja = "券売機の有無は公開情報だけでは断定せず、必要であればメニュー用と券売機用のどちらが合うか確認して進めます。"
        check_en = "I would not assume whether you use a ticket machine from public information alone; I would first check whether a menu guide, ticket-machine guide, or both are useful."
    elif english_state == "unknown":
        check_ja = "英語メニューの有無は念のため確認し、すでに十分な英語案内がある場合は制作をおすすめしません。"
        check_en = "I would first check whether you already have complete English ordering support; if you do, I would not recommend extra work."
    else:
        check_ja = "小さな確認用サンプルから始め、実際の制作では貴店からいただく最新のメニュー写真に合わせます。"
        check_en = "I would start with a small review sample and base the actual work on current menu photos from your shop."

    return _join_paragraphs([why_ja, friction_ja, check_ja]), _join_paragraphs([why_en, friction_en, check_en])


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
        "machine_only": {
            "strategy_label": "Ticket machine sample set",
            "strategy_note": "Selected because this lead only has ticket-machine ordering evidence, so the outreach stays focused on ordering guidance.",
            "menu_label": "English Menu Sample",
        },
        "unknown": {
            "strategy_label": "General sample set",
            "strategy_note": "Selected the general menu sample because the establishment profile still needs manual review.",
            "menu_label": "English Menu Sample",
        },
    }
    return plans[situation]


def _join_paragraphs(paragraphs: list[str]) -> str:
    return "\n\n".join(p.strip() for p in paragraphs if p and p.strip())
