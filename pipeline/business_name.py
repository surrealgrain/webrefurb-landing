from __future__ import annotations

import re


EMAIL_RE = re.compile(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
TITLE_RE = re.compile(r"(?is)<title[^>]*>(.*?)</title>")
H1_RE = re.compile(r"(?is)<h1[^>]*>(.*?)</h1>")
OG_SITE_NAME_RE = re.compile(
    r"""(?is)<meta[^>]+property=["']og:site_name["'][^>]+content=["']([^"']+)["']|<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:site_name["']"""
)
TAG_RE = re.compile(r"(?is)<[^>]+>")
SPACE_RE = re.compile(r"\s+")
LATIN_CONTACT_ROUTE_RE = re.compile(
    r"""(?ix)
    \b(
        email|
        e-mail|
        phone|
        telephone|
        tel|
        contact\s*form|
        contact|
        form|
        line|
        instagram|
        walk[\s-]*in|
        manual
    )\b
    """
)
BUSINESS_CATEGORY_RE = re.compile(r"(?i)\b(ramen|izakaya|restaurant|shop)\b")

SUSPICIOUS_NAME_TOKENS = (
    "contact form",
    "email route",
    "website only",
    "primary route",
    "contact route",
    "mailto:",
    "owner@",
    "noreply@",
    "no-reply@",
    "walk-in route",
    "manual outreach",
)

TITLE_SPLIT_TOKENS = ("|", "｜", " - ", " – ", " — ", " / ")
GENERIC_TITLE_SEGMENTS = (
    "official site",
    "official website",
    "公式サイト",
    "ホームページ",
    "お問い合わせ",
    "contact",
    "menu",
    "メニュー",
    "食べログ",
    "tabelog",
    "instagram",
    "facebook",
)


def normalise_business_name(value: str) -> str:
    cleaned = TAG_RE.sub(" ", str(value or ""))
    cleaned = SPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def business_name_key(value: str) -> str:
    cleaned = normalise_business_name(value).lower()
    for token in GENERIC_TITLE_SEGMENTS:
        cleaned = cleaned.replace(token, " ")
    cleaned = re.sub(r"[\s\-\|｜/–—()（）・.,'\"`]+", "", cleaned)
    return cleaned


def business_name_is_suspicious(value: str) -> bool:
    cleaned = normalise_business_name(value)
    lowered = cleaned.lower()
    if not cleaned or len(cleaned) > 80:
        return True
    if "@" in cleaned or EMAIL_RE.search(cleaned):
        return True
    if cleaned.startswith(("http://", "https://", "www.")):
        return True
    if LATIN_CONTACT_ROUTE_RE.search(lowered) and BUSINESS_CATEGORY_RE.search(lowered):
        return True
    return any(token in lowered for token in SUSPICIOUS_NAME_TOKENS)


def business_names_match(left: str, right: str) -> bool:
    left_key = business_name_key(left)
    right_key = business_name_key(right)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    shorter, longer = sorted((left_key, right_key), key=len)
    return len(shorter) >= 4 and shorter in longer


def extract_business_name_candidates(html: str) -> list[str]:
    source = html or ""
    candidates: list[str] = []

    og_match = OG_SITE_NAME_RE.search(source)
    if og_match:
        og_text = normalise_business_name(og_match.group(1) or og_match.group(2) or "")
        if og_text:
            candidates.append(og_text)

    h1_match = H1_RE.search(source)
    if h1_match:
        h1_text = normalise_business_name(h1_match.group(1))
        if h1_text:
            candidates.append(h1_text)

    title_match = TITLE_RE.search(source)
    if title_match:
        title_text = normalise_business_name(title_match.group(1))
        if title_text:
            candidates.extend(_split_title_segments(title_text))

    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        key = candidate.lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def resolve_business_name(*, source_name: str, html: str) -> tuple[str, str]:
    source_candidate = normalise_business_name(source_name)
    if source_candidate and not business_name_is_suspicious(source_candidate):
        return source_candidate, "source_name"

    for candidate in extract_business_name_candidates(html):
        if not business_name_is_suspicious(candidate):
            return candidate, "page_html"

    return source_candidate, "untrusted_source_name"


def _split_title_segments(title_text: str) -> list[str]:
    parts = [title_text]
    for token in TITLE_SPLIT_TOKENS:
        next_parts: list[str] = []
        for part in parts:
            split = [segment.strip() for segment in part.split(token) if segment.strip()]
            next_parts.extend(split or [part])
        parts = next_parts

    scored = sorted(parts, key=_title_segment_score, reverse=True)
    return scored


def _title_segment_score(segment: str) -> tuple[int, int]:
    lowered = segment.lower()
    penalty = sum(1 for token in GENERIC_TITLE_SEGMENTS if token in lowered)
    japanese_bonus = 1 if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", segment) else 0
    return (japanese_bonus - penalty, -abs(len(segment) - 12))
