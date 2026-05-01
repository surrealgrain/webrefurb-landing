"""Data models for the lead qualification system.

Self-contained — does not import from pipeline.models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReviewText:
    text: str
    language: str = ""           # "en", "ja", "mixed", "unknown"
    rating: int | None = None    # 1-5 star rating
    reviewer_name: str = ""
    reviewer_url: str = ""
    date: str = ""


@dataclass(frozen=True)
class ReviewScrapeResult:
    business_name: str
    place_id: str = ""
    map_url: str = ""
    reviews: list[ReviewText] = field(default_factory=list)
    total_review_count: int | None = None
    average_rating: float | None = None
    scrape_success: bool = False
    scrape_error: str = ""


@dataclass(frozen=True)
class PainSignalMatch:
    keyword: str
    language: str                # "en" or "ja"
    severity: str                # "high", "medium", "low"
    source: str                  # "google_review", "website_content", "website_evidence"
    context: str                 # surrounding text snippet (max 300 chars)
    review_text: str = ""


@dataclass(frozen=True)
class PainSignalAssessment:
    has_pain_signals: bool
    pain_score: int              # 0-100
    matches: list[PainSignalMatch] = field(default_factory=list)
    high_severity_count: int = 0
    medium_severity_count: int = 0
    low_severity_count: int = 0
    english_pain_count: int = 0
    japanese_pain_count: int = 0
    foreign_reviewer_count: int = 0
    summary: str = ""


@dataclass(frozen=True)
class QualifiedLeadEntry:
    # Identity
    business_name: str
    website: str
    address: str = ""
    phone: str = ""
    category: str = ""
    city: str = ""
    source: str = ""
    source_url: str = ""
    rating: float | None = None
    review_count: int | None = None

    # Phase 1: Menu evidence
    menu_evidence_found: bool = False
    machine_evidence_found: bool = False
    evidence_score: int = 0
    evidence_classes: list[str] = field(default_factory=list)
    evidence_urls: list[str] = field(default_factory=list)
    english_availability: str = "unknown"

    # Phase 2: Pain signals
    pain_assessment: PainSignalAssessment | None = None
    review_scrape_result: ReviewScrapeResult | None = None

    # Phase 3: Contact discovery
    contact_emails: list[str] = field(default_factory=list)
    has_contact_form: bool = False
    contact_form_url: str = ""

    # Scoring
    composite_score: float = 0.0
    tourist_exposure: float = 0.0
    recommended_package: str = ""
    outreach_priority: int = 0

    # Metadata
    qualification_phases_passed: list[str] = field(default_factory=list)
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "business_name": self.business_name,
            "website": self.website,
            "address": self.address,
            "phone": self.phone,
            "category": self.category,
            "city": self.city,
            "source": self.source,
            "source_url": self.source_url,
            "rating": self.rating,
            "review_count": self.review_count,
            "menu_evidence_found": self.menu_evidence_found,
            "machine_evidence_found": self.machine_evidence_found,
            "evidence_score": self.evidence_score,
            "evidence_classes": self.evidence_classes,
            "evidence_urls": self.evidence_urls,
            "english_availability": self.english_availability,
            "composite_score": round(self.composite_score, 2),
            "tourist_exposure": round(self.tourist_exposure, 3),
            "recommended_package": self.recommended_package,
            "outreach_priority": self.outreach_priority,
            "qualification_phases_passed": self.qualification_phases_passed,
            "rejection_reason": self.rejection_reason,
            "contact_emails": self.contact_emails,
            "has_contact_form": self.has_contact_form,
            "contact_form_url": self.contact_form_url,
        }
        if self.pain_assessment:
            d["pain_score"] = self.pain_assessment.pain_score
            d["pain_summary"] = self.pain_assessment.summary
            d["pain_matches_count"] = len(self.pain_assessment.matches)
            d["pain_high"] = self.pain_assessment.high_severity_count
            d["pain_medium"] = self.pain_assessment.medium_severity_count
            d["pain_low"] = self.pain_assessment.low_severity_count
        return d
