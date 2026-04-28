from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Evidence assessment
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EvidenceAssessment:
    is_ramen_candidate: bool
    is_izakaya_candidate: bool
    evidence_classes: list[str]
    menu_evidence_found: bool
    machine_evidence_found: bool
    course_or_drink_plan_evidence_found: bool
    score: int
    evidence_urls: list[str]
    best_evidence_url: str | None
    best_evidence_reason: str
    false_positive_risk: str
    hard_reject_reason: str | None = None
    snippets: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Binary lead result (v1: true or false, never "maybe")
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class QualificationResult:
    # Binary decision
    lead: bool
    rejection_reason: str | None

    # Identity
    business_name: str = ""
    website: str = ""
    category: str = ""
    address: str = ""
    phone: str = ""
    place_id: str = ""
    map_url: str = ""

    # Evidence
    lead_signals: list[str] = field(default_factory=list)
    evidence_classes: list[str] = field(default_factory=list)
    evidence_urls: list[str] = field(default_factory=list)
    evidence_snippets: list[str] = field(default_factory=list)
    image_locked_evidence: list[str] = field(default_factory=list)
    evidence_strength_score: int = 0

    # Menu / machine flags
    menu_evidence_found: bool = False
    machine_evidence_found: bool = False
    course_or_drink_plan_evidence_found: bool = False

    # English gap
    english_availability: str = "unknown"
    english_menu_issue: bool = False
    english_menu_issue_evidence: list[str] = field(default_factory=list)

    # V1 classification
    primary_category_v1: str = "other"  # "ramen" | "izakaya" | "other"
    lead_category: str = ""
    establishment_profile: str = "unknown"
    establishment_profile_evidence: list[str] = field(default_factory=list)
    establishment_profile_confidence: str = "low"
    establishment_profile_source_urls: list[str] = field(default_factory=list)

    # V1 scoring
    tourist_exposure_score: float = 0.0
    lead_score_v1: int = 0
    recommended_primary_package: str = ""

    # Misc
    rating: float | None = None
    reviews: int | None = None
    decision_reason: str = ""
    false_positive_risk: str = "medium"
    preview_available: bool = False
    pitch_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "business_name": self.business_name,
            "website": self.website,
            "lead": self.lead,
            "rejection_reason": self.rejection_reason,
            "primary_category_v1": self.primary_category_v1,
            "lead_category": self.lead_category,
            "establishment_profile": self.establishment_profile,
            "establishment_profile_evidence": self.establishment_profile_evidence,
            "establishment_profile_confidence": self.establishment_profile_confidence,
            "establishment_profile_source_urls": self.establishment_profile_source_urls,
            "english_menu_issue": self.english_menu_issue,
            "english_menu_issue_evidence": self.english_menu_issue_evidence,
            "tourist_exposure_score": self.tourist_exposure_score,
            "lead_score_v1": self.lead_score_v1,
            "recommended_primary_package": self.recommended_primary_package,
            "evidence_classes": self.evidence_classes,
            "evidence_urls": self.evidence_urls,
            "evidence_snippets": self.evidence_snippets,
            "menu_evidence_found": self.menu_evidence_found,
            "machine_evidence_found": self.machine_evidence_found,
            "evidence_strength_score": self.evidence_strength_score,
            "english_availability": self.english_availability,
            "decision_reason": self.decision_reason,
            "preview_available": self.preview_available or self.lead,
            "pitch_available": self.pitch_available or self.lead,
            "false_positive_risk": self.false_positive_risk,
        }


# ---------------------------------------------------------------------------
# Preview data model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PreviewItem:
    ja: str
    en: str
    price: str = ""
    source_url: str = ""
    source_type: str = ""
    confidence: str = "medium"  # "high" | "medium" | "low"


@dataclass(frozen=True)
class PreviewSection:
    header_ja: str
    header_en: str
    items: list[PreviewItem]


@dataclass(frozen=True)
class PreviewMenu:
    sections: list[PreviewSection]
    disclaimer_ja: str
    preview_basis: str = "scraped_public_evidence"
    preview_completeness: str = "partial_example"
    production_source_required: bool = True


