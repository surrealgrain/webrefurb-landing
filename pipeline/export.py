"""Mode B: PDF export and package assembly.

Uses Playwright for HTML-to-PDF and SVG-to-PDF conversion.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import PROJECT_ROOT
from .utils import ensure_dir, write_json
from .populate import populate_menu_html


# ---------------------------------------------------------------------------
# PDF generation via Playwright
# ---------------------------------------------------------------------------

PDF_RENDERER_SETUP_HINT = (
    "Install project dependencies in a virtualenv, then run "
    "`python3 -m playwright install chromium`."
)


class PdfExportError(RuntimeError):
    """Raised when a print-ready PDF cannot be generated."""


@dataclass(frozen=True)
class PrintProfile:
    paper_size: str = "A4"
    orientation: str = "portrait"

    @property
    def landscape(self) -> bool:
        return self.orientation == "landscape"


def is_valid_pdf(path: Path) -> bool:
    """Return True when path exists and has a PDF file signature."""
    return path.exists() and path.is_file() and path.read_bytes()[:4] == b"%PDF"


def _assert_valid_pdf(pdf_path: Path, source_path: Path) -> None:
    if is_valid_pdf(pdf_path):
        return
    if pdf_path.exists():
        pdf_path.unlink()
    raise PdfExportError(
        f"PDF export failed for {source_path.name}: renderer did not produce a valid PDF. "
        f"{PDF_RENDERER_SETUP_HINT}"
    )


async def svg_to_pdf(svg_path: Path, pdf_path: Path) -> Path:
    """Render an SVG file to a print-ready PDF using Playwright."""
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise PdfExportError(f"Playwright is required for PDF export. {PDF_RENDERER_SETUP_HINT}") from exc

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(f"file://{svg_path.resolve()}", wait_until="networkidle")
                await page.emulate_media(media="print")
                await page.pdf(
                    path=str(pdf_path),
                    print_background=True,
                    margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                )
            finally:
                await browser.close()
    except Exception as exc:
        if pdf_path.exists():
            pdf_path.unlink()
        raise PdfExportError(
            f"PDF export failed for {svg_path.name}. {PDF_RENDERER_SETUP_HINT}"
        ) from exc

    _assert_valid_pdf(pdf_path, svg_path)

    return pdf_path


async def html_to_pdf(html_path: Path, pdf_path: Path, *, print_profile: PrintProfile | None = None) -> Path:
    """Render an HTML file to a print-ready PDF using Playwright.

    Uses device_scale_factor=2 for high-resolution output suitable for
    professional printing. Respects CSS @page size rules.
    """
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    profile = print_profile or PrintProfile()

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise PdfExportError(f"Playwright is required for PDF export. {PDF_RENDERER_SETUP_HINT}") from exc

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await browser.new_page(
                    viewport={"width": 495, "height": 700},
                    device_scale_factor=2,
                )
                await page.goto(f"file://{html_path.resolve()}", wait_until="networkidle")
                await page.emulate_media(media="print")
                await page.pdf(
                    path=str(pdf_path),
                    format=profile.paper_size,
                    landscape=profile.landscape,
                    print_background=True,
                    prefer_css_page_size=True,
                    margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                )
            finally:
                await browser.close()
    except Exception as exc:
        if pdf_path.exists():
            pdf_path.unlink()
        raise PdfExportError(
            f"PDF export failed for {html_path.name}. {PDF_RENDERER_SETUP_HINT}"
        ) from exc

    _assert_valid_pdf(pdf_path, html_path)

    return pdf_path


def svg_to_pdf_sync(svg_path: Path, pdf_path: Path) -> Path:
    """Synchronous wrapper for svg_to_pdf."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, svg_to_pdf(svg_path, pdf_path)).result()
    else:
        return asyncio.run(svg_to_pdf(svg_path, pdf_path))


