"""Mode B: PDF export and package assembly.

Uses Playwright for HTML-to-PDF and SVG-to-PDF conversion.
Applies watermark to all custom build output.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .constants import TEMPLATE_PACKAGE_MENU, TEMPLATE_PACKAGE_MACHINE
from .utils import ensure_dir, write_json
from .populate import populate_menu_svg, populate_menu_html, populate_ticket_machine_svg


# ---------------------------------------------------------------------------
# PDF generation via Playwright
# ---------------------------------------------------------------------------

async def svg_to_pdf(svg_path: Path, pdf_path: Path) -> Path:
    """Render an SVG file to a print-ready PDF using Playwright."""
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(f"file://{svg_path.resolve()}")
            await page.pdf(
                path=str(pdf_path),
                print_background=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
            )
            await browser.close()
    except ImportError:
        # Fallback: copy SVG if Playwright not available.
        # NOTE: The resulting file is NOT a valid PDF.
        # Install playwright and run `playwright install chromium` for real PDF generation.
        shutil.copy2(svg_path, pdf_path.with_suffix(".svg"))

    return pdf_path


async def html_to_pdf(html_path: Path, pdf_path: Path) -> Path:
    """Render an HTML file to a print-ready PDF using Playwright."""
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(f"file://{html_path.resolve()}")
            await page.pdf(
                path=str(pdf_path),
                format="A3",
                landscape=True,
                print_background=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
            )
            await browser.close()
    except ImportError:
        # Fallback: copy HTML if Playwright not available.
        # NOTE: The resulting file is NOT a valid PDF.
        # Install playwright and run `playwright install chromium` for real PDF generation.
        shutil.copy2(html_path, pdf_path.with_suffix(".html"))

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


def html_to_pdf_sync(html_path: Path, pdf_path: Path) -> Path:
    """Synchronous wrapper for html_to_pdf."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, html_to_pdf(html_path, pdf_path)).result()
    else:
        return asyncio.run(html_to_pdf(html_path, pdf_path))


# ---------------------------------------------------------------------------
# Watermark application
# ---------------------------------------------------------------------------

_WATERMARK_TEXT = "SAMPLE"

def apply_watermark_html(html_path: Path) -> Path:
    """Add a watermark overlay to an HTML file."""
    content = html_path.read_text(encoding="utf-8")
    watermark_css = """
    <style>
    .watermark-overlay {
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%) rotate(-45deg);
        font-size: 120px;
        color: rgba(0,0,0,0.08);
        pointer-events: none;
        z-index: 9999;
        font-weight: bold;
        letter-spacing: 20px;
        white-space: nowrap;
    }
    </style>
    <div class="watermark-overlay">""" + _WATERMARK_TEXT + """</div>
"""
    # Insert before </body>
    if "</body>" in content:
        content = content.replace("</body>", f"{watermark_css}\n</body>")
    else:
        content += watermark_css

    html_path.write_text(content, encoding="utf-8")
    return html_path


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
    """Create a complete output package matching the confirmed template structure.

    Generates: populated SVGs, HTML previews, print-ready PDFs.
    Applies watermark to all output.
    """
    ensure_dir(output_dir)
    slug = restaurant_name.lower().replace(" ", "_") if restaurant_name else "custom"

    # Copy template package structure
    menu_src = TEMPLATE_PACKAGE_MENU

    # --- Food menu ---
    food_svg_src = menu_src / "food_menu_editable_vector.svg"
    food_html_src = menu_src / "food_menu_browser_preview.html"

    food_svg_out = output_dir / "food_menu_editable_vector.svg"
    food_html_out = output_dir / "food_menu_browser_preview.html"
    food_pdf_out = output_dir / "food_menu_print_ready.pdf"

    # Copy source templates as base
    if food_svg_src.exists():
        shutil.copy2(food_svg_src, food_svg_out)
    if food_html_src.exists():
        shutil.copy2(food_html_src, food_html_out)

    # Populate with restaurant data
    if food_svg_out.exists() and menu_data.get("sections"):
        populate_menu_svg(template_path=food_svg_out, data=menu_data, output_path=food_svg_out)
    if food_html_out.exists() and menu_data.get("sections"):
        populate_menu_html(template_path=food_html_out, data=menu_data, output_path=food_html_out)

    # Apply watermark to HTML
    if food_html_out.exists():
        apply_watermark_html(food_html_out)

    # Generate PDF from the populated HTML
    if food_html_out.exists():
        await html_to_pdf(food_html_out, food_pdf_out)

    # --- Drinks menu ---
    drinks_svg_src = menu_src / "drinks_menu_editable_vector.svg"
    drinks_html_src = menu_src / "drinks_menu_browser_preview.html"
    drinks_svg_out = output_dir / "drinks_menu_editable_vector.svg"
    drinks_html_out = output_dir / "drinks_menu_browser_preview.html"
    drinks_pdf_out = output_dir / "drinks_menu_print_ready.pdf"

    if drinks_svg_src.exists():
        shutil.copy2(drinks_svg_src, drinks_svg_out)
        if menu_data.get("sections"):
            populate_menu_svg(template_path=drinks_svg_out, data=menu_data, output_path=drinks_svg_out)
    if drinks_html_src.exists():
        shutil.copy2(drinks_html_src, drinks_html_out)
        populate_menu_html(template_path=drinks_html_out, data=menu_data, output_path=drinks_html_out)
        apply_watermark_html(drinks_html_out)
        await html_to_pdf(drinks_html_out, drinks_pdf_out)

    # --- Combined menu ---
    combined_html_src = menu_src / "restaurant_menu_print_master.html"
    combined_html_out = output_dir / "restaurant_menu_print_master.html"
    combined_pdf_out = output_dir / "restaurant_menu_print_ready_combined.pdf"

    if combined_html_src.exists():
        shutil.copy2(combined_html_src, combined_html_out)
        if menu_data.get("sections"):
            populate_menu_html(template_path=combined_html_out, data=menu_data, output_path=combined_html_out)
        apply_watermark_html(combined_html_out)
        await html_to_pdf(combined_html_out, combined_pdf_out)

    # --- Ticket machine guide ---
    ticket_pdf_out = None
    if ticket_data:
        machine_src = TEMPLATE_PACKAGE_MACHINE
        ticket_svg_src = machine_src / "ticket_machine_guide_editable_vector.svg"
        ticket_html_src = machine_src / "ticket_machine_guide_browser_preview.html"
        ticket_svg_out = output_dir / "ticket_machine_guide_editable_vector.svg"
        ticket_html_out = output_dir / "ticket_machine_guide_browser_preview.html"
        ticket_pdf_path = output_dir / "ticket_machine_guide_print_ready.pdf"

        if ticket_svg_src.exists():
            shutil.copy2(ticket_svg_src, ticket_svg_out)
            populate_ticket_machine_svg(template_path=ticket_svg_out, data=ticket_data, output_path=ticket_svg_out)

        if ticket_html_src.exists():
            shutil.copy2(ticket_html_src, ticket_html_out)
            apply_watermark_html(ticket_html_out)
            await html_to_pdf(ticket_html_out, ticket_pdf_path)
            ticket_pdf_out = ticket_pdf_path

    # --- Menu data JSON ---
    menu_json_out = output_dir / "menu_data.json"
    write_json(menu_json_out, menu_data)

    return output_dir
