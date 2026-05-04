"""Locked email templates for cold outreach.

Evidence-gated templates chosen by verified lead attributes, not
restaurant type alone.  See ``evidence_classifier.py`` for the
classification logic.

Design principles (Japanese B2B cold-email best practice):
  - Lead with their actual menu, not our service
  - 「初めてご連絡いたします」 not 「突然のご連絡失礼いたします」
  - No accusatory language about confusing menus
  - CTA is one word: reply 「希望」 (or photo request when needed)
  - No PDF attachments on first contact (inline preview image only)
  - Lamination/delivery details saved for after reply
  - Every claim backed by evidence; absence = "unknown", not "false"
"""

# ---------------------------------------------------------------------------
# Subject lines by scenario
# ---------------------------------------------------------------------------

SUBJECT_MENU = "【英語メニュー制作】貴店メニューの表記サンプルについて"
SUBJECT_MACHINE = "【券売機表示】英語注文ガイドのサンプルについて"
SUBJECT_NOMIHODAI = "【英語メニュー制作】飲み放題・コース表記のサンプル"
SUBJECT_NOMIHODAI_ONLY = "【英語メニュー制作】飲み放題表記のサンプル"
SUBJECT_COURSE_ONLY = "【英語メニュー制作】コース表記のサンプル"
SUBJECT_CONTACT_FORM = "英語メニュー制作サンプルのご相談"

# Legacy aliases for backward compatibility
SUBJECT = SUBJECT_MENU
MACHINE_ONLY_SUBJECT = SUBJECT_MACHINE

# ---------------------------------------------------------------------------
# Subject selection by template name
# ---------------------------------------------------------------------------

SUBJECT_BY_TEMPLATE: dict[str, str] = {
    "ramen_visible_menu": SUBJECT_MENU,
    "ramen_visible_menu_neutral_ordering": SUBJECT_MENU,
    "ramen_menu_plus_ticket_machine": SUBJECT_MACHINE,
    "ramen_ticket_machine_only": SUBJECT_MACHINE,
    "ramen_needs_menu_photo": SUBJECT_MENU,
    "ramen_needs_ticket_machine_photo": SUBJECT_MACHINE,
    "izakaya_standard": SUBJECT_MENU,
    "izakaya_food_drink_only": SUBJECT_MENU,
    "izakaya_course_only": SUBJECT_COURSE_ONLY,
    "izakaya_nomihodai_only": SUBJECT_NOMIHODAI_ONLY,
    "izakaya_nomihodai_course": SUBJECT_NOMIHODAI,
    "izakaya_needs_menu_photo": SUBJECT_MENU,
    "contact_form_public_menu": SUBJECT_CONTACT_FORM,
    "contact_form_needs_menu_photo": SUBJECT_CONTACT_FORM,
}

# ---------------------------------------------------------------------------
# Signature block
# ---------------------------------------------------------------------------

BUSINESS_NAME = "WebRefurb 英語メニュー制作"
SENDER_NAME = "Chris（クリス）"
SENDER_EMAIL = "chris@webrefurb.com"
SITE_URL = "https://webrefurb.com/ja"

SIGNATURE = SENDER_NAME

SIGNATURE_FULL = SIGNATURE

# ---------------------------------------------------------------------------
# Opt-out line
# ---------------------------------------------------------------------------

OPT_OUT_JA = "今後このようなご案内が不要でしたら、「不要」とご返信ください。以後ご連絡いたしません。"
OPT_OUT_EN = "If you do not wish to receive further messages, please reply with \"不要\" (unsubscribe). I will not contact you again."

# ---------------------------------------------------------------------------
# Dynamic phrase builders
# ---------------------------------------------------------------------------

# Menu-topic → Japanese label mapping
_TOPIC_LABELS: dict[str, str] = {
    "ramen_types": "ラーメンの種類",
    "toppings": "トッピング",
    "set_items": "セット内容",
    "food_items": "料理",
    "drink_items": "ドリンク",
    "course_items": "コース内容",
    "nomihodai": "飲み放題",
    "last_order": "ラストオーダー",
    "extra_charges": "追加料金",
    "ticket_machine_buttons": "券売機ボタン",
    "purchase_steps": "購入手順",
    "ordering_rules": "注文ルール",
}

# Topic groups for evidence-line phrasing
_RAMEN_EVIDENCE_TOPICS = ["ramen_types", "toppings", "set_items"]
_IZAKAYA_EVIDENCE_TOPICS = ["food_items", "drink_items", "course_items", "nomihodai"]
_IZAKAYA_BENEFIT_TOPICS = ["nomihodai", "last_order", "extra_charges", "course_items"]


def build_menu_topic_phrase(observed_topics: list[str], restaurant_type: str) -> str:
    """Build the menu-topic phrase for the evidence line.

    E.g. "ラーメンの種類・トッピング・セット内容などについて"
    Only includes topics that were actually observed.
    """
    if restaurant_type == "ramen":
        order = _RAMEN_EVIDENCE_TOPICS
    elif restaurant_type == "izakaya":
        order = _IZAKAYA_EVIDENCE_TOPICS
    else:
        order = list(_TOPIC_LABELS.keys())

    parts = []
    for topic in order:
        if topic in observed_topics:
            parts.append(_TOPIC_LABELS[topic])

    if not parts:
        return "メニュー内容について"

    return "・".join(parts) + "などについて"


def build_evidence_line_ja(
    *,
    public_menu_found: bool,
    menu_topic_phrase: str,
    restaurant_type: str,
) -> str:
    """Build the Japanese evidence/introduction line."""
    if not public_menu_found:
        return ""

    return (
        f"公開されている貴店メニューを拝見し、{menu_topic_phrase}、"
        "海外のお客様にも内容が伝わりやすい英語表記をご提案できればと思い、"
        "ご連絡いたしました。"
    )


