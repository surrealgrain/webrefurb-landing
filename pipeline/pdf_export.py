"""PDF helpers used by the English QR Menu export flow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


CUSTOM_PAPER_SIZES_MM = {
    "B4": (250, 353),
    "B5": (176, 250),
}


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


async def html_to_pdf(html_path: Path, pdf_path: Path, *, print_profile: PrintProfile | None = None) -> Path:
    """Render an HTML file to a print-ready PDF using Playwright."""
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
                pdf_options = {
                    "path": str(pdf_path),
                    "print_background": True,
                    "prefer_css_page_size": True,
                    "margin": {"top": "0", "bottom": "0", "left": "0", "right": "0"},
                }
                custom_size = CUSTOM_PAPER_SIZES_MM.get(str(profile.paper_size or "").upper())
                if custom_size:
                    width_mm, height_mm = custom_size
                    if profile.landscape:
                        width_mm, height_mm = height_mm, width_mm
                    pdf_options.update({
                        "width": f"{width_mm}mm",
                        "height": f"{height_mm}mm",
                        "prefer_css_page_size": False,
                    })
                else:
                    pdf_options.update({"format": profile.paper_size, "landscape": profile.landscape})
                await page.pdf(**pdf_options)
            finally:
                await browser.close()
    except Exception as exc:
        if pdf_path.exists():
            pdf_path.unlink()
        raise PdfExportError(f"PDF export failed for {html_path.name}. {PDF_RENDERER_SETUP_HINT}") from exc

    _assert_valid_pdf(pdf_path, html_path)
    return pdf_path


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
    return asyncio.run(html_to_pdf(html_path, pdf_path, print_profile=print_profile))
