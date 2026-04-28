from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import utc_now, write_json, read_json, ensure_dir, slugify, sha256_text
from .models import QualificationResult, PreviewMenu, TicketMachineHint
from .constants import OUTREACH_STATUS_NEW


# ---------------------------------------------------------------------------
# Normalisation helpers for duplicate matching
# ---------------------------------------------------------------------------

def _normalise_domain(url: str) -> str:
    """Extract and normalise the registered domain from a URL."""
    import re
    url = url.strip().lower()
    # Strip protocol
    url = re.sub(r'^https?://', '', url)
    # Strip path/query
    url = url.split('/')[0].split('?')[0].split('#')[0]
    # Strip www
    url = re.sub(r'^www\.', '', url)
    # Strip port
    url = url.split(':')[0]
    return url


def _normalise_phone(phone: str) -> str:
    """Strip non-digit characters from a phone number."""
    import re
    return re.sub(r'\D', '', phone)


def _normalise_name(name: str) -> str:
    """Lowercase, strip whitespace and common suffixes for fuzzy name match."""
    import re
    n = name.strip().lower()
    n = re.sub(r'\s+', '', n)
    # Strip common Japanese address/store suffixes
    for suffix in ('店', '支店', '号店', '本店'):
        n = n.removesuffix(suffix)
    return n


def _extract_area(address: str) -> str:
    """Extract the first meaningful area component from an address."""
    import re
    # Take the part before the first comma, strip whitespace
    area = address.split(",")[0].strip()
    # Normalise: lowercase, collapse whitespace
    area = re.sub(r'\s+', '', area.lower())
    return area


CONTACT_PRIORITY = {
    "email": 0,
    "contact_form": 1,
    "line": 2,
    "instagram": 3,
    "phone": 4,
    "walk_in": 5,
    "website": 6,
}

ACTIONABLE_CONTACT_TYPES = {"email", "contact_form", "line", "instagram", "phone", "walk_in"}


def _normalise_contact_value(contact_type: str, value: str) -> str:
    cleaned = str(value or "").strip()
    if contact_type == "email":
        return cleaned.lower()
    if contact_type == "phone":
        return _normalise_phone(cleaned)
    return cleaned.lower()


def _build_contact_record(
    *,
    contact_type: str,
    value: str,
    label: str = "",
    href: str = "",
    source: str = "",
    source_url: str = "",
    actionable: bool | None = None,
) -> dict[str, Any]:
    cleaned_value = str(value or "").strip()
    cleaned_label = str(label or "").strip() or cleaned_value
    cleaned_href = str(href or "").strip()
    if actionable is None:
        actionable = contact_type in ACTIONABLE_CONTACT_TYPES
    return {
        "type": contact_type,
        "value": cleaned_value,
        "label": cleaned_label,
        "href": cleaned_href,
        "source": str(source or "").strip(),
        "source_url": str(source_url or "").strip(),
        "actionable": bool(actionable),
    }


def _append_contact(
    contacts: list[dict[str, Any]],
    seen: set[tuple[str, str]],
    *,
    contact_type: str,
    value: str,
    label: str = "",
    href: str = "",
    source: str = "",
    source_url: str = "",
    actionable: bool | None = None,
) -> None:
    normalized_value = _normalise_contact_value(contact_type, value)
    if not normalized_value:
        return
    key = (contact_type, normalized_value)
    if key in seen:
        return
    seen.add(key)
    contacts.append(_build_contact_record(
        contact_type=contact_type,
        value=value,
        label=label,
        href=href,
        source=source,
        source_url=source_url,
        actionable=actionable,
    ))


