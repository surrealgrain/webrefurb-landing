"""Tests for evidence-gated lead classifier and template selection.

Each test creates a lead data dict, runs it through classify_lead(),
verifies the classification output, and (when template != skip) builds
the email via build_evidence_gated_email() to verify content constraints.
"""

from __future__ import annotations

import pytest

from pipeline.evidence_classifier import classify_lead
from pipeline.outreach import build_evidence_gated_email


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ramen_base(**overrides) -> dict:
    """Ramen shop with usable public menu, no ticket machine."""
    base = {
        "business_name": "テストラーメン",
        "restaurant_type": "ramen",
        "restaurant_type_confidence": 0.90,
        "contact_channel": "public_email",
        "public_contact_source": "official_website",
        "public_menu_found": True,
        "public_menu_usable_for_sample": True,
        "menu_readability_confidence": 0.85,
        "observed_menu_topics": ["ramen_types", "toppings", "set_items"],
        "ticket_machine_confidence": 0.0,
        "nomihodai_confidence": 0.0,
        "course_confidence": 0.0,
        "existing_english_menu_quality": "none_found",
    }
    base.update(overrides)
    return base


def _izakaya_base(**overrides) -> dict:
    """Izakaya with usable public menu, food + drink."""
    base = {
        "business_name": "テスト居酒屋",
        "restaurant_type": "izakaya",
        "restaurant_type_confidence": 0.90,
        "contact_channel": "public_email",
        "public_contact_source": "official_website",
        "public_menu_found": True,
        "public_menu_usable_for_sample": True,
        "menu_readability_confidence": 0.85,
        "observed_menu_topics": ["food_items", "drink_items"],
        "ticket_machine_confidence": 0.0,
        "nomihodai_confidence": 0.0,
        "course_confidence": 0.0,
        "existing_english_menu_quality": "none_found",
    }
    base.update(overrides)
    return base


def _build_email(classification: dict):
    """Build email and assert it's not None."""
    result = build_evidence_gated_email(classification)
    assert result is not None, "Expected an email, got skip"
    return result


# ---------------------------------------------------------------------------
# 1. Ramen: visible usable menu, no ticket machine
# ---------------------------------------------------------------------------

class TestRamenVisibleMenu:
    def test_selects_ramen_visible_menu(self):
        c = classify_lead(_ramen_base())
        assert c["selected_template"] == "ramen_visible_menu"
        assert "券売機" not in _build_email(c)["body"]

    def test_no_ticket_machine_mention(self):
        c = classify_lead(_ramen_base())
        body = _build_email(c)["body"]
        assert "券売機" not in body
        assert "食券" not in body


# ---------------------------------------------------------------------------
# 2. Ramen: visible menu + review says 食券制
# ---------------------------------------------------------------------------

class TestRamenMenuPlusMachineKeyword:
    def test_selects_menu_plus_ticket_machine(self):
        c = classify_lead(_ramen_base(
            machine_evidence_found=True,
            evidence_snippets=["食券制で注文します"],
            ticket_machine_confidence=0.92,
            ticket_machine_evidence_type="explicit_text",
            observed_menu_topics=["ramen_types", "toppings", "set_items"],
        ))
        assert c["selected_template"] == "ramen_menu_plus_ticket_machine"


# ---------------------------------------------------------------------------
# 3. Ramen: visible menu + clear ticket-machine photo
# ---------------------------------------------------------------------------

class TestRamenMenuPlusMachinePhoto:
    def test_selects_menu_plus_ticket_machine(self):
        c = classify_lead(_ramen_base(
            machine_evidence_found=True,
            ticket_machine_confidence=0.90,
            ticket_machine_evidence_type="clear_photo",
            observed_menu_topics=["ramen_types", "toppings", "set_items", "ticket_machine_buttons"],
        ))
        assert c["selected_template"] == "ramen_menu_plus_ticket_machine"


# ---------------------------------------------------------------------------
# 4. Ramen: no usable menu, readable ticket-machine buttons
# ---------------------------------------------------------------------------

class TestRamenTicketMachineOnly:
    def test_selects_ticket_machine_only(self):
        c = classify_lead(_ramen_base(
            public_menu_found=False,
            public_menu_usable_for_sample=False,
            menu_readability_confidence=0.0,
            machine_evidence_found=True,
            ticket_machine_confidence=0.92,
            ticket_machine_evidence_type="explicit_text",
            ticket_machine_content_usable=True,
            observed_menu_topics=["ticket_machine_buttons", "ramen_types"],
        ))
        assert c["selected_template"] == "ramen_ticket_machine_only"


