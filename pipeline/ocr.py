from __future__ import annotations

from typing import Any

from .models import OcrPhotoHint


def extract_ocr_hints(image_url_or_path: str) -> list[OcrPhotoHint]:
    """Extract structured hints from a menu image.

    V1 uses a deterministic stub that extracts from alt text, filenames,
    and known patterns. Real OCR/vision API can be wired in later.
    """
    hints: list[OcrPhotoHint] = []
    path = str(image_url_or_path).lower()

    # Deterministic stub: extract from filename patterns
    if any(p in path for p in ("menu", "kaken", "syokken", "kenbaiki", "ticket")):
        hints.append(OcrPhotoHint(
            photo_url=image_url_or_path,
            text_lines=["[deterministic stub: menu image detected by filename]"],
            section_headers=[],
            item_names=[],
            prices=[],
            confidence="low",
        ))

    return hints
