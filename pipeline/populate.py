"""Mode B: Template population for production menu outputs."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


JP_SIZE_RATIO = 0.85
JP_OPACITY = 0.65
JP_GAP_REM = 0.2
MIN_FONT_RATIO = 0.85
PRICE_GAP = "  "
SECTION_SLOT_LIMIT = 4
ITEM_SLOT_LIMIT = 8
FULL_WIDTH_BOX_X = 57.0
FULL_WIDTH_BOX_Y = 158.0
FULL_WIDTH_BOX_WIDTH = 498.0
FULL_WIDTH_BOX_HEIGHT = 506.0
WIDE_BOX_WIDTH = 498.0
HALF_BOX_WIDTH = 240.0
DEFAULT_TITLE_X = 306.0
SVG_NS = "{http://www.w3.org/2000/svg}"


def build_menu_data(
    *,
    menu_type: str,
    title: str,
    sections: list[dict[str, Any]],
    food_sections: list[dict[str, Any]] | None = None,
    drinks_sections: list[dict[str, Any]] | None = None,
    show_prices: bool = False,
    footer_note: str | None = None,
) -> dict[str, Any]:
    food = list(food_sections if food_sections is not None else sections)
    drinks = list(drinks_sections if drinks_sections is not None else [])
    data: dict[str, Any] = {
        "schema_version": "2026-04-p1",
        "menu_type": menu_type,
        "title": title,
        "sections": sections,
        "food": {"title": "FOOD MENU", "sections": food},
        "drinks": {"title": "DRINKS MENU", "sections": drinks},
        "show_prices": show_prices,
    }
    if footer_note is not None:
        data["footer_note"] = footer_note
    return data


def build_ticket_data(
    *,
    title: str,
    steps: list[str],
    rows: list[dict[str, Any]],
    footer_note: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": title,
        "steps": steps,
        "rows": rows,
    }
    if footer_note is not None:
        data["footer_note"] = footer_note
    return data


def populate_menu_svg(
    *,
    template_path: Path,
    data: dict[str, Any],
    output_path: Path,
) -> Path:
    tree = ET.parse(str(template_path))
    root = tree.getroot()
    ET.register_namespace("", "http://www.w3.org/2000/svg")

    panel_key = "drinks" if "drinks" in template_path.name else "food"
    panel_data = data.get(panel_key) if isinstance(data.get(panel_key), dict) else {}
    panel_payload = dict(panel_data)
    panel_payload["show_prices"] = bool(data.get("show_prices"))

    _layout_svg_sections(root, panel_payload)
    _populate_svg_items(root, panel_payload)
    _populate_svg_section_titles(root, panel_payload)
    _populate_svg_main_title(root, panel_payload)
    _populate_svg_footer_note(root, data)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(output_path), encoding="unicode", xml_declaration=True)
    return output_path


def populate_ticket_machine_svg(
    *,
    template_path: Path,
    data: dict[str, Any],
    output_path: Path,
) -> Path:
    tree = ET.parse(str(template_path))
    root = tree.getroot()
    svg_text = "{http://www.w3.org/2000/svg}text"

    steps_group = root.find(".//*[@id='how-to-use']")
    if steps_group is not None:
        step_elems = [
            el for el in steps_group.iter(svg_text)
            if "item" in el.get("class", "").split() and "button-item" not in el.get("class", "").split()
        ]
        for i, step_text in enumerate(data.get("steps", [])):
            if i < len(step_elems):
                step_elems[i].text = step_text

    btn_group = root.find(".//*[@id='button-grid']")
    if btn_group is not None:
        btn_elems = [el for el in btn_group.iter(svg_text) if "button-item" in el.get("class", "").split()]
        btn_idx = 0
        for row in data.get("rows", []):
            for button_label in row.get("buttons", []):
                if btn_idx < len(btn_elems):
                    elem = btn_elems[btn_idx]
                    for child in list(elem):
                        elem.remove(child)
                    elem.text = button_label
                    btn_idx += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(output_path), encoding="unicode", xml_declaration=True)
    return output_path


def populate_menu_html(
    *,
    template_path: Path,
    data: dict[str, Any],
    output_path: Path,
    business_name: str | None = None,
) -> Path:
    from .render import render_template_html

    render_data = deepcopy(data)
    render_data.setdefault("footer_note", "")
    html = render_template_html(
        template_path.read_text(encoding="utf-8"),
        render_data,
        business_name=business_name,
        remove_unprovided=True,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def _populate_svg_items(root: ET.Element, data: dict[str, Any]) -> None:
    sections = _render_svg_sections(data)
    slot_defs = _resolve_section_layout(len(sections))
    slots = _extract_svg_section_slots(root)
    show_prices = bool(data.get("show_prices"))
    for slot in slots:
        for elem in slot["item_en"]:
            elem.text = ""
            elem.set("display", "none")
            _restore_base_font_size(elem)
        for elem in slot["item_jp"]:
            elem.text = ""
            elem.set("display", "none")
            _restore_base_font_size(elem)

    for idx, section in enumerate(sections):
        slot = slots[idx]
        slot_def = slot_defs[idx]
        suppress_heading = _section_heading_is_redundant(data, section)
        render_items = _section_render_items(section, slot_def, suppress_heading=suppress_heading)
        item_en_elems = _ensure_item_capacity(root, slot["item_en"], len(render_items), slot_index=idx)
        item_jp_elems = _ensure_item_capacity(root, slot["item_jp"], len(render_items), slot_index=idx)
        slot["item_en"] = item_en_elems
        slot["item_jp"] = item_jp_elems
        for item_idx, render_item in enumerate(render_items):
            item = render_item["item"]
            en_text = _customer_visible_english(item, show_prices=show_prices) if isinstance(item, dict) else str(item)
            ja_text = str(item.get("japanese_name") or item.get("source_text") or "") if isinstance(item, dict) else ""
            en_elem = item_en_elems[item_idx]
            jp_elem = item_jp_elems[item_idx] if item_idx < len(item_jp_elems) else None
            y_value = render_item["y"]
            en_elem.set("display", "inline")
            en_elem.set("x", _fmt(slot_def["item_x"]))
            en_elem.set("y", _fmt(y_value))
            en_elem.set("font-size", _fmt(render_item["item_font"]))
            en_elem.set("_base-font-size", _fmt(render_item["item_font"]))
            en_elem.text = en_text
            if jp_elem is not None:
                jp_elem.set("display", "inline")
                jp_elem.set("x", _fmt(slot_def["jp_x"]))
                jp_elem.set("y", _fmt(y_value))
                jp_elem.set("font-size", _fmt(render_item["jp_font"]))
                jp_elem.set("_base-font-size", _fmt(render_item["jp_font"]))
                jp_elem.set("text-anchor", "end")
                jp_elem.text = ja_text
            _fit_text_to_slot(en_elem, en_text, jp_elem)
            if jp_elem is not None:
                _fit_japanese_text(jp_elem, ja_text)


def _populate_svg_section_titles(root: ET.Element, data: dict[str, Any]) -> None:
    slots = _extract_svg_section_slots(root)
    sections = _render_svg_sections(data)
    slot_defs = _resolve_section_layout(len(sections))
    for slot in slots:
        elem = slot["title"]
        elem.text = ""
    for idx, section in enumerate(sections):
        if idx < len(slots):
            if _section_heading_is_redundant(data, section):
                slots[idx]["title"].text = ""
                _populate_folded_subsection_title(slots, idx, section)
                continue
            typography = _section_typography(slot_defs[idx], len(section.get("items") or []))
            slots[idx]["title"].set("font-size", _fmt(typography["title_font"]))
            slots[idx]["title"].text = str(section.get("title") or "")
            _populate_folded_subsection_title(slots, idx, section)


def _populate_svg_main_title(root: ET.Element, data: dict[str, Any]) -> None:
    title = _effective_panel_title(data)
    svg_text = "{http://www.w3.org/2000/svg}text"
    for elem in root.iter(svg_text):
        if "title" in elem.get("class", "").split():
            elem.text = title
            break


def _populate_svg_footer_note(root: ET.Element, data: dict[str, Any]) -> None:
    footer = str(data.get("footer_note") or "")
    svg_text = "{http://www.w3.org/2000/svg}text"
    for elem in root.iter(svg_text):
        if "footer-note" in (elem.get("id") or ""):
            elem.text = footer
            break


def _customer_visible_english(item: dict[str, Any], *, show_prices: bool = False) -> str:
    english = str(item.get("english_name") or item.get("name") or "").strip()
    price = str(item.get("price") or "").strip()
    if _item_price_should_render(item, show_prices=show_prices) and price:
        return f"{english}{PRICE_GAP}{price}"
    return english


def _item_price_should_render(item: dict[str, Any], *, show_prices: bool) -> bool:
    price = str(item.get("price") or "").strip()
    if not price or not show_prices:
        return False
    if str(item.get("price_visibility") or "").strip() == "intentionally_hidden":
        return False
    return str(item.get("price_status") or "").strip() == "confirmed_by_business"


def _restore_base_font_size(elem: ET.Element) -> None:
    if "_base-font-size" not in elem.attrib:
        elem.set("_base-font-size", elem.get("font-size", "10"))
    elem.set("font-size", elem.get("_base-font-size", elem.get("font-size", "10")))


def _fit_text_to_slot(en_elem: ET.Element, text: str, jp_elem: ET.Element | None) -> None:
    base = float(en_elem.get("_base-font-size", en_elem.get("font-size", "10")) or 10)
    start_x = float(en_elem.get("x", "0") or 0)
    end_x = float(jp_elem.get("x", "543") or 543) if jp_elem is not None else start_x + 210
    max_width = max(60.0, end_x - start_x - 8.0)
    target = base
    while target > base * MIN_FONT_RATIO and _estimated_text_width(text, target) > max_width:
        target -= 0.25
    en_elem.set("font-size", f"{target:.2f}")


def _fit_japanese_text(elem: ET.Element, text: str) -> None:
    _restore_base_font_size(elem)
    if not text:
        return
    base = float(elem.get("_base-font-size", elem.get("font-size", "8.5")) or 8.5)
    max_width = max(60.0, float(elem.get("x", "543") or 543) - 83.0)
    target = base
    while target > base * MIN_FONT_RATIO and _estimated_text_width(text, target, wide=True) > max_width:
        target -= 0.25
    elem.set("font-size", f"{target:.2f}")


def _estimated_text_width(text: str, font_size: float, *, wide: bool = False) -> float:
    factor = 0.56 if not wide else 0.92
    return len(text) * font_size * factor


def _render_svg_sections(data: dict[str, Any]) -> list[dict[str, Any]]:
    sections = list((data.get("sections") or [])[:SECTION_SLOT_LIMIT])
    if not _should_fold_sides_into_ramen(sections):
        return sections

    folded = dict(sections[0])
    folded["_folded_subsections"] = sections[1:]
    return [folded]


def _effective_panel_title(data: dict[str, Any]) -> str:
    title = str(data.get("title") or "")
    sections = _render_svg_sections(data)
    if title.strip().upper() == "FOOD MENU" and len(sections) == 1 and _is_ramen_title(str(sections[0].get("title") or "")):
        return "RAMEN MENU"
    return title


def _section_heading_is_redundant(data: dict[str, Any], section: dict[str, Any]) -> bool:
    panel_title = _normalize_menu_title(_effective_panel_title(data))
    section_title = _normalize_menu_title(str(section.get("title") or ""))
    return panel_title == section_title or panel_title == f"{section_title} MENU"


def _normalize_menu_title(value: str) -> str:
    return " ".join(value.strip().upper().replace("&", "AND").split())


def _should_fold_sides_into_ramen(sections: list[dict[str, Any]]) -> bool:
    if len(sections) < 2:
        return False
    first_title = str(sections[0].get("title") or "")
    if not _is_ramen_title(first_title):
        return False
    return all(_is_side_addon_title(str(section.get("title") or "")) for section in sections[1:])


def _is_ramen_title(title: str) -> bool:
    normalized = title.strip().upper()
    return normalized in {"RAMEN", "NOODLES", "RAMEN MENU"} or "RAMEN" in normalized


def _is_side_addon_title(title: str) -> bool:
    normalized = title.strip().upper().replace("&", "AND")
    side_tokens = ("SIDE", "SMALL PLATE", "ADD-ON", "ADD ON", "TOPPING", "EXTRA")
    return any(token in normalized for token in side_tokens)


def layout_item_capacities(section_count: int) -> list[int]:
    return [slot["item_capacity"] for slot in _resolve_section_layout(section_count)]


def _layout_svg_sections(root: ET.Element, data: dict[str, Any]) -> None:
    sections = _render_svg_sections(data)
    slot_defs = _resolve_section_layout(len(sections))
    slots = _extract_svg_section_slots(root)
    if not sections:
        for slot in slots:
            _set_slot_visible(slot, False)
        return
    for idx, slot in enumerate(slots):
        if idx >= len(slot_defs):
            if idx == 1 and sections and sections[0].get("_folded_subsections"):
                slot["rect"].set("display", "none")
                for elem in slot["item_en"]:
                    elem.set("display", "none")
                for elem in slot["item_jp"]:
                    elem.set("display", "none")
                continue
            _set_slot_visible(slot, False)
            continue
        _set_slot_visible(slot, True)
        slot_def = slot_defs[idx]
        slot["rect"].set("x", _fmt(slot_def["box_x"]))
        slot["rect"].set("y", _fmt(slot_def["box_y"]))
        slot["rect"].set("width", _fmt(slot_def["box_width"]))
        slot["rect"].set("height", _fmt(slot_def["box_height"]))
        slot["title"].set("x", _fmt(slot_def["title_x"]))
        slot["title"].set("y", _fmt(slot_def["title_y"]))
        slot["title"].set("font-size", _fmt(slot_def["title_font"]))
        slot["title"].set("letter-spacing", _fmt(slot_def["title_letter_spacing"]))
        slot["title"].set("text-anchor", "middle")
        slot["underline"].set("x1", _fmt(slot_def["underline_x1"]))
        slot["underline"].set("x2", _fmt(slot_def["underline_x2"]))
        slot["underline"].set("y1", _fmt(slot_def["underline_y"]))
        slot["underline"].set("y2", _fmt(slot_def["underline_y"]))
        section = sections[idx]
        suppress_heading = _section_heading_is_redundant(data, section)
        if suppress_heading:
            slot["title"].set("display", "none")
            slot["underline"].set("display", "none")
        _layout_folded_subsection_title(slots, idx, section, suppress_heading=suppress_heading)


def _layout_folded_subsection_title(
    slots: list[dict[str, Any]],
    idx: int,
    section: dict[str, Any],
    *,
    suppress_heading: bool = False,
) -> None:
    if idx != 0 or not section.get("_folded_subsections") or len(slots) < 2:
        return
    title_y = 468.0 if suppress_heading else 493.0
    underline_y = title_y + 15.0
    sub_slot = slots[1]
    sub_slot["rect"].set("display", "none")
    sub_slot["title"].set("display", "inline")
    sub_slot["title"].set("x", _fmt(DEFAULT_TITLE_X))
    sub_slot["title"].set("y", _fmt(title_y))
    sub_slot["title"].set("font-size", "13.8")
    sub_slot["title"].set("letter-spacing", "1.2")
    sub_slot["title"].set("text-anchor", "middle")
    sub_slot["underline"].set("display", "inline")
    sub_slot["underline"].set("x1", "258.0")
    sub_slot["underline"].set("x2", "354.0")
    sub_slot["underline"].set("y1", _fmt(underline_y))
    sub_slot["underline"].set("y2", _fmt(underline_y))


def _populate_folded_subsection_title(slots: list[dict[str, Any]], idx: int, section: dict[str, Any]) -> None:
    if idx != 0 or not section.get("_folded_subsections") or len(slots) < 2:
        return
    slots[1]["title"].text = "SIDES / ADD-ONS"


def _extract_svg_section_slots(root: ET.Element) -> list[dict[str, Any]]:
    all_rects = [elem for elem in root.iter(f"{SVG_NS}rect") if "stroke" in elem.get("class", "").split()]
    rects = [elem for elem in all_rects if elem.get("data-slot-index") is not None]
    if len(rects) < SECTION_SLOT_LIMIT:
        rects = all_rects[2:2 + SECTION_SLOT_LIMIT]
    titles = [elem for elem in root.iter(f"{SVG_NS}text") if "section" in elem.get("class", "").split()]
    all_underlines = [
        elem for elem in root.iter(f"{SVG_NS}line")
        if "stroke" in elem.get("class", "").split()
        and abs(float(elem.get("x2", "0") or 0) - float(elem.get("x1", "0") or 0)) < 100
    ]
    underlines = [elem for elem in all_underlines if elem.get("data-slot-index") is not None]
    if len(underlines) < SECTION_SLOT_LIMIT:
        underlines = all_underlines[:SECTION_SLOT_LIMIT]
    item_en = [elem for elem in root.iter(f"{SVG_NS}text") if "item-en" in elem.get("class", "").split()]
    item_jp = [elem for elem in root.iter(f"{SVG_NS}text") if "item-jp" in elem.get("class", "").split()]

    for idx, elem in enumerate(rects[:SECTION_SLOT_LIMIT]):
        elem.set("data-slot-index", str(idx))
    for idx, elem in enumerate(titles[:SECTION_SLOT_LIMIT]):
        elem.set("data-slot-index", str(idx))
    for idx, elem in enumerate(underlines[:SECTION_SLOT_LIMIT]):
        elem.set("data-slot-index", str(idx))
    for idx, elem in enumerate(item_en):
        elem.set("data-slot-index", elem.get("data-slot-index") or str(min(idx // ITEM_SLOT_LIMIT, SECTION_SLOT_LIMIT - 1)))
    for idx, elem in enumerate(item_jp):
        elem.set("data-slot-index", elem.get("data-slot-index") or str(min(idx // ITEM_SLOT_LIMIT, SECTION_SLOT_LIMIT - 1)))

    slots: list[dict[str, Any]] = []
    for idx in range(SECTION_SLOT_LIMIT):
        slot_key = str(idx)
        slot_item_en = [elem for elem in item_en if elem.get("data-slot-index") == slot_key]
        slot_item_jp = [elem for elem in item_jp if elem.get("data-slot-index") == slot_key]
        slots.append({
            "rect": next(elem for elem in rects if elem.get("data-slot-index") == slot_key),
            "title": next(elem for elem in titles if elem.get("data-slot-index") == slot_key),
            "underline": next(elem for elem in underlines if elem.get("data-slot-index") == slot_key),
            "item_en": slot_item_en,
            "item_jp": slot_item_jp,
        })
    return slots


def _resolve_section_layout(section_count: int) -> list[dict[str, float]]:
    if section_count <= 1:
        return [{
            "box_x": FULL_WIDTH_BOX_X,
            "box_y": FULL_WIDTH_BOX_Y,
            "box_width": FULL_WIDTH_BOX_WIDTH,
            "box_height": FULL_WIDTH_BOX_HEIGHT,
            "title_x": DEFAULT_TITLE_X,
            "title_y": 205.0,
            "title_font": 19.4,
            "title_letter_spacing": 1.8,
            "underline_x1": 270.0,
            "underline_x2": 342.0,
            "underline_y": 223.0,
            "item_x": 82.0,
            "jp_x": 525.0,
            "item_start_y": 250.0,
            "item_end_y": 590.0,
            "default_step": 30.0,
            "item_font": 11.8,
            "jp_font": 9.4,
            "item_capacity": 14,
            "pack": "center",
        }]
    if section_count == 2:
        return [
            {
                "box_x": FULL_WIDTH_BOX_X,
                "box_y": 144.0,
                "box_width": WIDE_BOX_WIDTH,
                "box_height": 269.0,
                "title_x": DEFAULT_TITLE_X,
                "title_y": 185.0,
                "title_font": 17.0,
                "title_letter_spacing": 1.8,
                "underline_x1": 270.0,
                "underline_x2": 342.0,
                "underline_y": 201.0,
                "item_x": 82.0,
                "jp_x": 525.0,
                "item_start_y": 230.0,
                "item_end_y": 386.0,
                "default_step": 20.0,
                "item_font": 10.0,
                "jp_font": 8.5,
                "item_capacity": 9,
                "pack": "top",
            },
            {
                "box_x": FULL_WIDTH_BOX_X,
                "box_y": 439.0,
                "box_width": WIDE_BOX_WIDTH,
                "box_height": 269.0,
                "title_x": DEFAULT_TITLE_X,
                "title_y": 480.0,
                "title_font": 16.2,
                "title_letter_spacing": 1.2,
                "underline_x1": 270.0,
                "underline_x2": 342.0,
                "underline_y": 496.0,
                "item_x": 82.0,
                "jp_x": 525.0,
                "item_start_y": 525.0,
                "item_end_y": 681.0,
                "default_step": 20.0,
                "item_font": 10.0,
                "jp_font": 8.5,
                "item_capacity": 9,
                "pack": "top",
            },
        ]
    if section_count == 3:
        return [
            {
                "box_x": FULL_WIDTH_BOX_X,
                "box_y": 144.0,
                "box_width": WIDE_BOX_WIDTH,
                "box_height": 269.0,
                "title_x": DEFAULT_TITLE_X,
                "title_y": 185.0,
                "title_font": 17.0,
                "title_letter_spacing": 1.8,
                "underline_x1": 270.0,
                "underline_x2": 342.0,
                "underline_y": 201.0,
                "item_x": 82.0,
                "jp_x": 525.0,
                "item_start_y": 230.0,
                "item_end_y": 386.0,
                "default_step": 20.0,
                "item_font": 10.0,
                "jp_font": 8.5,
                "item_capacity": 9,
                "pack": "top",
            },
            {
                "box_x": 57.0,
                "box_y": 439.0,
                "box_width": HALF_BOX_WIDTH,
                "box_height": 269.0,
                "title_x": 177.0,
                "title_y": 480.0,
                "title_font": 16.2,
                "title_letter_spacing": 1.2,
                "underline_x1": 149.0,
                "underline_x2": 205.0,
                "underline_y": 496.0,
                "item_x": 75.0,
                "jp_x": 285.0,
                "item_start_y": 525.0,
                "item_end_y": 683.0,
                "default_step": 22.6,
                "item_font": 10.0,
                "jp_font": 8.5,
                "item_capacity": 8,
                "pack": "top",
            },
            {
                "box_x": 315.0,
                "box_y": 439.0,
                "box_width": HALF_BOX_WIDTH,
                "box_height": 269.0,
                "title_x": 435.0,
                "title_y": 480.0,
                "title_font": 16.2,
                "title_letter_spacing": 1.2,
                "underline_x1": 407.0,
                "underline_x2": 463.0,
                "underline_y": 496.0,
                "item_x": 333.0,
                "jp_x": 543.0,
                "item_start_y": 525.0,
                "item_end_y": 683.0,
                "default_step": 22.6,
                "item_font": 10.0,
                "jp_font": 8.5,
                "item_capacity": 8,
                "pack": "top",
            },
        ]
    return [
        {
            "box_x": 57.0,
            "box_y": 144.0,
            "box_width": HALF_BOX_WIDTH,
            "box_height": 269.0,
            "title_x": 177.0,
            "title_y": 185.0,
            "title_font": 17.0,
            "title_letter_spacing": 1.8,
            "underline_x1": 149.0,
            "underline_x2": 205.0,
            "underline_y": 201.0,
            "item_x": 75.0,
            "jp_x": 285.0,
            "item_start_y": 230.0,
            "item_end_y": 388.2,
            "default_step": 22.6,
            "item_font": 10.0,
            "jp_font": 8.5,
            "item_capacity": 8,
            "pack": "top",
        },
        {
            "box_x": 315.0,
            "box_y": 144.0,
            "box_width": HALF_BOX_WIDTH,
            "box_height": 269.0,
            "title_x": 435.0,
            "title_y": 185.0,
            "title_font": 17.0,
            "title_letter_spacing": 1.8,
            "underline_x1": 407.0,
            "underline_x2": 463.0,
            "underline_y": 201.0,
            "item_x": 333.0,
            "jp_x": 543.0,
            "item_start_y": 230.0,
            "item_end_y": 388.2,
            "default_step": 22.6,
            "item_font": 10.0,
            "jp_font": 8.5,
            "item_capacity": 8,
            "pack": "top",
        },
        {
            "box_x": 57.0,
            "box_y": 439.0,
            "box_width": HALF_BOX_WIDTH,
            "box_height": 269.0,
            "title_x": 177.0,
            "title_y": 480.0,
            "title_font": 16.2,
            "title_letter_spacing": 1.2,
            "underline_x1": 149.0,
            "underline_x2": 205.0,
            "underline_y": 496.0,
            "item_x": 75.0,
            "jp_x": 285.0,
            "item_start_y": 525.0,
            "item_end_y": 683.2,
            "default_step": 22.6,
            "item_font": 10.0,
            "jp_font": 8.5,
            "item_capacity": 8,
            "pack": "top",
        },
        {
            "box_x": 315.0,
            "box_y": 439.0,
            "box_width": HALF_BOX_WIDTH,
            "box_height": 269.0,
            "title_x": 435.0,
            "title_y": 480.0,
            "title_font": 16.2,
            "title_letter_spacing": 1.2,
            "underline_x1": 407.0,
            "underline_x2": 463.0,
            "underline_y": 496.0,
            "item_x": 333.0,
            "jp_x": 543.0,
            "item_start_y": 525.0,
            "item_end_y": 683.2,
            "default_step": 22.6,
            "item_font": 10.0,
            "jp_font": 8.5,
            "item_capacity": 8,
            "pack": "top",
        },
    ]


def _ensure_item_capacity(root: ET.Element, elems: list[ET.Element], needed: int, *, slot_index: int) -> list[ET.Element]:
    if not elems:
        return elems
    while len(elems) < needed:
        clone = deepcopy(elems[-1])
        clone.set("data-slot-index", str(slot_index))
        root.append(clone)
        elems.append(clone)
    return elems


def _section_render_items(
    section: dict[str, Any],
    slot_def: dict[str, float],
    *,
    suppress_heading: bool = False,
) -> list[dict[str, Any]]:
    if section.get("_folded_subsections"):
        return _folded_ramen_render_items(section, slot_def, suppress_heading=suppress_heading)

    items = list((section.get("items") or [])[: slot_def["item_capacity"]])
    if suppress_heading and slot_def.get("pack") == "center":
        slot_def = dict(slot_def)
        slot_def["item_start_y"] = slot_def["item_start_y"] - 18.0
        slot_def["item_end_y"] = slot_def["item_end_y"] + 18.0
    typography = _section_typography(slot_def, len(items))
    item_ys = _slot_item_ys(slot_def, len(items), line_step=typography["line_step"])
    return [
        {
            "item": item,
            "y": item_ys[item_idx],
            "item_font": typography["item_font"],
            "jp_font": typography["jp_font"],
        }
        for item_idx, item in enumerate(items)
    ]


def _folded_ramen_render_items(
    section: dict[str, Any],
    slot_def: dict[str, float],
    *,
    suppress_heading: bool = False,
) -> list[dict[str, Any]]:
    capacity = int(slot_def["item_capacity"])
    main_items = list(section.get("items") or [])
    subsection_items: list[Any] = []
    for subsection in section.get("_folded_subsections") or []:
        subsection_items.extend(subsection.get("items") or [])

    available_for_subitems = max(0, capacity - len(main_items))
    subitems = subsection_items[:available_for_subitems]
    main_count = len(main_items[:capacity])
    sub_count = len(subitems)
    typography = _folded_ramen_typography(
        main_count=main_count,
        sub_count=sub_count,
        suppress_heading=suppress_heading,
    )

    render_items: list[dict[str, Any]] = []
    main_ys = _distributed_item_ys(
        typography["main_region_start"],
        typography["main_region_end"],
        main_count,
        line_step=typography["main_step"],
    )
    for idx, item in enumerate(main_items[:capacity]):
        render_items.append({
            "item": item,
            "y": main_ys[idx],
            "item_font": typography["main_item_font"],
            "jp_font": typography["main_jp_font"],
        })

    sub_ys = _distributed_item_ys(
        typography["sub_region_start"],
        typography["sub_region_end"],
        sub_count,
        line_step=typography["sub_step"],
    )
    for idx, item in enumerate(subitems):
        render_items.append({
            "item": item,
            "y": sub_ys[idx],
            "item_font": typography["sub_item_font"],
            "jp_font": typography["sub_jp_font"],
        })
    return render_items


def _folded_ramen_typography(
    *,
    main_count: int,
    sub_count: int,
    suppress_heading: bool = False,
) -> dict[str, float]:
    if main_count <= 3:
        main_item_font = 18.2
        main_jp_font = 13.8
        main_step = 52.0
    elif main_count <= 4:
        main_item_font = 17.2
        main_jp_font = 13.2
        main_step = 46.0
    elif main_count <= 6:
        main_item_font = 16.0
        main_jp_font = 12.4
        main_step = 38.0
    else:
        main_item_font = 15.0
        main_jp_font = 11.6
        main_step = 32.0

    if sub_count <= 1:
        sub_item_font = 15.2
        sub_jp_font = 12.0
        sub_step = 0.0
    elif sub_count <= 2:
        sub_item_font = 14.6
        sub_jp_font = 11.6
        sub_step = 40.0
    elif sub_count <= 3:
        sub_item_font = 13.8
        sub_jp_font = 11.0
        sub_step = 34.0
    else:
        sub_item_font = 12.8
        sub_jp_font = 10.4
        sub_step = 28.0

    return {
        "main_item_font": main_item_font,
        "main_jp_font": main_jp_font,
        "main_region_start": 226.0 if suppress_heading else 248.0,
        "main_region_end": 410.0 if suppress_heading else 430.0,
        "main_step": main_step,
        "sub_item_font": sub_item_font,
        "sub_jp_font": sub_jp_font,
        "sub_region_start": 520.0 if suppress_heading else 540.0,
        "sub_region_end": 640.0 if suppress_heading else 656.0,
        "sub_step": sub_step,
    }


def _slot_item_ys(slot_def: dict[str, float], item_count: int, *, line_step: float | None = None) -> list[float]:
    if item_count <= 0:
        return []
    if item_count == 1:
        if slot_def.get("pack") == "center":
            return [(slot_def["item_start_y"] + slot_def["item_end_y"]) / 2]
        return [slot_def["item_start_y"]]
    available_step = (slot_def["item_end_y"] - slot_def["item_start_y"]) / (item_count - 1)
    target_step = line_step if line_step is not None else slot_def["default_step"]
    step = min(target_step, available_step)
    used_height = step * (item_count - 1)
    start_y = slot_def["item_start_y"]
    if slot_def.get("pack") == "center":
        start_y = slot_def["item_start_y"] + ((slot_def["item_end_y"] - slot_def["item_start_y"] - used_height) / 2)
    return [start_y + (step * idx) for idx in range(item_count)]


def _distributed_item_ys(start_y: float, end_y: float, item_count: int, *, line_step: float) -> list[float]:
    if item_count <= 0:
        return []
    if item_count == 1:
        return [(start_y + end_y) / 2]
    available_step = (end_y - start_y) / (item_count - 1)
    step = min(line_step, available_step)
    used_height = step * (item_count - 1)
    actual_start = start_y + ((end_y - start_y - used_height) / 2)
    return [actual_start + (step * idx) for idx in range(item_count)]


def _set_slot_visible(slot: dict[str, Any], visible: bool) -> None:
    display = "inline" if visible else "none"
    slot["rect"].set("display", display)
    slot["title"].set("display", display)
    slot["underline"].set("display", display)
    for elem in slot["item_en"]:
        elem.set("display", "none")
    for elem in slot["item_jp"]:
        elem.set("display", "none")


def _fmt(value: float) -> str:
    return f"{value:.1f}"


def _section_typography(slot_def: dict[str, float], item_count: int) -> dict[str, float]:
    if slot_def.get("pack") != "center":
        return {
            "title_font": slot_def["title_font"],
            "item_font": slot_def["item_font"],
            "jp_font": slot_def["jp_font"],
            "line_step": slot_def["default_step"],
        }

    if item_count <= 3:
        return {"title_font": 26.0, "item_font": 19.5, "jp_font": 14.4, "line_step": 50.0}
    if item_count <= 5:
        return {"title_font": 24.5, "item_font": 18.0, "jp_font": 13.6, "line_step": 44.0}
    if item_count <= 7:
        return {"title_font": 23.0, "item_font": 16.8, "jp_font": 12.8, "line_step": 50.0}
    if item_count <= 10:
        return {"title_font": 21.5, "item_font": 15.2, "jp_font": 11.6, "line_step": 34.0}
    return {"title_font": 20.2, "item_font": 13.6, "jp_font": 10.4, "line_step": 28.0}
