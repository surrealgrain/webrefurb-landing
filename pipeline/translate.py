"""Mode B: Japanese to English translation for menu items."""

from __future__ import annotations

import json

from .models import ExtractedItem, TranslatedItem
from .preview import _COMMON_TRANSLATIONS


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

def translate_items(items: list[ExtractedItem]) -> list[TranslatedItem]:
    """Translate extracted items to English.

    Uses deterministic common translations where available,
    falls back to LLM for unknown items.
    """
    # Collect items that need LLM translation
    need_llm: list[tuple[int, ExtractedItem]] = []
    results: list[TranslatedItem | None] = [None] * len(items)

    for i, item in enumerate(items):
        ja_name = item.japanese_name or item.name
        if ja_name in _COMMON_TRANSLATIONS:
            results[i] = TranslatedItem(
                name=_COMMON_TRANSLATIONS[ja_name],
                japanese_name=ja_name,
                price=item.price,
                section=item.section_hint,
            )
        else:
            need_llm.append((i, item))

    # Batch LLM translation for unknown items
    if need_llm:
        llm_results = _llm_translate_batch([item for _, item in need_llm])
        for (orig_idx, orig_item), translated in zip(need_llm, llm_results):
            results[orig_idx] = translated

    # Fill any remaining gaps with romanized fallback
    final: list[TranslatedItem] = []
    for i, item in enumerate(items):
        if results[i] is not None:
            final.append(results[i])
        else:
            ja_name = item.japanese_name or item.name
            final.append(TranslatedItem(
                name=f"[{ja_name}]",
                japanese_name=ja_name,
                price=item.price,
                section=item.section_hint,
            ))

    return final


def translate_section_headers(headers: list[str]) -> dict[str, str]:
    """Map Japanese section headers to English equivalents."""
    # Common header mappings
    common: dict[str, str] = {
        "ラーメン": "RAMEN",
        "らーめん": "RAMEN",
        "中華そば": "RAMEN",
        "つけ麺": "TSUKEMEN",
        "まぜそば": "MAZESOBA",
        "餃子": "GYOZA",
        "サイドメニュー": "SIDE DISHES",
        "サイド": "SIDES",
        "一品料理": "SIDE DISHES",
        "小鉢": "SMALL PLATES",
        "おすすめ": "RECOMMENDED",
        "本日のおすすめ": "TODAY'S SPECIAL",
        "トッピング": "TOPPINGS",
        "ご飯もの": "RICE DISHES",
        "ライス": "RICE",
        "ドリンク": "DRINKS",
        "お飲み物": "DRINKS",
        "ソフトドリンク": "SOFT DRINKS",
        "アルコール": "ALCOHOL",
        "生ビール": "DRAFT BEER",
        "ビール": "BEER",
        "日本酒": "SAKE",
        "焼酎": "SHOCHU",
        "サワー": "SOUR",
        "ハイボール": "HIGHBALL",
        "カクテル": "COCKTAILS",
        "ワイン": "WINE",
        "ソフトクリーム": "SOFT SERVE",
        "デザート": "DESSERT",
        "お子様": "KIDS MENU",
        "セット": "SET MENU",
        "定食": "SET MEALS",
        "揚げ物": "FRIED DISHES",
        "串焼き": "SKEWERS",
        "焼き鳥": "YAKITORI",
        "串": "SKEWERS",
        "〆": "FINISHING DISH",
        "コース": "COURSE",
        "飲み放題": "ALL-YOU-CAN-DRINK",
    }

    result: dict[str, str] = {}
    unknown: list[str] = []

    for h in headers:
        if h in common:
            result[h] = common[h]
        elif h.upper() == h and h.isascii():
            # Already English uppercase
            result[h] = h
        else:
            unknown.append(h)

    # LLM fallback for unknown headers
    if unknown:
        llm_map = _llm_translate_headers(unknown)
        result.update(llm_map)

    return result


