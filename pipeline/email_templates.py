"""Locked QR-first outreach copy for the current product reset."""

# ---------------------------------------------------------------------------
# Universal subject lines
# ---------------------------------------------------------------------------

SUBJECT_PERSONALIZED = "【WebRefurb】{name}様向け英語QRメニューのご案内"
SUBJECT_FALLBACK = "【WebRefurb】英語QRメニューのご案内"
SUBJECT_CONTACT_FORM = "英語QRメニューのご案内"

# Confidence threshold for personalized subject
SUBJECT_PERSONALIZED_MIN_CONFIDENCE = 0.90

# Maximum business-name length for personalized subject (avoids awkward wrapping)
SUBJECT_PERSONALIZED_MAX_NAME_LENGTH = 30

# Legacy aliases for backward compatibility
SUBJECT_MENU = SUBJECT_FALLBACK
SUBJECT = SUBJECT_FALLBACK

# ---------------------------------------------------------------------------
# Subject selection
# ---------------------------------------------------------------------------

# Legacy mapping — all templates now use the universal subject.
# Kept as a constant so existing code that references it still compiles.
SUBJECT_BY_TEMPLATE: dict[str, str] = {}


def build_subject(
    *,
    business_name: str = "",
    business_name_confidence: float = 0.0,
    template: str = "",
) -> str:
    """Return the universal outreach subject line.

    Uses the personalized form when the business name is available,
    high-confidence, reasonably short, and free of branch/location clutter.
    Otherwise falls back to the generic form.
    """
    # Contact-form templates keep their own subject
    if template.startswith("contact_form_"):
        return SUBJECT_CONTACT_FORM

    if _can_personalize(business_name, business_name_confidence):
        return SUBJECT_PERSONALIZED.format(name=business_name)

    return SUBJECT_FALLBACK


def _can_personalize(name: str, confidence: float) -> bool:
    """Check whether a business name is suitable for the personalized subject."""
    if not name or name == "テスト":
        return False
    if confidence < SUBJECT_PERSONALIZED_MIN_CONFIDENCE:
        return False
    if len(name) > SUBJECT_PERSONALIZED_MAX_NAME_LENGTH:
        return False
    # Reject names with messy branch/location parentheticals
    # e.g. "ラーメン店 新宿店（本店）" or "居酒屋 ○○ ＜青山店＞"
    if any(ch in name for ch in ("（", "＜", "《", "【", "〔")):
        return False
    return True

# ---------------------------------------------------------------------------
# Signature block
# ---------------------------------------------------------------------------

SENDER_NAME = "Chris（クリス）"

SIGNATURE = SENDER_NAME

SIGNATURE_FULL = SIGNATURE

# ---------------------------------------------------------------------------
# Opt-out line
# ---------------------------------------------------------------------------

OPT_OUT_JA = "今後このようなご案内が不要でしたら、「不要」とご返信ください。以後ご連絡いたしません。"
OPT_OUT_EN = "If you do not wish to receive further messages, please reply with \"不要\" (unsubscribe). I will not contact you again."

# ---------------------------------------------------------------------------
# Contact-form pitch (no attachments, no images — short and direct)
# ---------------------------------------------------------------------------

CONTACT_FORM_BODY = """\
お問い合わせフォームより失礼いたします。

WebRefurbのChris（クリス）と申します。日本語メニューはそのまま使える英語QRメニューを制作しています。

お客様はQRコードから英語メニューを読み、気になる料理をリストに追加して、「Show Staff List」で日本語の商品名のリストをスタッフの方に見せることができます。

デモはこちらです：
https://webrefurb.com/demo/

もし貴店でも役立ちそうでしたら、このフォームからお知らせください。

どうぞよろしくお願いいたします。

Chris（クリス）"""
