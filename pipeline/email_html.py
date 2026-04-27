"""Build professional HTML emails with header, inline menu image, and footer.

Uses CID (Content-ID) inline attachments for all images — the industry-standard
approach.  SVGs are rasterised to PNG first because Gmail strips <svg> tags.
"""

from __future__ import annotations

import html
from pathlib import Path

LOGO_SVG_PATH = Path(__file__).resolve().with_name("webrefurb_email_logo.svg")
LOGO_PNG_PATH = Path(__file__).resolve().with_name("_logo_cache.png")

LOGO_CID = "webrefurb-logo"
MENU_CID = "menu-preview"
MENU_URL = "https://www.webrefurb.com/previews/menu-sample.jpg"
MACHINE_URL = "https://www.webrefurb.com/previews/machine-sample.jpg"


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
        # Wrap SVG in minimal HTML so Playwright can render it reliably
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
# Email HTML builder
# ---------------------------------------------------------------------------

def build_pitch_email_html(
    *,
    text_body: str,
    menu_image_path: str | Path | None = None,
    include_menu_image: bool = True,
    include_machine_image: bool = False,
    locale: str = "en",
) -> str:
    """Build a full HTML email with header logo, body, images, and footer.

    Logo uses CID inline attachment. Menu and machine images are hosted on
    the web and referenced by URL — no attachments needed for those.

    Args:
        locale: "en" links to webrefurb.com, "ja" links to webrefurb.com/ja.
            The visible footer text always shows "webrefurb.com".

    Returns:
        Complete HTML string (typically < 10 KB).
    """
    has_logo = _ensure_logo_png() is not None
    site_url = "https://webrefurb.com/ja" if locale == "ja" else "https://webrefurb.com"

    lines = [l.strip() for l in text_body.strip().split("\n\n") if l.strip()]

    # -- Header (clean logo strip, hairline separator) --------------------
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

    # -- Body paragraphs ---------------------------------------------------
    body_parts: list[str] = []
    for line in lines:
        escaped = html.escape(line).replace("\n", "<br>")
        body_parts.append(
            '<p style="margin:0 0 16px 0; font-size:15px; line-height:1.65; '
            f'color:#111; text-align:left;">{escaped}</p>'
        )

    # -- Menu image (URL-hosted, no attachment) ---------------------------
    if include_menu_image and menu_image_path:
        body_parts.append(
            f'<img src="{MENU_URL}" width="600" alt="English Menu Sample" '
            'style="display:block; width:100%; max-width:600px; height:auto; '
            'margin:24px 0; border-radius:8px; border:1px solid #E8E8E5;" />'
        )

    # -- Ticket machine guide image (URL-hosted, no attachment) -----------
    if include_machine_image:
        body_parts.append(
            f'<img src="{MACHINE_URL}" width="600" alt="Ticket Machine Guide" '
            'style="display:block; width:100%; max-width:600px; height:auto; '
            'margin:24px 0; border-radius:8px; border:1px solid #E8E8E5;" />'
        )

    body_html = "\n".join(body_parts)

    # -- Footer (logo + hairline separator) --------------------------------
    if has_logo:
        footer = (
            '<div style="margin-top:40px; padding-top:20px; border-top:1px solid #E8E8E5;">'
            f'<a href="{site_url}" target="_blank" rel="noopener noreferrer">'
            f'<img src="cid:{LOGO_CID}" alt="WebRefurb" width="140" '
            f'style="display:block; width:140px; height:auto; opacity:0.6; margin-bottom:8px; border:0;" />'
            f'</a>'
            f'<a href="{site_url}" target="_blank" rel="noopener noreferrer" '
            'style="text-decoration:none; color:#999999; font-size:12px; line-height:1.4;">'
            'webrefurb.com</a>'
            '</div>'
        )
    else:
        footer = (
            '<div style="margin-top:40px; padding-top:20px; border-top:1px solid #E8E8E5;">'
            f'<a href="{site_url}" target="_blank" rel="noopener noreferrer" '
            'style="text-decoration:none; color:#aaaaaa; font-size:13px; line-height:1.6;">'
            'WebRefurb</a><br/>'
            f'<a href="{site_url}" target="_blank" rel="noopener noreferrer" '
            'style="text-decoration:none; color:#999999; font-size:12px; line-height:1.4;">'
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
# Attachment helpers
# ---------------------------------------------------------------------------

def build_inline_attachments(
    menu_image_path: str | Path | None = None,
) -> list[dict]:
    """Return the list of Resend inline-attachment dicts for email images.

    Only the logo is sent as a CID inline attachment. The menu image is
    hosted on the web and referenced by URL — no attachment needed.
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

    return attachments


def render_menu_to_jpeg(
    menu_html_path: str | Path,
    output_path: str | Path | None = None,
    width: int = 600,
) -> Path | None:
    """Render a menu HTML file to JPEG using Playwright (retina quality).

    Returns the path to the generated JPEG, or None if rendering fails.
    """
    try:
        from playwright.sync_api import sync_playwright

        menu_path = Path(menu_html_path).resolve()
        if not menu_path.exists():
            return None

        if output_path is None:
            output_path = menu_path.with_suffix(".jpg")
        out = Path(output_path)

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(
                viewport={"width": width, "height": 600},
                device_scale_factor=2,
            )
            page.goto(f"file://{menu_path}")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(out), full_page=True, type="jpeg", quality=92)
            browser.close()

        return out
    except Exception:
        return None


# Backward-compatible alias
render_menu_to_png = render_menu_to_jpeg
