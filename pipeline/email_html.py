"""Build professional HTML emails with header, inline menu image, and footer.

All images use CID (Content-ID) inline attachments — embedded directly in
the email.  No external URL fetches, so images load 100 % of the time in
every email client including mobile carriers that block remote content.

Max 2 inline images: menu sample + ticket machine guide (if applicable).
"""

from __future__ import annotations

import html
from pathlib import Path

LOGO_SVG_PATH = Path(__file__).resolve().with_name("webrefurb_email_logo.svg")
LOGO_PNG_PATH = Path(__file__).resolve().with_name("_logo_cache.png")

LOGO_CID = "webrefurb-logo"
MENU_CID = "menu-preview"
MACHINE_CID = "machine-preview"


# ---------------------------------------------------------------------------
# Logo rasterisation (SVG → PNG, cached)
# ---------------------------------------------------------------------------

def _ensure_logo_png() -> Path | None:
    """Rasterise the SVG logo to a PNG (cached on disk).

    Returns the PNG path, or None if the SVG is missing.
    """
    if LOGO_PNG_PATH.exists():
        return LOGO_PNG_PATH
    if not LOGO_SVG_PATH.exists():
        return None
    try:
        from playwright.sync_api import sync_playwright

        svg_abs = LOGO_SVG_PATH.resolve()
        wrapper = (
            '<!DOCTYPE html><html><head><style>'
            'html,body{margin:0;padding:0;background:transparent;}'
            '</style></head><body>'
            f'<img src="file://{svg_abs}" style="display:block;" />'
            '</body></html>'
        )
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w")
        tmp.write(wrapper)
        tmp.flush()

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(
                viewport={"width": 320, "height": 80},
                device_scale_factor=2,
            )
            page.goto(f"file://{Path(tmp.name).resolve()}")
            page.wait_for_load_state("networkidle")
            page.screenshot(
                path=str(LOGO_PNG_PATH),
                full_page=True,
                type="png",
                omit_background=True,
            )
            browser.close()
        Path(tmp.name).unlink(missing_ok=True)
        return LOGO_PNG_PATH
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Menu / machine image rendering (HTML → JPEG, cached)
# ---------------------------------------------------------------------------

def _render_html_to_jpeg(
    html_path: Path,
    output_path: Path,
    width: int = 600,
) -> Path | None:
    """Render an HTML file to JPEG using Playwright (retina quality).

    Returns the JPEG path, or None if rendering fails.
    """
    try:
        from playwright.sync_api import sync_playwright

        if not html_path.exists():
            return None

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(
                viewport={"width": width, "height": 600},
                device_scale_factor=2,
            )
            page.goto(f"file://{html_path.resolve()}")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(output_path), full_page=True, type="jpeg", quality=92)
            browser.close()

        return output_path
    except Exception:
        return None


def _ensure_menu_jpeg(html_path: str | Path | None) -> Path | None:
    """Render a menu HTML to JPEG if needed, return the JPEG path.

    Caches next to the source HTML as ``<name>_email_preview.jpg``.
    """
    if not html_path:
        return None
    src = Path(html_path)
    if not src.exists():
        return None
    cached = src.with_name(src.stem + "_email_preview.jpg")
    if cached.exists():
        return cached
    return _render_html_to_jpeg(src, cached)


# Backward-compatible alias for external callers
def render_menu_to_jpeg(
    menu_html_path: str | Path,
    output_path: str | Path | None = None,
    width: int = 600,
) -> Path | None:
    if output_path is None:
        output_path = Path(menu_html_path).with_suffix(".jpg")
    return _render_html_to_jpeg(Path(menu_html_path), Path(output_path), width)


render_menu_to_png = render_menu_to_jpeg


# ---------------------------------------------------------------------------
# Email HTML builder
# ---------------------------------------------------------------------------