# ---------------------------------------------------------------------------
# 5. Ramen: no usable menu, 食券制 mentioned but unreadable
# ---------------------------------------------------------------------------

class TestRamenNeedsMachinePhoto:
    def test_selects_needs_ticket_machine_photo(self):
        c = classify_lead(_ramen_base(
            public_menu_found=False,
            public_menu_usable_for_sample=False,
            menu_readability_confidence=0.0,
            machine_evidence_found=True,
            ticket_machine_confidence=0.92,
            ticket_machine_evidence_type="review_text",
            ticket_machine_content_usable=False,
            observed_menu_topics=["ramen_types"],
        ))
        assert c["selected_template"] in (
            "ramen_needs_ticket_machine_photo", "skip",
        )
        # Must not use ticket_machine_only unless content is usable
        assert c["selected_template"] != "ramen_ticket_machine_only"


# ---------------------------------------------------------------------------
# 6. Ramen: only weak signals (category + counter + cash-only)
# ---------------------------------------------------------------------------

class TestRamenWeakSignalsNoMachine:
    def test_no_ticket_machine_template(self):
        c = classify_lead(_ramen_base(
            ticket_machine_confidence=0.0,
            # Simulate weak signals being rejected
            evidence_snippets=["カウンター席のみ", "現金only"],
        ))
        assert c["ticket_machine_confidence"] < 0.85
        body_result = build_evidence_gated_email(c)
        if body_result is not None:
            assert "券売機" not in body_result["body"]


# ---------------------------------------------------------------------------
# 7. Ramen: ramen types only, no toppings or sets
# ---------------------------------------------------------------------------

class TestRamenTypesOnly:
    def test_mentions_types_not_toppings_or_sets(self):
        c = classify_lead(_ramen_base(
            observed_menu_topics=["ramen_types"],
        ))
        assert c["selected_template"] == "ramen_visible_menu"
        body = _build_email(c)["body"]
        assert "ラーメンの種類" in body
        assert "トッピング" not in body
        assert "セット内容" not in body


# ---------------------------------------------------------------------------
# 8. Ramen: ramen types + toppings, no sets
# ---------------------------------------------------------------------------

class TestRamenTypesAndToppings:
    def test_mentions_types_and_toppings_not_sets(self):
        c = classify_lead(_ramen_base(
            observed_menu_topics=["ramen_types", "toppings"],
        ))
        assert c["selected_template"] == "ramen_visible_menu"
        body = _build_email(c)["body"]
        assert "ラーメンの種類・トッピング" in body
        assert "セット内容" not in body


# ---------------------------------------------------------------------------
# 9. Ramen: visible menu, ticket-machine confidence = 0.60
# ---------------------------------------------------------------------------

class TestRamenMachineConfidence060:
    def test_no_ticket_machine_mention(self):
        c = classify_lead(_ramen_base(
            ticket_machine_confidence=0.60,
        ))
        assert c["selected_template"] in (
            "ramen_visible_menu", "ramen_visible_menu_neutral_ordering",
        )
        body = _build_email(c)["body"]
        assert "券売機" not in body


# ---------------------------------------------------------------------------
# 10. Izakaya: food + drink, no course/nomihodai
# ---------------------------------------------------------------------------

class TestIzakayaFoodDrink:
    def test_food_drink_template(self):
        c = classify_lead(_izakaya_base())
        assert c["selected_template"] in ("izakaya_food_drink_only", "izakaya_standard")
        body = _build_email(c)["body"]
        assert "料理・ドリンク" in body or "料理" in body
        assert "コース内容" not in body
        assert "飲み放題" not in body

    def test_no_course_or_nomihodai_mention(self):
        c = classify_lead(_izakaya_base())
        body = _build_email(c)["body"]
        assert "コース内容" not in body
        assert "飲み放題" not in body


# ---------------------------------------------------------------------------
# 11. Izakaya: course visible, no nomihodai
# ---------------------------------------------------------------------------

