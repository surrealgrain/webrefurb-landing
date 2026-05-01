"""Scrape Google Maps reviews for a restaurant using Playwright.

Mirrors the browser setup from pipeline.search_provider but focused on
extracting review text rather than place metadata.

Graceful degradation: returns empty results on any failure, never crashes.
"""

from __future__ import annotations

import re
import time
import urllib.parse
from typing import Any

from .models import ReviewScrapeResult, ReviewText

# Japanese character ranges for language detection
_JA_CHAR_RE = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]")
_LATIN_CHAR_RE = re.compile(r"[a-zA-Z]")


def scrape_google_reviews(
    *,
    business_name: str,
    address: str = "",
    city: str = "",
    place_id: str = "",
    max_reviews: int = 50,
    timeout_seconds: int = 20,
) -> ReviewScrapeResult:
    """Scrape Google Maps reviews for a restaurant.

    Strategy:
    1. If place_id given, navigate directly via place_id URL.
    2. Otherwise, search Google Maps for "{business_name} {address}".
    3. Click into place page, switch to Reviews tab.
    4. Scroll to load reviews, extract text/rating/reviewer/date.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return ReviewScrapeResult(
            business_name=business_name,
            scrape_success=False,
            scrape_error="playwright not installed",
        )

    browser = None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                locale="ja-JP",
                geolocation={"latitude": 35.658, "longitude": 139.701},
                permissions=["geolocation"],
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122 Safari/537.36"
                ),
            )
            page = context.new_page()
            page.set_default_timeout(max(5_000, min(timeout_seconds * 1000, 20_000)))

            # Navigate to place page
            if place_id:
                url = f"https://www.google.com/maps/place/?q=place_id:{place_id}&hl=ja"
            else:
                query = " ".join(part for part in [business_name, address, city] if part)
                url = "https://www.google.com/maps/search/" + urllib.parse.quote(query) + "?hl=ja&gl=jp"

            page.goto(url, wait_until="domcontentloaded", timeout=max(10_000, min(timeout_seconds * 1000, 30_000)))
            page.wait_for_timeout(3_000)

            # If we searched (no place_id), click first result
            if not place_id:
                clicked = _click_first_result(page)
                if not clicked:
                    context.close()
                    return ReviewScrapeResult(
                        business_name=business_name,
                        scrape_success=False,
                        scrape_error="no search result found",
                    )
                page.wait_for_timeout(2_000)

            # Click Reviews tab
            _click_reviews_tab(page)
            page.wait_for_timeout(1_500)

            # Scroll to load reviews
            _scroll_reviews(page, max_reviews)

            # Extract reviews
            reviews = _extract_reviews_from_page(page)

            # Extract metadata
            total_count = _extract_total_review_count(page)
            avg_rating = _extract_average_rating(page)

            context.close()

            return ReviewScrapeResult(
                business_name=business_name,
                place_id=place_id,
                reviews=reviews[:max_reviews],
                total_review_count=total_count,
                average_rating=avg_rating,
                scrape_success=True,
            )
    except Exception as exc:
        return ReviewScrapeResult(
            business_name=business_name,
            scrape_success=False,
            scrape_error=str(exc)[:200],
        )
    finally:
        try:
            if browser:
                browser.close()
        except Exception:
            pass


def detect_review_language(text: str) -> str:
    """Heuristic language detection based on character ratio."""
    if not text:
        return "unknown"
    ja_count = len(_JA_CHAR_RE.findall(text))
    latin_count = len(_LATIN_CHAR_RE.findall(text))
    total = ja_count + latin_count
    if total == 0:
        return "unknown"
    ja_ratio = ja_count / total
    if ja_ratio > 0.6:
        return "ja"
    if ja_ratio < 0.2:
        return "en"
    return "mixed"


def _click_first_result(page: Any) -> bool:
    """Click the first search result in Google Maps."""
    selectors = [
        'a[href*="/maps/place/"]',
        '[role="feed"] a',
        'div[role="feed"] > div > div a',
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                el.click()
                return True
        except Exception:
            continue
    return False


def _click_reviews_tab(page: Any) -> bool:
    """Find and click the Reviews tab button."""
    # Try button with "Reviews" or "レビュー" text
    selectors = [
        'button[role="tab"]:has-text("Reviews")',
        'button[role="tab"]:has-text("レビュー")',
        'button:has-text("Reviews")',
        'button:has-text("レビュー")',
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                el.click()
                return True
        except Exception:
            continue
    return False


def _scroll_reviews(page: Any, max_reviews: int) -> None:
    """Scroll the review panel to load more reviews."""
    # Find scrollable review container
    scrollable = page.query_selector(
        'div[role="main"] div[style*="overflow"]'
    ) or page.query_selector('div[role="main"]')

    scrolls = min(max_reviews // 5 + 1, 15)  # ~5 reviews per scroll
    for _ in range(scrolls):
        try:
            if scrollable:
                scrollable.evaluate("el => el.scrollBy(0, 500)")
            else:
                page.mouse.wheel(0, 500)
            page.wait_for_timeout(400)
        except Exception:
            break


def _extract_reviews_from_page(page: Any) -> list[ReviewText]:
    """Extract visible review elements."""
    reviews: list[ReviewText] = []
    seen_texts: set[str] = set()

    # Review containers — Google Maps uses various structures
    containers = page.query_selector_all(
        'div[data-review-id], div[jsaction*="review"]'
    )
    if not containers:
        # Fallback: look for review text blocks
        containers = page.query_selector_all('span[jsan][role="text"]')
        if not containers:
            containers = page.query_selector_all(
                'div[style*="white-space"] span'
            )

    for container in containers[:100]:
        try:
            text = _extract_review_text(container)
            if not text or len(text) < 10 or text in seen_texts:
                continue
            seen_texts.add(text)

            rating = _parse_star_rating(container)
            reviewer = _extract_reviewer_name(container)
            date_str = _extract_review_date(container)
            language = detect_review_language(text)

            reviews.append(ReviewText(
                text=text,
                language=language,
                rating=rating,
                reviewer_name=reviewer,
                date=date_str,
            ))
        except Exception:
            continue

    return reviews


def _extract_review_text(container: Any) -> str:
    """Extract review text from a container element."""
    # Try expanding truncated reviews first
    try:
        more_btn = container.query_selector('button[aria-label*="more"], button[aria-label*="もっと"]')
        if more_btn:
            more_btn.click()
    except Exception:
        pass

    # Get text content
    try:
        return (container.inner_text() or "").strip()
    except Exception:
        return ""


def _parse_star_rating(container: Any) -> int | None:
    """Extract star rating from a review element."""
    try:
        # Look for aria-label with star info
        star_el = container.query_selector('[aria-label*="star"], [aria-label*="星"]')
        if star_el:
            label = star_el.get_attribute("aria-label") or ""
            match = re.search(r"(\d)", label)
            if match:
                return int(match.group(1))
    except Exception:
        pass
    return None


def _extract_reviewer_name(container: Any) -> str:
    """Extract reviewer name."""
    try:
        # Google shows reviewer as a link/button near the top of each review
        name_el = container.query_selector("a[href*='/contrib/'] span, button span")
        if name_el:
            return (name_el.inner_text() or "").strip()
    except Exception:
        pass
    return ""


def _extract_review_date(container: Any) -> str:
    """Extract review date."""
    try:
        # Date is usually a span with text like "3 months ago", "3ヶ月前"
        spans = container.query_selector_all("span")
        for span in spans:
            text = (span.inner_text() or "").strip()
            if re.match(r"\d+ (year|month|week|day|hour)", text):
                return text
            if re.match(r"\d+(年|ヶ月|週|日|時間)", text):
                return text
    except Exception:
        pass
    return ""


def _extract_total_review_count(page: Any) -> int | None:
    """Extract total number of reviews."""
    try:
        el = page.query_selector('button:has-text("Reviews") span, button:has-text("レビュー") span')
        if el:
            text = (el.inner_text() or "").strip().replace(",", "").replace("件", "")
            match = re.search(r"(\d+)", text)
            if match:
                return int(match.group(1))
    except Exception:
        pass
    return None


def _extract_average_rating(page: Any) -> float | None:
    """Extract average star rating."""
    try:
        el = page.query_selector('[role="img"][aria-label*="star"], [role="img"][aria-label*="星"]')
        if el:
            label = el.get_attribute("aria-label") or ""
            match = re.search(r"([\d.]+)", label)
            if match:
                return float(match.group(1))
    except Exception:
        pass
    return None
