"""Render menu and ordering HTML from structured content + slot templates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lxml import etree, html as lxml_html

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "assets" / "templates"
MASTER_TEMPLATE = TEMPLATES_DIR / "izakaya_food_drinks_menu.html"
DEFAULT_CONTENT = TEMPLATES_DIR / "menu_content.json"
SAMPLE_SEAL_TEXT = "見本"
ALLOWED_PRICE_STATUSES = {
    "unknown",
    "detected_in_source",
    "pending_business_confirmation",
    "confirmed_by_business",
}
FORBIDDEN_CUSTOMER_TERMS = (
    "".join(chr(code) for code in (72, 86, 65, 67)),
    "automation",
    "scraping",
    "internal tools",
    "source policy",
    "Codex",
)
FAKE_RESTAURANT_MARKERS = (
    "博多らーめん亭",
    "隠れ家Bistro",
)


def _load_content(path: str | None) -> dict:
    src = Path(path) if path else DEFAULT_CONTENT
    with open(src, encoding="utf-8") as f:
        return json.load(f)


def normalize_render_content(
    data: dict[str, Any],
    *,
    business_name: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    """Return a canonical menu content shape used by HTML/SVG renderers."""
    normalized = dict(data or {})
    if business_name is not None:
        normalized["business_name"] = business_name
        normalized.setdefault("store_name", business_name)
    normalized.setdefault("business_name", normalized.get("store_name") or "")
    normalized.setdefault("store_name", normalized.get("business_name") or "")
    normalized.setdefault("profile", profile or normalized.get("menu_type") or "")
    normalized.setdefault("sections", [])
    normalized.setdefault("rule_blocks", normalized.get("rules") or [])
    normalized.setdefault("photos", [])
    normalized.setdefault("qr_data", normalized.get("qr") or {})
    normalized.setdefault("ticket_machine_mapping", normalized.get("ticket_machine") or {})
    normalized.setdefault("show_prices", False)
    if "food" not in normalized and normalized.get("sections"):
        normalized["food"] = {
            "title": normalized.get("title") or "Food Menu",
            "sections": normalized.get("sections") or [],
        }
    if "drinks" not in normalized:
        normalized["drinks"] = {"title": "Drinks Menu", "sections": []}
    return normalized


def validate_render_content_schema(data: dict[str, Any]) -> list[str]:
    """Validate the shared structured content schema for renderable outputs."""
    errors: list[str] = []
    content = normalize_render_content(data)
    if not str(content.get("business_name") or content.get("store_name") or "").strip():
        errors.append("business_name_missing")
    if not str(content.get("profile") or "").strip():
        errors.append("profile_missing")

    sections = _all_content_sections(content)
    if not sections:
        errors.append("sections_missing")
    for index, section in enumerate(sections):
        prefix = f"sections[{index}]"
        if not str(section.get("data_section") or section.get("title") or section.get("heading") or "").strip():
            errors.append(f"{prefix}.data_section_missing")
        items = section.get("items")
        if not isinstance(items, list):
            errors.append(f"{prefix}.items_not_list")
            continue
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            item_prefix = f"{prefix}.items[{item_index}]"
            if not str(item.get("japanese_name") or item.get("source_text") or "").strip():
                errors.append(f"{item_prefix}.japanese_name_missing")
            if not str(item.get("english_name") or item.get("name") or item.get("label") or "").strip():
                errors.append(f"{item_prefix}.english_label_missing")
            price_status = str(item.get("price_status") or "unknown").strip()
            if price_status not in ALLOWED_PRICE_STATUSES:
                errors.append(f"{item_prefix}.price_status_invalid")
    if not isinstance(content.get("photos"), list):
        errors.append("photos_not_list")
    if not isinstance(content.get("rule_blocks"), list):
        errors.append("rule_blocks_not_list")
    if not isinstance(content.get("qr_data"), dict):
        errors.append("qr_data_not_object")
    if not isinstance(content.get("ticket_machine_mapping"), dict):
        errors.append("ticket_machine_mapping_not_object")
    return errors


def validate_template_contract(template_path: Path) -> list[str]:
    """Validate one active HTML template against the Run 5 slot contract."""
    errors: list[str] = []
    text = template_path.read_text(encoding="utf-8")
    doc = _parse_document(text)
    body = _first(doc.xpath("//body"))
    visible_text = _visible_text(doc)
    slots = {str(el.get("data-slot") or "") for el in doc.xpath("//*[@data-slot]")}
    is_menu = "_menu" in template_path.stem
    is_qr = "qr" in template_path.stem
    is_ticket = "ticket_machine" in template_path.stem

    if body is None:
        errors.append("body_missing")
    elif not str(body.get("data-profile") or "").strip():
        errors.append("body_data_profile_missing")

    if "seal" not in slots or "seal-text" not in slots:
        errors.append("seal_slots_missing")
    if is_menu and "section-title" not in slots:
        errors.append("section_title_slots_missing")
    if is_menu and "section-items" not in slots:
        errors.append("section_item_slots_missing")
    if is_ticket and "button-grid" not in slots:
        errors.append("button_grid_slot_missing")
    if is_qr and "qr-code" not in slots:
        errors.append("qr_code_slot_missing")
    if "@media print" not in text or "@page" not in text:
        errors.append("print_css_missing")
    if "max-width: 760px" not in text and "@media (max-width" not in text:
        errors.append("mobile_css_missing")
    if is_menu:
        for section in doc.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " section ")]'):
            if not str(section.get("data-section") or "").strip():
                errors.append("section_data_section_missing")
                break
    if _contains_forbidden_customer_term(visible_text):
        errors.append("forbidden_customer_wording")
    if any(marker in visible_text for marker in FAKE_RESTAURANT_MARKERS):
        errors.append("fake_restaurant_marker")
    if _contains_visible_fake_price(doc):
        errors.append("fake_price_visible")
    _validate_images(doc, template_path.parent, errors)
    return errors


def validate_rendered_html(html_text: str, *, template_path: Path | None = None) -> list[str]:
    """Run lightweight structural validation on rendered HTML output."""
    errors: list[str] = []
    doc = _parse_document(html_text)
    visible_text = _visible_text(doc)
    slots = {str(el.get("data-slot") or "") for el in doc.xpath("//*[@data-slot]")}
    if _contains_forbidden_customer_term(visible_text):
        errors.append("forbidden_customer_wording")
    for marker in ("[[", "OCR required", "menu image detected"):
        if marker in visible_text:
            errors.append("stale_placeholder_visible")
            break
    for section in doc.xpath('//*[@data-section]'):
        items = section.xpath('.//*[@data-slot="item"]')
        if len(items) > 18:
            errors.append(f"section_overflow:{section.get('data-section')}")
    for element in doc.xpath("//*[text()]"):
        tag = str(element.tag).lower()
        if tag in {"script", "style", "template"} or isinstance(element, etree._Comment):
            continue
        text = (element.text or "").strip()
        if any(len(word) > 42 for word in text.split()):
            errors.append("long_unbreakable_text")
            break
    if "qr-code" in slots:
        qr = _first(doc.xpath('//*[@data-slot="qr-code"]'))
        if qr is not None and not qr.xpath(".//*[name()='svg' or self::img or name()='img']"):
            errors.append("qr_code_missing_rendered_payload")
    if template_path is not None:
        _validate_images(doc, template_path.parent, errors)
    return errors


def render_template_html(
    template_html: str,
    content: dict[str, Any],
    *,
    business_name: str | None = None,
    remove_unprovided: bool = False,
    strict: bool = False,
) -> str:
    """Render an HTML template by mutating declared `data-slot` elements."""
    normalized = normalize_render_content(content, business_name=business_name)
    schema_errors = validate_render_content_schema(normalized)
    if strict and schema_errors:
        raise ValueError("Invalid render content: " + ", ".join(schema_errors))

    doc = _parse_document(template_html)
    _apply_body_metadata(doc, normalized)
    _apply_layout_metadata(doc, normalized)
    if business_name or normalized.get("business_name"):
        _mutate_seal(doc, str(business_name or normalized.get("business_name") or ""))
    _render_panel_content(doc, normalized)
    _render_ticket_machine(doc, normalized)
    _render_qr_slots(doc, normalized)
    if remove_unprovided:
        _remove_unprovided_sections(doc, normalized)
        _remove_unused_drinks_panel(doc, normalized)

    rendered = _serialize_document(doc)
    render_errors = validate_rendered_html(rendered)
    if strict and render_errors:
        raise ValueError("Invalid rendered HTML: " + ", ".join(render_errors))
    return rendered


def _replace_section(html: str, data_section: str, heading: str,
                     items: list, sub: str = "", *,
                     show_prices: bool = False) -> str:
    """Compatibility wrapper for replacing one `data-section` via DOM slots."""
    doc = _parse_document(html)
    section = _find_section(doc, data_section)
    if section is None:
        import sys
        print(f"  warning: section '{data_section}' not found in template", file=sys.stderr)
        return html
    payload = {
        "data_section": data_section,
        "heading": heading,
        "sub": sub,
        "items": items,
    }
    _mutate_section(section, payload, show_prices=show_prices)
    return _serialize_document(doc)


def _build_v4c_items_html(items: list, *, show_prices: bool = False) -> str:
    """Build bilingual item HTML for legacy callers."""
    parts = []
    for item in items:
        if isinstance(item, dict):
            en = _item_english(item)
            jp = _item_japanese(item)
            price_span = f'<span class="item-price">{_escape(_item_price(item))}</span>' if _item_price_should_render(item, show_prices=show_prices) else ""
            if jp:
                parts.append(
                    f'<li data-slot="item"><span class="item-en">{_escape(en)}</span>'
                    f'{price_span}<span class="item-jp">{_escape(jp)}</span></li>'
                )
            else:
                parts.append(
                    f'<li data-slot="item"><span class="item-en">{_escape(en)}</span>{price_span}</li>'
                )
        else:
            parts.append(
                f'<li data-slot="item"><span class="item-en">{_escape(str(item))}</span></li>'
            )
    return "\n".join(f"          {p}" for p in parts)


def _replace_panel_title(html: str, panel_id: str, title: str) -> str:
    """Replace the panel title text within a specific panel via DOM slots."""
    doc = _parse_document(html)
    panel = _first(doc.xpath(f'//*[@id={_xpath_literal(panel_id)}]'))
    if panel is None:
        return html
    title_el = _find_panel_title(panel)
    if title_el is not None:
        _set_text_preserving_tail(title_el, title)
    return _serialize_document(doc)


def replace_seal_text(html: str, business_name: str) -> str:
    """Normalize seal stamp text to the generic sample mark."""
    doc = _parse_document(html)
    _mutate_seal(doc, business_name)
    return _serialize_document(doc)


def render(
    content_path: str | None = None,
    template_path: str | None = None,
    business_name: str | None = None,
) -> str:
    """Render the master template with JSON content. Returns final HTML string."""
    tpl_path = Path(template_path) if template_path else MASTER_TEMPLATE
    with open(tpl_path, encoding="utf-8") as f:
        template_html = f.read()

    content = _load_content(content_path)
    return render_template_html(template_html, content, business_name=business_name)


def _parse_document(html_text: str) -> etree._Element:
    parser = lxml_html.HTMLParser(encoding="utf-8")
    return lxml_html.document_fromstring(html_text, parser=parser)


def _serialize_document(doc: etree._Element) -> str:
    rendered = lxml_html.tostring(doc, encoding="unicode", method="html")
    if not rendered.lstrip().lower().startswith("<!doctype"):
        rendered = "<!DOCTYPE html>\n" + rendered
    return rendered


def _first(items: list[Any]) -> Any | None:
    return items[0] if items else None


def _xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    return "concat(" + ", \"'\", ".join(f"'{part}'" for part in value.split("'")) + ")"


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _class_tokens(element: etree._Element) -> set[str]:
    return set(str(element.get("class") or "").split())


def _has_class(element: etree._Element, class_name: str) -> bool:
    return class_name in _class_tokens(element)


def _set_text_preserving_tail(element: etree._Element, text: str) -> None:
    for child in list(element):
        element.remove(child)
    element.text = str(text)


def _visible_text(doc: etree._Element) -> str:
    hidden_tags = {"script", "style", "template"}
    parts: list[str] = []
    for element in doc.iter():
        tag = str(element.tag).lower()
        if tag in hidden_tags or isinstance(element, etree._Comment):
            continue
        if element.text:
            parts.append(element.text)
    return " ".join(" ".join(parts).split())


def _contains_forbidden_customer_term(text: str) -> bool:
    lower = text.lower()
    if any(term.lower() in lower for term in FORBIDDEN_CUSTOMER_TERMS if term != "AI"):
        return True
    tokens = {token.strip(".,:;!?()[]{}").upper() for token in text.split()}
    return "AI" in tokens


def _contains_visible_fake_price(doc: etree._Element) -> bool:
    for element in doc.iter():
        tag = str(element.tag).lower()
        if tag in {"script", "style", "template"} or isinstance(element, etree._Comment):
            continue
        text = element.text or ""
        if "¥" in text or "円" in text:
            return True
    return False


def _validate_images(doc: etree._Element, base_dir: Path, errors: list[str]) -> None:
    for image in doc.xpath("//img[@src]"):
        src = str(image.get("src") or "").strip()
        if not src or src.startswith(("http://", "https://", "data:", "/", "#")):
            continue
        if not (base_dir / src).exists():
            errors.append(f"broken_image:{src}")


def _all_content_sections(content: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for key in ("food", "drinks"):
        panel = content.get(key)
        if isinstance(panel, dict):
            sections.extend([s for s in panel.get("sections") or [] if isinstance(s, dict)])
    if not sections:
        sections.extend([s for s in content.get("sections") or [] if isinstance(s, dict)])
    return sections


def _apply_body_metadata(doc: etree._Element, content: dict[str, Any]) -> None:
    body = _first(doc.xpath("//body"))
    if body is None:
        return
    profile = str(content.get("profile") or "").strip()
    if profile:
        body.set("data-profile", profile)


def _apply_layout_metadata(doc: etree._Element, content: dict[str, Any]) -> None:
    body = _first(doc.xpath("//body"))
    if body is None:
        return
    sections = _all_content_sections(content)
    item_count = sum(len(section.get("items") or []) for section in sections)
    longest = 0
    for section in sections:
        for item in section.get("items") or []:
            text = _item_english(item) if isinstance(item, dict) else str(item)
            longest = max(longest, len(text))
    body.set("data-density", "dense" if item_count >= 28 else "sparse" if item_count <= 8 else "standard")
    body.set("data-long-names", "true" if longest >= 28 else "false")


def _mutate_seal(doc: etree._Element, business_name: str) -> None:
    length = str(len(SAMPLE_SEAL_TEXT))
    for seal in doc.xpath('//*[@data-slot="seal" or contains(concat(" ", normalize-space(@class), " "), " seal-stamp ")]'):
        seal.set("data-length", length)
    for seal_text in doc.xpath('//*[@data-slot="seal-text"]'):
        _set_text_preserving_tail(seal_text, SAMPLE_SEAL_TEXT)


def _render_panel_content(doc: etree._Element, content: dict[str, Any]) -> None:
    for panel_key in ("food", "drinks"):
        panel_data = content.get(panel_key)
        if not isinstance(panel_data, dict):
            continue
        panel = _find_panel(doc, panel_key)
        if panel is None:
            continue
        title = str(panel_data.get("title") or "").strip()
        title_el = _find_panel_title(panel)
        if title and title_el is not None:
            _set_text_preserving_tail(title_el, title)
        for section in panel_data.get("sections") or []:
            if isinstance(section, dict):
                _render_section(doc, section, show_prices=bool(content.get("show_prices")))

    if not any(isinstance(content.get(key), dict) and (content.get(key) or {}).get("sections") for key in ("food", "drinks")):
        for section in content.get("sections") or []:
            if isinstance(section, dict):
                _render_section(doc, section, show_prices=bool(content.get("show_prices")))


def _find_panel(doc: etree._Element, panel_key: str) -> etree._Element | None:
    panel_id = f"{panel_key}-panel"
    panel = _first(doc.xpath(f'//*[@id={_xpath_literal(panel_id)}]'))
    if panel is not None:
        return panel
    return _first(doc.xpath(f'//*[@data-panel={_xpath_literal(panel_key)}]'))


def _find_panel_title(panel: etree._Element) -> etree._Element | None:
    title = _first(panel.xpath('.//*[@data-slot="panel-title"]'))
    if title is not None:
        return title
    title = _first(panel.xpath('.//*[self::h1 or self::h2][contains(concat(" ", normalize-space(@class), " "), " menu-title ")]'))
    if title is not None:
        return title
    return _first(panel.xpath('.//*[self::h1 or self::h2][contains(concat(" ", normalize-space(@class), " "), " guide-title ")]'))


def _render_section(doc: etree._Element, section_payload: dict[str, Any], *, show_prices: bool) -> None:
    data_section = str(section_payload.get("data_section") or section_payload.get("id") or "").strip()
    if not data_section:
        data_section = _slug(str(section_payload.get("title") or section_payload.get("heading") or "section"))
        section_payload = dict(section_payload)
        section_payload["data_section"] = data_section
    section_el = _find_section(doc, data_section)
    if section_el is not None:
        _mutate_section(section_el, section_payload, show_prices=show_prices)


def _find_section(doc: etree._Element, data_section: str) -> etree._Element | None:
    return _first(doc.xpath(f'//*[@data-section={_xpath_literal(data_section)}]'))


def _mutate_section(section_el: etree._Element, section_payload: dict[str, Any], *, show_prices: bool) -> None:
    heading = str(section_payload.get("heading") or section_payload.get("title") or "").strip()
    sub = str(section_payload.get("sub") or section_payload.get("description") or "").strip()
    japanese_title = str(section_payload.get("japanese_title") or section_payload.get("japanese_name") or "").strip()
    title_el = _find_section_title(section_el)
    if title_el is not None and heading:
        _set_section_title(title_el, heading, japanese_title=japanese_title)
    kanji_el = _first(section_el.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " section-kanji ")]'))
    if kanji_el is not None and japanese_title:
        _set_text_preserving_tail(kanji_el, japanese_title)
    if sub:
        _set_section_subtitle(section_el, sub)

    items_el = _find_section_items(section_el)
    if items_el is None:
        return
    style = _item_style(items_el)
    for child in list(items_el):
        items_el.remove(child)
    for item in section_payload.get("items") or []:
        items_el.append(_build_item_element(item, style=style, show_prices=show_prices))


def _find_section_title(section_el: etree._Element) -> etree._Element | None:
    title = _first(section_el.xpath('.//*[@data-slot="section-title"]'))
    if title is not None:
        return title
    title = _first(section_el.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " section-title ")]'))
    if title is not None:
        return title
    return _first(section_el.xpath(".//*[self::h2 or self::h3]"))


def _set_section_title(title_el: etree._Element, heading: str, *, japanese_title: str = "") -> None:
    children = list(title_el)
    if not children:
        title_el.text = heading
        return
    title_el.text = f"{heading} "
    if japanese_title:
        children[0].text = japanese_title


def _set_section_subtitle(section_el: etree._Element, sub: str) -> None:
    sub_el = _first(section_el.xpath('.//*[@data-slot="section-sub"]'))
    if sub_el is None:
        sub_el = _first(section_el.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " section-sub ")]'))
    if sub_el is not None:
        _set_text_preserving_tail(sub_el, sub)


def _find_section_items(section_el: etree._Element) -> etree._Element | None:
    items = _first(section_el.xpath('.//*[@data-slot="section-items"]'))
    if items is not None:
        return items
    items = _first(section_el.xpath('.//*[self::ul or self::ol][contains(concat(" ", normalize-space(@class), " "), " menu-items ")]'))
    if items is not None:
        return items
    return _first(section_el.xpath(".//ul"))


def _item_style(items_el: etree._Element) -> str:
    sample = _first(items_el.xpath('.//*[@data-slot="item"]'))
    if sample is None:
        sample = _first(items_el.xpath("./li"))
    if sample is not None and sample.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " item-en ")]'):
        return "v4c"
    return "compact"


def _build_item_element(item: Any, *, style: str, show_prices: bool) -> etree._Element:
    item_data = item if isinstance(item, dict) else {"english_name": str(item), "japanese_name": ""}
    li = lxml_html.Element("li")
    li.set("data-slot", "item")
    english = _item_english(item_data)
    japanese = _item_japanese(item_data)
    price = _item_price(item_data)
    render_price = _item_price_should_render(item_data, show_prices=show_prices)
    if style == "v4c":
        en_span = lxml_html.Element("span")
        en_span.set("class", "item-en")
        en_span.text = english
        li.append(en_span)
        if render_price and price:
            price_span = lxml_html.Element("span")
            price_span.set("class", "item-price")
            price_span.text = price
            li.append(price_span)
        if japanese:
            jp_span = lxml_html.Element("span")
            jp_span.set("class", "item-jp")
            jp_span.text = japanese
            li.append(jp_span)
        return li

    en_span = lxml_html.Element("span")
    en_span.text = english
    li.append(en_span)
    if render_price and price:
        price_span = lxml_html.Element("span")
        price_span.set("class", "price")
        price_span.text = price
        li.append(price_span)
    if japanese:
        jp_span = lxml_html.Element("span")
        jp_span.set("class", "jp")
        jp_span.text = japanese
        li.append(jp_span)
    return li


def _item_english(item: dict[str, Any]) -> str:
    return str(item.get("english_name") or item.get("name") or item.get("label") or "").strip()


def _item_japanese(item: dict[str, Any]) -> str:
    return str(item.get("japanese_name") or item.get("source_text") or "").strip()


def _item_price(item: dict[str, Any]) -> str:
    return str(item.get("price") or "").strip()


def _item_price_should_render(item: dict[str, Any], *, show_prices: bool) -> bool:
    price = _item_price(item)
    if not price or not show_prices:
        return False
    if str(item.get("price_visibility") or "").strip() == "intentionally_hidden":
        return False
    return str(item.get("price_status") or "").strip() == "confirmed_by_business"


def _render_ticket_machine(doc: etree._Element, content: dict[str, Any]) -> None:
    mapping = content.get("ticket_machine_mapping")
    if not isinstance(mapping, dict):
        return
    title = str(mapping.get("title") or content.get("title") or "").strip()
    title_el = _first(doc.xpath('//*[@data-slot="panel-title"]'))
    if title and title_el is not None:
        _set_text_preserving_tail(title_el, title)

    steps = mapping.get("steps") or content.get("steps") or []
    step_labels = doc.xpath('//*[@data-slot="steps"]//*[contains(concat(" ", normalize-space(@class), " "), " step-label ")]')
    for index, step in enumerate(steps):
        if index < len(step_labels):
            _set_text_preserving_tail(step_labels[index], str(step))

    rows = mapping.get("rows") or content.get("rows") or []
    buttons: list[Any] = []
    for row in rows:
        if isinstance(row, dict):
            buttons.extend(row.get("buttons") or [])
        elif isinstance(row, list):
            buttons.extend(row)
    button_slots = doc.xpath('//*[@data-slot="button"]')
    for index, button in enumerate(buttons):
        if index >= len(button_slots):
            break
        _mutate_machine_button(button_slots[index], button)


def _mutate_machine_button(button_el: etree._Element, button: Any) -> None:
    if isinstance(button, dict):
        english = str(button.get("english_name") or button.get("name") or button.get("label") or button.get("en") or "").strip()
        japanese = str(button.get("japanese_name") or button.get("source_text") or button.get("jp") or "").strip()
        popular = bool(button.get("popular") or button.get("best_seller"))
    else:
        english = str(button)
        japanese = ""
        popular = False
    en = _first(button_el.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " btn-en ")]'))
    jp = _first(button_el.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " btn-jp ")]'))
    if en is not None:
        _set_text_preserving_tail(en, english)
    if jp is not None:
        _set_text_preserving_tail(jp, japanese)
    if popular:
        button_el.set("data-best", "")
    elif "data-best" in button_el.attrib:
        del button_el.attrib["data-best"]


def _render_qr_slots(doc: etree._Element, content: dict[str, Any]) -> None:
    qr_data = content.get("qr_data")
    if not isinstance(qr_data, dict):
        return
    headline = str(qr_data.get("headline") or "").strip()
    if headline:
        headline_el = _first(doc.xpath('//*[@data-slot="sign-headline"]'))
        if headline_el is not None:
            _set_text_preserving_tail(headline_el, headline)
    qr_svg = str(qr_data.get("svg") or "").strip()
    qr_image = str(qr_data.get("image_src") or "").strip()
    qr_slot = _first(doc.xpath('//*[@data-slot="qr-code"]'))
    if qr_slot is None or not (qr_svg or qr_image):
        return
    for child in list(qr_slot):
        qr_slot.remove(child)
    if qr_svg:
        try:
            fragment = lxml_html.fragment_fromstring(qr_svg, create_parent=False)
            qr_slot.append(fragment)
        except etree.ParserError:
            qr_slot.text = qr_svg
    else:
        img = lxml_html.Element("img")
        img.set("src", qr_image)
        img.set("alt", str(qr_data.get("alt") or "QR code for English menu"))
        qr_slot.append(img)


def _remove_unprovided_sections(doc: etree._Element, content: dict[str, Any]) -> None:
    provided = {
        str(section.get("data_section") or section.get("id") or _slug(str(section.get("title") or section.get("heading") or ""))).strip()
        for section in _all_content_sections(content)
    }
    provided.discard("")
    for section in list(doc.xpath('//*[@data-section]')):
        if str(section.get("data-section") or "") not in provided:
            parent = section.getparent()
            if parent is not None:
                parent.remove(section)


def _remove_unused_drinks_panel(doc: etree._Element, content: dict[str, Any]) -> None:
    drinks = content.get("drinks") if isinstance(content.get("drinks"), dict) else {}
    if (drinks or {}).get("sections"):
        return
    panel = _find_panel(doc, "drinks")
    if panel is not None and panel is not doc:
        parent = panel.getparent()
        if parent is not None:
            parent.remove(panel)


def _slug(value: str) -> str:
    output: list[str] = []
    prev_dash = False
    for char in value.lower():
        if char.isalnum():
            output.append(char)
            prev_dash = False
        elif not prev_dash:
            output.append("-")
            prev_dash = True
    return "".join(output).strip("-") or "section"


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Render menu from template + JSON")
    parser.add_argument("--content", default=None, help="Path to menu_content.json")
    parser.add_argument("--template", default=None, help="Path to template HTML")
    parser.add_argument("--output", default=None, help="Output HTML path (default: stdout)")
    args = parser.parse_args()

    html = render(content_path=args.content, template_path=args.template)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(html, encoding="utf-8")
        print(f"Written to {args.output}")
    else:
        print(html)


if __name__ == "__main__":
    main()