# ---------------------------------------------------------------------------
# Ticket machine hints
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TicketMachineButton:
    label: str
    price: str = ""
    source_url: str = ""
    confidence: str = "medium"


@dataclass(frozen=True)
class TicketMachineHint:
    has_ticket_machine: bool
    layout_type_guess: str = ""
    buttons: list[TicketMachineButton] = field(default_factory=list)


# ---------------------------------------------------------------------------
# OCR interface types
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OcrPhotoHint:
    photo_url: str
    text_lines: list[str]
    section_headers: list[str]
    item_names: list[str]
    prices: list[str]
    confidence: str = "medium"


# ---------------------------------------------------------------------------
# Source adapter types
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class NormalizedSourceResult:
    source_name: str  # "tabelog", "google_maps", etc.
    source_url: str = ""
    menu_photos: list[str] = field(default_factory=list)
    ocr_text: list[str] = field(default_factory=list)
    multilingual_menu_flag: bool | None = None
    menu_photo_flag: bool | None = None
    structured_menu_items: list[dict[str, str]] = field(default_factory=list)
    review_snippets: list[str] = field(default_factory=list)
    category: str = ""
    rating: float | None = None
    review_count: int | None = None
    address: str = ""
    phone: str = ""
    place_id: str = ""


# ---------------------------------------------------------------------------
# Mode B: Extraction types
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ExtractedItem:
    name: str
    price: str = ""
    section_hint: str = ""
    japanese_name: str = ""
    source_text: str = ""
    source_provenance: str = ""
    approval_status: str = "pending_review"


@dataclass(frozen=True)
class TicketMachineRow:
    category: str
    buttons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TicketMachineLayout:
    rows: list[TicketMachineRow] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Mode B: Translation types
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TranslatedItem:
    name: str
    japanese_name: str
    price: str = ""
    description: str = ""
    section: str = ""
    source_text: str = ""
    source_provenance: str = ""
    approval_status: str = "pending_review"
    item_type: str = ""


# ---------------------------------------------------------------------------
# Mode B: Custom build input/output
# ---------------------------------------------------------------------------
@dataclass
class CustomBuildInput:
    restaurant_name: str
    menu_items_text: str = ""
    menu_photo_paths: list[str] = field(default_factory=list)
    ticket_machine_photo_path: str | None = None
    notes: str = ""


@dataclass(frozen=True)
class CustomBuildResult:
    output_dir: Path
    food_pdf: Path | None = None
    drinks_pdf: Path | None = None
    combined_pdf: Path | None = None
    ticket_machine_pdf: Path | None = None
    menu_json: Path | None = None


# ---------------------------------------------------------------------------
# P5: Order / Quote / Payment models
# ---------------------------------------------------------------------------
@dataclass
class QuoteDetails:
    """Structured quote data for a package order."""
    restaurant_name: str
    package_key: str
    package_label: str
    price_yen: int
    scope_description: str
    revision_limit: int
    delivery_terms: str
    update_terms: str
    payment_instructions: str
    expiry_date: str  # ISO date
    quote_date: str  # ISO date
    is_custom: bool = False
    custom_reason: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "restaurant_name": self.restaurant_name,
            "package_key": self.package_key,
            "package_label": self.package_label,
            "price_yen": self.price_yen,
            "scope_description": self.scope_description,
            "revision_limit": self.revision_limit,
            "delivery_terms": self.delivery_terms,
            "update_terms": self.update_terms,
            "payment_instructions": self.payment_instructions,
            "expiry_date": self.expiry_date,
            "quote_date": self.quote_date,
            "is_custom": self.is_custom,
            "custom_reason": self.custom_reason,
            "notes": self.notes,
        }


