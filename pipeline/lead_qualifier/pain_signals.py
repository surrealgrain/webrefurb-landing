"""Bilingual pain signal detection from Google reviews and website evidence.

Pain signals are keywords and phrases that indicate ordering friction
for non-Japanese speakers: no English menu, ticket machine confusion,
staff language barriers, etc.

Both English and Japanese reviews are scanned. Japanese reviews mentioning
"外国人" or "英語メニューがない" are strong signals because they come from
Japanese customers observing the problem firsthand.

Score formula (0-100):
  HIGH match:  15 pts each (cap 60)
  MEDIUM match: 8 pts each (cap 32)
  LOW match:    3 pts each (cap 12)
  Foreign reviewer bonus: +2/reviewer (cap 10)
  Multi-language bonus: +5 if both EN and JA signals
"""

from __future__ import annotations

import re

from .models import (
    PainSignalAssessment,
    PainSignalMatch,
    ReviewScrapeResult,
)

# ---------------------------------------------------------------------------
# Pain signal keywords
# ---------------------------------------------------------------------------

EN_PAIN_HIGH: tuple[str, ...] = (
    "no english menu",
    "couldn't order",
    "could not order",
    "couldn't read the menu",
    "no english",
    "menu only in japanese",
    "ordering was impossible",
    "staff couldn't speak english",
    "no one spoke english",
    "ticket machine confusing",
    "couldn't use the ticket machine",
    "could not use the ticket machine",
    "pointing at menu",
    "had to use google translate",
    "google translate menu",
    "had to point at things",
    "nobody spoke english",
    "ordering system confusing",
    "couldn't understand the menu",
    "vending machine ordering",
    "only japanese menu",
    "no english speaking",
    "can't read japanese",
    "cannot read japanese",
)

EN_PAIN_MEDIUM: tuple[str, ...] = (
    "ordering was difficult",
    "hard to order",
    "language barrier",
    "menu in japanese only",
    "no english speaking staff",
    "menu is only in japanese",
    "difficult to understand menu",
    "wish there was english",
    "ordering process confusing",
    "couldn't read anything",
    "no english at all",
    "staff don't speak english",
    "very little english",
    "barely any english",
    "menu is all in japanese",
    "machine to order",
    "order from a machine",
    "food ticket machine",
)

EN_PAIN_LOW: tuple[str, ...] = (
    "tourist friendly",
    "foreigner friendly",
    "tourists",
    "english menu would be nice",
    "some english",
    "a bit of english",
    "limited english",
    "not much english",
    "english menu available but",
    "picture menu",
    "picture menu helped",
)

JA_PAIN_HIGH: tuple[str, ...] = (
    "英語のメニューがない",
    "英語メニューがない",
    "注文できない",
    "外国人が困っていた",
    "観光客が注文に困る",
    "券売機 わからない",
    "英語が通じない",
    "外国の方が困っていた",
    "英語の案内がない",
    "メニューが読めない",
    "注文の仕方がわからない",
)

JA_PAIN_MEDIUM: tuple[str, ...] = (
    "外国人",
    "観光客",
    "英語メニュー",
    "外国語対応",
    "英語ができない",
    "観光客対応",
    "外国の方",
    "英語対応",
    "多言語対応",
    "インバウンド",
)

JA_PAIN_LOW: tuple[str, ...] = (
    "英語の案内",
    "多言語",
    "外国人のお客様も",
    "海外からのお客様",
    "グローバル",
)

# Combined for iteration
_ALL_PAIN_KEYWORDS: list[tuple[str, str, str]] = []
for kw in EN_PAIN_HIGH:
    _ALL_PAIN_KEYWORDS.append((kw, "en", "high"))
for kw in EN_PAIN_MEDIUM:
    _ALL_PAIN_KEYWORDS.append((kw, "en", "medium"))
for kw in EN_PAIN_LOW:
    _ALL_PAIN_KEYWORDS.append((kw, "en", "low"))
for kw in JA_PAIN_HIGH:
    _ALL_PAIN_KEYWORDS.append((kw, "ja", "high"))
for kw in JA_PAIN_MEDIUM:
    _ALL_PAIN_KEYWORDS.append((kw, "ja", "medium"))
