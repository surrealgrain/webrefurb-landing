"""Tests for Mode B: Custom build pipeline."""

from __future__ import annotations

import asyncio
import json
import sys
import types
import zipfile
import pytest
from pathlib import Path

from pipeline.extract import extract_from_text
from pipeline.export import PdfExportError, build_custom_package, html_to_pdf
from pipeline.constants import PACKAGE_1_KEY, PACKAGE_2_KEY, PACKAGE_3_KEY
from pipeline.package_export import (
    approve_package_export,
    approve_package1_export,
    package_registry,
    select_print_profile,
    validate_package_output,
    validate_package1_output,
)
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
