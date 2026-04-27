"""Mode A: Cold outreach pipeline.

Classifies a business, selects the correct generic PDF assets,
and builds a cold outreach email from the locked template.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .email_templates import SUBJECT, BODY, LINE_INPERSON, LINE_MACHINE
from .constants import (
    CHRIS_CONTACT,
    GENERIC_MACHINE_PDF,
    GENERIC_MENU_PDF,
)
from .models import QualificationResult


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_business(qualification: QualificationResult) -> str:
    """Classify what outreach assets a business needs.

    Returns one of: "menu_only", "menu_and_machine",
    "menu_machine_unconfirmed", "machine_only".
    """
    has_menu = qualification.menu_evidence_found
    has_machine = qualification.machine_evidence_found

    if has_menu and has_machine:
        return "menu_and_machine"
    if has_menu and not has_machine:
        return "menu_machine_unconfirmed"
    if not has_menu and has_machine:
        return "machine_only"
    # Default: no specific evidence but still a qualified lead.
    # Treat as menu-only outreach since menus are almost universal.
    return "menu_only"


# ---------------------------------------------------------------------------
# Asset selection
# ---------------------------------------------------------------------------

def select_outreach_assets(classification: str) -> list[Path]:
    """Return the list of generic PDF paths for the given classification."""
    if classification == "menu_and_machine":
        return [GENERIC_MENU_PDF, GENERIC_MACHINE_PDF]
    if classification == "machine_only":
        return []  # no send until machine-only template exists
    # "menu_only", "menu_machine_unconfirmed", and any fallback
    return [GENERIC_MENU_PDF]


# ---------------------------------------------------------------------------
# Email builder
# ---------------------------------------------------------------------------

class MachineOnlyNotSupportedError(Exception):
    """Raised when trying to send a machine-only email (no template yet)."""


def build_outreach_email(
    *,
    business_name: str,
    classification: str,
    include_inperson_line: bool = True,
) -> dict[str, str]:
    """Build a cold outreach email from the locked template.

    Returns {"subject": str, "body": str, "include_machine_image": bool}.
    Never calls any LLM or translation layer.

    Raises:
        MachineOnlyNotSupportedError: if classification is "machine_only".
    """
    if classification == "machine_only":
        raise MachineOnlyNotSupportedError(
            "No email template exists for machine-only outreach yet"
        )

    # Single universal template for all business types
    subject = SUBJECT.replace("{店名}", business_name)
    body = BODY.replace("{店名}", business_name)

    # Toggle in-person line
    if not include_inperson_line:
        body = _remove_inperson_line(body)

    # Insert machine line for menu_and_machine classification
    include_machine_image = False
    if classification == "menu_and_machine":
        body = _insert_machine_line(body)
        include_machine_image = True

    return {
        "subject": subject,
        "body": body,
        "include_machine_image": include_machine_image,
    }


def _remove_inperson_line(body: str) -> str:
    """Remove the in-person delivery line and its surrounding blank line."""
    line_with_newline = f"\n{LINE_INPERSON}\n"
    if line_with_newline in body:
        body = body.replace(line_with_newline, "\n")
    elif LINE_INPERSON in body:
        body = body.replace(LINE_INPERSON, "")
    return body


def _insert_machine_line(body: str) -> str:
    """Insert the ticket machine line after the menu sample paragraph."""
    anchor = "実際に制作する際は、貴店のメニュー内容に合わせて作成いたします。"
    replacement = f"{anchor}\n{LINE_MACHINE}"
    return body.replace(anchor, replacement, 1)