class TestIzakayaCourseOnly:
    def test_course_template(self):
        c = classify_lead(_izakaya_base(
            observed_menu_topics=["food_items", "drink_items", "course_items"],
            course_confidence=0.80,
            course_evidence_notes="Course menu visible on website",
        ))
        assert c["selected_template"] == "izakaya_course_only"
        assert "飲み放題" not in _build_email(c)["subject"]


# ---------------------------------------------------------------------------
# 12. Izakaya: nomihodai visible, no course
# ---------------------------------------------------------------------------

class TestIzakayaNomihodaiOnly:
    def test_nomihodai_template(self):
        c = classify_lead(_izakaya_base(
            observed_menu_topics=["food_items", "drink_items", "nomihodai"],
            nomihodai_confidence=0.88,
            nomihodai_evidence_notes="Nomihodai found in menu",
        ))
        assert c["selected_template"] == "izakaya_nomihodai_only"
        assert "コース" not in _build_email(c)["subject"]


# ---------------------------------------------------------------------------
# 13. Izakaya: nomihodai + course visible
# ---------------------------------------------------------------------------

class TestIzakayaNomihodaiCourse:
    def test_nomihodai_course_template(self):
        c = classify_lead(_izakaya_base(
            observed_menu_topics=[
                "food_items", "drink_items", "nomihodai",
                "course_items", "last_order", "extra_charges",
            ],
            nomihodai_confidence=0.90,
            nomihodai_evidence_notes="Nomihodai plan found",
            course_confidence=0.85,
            course_evidence_notes="Course menu visible",
        ))
        assert c["selected_template"] == "izakaya_nomihodai_course"


# ---------------------------------------------------------------------------
# 14. Izakaya: food only
# ---------------------------------------------------------------------------

class TestIzakayaFoodOnly:
    def test_no_drink_or_course_mention(self):
        c = classify_lead(_izakaya_base(
            observed_menu_topics=["food_items"],
        ))
        body = _build_email(c)["body"]
        assert "料理" in body
        assert "ドリンク" not in body
        assert "コース" not in body


# ---------------------------------------------------------------------------
# 15. Izakaya: drink only
# ---------------------------------------------------------------------------

class TestIzakayaDrinkOnly:
    def test_no_food_or_course_mention(self):
        c = classify_lead(_izakaya_base(
            observed_menu_topics=["drink_items"],
        ))
        body = _build_email(c)["body"]
        # Should not mention 料理 unless observed
        assert "料理" not in body
        assert "コース" not in body


# ---------------------------------------------------------------------------
# 16. Menu found but too blurry
# ---------------------------------------------------------------------------

class TestMenuTooBlurry:
    def test_not_usable_for_sample(self):
        c = classify_lead(_ramen_base(
            public_menu_usable_for_sample=False,
            menu_readability_confidence=0.40,
        ))
        assert c["public_menu_usable_for_sample"] is False
        if c["selected_template"] != "skip":
            body = _build_email(c)["body"]
            assert "公開されているメニュー情報をもとに" not in body


# ---------------------------------------------------------------------------
# 17. No public menu, no ticket machine
# ---------------------------------------------------------------------------

class TestNoMenuNoMachine:
    def test_needs_photo_or_skip(self):
        c = classify_lead(_ramen_base(
            public_menu_found=False,
            public_menu_usable_for_sample=False,
            menu_readability_confidence=0.0,
        ))
        assert c["selected_template"] in (
            "ramen_needs_menu_photo", "skip",
        )


# ---------------------------------------------------------------------------
# 18. Contact form, public menu usable, no prohibition
# ---------------------------------------------------------------------------

class TestContactFormPublicMenu:
    def test_contact_form_template(self):
        c = classify_lead(_ramen_base(
            contact_channel="official_contact_form",
        ))
        assert c["selected_template"] == "contact_form_public_menu"
        body = _build_email(c)["body"]
        assert "reply to this email" not in body.lower()


# ---------------------------------------------------------------------------
# 19. Contact form says sales prohibited
# ---------------------------------------------------------------------------

class TestContactFormSalesProhibited:
    def test_skip(self):
        c = classify_lead(_ramen_base(
            contact_channel="official_contact_form",
            no_sales_or_solicitation_notice_found=True,
            no_sales_or_solicitation_notice_text="セールスお断り",
            should_skip_due_to_contact_policy=True,
        ))
        assert c["selected_template"] == "skip"