def normalise_lead_contacts(lead: dict[str, Any]) -> list[dict[str, Any]]:
    contacts: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for raw in lead.get("contacts") or []:
        contact_type = str(raw.get("type") or "").strip()
        if not contact_type:
            continue
        _append_contact(
            contacts,
            seen,
            contact_type=contact_type,
            value=str(raw.get("value") or ""),
            label=str(raw.get("label") or ""),
            href=str(raw.get("href") or ""),
            source=str(raw.get("source") or ""),
            source_url=str(raw.get("source_url") or ""),
            actionable=raw.get("actionable"),
        )

    if lead.get("email"):
        _append_contact(
            contacts,
            seen,
            contact_type="email",
            value=str(lead.get("email") or ""),
            href=f"mailto:{str(lead.get('email') or '').strip()}",
            source="legacy_record",
        )
    if lead.get("phone"):
        _append_contact(
            contacts,
            seen,
            contact_type="phone",
            value=str(lead.get("phone") or ""),
            href=f"tel:{_normalise_phone(str(lead.get('phone') or ''))}",
            source="legacy_record",
        )
    if lead.get("address"):
        _append_contact(
            contacts,
            seen,
            contact_type="walk_in",
            value=str(lead.get("address") or ""),
            label="Walk-in route",
            source="legacy_record",
        )
    if lead.get("website"):
        _append_contact(
            contacts,
            seen,
            contact_type="website",
            value=str(lead.get("website") or ""),
            label="Official website",
            href=str(lead.get("website") or ""),
            source="legacy_record",
            actionable=False,
        )

    contacts.sort(key=lambda contact: (CONTACT_PRIORITY.get(contact.get("type", ""), 99), str(contact.get("label") or "").lower()))
    return contacts


def get_primary_contact(lead: dict[str, Any]) -> dict[str, Any] | None:
    contacts = normalise_lead_contacts(lead)
    for contact in contacts:
        if contact.get("actionable"):
            return contact
    return contacts[0] if contacts else None


def get_primary_email_contact(lead: dict[str, Any]) -> dict[str, Any] | None:
    for contact in normalise_lead_contacts(lead):
        if contact.get("type") == "email":
            return contact
    return None


def has_supported_contact_route(lead: dict[str, Any]) -> bool:
    return any(bool(contact.get("actionable")) for contact in normalise_lead_contacts(lead))


def find_existing_lead(
    *,
    business_name: str = "",
    website: str = "",
    phone: str = "",
    place_id: str = "",
    address: str = "",
    state_root: Path | None = None,
) -> dict[str, Any] | None:
    """Find an existing lead matching any stable identifier.

    Matching priority: place_id > website domain > phone > normalised name+area.
    Returns the first matching lead record, or None.
    """
    leads = list_leads(state_root=state_root)

    norm_domain = _normalise_domain(website) if website else ""
    norm_phone = _normalise_phone(phone) if phone else ""
    norm_name = _normalise_name(business_name)

    for lead in leads:
        # Place ID (highest confidence)
        if place_id and lead.get("place_id") == place_id:
            return lead

        # Website domain
        lead_website = lead.get("website", "")
        if norm_domain and lead_website:
            if _normalise_domain(lead_website) == norm_domain:
                return lead

        # Phone number
        lead_phone = lead.get("phone", "")
        if norm_phone and lead_phone:
            if _normalise_phone(lead_phone) == norm_phone and len(norm_phone) >= 7:
                return lead

        # Normalised business name + area (never name alone)
        lead_name = lead.get("business_name", "")
        lead_address = lead.get("address", "")
        if norm_name and lead_name and _normalise_name(lead_name) == norm_name:
            if not address or not lead_address:
                # Can't cross-check area — don't exclude on name alone
                continue
            # Both have addresses: compare the first address component (area)
            cand_area = _extract_area(address)
            lead_area = _extract_area(lead_address)
            if not cand_area or not lead_area or cand_area != lead_area:
                # Same name, different area — different business
                continue
            return lead

    return None


