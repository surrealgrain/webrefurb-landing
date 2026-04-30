"""Discover and parse 特定商取引法 (Tokusho) pages.

特定商取引法に基づく表記 pages are especially valuable in Japan because:
  - Online shop operators are legally required to publish contact details
  - Ramen shops selling frozen ramen, gift sets, etc. must have tokushoho pages
  - These pages often list operator company info and email addresses
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .email_extractor import extract_emails_from_page

# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

TOKUSHOHO_TITLE_PATTERNS = [
    r"特定商取引法",
    r"特定商取引法に基づく表記",
    r"特商法",
    r"法律に基づく表記",
]

TOKUSHOHO_URL_PATTERNS = [
    r"tokushoho",
    r"legal",
    r"特定商取引",
    r"特商法",
    r"commerce",
    r"notation",
]

TOKUSHOHO_LINK_TEXT = [
    "特定商取引法に基づく表記",
    "特定商取引法",
    "特商法",
    "販売業者",
    "通信販売",
]

# Data fields typically found on tokushoho pages
TOKUSHOHO_FIELD_PATTERNS = {
    "seller_name": [
        r"販売業者[：:]\s*(.+)",
        r"販売事業者[：:]\s*(.+)",
        r"運営会社[：:]\s*(.+)",
        r"運営者[：:]\s*(.+)",
        r"事業者名[：:]\s*(.+)",
    ],
    "representative": [
        r"代表者[：:]\s*(.+)",
        r"代表取締役[：:]\s*(.+)",
        r"運営責任者[：:]\s*(.+)",
    ],
    "address": [
        r"所在地[：:]\s*(.+)",
        r"住所[：:]\s*(.+)",
        r"本店[：:]\s*(.+)",
    ],
    "phone": [
        r"電話番号[：:]\s*(.+)",
        r"TEL[：:]\s*(.+)",
        r"連絡先[：:]\s*(.+)",
    ],
    "email": [
        r"メールアドレス[：:]\s*(.+)",
        r"email[：:]\s*(.+)",
        r"E-?mail[：:]\s*(.+)",
        r"連絡先.*?メール[：:]\s*(.+)",
    ],
    "website": [
        r"URL[：:]\s*(.+)",
        r"ホームページ[：:]\s*(.+)",
        r"サイト[：:]\s*(.+)",
    ],
}


@dataclass
class TokushohoData:
    """Parsed data from a 特定商取引法 page."""
    url: str = ""
    is_tokushoho: bool = False
    seller_name: str = ""
    representative: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    confidence: float = 0.0
    raw_emails: list[dict] = None

    def __post_init__(self):
        if self.raw_emails is None:
            self.raw_emails = []


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def is_tokushoho_page(url: str, title: str = "", text: str = "") -> bool:
    """Check if a page is likely a tokushoho page."""
    url_lower = url.lower()
    title_lower = (title or "").lower()
    text_lower = (text or "").lower()

    # URL signals
    if any(re.search(p, url_lower) for p in TOKUSHOHO_URL_PATTERNS):
        return True

    # Title signals
    if any(re.search(p, title_lower) for p in TOKUSHOHO_TITLE_PATTERNS):
        return True

    # Content signals — must have "特定商取引法" somewhere
    if "特定商取引法" in text_lower or "特商法" in text_lower:
        return True

    return False


def find_tokushoho_links(html: str, base_url: str = "") -> list[str]:
    """Find links to tokushoho pages from HTML."""
    import re
    links: list[str] = []

    # Match <a href="..." with tokushoho-related link text
    link_pattern = re.compile(
        r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>'
        r'([^<]*?(?:特定商取引|特商法|販売業者|通信販売)[^<]*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for m in link_pattern.finditer(html):
        href = m.group(1).strip()
        links.append(href)

    # Also check href patterns directly
    href_pattern = re.compile(
        r'href=["\']([^"\']*(?:tokushoho|特定商取引|特商法|legal|commerce)[^"\']*)["\']',
        re.IGNORECASE,
    )
    for m in href_pattern.finditer(html):
        href = m.group(1).strip()
        if href not in links:
            links.append(href)

    return links


def parse_tokushoho_page(
    url: str,
    html: str = "",
    text: str = "",
    title: str = "",
) -> TokushohoData:
    """Parse a tokushoho page for structured data.

    Extracts seller name, representative, address, phone, email, website.
    Also runs email extraction for any emails on the page.
    """
    result = TokushohoData(url=url)

    if not is_tokushoho_page(url, title, text):
        return result

    result.is_tokushoho = True
    result.confidence = 0.8

    # Extract text if not provided
    if not text and html:
        text = _strip_html(html)

    # Parse structured fields
    for field_name, patterns in TOKUSHOHO_FIELD_PATTERNS.items():
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                value = m.group(1).strip()
                value = re.sub(r"<[^>]+>", "", value)  # strip any HTML
                value = value.rstrip("。、,.")
                if value:
                    setattr(result, field_name, value)
                    break

    # Extract emails
    extracted = extract_emails_from_page(html=html, visible_text=text, source_url=url)
    result.raw_emails = [e.__dict__ for e in extracted]

    # Set primary email from structured field or extracted
    if result.email and "@" in result.email:
        result.email = result.email.strip()
    elif extracted:
        result.email = extracted[0].email

    return result


def _strip_html(html: str) -> str:
    """Basic HTML to text stripping."""
    # Remove scripts and styles
    text = re.sub(r"<(?:script|style)[^>]*>.*?</(?:script|style)>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()