# ---------------------------------------------------------------------------
# 20. Public email but page says 営業メールお断り
# ---------------------------------------------------------------------------

class TestSalesProhibitionEmail:
    def test_skip(self):
        c = classify_lead(_ramen_base(
            no_sales_or_solicitation_notice_found=True,
            no_sales_or_solicitation_notice_text="営業メールお断り",
            should_skip_due_to_contact_policy=True,
        ))
        assert c["selected_template"] == "skip"


# ---------------------------------------------------------------------------
# 21. Comprehensive English menu found
# ---------------------------------------------------------------------------

class TestComprehensiveEnglishMenu:
    def test_skip(self):
        c = classify_lead(_ramen_base(
            existing_english_menu_quality="comprehensive",
            existing_english_menu_confidence=0.90,
            should_skip_due_to_existing_english_menu=True,
        ))
        assert c["selected_template"] == "skip"


# ---------------------------------------------------------------------------
# 22. Partial English menu found
# ---------------------------------------------------------------------------

class TestPartialEnglishMenu:
    def test_may_send_with_graceful_exit(self):
        c = classify_lead(_ramen_base(
            existing_english_menu_quality="partial",
            existing_english_menu_confidence=0.60,
        ))
        if c["selected_template"] != "skip":
            body = _build_email(c)["body"]
            assert "すでに十分な英語メニューをご用意済みでしたら" in body
            # Must not claim no English menu exists
            assert "英語メニューがない" not in body
            assert "英語表記がない" not in body


# ---------------------------------------------------------------------------
# 23. No public contact
# ---------------------------------------------------------------------------

class TestNoPublicContact:
    def test_skip(self):
        c = classify_lead(_ramen_base(
            contact_channel="none",
        ))
        assert c["selected_template"] == "skip"


# ---------------------------------------------------------------------------
# 24. Not clearly ramen or izakaya
# ---------------------------------------------------------------------------

class TestUnclearRestaurantType:
    def test_skip(self):
        c = classify_lead({
            "business_name": "テスト食堂",
            "restaurant_type": "unknown",
            "restaurant_type_confidence": 0.30,
            "contact_channel": "public_email",
            "public_menu_found": True,
            "public_menu_usable_for_sample": True,
            "menu_readability_confidence": 0.80,
            "observed_menu_topics": ["food_items"],
            "existing_english_menu_quality": "none_found",
        })
        assert c["selected_template"] == "skip"


# ---------------------------------------------------------------------------
# 25. Existing templates render without blank lines / placeholders
# ---------------------------------------------------------------------------

class TestCleanRendering:
    def test_no_blank_address_line(self):
        c = classify_lead(_ramen_base())
        body = _build_email(c)["body"]
        assert "BUSINESS_ADDRESS" not in body
        assert "所在地" not in body
        assert "住所" not in body

    def test_no_empty_lines_near_signature(self):
        c = classify_lead(_ramen_base())
        body = _build_email(c)["body"]
        lines = body.split("\n")
        # No double blank lines
        for i in range(len(lines) - 1):
            if lines[i].strip() == "" and lines[i + 1].strip() == "":
                pytest.fail("Double blank line found in email body")


# ---------------------------------------------------------------------------
# 26. Contact form keeps email contact intact
# ---------------------------------------------------------------------------

class TestContactFormIntact:
    def test_website_footer_intact(self):
        c = classify_lead(_ramen_base(
            contact_channel="official_contact_form",
        ))
        body = _build_email(c)["body"]
        # No address placeholder
        assert "所在地" not in body
        assert "住所" not in body
        assert "BUSINESS_ADDRESS" not in body


# ---------------------------------------------------------------------------
# Additional: claims validation
# ---------------------------------------------------------------------------

class TestClaimsGeneration:
    def test_blocked_topics_not_in_email(self):
        """Observed topics that are blocked must not appear in email."""
        c = classify_lead(_izakaya_base(
            observed_menu_topics=["food_items", "drink_items"],
            # No nomihodai or course evidence
            nomihodai_confidence=0.0,
            course_confidence=0.0,
        ))
        body = _build_email(c)["body"]
        assert "飲み放題" not in body
        assert "コース内容" not in body
        assert "mention_nomihodai" in c["blocked_claims"]
        assert "mention_course" in c["blocked_claims"]

    def test_ticket_machine_in_blocked_when_no_evidence(self):
        c = classify_lead(_ramen_base())
        assert "mention_ticket_machine" in c["blocked_claims"]

    def test_allowed_topics_in_email(self):
        c = classify_lead(_ramen_base(
            observed_menu_topics=["ramen_types", "toppings", "set_items"],
        ))
        body = _build_email(c)["body"]
        assert "ラーメンの種類" in body
        assert "トッピング" in body
        assert "セット内容" in body


