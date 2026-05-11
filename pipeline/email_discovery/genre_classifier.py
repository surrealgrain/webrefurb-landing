"""Genre classification for Japanese restaurants.

Determines if a restaurant fits our target genres:
  - Ramen (ラーメン, 中華そば, etc.)
  - Izakaya (居酒屋) and approved adjacent formats

Adjacent formats (allowed only if clearly relevant):
  kushikatsu, motsuyaki
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Genre definitions
# ---------------------------------------------------------------------------

# Core genres — always approved
CORE_GENRES = {
    "ramen": {
        "terms": ["ラーメン", "らーめん", "中華そば", "中華麺", "拉麺", "担々麺", "つけ麺",
                   "油そば", "まぜ麺", "ramen"],
        "confidence": 1.0,
    },
    "izakaya": {
        "terms": ["居酒屋", "大衆酒場", "大衆割烹", "izakaya", "Japanese pub",
                   "和食酒場", "酒処", "酒場"],
        "confidence": 1.0,
    },
}

# Adjacent genres — approved if clearly relevant
ADJACENT_GENRES = {
    "kushikatsu": {
        "terms": ["串カツ", "串揚げ", "くしカツ", "kushikatsu"],
        "confidence": 0.80,
    },
    "motsuyaki": {
        "terms": ["もつ焼き", "もつ焼", "ホルモン焼き", "motsuyaki", "motsu"],
        "confidence": 0.80,
    },
}

# Excluded genres — clearly not our target
EXCLUDED_TERMS = [
    "寿司", "sushi", "イタリアン", "italian", "フレンチ", "french",
    "カレー", "curry", "ハンバーガー", "burger", "中華料理", "中国料理",
    "韓国料理", "korean", "インド", "indian", "タイ料理", "thai",
    "パン", "ベーカリー", "bakery", "喫茶", "カフェ", "cafe",
    "美容室", "理容", "ホテル", "hotel", "クリーニング",
    "そば", "soba", "蕎麦",
]


@dataclass
class GenreResult:
    genre: str = ""
    category: str = ""  # "core", "adjacent", "excluded", "unknown"
    confidence: float = 0.0
    matched_terms: list[str] = None
    is_approved: bool = False

    def __post_init__(self):
        if self.matched_terms is None:
            self.matched_terms = []


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return text.lower().strip()


def classify_genre(
    genre_text: str = "",
    shop_name: str = "",
    description: str = "",
    extra_context: str = "",
) -> GenreResult:
    """Classify a restaurant's genre.

    Checks genre label, shop name, and any extra context for genre signals.
    """
    combined = " ".join(filter(None, [genre_text, shop_name, description, extra_context]))
    combined_lower = _normalize(combined)

    if not combined_lower:
        return GenreResult(category="unknown", confidence=0.0)

    # Check excluded first
    for term in EXCLUDED_TERMS:
        if _normalize(term) in combined_lower:
            return GenreResult(
                category="excluded",
                confidence=0.9,
                matched_terms=[term],
                is_approved=False,
            )

    # Check core genres
    for genre_key, genre_def in CORE_GENRES.items():
        matches = [t for t in genre_def["terms"] if _normalize(t) in combined_lower]
        if matches:
            return GenreResult(
                genre=genre_key,
                category="core",
                confidence=genre_def["confidence"],
                matched_terms=matches,
                is_approved=True,
            )

    # Check adjacent genres
    for genre_key, genre_def in ADJACENT_GENRES.items():
        matches = [t for t in genre_def["terms"] if _normalize(t) in combined_lower]
        if matches:
            return GenreResult(
                genre=genre_key,
                category="adjacent",
                confidence=genre_def["confidence"],
                matched_terms=matches,
                is_approved=True,
            )

    return GenreResult(category="unknown", confidence=0.0, is_approved=False)
