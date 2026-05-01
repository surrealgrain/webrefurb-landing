"""Tests for pipeline.lead_qualifier.queue (three-phase orchestrator)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from pipeline.lead_qualifier.models import (
    PainSignalAssessment,
    PainSignalMatch,
    QualifiedLeadEntry,
    ReviewScrapeResult,
    ReviewText,
)
from pipeline.lead_qualifier.queue import (
    _contact_quality_score,
    _dry_run_sample,
    _rank_outreach_queue,
    _update_entry,
    run_qualification_queue,
)


class TestDryRun:
    def test_dry_run_returns_sample(self):
        results = run_qualification_queue(city="Tokyo", category="ramen", dry_run=True)
        assert len(results) == 1
        assert results[0].business_name == "(dry run sample)"
        assert "dry_run" in results[0].qualification_phases_passed

    def test_dry_run_osaka(self):
        results = run_qualification_queue(city="Osaka", category="izakaya", dry_run=True)
        assert results[0].city == "Osaka"
        assert results[0].category == "izakaya"


class TestContactQualityScore:
    def test_email_scores_100(self):
        entry = QualifiedLeadEntry(
            business_name="Test", website="https://test.com",
            contact_emails=["test@example.com"],
        )
        assert _contact_quality_score(entry) == 100.0

    def test_contact_form_scores_60(self):
        entry = QualifiedLeadEntry(
            business_name="Test", website="https://test.com",
            has_contact_form=True, contact_form_url="https://test.com/contact",
        )
        assert _contact_quality_score(entry) == 60.0

    def test_no_contact_scores_0(self):
        entry = QualifiedLeadEntry(
            business_name="Test", website="https://test.com",
        )
        assert _contact_quality_score(entry) == 0.0

    def test_email_and_form_still_100(self):
        entry = QualifiedLeadEntry(
            business_name="Test", website="https://test.com",
            contact_emails=["test@example.com"],
            has_contact_form=True,
        )
        assert _contact_quality_score(entry) == 100.0


class TestRankOutreachQueue:
    def test_sorted_by_composite_score(self):
        low = QualifiedLeadEntry(
            business_name="Low", website="https://low.com",
            evidence_score=10,
            pain_assessment=PainSignalAssessment(has_pain_signals=True, pain_score=10, summary="low"),
        )
        high = QualifiedLeadEntry(
            business_name="High", website="https://high.com",
            evidence_score=70,
            pain_assessment=PainSignalAssessment(has_pain_signals=True, pain_score=60, summary="high"),
            contact_emails=["test@high.com"],
        )
        mid = QualifiedLeadEntry(
            business_name="Mid", website="https://mid.com",
            evidence_score=40,
            pain_assessment=PainSignalAssessment(has_pain_signals=True, pain_score=30, summary="mid"),
            has_contact_form=True,
        )
        ranked = _rank_outreach_queue([low, high, mid])
        assert ranked[0].business_name == "High"
        assert ranked[1].business_name == "Mid"
        assert ranked[2].business_name == "Low"

    def test_priority_assigned(self):
        entries = [
            QualifiedLeadEntry(
                business_name=f"Shop{i}", website=f"https://shop{i}.com",
                evidence_score=50 - i * 15,
                pain_assessment=PainSignalAssessment(
                    has_pain_signals=True, pain_score=60 - i * 20, summary="test"
                ),
            )
            for i in range(3)
        ]
        ranked = _rank_outreach_queue(entries)
        assert ranked[0].outreach_priority == 1
        assert ranked[1].outreach_priority == 2
        assert ranked[2].outreach_priority == 3

    def test_empty_list(self):
        assert _rank_outreach_queue([]) == []


class TestUpdateEntry:
    def test_update_single_field(self):
        original = QualifiedLeadEntry(
            business_name="Test", website="https://test.com",
        )
        updated = _update_entry(original, composite_score=42.5)
        assert updated.composite_score == 42.5
        assert updated.business_name == "Test"
        assert updated.website == "https://test.com"

    def test_update_preserves_other_fields(self):
        original = QualifiedLeadEntry(
            business_name="Test", website="https://test.com",
            city="Tokyo", category="ramen", evidence_score=75,
            menu_evidence_found=True,
        )
        updated = _update_entry(original, machine_evidence_found=True)
        assert updated.menu_evidence_found is True
        assert updated.machine_evidence_found is True
        assert updated.city == "Tokyo"
        assert updated.evidence_score == 75


class TestQualifiedLeadEntryToDict:
    def test_basic_fields(self):
        entry = QualifiedLeadEntry(
            business_name="Test Ramen",
            website="https://test.com",
            city="Tokyo",
            category="ramen",
            evidence_score=80,
        )
        d = entry.to_dict()
        assert d["business_name"] == "Test Ramen"
        assert d["website"] == "https://test.com"
        assert d["city"] == "Tokyo"
        assert d["category"] == "ramen"
        assert d["evidence_score"] == 80

    def test_pain_fields_included(self):
        pain = PainSignalAssessment(
            has_pain_signals=True,
            pain_score=45,
            summary="2 high-severity signals",
            high_severity_count=2,
            medium_severity_count=1,
            low_severity_count=0,
        )
        entry = QualifiedLeadEntry(
            business_name="Test",
            website="https://test.com",
            pain_assessment=pain,
        )
        d = entry.to_dict()
        assert d["pain_score"] == 45
        assert d["pain_summary"] == "2 high-severity signals"
        assert d["pain_matches_count"] == 0
        assert d["pain_high"] == 2

    def test_no_pain_fields_absent(self):
        entry = QualifiedLeadEntry(
            business_name="Test",
            website="https://test.com",
        )
        d = entry.to_dict()
        assert "pain_score" not in d


class TestOutputJson:
    def test_json_output(self, tmp_path):
        output_path = str(tmp_path / "queue.json")
        entries = [
            QualifiedLeadEntry(
                business_name="Test Ramen",
                website="https://test.com",
                composite_score=75.0,
                outreach_priority=1,
                qualification_phases_passed=["menu_evidence", "pain_signals"],
            )
        ]
        from pipeline.lead_qualifier.queue import _write_json_output
        _write_json_output(entries, output_path)

        with open(output_path) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["business_name"] == "Test Ramen"
        assert data[0]["composite_score"] == 75.0
        assert "menu_evidence" in data[0]["qualification_phases_passed"]
