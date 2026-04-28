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
from pipeline.email_templates import SUBJECT, BODY, LINE_INPERSON, LINE_MACHINE, CONTACT_FORM_BODY
from pipeline.constants import (
    GENERIC_MACHINE_PDF,
    GENERIC_MENU_PDF,
    OUTREACH_SAMPLE_IZAKAYA_FOOD_DRINKS_PDF,
    OUTREACH_SAMPLE_RAMEN_ONE_PAGE_PDF,
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
    def test_menu_only(self):
        assets = select_outreach_assets("menu_only")
        assert assets == [GENERIC_MENU_PDF]

    def test_menu_and_machine(self):
        assets = select_outreach_assets("menu_and_machine")
        assert assets == [GENERIC_MENU_PDF, GENERIC_MACHINE_PDF]

    def test_menu_machine_unconfirmed(self):
        assets = select_outreach_assets("menu_machine_unconfirmed")
        assert assets == [GENERIC_MENU_PDF]

    def test_machine_only_returns_machine_pdf(self):
        assets = select_outreach_assets("machine_only")
        assert assets == [GENERIC_MACHINE_PDF]

    def test_contact_form_returns_no_attachments(self):
        assets = select_outreach_assets("menu_only", contact_type="contact_form")
        assert assets == []

    def test_ramen_only_profile_uses_one_page_sample(self):
        assets = select_outreach_assets("menu_only", establishment_profile="ramen_only")
        assert assets == [OUTREACH_SAMPLE_RAMEN_ONE_PAGE_PDF]

    def test_izakaya_profile_uses_food_and_drinks_sample(self):
        assets = select_outreach_assets("menu_only", establishment_profile="izakaya_drink_heavy")
        assert assets == [OUTREACH_SAMPLE_IZAKAYA_FOOD_DRINKS_PDF]


# ---------------------------------------------------------------------------
# build_outreach_email
# ---------------------------------------------------------------------------

class TestBuildOutreachEmail:
    def test_subject(self):
        email = build_outreach_email(
            business_name="テストらーめん",
            classification="menu_only",
        )
        assert email["subject"] == "英語メニュー制作のご提案（テストらーめん様）"

    def test_subject_same_for_all_classifications(self):
        for classification in ("menu_only", "menu_and_machine", "menu_machine_unconfirmed"):
            email = build_outreach_email(
                business_name="テスト",
                classification=classification,
            )
            assert email["subject"] == "英語メニュー制作のご提案（テスト様）"

    def test_business_name_substituted(self):
        email = build_outreach_email(
            business_name="ラーメン二郎",
            classification="menu_only",
        )
        assert "ラーメン二郎" in email["body"]
        assert "ラーメン二郎 ご担当者様" in email["body"]

    def test_inperson_line_present_by_default(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
        )
        assert LINE_INPERSON in email["body"]

    def test_inperson_line_removed_when_disabled(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
            include_inperson_line=False,
        )
        assert LINE_INPERSON not in email["body"]

    def test_body_never_mentions_ai(self):
        for classification in ("menu_only", "menu_and_machine", "menu_machine_unconfirmed"):
            email = build_outreach_email(
                business_name="テスト",
                classification=classification,
            )
            body_lower = email["body"].lower()
            for token in ("ai", "artificial intelligence", "automation", "automated", "software", "machine learning", "llm", "gpt"):
                assert token not in body_lower, f"Found '{token}' in body for classification '{classification}'"

    def test_body_contains_locked_text(self):
        assert "突然のご連絡にて失礼いたします。" in BODY
        assert "Chris（クリス）と申します。" in BODY
        assert "デザインや仕上がりのイメージをご覧いただくためのものです。" in BODY

    def test_subject_contains_placeholder(self):
        assert "{店名}" in SUBJECT

    def test_template_contains_inperson_line(self):
        assert LINE_INPERSON in BODY

    def test_contact_form_pitch_uses_locked_body(self):
        pitch = build_contact_form_pitch()
        assert pitch["channel"] == "form"
        assert pitch["body"] == CONTACT_FORM_BODY
        assert "突然のご連絡にて失礼いたします。" in pitch["body"]
        assert "https://webrefurb.com/ja" in pitch["body"]
        assert "[chris@webrefurb.com](mailto:chris@webrefurb.com)" in pitch["body"]

    # -- Machine line and image tests -------------------------------------

    def test_menu_and_machine_includes_machine_line(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_and_machine",
        )
        assert LINE_MACHINE in email["body"]

    def test_menu_and_machine_includes_machine_image_flag(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_and_machine",
        )
        assert email["include_machine_image"] is True

    def test_menu_only_no_machine_line(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
        )
        assert LINE_MACHINE not in email["body"]
        assert email["include_machine_image"] is False

    def test_menu_machine_unconfirmed_no_machine_line(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_machine_unconfirmed",
        )
        assert LINE_MACHINE not in email["body"]
        assert email["include_machine_image"] is False

    def test_machine_only_uses_machine_specific_copy(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="machine_only",
        )
        assert email["subject"] == "英語注文ガイド制作のご提案（テスト様）"
        assert "券売機や注文方法" in email["body"]
        assert "メニューのお写真" not in email["body"]
        assert email["include_menu_image"] is False
        assert email["include_machine_image"] is True

    def test_ramen_only_profile_uses_ramen_specific_copy(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
            establishment_profile="ramen_only",
        )
        assert "看板のラーメン" in email["body"]
        assert "一枚もの" in email["body"]

    def test_izakaya_course_profile_uses_course_specific_copy(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_only",
            establishment_profile="izakaya_course_heavy",
        )
        assert "コース内容や飲み放題プラン" in email["body"]

    def test_menu_and_machine_attaches_both_pdfs(self):
        assets = select_outreach_assets("menu_and_machine")
        assert GENERIC_MENU_PDF in assets
        assert GENERIC_MACHINE_PDF in assets

    def test_machine_line_inserted_after_menu_paragraph(self):
        email = build_outreach_email(
            business_name="テスト",
            classification="menu_and_machine",
        )
        anchor = "実際に制作する際は、貴店のメニュー内容に合わせて作成いたします。"
        assert anchor in email["body"]
        # Machine line should appear right after the anchor
        idx_anchor = email["body"].index(anchor) + len(anchor)
        idx_machine = email["body"].index(LINE_MACHINE)
        assert idx_machine > idx_anchor
        # No blank paragraph between them
        between = email["body"][idx_anchor:idx_machine]
        assert between == "\n"


class TestBuildManualOutreachMessage:
    @pytest.mark.parametrize(
        ("channel", "expected_label", "expected_phrase"),
        [
            ("contact_form", "Contact Form Message", "https://webrefurb.com/ja"),
            ("line", "LINE Message", "そのままご返信ください"),
            ("instagram", "Instagram DM", "DMでご返信"),
            ("phone", "Phone Script", "メールかLINEでお送りいただけますでしょうか"),
            ("walk_in", "Walk-in Script", "お写真を見せていただけますでしょうか"),
        ],
    )
    def test_manual_channels_return_route_specific_copy(self, channel, expected_label, expected_phrase):
        draft = build_manual_outreach_message(
            business_name="テスト",
            classification="menu_only",
            channel=channel,
        )
        assert draft["subject"] == ""
        assert draft["channel"] == channel
        assert draft["channel_label"] == expected_label
        assert expected_phrase in draft["body"]

    def test_manual_machine_only_copy_mentions_ticket_machine(self):
        draft = build_manual_outreach_message(
            business_name="テスト",
            classification="machine_only",
            channel="line",
        )
        assert "券売機や注文方法" in draft["body"]
        assert draft["include_menu_image"] is False
        assert draft["include_machine_image"] is True

    def test_manual_contact_form_uses_locked_body(self):
        draft = build_manual_outreach_message(
            business_name="テスト",
            classification="menu_only",
            channel="contact_form",
        )
        assert draft["body"] == CONTACT_FORM_BODY
        assert draft["include_menu_image"] is False
        assert draft["include_machine_image"] is False

    def test_manual_izakaya_drink_profile_mentions_nomihodai(self):
        draft = build_manual_outreach_message(
            business_name="テスト",
            classification="menu_only",
            channel="instagram",
            establishment_profile="izakaya_drink_heavy",
        )
        assert "飲み放題" in draft["body"]


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
