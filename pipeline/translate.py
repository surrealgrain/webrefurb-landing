"""Mode B: Japanese to English translation for menu items.

Deterministic map covers high-frequency items. LLM fallback handles the
rest with output validation to prevent bad translations from reaching
customers.
"""

from __future__ import annotations

import json
import logging

from .models import ExtractedItem, TranslatedItem


logger = logging.getLogger("webrefurb.translate")


# ---------------------------------------------------------------------------
# Deterministic translation map (production)
# ---------------------------------------------------------------------------
# Covers items that appear on the vast majority of ramen and izakaya menus.
# LLM fallback is only for specialty / regional items.
# preview.py keeps its own smaller _COMMON_TRANSLATIONS for preview HTML.

TRANSLATION_MAP: dict[str, str] = {
    # --- Ramen basics ---
    "ラーメン": "Ramen",
    "らーめん": "Ramen",
    "中華そば": "Chuka Soba",
    "醤油ラーメン": "Shoyu Ramen",
    "味噌ラーメン": "Miso Ramen",
    "塩ラーメン": "Shio Ramen",
    "豚骨ラーメン": "Tonkotsu Ramen",
    "鶏白湯ラーメン": "Tori Paitan Ramen",
    "背脂醤油ラーメン": "Back-Fat Shoyu Ramen",
    "煮干しラーメン": "Niboshi Ramen",
    "家系ラーメン": "Iekei Ramen",
    "二郎系": "Jiro-Style Ramen",
    "味噌バターコーン": "Miso Butter Corn Ramen",
    "辛味噌ラーメン": "Spicy Miso Ramen",
    "担々麺": "Tan Tan Men",
    "台湾ラーメン": "Taiwan Ramen",
    "冷やし中華": "Hiyashi Chuka (Cold Noodles)",
    "冷ラー": "Cold Ramen",
    "つけ麺": "Tsukemen",
    "まぜそば": "Mazesoba",
    "油そば": "Abura Soba",
    # --- Ramen with toppings ---
    "味玉ラーメン": "Ajitama Ramen (Marinated Egg)",
    "チャーシューメン": "Chashu Ramen",
    "ワンタンメン": "Wonton Ramen",
    "タンメン": "Tanmen (Vegetable Noodle Soup)",
    "全部入り": "Everything In",
    "特製": "Special",
    # --- Sizes / portions ---
    "大盛": "Large",
    "大盛り": "Large",
    "小盛": "Small",
    "半ラーメン": "Half Ramen",
    "替玉": "Extra Noodles (Kaedama)",
    "麺大盛": "Large Noodles",
    # --- Common toppings ---
    "チャーシュー": "Chashu Pork",
    "味玉": "Marinated Egg (Ajitama)",
    "味付け玉子": "Marinated Egg (Ajitama)",
    "メンマ": "Bamboo Shoots",
    "ネギ": "Green Onion",
    "もやし": "Bean Sprouts",
    "のり": "Seaweed (Nori)",
    "にんにく": "Garlic",
    "生卵": "Raw Egg",
    "ゆで卵": "Boiled Egg",
    "バター": "Butter",
    "コーン": "Corn",
    "チーズ": "Cheese",
    "キムチ": "Kimchi",
    "高菜": "Takana (Pickled Mustard Leaf)",
    "紅生姜": "Pickled Ginger",
    "トッピング": "Toppings",
    # --- Sides ---
    "餃子": "Gyoza Dumplings",
    "唐揚げ": "Japanese Fried Chicken",
    "チャーハン": "Fried Rice",
    "半チャーハン": "Half Fried Rice",
    "ご飯": "Rice",
    "ライス": "Rice",
    "白飯": "Rice",
    "枝豆": "Edamame",
    "たこ焼き": "Takoyaki",
    "出し巻き玉子": "Dashimaki Tamago (Rolled Omelette)",
    "ポテトフライ": "French Fries",
    "明太子": "Mentaiko (Spicy Cod Roe)",
    "冷奴": "Hiyayakko (Cold Tofu)",
    "サラダ": "Salad",
    "ポテト": "Potato Fries",
    "ソフトクリーム": "Soft Serve",
    "アイス": "Ice Cream",
    # --- Yakitori / skewers ---
    "焼き鳥": "Yakitori (Grilled Chicken)",
    "串焼き": "Kushiyaki (Grilled Skewers)",
    "串": "Skewers",
    # --- Izakaya mains ---
    "刺身": "Sashimi",
    "揚げ物": "Fried Dishes",
    "一品料理": "Side Dishes",
    "お通し": "Otoshi (Seating Charge)",
    # --- Beer ---
    "生ビール": "Draft Beer",
    "ビール": "Beer",
    "中ジョッキ": "Medium Draft Beer",
    "小ジョッキ": "Small Draft Beer",
    "メガビール": "Mega Beer",
    # --- Highball / whisky ---
    "ハイボール": "Highball",
    "角ハイボール": "Kaku Highball",
    "メガハイボール": "Mega Highball",
    "ジンジャーハイボール": "Ginger Highball",
    "コーラハイボール": "Cola Highball",
    # --- Sour ---
    "サワー": "Sour",
    "レモンサワー": "Lemon Sour",
    "グレープフルーツサワー": "Grapefruit Sour",
    "ウーロンハイ": "Oolong High",
    "緑茶ハイ": "Green Tea High",
    # --- Sake / shochu ---
    "日本酒": "Sake",
    "焼酎": "Shochu",
    "梅酒": "Umeshu (Plum Wine)",
    # --- Other drinks ---
    "ワイン": "Wine",
    "カクテル": "Cocktails",
    "ウーロン茶": "Oolong Tea",
    "緑茶": "Green Tea",
    "コーラ": "Cola",
    "ジンジャーエール": "Ginger Ale",
    "ノンアルコール": "Non-Alcoholic",
    "ノンアル": "Non-Alcoholic",
    "お茶": "Tea",
    "水": "Water",
    # --- Plans / courses ---
    "飲み放題": "All-You-Can-Drink",
    "食べ放題": "All-You-Can-Eat",
    "コース": "Course Menu",
    "宴会": "Banquet Course",
    "セット": "Set Menu",
    "定食": "Set Meals",
    "お子様": "Kids Menu",
    "デザート": "Dessert",
    # --- Modifiers ---
    "辛め": "Extra Spicy",
    "辛さ調整可": "Spice Level Adjustable",
    "あっさり": "Light Broth",
    "こってり": "Rich Broth",
    # --- Headers used as items ---
    "おすすめ": "Recommended",
    "本日のおすすめ": "Today's Special",
}

