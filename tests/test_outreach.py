"""Tests for Mode A: Cold outreach pipeline."""

from __future__ import annotations

import pytest

from pipeline.models import QualificationResult
from pipeline.outreach import (
    classify_business,
    select_outreach_assets,
    build_outreach_email,
    MachineOnlyNotSupportedError,
)
from pipeline.email_templates import SUBJECT, BODY, LINE_INPERSON, LINE_MACHINE
from pipeline.constants import GENERIC_MENU_PDF, GENERIC_MACHINE_PDF


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

    def test_machine_only_returns_empty(self):
        assets = select_outreach_assets("machine_only")
        assert assets == []


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

    def test_machine_only_raises(self):
        with pytest.raises(MachineOnlyNotSupportedError):
            build_outreach_email(
                business_name="テスト",
                classification="machine_only",
            )

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
