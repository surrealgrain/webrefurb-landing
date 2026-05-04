"""Tests for Mode A: Cold outreach pipeline."""

from __future__ import annotations

import pytest

from pipeline.models import QualificationResult
from pipeline.outreach import (
    build_manual_outreach_message,
    classify_business,
    select_outreach_assets,
    build_outreach_email,
    build_contact_form_pitch,
)
from pipeline.email_templates import (
    SUBJECT_MENU,
    SUBJECT_MACHINE,
    SUBJECT_NOMIHODAI,
    CONTACT_FORM_BODY,
    OPT_OUT_JA,
    OPT_OUT_EN,
    SIGNATURE_FULL,
    SENDER_NAME,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_qual(*, menu: bool = True, machine: bool = False) -> QualificationResult:
    return QualificationResult(
        lead=True,
        rejection_reason=None,
        business_name="Test Ramen",
        menu_evidence_found=menu,
        machine_evidence_found=machine,
    )


# ---------------------------------------------------------------------------
# classify_business
# ---------------------------------------------------------------------------

class TestClassifyBusiness:
    def test_menu_only(self):
        q = _make_qual(menu=True, machine=False)
        assert classify_business(q) == "menu_machine_unconfirmed"

    def test_menu_and_machine(self):
        q = _make_qual(menu=True, machine=True)
        assert classify_business(q) == "menu_and_machine"

    def test_machine_only(self):
        q = _make_qual(menu=False, machine=True)
        assert classify_business(q) == "machine_only"

    def test_no_evidence_defaults_to_menu_only(self):
        q = _make_qual(menu=False, machine=False)
        assert classify_business(q) == "menu_only"


# ---------------------------------------------------------------------------
# select_outreach_assets
# ---------------------------------------------------------------------------

class TestSelectOutreachAssets:
    """First-contact emails no longer attach PDFs — always returns empty."""

    def test_menu_only_returns_empty(self):
        assert select_outreach_assets("menu_only") == []

    def test_menu_and_machine_returns_empty(self):
        assert select_outreach_assets("menu_and_machine") == []

    def test_machine_only_returns_empty(self):
        assert select_outreach_assets("machine_only") == []

    def test_contact_form_returns_empty(self):
        assert select_outreach_assets("menu_only", contact_type="contact_form") == []

    def test_with_profile_returns_empty(self):
        assert select_outreach_assets("menu_only", establishment_profile="ramen_only") == []


# ---------------------------------------------------------------------------
# build_outreach_email
# ---------------------------------------------------------------------------

class TestBuildOutreachEmail:
    # -- Subject lines -----------------------------------------------------

    def test_ramen_menu_subject(self):
        email = build_outreach_email(
            business_name="テストらーめん",
            classification="menu_only",
            establishment_profile="ramen_only",
        )
        assert email["subject"] == SUBJECT_MENU

    def test_menu_and_machine_subject(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_and_machine",
        )
        assert email["subject"] == SUBJECT_MACHINE

    def test_machine_only_subject(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="machine_only",
        )
        assert email["subject"] == SUBJECT_MACHINE

    def test_izakaya_nomihodai_subject(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
            establishment_profile="izakaya_drink_heavy",
        )
        assert email["subject"] == SUBJECT_NOMIHODAI

    # -- Shared structure --------------------------------------------------

    def test_business_name_substituted(self):
        email = build_outreach_email(
            business_name="ラーメン二郎",
            classification="menu_only",
        )
        assert "ラーメン二郎" in email["body"]
        assert "ラーメン二郎 ご担当者様" in email["body"]

    def test_body_starts_with_hajimete_gorenraku(self):
        """All situations use 「初めてご連絡いたします」 (not 突然のご連絡)."""
        for classification in ("menu_only", "menu_and_machine", "machine_only"):
            for profile in ("ramen_only", "izakaya_food_and_drinks", "unknown"):
                email = build_outreach_email(
                    business_name="テスト",
                    classification=classification,
                    establishment_profile=profile,
                )
                assert "初めてご連絡いたします。" in email["body"], (
                    f"Missing standard greeting for classification='{classification}' profile='{profile}'"
                )
                assert "突然のご連絡" not in email["body"]

    def test_body_contains_sender_name(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
        )
        assert "Chris（クリス）" in email["body"]

    def test_body_contains_opt_out(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
        )
        assert OPT_OUT_JA in email["body"]
        assert "不要" in email["body"]

    def test_english_body_contains_opt_out(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
        )
        assert "I will not contact you again" in email["english_body"]

    def test_body_contains_full_signature(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
        )
        assert SIGNATURE_FULL in email["body"]

    def test_body_never_mentions_ai(self):
        import re
        forbidden = (
            r"\bai\b", "artificial intelligence", "automation", "automated",
            "software", "machine learning", "llm", "gpt",
        )
        for classification in ("menu_only", "menu_and_machine", "machine_only"):
            for profile in ("ramen_only", "izakaya_food_and_drinks", "unknown"):
                email = build_outreach_email(
                    business_name="テスト",
                    classification=classification,
                    establishment_profile=profile,
                )
                body_lower = email["body"].lower()
                for token in forbidden:
                    if token.startswith(r"\b"):
                        assert not re.search(token, body_lower), f"Found '{token}' in body for classification='{classification}' profile='{profile}'"
                    else:
                        assert token not in body_lower, f"Found '{token}' in body for classification='{classification}' profile='{profile}'"

    def test_cold_outreach_does_not_lead_with_all_prices(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
            establishment_profile="ramen_only",
        )
        combined = email["body"] + "\n" + email["english_body"]

        assert "¥30,000" not in combined
        assert "¥45,000" not in combined
        assert "¥65,000" not in combined
        assert "English Ordering Files" not in combined
        assert "Counter-Ready Ordering Kit" not in combined
        assert "Live QR English Menu" not in combined

    def test_cold_outreach_does_not_mention_lamination_or_delivery(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
            establishment_profile="ramen_only",
        )
        combined = email["body"] + "\n" + email["english_body"]
        assert "ラミネート" not in combined
        assert "lamination" not in combined.lower()
        assert "配送" not in combined
        assert "delivery" not in combined.lower()

    def test_cold_outreach_does_not_attach_pdfs(self):
        """First-contact emails should not reference PDF attachments."""
        for classification in ("menu_only", "menu_and_machine", "machine_only"):
            email = build_outreach_email(
                business_name="テスト",
                classification=classification,
            )
            assert "PDF" not in email["body"]
            assert "添付" not in email["body"]

    def test_cta_uses_simple_reply_kibou(self):
        """CTA should be one-word: reply 「希望」."""
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
            establishment_profile="ramen_only",
        )
        assert "「希望」" in email["body"]
        assert "「希望」とだけご返信" in email["body"]

    def test_cold_outreach_includes_shop_specific_safe_observation(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
            establishment_profile="ramen_only",
            lead_dossier={
                "proof_items": [
                    {
                        "customer_preview_eligible": True,
                        "snippet": "醤油ラーメン 味玉 トッピング メニュー",
                    }
                ]
            },
        )

        assert "醤油ラーメン 味玉 トッピング メニュー" in email["body"]
        assert "public menu or ordering details" in email["english_body"]

    # -- Situation-specific copy -------------------------------------------

    def test_ramen_menu_has_ramen_specific_focus(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
            establishment_profile="ramen_only",
        )
        assert "ラーメン店向け" in email["body"]
        assert "ラーメンの種類・トッピング・セット内容" in email["body"]
        assert "英語表記がメニュー内容や注文方法に対応していると" in email["body"]
        assert email["include_menu_image"] is True
        assert email["include_machine_image"] is False

    def test_ramen_menu_and_machine_mentions_both(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_and_machine",
        )
        assert "ラーメンの種類、トッピング、セット内容、券売機ボタン" in email["body"]
        assert "券売機" in email["body"]
        assert "最新のメニューや券売機のお写真" in email["body"]
        assert email["include_menu_image"] is True
        assert email["include_machine_image"] is True

    def test_izakaya_menu_has_izakaya_specific_focus(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
            establishment_profile="izakaya_food_and_drinks",
        )
        assert "居酒屋向け" in email["body"]
        assert "料理・ドリンク・コース内容" in email["body"]
        assert "卓上で判断" in email["body"]
        assert "券売機" not in email["body"]
        assert email["include_menu_image"] is True
        assert email["include_machine_image"] is False

    def test_izakaya_nomihodai_has_nomihodai_specific_focus(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
            establishment_profile="izakaya_drink_heavy",
        )
        assert "飲み放題のルール、ラストオーダー" in email["body"]
        assert "飲み放題・コース内容" in email["body"]
        assert "個別のご質問を減らすことにもつながります" in email["body"]
        assert email["subject"] == SUBJECT_NOMIHODAI
        assert email["include_menu_image"] is True
        assert email["include_machine_image"] is False

    def test_izakaya_course_heavy_also_uses_nomihodai(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
            establishment_profile="izakaya_course_heavy",
        )
        assert email["subject"] == SUBJECT_NOMIHODAI
        assert "飲み放題" in email["body"]

    def test_machine_only_uses_machine_specific_copy(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="machine_only",
        )
        assert email["subject"] == SUBJECT_MACHINE
        assert "券売機" in email["body"]
        assert "注文ガイド" in email["body"]
        assert "最新の券売機写真やメニュー写真" in email["body"]
        assert email["include_menu_image"] is False
        assert email["include_machine_image"] is True

    def test_unknown_defaults_to_ramen(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
            establishment_profile="unknown",
        )
        assert email["subject"] == SUBJECT_MENU
        assert "ラーメン店向け" in email["body"]

    def test_ramen_menu_has_graceful_exit(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
            establishment_profile="ramen_only",
        )
        assert "すでに十分な英語メニューをご用意済みでしたら、ご放念ください。" in email["body"]

    def test_machine_only_has_no_graceful_exit(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="machine_only",
        )
        assert "ご放念ください" not in email["body"]

    def test_ramen_menu_and_machine_has_no_graceful_exit(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_and_machine",
        )
        assert "ご放念ください" not in email["body"]

    # -- Contact form pitch ------------------------------------------------

    def test_contact_form_pitch_uses_locked_body(self):
        pitch = build_contact_form_pitch()
        assert pitch["channel"] == "form"
        assert pitch["body"] == CONTACT_FORM_BODY
        assert "Chris（クリス）" in pitch["body"]

    def test_contact_form_pitch_with_url_uses_custom_body(self):
        pitch = build_contact_form_pitch(sample_menu_url="https://example.com/sample")
        assert pitch["channel"] == "form"
        assert "https://example.com/sample" in pitch["body"]
        assert "ご確認いただけます" in pitch["body"]
        assert "突然のご連絡" not in pitch["body"]
        assert "添付ではなく" in pitch["body"]
        assert "chris@webrefurb.com" in pitch["body"]
        assert "希望" in pitch["body"]


