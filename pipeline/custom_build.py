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
from .populate import build_menu_data
from .export import build_custom_package
from .utils import ensure_dir, slugify


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

    menu_data = build_menu_data(
        menu_type="combined",
        title=f"{build_input.restaurant_name.upper()} MENU",
        sections=sections,
        show_prices=any(item.price for item in translated),
        footer_note=build_input.notes or None,
    )

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
        combined_pdf=pkg_dir / "restaurant_menu_print_ready_combined.pdf" if (pkg_dir / "restaurant_menu_print_ready_combined.pdf").exists() else None,
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
        section_data = {
            "title": en_section,
            "items": [
                {
                    "name": item.name,
                    "japanese_name": item.japanese_name,
                    "price": item.price or None,
                    "description": item.description or None,
                }
                for item in items_list
            ],
        }
        sections.append(section_data)

    return sections