# Backward-compatible alias — preview.py still uses its own _COMMON_TRANSLATIONS
_COMMON_TRANSLATIONS = TRANSLATION_MAP


# ---------------------------------------------------------------------------
# LLM model and glossary
# ---------------------------------------------------------------------------
LLM_MODEL = "google/gemini-2.5-flash-preview-05-20"

_GLOSSARY = (
    "醤油=Shoyu, 味噌=Miso, 塩=Shio, 豚骨=Tonkotsu, "
    "チャーシュー=Chashu Pork, 味玉=Marinated Egg (Ajitama), "
    "替玉=Extra Noodles (Kaedama), 餃子=Gyoza, "
    "唐揚げ=Japanese Fried Chicken, "
    "大盛=Large, 小盛=Small, "
    "飲み放題=All-You-Can-Drink, つけ麺=Tsukemen, まぜそば=Mazesoba, "
    "油そば=Abura Soba, 焼き鳥=Yakitori (Grilled Chicken), "
    "刺身=Sashimi, ハイボール=Highball, 日本酒=Sake, 焼酎=Shochu."
)


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
        if ja_name in TRANSLATION_MAP:
            results[i] = TranslatedItem(
                name=TRANSLATION_MAP[ja_name],
                japanese_name=ja_name,
                price=item.price,
                section=item.section_hint,
                source_text=item.source_text or ja_name,
                source_provenance=item.source_provenance,
                approval_status=item.approval_status,
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
                source_text=item.source_text or ja_name,
                source_provenance=item.source_provenance,
                approval_status=item.approval_status,
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
        "限定": "LIMITED TIME",
        "夏季限定": "SUMMER LIMITED",
        "冬季限定": "WINTER LIMITED",
        "お通し": "OTOSHI (SEATING CHARGE)",
        "ドリンクバー": "DRINK BAR",
        "一品": "SIDES",
        "単品": "SINGLE ITEMS",
        "麺類": "NOODLES",
        "麺": "NOODLES",
        "ごはん": "RICE",
        "白飯": "RICE",
        "油そば": "ABURA SOBA",
        "おつまみ": "SNACKS",
        "肉料理": "MEAT DISHES",
        "魚料理": "FISH DISHES",
        "野菜料理": "VEGETABLE DISHES",
        "たこ焼き": "TAKOYAKI",
        "サラダ": "SALAD",
        "スープ": "SOUP",
        "梅酒": "PLUM WINE",
        "サワー": "SOUR",
        "カクテル": "COCKTAILS",
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
        if btn in TRANSLATION_MAP:
            results.append(TRANSLATION_MAP[btn])
        else:
            results.append("")
            need_llm.append((i, btn))

    if need_llm:
        translations = _llm_translate_button_labels([b for _, b in need_llm])
        for (orig_idx, _), translated in zip(need_llm, translations):
            results[orig_idx] = translated

    # Fill gaps with romanized fallback
    return [r or f"[{buttons[i]}]" for i, r in enumerate(results)]


def has_unresolved_translations(items: list[TranslatedItem]) -> list[str]:
    """Return Japanese names of items with unresolved bracket fallbacks.

    Used as a quality gate before export — any bracket translations
    indicate items that need operator review.
    """
    unresolved: list[str] = []
    for item in items:
        if item.name.startswith("[") and item.name.endswith("]"):
            unresolved.append(item.japanese_name or item.name)
    return unresolved


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _llm_translate_batch(items: list[ExtractedItem]) -> list[TranslatedItem]:
    """Translate a batch of unknown items via LLM.

    Validates output count matches input to prevent silent data loss.
    """
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
            model=LLM_MODEL,
            system=(
                "You are a Japanese-to-English menu translator for ramen and izakaya restaurants. "
                "Translate each Japanese dish name to literal, accurate English. "
                "Use standard romanization and conventional English naming for Japanese dishes. "
                "Do NOT add words like 'delicious', 'savory', 'premium', or 'special'. "
                "Translate literally — if the Japanese says 'shrimp', the English must say 'shrimp'. "
                "Keep the same number of items in the same order. "
                f"Use these exact translations for known terms: {_GLOSSARY} "
                "Return a JSON array of objects with keys: name (English), japanese_name (original Japanese). "
                "Return only the JSON array, no other text."
            ),
            user=f"Translate these {len(items)} menu items to English:\n{items_text}",
            api_key=api_key,
            max_tokens=2048,
        )
        parsed = json.loads(response)

        # --- Output validation ---
        if not isinstance(parsed, list):
            logger.warning("LLM returned non-array for item translation, falling back")
            return [_make_romanized_fallback(item) for item in items]

        if len(parsed) != len(items):
            logger.warning(
                "LLM item count mismatch: sent %d, got %d — filling gaps",
                len(items), len(parsed),
            )

        results: list[TranslatedItem] = []
        for i, item in enumerate(items):
            if i < len(parsed) and isinstance(parsed[i], dict) and "name" in parsed[i]:
                entry = parsed[i]
                en_name = str(entry["name"]).strip()
                llm_ja = str(entry.get("japanese_name", "")).strip()
                orig_ja = item.japanese_name or item.name
                if llm_ja and llm_ja != orig_ja:
                    logger.warning(
                        "LLM round-trip mismatch: sent '%s', got japanese_name '%s'",
                        orig_ja, llm_ja,
                    )
                results.append(TranslatedItem(
                    name=en_name,
                    japanese_name=llm_ja or orig_ja,
                    price=item.price,
                    section=item.section_hint,
                    source_text=item.source_text or orig_ja,
                    source_provenance=item.source_provenance,
                    approval_status=item.approval_status,
                ))
            else:
                results.append(_make_romanized_fallback(item))
        return results
    except Exception as exc:
        logger.warning("LLM item translation failed: %s", exc)
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
            model=LLM_MODEL,
            system=(
                "Translate Japanese restaurant menu section headers to short English UPPERCASE labels. "
                "Be literal. Do not add words like 'OUR' or 'SPECIAL'. "
                f"Use these translations for known terms: {_GLOSSARY} "
                "Return a JSON object mapping each Japanese header to its English translation. "
                "Return only the JSON object."
            ),
            user="\n".join(headers),
            api_key=api_key,
            max_tokens=512,
        )
        result = json.loads(response)
        if not isinstance(result, dict):
            return {h: h.upper() for h in headers}
        return result
    except Exception as exc:
        logger.warning("LLM header translation failed: %s", exc)
        return {h: h.upper() for h in headers}


