"""Mode B: Template population — inject translated content into locked templates.

Populates SVG and HTML templates with translated menu items and bilingual labels.
Never changes box geometry, borders, fonts (families), colors, spacing, or ornaments.
"""

from __future__ import annotations

import json
import re
from html import escape as html_esc
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


# ---------------------------------------------------------------------------
# Bilingual label styling constants
# ---------------------------------------------------------------------------
JP_SIZE_RATIO = 0.85  # 85% of English text size
JP_OPACITY = 0.65     # 65% opacity
JP_GAP_REM = 0.2      # 0.2rem gap below English
MIN_FONT_RATIO = 0.85  # minimum 85% of base size for overflow


# ---------------------------------------------------------------------------
# Menu data builders
# ---------------------------------------------------------------------------

def build_menu_data(
    *,
    menu_type: str,
    title: str,
    sections: list[dict[str, Any]],
    show_prices: bool = False,
    footer_note: str | None = None,
) -> dict[str, Any]:
    """Build a JSON dict matching menu_schema.json from translated items."""
    data: dict[str, Any] = {
        "menu_type": menu_type,
        "title": title,
        "sections": sections,
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
    """Build a JSON dict matching ticket_machine_guide_schema.json."""
    data: dict[str, Any] = {
        "title": title,
        "steps": steps,
        "rows": rows,
    }
    if footer_note is not None:
        data["footer_note"] = footer_note
    return data


# ---------------------------------------------------------------------------
# SVG population
# ---------------------------------------------------------------------------

def populate_menu_svg(
    *,
    template_path: Path,
    data: dict[str, Any],
    output_path: Path,
) -> Path:
    """Load an SVG menu template, populate content slots, write to output.

    Replaces text content in XML elements identified by ID or class.
    Applies bilingual styling to item text.
    """
    tree = ET.parse(str(template_path))
    root = tree.getroot()

    # Register SVG namespace
    ns = {"svg": "http://www.w3.org/2000/svg"}
    for prefix, uri in ns.items():
        ET.register_namespace(prefix, uri)

    # Find and replace item text elements
    _populate_svg_items(root, data, ns)

    # Find and replace section title elements
    _populate_svg_section_titles(root, data, ns)

    # Replace main title
    _populate_svg_main_title(root, data, ns)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(output_path), encoding="unicode", xml_declaration=True)
    return output_path


def populate_ticket_machine_svg(
    *,
    template_path: Path,
    data: dict[str, Any],
    output_path: Path,
) -> Path:
    """Populate a ticket machine guide SVG template using CSS class selectors."""
    tree = ET.parse(str(template_path))
    root = tree.getroot()

    svg_text = "{http://www.w3.org/2000/svg}text"

    # Populate steps: find text elements inside <g id="how-to-use">
    steps_group = root.find(".//*[@id='how-to-use']")
    if steps_group is not None:
        step_elems = [
            el for el in steps_group.iter(svg_text)
            if "item" in el.get("class", "").split()
               and "button-item" not in el.get("class", "").split()
        ]
        for i, step_text in enumerate(data.get("steps", [])):
            if i < len(step_elems):
                step_elems[i].text = step_text

    # Populate button labels: find button-item text elements inside <g id="button-grid">
    btn_group = root.find(".//*[@id='button-grid']")
    if btn_group is not None:
        btn_elems = [
            el for el in btn_group.iter(svg_text)
            if "button-item" in el.get("class", "").split()
        ]
        btn_idx = 0
        for row in data.get("rows", []):
            for button_label in row.get("buttons", []):
                if btn_idx < len(btn_elems):
                    elem = btn_elems[btn_idx]
                    # Clear any existing tspan children
                    for child in list(elem):
                        elem.remove(child)
                    elem.text = button_label
                    btn_idx += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(output_path), encoding="unicode", xml_declaration=True)
    return output_path


# ---------------------------------------------------------------------------
# HTML population
# ---------------------------------------------------------------------------

def populate_menu_html(
    *,
    template_path: Path,
    data: dict[str, Any],
    output_path: Path,
) -> Path:
    """Load an HTML menu template, populate data-slots, write to output.

    Uses the regex-based replacement pattern from render.py.
    Injects bilingual content into data-slot elements.
    """
    html = template_path.read_text(encoding="utf-8")

    # Replace panel titles
    for panel_key in ("food", "drinks"):
        panel_id = f"{panel_key}-panel"
        panel_data = data.get(panel_key)
        if panel_data:
            html = _replace_html_panel_title(html, panel_id, panel_data.get("title", ""))

    # Replace sections
    sections = data.get("sections", [])
    for section in sections:
        section_id = section.get("data_section", section.get("title", "").lower().replace(" ", "-"))
        items = section.get("items", [])
        heading = section.get("title", "")
        items_text = []
        for item in items:
            if isinstance(item, dict):
                en = item.get("name", "")
                ja = item.get("japanese_name", "")
                price = item.get("price", "")
                if ja and ja != en:
                    items_text.append(
                        f'{html_esc(en)} <span class="ja-label" style="font-size:{JP_SIZE_RATIO * 100:.0f}%;opacity:{JP_OPACITY};display:block;margin-top:{JP_GAP_REM}rem;font-weight:400">{html_esc(ja)}</span>'
                    )
                else:
                    items_text.append(html_esc(en))
            else:
                items_text.append(html_esc(str(item)))

        html = _replace_html_section(html, section_id, heading, items_text)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# Internal helpers — SVG
