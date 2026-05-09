from __future__ import annotations

from pipeline.constants import GENERIC_DEMO_URL
from pipeline.email_templates import CONTACT_FORM_BODY
from pipeline.outreach import build_contact_form_pitch, build_manual_outreach_message, build_outreach_email


BANNED_OUTBOUND_TERMS = (
    "automation",
    "scraping",
    "crawler",
    "classifier",
    "internal tool",
    "QR ordering system",
    "ordering system",
    "online ordering",
    "checkout",
    "place order",
    "submit order",
)


def _combined(email: dict[str, str]) -> str:
    return "\n".join(str(email.get(key) or "") for key in ("subject", "body", "english_body"))


def test_first_contact_is_qr_first_and_reply_only():
    email = build_outreach_email(
        business_name="青空ラーメン",
        classification="menu_only",
        establishment_profile="ramen",
    )
    combined = _combined(email)

    assert "英語QRメニュー" in email["body"]
    assert "日本語メニュー" in email["body"]
    assert "QRコード" in email["body"]
    assert "注文リスト" in email["body"]
    assert "日本語の商品名・数量・選択肢" in email["body"]
    assert GENERIC_DEMO_URL in combined
    assert "ご連絡" in email["body"]
    assert "files" not in email["english_body"].lower()
    assert email["include_menu_image"] is False
    assert email["include_machine_image"] is False


def test_first_contact_does_not_ask_for_photos_or_claim_custom_demo():
    email = build_outreach_email(
        business_name="港居酒屋",
        classification="menu_only",
        establishment_profile="izakaya",
    )
    combined = _combined(email)

    assert "send menu photos" not in combined.lower()
    assert "please send photos" not in combined.lower()
    assert "menu photos" not in combined.lower()
    assert "based on your menu" not in combined.lower()
    assert "sample from public menu" not in combined.lower()
    assert "made from your menu" not in combined.lower()
    assert "貴店のメニューをもとに" not in combined
    assert "公開されているメニュー情報" not in combined
    assert "¥65,000" not in combined
    assert "65,000円" not in combined


def test_first_contact_avoids_banned_old_terms():
    email = build_outreach_email(
        business_name="港居酒屋",
        classification="menu_and_machine",
        establishment_profile="izakaya_course_heavy",
    )
    combined = _combined(email)
    lowered = combined.lower()

    assert not __import__("re").search(r"\bai\b", lowered)
    for term in BANNED_OUTBOUND_TERMS:
        assert term.lower() not in lowered
    assert "package_1_remote_30k" not in combined
    assert "package_2_printed_delivered_45k" not in combined
    assert "package_3_qr_menu_65k" not in combined


def test_contact_form_copy_is_short_qr_first_and_demo_based():
    assert "英語QRメニュー" in CONTACT_FORM_BODY
    assert GENERIC_DEMO_URL in CONTACT_FORM_BODY
    assert "返信" not in CONTACT_FORM_BODY
    assert "添付" not in CONTACT_FORM_BODY


def test_manual_contact_form_copy_matches_qr_product_scope():
    message = build_manual_outreach_message(
        business_name="港居酒屋",
        classification="menu_only",
        establishment_profile="izakaya",
        channel="contact_form",
    )

    assert message["channel"] == "contact_form"
    assert "英語QRメニュー" in message["body"]
    assert "注文リスト" in message["body"]
    assert GENERIC_DEMO_URL in message["body"]


def test_contact_form_pitch_uses_generic_demo_without_attachments():
    pitch = build_contact_form_pitch(
        sample_menu_url=GENERIC_DEMO_URL,
    )

    assert "英語QRメニュー" in pitch["body"]
    assert GENERIC_DEMO_URL in pitch["body"]
    assert pitch["channel"] == "contact_form"