def _llm_translate_button_labels(buttons: list[str]) -> list[str]:
    """Translate ticket machine button labels via LLM.

    Button labels must be short, literal, and clear. The tourist needs
    to match the English text to the Japanese button and press confidently.
    """
    from .llm_client import call_llm
    import os

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return [f"[{b}]" for b in buttons]

    try:
        response = call_llm(
            model=LLM_MODEL,
            system=(
                "Translate Japanese ticket machine button labels to short English names. "
                "Keep translations brief (2-4 words max) so they fit on a button. "
                "Be literal — translate exactly what the button says, no more. "
                "Preserve the ingredient: if it says 'shrimp', say 'Shrimp'. "
                "Do NOT add words like 'delicious' or 'special'. "
                f"Use these translations for known terms: {_GLOSSARY} "
                "Return a JSON array of English strings in the same order. "
                "Return only the JSON array."
            ),
            user="\n".join(buttons),
            api_key=api_key,
            max_tokens=512,
        )
        parsed = json.loads(response)
        if isinstance(parsed, list) and len(parsed) == len(buttons):
            return [str(s) for s in parsed]
        if isinstance(parsed, list):
            result = [str(s) for s in parsed]
            while len(result) < len(buttons):
                result.append(f"[{buttons[len(result)]}]")
            return result[:len(buttons)]
        return [f"[{b}]" for b in buttons]
    except Exception as exc:
        logger.warning("LLM button translation failed: %s", exc)
        return [f"[{b}]" for b in buttons]


def _make_romanized_fallback(item: ExtractedItem) -> TranslatedItem:
    """Create a romanized fallback translation."""
    ja = item.japanese_name or item.name
    return TranslatedItem(
        name=f"[{ja}]",
        japanese_name=ja,
        price=item.price,
        section=item.section_hint,
        source_text=item.source_text or ja,
        source_provenance=item.source_provenance,
        approval_status=item.approval_status,
    )