def build_pitch_email_html(
    *,
    text_body: str,
    include_menu_image: bool = True,
    include_machine_image: bool = False,
    locale: str = "en",
) -> str:
    """Build a full HTML email with header logo, body, CID images, and footer.

    Menu and machine guide images use CID references — they must be
    provided as inline attachments via ``build_inline_attachments()``.

    Args:
        locale: "en" links to webrefurb.com, "ja" links to webrefurb.com/ja.

    Returns:
        Complete HTML string.
    """
    has_logo = _ensure_logo_png() is not None
    site_url = "https://webrefurb.com/ja" if locale == "ja" else "https://webrefurb.com"

    lines = [l.strip() for l in text_body.strip().split("\n\n") if l.strip()]

    # -- Header ----------------------------------------------------------
    if has_logo:
        header_logo = (
            f'<a href="{site_url}" target="_blank" rel="noopener noreferrer">'
            f'<img src="cid:{LOGO_CID}" alt="WebRefurb" width="180" '
            f'style="display:block; width:180px; height:auto; border:0;" />'
            f'</a>'
        )
    else:
        header_logo = (
            f'<a href="{site_url}" target="_blank" rel="noopener noreferrer" '
            'style="text-decoration:none; color:#111;">'
            '<span style="font-size:16px; font-weight:700; letter-spacing:-0.3px; color:#111;">'
            'WebRefurb</span></a>'
        )
    header = (
        '<div style="padding-bottom:20px; margin-bottom:24px; border-bottom:1px solid #E8E8E5;">'
        f'{header_logo}'
        '</div>'
    )

    # -- Body paragraphs -------------------------------------------------
    body_parts: list[str] = []
    for line in lines:
        escaped = html.escape(line).replace("\n", "<br>")
        body_parts.append(
            '<p style="margin:0 0 16px 0; font-size:15px; line-height:1.65; '
            f'color:#111; text-align:left;">{escaped}</p>'
        )

    # -- Menu image (CID inline, embedded in email) ----------------------
    if include_menu_image:
        body_parts.append(
            f'<img src="cid:{MENU_CID}" width="600" alt="English Menu Sample" '
            'style="display:block; width:100%; max-width:600px; height:auto; '
            'margin:24px 0; border-radius:8px; border:1px solid #E8E8E5;" />'
        )

    # -- Ticket machine guide image (CID inline) -------------------------
    if include_machine_image:
        body_parts.append(
            f'<img src="cid:{MACHINE_CID}" width="600" alt="Ticket Machine Guide" '
            'style="display:block; width:100%; max-width:600px; height:auto; '
            'margin:24px 0; border-radius:8px; border:1px solid #E8E8E5;" />'
        )

    body_html = "\n".join(body_parts)

    # -- Footer ----------------------------------------------------------
    if has_logo:
        footer = (
            '<div style="margin-top:40px; padding-top:20px; border-top:1px solid #E8E8E5;">'
            f'<a href="{site_url}" target="_blank" rel="noopener noreferrer">'
            f'<img src="cid:{LOGO_CID}" alt="WebRefurb" width="140" '
            f'style="display:block; width:140px; height:auto; opacity:0.6; margin-bottom:8px; border:0;" />'
            f'</a>'
            f'<a href="mailto:chris@webrefurb.com" '
            'style="text-decoration:none; color:#aaaaaa; font-size:12px; line-height:1.4;">'
            'chris@webrefurb.com</a>'
            '<span style="color:#cccccc; font-size:12px; margin:0 6px;">·</span>'
            f'<a href="{site_url}" target="_blank" rel="noopener noreferrer" '
            'style="text-decoration:none; color:#aaaaaa; font-size:12px; line-height:1.4;">'
            'webrefurb.com</a>'
            '</div>'
        )
    else:
        footer = (
            '<div style="margin-top:40px; padding-top:20px; border-top:1px solid #E8E8E5;">'
            f'<a href="mailto:chris@webrefurb.com" '
            'style="text-decoration:none; color:#aaaaaa; font-size:12px; line-height:1.4;">'
            'chris@webrefurb.com</a>'
            '<span style="color:#cccccc; font-size:12px; margin:0 6px;">·</span>'
            f'<a href="{site_url}" target="_blank" rel="noopener noreferrer" '
            'style="text-decoration:none; color:#aaaaaa; font-size:12px; line-height:1.4;">'
            'webrefurb.com</a>'
            '</div>'
        )

    return (
        '<!DOCTYPE html>'
        '<html lang="ja" xmlns="http://www.w3.org/1999/xhtml">'
        '<head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '</head>'
        '<body style="margin:0; padding:32px 20px; font-family:-apple-system,BlinkMacSystemFont,'
        "'Segoe UI',Helvetica,Arial,sans-serif; background-color:#ffffff;\">"
        f'<table width="600" cellpadding="0" cellspacing="0" border="0" align="center">'
        f'<tr><td>{header}</td></tr>'
        f'<tr><td style="padding:24px 0 0 0;">{body_html}</td></tr>'
        f'<tr><td>{footer}</td></tr>'
        '</table>'
        '</body></html>'
    )


# ---------------------------------------------------------------------------
# CID inline attachment builder
# ---------------------------------------------------------------------------

def build_inline_attachments(
    *,
    menu_jpeg_path: str | Path | None = None,
    machine_jpeg_path: str | Path | None = None,
) -> list[dict]:
    """Return the list of Resend inline-attachment dicts for all email images.

    Produces up to 4 CID attachments: logo (header+footer shared),
    menu preview, and machine guide preview.
    """
    import base64

    attachments: list[dict] = []

    # Logo PNG (shared CID for header + footer)
    logo_png = _ensure_logo_png()
    if logo_png and logo_png.exists():
        attachments.append({
            "filename": "logo.png",
            "content": base64.b64encode(logo_png.read_bytes()).decode("ascii"),
            "content_id": LOGO_CID,
            "disposition": "inline",
            "mime_type": "image/png",
        })

    # Menu preview JPEG
    if menu_jpeg_path:
        menu_path = Path(menu_jpeg_path)
        if menu_path.exists():
            attachments.append({
                "filename": "英語メニューサンプル.jpg",
                "content": base64.b64encode(menu_path.read_bytes()).decode("ascii"),
                "content_id": MENU_CID,
                "disposition": "inline",
                "mime_type": "image/jpeg",
            })

    # Machine guide preview JPEG
    if machine_jpeg_path:
        machine_path = Path(machine_jpeg_path)
        if machine_path.exists():
            attachments.append({
                "filename": "券売機注文ガイド.jpg",
                "content": base64.b64encode(machine_path.read_bytes()).decode("ascii"),
                "content_id": MACHINE_CID,
                "disposition": "inline",
                "mime_type": "image/jpeg",
            })

    return attachments
