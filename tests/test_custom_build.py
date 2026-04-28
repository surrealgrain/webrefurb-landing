"""Tests for Mode B: Custom build pipeline."""

from __future__ import annotations

import asyncio
import json
import sys
import types
import zipfile
import pytest
from pathlib import Path
from xml.etree import ElementTree as ET

from pipeline.constants import PACKAGE_1_KEY, PACKAGE_2_KEY, PACKAGE_3_KEY, TEMPLATE_PACKAGE_MENU
from pipeline.extract import extract_from_text
from pipeline.custom_build import run_custom_build
from pipeline.export import PdfExportError, build_custom_package, html_to_pdf
from pipeline.package_export import (
    approve_package_export,
    approve_package1_export,
    package_registry,
    select_print_profile,
    validate_package_output,
    validate_package1_output,
)
from pipeline.translate import translate_items, translate_section_headers
from pipeline.populate import build_menu_data, build_ticket_data, layout_item_capacities, populate_menu_svg
from pipeline.models import CustomBuildInput, ExtractedItem, TranslatedItem


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

    def test_prices_stay_hidden_by_default_even_when_present(self):
        sections = [
            {
                "title": "RAMEN",
                "items": [
                    {"name": "Shoyu Ramen", "japanese_name": "醤油ラーメン", "price": "¥900", "price_status": "confirmed_by_business"},
                ],
            }
        ]
        data = build_menu_data(
            menu_type="food",
            title="FOOD MENU",
            sections=sections,
        )
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


class TestAdaptiveMenuLayout:
    def test_layout_item_capacities_follow_section_count(self):
        assert layout_item_capacities(1) == [14]
        assert layout_item_capacities(2) == [9, 9]
        assert layout_item_capacities(3) == [9, 8, 8]
        assert layout_item_capacities(4) == [8, 8, 8, 8]

    def test_single_section_food_menu_uses_one_full_width_box(self, tmp_path):
        output_path = tmp_path / "food_menu.svg"
        data = build_menu_data(
            menu_type="food",
            title="FOOD MENU",
            sections=[
                {
                    "title": "RAMEN",
                    "items": [
                        {"name": "Shoyu Ramen", "english_name": "Shoyu Ramen", "japanese_name": "醤油ラーメン"},
                        {"name": "Miso Ramen", "english_name": "Miso Ramen", "japanese_name": "味噌ラーメン"},
                    ],
                }
            ],
            food_sections=[
                {
                    "title": "RAMEN",
                    "items": [
                        {"name": "Shoyu Ramen", "english_name": "Shoyu Ramen", "japanese_name": "醤油ラーメン"},
                        {"name": "Miso Ramen", "english_name": "Miso Ramen", "japanese_name": "味噌ラーメン"},
                    ],
                }
            ],
        )

        populate_menu_svg(
            template_path=TEMPLATE_PACKAGE_MENU / "food_menu_editable_vector.svg",
            data=data,
            output_path=output_path,
        )

        root = ET.parse(output_path).getroot()
        rects = [
            elem for elem in root.iter("{http://www.w3.org/2000/svg}rect")
            if "stroke" in elem.get("class", "").split() and elem.get("data-slot-index") is not None
        ]
        visible = [elem for elem in rects if elem.get("display") != "none"]
        hidden = [elem for elem in rects if elem.get("display") == "none"]

        assert len(visible) == 1
        assert len(hidden) == 3
        assert visible[0].get("width") == "498.0"
        assert visible[0].get("height") == "506.0"
        item_fonts = [
            float(elem.get("font-size", "0") or 0)
            for elem in root.iter("{http://www.w3.org/2000/svg}text")
            if "item-en" in elem.get("class", "").split() and elem.get("display") != "none" and "".join(elem.itertext()).strip()
        ]
        assert item_fonts
        assert max(item_fonts) >= 16.0
        text_values = {" ".join(part.strip() for part in elem.itertext()).strip() for elem in root.iter("{http://www.w3.org/2000/svg}text")}
        assert "RAMEN MENU" in text_values
        assert "RAMEN" not in text_values
        assert "Shoyu Ramen" in text_values


