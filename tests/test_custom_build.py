"""Tests for Mode B: Custom build pipeline."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from pipeline.extract import extract_from_text
from pipeline.translate import translate_items, translate_section_headers
from pipeline.populate import build_menu_data, build_ticket_data
from pipeline.models import ExtractedItem, TranslatedItem


# ---------------------------------------------------------------------------
# extract_from_text
# ---------------------------------------------------------------------------

class TestExtractFromText:
    def test_basic_items_with_prices(self):
        text = "醤油ラーメン ¥900\n味噌ラーメン ¥950"
        items = extract_from_text(text)
        assert len(items) == 2
        assert items[0].name == "醤油ラーメン"
        assert items[0].price == "¥900"
        assert items[1].name == "味噌ラーメン"
        assert items[1].price == "¥950"

    def test_items_without_prices(self):
        text = "餃子\n唐揚げ\n枝豆"
        items = extract_from_text(text)
        assert len(items) == 3
        assert items[0].name == "餃子"
        assert items[0].price == ""

    def test_section_headers_detected(self):
        text = "【ラーメン】\n醤油ラーメン ¥900\n【サイド】\n餃子 ¥400"
        items = extract_from_text(text)
        assert len(items) == 2
        assert items[0].section_hint == "ラーメン"
        assert items[1].section_hint == "サイド"

    def test_japanese_price_yen_symbol(self):
        text = "ラーメン 900円"
        items = extract_from_text(text)
        assert len(items) == 1
        assert items[0].price == "900円"

    def test_empty_input(self):
        assert extract_from_text("") == []

    def test_whitespace_only(self):
        assert extract_from_text("   \n  \n  ") == []

    def test_mixed_header_styles(self):
        text = "■ ラーメン\n醤油 ¥900\n♦ サイド\n餃子 ¥400"
        items = extract_from_text(text)
        assert len(items) == 2

    def test_preserves_japanese_name(self):
        text = "醤油ラーメン ¥900"
        items = extract_from_text(text)
        assert items[0].japanese_name == "醤油ラーメン"


# ---------------------------------------------------------------------------
# translate_items (deterministic path only)
# ---------------------------------------------------------------------------

class TestTranslateItems:
    def test_common_translations_deterministic(self):
        items = [
            ExtractedItem(name="醤油ラーメン", price="¥900", section_hint="RAMEN", japanese_name="醤油ラーメン"),
            ExtractedItem(name="味噌ラーメン", price="¥950", section_hint="RAMEN", japanese_name="味噌ラーメン"),
            ExtractedItem(name="餃子", price="¥400", section_hint="SIDES", japanese_name="餃子"),
        ]
        translated = translate_items(items)
        assert len(translated) == 3
        assert translated[0].name == "Shoyu Ramen"
        assert translated[0].japanese_name == "醤油ラーメン"
        assert translated[1].name == "Miso Ramen"
        assert translated[2].name == "Gyoza Dumplings"

    def test_unknown_items_romanized_fallback(self):
        items = [
            ExtractedItem(name="特製ラーメン", price="¥1200", japanese_name="特製ラーメン"),
        ]
        translated = translate_items(items)
        # Without API key, falls back to romanized
        assert len(translated) == 1
        assert translated[0].japanese_name == "特製ラーメン"

    def test_preserves_prices(self):
        items = [
            ExtractedItem(name="醤油ラーメン", price="¥900", japanese_name="醤油ラーメン"),
        ]
        translated = translate_items(items)
        assert translated[0].price == "¥900"

    def test_preserves_sections(self):
        items = [
            ExtractedItem(name="醤油ラーメン", section_hint="RAMEN", japanese_name="醤油ラーメン"),
        ]
        translated = translate_items(items)
        assert translated[0].section == "RAMEN"


# ---------------------------------------------------------------------------
# translate_section_headers
# ---------------------------------------------------------------------------

class TestTranslateSectionHeaders:
    def test_common_headers(self):
        headers = ["ラーメン", "トッピング", "ドリンク"]
        result = translate_section_headers(headers)
        assert result["ラーメン"] == "RAMEN"
        assert result["トッピング"] == "TOPPINGS"
        assert result["ドリンク"] == "DRINKS"

    def test_already_english_headers(self):
        headers = ["RAMEN", "SIDES"]
        result = translate_section_headers(headers)
        assert result["RAMEN"] == "RAMEN"
        assert result["SIDES"] == "SIDES"

    def test_empty_input(self):
        result = translate_section_headers([])
        assert result == {}


# ---------------------------------------------------------------------------
# build_menu_data
# ---------------------------------------------------------------------------

class TestBuildMenuData:
    def test_produces_valid_structure(self):
        sections = [
            {
                "title": "RAMEN",
                "items": [
                    {"name": "Shoyu Ramen", "japanese_name": "醤油ラーメン", "price": "¥900"},
                ],
            }
        ]
        data = build_menu_data(
            menu_type="food",
            title="FOOD MENU",
            sections=sections,
        )
        assert data["menu_type"] == "food"
        assert data["title"] == "FOOD MENU"
        assert len(data["sections"]) == 1
        assert data["show_prices"] is False

    def test_with_footer(self):
        data = build_menu_data(
            menu_type="combined",
            title="MENU",
            sections=[],
            footer_note="English translations for reference.",
        )
        assert data["footer_note"] == "English translations for reference."

    def test_optional_fields(self):
        data = build_menu_data(menu_type="custom", title="TEST", sections=[])
        assert "footer_note" not in data


# ---------------------------------------------------------------------------
# build_ticket_data
# ---------------------------------------------------------------------------

class TestBuildTicketData:
    def test_produces_valid_structure(self):
        rows = [
            {"category": "ramen_row_1", "buttons": ["Shoyu", "Miso"]},
        ]
        data = build_ticket_data(
            title="TICKET MACHINE GUIDE",
            steps=["Insert money", "Select item", "Take ticket", "Give to staff"],
            rows=rows,
        )
        assert data["title"] == "TICKET MACHINE GUIDE"
        assert len(data["steps"]) == 4
        assert len(data["rows"]) == 1
