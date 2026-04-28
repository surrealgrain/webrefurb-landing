"""Mode A: Cold outreach pipeline.

Classifies a business, selects the correct generic PDF assets,
and builds a cold outreach email from the locked template.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .email_templates import (
    SUBJECT,
    MACHINE_ONLY_SUBJECT,
    BODY,
    MACHINE_ONLY_BODY,
    LINE_INPERSON,
    LINE_MACHINE,
    ENGLISH_BODY,
    MACHINE_ONLY_ENGLISH_BODY,
    ENGLISH_LINE_INPERSON,
    ENGLISH_LINE_MACHINE,
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
    profile_plan = _profile_asset_plan(establishment_profile, classification)
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


def build_outreach_email(
    *,
    business_name: str,
    classification: str,
    establishment_profile: str = "unknown",
    include_inperson_line: bool = True,
) -> dict[str, str | bool]:
    """Build a cold outreach email from the locked template.

    Returns {"subject": str, "body": str, "include_menu_image": bool,
    "include_machine_image": bool}.
    Never calls any LLM or translation layer.
    """
    detail = _outreach_detail(classification, establishment_profile)

    if classification == "machine_only":
        subject = MACHINE_ONLY_SUBJECT.replace("{店名}", business_name)
        body = MACHINE_ONLY_BODY.replace("{店名}", business_name)
        english_body = MACHINE_ONLY_ENGLISH_BODY.replace("{store_name}", business_name)
        include_menu_image = False
        include_machine_image = True
    else:
        subject = SUBJECT.replace("{店名}", business_name)
        body = _join_paragraphs([
            f"{business_name} ご担当者様",
            "突然のご連絡にて失礼いたします。",
            "飲食店向けの英語メニュー制作を行っております、Chris（クリス）と申します。",
            detail["japanese_focus"],
            detail["japanese_sample_note"],
            "実際に制作する際は、貴店のメニュー内容に合わせて作成いたします。",
            detail["japanese_photo_request"],
            LINE_INPERSON if include_inperson_line else "",
            "ご検討いただけますと幸いです。",
            "どうぞよろしくお願いいたします。",
            "Chris（クリス）",
        ])
        english_body = _join_paragraphs([
            f"Dear {business_name} team,",
            "I hope you do not mind my sudden message.",
            "My name is Chris, and I create English menus for restaurants.",
            detail["english_focus"],
            detail["english_sample_note"],
            "When creating the actual version, I would prepare it to match your restaurant's menu content.",
            detail["english_photo_request"],
            ENGLISH_LINE_INPERSON if include_inperson_line else "",
            "Thank you for your consideration.",
            "I look forward to hearing from you.",
            "Chris",
        ])
        include_menu_image = True
        include_machine_image = False

    # Insert machine line for menu_and_machine classification
    if classification == "menu_and_machine":
        body = _insert_machine_line(body)
        english_body = _insert_english_machine_line(english_body)
        include_machine_image = True

    return {
        "subject": subject,
        "body": body,
        "english_body": english_body,
        "include_menu_image": include_menu_image,
        "include_machine_image": include_machine_image,
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


def build_manual_outreach_message(
    *,
    business_name: str,
    classification: str,
    channel: str,
    establishment_profile: str = "unknown",
    include_inperson_line: bool = True,
) -> dict[str, str | bool]:
    """Build a route-specific manual outreach draft for non-email channels."""
    if channel not in SUPPORTED_MANUAL_CHANNELS:
        raise ValueError(f"Unsupported manual outreach channel: {channel}")

    detail = _outreach_detail(classification, establishment_profile)
    support_line_jp = (
        "ラミネート加工や店舗へのお届けまで対応可能です。"
        if include_inperson_line
        else ""
    )
    support_line_en = (
        "I can also handle lamination and delivery to your restaurant."
        if include_inperson_line
        else ""
    )
    include_menu_image = classification != "machine_only"
    include_machine_image = classification in {"menu_and_machine", "machine_only"}

    if channel == "contact_form":
        include_menu_image = False
        include_machine_image = False
        body = CONTACT_FORM_BODY
        english_body = _join_paragraphs([
            "Hello,",
            "My name is Chris from WebRefurb, and I create English menus and ordering guides for restaurants.",
            detail["english_focus"],
            "I can prepare print-ready data, laminated copies, and restaurant delivery to match your current setup." if include_inperson_line else "I can prepare print-ready data to match your current setup.",
            detail["english_photo_request"],
            "Details: https://webrefurb.com/ja",
            "You can reply to chris@webrefurb.com.",
            "Thank you for your time.",
            "Chris",
        ])
    elif channel == "line":
        body = _join_paragraphs([
            f"{business_name} ご担当者様",
            "突然のご連絡失礼いたします。飲食店向けの英語メニューや注文ガイド制作をしているChris（クリス）です。",
            detail["japanese_focus"],
            detail["japanese_sample_note"],
            detail["japanese_photo_request"],
            support_line_jp,
            "詳しくはこちらです。https://webrefurb.com/ja",
            "ご興味がございましたら、そのままご返信ください。",
            "Chris（クリス）",
        ])
        english_body = _join_paragraphs([
            f"Hello {business_name} team,",
            "My name is Chris, and I create English menus and ordering guides for restaurants.",
            detail["english_focus"],
            detail["english_sample_note"],
            detail["english_photo_request"],
            support_line_en,
            "Details: https://webrefurb.com/ja",
            "If you are interested, please reply here.",
            "Chris",
        ])
    elif channel == "instagram":
        body = _join_paragraphs([
            f"{business_name} ご担当者様",
            "突然のDM失礼いたします。飲食店向けの英語メニューや注文ガイド制作をしているChris（クリス）です。",
            detail["japanese_focus"],
            detail["japanese_sample_note"],
            detail["japanese_photo_request"],
            support_line_jp,
            "ご興味がございましたら、DMでご返信いただけますと幸いです。",
            "詳細: https://webrefurb.com/ja",
            "Chris（クリス）",
        ])
        english_body = _join_paragraphs([
            f"Hello {business_name} team,",
            "My name is Chris, and I create English menus and ordering guides for restaurants.",
            detail["english_focus"],
            detail["english_sample_note"],
            detail["english_photo_request"],
            support_line_en,
            "If you are interested, please reply by DM.",
            "Details: https://webrefurb.com/ja",
            "Chris",
        ])
    elif channel == "phone":
        body = _join_paragraphs([
            "お忙しいところ失礼いたします。飲食店向けの英語メニューや注文ガイド制作をしているChris（クリス）と申します。",
            detail["japanese_focus"],
            detail["japanese_sample_note"],
            detail["japanese_photo_request"].replace("お送りください。", "メールかLINEでお送りいただけますでしょうか。"),
            support_line_jp,
            "詳細は https://webrefurb.com/ja でもご覧いただけます。",
            "ありがとうございました。",
        ])
        english_body = _join_paragraphs([
            "Hello, this is Chris. I create English menus and ordering guides for restaurants.",
            detail["english_focus"],
            detail["english_sample_note"],
            detail["english_photo_request"].replace("please send photos of your current materials.", "if this sounds helpful, could you send photos of your current materials by email or LINE?"),
            support_line_en,
            "You can also see details at https://webrefurb.com/ja.",
            "Thank you for your time.",
        ])
    else:
        body = _join_paragraphs([
            "こんにちは。飲食店向けの英語メニューや注文ガイド制作をしているChris（クリス）と申します。",
            detail["japanese_focus"],
            detail["japanese_sample_note"],
            detail["japanese_photo_request"].replace("お送りください。", "もしご興味があれば、お写真を見せていただけますでしょうか。"),
            support_line_jp,
            "詳しくは https://webrefurb.com/ja をご覧ください。",
            "どうぞよろしくお願いいたします。",
        ])
        english_body = _join_paragraphs([
            "Hello, my name is Chris, and I create English menus and ordering guides for restaurants.",
            detail["english_focus"],
            detail["english_sample_note"],
            detail["english_photo_request"].replace("please send photos of your current materials.", "if you are interested, could you show me photos of your current materials?"),
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


def _remove_inperson_line(body: str) -> str:
    """Remove the in-person delivery line and its surrounding blank line."""
    line_with_newline = f"\n{LINE_INPERSON}\n"
    if line_with_newline in body:
        body = body.replace(line_with_newline, "\n")
    elif LINE_INPERSON in body:
        body = body.replace(LINE_INPERSON, "")
    return body


def _insert_machine_line(body: str) -> str:
    """Insert the ticket machine line after the menu sample paragraph."""
    anchor = "実際に制作する際は、貴店のメニュー内容に合わせて作成いたします。"
    replacement = f"{anchor}\n{LINE_MACHINE}"
    return body.replace(anchor, replacement, 1)


def _remove_english_inperson_line(body: str) -> str:
    """Remove the in-person delivery line from the English operator draft."""
    line_with_newline = f"\n{ENGLISH_LINE_INPERSON}\n"
    if line_with_newline in body:
        body = body.replace(line_with_newline, "\n")
    elif ENGLISH_LINE_INPERSON in body:
        body = body.replace(ENGLISH_LINE_INPERSON, "")
    return body


def _insert_english_machine_line(body: str) -> str:
    """Insert the ticket machine line after the sample paragraph."""
    anchor = "When creating the actual version, I would prepare it to match your restaurant's menu content."
    replacement = f"{anchor}\n{ENGLISH_LINE_MACHINE}"
    return body.replace(anchor, replacement, 1)


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


def _profile_asset_plan(establishment_profile: str, classification: str) -> dict[str, str]:
    if classification == "machine_only":
        return {
            "strategy_label": "Ticket machine sample set",
            "strategy_note": "Selected because this lead only has ticket-machine ordering evidence, so the outreach stays focused on ordering guidance.",
            "menu_label": "English Menu Sample",
        }

    plans = {
        "ramen_only": {
            "strategy_label": "Ramen-only sample set",
            "strategy_note": "Selected a one-page ramen sample because this lead looks like a focused ramen menu without meaningful drinks evidence.",
            "menu_label": "Ramen Menu Sample (One Page)",
        },
        "ramen_with_sides_add_ons": {
            "strategy_label": "Ramen + sides sample set",
            "strategy_note": "Selected a ramen-plus-sides sample because this lead shows add-ons or small plates that should stay visible in the proof-of-value.",
            "menu_label": "Ramen + Sides Sample",
        },
        "ramen_with_drinks": {
            "strategy_label": "Ramen + drinks sample set",
            "strategy_note": "Selected a ramen sample with drinks because this lead appears to use both food and drinks guidance.",
            "menu_label": "Ramen + Drinks Sample",
        },
        "ramen_ticket_machine": {
            "strategy_label": "Ramen + ticket machine sample set",
            "strategy_note": "Selected menu plus ticket-machine proof because this lead has evidence that guests need both menu and ordering guidance.",
            "menu_label": "Ramen + Drinks Sample",
        },
        "izakaya_food_and_drinks": {
            "strategy_label": "Izakaya food + drinks sample set",
            "strategy_note": "Selected a split food-and-drinks sample because this lead looks like an izakaya where both sections matter in the customer experience.",
            "menu_label": "Izakaya Food + Drinks Sample",
        },
        "izakaya_drink_heavy": {
            "strategy_label": "Drink-forward izakaya sample set",
            "strategy_note": "Selected a drink-forward izakaya sample because this lead has evidence of drinks or nomihodai being a key proof point.",
            "menu_label": "Drink-Forward Izakaya Sample",
        },
        "izakaya_course_heavy": {
            "strategy_label": "Course + drinks sample set",
            "strategy_note": "Selected a course-and-drinks sample because this lead appears to rely on course or plan explanations.",
            "menu_label": "Course + Drinks Sample",
        },
    }
    return plans.get(
        establishment_profile,
        {
            "strategy_label": "General sample set",
            "strategy_note": "Selected the general menu sample because the establishment profile still needs manual review.",
            "menu_label": "English Menu Sample",
        },
    )


def _outreach_detail(classification: str, establishment_profile: str) -> dict[str, str]:
    if classification == "machine_only":
        return {
            "japanese_focus": "海外からのお客様が券売機や注文方法で迷わずご注文いただけるよう、英語の注文ガイド制作をお手伝いしております。",
            "english_focus": "I help restaurants make ticket machines and ordering steps easier for overseas customers to understand with an English ordering guide.",
            "japanese_photo_request": "現在お使いの券売機や注文案内のお写真をお送りください。",
            "english_photo_request": "If you are interested, please send photos of your current ticket machine or ordering guide.",
            "japanese_sample_note": "サンプルは券売機や注文案内の見せ方を確認いただくためのものです。",
            "english_sample_note": "The sample is intended to show how an English ordering guide can match your current ticket-machine or ordering flow.",
        }
    if establishment_profile == "ramen_ticket_machine" or classification == "menu_and_machine":
        return {
            "japanese_focus": "海外からのお客様がメニューと券売機の両方を分かりやすく見られるよう、英語メニューと注文ガイド制作をお手伝いしております。",
            "english_focus": "I help restaurants make both menus and ticket-machine ordering easier for overseas customers to follow with English menus and ordering guides.",
            "japanese_photo_request": "現在お使いのメニューや券売機のお写真をお送りください。",
            "english_photo_request": "If you are interested, please send photos of your current menu and ticket machine.",
            "japanese_sample_note": "サンプルでは、ラーメンメニューと券売機ガイドを同じ見た目の方向性で揃えられることをご確認いただけます。",
            "english_sample_note": "The sample is intended to show how the menu and ticket-machine guide can stay visually consistent for your shop.",
        }
    if establishment_profile == "ramen_only":
        return {
            "japanese_focus": "海外からのお客様が看板のラーメンを迷わず選べるよう、現在の構成に合わせた英語ラーメンメニュー制作をお手伝いしております。",
            "english_focus": "I help ramen shops make their core ramen choices easy for overseas customers to understand with an English menu that keeps the current structure.",
            "japanese_photo_request": "現在お使いのラーメンメニューのお写真をお送りください。",
            "english_photo_request": "If you are interested, please send photos of your current ramen menu.",
            "japanese_sample_note": "サンプルは、ラーメン中心の一枚ものでも見やすく整えられることをご確認いただくためのものです。",
            "english_sample_note": "The sample is intended to show how a focused one-page ramen menu can stay clean and easy to scan in English.",
        }
    if establishment_profile == "ramen_with_sides_add_ons":
        return {
            "japanese_focus": "ラーメンに加えてサイドや追加メニューも伝わりやすくなるよう、英語メニュー制作をお手伝いしております。",
            "english_focus": "I help ramen shops present both their ramen and supporting side dishes or add-ons clearly in English.",
            "japanese_photo_request": "現在お使いのラーメン、サイド、追加メニューのお写真をお送りください。",
            "english_photo_request": "If you are interested, please send photos of your current ramen, sides, and add-on items.",
            "japanese_sample_note": "サンプルは、ラーメンを主役にしながらサイドや追加項目も自然に見せる構成をご確認いただくためのものです。",
            "english_sample_note": "The sample is intended to show how ramen can stay the hero while side dishes and add-ons remain easy to understand.",
        }
    if establishment_profile == "ramen_with_drinks":
        return {
            "japanese_focus": "ラーメンとドリンクの両方が海外からのお客様に分かりやすく伝わるよう、英語メニュー制作をお手伝いしております。",
            "english_focus": "I help ramen shops explain both food and drink choices more clearly to overseas customers with an English menu.",
            "japanese_photo_request": "現在お使いのラーメンメニューとドリンクメニューのお写真をお送りください。",
            "english_photo_request": "If you are interested, please send photos of your current ramen menu and drink menu.",
            "japanese_sample_note": "サンプルは、ラーメンとドリンクを同じ見た目のまま整理して見せられることをご確認いただくためのものです。",
            "english_sample_note": "The sample is intended to show how food and drinks can be organized clearly in English without changing the feel of your current menu.",
        }
    if establishment_profile == "izakaya_drink_heavy":
        return {
            "japanese_focus": "ドリンクメニューや飲み放題のご案内が海外からのお客様にも伝わりやすくなるよう、英語メニュー制作をお手伝いしております。",
            "english_focus": "I help izakayas make drink menus and all-you-can-drink guidance easier for overseas customers to follow with English menu support.",
            "japanese_photo_request": "現在お使いのお料理、ドリンク、飲み放題案内のお写真をお送りください。",
            "english_photo_request": "If you are interested, please send photos of your current food menu, drink menu, and any nomihodai guidance.",
            "japanese_sample_note": "サンプルは、お料理とドリンクを分けて見せながらドリンク訴求も強められる構成をご確認いただくためのものです。",
            "english_sample_note": "The sample is intended to show how food and drinks can stay separate while giving drink-focused guidance more room.",
        }
    if establishment_profile == "izakaya_course_heavy":
        return {
            "japanese_focus": "コース内容や飲み放題プランが海外からのお客様にも伝わりやすくなるよう、英語メニュー制作をお手伝いしております。",
            "english_focus": "I help izakayas explain course menus and drink plans more clearly to overseas customers with English menu support.",
            "japanese_photo_request": "現在お使いのお料理、コース、ドリンクプランのお写真をお送りください。",
            "english_photo_request": "If you are interested, please send photos of your current food menu, course information, and drink plans.",
            "japanese_sample_note": "サンプルは、料理だけでなくコースやプラン説明も整理して見せられることをご確認いただくためのものです。",
            "english_sample_note": "The sample is intended to show how course explanations and drink plans can stay structured and readable in English.",
        }
    if establishment_profile == "izakaya_food_and_drinks":
        return {
            "japanese_focus": "お料理とドリンクの両方が海外からのお客様に分かりやすく伝わるよう、英語メニュー制作をお手伝いしております。",
            "english_focus": "I help izakayas make both food and drink menus easier for overseas customers to understand with English menu support.",
            "japanese_photo_request": "現在お使いのお料理メニューとドリンクメニューのお写真をお送りください。",
            "english_photo_request": "If you are interested, please send photos of your current food menu and drink menu.",
            "japanese_sample_note": "サンプルは、お料理とドリンクを分けて見せる英語メニューの雰囲気をご確認いただくためのものです。",
            "english_sample_note": "The sample is intended to show a split food-and-drinks layout that still feels close to your current menu setup.",
        }
    return {
        "japanese_focus": "海外からのお客様へのご案内が少しでもスムーズになるよう、英語メニュー制作をお手伝いしております。",
        "english_focus": "I help restaurants make guidance for overseas customers smoother with English menus.",
        "japanese_photo_request": "現在お使いのメニューのお写真をお送りください。",
        "english_photo_request": "If you are interested, please send photos of your current menu.",
        "japanese_sample_note": "サンプルは、現在のメニュー構成に合わせて英語版を整えたときの見え方をご確認いただくためのものです。",
        "english_sample_note": "The sample is intended to show how your current menu structure can be adapted into a clear English version.",
    }


def _join_paragraphs(paragraphs: list[str]) -> str:
    return "\n\n".join(paragraph.strip() for paragraph in paragraphs if paragraph and paragraph.strip())
