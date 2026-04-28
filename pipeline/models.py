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