def translate_ticket_buttons(buttons: list[str]) -> list[str]:
    """Translate ticket machine button labels to English."""
    results: list[str] = []
    need_llm: list[tuple[int, str]] = []

    for i, btn in enumerate(buttons):
        if btn in _COMMON_TRANSLATIONS:
            results.append(_COMMON_TRANSLATIONS[btn])
        else:
            results.append("")
            need_llm.append((i, btn))

    if need_llm:
        translations = _llm_translate_button_labels([b for _, b in need_llm])
        for (orig_idx, _), translated in zip(need_llm, translations):
            results[orig_idx] = translated

    # Fill gaps with romanized fallback
    return [r or f"[{buttons[i]}]" for i, r in enumerate(results)]


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _llm_translate_batch(items: list[ExtractedItem]) -> list[TranslatedItem]:
    """Translate a batch of unknown items via LLM."""
    from .llm_client import call_llm
    import os

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return [_make_romanized_fallback(item) for item in items]

    items_text = "\n".join(
        f"- {item.japanese_name or item.name}"
        for item in items
    )

    try:
        response = call_llm(
            model="google/gemini-2.0-flash-001",
            system=(
                "You are a Japanese-to-English menu translator for ramen and izakaya restaurants. "
                "Translate each Japanese dish name to natural English using standard romanization "
                "and conventional English naming for Japanese dishes. "
                "Return a JSON array of objects with keys: name (English), japanese_name (original). "
                "Return only the JSON array, no other text."
            ),
            user=f"Translate these menu items to English:\n{items_text}",
            api_key=api_key,
            max_tokens=2048,
        )
        parsed = json.loads(response)
        results: list[TranslatedItem] = []
        for entry, item in zip(parsed, items):
            if isinstance(entry, dict) and "name" in entry:
                results.append(TranslatedItem(
                    name=entry["name"],
                    japanese_name=entry.get("japanese_name", item.japanese_name or item.name),
                    price=item.price,
                    section=item.section_hint,
                ))
            else:
                results.append(_make_romanized_fallback(item))
        return results
    except Exception:
        return [_make_romanized_fallback(item) for item in items]


def _llm_translate_headers(headers: list[str]) -> dict[str, str]:
    """Translate section headers via LLM."""
    from .llm_client import call_llm
    import os

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return {h: h.upper() for h in headers}

    try:
        response = call_llm(
            model="google/gemini-2.0-flash-001",
            system=(
                "Translate Japanese restaurant menu section headers to short English uppercase labels. "
                "Return a JSON object mapping each Japanese header to its English translation. "
                "Return only the JSON object."
            ),
            user="\n".join(headers),
            api_key=api_key,
            max_tokens=512,
        )
        return json.loads(response)
    except Exception:
        return {h: h.upper() for h in headers}


def _llm_translate_button_labels(buttons: list[str]) -> list[str]:
    """Translate ticket machine button labels via LLM."""
    from .llm_client import call_llm
    import os

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return [f"[{b}]" for b in buttons]

    try:
        response = call_llm(
            model="google/gemini-2.0-flash-001",
            system=(
                "Translate Japanese ticket machine button labels to short English names. "
                "Return a JSON array of English strings in the same order. "
                "Return only the JSON array."
            ),
            user="\n".join(buttons),
            api_key=api_key,
            max_tokens=512,
        )
        parsed = json.loads(response)
        if isinstance(parsed, list):
            return [str(s) for s in parsed]
        return [f"[{b}]" for b in buttons]
    except Exception:
        return [f"[{b}]" for b in buttons]


def _make_romanized_fallback(item: ExtractedItem) -> TranslatedItem:
    """Create a romanized fallback translation."""
    ja = item.japanese_name or item.name
    return TranslatedItem(
        name=f"[{ja}]",
        japanese_name=ja,
        price=item.price,
        section=item.section_hint,
    )
