"""Extract emails from HTML/text with Japanese obfuscation normalization.

Handles:
  - Full-width characters: info＠example.jp → info@example.jp
  - Bracket notation: info [at] example.jp, info(at)example.jp
  - Star substitution: info★example.jp (only when page context confirms ★→@)
  - mailto: links
  - Visible text patterns: メール：info@example.jp, E-mail：info@example.jp
  - False-positive filtering: CSS, JS, tracking IDs, image filenames, example.com
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Standard email pattern
_STANDARD_EMAIL = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# Full-width @: ＠
_FULLWIDTH_AT = re.compile(
    r"([a-zA-Z0-9._%+\-]+)\uff20([a-zA-Z0-9.\-\uff0d]+\.[a-zA-Z0-9.\-]{2,})"
)

# [at] / (at) notation
_BRACKET_AT = re.compile(
    r"([a-zA-Z0-9._%+\-]+)\s*(?:\[at\]|\(at\))\s*([a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
    re.IGNORECASE,
)

# ★ / ☆ substitution (context-dependent)
_STAR_AT = re.compile(
    r"([a-zA-Z0-9._%+\-]+)\s*[★☆]\s*([a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})"
)

# mailto: links in HTML
_MAILTO = re.compile(
    r'href=["\']mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})["\']',
    re.IGNORECASE,
)

# Japanese-prefixed email: メール：, E-mail：, Mail：
_PREFIX_EMAIL = re.compile(
    r"(?:メール|E-?mail|Mail|e-?mail|EMAIL)[：:\s]+([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
    re.IGNORECASE,
)

# False-positive domains/patterns to exclude
_FALSE_POSITIVE_DOMAINS = {
    "example.com", "example.jp", "example.net", "example.org",
    "email.com", "domain.com", "yourdomain.com", "xxx.com",
    "s-template.jp", "dummy.jp", "test.com", "test.jp",
    "localhost", "0.0.0.0",
    "sentry.io", "sentry.wixpress.com", "sentry-next.wixpress.com",
}

# False-positive prefixes/patterns in context
_FALSE_POSITIVE_CONTEXT = re.compile(
    r"(?:tracking[_-]?id|ga[_-]|gtm|pixel|beacon|spinner|loading|placeholder|screenshot|icon|logo|banner|favicon|background|gradient|css|stylesheet|script|noscript)",
    re.IGNORECASE,
)

# File extensions that indicate non-email text
_FILE_EXTENSIONS = re.compile(r"\.(?:png|jpg|jpeg|gif|svg|css|js|woff|ttf|ico|webp|mp4)(?:\?|$)", re.IGNORECASE)


@dataclass
class ExtractedEmail:
    email: str
    method: str  # "mailto", "standard", "fullwidth", "bracket", "star", "prefix"
    context: str = ""  # surrounding text snippet
    line: str = ""  # full line where found


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _normalize_fullwidth(text: str) -> str:
    """NFKC normalize and replace full-width chars."""
    text = unicodedata.normalize("NFKC", text)
    # Full-width hyphen → regular
    text = text.replace("\uff0d", "-")
    return text


def _star_context_confirms_at(text: str) -> bool:
    """Check if surrounding text explicitly says ★ means @.

    Look for patterns like:
      ★を@に変換
      ★→@
      （★は@に読み替えてください）
    """
    patterns = [
        r"[★☆]\s*[をは]?\s*[@＠]",
        r"[★☆].*?[@＠].*?変換|読[み]替[え]",
        r"[@＠].*?[★☆].*?変換|読[み]替[え]",
        r"スター.*?[@＠]",
    ]
    for p in patterns:
        if re.search(p, text):
            return True
    return False


def _clean_email(raw: str) -> str:
    """Lowercase and strip surrounding whitespace/punctuation."""
    email = raw.strip().lower()
    # Remove trailing punctuation that's not part of email
    email = re.sub(r"[.,;:!?)\]>}]+$", "", email)
    email = re.sub(r"^[<(\\[{]+", "", email)
    return email


def _is_false_positive(email: str, context: str = "") -> bool:
    """Check if an extracted email is a false positive."""
    local, _, domain = email.partition("@")

    # Known false-positive domains
    if domain in _FALSE_POSITIVE_DOMAINS:
        return True

    # Image/file paths mistaken for emails
    if _FILE_EXTENSIONS.search(email):
        return True

    # CSS/JS/tracking context
    if context and _FALSE_POSITIVE_CONTEXT.search(context):
        return True

    # Very short local parts that look like IDs
    if len(local) <= 1 and not local.isalpha():
        return True

    # Common non-email patterns
    if local in ("noreply", "no-reply", "mailer-daemon", "root", "admin"):
        if domain in _FALSE_POSITIVE_DOMAINS:
            return True

    return False


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

def extract_emails(
    text: str,
    html: str = "",
    source_url: str = "",
) -> list[ExtractedEmail]:
    """Extract all valid emails from text and/or HTML content.

    Args:
        text: Plain text or visible text extracted from HTML.
        html: Raw HTML (used for mailto: extraction).
        source_url: URL of the source page (for context).

    Returns:
        Deduplicated list of ExtractedEmail, ordered by confidence.
    """
    found: dict[str, ExtractedEmail] = {}

    def _add(email: str, method: str, context: str = "", line: str = ""):
        email = _clean_email(email)
        if not email or "@" not in email:
            return
        if _is_false_positive(email, context):
            return
        # Validate basic syntax
        if not _STANDARD_EMAIL.match(email):
            return
        if email not in found:
            found[email] = ExtractedEmail(
                email=email,
                method=method,
                context=context[:200],
                line=line[:300],
            )

    combined = text or ""
    if html:
        combined = html + "\n" + combined

    # 1. mailto: links (highest confidence)
    if html:
        for m in _MAILTO.finditer(html):
            _add(m.group(1), "mailto", line=m.group(0))

    # 2. Japanese-prefixed emails
    for m in _PREFIX_EMAIL.finditer(combined):
        _add(m.group(1), "prefix", context=m.group(0), line=m.group(0))

    # 3. Full-width @ emails
    for m in _FULLWIDTH_AT.finditer(combined):
        normalized = f"{m.group(1)}@{_normalize_fullwidth(m.group(2))}"
        _add(normalized, "fullwidth", context=m.group(0), line=m.group(0))

    # 4. Bracket [at] / (at) emails
    for m in _BRACKET_AT.finditer(combined):
        _add(f"{m.group(1)}@{m.group(2)}", "bracket", context=m.group(0), line=m.group(0))

    # 5. Star ★/☆ emails (only if context confirms)
    if _star_context_confirms_at(combined):
        for m in _STAR_AT.finditer(combined):
            _add(f"{m.group(1)}@{m.group(2)}", "star", context=m.group(0), line=m.group(0))

    # 6. Standard emails (lowest priority for dedup)
    for m in _STANDARD_EMAIL.finditer(combined):
        _add(m.group(0), "standard", context=m.group(0), line=m.group(0))

    return list(found.values())


def extract_emails_from_page(
    html: str,
    visible_text: str = "",
    source_url: str = "",
) -> list[ExtractedEmail]:
    """Convenience: extract from both raw HTML and visible text."""
    return extract_emails(
        text=visible_text,
        html=html,
        source_url=source_url,
    )