class TestBuildManualOutreachMessage:
    @pytest.mark.parametrize(
        ("channel", "expected_label"),
        [
            ("contact_form", "Contact Form Message"),
        ],
    )
    def test_manual_channels_return_route_specific_copy(self, channel, expected_label):
        draft = build_manual_outreach_message(
            business_name="テスト",
            classification="menu_only",
            channel=channel,
        )
        assert draft["subject"] == ""
        assert draft["channel"] == channel
        assert draft["channel_label"] == expected_label

    @pytest.mark.parametrize("channel", ["line", "instagram", "phone", "walk_in"])
    def test_unsupported_manual_channels_raise(self, channel):
        with pytest.raises(ValueError, match="Unsupported manual outreach channel"):
            build_manual_outreach_message(
                business_name="テスト",
                classification="menu_only",
                channel=channel,
            )

    def test_manual_contact_form_uses_locked_body(self):
        draft = build_manual_outreach_message(
            business_name="テスト",
            classification="menu_only",
            channel="contact_form",
        )
        assert draft["body"] == CONTACT_FORM_BODY
        assert draft["include_menu_image"] is False
        assert draft["include_machine_image"] is False

    def test_manual_contact_form_uses_locked_body_for_izakaya(self):
        draft = build_manual_outreach_message(
            business_name="テスト",
            classification="menu_only",
            channel="contact_form",
            establishment_profile="izakaya_drink_heavy",
        )
        assert draft["body"] == CONTACT_FORM_BODY


