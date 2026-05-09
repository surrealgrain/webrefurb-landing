"""Locked QR-first outreach copy for the current product reset."""

# ---------------------------------------------------------------------------
# Universal subject lines
# ---------------------------------------------------------------------------

SUBJECT = "英語QRメニューのご案内"

# Legacy aliases
SUBJECT_FALLBACK = SUBJECT
SUBJECT_PERSONALIZED = SUBJECT
SUBJECT_CONTACT_FORM = SUBJECT
SUBJECT_MENU = SUBJECT

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
    """Return the universal outreach subject line."""
    return SUBJECT

# ---------------------------------------------------------------------------
# Signature block
# ---------------------------------------------------------------------------

SENDER_NAME = "Chris（クリス）"

SIGNATURE = f"{SENDER_NAME}\nWebRefurb\nhttps://webrefurb.com/"

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

WebRefurbのChris（クリス）と申します。飲食店向けに英語QRメニューを制作しています。

こちらは、現在の日本語メニューやPOSを変更せずに使える仕組みです。

店内に置いたQRコードを外国人のお客様がスマートフォンで読み取り、英語で料理の説明や写真を確認できます。

気になる料理は「注文リスト」に追加でき、最後に日本語の商品名・数量・選択肢がまとまった画面をスタッフの方に見せられます。

そのため、お客様は注文しやすくなり、スタッフの方も英語で細かく説明する負担を減らせます。

デモページはこちらです：
https://webrefurb.com/demo/

デモは最初に日本語で表示されますが、画面上部の「EN / JP」切り替えで、外国人のお客様側の英語表示もご確認いただけます。

もし貴店でも役立ちそうでしたら、このフォームからお知らせください。

どうぞよろしくお願いいたします。

Chris（クリス）
WebRefurb
https://webrefurb.com/"""