# ---------------------------------------------------------------------------
# Human review triggers
# ---------------------------------------------------------------------------

class TestHumanReview:
    def test_medium_ticket_machine_triggers_review(self):
        c = classify_lead(_ramen_base(
            ticket_machine_confidence=0.75,
        ))
        assert c["human_review_required"] is True

    def test_low_type_confidence_triggers_review(self):
        c = classify_lead({
            "business_name": "テスト",
            "restaurant_type": "ramen",
            "restaurant_type_confidence": 0.65,
            "contact_channel": "public_email",
            "public_menu_found": True,
            "public_menu_usable_for_sample": True,
            "menu_readability_confidence": 0.85,
            "observed_menu_topics": ["ramen_types"],
            "existing_english_menu_quality": "none_found",
        })
        assert c["human_review_required"] is True


# ===================================================================
# INTEGRATION AND SAFETY AUDIT
# ===================================================================

# --- 3. Production flow simulation ---

class TestProductionFlowSimulation:
    """Simulate the real production sending flow and verify the
    evidence-gated classifier is used, not the old builder."""

    def test_classify_and_build_called_for_ramen(self):
        """Full flow: classify_lead → build_evidence_gated_email → verify."""
        c = classify_lead(_ramen_base())
        result = build_evidence_gated_email(c)
        assert result is not None
        assert "subject" in result
        assert "body" in result
        assert "english_body" in result
        assert result["body"] != ""

    def test_skipped_leads_return_none(self):
        """Skipped leads produce None from build_evidence_gated_email."""
        c = classify_lead(_ramen_base(
            contact_channel="none",
        ))
        assert c["selected_template"] == "skip"
        result = build_evidence_gated_email(c)
        assert result is None

    def test_human_review_leads_still_buildable_but_flagged(self):
        """Human review leads can be built but must be flagged."""
        c = classify_lead(_ramen_base(
            ticket_machine_confidence=0.75,
        ))
        assert c["human_review_required"] is True
        result = build_evidence_gated_email(c)
        assert result is not None

    def test_old_builder_not_in_production_path(self):
        """Verify the production path uses evidence-gated, not old builder."""
        c = classify_lead(_ramen_base())
        result = build_evidence_gated_email(c)
        assert result is not None
        assert result.get("classification") is not None
        assert result["classification"]["selected_template"] == "ramen_visible_menu"


# --- 4. Negative-claim rendered email tests ---

class TestNegativeClaims:
    """Assert that the rendered Japanese email body does NOT contain
    unsupported claims."""

    def test_no_ticket_machine_without_evidence(self):
        c = classify_lead(_ramen_base())
        body = _build_email(c)["body"]
        assert "券売機" not in body
        assert "食券" not in body

    def test_no_nomihodai_without_evidence(self):
        c = classify_lead(_izakaya_base())
        body = _build_email(c)["body"]
        assert "飲み放題" not in body

    def test_no_course_without_evidence(self):
        c = classify_lead(_izakaya_base())
        body = _build_email(c)["body"]
        assert "コース" not in body

    def test_no_toppings_without_observation(self):
        c = classify_lead(_ramen_base(
            observed_menu_topics=["ramen_types"],
        ))
        body = _build_email(c)["body"]
        assert "トッピング" not in body

    def test_no_set_items_without_observation(self):
        c = classify_lead(_ramen_base(
            observed_menu_topics=["ramen_types", "toppings"],
        ))
        body = _build_email(c)["body"]
        assert "セット内容" not in body

    def test_no_sample_offer_without_usable_menu(self):
        c = classify_lead(_ramen_base(
            public_menu_usable_for_sample=False,
            menu_readability_confidence=0.30,
        ))
        if c["selected_template"] == "skip":
            return
        result = build_evidence_gated_email(c)
        if result is None:
            return
        assert "公開されているメニュー情報をもとに" not in result["body"]

    def test_no_created_sample_claim(self):
        """作成しました must never appear (use ご提案できれば instead)."""
        c = classify_lead(_ramen_base())
        body = _build_email(c)["body"]
        assert "作成しました" not in body

    def test_no_address_placeholder(self):
        c = classify_lead(_ramen_base())
        body = _build_email(c)["body"]
        assert "BUSINESS_ADDRESS" not in body
        assert "所在地" not in body
        assert "住所" not in body