# ---------------------------------------------------------------------------
# Email HTML locale-aware links
# ---------------------------------------------------------------------------

class TestEmailLocaleLinks:
    """Verify footer/header links route to the correct locale."""

    def test_default_locale_links_to_root(self):
        from pipeline.email_html import build_pitch_email_html

        html = build_pitch_email_html(
            text_body="テスト本文",
            include_menu_image=False,
            include_machine_image=False,
        )
        assert 'href="https://webrefurb.com"' in html
        assert "webrefurb.com/ja" not in html

    def test_ja_locale_links_to_ja(self):
        from pipeline.email_html import build_pitch_email_html

        html = build_pitch_email_html(
            text_body="テスト本文",
            include_menu_image=False,
            include_machine_image=False,
            locale="ja",
        )
        assert 'href="https://webrefurb.com/ja"' in html
        # Visible text still shows plain domain
        assert ">webrefurb.com</a>" in html

    def test_ja_locale_header_logo_links_to_ja(self):
        from pipeline.email_html import build_pitch_email_html

        html = build_pitch_email_html(
            text_body="テスト本文",
            include_menu_image=False,
            include_machine_image=False,
            locale="ja",
        )
        # Header logo link
        assert html.count('href="https://webrefurb.com/ja"') >= 2  # header + footer

    def test_ja_locale_does_not_show_ja_in_visible_text(self):
        from pipeline.email_html import build_pitch_email_html

        html = build_pitch_email_html(
            text_body="テスト本文",
            include_menu_image=False,
            include_machine_image=False,
            locale="ja",
        )
        # The visible "webrefurb.com" text link should not contain /ja
        assert ">webrefurb.com</a>" in html
        assert ">webrefurb.com/ja</a>" not in html