def build_benefit_line_ja(
    *,
    restaurant_type: str,
    observed_topics: list[str],
    allowed_claims: list[str],
    template: str,
) -> str:
    """Build the Japanese benefit line based on observed evidence."""

    # Ticket machine templates
    if "mention_ticket_machine" in allowed_claims:
        if template in ("ramen_menu_plus_ticket_machine",):
            return (
                "ラーメンの種類、トッピング、セット内容、券売機ボタンの表記が"
                "英語で対応していると、初めて来店される海外のお客様でも"
                "券売機前で迷いにくくなります。"
            )
        if template == "ramen_ticket_machine_only":
            return (
                "券売機のボタン内容や購入手順が英語で分かると、"
                "混雑時でもお客様が自分で注文しやすくなります。"
            )

    # Ramen benefit
    if restaurant_type == "ramen":
        return (
            "英語表記がメニュー内容や注文方法に対応していると、"
            "お客様が注文前に判断しやすくなり、"
            "スタッフの方へのご質問を減らすことにもつながります。"
        )

    # Izakaya benefit — dynamic based on topics
    if restaurant_type == "izakaya":
        benefit_parts = []
        if "food_items" in observed_topics or "drink_items" in observed_topics:
            benefit_parts.append("海外のお客様が卓上で判断しやすくなり")

        detail_parts = []
        if "nomihodai" in observed_topics and "mention_nomihodai" in allowed_claims:
            detail_parts.append("飲み放題のルール")
        if "last_order" in observed_topics:
            detail_parts.append("ラストオーダー")
        if "course_items" in observed_topics and "mention_course" in allowed_claims:
            detail_parts.append("コース内容")
        if "extra_charges" in observed_topics:
            detail_parts.append("追加料金")

        if detail_parts:
            detail_str = "、".join(detail_parts)
            return (
                f"{detail_str}などが英語で整理されていると、"
                "海外のお客様が卓上で判断しやすくなり、"
                "スタッフの方への個別のご質問を減らすことにもつながります。"
            )

        if benefit_parts:
            topic_labels = []
            if "food_items" in observed_topics:
                topic_labels.append("料理")
            if "drink_items" in observed_topics:
                topic_labels.append("ドリンク")
            if topic_labels:
                topic_str = "、".join(topic_labels)
            else:
                topic_str = "メニュー内容"
            return (
                f"{topic_str}が英語で整理されていると、"
                "海外のお客様が卓上で判断しやすくなり、"
                "スタッフの方へのご質問を減らすことにもつながります。"
            )

        return (
            "英語表記がメニュー内容に対応していると、"
            "海外のお客様が判断しやすくなり、"
            "スタッフの方へのご質問を減らすことにもつながります。"
        )

    return ""


def build_cta_ja(
    *,
    public_menu_usable: bool,
    ticket_machine_content_usable: bool,
    needs_photo: bool,
    has_ticket_machine: bool,
    template: str,
) -> str:
    """Build the Japanese CTA based on evidence availability."""

    if needs_photo and not public_menu_usable and not ticket_machine_content_usable:
        return (
            "ご希望でしたら、現在お使いのメニューのお写真を1枚"
            "お送りいただければ、1ページ分の確認用サンプルを"
            "無料でお作りします。\n"
            "このメールに「希望」とだけご返信いただければ結構です。"
        )

    if public_menu_usable and has_ticket_machine:
        return (
            "ご希望でしたら、公開されているメニュー情報をもとに、"
            "1ページ分の確認用サンプルを無料でお作りします。\n"
            "このメールに「希望」とだけご返信いただければ結構です。\n\n"
            "実際に制作する際は、最新のメニューや券売機のお写真を"
            "確認してから進めます。"
        )

    if ticket_machine_content_usable and not public_menu_usable:
        return (
            "ご希望でしたら、券売機横に置ける1ページ分の確認用サンプルを"
            "無料でお作りします。\n"
            "このメールに「希望」とだけご返信いただければ結構です。\n\n"
            "実際に制作する際は、最新の券売機写真やメニュー写真を"
            "確認してから進めます。"
        )

    if public_menu_usable:
        return (
            "ご希望でしたら、公開されているメニュー情報をもとに、"
            "1ページ分の確認用サンプルを無料でお作りします。\n"
            "このメールに「希望」とだけご返信いただければ結構です。"
        )

    return (
        "ご希望でしたら、現在お使いのメニューのお写真を1枚"
        "お送りいただければ、1ページ分の確認用サンプルを"
        "無料でお作りします。\n"
        "このメールに「希望」とだけご返信いただければ結構です。"
    )


def build_graceful_exit_ja(existing_english_menu_quality: str) -> str:
    """Build the graceful exit line."""
    if existing_english_menu_quality in ("partial", "unclear", "comprehensive"):
        return "すでに十分な英語メニューをご用意済みでしたら、ご放念ください。"
    return ""


# ---------------------------------------------------------------------------
# Contact-form pitch (no attachments, no images — short and direct)
# ---------------------------------------------------------------------------

CONTACT_FORM_BODY = """\
お問い合わせフォームより失礼いたします。

ラーメン店・居酒屋向けに英語メニュー制作を行っております、WebRefurbのChris（クリス）と申します。

公開されているメニュー情報を拝見し、海外のお客様にも内容が伝わりやすい英語メニュー表記のサンプル作成についてご案内したく、ご連絡しました。

必要でしたら、貴店メニューの一部をもとに、1ページ分の確認用サンプルを無料でお作りします。

ご興味がございましたら、下記メールアドレスまでご連絡いただけますと幸いです。

不要なご案内でしたら、ご放念ください。

どうぞよろしくお願いいたします。

Chris（クリス）"""