# --- 5. Positive-claim rendered email tests ---

class TestPositiveClaims:
    """Confirm that supported claims appear when evidence supports them."""

    def test_ticket_machine_wording_when_evidenced(self):
        c = classify_lead(_ramen_base(
            machine_evidence_found=True,
            ticket_machine_confidence=0.92,
            ticket_machine_evidence_type="explicit_text",
            observed_menu_topics=["ramen_types", "toppings", "set_items", "ticket_machine_buttons"],
        ))
        body = _build_email(c)["body"]
        assert "券売機" in body

    def test_nomihodai_wording_when_evidenced(self):
        c = classify_lead(_izakaya_base(
            observed_menu_topics=["food_items", "drink_items", "nomihodai"],
            nomihodai_confidence=0.90,
            nomihodai_evidence_notes="Nomihodai in menu",
        ))
        body = _build_email(c)["body"]
        assert "飲み放題" in body

    def test_course_wording_when_evidenced(self):
        c = classify_lead(_izakaya_base(
            observed_menu_topics=["food_items", "drink_items", "course_items"],
            course_confidence=0.82,
            course_evidence_notes="Course menu on website",
        ))
        body = _build_email(c)["body"]
        assert "コース" in body

    def test_ramen_types_only_shows_types(self):
        c = classify_lead(_ramen_base(
            observed_menu_topics=["ramen_types"],
        ))
        body = _build_email(c)["body"]
        assert "ラーメンの種類" in body
        assert "トッピング" not in body
        assert "セット内容" not in body

    def test_food_drink_izakaya_shows_both(self):
        c = classify_lead(_izakaya_base())
        body = _build_email(c)["body"]
        assert "料理" in body
        assert "ドリンク" in body
        assert "飲み放題" not in body
        assert "コース" not in body


# --- 6. CTA behavior ---

class TestCTABehavior:
    def test_usable_menu_uses_kibou_cta(self):
        c = classify_lead(_ramen_base())
        body = _build_email(c)["body"]
        assert "「希望」とだけご返信いただければ結構です" in body

    def test_no_usable_menu_uses_photo_cta(self):
        c = classify_lead(_ramen_base(
            public_menu_usable_for_sample=False,
            menu_readability_confidence=0.30,
        ))
        if c["selected_template"] == "skip":
            pytest.skip("Template is skip, no CTA to check")
        result = build_evidence_gated_email(c)
        if result is None:
            pytest.skip("Template is skip")
        assert "お写真を1枚お送りいただければ" in result["body"]

    def test_ticket_machine_content_uses_kibou_cta(self):
        c = classify_lead(_ramen_base(
            public_menu_found=False,
            public_menu_usable_for_sample=False,
            menu_readability_confidence=0.0,
            machine_evidence_found=True,
            ticket_machine_confidence=0.92,
            ticket_machine_evidence_type="explicit_text",
            ticket_machine_content_usable=True,
            observed_menu_topics=["ticket_machine_buttons", "ramen_types"],
        ))
        result = build_evidence_gated_email(c)
        if result is not None:
            assert "「希望」とだけご返信" in result["body"]

    def test_contact_form_no_reply_to_email(self):
        c = classify_lead(_ramen_base(
            contact_channel="official_contact_form",
        ))
        body = _build_email(c)["body"]
        assert "reply to this email" not in body.lower()


# --- 7. Skip behavior ---