def html_to_pdf_sync(html_path: Path, pdf_path: Path, *, print_profile: PrintProfile | None = None) -> Path:
    """Synchronous wrapper for html_to_pdf."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, html_to_pdf(html_path, pdf_path, print_profile=print_profile)).result()
    else:
        return asyncio.run(html_to_pdf(html_path, pdf_path, print_profile=print_profile))


# ---------------------------------------------------------------------------
# Package assembly
# ---------------------------------------------------------------------------

async def build_custom_package(
    *,
    output_dir: Path,
    menu_data: dict[str, Any],
    ticket_data: dict[str, Any] | None = None,
    restaurant_name: str = "",
) -> Path:
    """Create a complete output package using v4c dark HTML templates.

    Generates: populated HTMLs + print-ready A5 PDFs (highest quality).
    Templates are selected by restaurant type (ramen vs izakaya).
    """
    ensure_dir(output_dir)

    # Determine template type from menu data
    is_izakaya = "izakaya" in (menu_data.get("menu_type") or "").lower()
    V4C = PROJECT_ROOT / "assets" / "templates"

    # --- Food menu ---
    food_template = "izakaya_food_menu.html" if is_izakaya else "ramen_food_menu.html"
    food_src = V4C / food_template
    food_html_out = output_dir / "food_menu.html"
    food_pdf_out = output_dir / "food_menu_print_ready.pdf"

    if food_src.exists():
        shutil.copy2(food_src, food_html_out)
        populate_menu_html(
            template_path=food_html_out,
            data=menu_data,
            output_path=food_html_out,
            business_name=restaurant_name or None,
        )
        await html_to_pdf(
            food_html_out, food_pdf_out,
            print_profile=PrintProfile(paper_size="A5"),
        )

    # --- Drinks menu ---
    drinks_template = "izakaya_drinks_menu.html" if is_izakaya else "ramen_drinks_menu.html"
    drinks_src = V4C / drinks_template
    drinks_html_out = output_dir / "drinks_menu.html"
    drinks_pdf_out = output_dir / "drinks_menu_print_ready.pdf"

    has_drinks = bool((menu_data.get("drinks") or {}).get("sections"))
    if has_drinks and drinks_src.exists():
        shutil.copy2(drinks_src, drinks_html_out)
        populate_menu_html(
            template_path=drinks_html_out,
            data=menu_data,
            output_path=drinks_html_out,
            business_name=restaurant_name or None,
        )
        await html_to_pdf(
            drinks_html_out, drinks_pdf_out,
            print_profile=PrintProfile(paper_size="A5"),
        )

    # --- Ticket machine guide ---
    if ticket_data:
        machine_src = V4C / "ticket_machine_guide.html"
        ticket_html_out = output_dir / "ticket_machine_guide.html"
        ticket_pdf_path = output_dir / "ticket_machine_guide_print_ready.pdf"

        if machine_src.exists():
            shutil.copy2(machine_src, ticket_html_out)
            # Populate ticket machine guide with button data
            _populate_ticket_machine_html(ticket_html_out, ticket_data, restaurant_name)
            await html_to_pdf(
                ticket_html_out, ticket_pdf_path,
                print_profile=PrintProfile(paper_size="A5"),
            )

    # --- Menu data JSON ---
    menu_json_out = output_dir / "menu_data.json"
    write_json(menu_json_out, menu_data)

    return output_dir


def _populate_ticket_machine_html(
    html_path: Path, data: dict[str, Any], restaurant_name: str | None,
) -> None:
    """Populate the v4c ticket machine guide HTML with button data."""
    import re
    from html import escape as esc

    html = html_path.read_text(encoding="utf-8")

    # Replace seal text
    if restaurant_name:
        from .render import replace_seal_text
        html = replace_seal_text(html, restaurant_name)

    # Replace button labels — find all machine-btn elements and update text
    buttons = data.get("buttons", [])
    if buttons:
        # Find existing button slots
        btn_pattern = re.compile(
            r'(<div\s+class="machine-btn"[^>]*>\s*)'
            r'(?:<span\s+class="best-tag"[^>]*>[^<]*</span>\s*)?'
            r'<span\s+class="btn-en">)([^<]*)(</span>\s*'
            r'<span\s+class="btn-jp">)([^<]*)(</span>)',
        )
        existing = list(btn_pattern.finditer(html))
        for idx, match in enumerate(existing):
            if idx < len(buttons):
                btn = buttons[idx] if isinstance(buttons[idx], dict) else {"en": str(buttons[idx]), "jp": ""}
                en = btn.get("en", btn.get("english_name", ""))
                jp = btn.get("jp", btn.get("japanese_name", ""))
                # Keep best-tag if present
                best_tag = '<span class="best-tag">Popular</span>\n          ' if idx == 0 else ""
                replacement = (
                    rf'\g<1>{best_tag}<span class="btn-en">{esc(en)}</span>\g<3>'
                    rf'{esc(jp)}\g<5>'
                )
                html = html[:match.start()] + btn_pattern.sub(
                    replacement, html[match.start():], count=1,
                )

    html_path.write_text(html, encoding="utf-8")
