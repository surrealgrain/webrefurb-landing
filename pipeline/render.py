"""Render a menu HTML file from the master template + JSON content."""

import html as html_lib
import json
import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "assets" / "templates"
MASTER_TEMPLATE = TEMPLATES_DIR / "izakaya_food_menu.html"
DEFAULT_CONTENT = TEMPLATES_DIR / "menu_content.json"


def _load_content(path: str | None) -> dict:
    src = Path(path) if path else DEFAULT_CONTENT
    with open(src, encoding="utf-8") as f:
        return json.load(f)


def _esc(text: str) -> str:
    return html_lib.escape(text)


def _replace_section(html: str, data_section: str, heading: str,
                     items: list[str], sub: str = "") -> str:
    """Replace header + items content inside a section matched by data-section.

    Handles both v1 (bare h2 + ul) and v2 (section-header-group wrapper) layout.
    """
    # v2: section-header-group wrapping h2 + optional section-sub
    pattern_v2 = re.compile(
        rf'(<div\s+class="section"\s+data-section="{re.escape(data_section)}"\s*>\s*)'
        r'(<div\s+class="section-header-group">).*?(</div>\s*)'  # header group
        r'(<ul\s+class="menu-items"[^>]*>).*?(</ul>)',           # items
        re.DOTALL,
    )

    items_html = "\n".join(
        f'          <li data-slot="item">{_esc(item)}</li>' for item in items
    )

    sub_line = ""
    if sub:
        sub_line = f'\n            <div class="section-sub" data-slot="section-sub">{_esc(sub)}</div>'

    replacement_v2 = (
        rf'\g<1>'
        rf'<div class="section-header-group">\n'
        rf'            <h2 class="section-header" data-slot="section-title">{_esc(heading)}</h2>'
        f'{sub_line}\n'
        rf'          </div>\n'
        rf'          <ul class="menu-items" data-slot="section-items">\n'
        f'{items_html}\n'
        rf'          </ul>'
    )

    result, count = pattern_v2.subn(replacement_v2, html, count=1)
    if count > 0:
        return result

    # v1 fallback: bare h2 + ul (no header-group wrapper)
    pattern_v1 = re.compile(
        rf'(<div\s+class="section"\s+data-section="{re.escape(data_section)}"\s*>\s*)'
        r'(<h2\s+class="section-header"[^>]*>).*?(</h2>\s*)'
        r'(<ul\s+class="menu-items"[^>]*>).*?(</ul>)',
        re.DOTALL,
    )
    replacement_v1 = (
        rf'\g<1>'
        rf'<h2 class="section-header" data-slot="section-title">{_esc(heading)}</h2>\n'
        rf'        <ul class="menu-items" data-slot="section-items">\n'
        f'{items_html}\n'
        rf'        </ul>'
    )

    result, count = pattern_v1.subn(replacement_v1, html, count=1)
    if count == 0:
        import sys
        print(f"  warning: section '{data_section}' not found in template", file=sys.stderr)
    return result


def _replace_panel_title(html: str, panel_id: str, title: str) -> str:
    """Replace the panel title text within a specific panel."""
    # Find the panel by id, then replace the first h1 inside it
    panel_pat = re.compile(
        rf'(<div\s+class="menu-panel"\s+id="{re.escape(panel_id)}">.*?'
        rf'<h1\s+class="menu-title"\s+data-slot="panel-title">)(.*?)(</h1>)',
        re.DOTALL,
    )
    result, count = panel_pat.subn(rf'\g<1>{_esc(title)}\3', html, count=1)
    return result


def render(content_path: str | None = None, template_path: str | None = None) -> str:
    """Render the master template with JSON content. Returns final HTML string."""
    tpl_path = Path(template_path) if template_path else MASTER_TEMPLATE
    with open(tpl_path, encoding="utf-8") as f:
        html = f.read()

    content = _load_content(content_path)

    for panel_key in ("food", "drinks"):
        panel_id = f"{panel_key}-panel"
        panel_data = content[panel_key]

        html = _replace_panel_title(html, panel_id, panel_data["title"])

        for section in panel_data["sections"]:
            html = _replace_section(
                html,
                section["data_section"],
                section["heading"],
                section["items"],
                sub=section.get("sub", ""),
            )

    return html


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
