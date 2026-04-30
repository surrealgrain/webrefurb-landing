"""Generate Japanese search queries for email discovery.

The intelligence here is specifically tuned for Japanese ramen/izakaya shops:
- Per-lead queries using shop name, phone, address
- Broad discovery queries for ramen/izakaya categories
- Specialized 特商法 / online-shop / operator-company patterns
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from .models import InputLead

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-lead query templates
# ---------------------------------------------------------------------------

SHOP_NAME_QUERIES = [
    '"{shop}" "メールアドレス"',
    '"{shop}" "お問い合わせ"',
    '"{shop}" "会社概要"',
    '"{shop}" "運営会社"',
    '"{shop}" "特定商取引法"',
    '"{shop}" "特商法"',
    '"{shop}" "公式"',
    '"{shop}" "公式通販"',
    '"{shop}" "オンラインショップ"',
    '"{shop}" "お取り寄せ"',
]

# Only add these if phone is available
PHONE_QUERIES = [
    '"{phone}" "メールアドレス"',
    '"{phone}" "会社情報"',
    '"{phone}" "求人"',
]

# Only add these if address is available (use first part of address)
ADDRESS_QUERIES = [
    '"{area}" "{shop}"',
    '"{area}" "メールアドレス"',
]

# Broader category queries (run once per batch, not per lead)
CATEGORY_QUERIES = [
    '"ラーメン" "特定商取引法" "メールアドレス"',
    '"ラーメン" "公式通販" "メールアドレス"',
    '"居酒屋" "会社概要" "メールアドレス"',
    '"居酒屋" "採用" "メールアドレス"',
    '"ラーメン" "運営会社" "お問い合わせ"',
    '"大衆酒場" "メールアドレス"',
    '"焼鳥" "特定商取引法" "メールアドレス"',
]

# Site-restricted queries for PR / shop platforms
SITE_QUERIES = [
    "site:tabelog.com {shop} メニュー",
    "site:hotpepper.jp {shop} メニュー",
    "site:gnavi.co.jp {shop} メニュー",
    "site:gurunavi.com {shop} メニュー",
    "site:retty.me {shop}",
    "site:hitosara.com {shop}",
    "site:prtimes.jp {shop} メールアドレス",
    "site:value-press.com {shop} メールアドレス",
    "site:thebase.in {shop} 特定商取引法",
    "site:stores.jp {shop} 特定商取引法",
    "site:shop-pro.jp {shop} メールアドレス",
]

# PR-time site queries (broad)
SITE_BROAD_QUERIES = [
    "site:tabelog.com ラーメン メニュー",
    "site:tabelog.com 居酒屋 英語メニュー",
    "site:hotpepper.jp 居酒屋 英語メニュー",
    "site:gnavi.co.jp 居酒屋 Menus in English",
    "site:ramendb.supleks.jp ラーメン 東京",
    "site:prtimes.jp ラーメン メールアドレス",
    "site:prtimes.jp 居酒屋 メールアドレス",
    "site:value-press.com ラーメン メールアドレス",
    "site:thebase.in ラーメン 特定商取引法",
    "site:stores.jp ラーメン 特定商取引法",
    "site:shop-pro.jp ラーメン メールアドレス",
]

# Recruitment-specific (used to find operator company)
RECRUITMENT_QUERIES = [
    '"{shop}" "求人" "メールアドレス"',
    '"{shop}" "採用" "お問い合わせ"',
]


# ---------------------------------------------------------------------------
# Query generation
# ---------------------------------------------------------------------------

def _address_area(address: str) -> str:
    """Extract the first meaningful part of a Japanese address for search."""
    if not address:
        return ""
    # Take up to the first 区/市/町/村 — typically the ward or city
    m = re.match(r"(..[都道府県])?\s*(.{1,6}?[区市町村])", address)
    if m:
        parts = [p for p in m.groups() if p]
        return "".join(parts)
    # Fallback: first 6 chars
    return address[:6].strip()


def generate_lead_queries(
    lead: InputLead,
    max_queries: int = 5,
    include_site_queries: bool = False,
) -> list[str]:
    """Generate prioritized search queries for one lead.

    Returns at most *max_queries* queries, ordered by expected email yield:
      1. Shop-name + メールアドレス (highest yield)
      2. Shop-name + 特商法/通販 (high yield for operator email)
      3. Shop-name + company/contact pages
      4. Phone-based queries (if phone available)
      5. Address-based queries (if address available)
      6. Site-restricted queries (optional, lower yield)
    """
    queries: list[str] = []
    shop = lead.shop_name
    phone = lead.phone
    area = _address_area(lead.address)

    # 1. Shop-name queries
    for tmpl in SHOP_NAME_QUERIES:
        queries.append(tmpl.format(shop=shop))

    # 2. Recruitment queries (for operator discovery)
    for tmpl in RECRUITMENT_QUERIES:
        queries.append(tmpl.format(shop=shop))

    # 3. Phone-based queries
    if phone:
        for tmpl in PHONE_QUERIES:
            queries.append(tmpl.format(phone=phone))

    # 4. Address-based queries
    if area:
        for tmpl in ADDRESS_QUERIES:
            queries.append(tmpl.format(shop=shop, area=area))

    # 5. Site-restricted queries (optional)
    if include_site_queries:
        for tmpl in SITE_QUERIES:
            queries.append(tmpl.format(shop=shop))

    return queries[:max_queries]


def generate_category_queries() -> list[str]:
    """Return broad category-discovery queries (run once per batch)."""
    return list(CATEGORY_QUERIES)


def generate_site_broad_queries() -> list[str]:
    """Return site-restricted broad queries (run once per batch)."""
    return list(SITE_BROAD_QUERIES)
