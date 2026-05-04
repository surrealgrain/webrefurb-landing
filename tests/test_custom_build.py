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
    get_build_history,
    package_registry,
    select_print_profile,
    validate_package_output,
    validate_package1_output,
)
from pipeline.translate import translate_items, translate_section_headers
from pipeline.populate import build_menu_data, build_ticket_data, layout_item_capacities, populate_menu_svg, populate_menu_html
from pipeline.models import CustomBuildInput, ExtractedItem, TranslatedItem


def _pdf_bytes(width_pt: float = 594.96, height_pt: float = 841.92) -> bytes:
    return (
        "%PDF-1.4\n"
        f"1 0 obj\n<< /Type /Page /MediaBox [0 0 {width_pt:.2f} {height_pt:.2f}] >>\nendobj\n"
        "%%EOF\n"
    ).encode("ascii")


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

    def test_single_section_food_menu_uses_v4c_html_template(self, tmp_path):
        output_path = tmp_path / "food_menu.html"
        data = build_menu_data(
            menu_type="food",
            title="FOOD MENU",
            sections=[
                {
                    "title": "RAMEN",
                    "data_section": "ramen",
                    "items": [
                        {"name": "Shoyu Ramen", "english_name": "Shoyu Ramen", "japanese_name": "醤油ラーメン"},
                        {"name": "Miso Ramen", "english_name": "Miso Ramen", "japanese_name": "味噌ラーメン"},
                    ],
                }
            ],
            food_sections=[
                {
                    "title": "RAMEN",
                    "data_section": "ramen",
                    "items": [
                        {"name": "Shoyu Ramen", "english_name": "Shoyu Ramen", "japanese_name": "醤油ラーメン"},
                        {"name": "Miso Ramen", "english_name": "Miso Ramen", "japanese_name": "味噌ラーメン"},
                    ],
                }
            ],
        )

        populate_menu_html(
            template_path=TEMPLATE_PACKAGE_MENU / "ramen_food_menu.html",
            data=data,
            output_path=output_path,
        )

        html = output_path.read_text(encoding="utf-8")
        assert "Shoyu Ramen" in html
        assert "醤油ラーメン" in html
        assert "Miso Ramen" in html
        assert "味噌ラーメン" in html
        assert 'data-section="ramen"' in html


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

    def test_izakaya_family_sections_use_izakaya_template_family(self, tmp_path, monkeypatch):
        captured: dict[str, object] = {}

        async def fake_build_custom_package(*, output_dir: Path, menu_data: dict, ticket_data=None, restaurant_name: str = "") -> Path:
            captured["menu_data"] = menu_data
            output_dir.mkdir(parents=True, exist_ok=True)
            return output_dir

        monkeypatch.setattr("pipeline.custom_build.build_custom_package", fake_build_custom_package)

        run_custom_build(
            CustomBuildInput(
                restaurant_name="Tori Stand",
                menu_items_text="【焼き鳥】\n焼き鳥 ¥180\n【おでん】\nおでん ¥200\n【ドリンク】\n生ビール ¥600",
            ),
            output_dir=tmp_path / "build",
        )

        menu_data = captured["menu_data"]
        assert menu_data["menu_type"] == "izakaya"
        assert [section["data_section"] for section in menu_data["food"]["sections"]] == ["skewers", "small-plates"]
        assert menu_data["drinks"]["sections"][0]["data_section"] == "beer-highballs"

    def test_ramen_sides_fold_into_single_html_output(self, tmp_path):
        output_path = tmp_path / "food_menu.html"
        data = build_menu_data(
            menu_type="food",
            title="FOOD MENU",
            sections=[
                {
                    "title": "RAMEN",
                    "data_section": "ramen",
                    "items": [
                        {"name": "Shoyu Ramen", "english_name": "Shoyu Ramen", "japanese_name": "醤油ラーメン"},
                        {"name": "Miso Ramen", "english_name": "Miso Ramen", "japanese_name": "味噌ラーメン"},
                    ],
                },
                {
                    "title": "SMALL PLATES",
                    "data_section": "sides-add-ons",
                    "items": [
                        {"name": "Gyoza", "english_name": "Gyoza", "japanese_name": "餃子"},
                        {"name": "Karaage", "english_name": "Karaage", "japanese_name": "唐揚げ"},
                    ],
                },
            ],
        )

        populate_menu_html(
            template_path=TEMPLATE_PACKAGE_MENU / "ramen_food_menu.html",
            data=data,
            output_path=output_path,
        )

        html = output_path.read_text(encoding="utf-8")
        assert "Shoyu Ramen" in html
        assert "Miso Ramen" in html
        assert "Gyoza" in html
        assert "Karaage" in html
        # Both sections should appear in the single HTML output
        assert 'data-section="ramen"' in html
        assert 'data-section="sides-add-ons"' in html


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
    def _write_paid_order(self, state_root: Path, order_id: str = "ord-test") -> None:
        (state_root / "orders").mkdir(parents=True, exist_ok=True)
        (state_root / "orders" / f"{order_id}.json").write_text(
            json.dumps({
                "order_id": order_id,
                "state": "owner_review",
                "quote": {"quote_date": "2026-04-28"},
                "payment": {"status": "confirmed"},
                "intake": {
                    "full_menu_photos": True,
                    "price_confirmation": True,
                    "delivery_details": True,
                    "business_contact_confirmed": True,
                    "is_complete": True,
                },
                "approval": {
                    "approved": True,
                    "approver_name": "Tanaka",
                    "approved_package": "package_1_remote_30k",
                    "source_data_checksum": "source123",
                    "artifact_checksum": "artifact123",
                },
                "privacy_note_accepted": True,
            }),
            encoding="utf-8",
        )

    def _write_package_output(self, output_dir: Path, item_count: int = 2) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name in (
            "food_menu_print_ready.pdf",
            "drinks_menu_print_ready.pdf",
        ):
            (output_dir / name).write_bytes(_pdf_bytes())
        (output_dir / "food_menu.html").write_text(
            '<html><body><div class="menu-wrapper"><div class="menu-panel">'
            '<div class="sections-stack"><div class="section" data-section="menu">'
            '<div class="section-header"><span class="section-title">MENU</span></div>'
            '<ul class="menu-items">'
            + "".join(
                f'<li><span class="item-en">Item {idx}</span><span class="item-jp">品{idx}</span></li>'
                for idx in range(item_count)
            )
            + '</ul></div></div></div></div></body></html>',
            encoding="utf-8",
        )
        (output_dir / "drinks_menu.html").write_text(
            '<html><body><div class="menu-wrapper"><div class="menu-panel">'
            '<div class="sections-stack"></div></div></div></body></html>',
            encoding="utf-8",
        )
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

    def test_build_history_recomputes_validation_instead_of_trusting_stale_job_metadata(self, tmp_path):
        (tmp_path / "jobs").mkdir()
        (tmp_path / "jobs" / "stale.json").write_text(
            json.dumps({
                "job_id": "stale",
                "restaurant_name": "Stale Ramen",
                "status": "ready_for_review",
                "package_key": PACKAGE_1_KEY,
                "output_dir": str(tmp_path / "missing-build"),
                "package_validation": {"ok": True, "errors": [], "warnings": []},
            }),
            encoding="utf-8",
        )

        builds = get_build_history(state_root=tmp_path)["builds"]

        assert builds[0]["validation"]["ok"] is False
        assert builds[0]["validation"]["errors"] == ["output_dir_missing"]

    def test_package_approval_blocks_without_paid_operations_record(self, tmp_path):
        output_dir = tmp_path / "builds" / "job-unpaid"
        self._write_package_output(output_dir)
        (tmp_path / "jobs").mkdir()
        (tmp_path / "jobs" / "job-unpaid.json").write_text(
            json.dumps({
                "job_id": "job-unpaid",
                "restaurant_name": "Unpaid Ramen",
                "status": "ready_for_review",
                "package_key": PACKAGE_1_KEY,
                "output_dir": str(output_dir),
            }),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="Paid operations blocked"):
            approve_package_export(
                state_root=tmp_path,
                job_id="job-unpaid",
                package_key=PACKAGE_1_KEY,
            )

    def test_package2_approval_creates_print_pack_zip(self, tmp_path, monkeypatch):
        def fake_html_to_pdf_sync(html_path: Path, pdf_path: Path, *, print_profile=None) -> Path:
            if getattr(print_profile, "paper_size", "") == "B4":
                pdf_path.write_bytes(_pdf_bytes(width_pt=708.96, height_pt=1001.04))
            else:
                pdf_path.write_bytes(_pdf_bytes())
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
                "order_id": "ord-print",
            }),
            encoding="utf-8",
        )
        self._write_paid_order(tmp_path, "ord-print")

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
            async def new_page(self, **_kwargs):
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
        async def fake_html_to_pdf(html_path: Path, pdf_path: Path, **_kwargs) -> Path:
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
                ticket_data=build_ticket_data(
                    title="TICKET MACHINE GUIDE",
                    steps=["Insert money", "Choose ramen", "Take ticket", "Give ticket to staff"],
                    rows=[
                        {"buttons": [{"en": "Shoyu Ramen", "jp": "醤油ラーメン"}]},
                    ],
                ),
                restaurant_name="Hinode Ramen",
            )
        )

        html_outputs = [
            output_dir / "food_menu.html",
            output_dir / "ticket_machine_guide.html",
        ]
        for html_path in html_outputs:
            assert html_path.exists()
            content = html_path.read_text(encoding="utf-8")
            assert "watermark-overlay" not in content
            assert "SAMPLE" not in content
            assert "Sample preview only" not in content

    def test_package1_review_blocks_non_pdf_export(self, tmp_path):
        output_dir = tmp_path / "build"
        output_dir.mkdir()
        for name in (
            "food_menu_print_ready.pdf",
            "drinks_menu_print_ready.pdf",
        ):
            (output_dir / name).write_text("not a pdf", encoding="utf-8")
        (output_dir / "food_menu.html").write_text("<html>ok</html>", encoding="utf-8")
        (output_dir / "drinks_menu.html").write_text("<html>ok</html>", encoding="utf-8")
        (output_dir / "menu_data.json").write_text(
            json.dumps({"sections": [{"title": "RAMEN", "items": [{"name": "Shoyu"}]}]}),
            encoding="utf-8",
        )

        report = validate_package1_output(output_dir=output_dir)

        assert report["ok"] is False
        assert "food_menu_print_ready.pdf_not_pdf" in report["errors"]

    def _write_validation_output(self, output_dir: Path, food_html: str, drinks_html: str, menu_json: dict) -> None:
        """Write v4c HTML files and menu data for validation tests."""
        output_dir.mkdir(parents=True, exist_ok=True)
        for name in ("food_menu_print_ready.pdf", "drinks_menu_print_ready.pdf"):
            (output_dir / name).write_bytes(_pdf_bytes())
        (output_dir / "food_menu.html").write_text(food_html, encoding="utf-8")
        (output_dir / "drinks_menu.html").write_text(drinks_html, encoding="utf-8")
        (output_dir / "menu_data.json").write_text(json.dumps(menu_json), encoding="utf-8")

    def test_package_review_allows_unconfirmed_hidden_prices_but_blocks_stale_template_text(self, tmp_path):
        output_dir = tmp_path / "build"
        food_html = (
            '<html><body><div class="menu-wrapper"><div class="menu-panel">'
            '<div class="sections-stack"><div class="section" data-section="ramen">'
            '<div class="section-header"><span class="section-title">RAMEN</span></div>'
            '<ul class="menu-items">'
            '<li><span class="item-en">Shoyu Ramen</span><span class="item-jp">醤油ラーメン</span></li>'
            '<li><span class="item-en">Edamame</span><span class="item-jp">枝豆</span></li>'
            '</ul></div></div></div></div></body></html>'
        )
        drinks_html = (
            '<html><body><div class="menu-wrapper"><div class="menu-panel">'
            '<div class="sections-stack"></div></div></div></body></html>'
        )
        menu_json = {
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
        }
        self._write_validation_output(output_dir, food_html, drinks_html, menu_json)

        report = validate_package1_output(output_dir=output_dir)

        assert report["ok"] is False
        assert "food_price_missing:¥900" not in report["errors"]
        assert "food_stale_template_text_present" in report["errors"]

    def test_package_review_allows_explicit_operator_hidden_prices(self, tmp_path):
        output_dir = tmp_path / "build"
        food_html = (
            '<html><body><div class="menu-wrapper"><div class="menu-panel">'
            '<div class="sections-stack"><div class="section" data-section="ramen">'
            '<div class="section-header"><span class="section-title">RAMEN</span></div>'
            '<ul class="menu-items">'
            '<li><span class="item-en">Shoyu Ramen</span><span class="item-jp">醤油ラーメン</span></li>'
            '</ul></div></div></div></div></body></html>'
        )
        drinks_html = (
            '<html><body><div class="menu-wrapper"><div class="menu-panel">'
            '<div class="sections-stack"></div></div></div></body></html>'
        )
        menu_json = {
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
        }
        self._write_validation_output(output_dir, food_html, drinks_html, menu_json)

        report = validate_package1_output(output_dir=output_dir)

        assert report["ok"] is True

    def test_package_review_blocks_unconfirmed_prices_visible_in_customer_output(self, tmp_path):
        output_dir = tmp_path / "build"
        food_html = (
            '<html><body><div class="menu-wrapper"><div class="menu-panel">'
            '<div class="sections-stack"><div class="section" data-section="ramen">'
            '<div class="section-header"><span class="section-title">RAMEN</span></div>'
            '<ul class="menu-items">'
            '<li><span class="item-en">Shoyu Ramen  ¥900</span><span class="item-jp">醤油ラーメン</span></li>'
            '</ul></div></div></div></div></body></html>'
        )
        drinks_html = (
            '<html><body><div class="menu-wrapper"><div class="menu-panel">'
            '<div class="sections-stack"></div></div></div></body></html>'
        )
        menu_json = {
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
        }
        self._write_validation_output(output_dir, food_html, drinks_html, menu_json)

        report = validate_package1_output(output_dir=output_dir)

        assert report["ok"] is False
        assert "food_unconfirmed_price_visible:¥900" in report["errors"]

    def test_package_review_blocks_missing_prices_when_price_display_enabled(self, tmp_path):
        output_dir = tmp_path / "build"
        food_html = (
            '<html><body><div class="menu-wrapper"><div class="menu-panel">'
            '<div class="sections-stack"><div class="section" data-section="ramen">'
            '<div class="section-header"><span class="section-title">RAMEN</span></div>'
            '<ul class="menu-items">'
            '<li><span class="item-en">Shoyu Ramen</span><span class="item-jp">醤油ラーメン</span></li>'
            '</ul></div></div></div></div></body></html>'
        )
        drinks_html = (
            '<html><body><div class="menu-wrapper"><div class="menu-panel">'
            '<div class="sections-stack"></div></div></div></body></html>'
        )
        menu_json = {
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
        }
        self._write_validation_output(output_dir, food_html, drinks_html, menu_json)

        report = validate_package1_output(output_dir=output_dir)

        assert report["ok"] is False
        assert "food_price_missing:¥900" in report["errors"]

    def test_package_review_allows_redundant_headings_to_be_suppressed(self, tmp_path):
        output_dir = tmp_path / "build"
        food_html = (
            '<html><body><div class="menu-wrapper"><div class="menu-panel">'
            '<div class="sections-stack">'
            '<div class="section" data-section="ramen">'
            '<div class="section-header"><span class="section-title">RAMEN</span></div>'
            '<ul class="menu-items">'
            '<li><span class="item-en">Shoyu Ramen</span><span class="item-jp">醤油ラーメン</span></li>'
            '</ul></div>'
            '<div class="section" data-section="sides">'
            '<div class="section-header"><span class="section-title">SIDES / ADD-ONS</span></div>'
            '<ul class="menu-items">'
            '<li><span class="item-en">Gyoza</span><span class="item-jp">餃子</span></li>'
            '</ul></div>'
            '</div></div></div></body></html>'
        )
        drinks_html = (
            '<html><body><div class="menu-wrapper"><div class="menu-panel">'
            '<div class="sections-stack"><div class="section" data-section="drinks">'
            '<div class="section-header"><span class="section-title">DRINKS</span></div>'
            '<ul class="menu-items">'
            '<li><span class="item-en">Draft Beer</span><span class="item-jp">生ビール</span></li>'
            '</ul></div></div></div></div></body></html>'
        )
        menu_json = {
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
        }
        self._write_validation_output(output_dir, food_html, drinks_html, menu_json)

        report = validate_package1_output(output_dir=output_dir)

        assert report["ok"] is True

    def test_package_review_blocks_show_prices_without_confirmed_prices(self, tmp_path):
        output_dir = tmp_path / "build"
        food_html = (
            '<html><body><div class="menu-wrapper"><div class="menu-panel">'
            '<div class="sections-stack"><div class="section" data-section="ramen">'
            '<div class="section-header"><span class="section-title">RAMEN</span></div>'
            '<ul class="menu-items">'
            '<li><span class="item-en">Shoyu Ramen</span><span class="item-jp">醤油ラーメン</span></li>'
            '</ul></div></div></div></div></body></html>'
        )
        drinks_html = (
            '<html><body><div class="menu-wrapper"><div class="menu-panel">'
            '<div class="sections-stack"></div></div></div></body></html>'
        )
        menu_json = {
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
        }
        self._write_validation_output(output_dir, food_html, drinks_html, menu_json)

        report = validate_package1_output(output_dir=output_dir)

        assert report["ok"] is False
        assert "food_show_prices_without_confirmed_prices" in report["errors"]

    def test_package_review_blocks_invalid_price_state_names(self, tmp_path):
        output_dir = tmp_path / "build"
        food_html = (
            '<html><body><div class="menu-wrapper"><div class="menu-panel">'
            '<div class="sections-stack"><div class="section" data-section="ramen">'
            '<div class="section-header"><span class="section-title">RAMEN</span></div>'
            '<ul class="menu-items">'
            '<li><span class="item-en">Shoyu Ramen</span><span class="item-jp">醤油ラーメン</span></li>'
            '</ul></div></div></div></div></body></html>'
        )
        drinks_html = (
            '<html><body><div class="menu-wrapper"><div class="menu-panel">'
            '<div class="sections-stack"></div></div></div></body></html>'
        )
        menu_json = {
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
        }
        self._write_validation_output(output_dir, food_html, drinks_html, menu_json)

        report = validate_package1_output(output_dir=output_dir)

        assert report["ok"] is False
        assert "food_price_status_invalid:pending_owner_confirmation" in report["errors"]
        assert "food_price_visibility_invalid:pending_owner_confirmation" in report["errors"]

    def test_package1_approval_creates_final_zip(self, tmp_path):
        output_dir = tmp_path / "builds" / "job123"
        output_dir.mkdir(parents=True)
        for name in (
            "food_menu_print_ready.pdf",
            "drinks_menu_print_ready.pdf",
        ):
            (output_dir / name).write_bytes(_pdf_bytes())
        (output_dir / "food_menu.html").write_text(
            '<html><body><div class="menu-wrapper"><div class="menu-panel">'
            '<div class="sections-stack"><div class="section" data-section="ramen">'
            '<div class="section-header"><span class="section-title">RAMEN</span></div>'
            '<ul class="menu-items">'
            '<li><span class="item-en">Shoyu</span></li>'
            '</ul></div></div></div></div></body></html>',
            encoding="utf-8",
        )
        (output_dir / "drinks_menu.html").write_text("<html>drinks</html>", encoding="utf-8")
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
                "order_id": "ord-p1",
            }),
            encoding="utf-8",
        )
        self._write_paid_order(tmp_path, "ord-p1")

        result = approve_package1_export(state_root=tmp_path, job_id="job123")

        assert result["status"] == "completed"
        assert result["review_status"] == "approved"
        with zipfile.ZipFile(result["final_export_path"]) as package:
            names = set(package.namelist())
        assert "food_menu_print_ready.pdf" in names
        assert "PACKAGE_MANIFEST.json" in names