def create_lead_record(
    *,
    qualification: QualificationResult,
    preview_html: str,
    pitch_draft: dict[str, dict[str, str]],
    contacts: list[dict[str, Any]] | None = None,
    source_query: str = "",
    state_root: Path | None = None,
) -> dict[str, Any]:
    """Create a lead record dict ready for persistence."""
    if state_root is None:
        state_root = Path(__file__).resolve().parent.parent / "state"

    business_name = qualification.business_name
    area = slugify(qualification.address.split(",")[0] if qualification.address else "unknown")
    name_slug = slugify(business_name)
    short_hash = sha256_text(f"{business_name}{qualification.website}")[:4]
    lead_id = f"wrm-{name_slug}-{area}-{short_hash}"

    preview_rel = f"state/previews/{lead_id}/english-menu.html"
    record_rel = f"state/leads/{lead_id}.json"
    contact_records = normalise_lead_contacts({"contacts": contacts or []})
    primary_contact = next((contact for contact in contact_records if contact.get("actionable")), None)
    email_contact = next((contact for contact in contact_records if contact.get("type") == "email"), None)

    return {
        # Identity
        "lead_id": lead_id,
        "generated_at": utc_now(),
        "business_name": business_name,
        "website": qualification.website,
        "address": qualification.address,
        "phone": qualification.phone,
        "place_id": qualification.place_id,
        "rating": qualification.rating,
        "reviews": qualification.reviews,

        # Source tracking
        "source_query": source_query,
        "source_urls": {
            "website": qualification.website,
            "map_url": qualification.map_url,
            "evidence_urls": qualification.evidence_urls,
        },
        "contacts": contact_records,
        "primary_contact": primary_contact,
        "has_supported_contact_route": bool(primary_contact),
        "email": email_contact["value"] if email_contact else "",

        # Binary lead decision
        "lead": qualification.lead,
        "rejection_reason": qualification.rejection_reason,
        "lead_category": qualification.lead_category,
        "establishment_profile": qualification.establishment_profile,
        "establishment_profile_evidence": qualification.establishment_profile_evidence,
        "establishment_profile_confidence": qualification.establishment_profile_confidence,
        "establishment_profile_source_urls": qualification.establishment_profile_source_urls,
        "establishment_profile_override": "",
        "establishment_profile_override_note": "",
        "establishment_profile_override_at": None,

        # V1 scoring
        "english_menu_issue": qualification.english_menu_issue,
        "english_menu_issue_evidence": qualification.english_menu_issue_evidence,
        "tourist_exposure_score": qualification.tourist_exposure_score,
        "lead_score_v1": qualification.lead_score_v1,
        "recommended_primary_package": qualification.recommended_primary_package,

        # Evidence
        "evidence_classes": qualification.evidence_classes,
        "evidence_urls": qualification.evidence_urls,
        "evidence_snippets": qualification.evidence_snippets,
        "image_locked_evidence": qualification.image_locked_evidence,
        "menu_evidence_found": qualification.menu_evidence_found,
        "machine_evidence_found": qualification.machine_evidence_found,
        "evidence_strength_score": qualification.evidence_strength_score,

        # V1 classification
        "primary_category_v1": qualification.primary_category_v1,

        # Pitch
        "pitch_draft": pitch_draft,

        # Production boundary
        "production_inputs_needed": [
            "full_menu_photos",
            *(["ticket_machine_photos"] if qualification.machine_evidence_found else []),
        ],
        "preview_available": qualification.preview_available,
        "pitch_available": qualification.pitch_available,

        # File paths
        "preview_path": preview_rel,
        "record_path": record_rel,
        "review_status": "pending",

        # Outreach tracking
        "outreach_status": OUTREACH_STATUS_NEW,
        "outreach_classification": None,
        "outreach_assets_selected": [],
        "outreach_sent_at": None,
        "outreach_draft_body": None,
        "outreach_include_inperson": True,
        "status_history": [
            {"status": OUTREACH_STATUS_NEW, "timestamp": utc_now()},
        ],
    }


def persist_lead_record(record: dict[str, Any], state_root: Path | None = None) -> Path:
    """Write a lead record to disk. Returns the path."""
    if state_root is None:
        state_root = Path(__file__).resolve().parent.parent / "state"

    leads_dir = state_root / "leads"
    ensure_dir(leads_dir)

    path = leads_dir / f"{record['lead_id']}.json"
    write_json(path, record)
    return path


def load_lead(lead_id: str, state_root: Path | None = None) -> dict[str, Any] | None:
    if state_root is None:
        state_root = Path(__file__).resolve().parent.parent / "state"
    path = state_root / "leads" / f"{lead_id}.json"
    return read_json(path)


def list_leads(state_root: Path | None = None) -> list[dict[str, Any]]:
    if state_root is None:
        state_root = Path(__file__).resolve().parent.parent / "state"
    leads_dir = state_root / "leads"
    if not leads_dir.exists():
        return []
    results = []
    for path in sorted(leads_dir.glob("wrm-*.json")):
        record = read_json(path)
        if record:
            results.append(record)
    return results