for kw in JA_PAIN_LOW:
    _ALL_PAIN_KEYWORDS.append((kw, "ja", "low"))


def assess_pain_signals(
    *,
    business_name: str,
    website_text: str = "",
    review_scrape_result: ReviewScrapeResult | None = None,
    evidence_classes: list[str] | None = None,
    english_availability: str = "unknown",
    machine_evidence_found: bool = False,
) -> PainSignalAssessment:
    """Combine website-level and review-level signals into a unified pain assessment."""
    matches: list[PainSignalMatch] = []

    # Review-level signals
    foreign_reviewer_count = 0
    if review_scrape_result and review_scrape_result.reviews:
        review_matches, foreign_count = _analyze_review_pain(review_scrape_result.reviews)
        matches.extend(review_matches)
        foreign_reviewer_count = foreign_count

    # Website text signals (keyword scan on crawled text)
    if website_text:
        website_matches = _analyze_text_pain(website_text, source="website_content")
        matches.extend(website_matches)

    # Evidence-derived signals (from evidence.py outputs, no duplication)
    if evidence_classes or english_availability != "unknown" or machine_evidence_found:
        evidence_matches = _analyze_evidence_pain(
            evidence_classes=evidence_classes or [],
            english_availability=english_availability,
            machine_evidence_found=machine_evidence_found,
        )
        matches.extend(evidence_matches)

    # Deduplicate matches by keyword (keep highest severity)
    matches = _dedupe_matches(matches)

    # Compute score
    pain_score = _compute_pain_score(matches, foreign_reviewer_count)

    # Count severities
    high_count = sum(1 for m in matches if m.severity == "high")
    medium_count = sum(1 for m in matches if m.severity == "medium")
    low_count = sum(1 for m in matches if m.severity == "low")
    en_count = sum(1 for m in matches if m.language == "en")
    ja_count = sum(1 for m in matches if m.language == "ja")

    has_pain = pain_score >= 10
    summary = _build_summary(matches, pain_score, foreign_reviewer_count)

    return PainSignalAssessment(
        has_pain_signals=has_pain,
        pain_score=pain_score,
        matches=matches,
        high_severity_count=high_count,
        medium_severity_count=medium_count,
        low_severity_count=low_count,
        english_pain_count=en_count,
        japanese_pain_count=ja_count,
        foreign_reviewer_count=foreign_reviewer_count,
        summary=summary,
    )


def _analyze_review_pain(
    reviews: list,
) -> tuple[list[PainSignalMatch], int]:
    """Scan review text for pain keywords. Returns matches + foreign reviewer count."""
    matches: list[PainSignalMatch] = []
    foreign_count = 0

    for review in reviews:
        text = (review.text or "").lower()
        if not text:
            continue

        # Check if foreign reviewer
        is_foreign = _is_foreign_reviewer(review.reviewer_name, review.text)
        if is_foreign:
            foreign_count += 1

        # Scan for pain keywords
        for keyword, lang, severity in _ALL_PAIN_KEYWORDS:
            if keyword.lower() in text:
                context = _extract_context(review.text, keyword)
                matches.append(PainSignalMatch(
                    keyword=keyword,
                    language=lang,
                    severity=severity,
                    source="google_review",
                    context=context,
                    review_text=review.text[:300],
                ))

    return matches, foreign_count


def _analyze_text_pain(
    text: str,
    source: str = "website_content",
) -> list[PainSignalMatch]:
    """Scan arbitrary text for pain keywords."""
    matches: list[PainSignalMatch] = []
    lowered = text.lower()

    for keyword, lang, severity in _ALL_PAIN_KEYWORDS:
        if keyword.lower() in lowered:
            context = _extract_context(text, keyword)
            matches.append(PainSignalMatch(
                keyword=keyword,
                language=lang,
                severity=severity,
                source=source,
                context=context,
            ))

    return matches


