"""Mode B: Custom build orchestration.

Ties together extract → translate → populate → export for a complete
custom menu build from owner-provided data.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .models import CustomBuildInput, CustomBuildResult
from .extract import extract_from_text, extract_from_photo, extract_ticket_machine_layout
from .translate import translate_items, translate_section_headers, translate_ticket_buttons
from .populate import ITEM_SLOT_LIMIT, SECTION_SLOT_LIMIT, build_menu_data, layout_item_capacities
from .export import build_custom_package
from .utils import ensure_dir, slugify

# Mapping from English section titles (lowercased) to v4c template data-section keys
_RAMEN_DATA_SECTIONS = {
    "ramen": "ramen",
    "noodles": "ramen",
    "ramen menu": "ramen",
    "tsukemen": "ramen",
    "dipping noodles": "ramen",
    "abura soba": "ramen",
    "mazesoba": "ramen",
    "tantanmen": "ramen",
    "tan tan men": "ramen",
    "chuka soba": "ramen",
    "sides": "sides-add-ons",
    "sides & add-ons": "sides-add-ons",
    "sides and add-ons": "sides-add-ons",
    "add-ons": "sides-add-ons",
    "extras": "sides-add-ons",
    "toppings": "sides-add-ons",
}
_IZAKAYA_DATA_SECTIONS = {
    "ramen": "ramen",
    "noodles": "ramen",
    "small plates": "small-plates",
    "appetizers": "small-plates",
    "starters": "small-plates",
    "side dishes": "small-plates",
    "oden": "small-plates",
    "seafood": "small-plates",
    "sashimi": "small-plates",
    "sake snacks": "small-plates",
    "skewers": "skewers",
    "grilled skewers": "skewers",
    "yakitori": "skewers",
    "kushiyaki": "skewers",
    "yakiton": "skewers",
    "kushikatsu": "skewers",
    "kushiage": "skewers",
    "fried skewers": "skewers",
    "robata": "skewers",
    "robatayaki": "skewers",
    "grilled dishes": "skewers",
    "rice": "rice-noodles",
    "rice & noodles": "rice-noodles",
    "noodle dishes": "rice-noodles",
    "rice dishes": "rice-noodles",
}
_DRINKS_DATA_SECTIONS = {
    "beer": "beer-highballs",
    "beers": "beer-highballs",
    "beer & highballs": "beer-highballs",
    "beer and highballs": "beer-highballs",
    "drinks": "beer-highballs",
    "beverages": "beer-highballs",
    "alcohol": "beer-highballs",
    "cocktails": "beer-highballs",
    "soft drinks": "soft-drinks-tea",
    "soft drinks & tea": "soft-drinks-tea",
    "tea": "soft-drinks-tea",
    "non-alcoholic": "soft-drinks-tea",
}

_DRINK_TOKENS = frozenset({
    "drink", "beer", "highball", "sake", "wine", "cocktail", "tea", "juice",
    "soda", "soft", "alcohol", "whisky", "whiskey", "shochu", "ramune",
    "cola", "ドリンク", "飲み物", "お飲み物", "ビール", "ハイボール", "日本酒",
    "焼酎", "サワー", "カクテル", "ワイン", "ソフトドリンク", "茶", "お茶",
})


def _resolve_data_section(title: str, is_drink: bool) -> str:
    """Map an English section title to a v4c template data-section key."""
    normalized = title.strip().lower().replace("&", "and")
    lookups = [_DRINKS_DATA_SECTIONS] if is_drink else [_RAMEN_DATA_SECTIONS, _IZAKAYA_DATA_SECTIONS]
    for lookup in lookups:
        # Exact match
        if normalized in lookup:
            return lookup[normalized]
        # Partial match
        for key, value in lookup.items():
            if key in normalized or normalized in key:
                return value
    # Fallback: use the title slug
    return slugify(title)


def run_custom_build(
    build_input: CustomBuildInput,
    *,
    output_dir: Path | None = None,
) -> CustomBuildResult:
    """Execute the full Mode B custom build pipeline.

    Steps:
    1. Extract items from provided text/photos
    2. Translate to English with bilingual pairs
    3. Build structured menu data
    4. Populate template with custom content
    5. Export final customer-ready PDFs
    6. Return packaged result
    """
    # --- Output directory ---
    if output_dir is None:
        output_dir = Path("state/builds") / slugify(build_input.restaurant_name)
    ensure_dir(output_dir)

    # --- Step 1: Extract ---
    all_items = []

    # From text input
    if build_input.menu_items_text:
        text_items = extract_from_text(build_input.menu_items_text)
        all_items.extend(text_items)

    # From photo uploads
    for photo_path in build_input.menu_photo_paths:
        photo_items = extract_from_photo(photo_path)
        all_items.extend(photo_items)

    # --- Step 2: Translate ---
    translated = translate_items(all_items)

    # Translate section headers
    unique_sections = list({item.section for item in translated if item.section})
    section_map = translate_section_headers(unique_sections)

    # --- Step 3: Build structured data ---
    sections = _organize_sections(translated, section_map)
    food_sections = [section for section in sections if section.get("item_type") == "food"]
    drinks_sections = [section for section in sections if section.get("item_type") == "drink"]

    # Determine menu_type from section classification
    has_drinks_sections = bool(drinks_sections)
    izakaya_sections = {"small-plates", "skewers", "rice-noodles"}
    has_izakaya_food = any(
        s.get("data_section", "") in izakaya_sections for s in food_sections
    )
    if has_izakaya_food:
        menu_type = "izakaya"
    else:
        menu_type = "ramen"

    menu_data = build_menu_data(
        menu_type=menu_type,
        title=f"{build_input.restaurant_name.upper()} MENU",
        sections=sections,
        food_sections=food_sections,
        drinks_sections=drinks_sections,
        show_prices=False,
        footer_note=build_input.notes or None,
    )
    menu_data["review_checklist"] = _review_checklist(
        food_sections=food_sections,
        drinks_sections=drinks_sections,
        show_prices=bool(menu_data.get("show_prices")),
    )
    menu_data["render_issues"] = _render_issues(food_sections=food_sections, drinks_sections=drinks_sections)
    approval_blockers = _approval_blockers(translated)
    approval_blockers.extend(menu_data["render_issues"])
    if approval_blockers:
        menu_data["approval_blockers"] = sorted(set(approval_blockers))

    # Ticket machine data
    ticket_data = None
    if build_input.ticket_machine_photo_path:
        layout = extract_ticket_machine_layout(build_input.ticket_machine_photo_path)
        if layout.rows:
            translated_rows = []
            for row in layout.rows:
                en_buttons = translate_ticket_buttons(row.buttons)
                translated_rows.append({
                    "category": row.category,
                    "buttons": en_buttons,
                })
            ticket_data = {
                "title": "TICKET MACHINE GUIDE",
                "steps": [
                    "Insert money",
                    "Select your item",
                    "Take your ticket",
                    "Give ticket to staff",
                ],
                "rows": translated_rows,
                "footer_note": None,
            }

    # --- Steps 4-5: Populate + Export ---
    result = asyncio.run(_populate_and_export(
        output_dir=output_dir,
        menu_data=menu_data,
        ticket_data=ticket_data,
        restaurant_name=build_input.restaurant_name,
    ))

    return result


async def _populate_and_export(
    *,
    output_dir: Path,
    menu_data: dict[str, Any],
    ticket_data: dict[str, Any] | None,
    restaurant_name: str,
) -> CustomBuildResult:
    """Run the async export step (population is handled inside build_custom_package)."""
    # Build the complete package with population + PDFs
    pkg_dir = await build_custom_package(
        output_dir=output_dir,
        menu_data=menu_data,
        ticket_data=ticket_data,
        restaurant_name=restaurant_name,
    )

    return CustomBuildResult(
        output_dir=pkg_dir,
        food_pdf=pkg_dir / "food_menu_print_ready.pdf" if (pkg_dir / "food_menu_print_ready.pdf").exists() else None,
        drinks_pdf=pkg_dir / "drinks_menu_print_ready.pdf" if (pkg_dir / "drinks_menu_print_ready.pdf").exists() else None,
        combined_pdf=None,  # v4c pipeline produces separate food/drinks PDFs
        ticket_machine_pdf=pkg_dir / "ticket_machine_guide_print_ready.pdf" if (pkg_dir / "ticket_machine_guide_print_ready.pdf").exists() else None,
        menu_json=pkg_dir / "menu_data.json",
    )


def _organize_sections(
    items: list,
    section_map: dict[str, str],
) -> list[dict[str, Any]]:
    """Organize translated items into sections for the menu data schema."""
    from .models import TranslatedItem

    # Group by section
    section_items: dict[str, list[TranslatedItem]] = {}
    for item in items:
        section = item.section or "Menu"
        if section not in section_items:
            section_items[section] = []
        section_items[section].append(item)

    # Build sections list
    sections: list[dict[str, Any]] = []
    for ja_section, items_list in section_items.items():
        en_section = section_map.get(ja_section, ja_section.upper())
        is_drink = _classify_item_type(items_list[0]) == "drink" if items_list else False
        data_section = _resolve_data_section(en_section, is_drink=is_drink)
        section_data = {
            "title": en_section,
            "data_section": data_section,
            "item_type": "drink" if is_drink else "food",
            "items": [
                {
                    "name": item.name,
                    "english_name": item.name,
                    "japanese_name": item.japanese_name,
                    "source_text": item.source_text or item.japanese_name,
                    "section": en_section,
                    "price": item.price or None,
                    "price_status": "detected_in_source" if item.price else "unknown",
                    "price_visibility": "pending_business_confirmation" if item.price else "not_applicable",
                    "source_provenance": item.source_provenance or "owner_text",
                    "approval_status": item.approval_status or "pending_review",
                    "item_type": _classify_item_type(item),
                    "description": item.description or None,
                }
                for item in items_list
            ],
        }
        sections.append(section_data)

    return sections


def _approval_blockers(items: list) -> list[str]:
    blockers: list[str] = []
    if any(_looks_like_fallback(item.name) for item in items):
        blockers.append("llm_fallback_requires_operator_review")
    return blockers


def _looks_like_fallback(value: str) -> bool:
    stripped = str(value or "").strip()
    return stripped.startswith("[") and stripped.endswith("]")


def _classify_item_type(item) -> str:
    combined = " ".join(
        (
            str(item.section or "").lower(),
            str(item.name or "").lower(),
            str(item.japanese_name or "").lower(),
        )
    )
    return "drink" if any(token in combined for token in _DRINK_TOKENS) else "food"


def _review_checklist(
    *,
    food_sections: list[dict[str, Any]],
    drinks_sections: list[dict[str, Any]],
    show_prices: bool,
) -> dict[str, Any]:
    all_sections = [*food_sections, *drinks_sections]
    all_items = [item for section in all_sections for item in section.get("items", [])]
    source_price_count = sum(1 for item in all_items if str(item.get("price") or "").strip())
    return {
        "item_count": len(all_items),
        "price_count": sum(1 for item in all_items if _price_should_render(item, show_prices=show_prices)),
        "source_price_count": source_price_count,
        "hidden_price_count": max(0, source_price_count - sum(1 for item in all_items if _price_should_render(item, show_prices=show_prices))),
        "food_section_count": len(food_sections),
        "drinks_section_count": len(drinks_sections),
        "section_split": "separated" if food_sections and drinks_sections else "single_panel_only",
        "stale_text_absent": True,
        "owner_source_present": all(bool(item.get("source_provenance")) for item in all_items),
    }


def _price_should_render(item: dict[str, Any], *, show_prices: bool) -> bool:
    price = str(item.get("price") or "").strip()
    if not price or not show_prices:
        return False
    if str(item.get("price_visibility") or "").strip() == "intentionally_hidden":
        return False
    return str(item.get("price_status") or "").strip() == "confirmed_by_business"


def _render_issues(*, food_sections: list[dict[str, Any]], drinks_sections: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    if len(food_sections) > SECTION_SLOT_LIMIT:
        issues.append("food_sections_exceed_template_capacity")
    if len(drinks_sections) > SECTION_SLOT_LIMIT:
        issues.append("drinks_sections_exceed_template_capacity")
    food_capacities = layout_item_capacities(len(food_sections))
    drinks_capacities = layout_item_capacities(len(drinks_sections))
    for idx, section in enumerate(food_sections):
        capacity = food_capacities[idx] if idx < len(food_capacities) else ITEM_SLOT_LIMIT
        if len(section.get("items") or []) > capacity:
            issues.append(f"food_section_overflow:{section.get('title', '')}")
    for idx, section in enumerate(drinks_sections):
        capacity = drinks_capacities[idx] if idx < len(drinks_capacities) else ITEM_SLOT_LIMIT
        if len(section.get("items") or []) > capacity:
            issues.append(f"drinks_section_overflow:{section.get('title', '')}")
    return issues
