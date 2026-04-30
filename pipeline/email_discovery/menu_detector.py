"""Detect menu presence and relevance for ramen/izakaya shops.

Detects whether the restaurant has a visible menu, which is critical
for our English menu translation service.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Detection terms
# ---------------------------------------------------------------------------

# General menu indicators
MENU_TERMS = [
    "メニュー", "お品書き", "フード", "ドリンク", "料理",
    "menu", "food", "drink", "品書き",
]

# URL patterns suggesting menu pages
MENU_URL_PATTERNS = [
    r"menu", r"メニュー", r"food", r"drink",
    r"品書き", r"course", r"コース",
]

# Ramen-specific menu terms
RAMEN_TERMS = [
    "醤油", "味噌", "塩", "豚骨", "つけ麺", "替玉",
    "チャーシュー", "煮卵", "背脂", "煮干し", "鶏白湯",
    "担々麺", "油そば", "まぜ麺", "味玉", "ネギ",
    "もやし", "キャベツ", "ニンニク", "高菜",
]

# Izakaya-specific menu terms
IZAKAYA_TERMS = [
    "焼鳥", "唐揚げ", "枝豆", "刺身", "日本酒", "焼酎",
    "生ビール", "飲み放題", "コース", "お通し", "サラダ",
    "天ぷら", "餃子", "冷奴", "出汁巻き", "肉じゃが",
    "アジフライ", "ポテトフライ", "ハイボール",
]

# Ticket machine / 食券 terms
TICKET_MACHINE_TERMS = [
    "食券", "券売機", "チケット", "販売機",
]

# PDF menu indicators
PDF_MENU_PATTERN = re.compile(r'\.pdf["\']?', re.IGNORECASE)

# Menu image indicators
IMAGE_MENU_PATTERN = re.compile(
    r'<img[^>]+(?:menu|メニュー|品書き)[^>]*>',
    re.IGNORECASE,
)


@dataclass
class MenuDetection:
    has_menu: bool = False
    menu_url: str = ""
    menu_type: str = ""  # "page", "pdf", "image", "ticket_machine"
    has_ramen_terms: bool = False
    has_izakaya_terms: bool = False
    has_ticket_machine: bool = False
    matched_terms: list[str] = None
    confidence: float = 0.0

    def __post_init__(self):
        if self.matched_terms is None:
            self.matched_terms = []


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_menu_url(urls: list[str]) -> list[str]:
    """Filter URLs that look like menu pages."""
    menu_urls = []
    for url in urls:
        url_lower = url.lower()
        if any(re.search(p, url_lower) for p in MENU_URL_PATTERNS):
            menu_urls.append(url)
    return menu_urls


def detect_menu_in_text(text: str) -> MenuDetection:
    """Detect menu presence from page text.

    Looks for menu terms, ramen/izakaya-specific items, and ticket machine terms.
    """
    if not text:
        return MenuDetection()

    text_lower = text.lower()

    # Check general menu terms
    matched_menu = [t for t in MENU_TERMS if t.lower() in text_lower]

    # Check ramen terms
    matched_ramen = [t for t in RAMEN_TERMS if t in text]

    # Check izakaya terms
    matched_izakaya = [t for t in IZAKAYA_TERMS if t in text]

    # Check ticket machine
    matched_ticket = [t for t in TICKET_MACHINE_TERMS if t in text]

    has_menu = bool(matched_menu)
    has_ramen = bool(matched_ramen)
    has_izakaya = bool(matched_izakaya)
    has_ticket = bool(matched_ticket)

    # Confidence based on number of matches
    total_matches = len(matched_menu) + len(matched_ramen) + len(matched_izakaya)
    confidence = min(total_matches / 10.0, 1.0)  # 10+ matches = 100%

    return MenuDetection(
        has_menu=has_menu,
        menu_type="ticket_machine" if has_ticket else ("page" if has_menu else ""),
        has_ramen_terms=has_ramen,
        has_izakaya_terms=has_izakaya,
        has_ticket_machine=has_ticket,
        matched_terms=matched_menu + matched_ramen + matched_izakaya,
        confidence=confidence,
    )


def detect_menu_in_html(html: str, text: str = "") -> MenuDetection:
    """Detect menu from HTML content.

    Checks for PDF links, menu images, and text content.
    """
    result = detect_menu_in_text(text or "")

    # Check for PDF menu links
    if PDF_MENU_PATTERN.search(html):
        result.has_menu = True
        result.menu_type = "pdf"
        result.confidence = max(result.confidence, 0.6)

    # Check for menu images
    if IMAGE_MENU_PATTERN.search(html):
        result.has_menu = True
        if not result.menu_type:
            result.menu_type = "image"
        result.confidence = max(result.confidence, 0.5)

    return result