class TestRunCustomBuild:
    def test_source_prices_stay_hidden_until_business_confirmation(self, tmp_path, monkeypatch):
        captured: dict[str, object] = {}

        async def fake_build_custom_package(*, output_dir: Path, menu_data: dict, ticket_data=None, restaurant_name: str = "") -> Path:
            captured["menu_data"] = menu_data
            output_dir.mkdir(parents=True, exist_ok=True)
            return output_dir

        monkeypatch.setattr("pipeline.custom_build.build_custom_package", fake_build_custom_package)

        result = run_custom_build(
            CustomBuildInput(
                restaurant_name="Hinode Ramen",
                menu_items_text="【ラーメン】\n醤油ラーメン ¥900\n【ドリンク】\n生ビール ¥600",
            ),
            output_dir=tmp_path / "build",
        )

        menu_data = captured["menu_data"]
        assert result.output_dir == tmp_path / "build"
        assert menu_data["show_prices"] is False
        food_item = menu_data["food"]["sections"][0]["items"][0]
        drink_item = menu_data["drinks"]["sections"][0]["items"][0]
        assert food_item["price_status"] == "detected_in_source"
        assert drink_item["price_status"] == "detected_in_source"
        assert food_item["price_visibility"] == "pending_business_confirmation"
        assert menu_data["review_checklist"]["price_count"] == 0
        assert menu_data["review_checklist"]["source_price_count"] == 2

    def test_ramen_sides_fold_into_bottom_of_ramen_panel(self, tmp_path):
        output_path = tmp_path / "food_menu.svg"
        data = build_menu_data(
            menu_type="food",
            title="FOOD MENU",
            sections=[
                {
                    "title": "RAMEN",
                    "items": [
                        {"name": "Shoyu Ramen", "english_name": "Shoyu Ramen", "japanese_name": "醤油ラーメン"},
                        {"name": "Miso Ramen", "english_name": "Miso Ramen", "japanese_name": "味噌ラーメン"},
                    ],
                },
                {
                    "title": "SMALL PLATES",
                    "items": [
                        {"name": "Gyoza", "english_name": "Gyoza", "japanese_name": "餃子"},
                        {"name": "Karaage", "english_name": "Karaage", "japanese_name": "唐揚げ"},
                    ],
                },
            ],
        )

        populate_menu_svg(
            template_path=TEMPLATE_PACKAGE_MENU / "food_menu_editable_vector.svg",
            data=data,
            output_path=output_path,
        )

        root = ET.parse(output_path).getroot()
        rects = [
            elem for elem in root.iter("{http://www.w3.org/2000/svg}rect")
            if "stroke" in elem.get("class", "").split() and elem.get("data-slot-index") is not None
        ]
        visible_rects = [elem for elem in rects if elem.get("display") != "none"]
        title_texts = {
            "".join(elem.itertext()).strip(): elem
            for elem in root.iter("{http://www.w3.org/2000/svg}text")
            if "section" in elem.get("class", "").split() and "".join(elem.itertext()).strip()
        }
        item_positions = {
            "".join(elem.itertext()).strip(): float(elem.get("y", "0") or 0)
            for elem in root.iter("{http://www.w3.org/2000/svg}text")
            if "item-en" in elem.get("class", "").split() and elem.get("display") != "none" and "".join(elem.itertext()).strip()
        }

        assert len(visible_rects) == 1
        main_titles = {
            "".join(elem.itertext()).strip()
            for elem in root.iter("{http://www.w3.org/2000/svg}text")
            if "title" in elem.get("class", "").split() and "".join(elem.itertext()).strip()
        }
        assert "RAMEN MENU" in main_titles
        assert "RAMEN" not in title_texts
        assert "SIDES / ADD-ONS" in title_texts
        assert item_positions["Gyoza"] > item_positions["Miso Ramen"]
        assert title_texts["SIDES / ADD-ONS"].get("display") == "inline"
        item_fonts = {
            "".join(elem.itertext()).strip(): float(elem.get("font-size", "0") or 0)
            for elem in root.iter("{http://www.w3.org/2000/svg}text")
            if "item-en" in elem.get("class", "").split() and elem.get("display") != "none" and "".join(elem.itertext()).strip()
        }
        assert item_positions["Shoyu Ramen"] >= 250.0
        assert item_positions["Gyoza"] >= 550.0
        assert item_fonts["Shoyu Ramen"] >= 18.0
        assert item_fonts["Gyoza"] >= 14.0


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


