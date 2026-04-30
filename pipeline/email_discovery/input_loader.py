"""Load and normalize leads from CSV input."""

from __future__ import annotations

import csv
import logging
import re
import unicodedata
from pathlib import Path
from typing import Optional

from .models import InputLead

logger = logging.getLogger(__name__)

# Minimum required fields to attempt discovery
REQUIRED_FIELDS = {"shop_name"}


def _normalize_phone(raw: str) -> str:
    """Strip non-digit characters, keep leading + for international."""
    if not raw:
        return ""
    raw = raw.strip()
    plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    if plus and digits:
        return f"+{digits}"
    return digits


def _normalize_url(raw: str) -> str:
    """Basic URL cleanup."""
    if not raw:
        return ""
    url = raw.strip()
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _normalize_text(raw: str) -> str:
    """NFKC normalize Japanese text, collapse whitespace."""
    if not raw:
        return ""
    text = unicodedata.normalize("NFKC", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_leads_csv(path: str, encoding: str = "utf-8-sig") -> list[InputLead]:
    """Load leads from a CSV file.

    Accepts flexible column names (case-insensitive, hyphens/underscores/spaces equivalent).
    Skips rows that have no shop_name. Deduplicates by (shop_name, prefecture).
    """
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {path}")

    with open(csv_path, "r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)

    if not raw_rows:
        logger.warning("CSV file is empty: %s", path)
        return []

    # Normalize column names: lowercase, replace hyphens/spaces with underscores
    normalized_rows: list[dict[str, str]] = []
    for row in raw_rows:
        norm = {}
        for k, v in row.items():
            key = re.sub(r"[\s\-]+", "_", k.strip().lower()) if k else ""
            norm[key] = v or ""
        normalized_rows.append(norm)

    leads: list[InputLead] = []
    seen: set[str] = set()

    for i, row in enumerate(normalized_rows):
        shop_name = _normalize_text(row.get("shop_name", ""))
        if not shop_name:
            logger.debug("Row %d skipped: no shop_name", i + 1)
            continue

        prefecture = _normalize_text(row.get("prefecture", ""))
        dedup_key = f"{shop_name}|{prefecture}"
        if dedup_key in seen:
            logger.debug("Row %d skipped: duplicate %s", i + 1, shop_name)
            continue
        seen.add(dedup_key)

        lead = InputLead(
            shop_name=shop_name,
            genre=_normalize_text(row.get("genre", "")),
            address=_normalize_text(row.get("address", "")),
            city=_normalize_text(row.get("city", "")),
            prefecture=prefecture,
            phone=_normalize_phone(row.get("phone", "")),
            portal_url=_normalize_url(row.get("portal_url", "")),
            official_site_url=_normalize_url(row.get("official_site_url", "")),
            menu_url=_normalize_url(row.get("menu_url", "")),
            notes=row.get("notes", ""),
        )
        leads.append(lead)

    logger.info("Loaded %d leads from %s", len(leads), path)
    return leads