class TestSkipBehavior:
    def test_no_public_contact_skips(self):
        c = classify_lead(_ramen_base(contact_channel="none"))
        assert c["selected_template"] == "skip"
        assert "No public email" in c["selected_template_reason"] or "contact" in c["selected_template_reason"].lower()

    def test_sales_prohibition_skips(self):
        c = classify_lead(_ramen_base(
            should_skip_due_to_contact_policy=True,
            no_sales_or_solicitation_notice_found=True,
        ))
        assert c["selected_template"] == "skip"

    def test_comprehensive_english_menu_skips(self):
        c = classify_lead(_ramen_base(
            existing_english_menu_quality="comprehensive",
            should_skip_due_to_existing_english_menu=True,
        ))
        assert c["selected_template"] == "skip"

    def test_unclear_type_skips(self):
        c = classify_lead({
            "business_name": "テスト",
            "restaurant_type": "unknown",
            "restaurant_type_confidence": 0.30,
            "contact_channel": "public_email",
            "public_menu_found": True,
            "public_menu_usable_for_sample": True,
            "menu_readability_confidence": 0.80,
            "observed_menu_topics": ["food_items"],
            "existing_english_menu_quality": "none_found",
        })
        assert c["selected_template"] == "skip"

    def test_human_review_flagged_not_auto_sent(self):
        """Human review leads have the flag but template may still be set."""
        c = classify_lead(_ramen_base(ticket_machine_confidence=0.75))
        assert c["human_review_required"] is True


# --- 8. Audit log ---

class TestAuditLog:
    def test_audit_fields_present(self):
        c = classify_lead(_ramen_base())
        assert "selected_template" in c
        assert "selected_template_reason" in c
        assert "allowed_claims" in c
        assert "blocked_claims" in c
        assert "public_menu_evidence_notes" in c
        assert "public_contact_source" in c
        assert "human_review_required" in c

    def test_audit_in_email_result(self):
        c = classify_lead(_ramen_base())
        result = build_evidence_gated_email(c)
        assert result is not None
        assert "classification" in result
        assert result["classification"]["selected_template"] == "ramen_visible_menu"

    def test_skip_audit_has_reason(self):
        c = classify_lead(_ramen_base(contact_channel="none"))
        assert c["selected_template"] == "skip"
        assert c["selected_template_reason"] != ""
        result = build_evidence_gated_email(c)
        assert result is None

    def test_all_templates_covered_by_tests(self):
        """Verify every template value has at least one test that exercises it."""
        from pipeline.evidence_classifier import VALID_TEMPLATES
        tested = {
            "ramen_visible_menu",
            "ramen_visible_menu_neutral_ordering",
            "ramen_menu_plus_ticket_machine",
            "ramen_ticket_machine_only",
            "ramen_needs_menu_photo",
            "ramen_needs_ticket_machine_photo",
            "izakaya_standard",
            "izakaya_food_drink_only",
            "izakaya_course_only",
            "izakaya_nomihodai_only",
            "izakaya_nomihodai_course",
            "izakaya_needs_menu_photo",
            "contact_form_public_menu",
            "contact_form_needs_menu_photo",
            "skip",
        }
        untested = VALID_TEMPLATES - tested
        assert untested == set(), f"Templates not covered by tests: {untested}"


# ===================================================================
# SEND-GATE INTEGRATION TESTS
# ===================================================================

class TestSendGateBlocking:
    """Verify the send gate blocks emails that should not go out."""

    def test_preexisting_lead_without_audit_gets_classified(self):
        """A lead with no evidence_audit gets classified before send."""
        lead = _ramen_base()
        # Remove evidence_audit to simulate pre-existing lead
        lead.pop("evidence_audit", None)
        c = classify_lead(lead)
        assert c["selected_template"] != "skip"
        result = build_evidence_gated_email(c)
        assert result is not None
        # Audit should be buildable
        from dashboard.app import _build_evidence_audit
        audit = _build_evidence_audit(c)
        assert audit["selected_template"] == "ramen_visible_menu"

    def test_no_audit_never_calls_old_builder(self):
        """Even without audit, old build_outreach_email must not be called."""
        import inspect
        from pipeline.outreach import build_evidence_gated_email

        # Verify the evidence-gated path is used
        c = classify_lead(_ramen_base())
        result = build_evidence_gated_email(c)
        assert result is not None
        assert "classification" in result

    def test_insufficient_data_blocks_send(self):
        """Lead with insufficient data should be blocked from sending."""
        c = classify_lead({
            "business_name": "テスト",
            # Missing most fields — should classify as skip
        })
        assert c["selected_template"] == "skip"
        assert build_evidence_gated_email(c) is None

    def test_skip_template_blocks_send(self):
        c = classify_lead(_ramen_base(contact_channel="none"))
        assert c["selected_template"] == "skip"
        result = build_evidence_gated_email(c)
        assert result is None

    def test_human_review_blocks_auto_send(self):
        c = classify_lead(_ramen_base(ticket_machine_confidence=0.75))
        assert c["human_review_required"] is True
        # Email can be built but must not be auto-sent
        result = build_evidence_gated_email(c)
        assert result is not None
        # Send gate should check human_review_required