class TestCustomerExport:
    def _write_package_output(self, output_dir: Path, item_count: int = 2) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name in (
            "restaurant_menu_print_ready_combined.pdf",
            "food_menu_print_ready.pdf",
            "drinks_menu_print_ready.pdf",
        ):
            (output_dir / name).write_bytes(b"%PDF-1.4\n% test\n")
        (output_dir / "food_menu_editable_vector.svg").write_text("<svg></svg>", encoding="utf-8")
        (output_dir / "drinks_menu_editable_vector.svg").write_text("<svg></svg>", encoding="utf-8")
        (output_dir / "restaurant_menu_print_master.html").write_text("<html>preview</html>", encoding="utf-8")
        (output_dir / "food_menu_browser_preview.html").write_text("<html>food</html>", encoding="utf-8")
        (output_dir / "drinks_menu_browser_preview.html").write_text("<html>drinks</html>", encoding="utf-8")
        (output_dir / "menu_data.json").write_text(
            json.dumps({
                "sections": [
                    {
                        "title": "MENU",
                        "items": [{"name": f"Item {idx}", "japanese_name": f"品{idx}"} for idx in range(item_count)],
                    }
                ]
            }),
            encoding="utf-8",
        )

    def test_package_registry_has_final_prices(self):
        packages = {package["key"]: package for package in package_registry()}

        assert packages[PACKAGE_1_KEY]["price_yen"] == 30000
        assert packages[PACKAGE_2_KEY]["price_yen"] == 45000
        assert packages[PACKAGE_3_KEY]["price_yen"] == 65000

    def test_package2_print_profile_selects_a4_b4_and_quote_gate(self):
        normal = {"sections": [{"items": [{"name": str(idx)} for idx in range(20)]}]}
        dense = {"sections": [{"items": [{"name": str(idx)} for idx in range(50)]}]}
        too_large = {"sections": [{"items": [{"name": str(idx)} for idx in range(80)]}]}

        assert select_print_profile(normal)["paper_size"] == "A4"
        assert select_print_profile(dense)["paper_size"] == "B4"
        assert select_print_profile(dense)["custom_quote_required"] is False
        assert select_print_profile(too_large)["custom_quote_required"] is True

    def test_package2_blocks_missing_delivery_fields(self, tmp_path):
        output_dir = tmp_path / "build"
        self._write_package_output(output_dir)

        report = validate_package_output(output_dir=output_dir, package_key=PACKAGE_2_KEY)

        assert report["ok"] is False
        assert "delivery_contact_name_missing" in report["errors"]
        assert "delivery_address_missing" in report["errors"]

    def test_package2_approval_creates_print_pack_zip(self, tmp_path, monkeypatch):
        def fake_html_to_pdf_sync(html_path: Path, pdf_path: Path, *, print_profile=None) -> Path:
            pdf_path.write_bytes(b"%PDF-1.4\n% print pack\n")
            return pdf_path

        monkeypatch.setattr("pipeline.package_export.html_to_pdf_sync", fake_html_to_pdf_sync)
        output_dir = tmp_path / "builds" / "job-print"
        self._write_package_output(output_dir, item_count=50)
        (tmp_path / "jobs").mkdir()
        (tmp_path / "jobs" / "job-print.json").write_text(
            json.dumps({
                "job_id": "job-print",
                "restaurant_name": "Hinode Ramen",
                "status": "ready_for_review",
                "package_key": PACKAGE_2_KEY,
                "output_dir": str(output_dir),
            }),
            encoding="utf-8",
        )

        result = approve_package_export(
            state_root=tmp_path,
            job_id="job-print",
            package_key=PACKAGE_2_KEY,
            delivery_details={
                "delivery_contact_name": "Tanaka",
                "delivery_address": "1-2-3 Tokyo",
            },
        )

        assert result["package_key"] == PACKAGE_2_KEY
        with zipfile.ZipFile(result["final_export_path"]) as package:
            names = set(package.namelist())
            print_order = json.loads(package.read("PRINT_ORDER.json"))
        assert "PRINT_CHECKLIST.md" in names
        assert "DELIVERY_CHECKLIST.md" in names
        assert "food_menu_print_b4.pdf" in names
        assert print_order["print_profile"]["paper_size"] == "B4"

    def test_html_to_pdf_rejects_invalid_renderer_output(self, tmp_path, monkeypatch):
        class FakePage:
            async def goto(self, *_args, **_kwargs):
                return None

            async def emulate_media(self, *_args, **_kwargs):
                return None

            async def pdf(self, *, path: str, **_kwargs):
                Path(path).write_text("not a pdf", encoding="utf-8")

        class FakeBrowser:
            async def new_page(self):
                return FakePage()

            async def close(self):
                return None

        class FakeChromium:
            async def launch(self):
                return FakeBrowser()

        class FakePlaywright:
            chromium = FakeChromium()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

        monkeypatch.setitem(
            sys.modules,
            "playwright.async_api",
            types.SimpleNamespace(async_playwright=lambda: FakePlaywright()),
        )

        html_path = tmp_path / "menu.html"
        pdf_path = tmp_path / "menu.pdf"
        html_path.write_text("<html><body>Menu</body></html>", encoding="utf-8")

        with pytest.raises(PdfExportError, match="valid PDF"):
            asyncio.run(html_to_pdf(html_path, pdf_path))

        assert not pdf_path.exists()

    def test_custom_package_outputs_are_not_watermarked(self, tmp_path, monkeypatch):
        async def fake_html_to_pdf(html_path: Path, pdf_path: Path) -> Path:
            pdf_path.write_text("pdf placeholder", encoding="utf-8")
            return pdf_path

        monkeypatch.setattr("pipeline.export.html_to_pdf", fake_html_to_pdf)

        menu_data = build_menu_data(
            menu_type="combined",
            title="HINODE RAMEN MENU",
            sections=[
                {
                    "title": "RAMEN",
                    "items": [
                        {
                            "name": "Shoyu Ramen",
                            "japanese_name": "醤油ラーメン",
                            "price": "¥900",
                            "description": "Classic soy sauce ramen.",
                        }
                    ],
                }
            ],
            show_prices=True,
        )

        output_dir = asyncio.run(
            build_custom_package(
                output_dir=tmp_path / "build",
                menu_data=menu_data,
                restaurant_name="Hinode Ramen",
            )
        )

        html_outputs = [
            output_dir / "food_menu_browser_preview.html",
            output_dir / "drinks_menu_browser_preview.html",
            output_dir / "restaurant_menu_print_master.html",
        ]
        for html_path in html_outputs:
            assert html_path.exists()
            content = html_path.read_text(encoding="utf-8")
            assert "watermark-overlay" not in content
            assert "SAMPLE" not in content

    def test_package1_review_blocks_non_pdf_export(self, tmp_path):
        output_dir = tmp_path / "build"
        output_dir.mkdir()
        for name in (
            "restaurant_menu_print_ready_combined.pdf",
            "food_menu_print_ready.pdf",
            "drinks_menu_print_ready.pdf",
        ):
            (output_dir / name).write_text("not a pdf", encoding="utf-8")
        (output_dir / "food_menu_editable_vector.svg").write_text("<svg></svg>", encoding="utf-8")
        (output_dir / "drinks_menu_editable_vector.svg").write_text("<svg></svg>", encoding="utf-8")
        (output_dir / "restaurant_menu_print_master.html").write_text("<html>ok</html>", encoding="utf-8")
        (output_dir / "menu_data.json").write_text(
            json.dumps({"sections": [{"title": "RAMEN", "items": [{"name": "Shoyu"}]}]}),
            encoding="utf-8",
        )

        report = validate_package1_output(output_dir=output_dir)

        assert report["ok"] is False
        assert "restaurant_menu_print_ready_combined.pdf_not_pdf" in report["errors"]

    def test_package_review_allows_unconfirmed_hidden_prices_but_blocks_stale_template_text(self, tmp_path):
        output_dir = tmp_path / "build"
        output_dir.mkdir()
        for name in (
            "restaurant_menu_print_ready_combined.pdf",
            "food_menu_print_ready.pdf",
            "drinks_menu_print_ready.pdf",
        ):
            (output_dir / name).write_bytes(b"%PDF-1.4\n% test\n")
        (output_dir / "restaurant_menu_print_master.html").write_text(
            '<html><body><img src="food_menu_editable_vector.svg"><img src="drinks_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "food_menu_browser_preview.html").write_text(
            '<html><body><img src="food_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "drinks_menu_browser_preview.html").write_text(
            '<html><body><img src="drinks_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "food_menu_editable_vector.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text class="title">FOOD MENU</text>'
            '<text class="section">RAMEN</text>'
            '<text class="item-en">Shoyu Ramen</text>'
            '<text class="item-jp">醤油ラーメン</text>'
            '<text class="item-en">Edamame</text>'
            '</svg>',
            encoding="utf-8",
        )
        (output_dir / "drinks_menu_editable_vector.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text class="title">DRINKS MENU</text>'
            '</svg>',
            encoding="utf-8",
        )
        (output_dir / "menu_data.json").write_text(
            json.dumps({
                "food": {
                    "title": "FOOD MENU",
                    "sections": [{
                        "title": "RAMEN",
                        "items": [{
                            "name": "Shoyu Ramen",
                            "english_name": "Shoyu Ramen",
                            "japanese_name": "醤油ラーメン",
                            "source_text": "醤油ラーメン",
                            "section": "RAMEN",
                            "price": "¥900",
                            "price_status": "confirmed_by_business",
                            "source_provenance": "owner_text",
                            "approval_status": "pending_review",
                        }],
                    }],
                },
                "drinks": {"title": "DRINKS MENU", "sections": []},
                "show_prices": False,
                "sections": [{
                    "title": "RAMEN",
                    "items": [{"name": "Shoyu Ramen", "japanese_name": "醤油ラーメン"}],
                }],
            }),
            encoding="utf-8",
        )

        report = validate_package1_output(output_dir=output_dir)

        assert report["ok"] is False
        assert "food_price_missing:¥900" not in report["errors"]
        assert "food_stale_template_text_present" in report["errors"]

    def test_package_review_allows_explicit_operator_hidden_prices(self, tmp_path):
        output_dir = tmp_path / "build"
        output_dir.mkdir()
        for name in (
            "restaurant_menu_print_ready_combined.pdf",
            "food_menu_print_ready.pdf",
            "drinks_menu_print_ready.pdf",
        ):
            (output_dir / name).write_bytes(b"%PDF-1.4\n% test\n")
        (output_dir / "restaurant_menu_print_master.html").write_text(
            '<html><body><img src="food_menu_editable_vector.svg"><img src="drinks_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "food_menu_browser_preview.html").write_text(
            '<html><body><img src="food_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "drinks_menu_browser_preview.html").write_text(
            '<html><body><img src="drinks_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "food_menu_editable_vector.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text class="title">RAMEN MENU</text>'
            '<text class="item-en">Shoyu Ramen</text>'
            '<text class="item-jp">醤油ラーメン</text>'
            '</svg>',
            encoding="utf-8",
        )
        (output_dir / "drinks_menu_editable_vector.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text class="title">DRINKS MENU</text>'
            '</svg>',
            encoding="utf-8",
        )
        (output_dir / "menu_data.json").write_text(
            json.dumps({
                "food": {
                    "title": "FOOD MENU",
                    "sections": [{
                        "title": "RAMEN",
                        "items": [{
                            "name": "Shoyu Ramen",
                            "english_name": "Shoyu Ramen",
                            "japanese_name": "醤油ラーメン",
                            "source_text": "醤油ラーメン",
                            "section": "RAMEN",
                            "price": "¥900",
                            "price_status": "confirmed_by_business",
                            "price_visibility": "intentionally_hidden",
                            "source_provenance": "owner_text",
                            "approval_status": "pending_review",
                        }],
                    }],
                },
                "drinks": {"title": "DRINKS MENU", "sections": []},
                "show_prices": False,
                "sections": [{
                    "title": "RAMEN",
                    "items": [{"name": "Shoyu Ramen", "japanese_name": "醤油ラーメン"}],
                }],
            }),
            encoding="utf-8",
        )

        report = validate_package1_output(output_dir=output_dir)

        assert report["ok"] is True

    def test_package_review_blocks_unconfirmed_prices_visible_in_customer_output(self, tmp_path):
        output_dir = tmp_path / "build"
        output_dir.mkdir()
        for name in (
            "restaurant_menu_print_ready_combined.pdf",
            "food_menu_print_ready.pdf",
            "drinks_menu_print_ready.pdf",
        ):
            (output_dir / name).write_bytes(b"%PDF-1.4\n% test\n")
        (output_dir / "restaurant_menu_print_master.html").write_text(
            '<html><body><img src="food_menu_editable_vector.svg"><img src="drinks_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "food_menu_browser_preview.html").write_text(
            '<html><body><img src="food_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "drinks_menu_browser_preview.html").write_text(
            '<html><body><img src="drinks_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "food_menu_editable_vector.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text class="title">FOOD MENU</text>'
            '<text class="section">RAMEN</text>'
            '<text class="item-en">Shoyu Ramen  ¥900</text>'
            '<text class="item-jp">醤油ラーメン</text>'
            '</svg>',
            encoding="utf-8",
        )
        (output_dir / "drinks_menu_editable_vector.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text class="title">DRINKS MENU</text>'
            '</svg>',
            encoding="utf-8",
        )
        (output_dir / "menu_data.json").write_text(
            json.dumps({
                "food": {
                    "title": "FOOD MENU",
                    "sections": [{
                        "title": "RAMEN",
                        "items": [{
                            "name": "Shoyu Ramen",
                            "english_name": "Shoyu Ramen",
                            "japanese_name": "醤油ラーメン",
                            "source_text": "醤油ラーメン",
                            "section": "RAMEN",
                            "price": "¥900",
                            "price_status": "detected_in_source",
                            "price_visibility": "pending_business_confirmation",
                            "source_provenance": "owner_text",
                            "approval_status": "pending_review",
                        }],
                    }],
                },
                "drinks": {"title": "DRINKS MENU", "sections": []},
                "show_prices": False,
                "sections": [{
                    "title": "RAMEN",
                    "items": [{"name": "Shoyu Ramen", "japanese_name": "醤油ラーメン"}],
                }],
            }),
            encoding="utf-8",
        )

        report = validate_package1_output(output_dir=output_dir)

        assert report["ok"] is False
        assert "food_unconfirmed_price_visible:¥900" in report["errors"]

    def test_package_review_blocks_missing_prices_when_price_display_enabled(self, tmp_path):
        output_dir = tmp_path / "build"
        output_dir.mkdir()
        for name in (
            "restaurant_menu_print_ready_combined.pdf",
            "food_menu_print_ready.pdf",
            "drinks_menu_print_ready.pdf",
        ):
            (output_dir / name).write_bytes(b"%PDF-1.4\n% test\n")
        (output_dir / "restaurant_menu_print_master.html").write_text(
            '<html><body><img src="food_menu_editable_vector.svg"><img src="drinks_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "food_menu_browser_preview.html").write_text(
            '<html><body><img src="food_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "drinks_menu_browser_preview.html").write_text(
            '<html><body><img src="drinks_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "food_menu_editable_vector.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text class="title">FOOD MENU</text>'
            '<text class="section">RAMEN</text>'
            '<text class="item-en">Shoyu Ramen</text>'
            '<text class="item-jp">醤油ラーメン</text>'
            '</svg>',
            encoding="utf-8",
        )
        (output_dir / "drinks_menu_editable_vector.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text class="title">DRINKS MENU</text>'
            '</svg>',
            encoding="utf-8",
        )
        (output_dir / "menu_data.json").write_text(
            json.dumps({
                "food": {
                    "title": "FOOD MENU",
                    "sections": [{
                        "title": "RAMEN",
                        "items": [{
                            "name": "Shoyu Ramen",
                            "english_name": "Shoyu Ramen",
                            "japanese_name": "醤油ラーメン",
                            "source_text": "醤油ラーメン",
                            "section": "RAMEN",
                            "price": "¥900",
                            "price_status": "confirmed_by_business",
                            "source_provenance": "owner_text",
                            "approval_status": "pending_review",
                        }],
                    }],
                },
                "drinks": {"title": "DRINKS MENU", "sections": []},
                "show_prices": True,
                "sections": [{
                    "title": "RAMEN",
                    "items": [{"name": "Shoyu Ramen", "japanese_name": "醤油ラーメン"}],
                }],
            }),
            encoding="utf-8",
        )

        report = validate_package1_output(output_dir=output_dir)

        assert report["ok"] is False
        assert "food_price_missing:¥900" in report["errors"]

    def test_package_review_allows_redundant_headings_to_be_suppressed(self, tmp_path):
        output_dir = tmp_path / "build"
        output_dir.mkdir()
        for name in (
            "restaurant_menu_print_ready_combined.pdf",
            "food_menu_print_ready.pdf",
            "drinks_menu_print_ready.pdf",
        ):
            (output_dir / name).write_bytes(b"%PDF-1.4\n% test\n")
        (output_dir / "restaurant_menu_print_master.html").write_text(
            '<html><body><img src="food_menu_editable_vector.svg"><img src="drinks_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "food_menu_browser_preview.html").write_text(
            '<html><body><img src="food_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "drinks_menu_browser_preview.html").write_text(
            '<html><body><img src="drinks_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "food_menu_editable_vector.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text class="title">RAMEN MENU</text>'
            '<text class="item-en">Shoyu Ramen</text>'
            '<text class="item-jp">醤油ラーメン</text>'
            '<text class="item-en">Gyoza</text>'
            '<text class="item-jp">餃子</text>'
            '<text class="section">SIDES / ADD-ONS</text>'
            '</svg>',
            encoding="utf-8",
        )
        (output_dir / "drinks_menu_editable_vector.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text class="title">DRINKS MENU</text>'
            '<text class="item-en">Draft Beer</text>'
            '<text class="item-jp">生ビール</text>'
            '</svg>',
            encoding="utf-8",
        )
        (output_dir / "menu_data.json").write_text(
            json.dumps({
                "food": {
                    "title": "FOOD MENU",
                    "sections": [
                        {
                            "title": "RAMEN",
                            "items": [{
                                "name": "Shoyu Ramen",
                                "english_name": "Shoyu Ramen",
                                "japanese_name": "醤油ラーメン",
                                "source_text": "醤油ラーメン",
                                "section": "RAMEN",
                                "price_status": "unknown",
                                "price_visibility": "not_applicable",
                                "source_provenance": "owner_text",
                                "approval_status": "pending_review",
                            }],
                        },
                        {
                            "title": "SIDES",
                            "items": [{
                                "name": "Gyoza",
                                "english_name": "Gyoza",
                                "japanese_name": "餃子",
                                "source_text": "餃子",
                                "section": "SIDES",
                                "price_status": "unknown",
                                "price_visibility": "not_applicable",
                                "source_provenance": "owner_text",
                                "approval_status": "pending_review",
                            }],
                        },
                    ],
                },
                "drinks": {
                    "title": "DRINKS MENU",
                    "sections": [{
                        "title": "DRINKS",
                        "items": [{
                            "name": "Draft Beer",
                            "english_name": "Draft Beer",
                            "japanese_name": "生ビール",
                            "source_text": "生ビール",
                            "section": "DRINKS",
                            "price_status": "unknown",
                            "price_visibility": "not_applicable",
                            "source_provenance": "owner_text",
                            "approval_status": "pending_review",
                        }],
                    }],
                },
                "show_prices": False,
                "sections": [
                    {"title": "RAMEN", "items": [{"name": "Shoyu Ramen", "japanese_name": "醤油ラーメン"}]},
                    {"title": "SIDES", "items": [{"name": "Gyoza", "japanese_name": "餃子"}]},
                    {"title": "DRINKS", "items": [{"name": "Draft Beer", "japanese_name": "生ビール"}]},
                ],
            }),
            encoding="utf-8",
        )

        report = validate_package1_output(output_dir=output_dir)

        assert report["ok"] is True

    def test_package_review_blocks_show_prices_without_confirmed_prices(self, tmp_path):
        output_dir = tmp_path / "build"
        output_dir.mkdir()
        for name in (
            "restaurant_menu_print_ready_combined.pdf",
            "food_menu_print_ready.pdf",
            "drinks_menu_print_ready.pdf",
        ):
            (output_dir / name).write_bytes(b"%PDF-1.4\n% test\n")
        (output_dir / "restaurant_menu_print_master.html").write_text(
            '<html><body><img src="food_menu_editable_vector.svg"><img src="drinks_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "food_menu_browser_preview.html").write_text(
            '<html><body><img src="food_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "drinks_menu_browser_preview.html").write_text(
            '<html><body><img src="drinks_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "food_menu_editable_vector.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text class="title">FOOD MENU</text>'
            '<text class="section">RAMEN</text>'
            '<text class="item-en">Shoyu Ramen</text>'
            '<text class="item-jp">醤油ラーメン</text>'
            '</svg>',
            encoding="utf-8",
        )
        (output_dir / "drinks_menu_editable_vector.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text class="title">DRINKS MENU</text>'
            '</svg>',
            encoding="utf-8",
        )
        (output_dir / "menu_data.json").write_text(
            json.dumps({
                "food": {
                    "title": "FOOD MENU",
                    "sections": [{
                        "title": "RAMEN",
                        "items": [{
                            "name": "Shoyu Ramen",
                            "english_name": "Shoyu Ramen",
                            "japanese_name": "醤油ラーメン",
                            "source_text": "醤油ラーメン",
                            "section": "RAMEN",
                            "price": "¥900",
                            "price_status": "detected_in_source",
                            "price_visibility": "pending_business_confirmation",
                            "source_provenance": "owner_text",
                            "approval_status": "pending_review",
                        }],
                    }],
                },
                "drinks": {"title": "DRINKS MENU", "sections": []},
                "show_prices": True,
                "sections": [{
                    "title": "RAMEN",
                    "items": [{"name": "Shoyu Ramen", "japanese_name": "醤油ラーメン"}],
                }],
            }),
            encoding="utf-8",
        )

        report = validate_package1_output(output_dir=output_dir)

        assert report["ok"] is False
        assert "food_show_prices_without_confirmed_prices" in report["errors"]

    def test_package_review_blocks_invalid_price_state_names(self, tmp_path):
        output_dir = tmp_path / "build"
        output_dir.mkdir()
        for name in (
            "restaurant_menu_print_ready_combined.pdf",
            "food_menu_print_ready.pdf",
            "drinks_menu_print_ready.pdf",
        ):
            (output_dir / name).write_bytes(b"%PDF-1.4\n% test\n")
        (output_dir / "restaurant_menu_print_master.html").write_text(
            '<html><body><img src="food_menu_editable_vector.svg"><img src="drinks_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "food_menu_browser_preview.html").write_text(
            '<html><body><img src="food_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "drinks_menu_browser_preview.html").write_text(
            '<html><body><img src="drinks_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "food_menu_editable_vector.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text class="title">FOOD MENU</text>'
            '<text class="section">RAMEN</text>'
            '<text class="item-en">Shoyu Ramen</text>'
            '<text class="item-jp">醤油ラーメン</text>'
            '</svg>',
            encoding="utf-8",
        )
        (output_dir / "drinks_menu_editable_vector.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text class="title">DRINKS MENU</text>'
            '</svg>',
            encoding="utf-8",
        )
        (output_dir / "menu_data.json").write_text(
            json.dumps({
                "food": {
                    "title": "FOOD MENU",
                    "sections": [{
                        "title": "RAMEN",
                        "items": [{
                            "name": "Shoyu Ramen",
                            "english_name": "Shoyu Ramen",
                            "japanese_name": "醤油ラーメン",
                            "source_text": "醤油ラーメン",
                            "section": "RAMEN",
                            "price": "¥900",
                            "price_status": "pending_owner_confirmation",
                            "price_visibility": "pending_owner_confirmation",
                            "source_provenance": "owner_text",
                            "approval_status": "pending_review",
                        }],
                    }],
                },
                "drinks": {"title": "DRINKS MENU", "sections": []},
                "show_prices": False,
                "sections": [{
                    "title": "RAMEN",
                    "items": [{"name": "Shoyu Ramen", "japanese_name": "醤油ラーメン"}],
                }],
            }),
            encoding="utf-8",
        )

        report = validate_package1_output(output_dir=output_dir)

        assert report["ok"] is False
        assert "food_price_status_invalid:pending_owner_confirmation" in report["errors"]
        assert "food_price_visibility_invalid:pending_owner_confirmation" in report["errors"]

    def test_package1_approval_creates_final_zip(self, tmp_path):
        output_dir = tmp_path / "builds" / "job123"
        output_dir.mkdir(parents=True)
        for name in (
            "restaurant_menu_print_ready_combined.pdf",
            "food_menu_print_ready.pdf",
            "drinks_menu_print_ready.pdf",
        ):
            (output_dir / name).write_bytes(b"%PDF-1.4\n% test\n")
        (output_dir / "food_menu_editable_vector.svg").write_text("<svg></svg>", encoding="utf-8")
        (output_dir / "drinks_menu_editable_vector.svg").write_text("<svg></svg>", encoding="utf-8")
        (output_dir / "restaurant_menu_print_master.html").write_text("<html>ok</html>", encoding="utf-8")
        (output_dir / "menu_data.json").write_text(
            json.dumps({"sections": [{"title": "RAMEN", "items": [{"name": "Shoyu"}]}]}),
            encoding="utf-8",
        )
        (tmp_path / "jobs").mkdir()
        (tmp_path / "jobs" / "job123.json").write_text(
            json.dumps({
                "job_id": "job123",
                "restaurant_name": "Hinode Ramen",
                "status": "ready_for_review",
                "output_dir": str(output_dir),
            }),
            encoding="utf-8",
        )

        result = approve_package1_export(state_root=tmp_path, job_id="job123")

        assert result["status"] == "completed"
        assert result["review_status"] == "approved"
        with zipfile.ZipFile(result["final_export_path"]) as package:
            names = set(package.namelist())
        assert "restaurant_menu_print_ready_combined.pdf" in names
        assert "PACKAGE_MANIFEST.json" in names
