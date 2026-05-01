"""Tests for pipeline.lead_qualifier.pain_signals."""

from __future__ import annotations

import pytest

from pipeline.lead_qualifier.models import (
    PainSignalAssessment,
    PainSignalMatch,
    ReviewScrapeResult,
    ReviewText,
)
from pipeline.lead_qualifier.pain_signals import (
    EN_PAIN_HIGH,
    EN_PAIN_LOW,
    EN_PAIN_MEDIUM,
    JA_PAIN_HIGH,
    JA_PAIN_LOW,
    JA_PAIN_MEDIUM,
    assess_pain_signals,
    _compute_pain_score,
    _is_foreign_reviewer,
)


class TestEnglishHighSeverityMatching:
    def test_no_english_menu(self):
        reviews = [ReviewText(text="There was no english menu at all.", language="en")]
        result = _assess_with_reviews(reviews)
        assert result.has_pain_signals
        assert any(m.keyword == "no english menu" and m.severity == "high" for m in result.matches)

    def test_couldnt_order(self):
        reviews = [ReviewText(text="I couldn't order anything.", language="en")]
        result = _assess_with_reviews(reviews)
        assert result.has_pain_signals
        assert any("couldn't order" in m.keyword for m in result.matches)

    def test_ticket_machine_confusing(self):
        reviews = [ReviewText(text="The ticket machine confusing interface was hard.", language="en")]
        result = _assess_with_reviews(reviews)
        assert result.has_pain_signals
        assert any("ticket machine confusing" in m.keyword for m in result.matches)

    def test_google_translate(self):
        reviews = [ReviewText(text="Had to use google translate for everything.", language="en")]
        result = _assess_with_reviews(reviews)
        assert result.has_pain_signals
        assert any("google translate" in m.keyword for m in result.matches)


class TestEnglishMediumSeverityMatching:
    def test_language_barrier(self):
        reviews = [ReviewText(text="There was a language barrier.", language="en")]
        result = _assess_with_reviews(reviews)
        assert result.has_pain_signals
        assert any(m.keyword == "language barrier" and m.severity == "medium" for m in result.matches)

    def test_hard_to_order(self):
        reviews = [ReviewText(text="It was hard to order.", language="en")]
        result = _assess_with_reviews(reviews)
        assert result.has_pain_signals

    def test_food_ticket_machine(self):
        reviews = [ReviewText(text="You order from a food ticket machine.", language="en")]
        result = _assess_with_reviews(reviews)
        assert result.has_pain_signals


class TestEnglishLowSeverityMatching:
    def test_tourist_friendly(self):
        reviews = [ReviewText(text="Place was tourist friendly but menu issues.", language="en")]
        result = _assess_with_reviews(reviews)
        assert any(m.severity == "low" for m in result.matches)


class TestJapanesePainKeywords:
    def test_japanese_high_no_english_menu(self):
        reviews = [ReviewText(text="英語のメニューがないので困りました。", language="ja")]
        result = _assess_with_reviews(reviews)
        assert result.has_pain_signals
        assert any(m.language == "ja" and m.severity == "high" for m in result.matches)

    def test_japanese_high_cannot_order(self):
        reviews = [ReviewText(text="外国人が注文できない状況でした。", language="ja")]
        result = _assess_with_reviews(reviews)
        assert result.has_pain_signals

    def test_japanese_medium_foreigners(self):
        reviews = [ReviewText(text="外国人のお客様も来店されます。", language="ja")]
        result = _assess_with_reviews(reviews)
        assert any(m.language == "ja" for m in result.matches)

    def test_japanese_low_multilingual(self):
        reviews = [ReviewText(text="多言語対応が必要ですね。", language="ja")]
        result = _assess_with_reviews(reviews)
        assert any(m.language == "ja" and m.severity == "low" for m in result.matches)


