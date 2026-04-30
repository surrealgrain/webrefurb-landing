"""Resolve operator companies behind shops.

Many ramen/izakaya shops don't publish emails under the shop name,
but their operating company does. This module resolves:
  shop → company name → company website → public email/contact form

Sources for operator discovery:
  - 特定商取引法 pages (seller_name field)
  - Recruitment pages (company name in job postings)
  - PR pages (press releases mention operating company)
  - Directory listings (Tabelog, Google Maps)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .models import OperatorCompany

# ---------------------------------------------------------------------------
# Company-name extraction patterns
# ---------------------------------------------------------------------------

# Common corporate suffixes
_COMPANY_SUFFIXES = [
    "株式会社", "有限会社", "合同会社", "合名会社", "合資会社",
    "株式会社", "(株)", "（株）", "(有)", "（有）", "(同)",
    "Co., Ltd.", "Co.,Ltd.", "Inc.", "Ltd.", "K.K.",
]

# Patterns for finding company names in text
_COMPANY_NAME_PATTERNS = [
    # "運営会社：株式会社〇〇" style
    r"運営会社[：:]\s*((?:株式会社|有限会社|合同会社).+?)(?:\n|$|<)",
    r"運営会社[：:]\s*(.+?)(?:\n|$|<)",
    # "販売業者：株式会社〇〇" (from tokushoho)
    r"販売業者[：:]\s*((?:株式会社|有限会社|合同会社).+?)(?:\n|$|<)",
    r"販売事業者[：:]\s*((?:株式会社|有限会社|合同会社).+?)(?:\n|$|<)",
    # "会社名：〇〇"
    r"(?:会社名|企業名|公司名)[：:]\s*(.+?)(?:\n|$|<)",
    # Parenthesized company
    r"((?:株式会社|有限会社|合同会社).{2,30}?)(?:\s|</|<|$)",
]

# URL extraction
_URL_PATTERN = re.compile(
    r'https?://[a-zA-Z0-9._\-]+\.[a-zA-Z]{2,}[a-zA-Z0-9./_\-]*'
)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

@dataclass
class CompanyInfo:
    name: str = ""
    url: str = ""
    email: str = ""
    source_url: str = ""
    source_type: str = ""  # "tokushoho", "recruitment", "pr", "directory"
    confidence: float = 0.0


def extract_company_name(text: str) -> Optional[str]:
    """Try to extract a company name from page text."""
    for pattern in _COMPANY_NAME_PATTERNS:
        m = re.search(pattern, text)
        if m:
            name = m.group(1).strip()
            # Clean up
            name = re.sub(r"<[^>]+>", "", name)
            name = re.sub(r"\s+", " ", name).strip()
            name = name.rstrip("。、,.")
            if len(name) >= 4:  # Minimum reasonable company name length
                return name
    return None


def extract_company_url(text: str, company_name: str = "") -> Optional[str]:
    """Try to find a company website URL in text."""
    # Look for URL near company name
    if company_name:
        # Find text around company name
        idx = text.find(company_name)
        if idx >= 0:
            nearby = text[max(0, idx - 200):idx + 500]
            urls = _URL_PATTERN.findall(nearby)
            if urls:
                return urls[0]

    # Fallback: look for URL with company-related labels
    url_label_patterns = [
        r"(?:ホームページ|HP|サイト|URL|website)[：:]\s*(https?://\S+)",
        r"(?:会社.*?URL|企業.*?URL|運営.*?URL)[：:]\s*(https?://\S+)",
    ]
    for pattern in url_label_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1).strip().rstrip("。、,.")

    return None


def resolve_from_tokushoho(
    tokushoho_data: "TokushohoData",
) -> Optional[CompanyInfo]:
    """Resolve operator company from parsed tokushoho data."""
    if not tokushoho_data or not tokushoho_data.is_tokushoho:
        return None

    name = tokushoho_data.seller_name
    if not name:
        return None

    info = CompanyInfo(
        name=name,
        url=tokushoho_data.website,
        email=tokushoho_data.email,
        source_url=tokushoho_data.url,
        source_type="tokushoho",
        confidence=0.8,
    )

    return info


def resolve_from_page(
    url: str,
    text: str,
    page_type: str = "",
) -> Optional[CompanyInfo]:
    """Try to extract operator company info from any page."""
    name = extract_company_name(text)
    if not name:
        return None

    company_url = extract_company_url(text, name)

    confidence = 0.5
    if page_type in ("company", "about"):
        confidence = 0.7
    elif page_type == "tokushoho":
        confidence = 0.8
    elif page_type in ("recruitment", "job"):
        confidence = 0.6

    return CompanyInfo(
        name=name,
        url=company_url or "",
        source_url=url,
        source_type=page_type,
        confidence=confidence,
    )


def company_info_to_operator(info: CompanyInfo) -> OperatorCompany:
    """Convert CompanyInfo to OperatorCompany model."""
    return OperatorCompany(
        name=info.name,
        url=info.url,
        email=info.email,
        source_url=info.source_url,
        source_type=info.source_type,
    )
