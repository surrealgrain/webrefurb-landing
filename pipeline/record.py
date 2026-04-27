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

        # Normalised business name + area
        lead_name = lead.get("business_name", "")
        if norm_name and lead_name:
            if _normalise_name(lead_name) == norm_name:
                return lead

    return None


def create_lead_record(
    *,
    qualification: QualificationResult,
    preview_html: str,
    pitch_draft: dict[str, dict[str, str]],
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
        "source_urls": {},

        # Binary lead decision
        "lead": qualification.lead,
        "rejection_reason": qualification.rejection_reason,
        "lead_category": qualification.lead_category,

        # V1 scoring
        "english_menu_issue": qualification.english_menu_issue,
        "english_menu_issue_evidence": qualification.english_menu_issue_evidence,
        "tourist_exposure_score": qualification.tourist_exposure_score,
        "lead_score_v1": qualification.lead_score_v1,
        "recommended_primary_package": qualification.recommended_primary_package,

        # Evidence
        "evidence_classes": qualification.evidence_classes,
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
