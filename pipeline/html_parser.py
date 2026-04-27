from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any


class TextExtractor(HTMLParser):
    """Extract text, links, and images from HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.text_parts: list[str] = []
        self.links: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self._current_link: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if lowered == "a":
            self._current_link = {"href": attrs_dict.get("href", ""), "text": ""}
        if lowered == "img":
            self.images.append({
                "src": attrs_dict.get("src", ""),
                "alt": attrs_dict.get("alt", ""),
                "title": attrs_dict.get("title", ""),
            })

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if lowered == "a" and self._current_link is not None:
            self.links.append(self._current_link)
            self._current_link = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        cleaned = re.sub(r"\s+", " ", data).strip()
        if not cleaned:
            return
        self.text_parts.append(cleaned)
        if self._current_link is not None:
            self._current_link["text"] = f"{self._current_link.get('text', '')} {cleaned}".strip()


def extract_page_payload(url: str, html: str) -> dict[str, Any]:
    """Parse HTML into a structured payload with text, links, and images."""
    parser = TextExtractor()
    try:
        parser.feed(html or "")
    except Exception:
        pass
    text = re.sub(r"\s+", " ", " ".join(parser.text_parts)).strip()
    return {"url": url, "text": text, "links": parser.links, "images": parser.images, "html": html or ""}
