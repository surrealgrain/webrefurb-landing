"""QR menu detection: check restaurant websites and reviews for existing
QR code / digital ordering systems.

Two detection methods:
1. Website scan via Firecrawl — scrapes the restaurant's own site for QR
   ordering text, platform embeds, and ordering links.
2. Review scan via search — queries for review mentions of QR/digital ordering.

Used during lead verification to flag restaurants that already have QR menus
(don't need our product) or tech-forward restaurants lacking English
(prime targets).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# QR menu indicators found on restaurant websites
# ---------------------------------------------------------------------------

# Japanese text patterns that strongly indicate QR/digital ordering
_QR_TEXT_PATTERNS: tuple[re.Pattern, ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"QRコード.{0,15}(注文|オーダー|ご注文)",
        r"QR.{0,5}メニュー",
        r"QRコード.{0,10}メニュー",
        r"二次元コード.{0,15}(注文|メニュー)",
        r"スマホ.{0,10}(注文|オーダー)",
        r"スマートフォン.{0,10}(注文|オーダー)",
        r"モバイルオーダー",
        r"セルフオーダー",
        r"スキャン.{0,10}(注文|オーダー)",
        r"オンライン注文",
        r"オンラインオーダー",
        r"テーブル.{0,10}(注文|オーダー)",
        r"タブレット.{0,10}(注文|オーダー)",
    )
)

# Ordering platform domains (Japan-focused)
_QR_PLATFORM_DOMAINS: tuple[str, ...] = (
    "o-ordering.com",
    "o-der.com",
    "ordering.com",
    "ub.ee",
    "air-wallet.com",
    "airwallet",
    "synchro-food.jp",
    "food-lineup.com",
    "menu.jp",
    "qrmenu.jp",
    "qr-menu",
    "dot-order.com",
    "dotorder",
    "selforder",
    "mobileorder",
    "tableorder",
    "pocapocha",
    "pokekara",
    "fanbeats",
    "toratora-order",
    "epark",
    "skippa",
    "okinii",
    "ugoku",
)

# English-language QR ordering terms
_QR_EN_TERMS: tuple[str, ...] = (
    "qr menu",
    "qr order",
    "scan to order",
    "scan the qr",
    "mobile ordering",
    "digital menu",
    "online ordering",
    "self-order",
    "self order",
    "tablet ordering",
)


# ---------------------------------------------------------------------------
# QR mention patterns for review/search scanning
# ---------------------------------------------------------------------------

_QR_REVIEW_PATTERNS: tuple[re.Pattern, ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"QR.{0,5}(注文|オーダー|メニュー)",
        r"QRコードで(注文|注文|オーダー)",
        r"スマホで(注文|オーダー)",
        r"モバイルオーダー",
        r"セルフオーダー",
        r"タブレットで(注文|オーダー)",
        r"スキャンして(注文|オーダー)",
        r"qr menu",
        r"scan.{0,10}order",
        r"qr order",
        r"mobile order",
        r"tablet order",
    )
)


@dataclass
class QRMenuDetection:
    """Result of QR menu detection checks."""
    detected: bool = False
    confidence: str = ""  # "high" | "medium" | "low"
    source: str = ""      # "website" | "reviews" | "tabelog"
    evidence: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 1. Website scan via Firecrawl
# ---------------------------------------------------------------------------

def detect_qr_menu_from_website(url: str, *, timeout: int = 20) -> QRMenuDetection:
    """Scrape a restaurant website via Firecrawl and check for QR ordering.

    Looks for:
    - QR ordering text in the page content
    - Links/embeds from known QR ordering platforms
    - QR-related English terms
    """
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        return QRMenuDetection(detected=False, confidence="", source="website", evidence=["no FIRECRAWL_API_KEY"])

    try:
        payload = json.dumps({"url": url}).encode("utf-8")
        req = urllib.request.Request(
            "https://api.firecrawl.dev/v2/scrape",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError, Exception) as exc:
        return QRMenuDetection(detected=False, confidence="", source="website", evidence=[f"scrape failed: {exc}"])

    markdown = str(data.get("data", {}).get("markdown", "") or "")
    links_html = str(data.get("data", {}).get("links") or [])
    raw_html = str(data.get("data", {}).get("html", "") or "")
    combined = f"{markdown}\n{links_html}\n{raw_html}"

    if not markdown and not raw_html:
        return QRMenuDetection(detected=False, confidence="", source="website", evidence=["empty scrape"])

    evidence: list[str] = []
    confidence = "low"

    # Check Japanese text patterns
    for pat in _QR_TEXT_PATTERNS:
        m = pat.search(combined)
        if m:
            evidence.append(f"text match: {m.group()[:80]}")
            confidence = "high"

    # Check for ordering platform domains
    combined_lower = combined.lower()
    for domain in _QR_PLATFORM_DOMAINS:
        if domain in combined_lower:
            evidence.append(f"platform: {domain}")
            confidence = "high"

    # Check for QR code images in HTML
    qr_img = re.search(r'<img[^>]*(?:qr|QR)[^>]*>', raw_html, re.IGNORECASE)
    if qr_img:
        evidence.append("qr image tag found")
        confidence = max(confidence, "medium", key=["low", "medium", "high"].index)

    # Check English terms
    for term in _QR_EN_TERMS:
        if term in combined_lower:
            evidence.append(f"en term: {term}")
            if confidence != "high":
                confidence = "medium"

    return QRMenuDetection(
        detected=len(evidence) > 0,
        confidence=confidence,
        source="website",
        evidence=evidence[:5],
    )


# ---------------------------------------------------------------------------
# 2. Review scan via Serper.dev
# ---------------------------------------------------------------------------

def detect_qr_from_reviews(
    business_name: str,
    *,
    city: str = "",
    api_key: str = "",
    timeout: int = 10,
) -> QRMenuDetection:
    """Search for review mentions of QR/digital ordering at a restaurant.

    Uses Serper.dev organic search to find reviews mentioning QR ordering.
    """
    api_key = api_key or os.environ.get("SERPER_API_KEY", "")
    if not api_key:
        return QRMenuDetection(detected=False, confidence="", source="reviews", evidence=["no SERPER_API_KEY"])

    city_part = f" {city}" if city else ""
    queries = [
        f'"{business_name}" QR 注文{city_part} 口コミ',
        f'"{business_name}" スマホ 注文{city_part} レビュー',
    ]

    evidence: list[str] = []
    for query in queries:
        try:
            payload = json.dumps({"q": query, "gl": "jp", "hl": "ja"}).encode("utf-8")
            req = urllib.request.Request(
                "https://google.serper.dev/search",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-API-KEY": api_key,
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue

        for result in data.get("organic", []):
            text = " ".join([
                str(result.get("title", "")),
                str(result.get("snippet", "")),
            ])
            for pat in _QR_REVIEW_PATTERNS:
                m = pat.search(text)
                if m:
                    evidence.append(f"review: {m.group()[:60]} in '{result.get('title', '')[:40]}'")
                    break  # one match per result is enough

    return QRMenuDetection(
        detected=len(evidence) > 0,
        confidence="medium" if evidence else "",
        source="reviews",
        evidence=evidence[:5],
    )


# ---------------------------------------------------------------------------
# 3. Text-only check (for already-fetched content)
# ---------------------------------------------------------------------------

def has_qr_menu_signals(text: str) -> bool:
    """Quick check: does the given text contain QR menu indicators?

    Useful for scanning already-fetched page content, search snippets,
    or Tabelog page HTML without making additional network requests.
    """
    if not text:
        return False
    for pat in _QR_TEXT_PATTERNS:
        if pat.search(text):
            return True
    lowered = text.lower()
    for term in _QR_EN_TERMS:
        if term in lowered:
            return True
    for domain in _QR_PLATFORM_DOMAINS:
        if domain in lowered:
            return True
    return False