class TestNoFalsePositives:
    def test_positive_review_no_pain(self):
        reviews = [ReviewText(
            text="Amazing ramen! Best broth I've ever had. Great service and atmosphere.",
            language="en",
            reviewer_name="田中太郎",
        )]
        result = _assess_with_reviews(reviews)
        assert not result.has_pain_signals
        assert result.pain_score == 0

    def test_neutral_japanese_review(self):
        reviews = [ReviewText(text="美味しいラーメンでした。また行きたいです。", language="ja")]
        result = _assess_with_reviews(reviews)
        assert not result.has_pain_signals


class TestForeignReviewerDetection:
    def test_western_name(self):
        assert _is_foreign_reviewer("John Smith", "Great place")

    def test_western_name_with_hyphen(self):
        assert _is_foreign_reviewer("Mary-Jane O'Brien", "Good ramen")

    def test_japanese_name_not_flagged(self):
        assert not _is_foreign_reviewer("田中太郎", "美味しかった")

    def test_empty_name_english_text(self):
        assert _is_foreign_reviewer("", "This is an English review about ramen and noodles being delicious")

    def test_empty_name_japanese_text(self):
        assert not _is_foreign_reviewer("", "とても美味しいラーメンでした。おすすめです。")

    def test_empty_name_short_text(self):
        assert not _is_foreign_reviewer("", "ok")


class TestPainScoreComputation:
    def test_zero_matches(self):
        assert _compute_pain_score([], 0) == 0

    def test_single_high_match(self):
        matches = [PainSignalMatch(keyword="test", language="en", severity="high", source="test", context="")]
        assert _compute_pain_score(matches, 0) == 15

    def test_high_cap_at_60(self):
        matches = [
            PainSignalMatch(keyword=f"test{i}", language="en", severity="high", source="test", context="")
            for i in range(10)
        ]
        assert _compute_pain_score(matches, 0) >= 60
        # High contributes max 60, total with nothing else should be 60
        assert _compute_pain_score(matches, 0) == 60

    def test_medium_cap_at_32(self):
        matches = [
            PainSignalMatch(keyword=f"test{i}", language="en", severity="medium", source="test", context="")
            for i in range(10)
        ]
        assert _compute_pain_score(matches, 0) == 32

    def test_low_cap_at_12(self):
        matches = [
            PainSignalMatch(keyword=f"test{i}", language="en", severity="low", source="test", context="")
            for i in range(10)
        ]
        assert _compute_pain_score(matches, 0) == 12

    def test_foreign_reviewer_bonus(self):
        matches = [PainSignalMatch(keyword="test", language="en", severity="medium", source="test", context="")]
        score_no_foreign = _compute_pain_score(matches, 0)
        score_with_foreign = _compute_pain_score(matches, 3)
        assert score_with_foreign > score_no_foreign
        assert score_with_foreign == 8 + 6  # 8 medium + 3*2 foreign

    def test_foreign_bonus_cap_at_10(self):
        matches = [PainSignalMatch(keyword="test", language="en", severity="low", source="test", context="")]
        assert _compute_pain_score(matches, 20) == 3 + 10  # 3 low + 10 foreign cap

    def test_multi_language_bonus(self):
        en_match = PainSignalMatch(keyword="test_en", language="en", severity="medium", source="test", context="")
        ja_match = PainSignalMatch(keyword="test_ja", language="ja", severity="medium", source="test", context="")
        score = _compute_pain_score([en_match, ja_match], 0)
        assert score == 8 + 8 + 5  # two medium + multi bonus

    def test_total_capped_at_100(self):
        matches = [
            PainSignalMatch(keyword=f"h{i}", language="en", severity="high", source="test", context="")
            for i in range(5)
        ] + [
            PainSignalMatch(keyword=f"m{i}", language="en", severity="medium", source="test", context="")
            for i in range(5)
        ] + [
            PainSignalMatch(keyword=f"l{i}", language="en", severity="low", source="test", context="")
            for i in range(5)
        ]
        score = _compute_pain_score(matches, 10)
        assert score == 100