def _analyze_evidence_pain(
    *,
    evidence_classes: list[str],
    english_availability: str,
    machine_evidence_found: bool,
) -> list[PainSignalMatch]:
    """Derive pain signals from evidence.py outputs without duplicating its logic."""
    matches: list[PainSignalMatch] = []

    # English availability gaps
    if english_availability in ("missing", "hard_to_use", "image_only"):
        label = {
            "missing": "no english menu detected",
            "hard_to_use": "english menu hard to use",
            "image_only": "english menu image-only",
        }.get(english_availability, english_availability)

        matches.append(PainSignalMatch(
            keyword=label,
            language="en",
            severity="high",
            source="website_evidence",
            context=f"english_availability={english_availability}",
        ))

    # Image-locked menus (scanned images, no text)
    if "image_locked_menu" in evidence_classes:
        matches.append(PainSignalMatch(
            keyword="menu image only no selectable text",
            language="en",
            severity="medium",
            source="website_evidence",
            context="evidence_class=image_locked_menu",
        ))

    # Ticket machine without English
    no_english = english_availability in ("missing", "hard_to_use", "image_only", "unknown")
    if machine_evidence_found and no_english:
        matches.append(PainSignalMatch(
            keyword="ticket machine no english support",
            language="en",
            severity="high",
            source="website_evidence",
            context=f"machine_evidence=True, english_availability={english_availability}",
        ))

    return matches


def _is_foreign_reviewer(reviewer_name: str, review_text: str) -> bool:
    """Heuristic: non-Japanese name or non-Japanese review text."""
    name = (reviewer_name or "").strip()
    # Latin characters in name strongly suggest non-Japanese
    if name and re.match(r"^[a-zA-Z\s\-'.]+$", name):
        return True
    # Review text primarily non-Japanese
    if review_text:
        ja_chars = len(re.findall(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]", review_text))
        latin_chars = len(re.findall(r"[a-zA-Z]", review_text))
        total = ja_chars + latin_chars
        if total > 5 and latin_chars / total > 0.7:
            return True
    return False


def _extract_context(text: str, keyword: str, window: int = 80) -> str:
    """Extract surrounding text around a keyword match."""
    lowered = text.lower()
    kw_lower = keyword.lower()
    idx = lowered.find(kw_lower)
    if idx == -1:
        return text[:window * 2]
    start = max(0, idx - window)
    end = min(len(text), idx + len(keyword) + window)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet[:300]


def _compute_pain_score(
    matches: list[PainSignalMatch],
    foreign_reviewer_count: int,
) -> int:
    """Compute 0-100 composite pain score."""
    high_pts = min(sum(15 for m in matches if m.severity == "high"), 60)
    medium_pts = min(sum(8 for m in matches if m.severity == "medium"), 32)
    low_pts = min(sum(3 for m in matches if m.severity == "low"), 12)

    # Foreign reviewer bonus only amplifies existing signals
    if matches:
        foreign_pts = min(foreign_reviewer_count * 2, 10)
    else:
        foreign_pts = 0

    # Multi-language bonus
    has_en = any(m.language == "en" for m in matches)
    has_ja = any(m.language == "ja" for m in matches)
    multi_bonus = 5 if (has_en and has_ja) else 0

    return min(high_pts + medium_pts + low_pts + foreign_pts + multi_bonus, 100)


def _dedupe_matches(matches: list[PainSignalMatch]) -> list[PainSignalMatch]:
    """Deduplicate matches by keyword, keeping highest severity."""
    severity_rank = {"high": 3, "medium": 2, "low": 1}
    best: dict[str, PainSignalMatch] = {}
    for m in matches:
        key = f"{m.keyword}:{m.source}"
        existing = best.get(key)
        if not existing or severity_rank.get(m.severity, 0) > severity_rank.get(existing.severity, 0):
            best[key] = m
    return list(best.values())


def _build_summary(
    matches: list[PainSignalMatch],
    pain_score: int,
    foreign_reviewer_count: int,
) -> str:
    """Build a human-readable summary of pain signals."""
    if not matches:
        return "No ordering friction signals found."
    parts: list[str] = []
    high = [m for m in matches if m.severity == "high"]
    if high:
        parts.append(f"{len(high)} high-severity signal(s): " + ", ".join(m.keyword for m in high[:3]))
    medium = [m for m in matches if m.severity == "medium"]
    if medium:
        parts.append(f"{len(medium)} medium-severity")
    if foreign_reviewer_count:
        parts.append(f"{foreign_reviewer_count} foreign reviewer(s)")
    parts.append(f"pain score: {pain_score}/100")
    return "; ".join(parts)
