from __future__ import annotations

from pathlib import Path

from pipeline.populate import build_menu_data, populate_menu_html
from pipeline.render import (
    render_template_html,
    validate_render_content_schema,
    validate_rendered_html,
    validate_template_contract,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = PROJECT_ROOT / "assets" / "templates"
ACTIVE_HTML_TEMPLATES = [
    TEMPLATES_ROOT / "ramen_food_menu.html",
    TEMPLATES_ROOT / "izakaya_food_drinks_menu.html",
    TEMPLATES_ROOT / "ticket_machine_guide.html",
    TEMPLATES_ROOT / "qr_code_sign.html",
]


def test_active_html_templates_pass_run5_contract():
    errors = {
        path.name: validate_template_contract(path)
        for path in ACTIVE_HTML_TEMPLATES
    }

    assert errors
    assert all(not template_errors for template_errors in errors.values()), errors


def test_active_html_templates_show_customer_sample_caveat():
    for path in ACTIVE_HTML_TEMPLATES:
        text = path.read_text(encoding="utf-8")
        assert "Illustrative sample only" in text, path.name
        assert "owner-confirmed menu content" in text, path.name
        assert "owner-provided photos" in text, path.name


def test_html_renderer_no_longer_uses_regex_replacement():
    source = (PROJECT_ROOT / "pipeline" / "render.py").read_text(encoding="utf-8")

    assert "import re" not in source
    assert "re.sub" not in source
    assert "re.compile" not in source


def test_shared_render_content_schema_covers_required_fields():
    errors = validate_render_content_schema({
        "business_name": "Hinode Ramen",
        "profile": "ramen_only",
        "sections": [
            {
                "data_section": "ramen",
                "title": "Ramen",
                "items": [
                    {
                        "name": "Shoyu Ramen",
                        "japanese_name": "醤油ラーメン",
                        "description": "Clear soy sauce broth.",
                        "price": "¥900",
                        "price_status": "confirmed_by_business",
                        "photos": [],
                    }
                ],
            }
        ],
        "rule_blocks": [{"title": "How to order", "body": "Choose, pay, then hand the ticket to staff."}],
        "photos": [],
        "qr_data": {"url": "https://webrefurb.com/menus/sample/"},
        "ticket_machine_mapping": {"rows": [{"buttons": ["Shoyu Ramen"]}]},
    })

    assert errors == []


def test_populate_menu_html_uses_structured_slots_and_removes_unprovided_sections(tmp_path):
    output_path = tmp_path / "food_menu.html"
    data = build_menu_data(
        menu_type="ramen_only",
        title="FOOD MENU",
        sections=[
            {
                "title": "RAMEN",
                "data_section": "ramen",
                "items": [
                    {"name": "Shoyu Ramen", "japanese_name": "醤油ラーメン"},
                ],
            }
        ],
        food_sections=[
            {
                "title": "RAMEN",
                "data_section": "ramen",
                "items": [
                    {"name": "Shoyu Ramen", "japanese_name": "醤油ラーメン"},
                ],
            }
        ],
    )

    populate_menu_html(
        template_path=TEMPLATES_ROOT / "ramen_food_menu.html",
        data=data,
        output_path=output_path,
        business_name="Hinode Ramen",
    )

    html = output_path.read_text(encoding="utf-8")
    assert "見本" in html
    assert "Hinode Ramen" not in html
    assert "Shoyu Ramen" in html
    assert "Miso Ramen" not in html
    assert 'data-section="sides-add-ons"' not in html
    assert validate_rendered_html(html, template_path=TEMPLATES_ROOT / "ramen_food_menu.html") == []


def test_ticket_machine_and_qr_templates_render_from_structured_content():
    ticket_html = render_template_html(
        (TEMPLATES_ROOT / "ticket_machine_guide.html").read_text(encoding="utf-8"),
        {
            "business_name": "Hinode Ramen",
            "profile": "ticket_machine_guide",
            "sections": [
                {
                    "title": "RAMEN",
                    "data_section": "ramen",
                    "items": [{"name": "Shoyu Ramen", "japanese_name": "醤油ラーメン"}],
                }
            ],
            "ticket_machine_mapping": {
                "steps": ["Insert money", "Choose ramen", "Take ticket", "Give ticket to staff"],
                "rows": [
                    {"buttons": [
                        {"name": "Shoyu Ramen", "japanese_name": "醤油ラーメン", "popular": True},
                        {"name": "Miso Ramen", "japanese_name": "味噌ラーメン"},
                    ]}
                ],
            },
        },
        business_name="Hinode Ramen",
    )
    assert "Choose ramen" in ticket_html
    assert "Shoyu Ramen" in ticket_html
    assert validate_rendered_html(ticket_html, template_path=TEMPLATES_ROOT / "ticket_machine_guide.html") == []

    qr_html = render_template_html(
        (TEMPLATES_ROOT / "qr_code_sign.html").read_text(encoding="utf-8"),
        {
            "business_name": "Hinode Ramen",
            "profile": "qr_code_sign",
            "sections": [
                {
                    "title": "RAMEN",
                    "data_section": "ramen",
                    "items": [{"name": "Shoyu Ramen", "japanese_name": "醤油ラーメン"}],
                }
            ],
            "qr_data": {
                "headline": "Scan for English Menu",
                "svg": '<svg viewBox="0 0 10 10"><rect width="10" height="10"></rect></svg>',
            },
        },
        business_name="Hinode Ramen",
    )
    assert "<svg" in qr_html
    assert "見本" in qr_html
    assert "Hinode Ramen" not in qr_html
    assert validate_rendered_html(qr_html, template_path=TEMPLATES_ROOT / "qr_code_sign.html") == []
