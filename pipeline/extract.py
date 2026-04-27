"""Mode B: Menu item extraction from text, photos, and files."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .constants import PRICE_RE
from .models import ExtractedItem, TicketMachineLayout, TicketMachineRow


# ---------------------------------------------------------------------------
# Section header detection patterns
# ---------------------------------------------------------------------------
_SECTION_HEADER_RE = re.compile(
    r"^【(.+?)】\s*$|"
    r"^♦\s*(.+?)\s*$|"
    r"^——\s*(.+?)\s*——$|"
    r"^■\s+(.+?)\s*$|"
    r"^[◆◇★☆▶▸►]\s+(.+?)\s*$",
    re.MULTILINE,
)

_LINE_SPLIT_RE = re.compile(r"\n")

_PRICE_SUFFIX_RE = re.compile(
    r"\s+(¥\s?\d[\d,]*|\d{2,5}\s?円|\$\s?\d[\d,.]*)\s*$"
)


def extract_from_text(raw_text: str) -> list[ExtractedItem]:
    """Parse typed/pasted menu text into structured items.

    Detects Japanese section header patterns and extracts item name + price pairs.
    """
    items: list[ExtractedItem] = []
    current_section = ""

    for line in raw_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # Check if this is a section header
        header_match = _SECTION_HEADER_RE.match(line)
        if header_match:
            current_section = header_match.group(1) or header_match.group(2) or header_match.group(3) or header_match.group(4) or line
            continue

        # Extract price from end of line
        price = ""
        name = line
        price_match = _PRICE_SUFFIX_RE.search(line)
        if price_match:
            price = price_match.group(1).strip()
            name = line[:price_match.start()].strip()

        # Skip empty names
        if not name:
            continue

        items.append(ExtractedItem(
            name=name,
            price=price,
            section_hint=current_section,
            japanese_name=name,  # Will be set properly in translation step
        ))

    return items


def extract_from_photo(photo_path: str) -> list[ExtractedItem]:
    """Extract menu items from a photo using LLM vision API.

    Falls back to deterministic filename matching if API unavailable.
    """
    from .llm_client import call_vision

    path = Path(photo_path)
    if not path.exists():
        return []

    try:
        response = call_vision(
            image_path=str(path),
            system=(
                "You are a Japanese menu OCR system. Extract all menu items from this image. "
                "Return a JSON array of objects with keys: name (Japanese item name), "
                "price (as string, include currency symbol), section (section header if visible). "
                "Return only the JSON array, no other text."
            ),
            user="Extract all menu items from this photo. Return JSON only.",
        )
        parsed = json.loads(response)
        items = []
        for entry in parsed:
            if isinstance(entry, dict) and "name" in entry:
                items.append(ExtractedItem(
                    name=entry.get("name", ""),
                    price=entry.get("price", ""),
                    section_hint=entry.get("section", ""),
                    japanese_name=entry.get("name", ""),
                ))
        return items
    except Exception:
        return _fallback_extract_from_filename(photo_path)


def extract_from_file(file_path: str) -> list[ExtractedItem]:
    """Detect file type and route to appropriate extraction method."""
    path = Path(file_path)
    if not path.exists():
        return []

    suffix = path.suffix.lower()

    if suffix in (".txt", ".csv", ".md"):
        return extract_from_text(path.read_text(encoding="utf-8"))
    elif suffix in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"):
        return extract_from_photo(file_path)
    elif suffix == ".pdf":
        # PDF extraction — attempt text extraction first
        try:
            import subprocess
            result = subprocess.run(
                ["pdftotext", str(path), "-"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return extract_from_text(result.stdout)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return []
    else:
        return extract_from_text(path.read_text(encoding="utf-8", errors="replace"))


def extract_ticket_machine_layout(photo_path: str) -> TicketMachineLayout:
    """Extract button grid layout from a ticket machine photo.

    Returns a TicketMachineLayout with up to 4 rows of 4 buttons each.
    """
    from .llm_client import call_vision

    path = Path(photo_path)
    if not path.exists():
        return TicketMachineLayout(rows=[])

    try:
        response = call_vision(
            image_path=str(path),
            system=(
                "You are analyzing a Japanese ramen ticket vending machine photo. "
                "Identify all visible buttons organized in rows. "
                "Return a JSON object with key 'rows' containing an array of row objects. "
                "Each row has 'category' (e.g. 'ramen_row_1', 'sides_row') and "
                "'buttons' (array of up to 4 button label strings in Japanese). "
                "Maximum 4 rows, 4 buttons per row. Return only the JSON object."
            ),
            user="Identify the button layout of this ticket machine. Return JSON only.",
        )
        parsed = json.loads(response)
        rows = []
        for row_data in parsed.get("rows", [])[:4]:
            buttons = row_data.get("buttons", [])[:4]
            if buttons:
                rows.append(TicketMachineRow(
                    category=row_data.get("category", ""),
                    buttons=buttons,
                ))
        return TicketMachineLayout(rows=rows)
    except Exception:
        return TicketMachineLayout(rows=[])


def _fallback_extract_from_filename(photo_path: str) -> list[ExtractedItem]:
    """Deterministic fallback: extract hints from filename patterns."""
    from .constants import _FILENAME_MENU_PATTERNS
    path_lower = str(photo_path).lower()

    if not any(p in path_lower for p in _FILENAME_MENU_PATTERNS):
        return []

    return [ExtractedItem(
        name="[menu image detected — OCR required]",
        section_hint="",
    )]