@dataclass
class PaymentDetails:
    """Payment tracking for an order."""
    method: str = ""  # "bank_transfer" | "manual"
    status: str = "pending"  # "pending" | "received" | "confirmed"
    amount_yen: int = 0
    reference: str = ""  # bank transfer reference or receipt number
    paid_at: str | None = None  # ISO timestamp
    confirmed_at: str | None = None  # ISO timestamp
    confirmed_by: str = ""  # operator who confirmed
    invoice_number: str = ""
    invoice_registration_number: str = ""  # Japanese invoice reg number if applicable

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "status": self.status,
            "amount_yen": self.amount_yen,
            "reference": self.reference,
            "paid_at": self.paid_at,
            "confirmed_at": self.confirmed_at,
            "confirmed_by": self.confirmed_by,
            "invoice_number": self.invoice_number,
            "invoice_registration_number": self.invoice_registration_number,
        }


@dataclass
class IntakeChecklist:
    """Owner intake checklist for production inputs."""
    full_menu_photos: bool = False
    ticket_machine_photos: bool = False
    price_confirmation: bool = False
    dietary_ingredient_notes: bool = False
    delivery_details: bool = False
    business_contact_confirmed: bool = False
    notes: str = ""

    def is_complete(self) -> bool:
        return all([
            self.full_menu_photos,
            self.price_confirmation,
            self.delivery_details,
            self.business_contact_confirmed,
        ])

    def to_dict(self) -> dict[str, Any]:
        return {
            "full_menu_photos": self.full_menu_photos,
            "ticket_machine_photos": self.ticket_machine_photos,
            "price_confirmation": self.price_confirmation,
            "dietary_ingredient_notes": self.dietary_ingredient_notes,
            "delivery_details": self.delivery_details,
            "business_contact_confirmed": self.business_contact_confirmed,
            "is_complete": self.is_complete(),
            "notes": self.notes,
        }


@dataclass
class OwnerApproval:
    """Record of owner approval for production output."""
    approved: bool = False
    approver_name: str = ""
    approved_package: str = ""
    approved_at: str | None = None  # ISO timestamp
    source_data_checksum: str = ""
    artifact_checksum: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "approver_name": self.approver_name,
            "approved_package": self.approved_package,
            "approved_at": self.approved_at,
            "source_data_checksum": self.source_data_checksum,
            "artifact_checksum": self.artifact_checksum,
            "notes": self.notes,
        }


@dataclass
class RevisionRecord:
    """Tracks revision rounds."""
    current_round: int = 0
    limit: int = 2
    history: list[dict[str, str]] = field(default_factory=list)

    def can_revise(self) -> bool:
        return self.current_round < self.limit

    def add_round(self, *, notes: str = "", requested_at: str = "") -> None:
        self.current_round += 1
        self.history.append({
            "round": str(self.current_round),
            "notes": notes,
            "requested_at": requested_at,
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_round": self.current_round,
            "limit": self.limit,
            "can_revise": self.can_revise(),
            "history": self.history,
        }


@dataclass
class Order:
    """Full order record linking a lead to a package purchase."""
    order_id: str
    lead_id: str
    business_name: str
    package_key: str
    state: str = "quoted"
    quote: QuoteDetails | None = None
    payment: PaymentDetails | None = None
    intake: IntakeChecklist | None = None
    approval: OwnerApproval | None = None
    revisions: RevisionRecord | None = None
    delivery_tracking: str = ""
    created_at: str = ""
    updated_at: str = ""
    state_history: list[dict[str, str]] = field(default_factory=list)
    privacy_note_accepted: bool = False
    custom_quote_triggers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "lead_id": self.lead_id,
            "business_name": self.business_name,
            "package_key": self.package_key,
            "state": self.state,
            "quote": self.quote.to_dict() if self.quote else None,
            "payment": self.payment.to_dict() if self.payment else None,
            "intake": self.intake.to_dict() if self.intake else None,
            "approval": self.approval.to_dict() if self.approval else None,
            "revisions": self.revisions.to_dict() if self.revisions else None,
            "delivery_tracking": self.delivery_tracking,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "state_history": self.state_history,
            "privacy_note_accepted": self.privacy_note_accepted,
            "custom_quote_triggers": self.custom_quote_triggers,
        }