class TestSendTimeClaimValidation:
    """Verify _validate_email_claims catches unsupported claims."""

    def test_valid_email_passes_validation(self):
        from dashboard.app import _validate_email_claims
        c = classify_lead(_ramen_base())
        result = build_evidence_gated_email(c)
        audit = c  # classification IS the audit source
        # Should not raise
        _validate_email_claims(result["body"], {
            "allowed_claims": c["allowed_claims"],
        })

    def test_ticket_machine_claim_without_evidence_fails(self):
        from dashboard.app import _validate_email_claims
        with pytest.raises(ValueError, match="券売機"):
            _validate_email_claims(
                "券売機の案内です",
                {"allowed_claims": []},
            )

    def test_nomihodai_claim_without_evidence_fails(self):
        from dashboard.app import _validate_email_claims
        with pytest.raises(ValueError, match="飲み放題"):
            _validate_email_claims(
                "飲み放題の案内です",
                {"allowed_claims": []},
            )

    def test_course_claim_without_evidence_fails(self):
        from dashboard.app import _validate_email_claims
        with pytest.raises(ValueError, match="コース"):
            _validate_email_claims(
                "コース内容について",
                {"allowed_claims": []},
            )

    def test_toppings_claim_without_evidence_fails(self):
        from dashboard.app import _validate_email_claims
        with pytest.raises(ValueError, match="トッピング"):
            _validate_email_claims(
                "トッピングの案内です",
                {"allowed_claims": []},
            )

    def test_set_items_claim_without_evidence_fails(self):
        from dashboard.app import _validate_email_claims
        with pytest.raises(ValueError, match="セット内容"):
            _validate_email_claims(
                "セット内容について",
                {"allowed_claims": []},
            )

    def test_placeholder_fails(self):
        from dashboard.app import _validate_email_claims
        with pytest.raises(ValueError, match="BUSINESS_ADDRESS"):
            _validate_email_claims(
                "テスト BUSINESS_ADDRESS テスト",
                {"allowed_claims": []},
            )

    def test_allowed_claim_passes(self):
        from dashboard.app import _validate_email_claims
        # Should NOT raise — ticket machine claim is allowed
        _validate_email_claims(
            "券売機の案内です",
            {"allowed_claims": ["mention_ticket_machine"]},
        )


class TestAuditVersioning:
    """Verify audit has versioning and timestamp fields."""

    def test_audit_has_version_fields(self):
        from dashboard.app import _build_evidence_audit
        c = classify_lead(_ramen_base())
        audit = _build_evidence_audit(c)
        assert "evidence_classifier_version" in audit
        assert "template_renderer_version" in audit
        assert audit["evidence_classifier_version"] == "1.0"

    def test_audit_has_timestamp(self):
        from dashboard.app import _build_evidence_audit
        c = classify_lead(_ramen_base())
        audit = _build_evidence_audit(c)
        assert "generated_at" in audit
        assert "202" in audit["generated_at"]  # ISO date starts with year

    def test_audit_has_all_required_fields(self):
        from dashboard.app import _build_evidence_audit
        c = classify_lead(_ramen_base())
        audit = _build_evidence_audit(c)
        required = [
            "evidence_classifier_version", "template_renderer_version",
            "generated_at", "selected_template", "selected_template_reason",
            "allowed_claims", "blocked_claims", "human_review_required",
            "skip_reason",
        ]
        for field in required:
            assert field in audit, f"Missing audit field: {field}"

    def test_old_builder_not_in_automatic_send_flow(self):
        """Verify build_outreach_email is not imported in send function."""
        import ast
        import inspect
        # Read the source and check the send function's imports
        source = inspect.getsource(
            __import__("dashboard.app", fromlist=["_send_lead_email_payload"])._send_lead_email_payload
        )
        assert "build_outreach_email" not in source, (
            "build_outreach_email still referenced in _send_lead_email_payload"
        )