# ---------------------------------------------------------------------------

def _populate_svg_items(root: ET.Element, data: dict, ns: dict) -> None:
    """Replace item text in SVG elements using CSS class selectors."""
    svg_text = "{http://www.w3.org/2000/svg}text"

    # Collect item-en and item-jp elements in document order
    en_elems: list[ET.Element] = []
    jp_elems: list[ET.Element] = []
    for elem in root.iter(svg_text):
        classes = elem.get("class", "").split()
        if "item-en" in classes:
            en_elems.append(elem)
        elif "item-jp" in classes:
            jp_elems.append(elem)

    # Map data items to elements sequentially
    elem_idx = 0
    for section in data.get("sections", []):
        for item in section.get("items", []):
            if elem_idx >= len(en_elems):
                break
            if isinstance(item, dict):
                en_name = item.get("name", "")
                ja_name = item.get("japanese_name", "")
            else:
                en_name = str(item)
                ja_name = ""

            en_elems[elem_idx].text = en_name
            if elem_idx < len(jp_elems) and ja_name:
                jp_elems[elem_idx].text = ja_name
            elem_idx += 1


def _populate_svg_section_titles(root: ET.Element, data: dict, ns: dict) -> None:
    """Replace section title text in SVG elements using CSS class selectors."""
    svg_text = "{http://www.w3.org/2000/svg}text"
    section_elems = [
        elem for elem in root.iter(svg_text)
        if "section" in elem.get("class", "").split()
    ]
    for idx, section in enumerate(data.get("sections", [])):
        if idx < len(section_elems):
            section_elems[idx].text = section.get("title", "")


def _populate_svg_main_title(root: ET.Element, data: dict, ns: dict) -> None:
    """Replace the main menu title using CSS class selector."""
    title = data.get("title", "")
    svg_text = "{http://www.w3.org/2000/svg}text"
    for elem in root.iter(svg_text):
        if "title" in elem.get("class", "").split():
            elem.text = title
            break


# ---------------------------------------------------------------------------
# Internal helpers — HTML
# ---------------------------------------------------------------------------

def _replace_html_section(html: str, data_section: str, heading: str, items: list[str]) -> str:
    """Replace section content in HTML template."""
    # v2 layout: section-header-group wrapper
    pattern_v2 = re.compile(
        rf'(<div\s+class="section"\s+data-section="{re.escape(data_section)}"\s*>\s*)'
        r'(<div\s+class="section-header-group">).*?(</div>\s*)'
        r'(<ul\s+class="menu-items"[^>]*>).*?(</ul>)',
        re.DOTALL,
    )

    items_html = "\n".join(
        f'          <li data-slot="item">{item}</li>' for item in items
    )

    replacement = (
        rf'\g<1>'
        rf'<div class="section-header-group">\n'
        rf'            <h2 class="section-header" data-slot="section-title">{html_esc(heading)}</h2>\n'
        rf'          </div>\n'
        rf'          <ul class="menu-items" data-slot="section-items">\n'
        f'{items_html}\n'
        rf'          </ul>'
    )

    result, count = pattern_v2.subn(replacement, html, count=1)
    if count > 0:
        return result

    # v1 fallback: bare h2 + ul
    pattern_v1 = re.compile(
        rf'(<div\s+class="section"\s+data-section="{re.escape(data_section)}"\s*>\s*)'
        r'(<h2\s+class="section-header"[^>]*>).*?(</h2>\s*)'
        r'(<ul\s+class="menu-items"[^>]*>).*?(</ul>)',
        re.DOTALL,
    )
    replacement_v1 = (
        rf'\g<1>'
        rf'<h2 class="section-header" data-slot="section-title">{html_esc(heading)}</h2>\n'
        rf'        <ul class="menu-items" data-slot="section-items">\n'
        f'{items_html}\n'
        rf'        </ul>'
    )

    result, count = pattern_v1.subn(replacement_v1, html, count=1)
    return result


def _replace_html_panel_title(html: str, panel_id: str, title: str) -> str:
    """Replace panel title text in HTML template."""
    pattern = re.compile(
        rf'(<div\s+class="menu-panel"\s+id="{re.escape(panel_id)}">.*?'
        rf'<h1\s+class="menu-title"\s+data-slot="panel-title">)(.*?)(</h1>)',
        re.DOTALL,
    )
    return pattern.sub(rf'\g<1>{html_esc(title)}\3', html, count=1)
