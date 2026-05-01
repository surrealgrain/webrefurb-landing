"""Tests for pipeline.lead_qualifier.review_scraper."""

from __future__ import annotations

import pytest

from pipeline.lead_qualifier.models import ReviewScrapeResult, ReviewText
from pipeline.lead_qualifier.review_scraper import detect_review_language


class TestLanguageDetection:
    def test_english_review(self):
        assert detect_review_language("Great ramen, best broth ever!") == "en"

    def test_japanese_review(self):
        assert detect_review_language("とても美味しいラーメンでした") == "ja"

    def test_mixed_review(self):
        text = "美味しい ramen at this お店"
        lang = detect_review_language(text)
        assert lang == "mixed"

    def test_empty_text(self):
        assert detect_review_language("") == "unknown"

    def test_numbers_only(self):
        assert detect_review_language("12345") == "unknown"

    def test_mostly_english_with_some_japanese(self):
        # English dominant but a few Japanese chars — mixed because ratio is borderline
        text = "This ramen shop was great but 美味しかった"
        lang = detect_review_language(text)
        assert lang in ("en", "mixed")  # borderline, both acceptable

    def test_mostly_japanese_with_some_english(self):
        text = "このラーメンは delicious でした"
        lang = detect_review_language(text)
        assert lang in ("ja", "mixed")  # borderline, both acceptable

    def test_short_english(self):
        assert detect_review_language("ok") == "en"

    def test_short_japanese(self):
        assert detect_review_language("美味") == "ja"


class TestReviewScrapeResultModel:
    def test_default_values(self):
        result = ReviewScrapeResult(business_name="Test Shop")
        assert result.business_name == "Test Shop"
        assert result.reviews == []
        assert result.scrape_success is False
        assert result.scrape_error == ""
        assert result.place_id == ""
        assert result.total_review_count is None
        assert result.average_rating is None

    def test_with_reviews(self):
        reviews = [
            ReviewText(text="No english menu!", language="en", rating=3),
            ReviewText(text="美味しいラーメン", language="ja", rating=5),
        ]
        result = ReviewScrapeResult(
            business_name="Test Shop",
            reviews=reviews,
            scrape_success=True,
            average_rating=3.8,
            total_review_count=150,
        )
        assert len(result.reviews) == 2
        assert result.scrape_success is True
        assert result.average_rating == 3.8
        assert result.total_review_count == 150


class TestReviewTextModel:
    def test_default_values(self):
        r = ReviewText(text="Great ramen")
        assert r.text == "Great ramen"
        assert r.language == ""
        assert r.rating is None
        assert r.reviewer_name == ""
        assert r.date == ""

    def test_full_review(self):
        r = ReviewText(
            text="No english menu",
            language="en",
            rating=2,
            reviewer_name="John",
            date="3 months ago",
        )
        assert r.rating == 2
        assert r.reviewer_name == "John"
        assert r.date == "3 months ago"


class TestScrapeGoogleReviewsGracefulFailure:
    def test_returns_result_on_playwright_error(self):
        """Even if playwright is broken, we get a valid result, not an exception."""
        from pipeline.lead_qualifier.review_scraper import scrape_google_reviews
        # This will fail to connect to a real browser in test, but should not crash
        result = scrape_google_reviews(
            business_name="Nonexistent Shop xyz123",
            address="Nowhere",
            city="TestCity",
            timeout_seconds=5,
        )
        assert isinstance(result, ReviewScrapeResult)
        assert result.business_name == "Nonexistent Shop xyz123"
        # Either success=False (browser failed) or success=True (unlikely)
        assert isinstance(result.scrape_success, bool)