class TestWebsiteEvidencePain:
    def test_missing_english_is_high_pain(self):
        result = assess_pain_signals(
            business_name="Test Ramen",
            english_availability="missing",
        )
        assert result.has_pain_signals
        assert any(m.severity == "high" and "no english" in m.keyword for m in result.matches)

    def test_hard_to_use_english_is_high_pain(self):
        result = assess_pain_signals(
            business_name="Test Ramen",
            english_availability="hard_to_use",
        )
        assert result.has_pain_signals
        assert any(m.severity == "high" for m in result.matches)

    def test_image_only_english_is_high_pain(self):
        result = assess_pain_signals(
            business_name="Test Ramen",
            english_availability="image_only",
        )
        assert result.has_pain_signals

    def test_clear_usable_not_pain(self):
        result = assess_pain_signals(
            business_name="Test Ramen",
            english_availability="clear_usable",
        )
        assert not result.has_pain_signals

    def test_image_locked_menu_is_medium_pain(self):
        result = assess_pain_signals(
            business_name="Test Ramen",
            evidence_classes=["image_locked_menu", "menu_text_found"],
        )
        assert any(m.keyword == "menu image only no selectable text" for m in result.matches)

    def test_ticket_machine_no_english_is_high_pain(self):
        result = assess_pain_signals(
            business_name="Test Ramen",
            machine_evidence_found=True,
            english_availability="missing",
        )
        assert any("ticket machine" in m.keyword and m.severity == "high" for m in result.matches)

    def test_ticket_machine_with_english_no_pain(self):
        result = assess_pain_signals(
            business_name="Test Ramen",
            machine_evidence_found=True,
            english_availability="clear_usable",
        )
        assert not any("ticket machine" in m.keyword for m in result.matches)


class TestCombinedSignals:
    def test_reviews_plus_evidence(self):
        reviews = [ReviewText(text="No english menu available.", language="en")]
        result = assess_pain_signals(
            business_name="Test Ramen",
            review_scrape_result=ReviewScrapeResult(
                business_name="Test Ramen",
                reviews=reviews,
                scrape_success=True,
            ),
            english_availability="missing",
            machine_evidence_found=True,
        )
        assert result.pain_score >= 30  # Multiple signals stacked

    def test_website_text_scanned(self):
        result = assess_pain_signals(
            business_name="Test Ramen",
            website_text="This shop has a ticket machine confusing ordering process for tourists.",
        )
        assert result.has_pain_signals
        assert any("ticket machine confusing" in m.keyword for m in result.matches)


class TestSummary:
    def test_no_signals_summary(self):
        result = assess_pain_signals(business_name="Test Ramen")
        assert "No ordering friction" in result.summary

    def test_signals_summary(self):
        reviews = [ReviewText(text="No english menu and couldn't order.", language="en")]
        result = _assess_with_reviews(reviews)
        assert "high-severity" in result.summary
        assert "pain score" in result.summary


class TestKeywordCoverage:
    def test_all_en_high_are_strings(self):
        for kw in EN_PAIN_HIGH:
            assert isinstance(kw, str) and len(kw) > 3

    def test_all_en_medium_are_strings(self):
        for kw in EN_PAIN_MEDIUM:
            assert isinstance(kw, str) and len(kw) > 3

    def test_all_en_low_are_strings(self):
        for kw in EN_PAIN_LOW:
            assert isinstance(kw, str) and len(kw) > 3

    def test_all_ja_high_are_strings(self):
        for kw in JA_PAIN_HIGH:
            assert isinstance(kw, str) and len(kw) > 2

    def test_all_ja_medium_are_strings(self):
        for kw in JA_PAIN_MEDIUM:
            assert isinstance(kw, str) and len(kw) > 1

    def test_all_ja_low_are_strings(self):
        for kw in JA_PAIN_LOW:
            assert isinstance(kw, str) and len(kw) > 1


# Helper
def _assess_with_reviews(reviews: list[ReviewText]) -> PainSignalAssessment:
    return assess_pain_signals(
        business_name="Test Ramen",
        review_scrape_result=ReviewScrapeResult(
            business_name="Test Ramen",
            reviews=reviews,
            scrape_success=True,
        ),
    )
