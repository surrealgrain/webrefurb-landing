"""Mode A: QR-first cold outreach pipeline.

The active first contact is one product only: English QR Menu + Show Staff
List. It uses a generic demo link and asks for a reply only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .email_templates import (
    SUBJECT_FALLBACK,
    CONTACT_FORM_BODY,
    OPT_OUT_JA,
    OPT_OUT_EN,
    SIGNATURE_FULL,
    SENDER_NAME,
    build_subject,
)
from .constants import (
    GENERIC_DEMO_URL,
)
from .models import QualificationResult

SUPPORTED_MANUAL_CHANNELS = {"contact_form"}

MANUAL_CHANNEL_LABELS = {
    "contact_form": "Contact Form Message",
}


# ---------------------------------------------------------------------------
# Situation determination
# ---------------------------------------------------------------------------

def _determine_situation(
    classification: str,
    establishment_profile: str,
    lead_dossier: dict[str, Any] | None = None,
) -> str:
    if establishment_profile.startswith("izakaya"):
        return "izakaya"
    return "ramen"


# ---------------------------------------------------------------------------
# Situation templates (Japanese + English)
# ---------------------------------------------------------------------------

_SITUATIONS = {
    "ramen": {
        "genre_intro_ja": "ラーメン店向けに、英語QRメニューを制作しております、WebRefurbのChris（クリス）と申します。",
        "genre_intro_en": "My name is Chris from WebRefurb. I create English QR Menus for ramen restaurants.",
    },
    "izakaya": {
        "genre_intro_ja": "居酒屋向けに、英語QRメニューを制作しております、WebRefurbのChris（クリス）と申します。",
        "genre_intro_en": "My name is Chris from WebRefurb. I create English QR Menus for izakaya restaurants.",
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
    """Build a QR-first cold outreach email.

    Returns {"subject": str, "body": str, "english_body": str,
    "include_menu_image": bool, "include_machine_image": bool}.
    Never calls any LLM or translation layer.
    """
    situation = _determine_situation(classification, establishment_profile, lead_dossier=lead_dossier)
    tmpl = _SITUATIONS[situation]

    subject = build_subject(business_name=business_name)
    demo_url = GENERIC_DEMO_URL

    # -- Japanese body -------------------------------------------------------
    body = _join_paragraphs([
        f"{business_name} ご担当者様",
        "初めてご連絡いたします。",
        tmpl["genre_intro_ja"],
        "日本語メニューはそのまま使い、お客様がテーブルやカウンターでQRコードを読み取って、スマートフォンで英語メニューを確認できる形です。",
        "お客様は気になる料理をリストに追加し、最後に日本語の商品名・数量・選択肢が並んだ「Show Staff List」をスタッフの方に見せることができます。",
        f"汎用デモはこちらです：\n{demo_url}",
        "もし貴店でも役立ちそうでしたら、このメールにご返信ください。",
        "すでに十分な英語QRメニューをご用意済みでしたら、ご放念ください。",
        OPT_OUT_JA,
        "どうぞよろしくお願いいたします。",
        SIGNATURE_FULL,
    ])

    # -- English body --------------------------------------------------------
    english_body = _join_paragraphs([
        f"Dear {business_name} team,",
        "I hope you do not mind my reaching out.",
        tmpl["genre_intro_en"],
        "Your existing Japanese menu can stay as-is. Customers scan a QR code at the table or counter and read the English menu on their phone.",
        "They can tap Add to list, review what they selected, then show a Japanese item list to staff. It only prepares a list for the customer to show staff.",
        f"Generic demo: {demo_url}",
        "If this would be useful, please reply to this email.",
        "If you already have a good English QR menu, please disregard this message.",
        OPT_OUT_EN,
        "Thank you for your consideration.",
        SENDER_NAME,
    ])

    return {
        "subject": subject,
        "body": body,
        "english_body": english_body,
        "include_menu_image": False,
        "include_machine_image": False,
    }


# ---------------------------------------------------------------------------
# Evidence-gated email builder
# ---------------------------------------------------------------------------

def build_evidence_gated_email(
    classification: dict[str, Any],
) -> dict[str, str | bool] | None:
    """Build the QR-first email after evidence gates allow outreach."""
    template = classification["selected_template"]
    if template == "skip":
        return None
    business_name = classification["business_name"] or "テスト"
    restaurant_type = classification["restaurant_type"]

    subject = build_subject(
        business_name=business_name,
        business_name_confidence=classification.get("business_name_confidence", 0.0),
        template=template,
    )
    draft = build_outreach_email(
        business_name=business_name,
        classification="menu_only",
        establishment_profile=restaurant_type,
    )
    return {
        "subject": subject,
        "body": str(draft["body"]),
        "english_body": str(draft["english_body"]),
        "include_menu_image": False,
        "include_machine_image": False,
        "classification": classification,
    }


def _english_restaurant_type_label(restaurant_type: str) -> str:
    if restaurant_type == "ramen":
        return "ramen shops"
    if restaurant_type == "izakaya":
        return "izakaya"
    return "Japanese restaurants"


def build_contact_form_pitch(*, sample_menu_url: str = "", sender_name: str = "Chris（クリス）") -> dict[str, str]:
    """Return the locked contact-form pitch body.

    Contact forms cannot receive attachments, so this is intentionally separate
    from the normal e-mail outreach package.
    """
    return {
        "body": _contact_form_body(sample_menu_url=sample_menu_url, sender_name=sender_name),
        "channel": "contact_form",
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
            "I create English QR Menus for Japanese restaurants. The existing Japanese menu can stay as-is.",
            "Customers scan, read the English menu, add items to a simple list, and show Japanese item names to staff.",
            f"Generic demo: {sample_menu_url or GENERIC_DEMO_URL}",
            "If this would be useful, please contact me through this form.",
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
    demo_url = sample_menu_url or GENERIC_DEMO_URL
    return _join_paragraphs([
        "お問い合わせフォームより失礼いたします。",
        f"WebRefurbの{sender_name}です。日本語メニューはそのまま使える英語QRメニューを制作しています。",
        "お客様はQRコードから英語メニューを読み、気になる料理をリストに追加して、「Show Staff List」で日本語の商品名のリストをスタッフの方に見せることができます。",
        f"汎用デモはこちらです：\n{demo_url}",
        "貴店でも役立ちそうでしたら、このフォームからお知らせください。",
        "どうぞよろしくお願いいたします。",
        sender_name,
    ])


def _menu_sample_for_profile(establishment_profile: str, classification: str) -> Path | None:
    return None


def _profile_asset_plan(situation: str) -> dict[str, str]:
    plans = {
        "ramen": {
            "strategy_label": "Generic English QR Menu demo",
            "strategy_note": "First contact links to the generic QR demo and does not attach sample menus.",
            "menu_label": "Generic Demo",
        },
        "izakaya": {
            "strategy_label": "Generic English QR Menu demo",
            "strategy_note": "First contact links to the generic QR demo and does not attach sample menus.",
            "menu_label": "Generic Demo",
        },
    }
    return plans[situation]


def _join_paragraphs(paragraphs: list[str]) -> str:
    return "\n\n".join(p.strip() for p in paragraphs if p and p.strip())
