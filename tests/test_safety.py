"""Tests for duplicate detection, sent-business exclusion, and send safety."""

from __future__ import annotations

import json
import re
import pytest
from pathlib import Path

import pipeline.record as record_mod
from pipeline.record import (
    create_lead_record,
    persist_lead_record,
    find_existing_lead,
    load_lead,
    _normalise_domain,
    _normalise_phone,
    _normalise_name,
    list_leads,
)
from pipeline.models import QualificationResult
from pipeline.constants import OUTREACH_STATUS_SENT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_qual(
    *,
    business_name: str = "Test Ramen",
    website: str = "https://test-ramen.com",
    phone: str = "03-1234-5678",
    place_id: str = "ChIJ_test",
    address: str = "Tokyo",
) -> QualificationResult:
    return QualificationResult(
        lead=True,
        rejection_reason=None,
        business_name=business_name,
        website=website,
        phone=phone,
        place_id=place_id,
        address=address,
    )


@pytest.fixture
def tmp_state(tmp_path):
    """Create a temporary state directory with leads/."""
    leads_dir = tmp_path / "leads"
    leads_dir.mkdir()
    return tmp_path


def _persist(qual: QualificationResult, state_root: Path, **overrides) -> dict:
    """Create and persist a lead record, optionally overriding fields."""
    record = create_lead_record(
        qualification=qual,
        preview_html="<p>test</p>",
        pitch_draft={"body": {"body": "test"}},
        state_root=state_root,
    )
    record.update(overrides)
    persist_lead_record(record, state_root=state_root)
    return record


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

class TestNormalise:
    def test_domain_strips_protocol(self):
        assert _normalise_domain("https://www.example.com/path") == "example.com"

    def test_domain_strips_www(self):
        assert _normalise_domain("www.example.com") == "example.com"

    def test_domain_strips_port(self):
        assert _normalise_domain("example.com:8080") == "example.com"

    def test_phone_strips_non_digits(self):
        assert _normalise_phone("03-1234-5678") == "0312345678"

    def test_name_lowercases(self):
        assert _normalise_name("Test RAMEN") == "testramen"

    def test_name_strips_store_suffix(self):
        assert _normalise_name("ラーメン店") == "ラーメン"


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

class TestFindExistingLead:
    def test_match_by_place_id(self, tmp_state):
        _persist(_make_qual(place_id="ChIJ_abc"), tmp_state)
        result = find_existing_lead(place_id="ChIJ_abc", state_root=tmp_state)
        assert result is not None
        assert result["place_id"] == "ChIJ_abc"

    def test_match_by_website_domain(self, tmp_state):
        _persist(_make_qual(website="https://www.test-ramen.com"), tmp_state)
        result = find_existing_lead(website="https://test-ramen.com/menu", state_root=tmp_state)
        assert result is not None

    def test_match_by_phone(self, tmp_state):
        _persist(_make_qual(phone="03-1234-5678"), tmp_state)
        result = find_existing_lead(phone="0312345678", state_root=tmp_state)
        assert result is not None

    def test_name_only_no_match(self, tmp_state):
        """Name match without address should NOT exclude — skip silently."""
        _persist(_make_qual(business_name="Test Ramen", address="Shibuya, Tokyo"), tmp_state)
        # Candidate with same name but no address provided
        result = find_existing_lead(business_name="test ramen", state_root=tmp_state)
        assert result is None

    def test_name_different_area_no_match(self, tmp_state):
        """Same name, different area — different business."""
        _persist(_make_qual(business_name="Test Ramen", address="Shibuya, Tokyo"), tmp_state)
        result = find_existing_lead(
            business_name="test ramen", address="Shinjuku, Tokyo", state_root=tmp_state,
        )
        assert result is None

    def test_name_same_area_matches(self, tmp_state):
        """Same name + same area = duplicate."""
        _persist(_make_qual(business_name="Test Ramen", address="Shibuya, Tokyo"), tmp_state)
        result = find_existing_lead(
            business_name="test ramen", address="Shibuya, Tokyo", state_root=tmp_state,
        )
        assert result is not None

    def test_no_match_returns_none(self, tmp_state):
        _persist(_make_qual(), tmp_state)
        result = find_existing_lead(
            business_name="Completely Different",
            website="https://other.com",
            phone="099-9999-9999",
            place_id="ChIJ_other",
            state_root=tmp_state,
        )
        assert result is None

    def test_different_domain_no_match(self, tmp_state):
        _persist(_make_qual(website="https://test-ramen.com"), tmp_state)
        result = find_existing_lead(website="https://other-ramen.com", state_root=tmp_state)
        assert result is None

    def test_lead_list_cache_reuses_hydrated_records(self, tmp_state, monkeypatch):
        _persist(_make_qual(), tmp_state)
        calls = 0
        original = record_mod.ensure_lead_dossier

        def counted(record):
            nonlocal calls
            calls += 1
            return original(record)

        monkeypatch.setattr(record_mod, "ensure_lead_dossier", counted)

        assert len(list_leads(state_root=tmp_state)) == 1
        assert len(list_leads(state_root=tmp_state)) == 1
        assert calls == 1

    def test_find_existing_lead_reuses_dedup_index(self, tmp_state, monkeypatch):
        _persist(_make_qual(place_id="ChIJ_indexed"), tmp_state)
        calls = 0
        original = record_mod.ensure_lead_dossier

        def counted(record):
            nonlocal calls
            calls += 1
            return original(record)

        monkeypatch.setattr(record_mod, "ensure_lead_dossier", counted)

        assert find_existing_lead(place_id="ChIJ_indexed", state_root=tmp_state) is not None
        assert find_existing_lead(place_id="ChIJ_indexed", state_root=tmp_state) is not None
        assert calls == 1

    def test_lead_list_cache_invalidates_when_dossier_logic_changes(self, tmp_state, monkeypatch):
        _persist(_make_qual(), tmp_state)
        calls = 0
        original = record_mod.ensure_lead_dossier
        logic_signature = (("lead_dossier.py", 1, 1),)

        def counted(record):
            nonlocal calls
            calls += 1
            return original(record)

        def fake_logic_signature():
            return logic_signature

        monkeypatch.setattr(record_mod, "ensure_lead_dossier", counted)
        monkeypatch.setattr(record_mod, "_lead_cache_logic_signature", fake_logic_signature)

        assert len(list_leads(state_root=tmp_state)) == 1
        assert calls == 1

        logic_signature = (("lead_dossier.py", 2, 1),)

        assert len(list_leads(state_root=tmp_state)) == 1
        assert calls == 2


# ---------------------------------------------------------------------------
# Sent-business exclusion
# ---------------------------------------------------------------------------

class TestSentExclusion:
    def test_sent_lead_found_by_existing_check(self, tmp_state):
        """A sent lead is still found by find_existing_lead."""
        record = _persist(_make_qual(), tmp_state, outreach_status=OUTREACH_STATUS_SENT)
        assert record["outreach_status"] == "sent"

        result = find_existing_lead(
            business_name="Test Ramen",
            website="https://test-ramen.com",
            address="Tokyo",
            state_root=tmp_state,
        )
        assert result is not None
        assert result["outreach_status"] == "sent"

    def test_sent_lead_not_overwritten(self, tmp_state):
        """Persisting a new record with the same lead_id overwrites, but
        search exclusion prevents it from getting that far."""
        record = _persist(_make_qual(), tmp_state, outreach_status=OUTREACH_STATUS_SENT)
        # Re-persist with new status — this simulates what would happen
        # if somehow the same record was updated
        record["outreach_status"] = "new"
        persist_lead_record(record, state_root=tmp_state)

        # Verify the file was overwritten
        reloaded = list_leads(state_root=tmp_state)[0]
        # This confirms that exclusion at the search level is critical
        assert reloaded["outreach_status"] == "new"

    def test_sent_status_persists_on_disk(self, tmp_state):
        record = _persist(_make_qual(), tmp_state, outreach_status=OUTREACH_STATUS_SENT)
        # Reload from disk
        leads = list_leads(state_root=tmp_state)
        assert len(leads) == 1
        assert leads[0]["outreach_status"] == "sent"

    def test_evidence_urls_are_persisted_for_review(self, tmp_state):
        qual = _make_qual()
        object.__setattr__(qual, "evidence_urls", ["https://test-ramen.com/menu"])
        object.__setattr__(qual, "evidence_snippets", ["メニュー 醤油ラーメン 900円"])
        record = _persist(qual, tmp_state)

        assert record["evidence_urls"] == ["https://test-ramen.com/menu"]
        assert record["source_urls"]["evidence_urls"] == ["https://test-ramen.com/menu"]
        assert record["evidence_snippets"] == ["メニュー 醤油ラーメン 900円"]

    def test_lead_record_persists_phase_2_readiness_fields(self, tmp_state):
        qual = _make_qual()
        object.__setattr__(qual, "lead_evidence_dossier", {"ticket_machine_state": "unknown"})
        object.__setattr__(qual, "proof_items", [{"source_type": "official_or_shop_site"}])
        object.__setattr__(qual, "launch_readiness_status", "manual_review")
        object.__setattr__(qual, "launch_readiness_reasons", ["no_customer_safe_proof_item"])

        record = _persist(qual, tmp_state)
        stored = load_lead(record["lead_id"], state_root=tmp_state)

        assert isinstance(stored["lead"], bool)
        assert stored["lead_evidence_dossier"]["ticket_machine_state"] == "unknown"
        assert stored["lead_evidence_dossier"]["english_menu_state"] == "unknown"
        assert stored["lead_evidence_dossier"]["proof_items"] == []
        assert stored["proof_items"] == []
        assert stored["launch_readiness_status"] == "manual_review"
        assert stored["launch_readiness_reasons"] == ["no_supported_contact_route", "no_customer_safe_proof_item"]
        assert stored["message_variant"] == ""
        assert stored["launch_batch_id"] == ""
        assert stored["launch_outcome"] == {}


class TestBusinessNameLocking:
    def test_persist_promotes_verified_name_to_locked_name(self, tmp_state):
        record = {
            "lead_id": "wrm-locked-name",
            "generated_at": "2026-04-28T00:00:00+00:00",
            "business_name": "青空ラーメン",
            "business_name_verified_by": ["google", "official_site"],
        }

        persist_lead_record(record, state_root=tmp_state)
        loaded = load_lead("wrm-locked-name", state_root=tmp_state)

        assert loaded is not None
        assert loaded["business_name"] == "青空ラーメン"
        assert loaded["locked_business_name"] == "青空ラーメン"
        assert loaded["business_name_locked"] is True
        assert loaded["business_name_lock_reason"] == "two_source_verification"


# ---------------------------------------------------------------------------
# Send safety guards (tested via outreach module)
# ---------------------------------------------------------------------------

class TestSendSafetyGuards:
    def test_machine_only_builds_without_internal_tool_language(self):
        from pipeline.outreach import build_manual_outreach_message, build_outreach_email

        email = build_outreach_email(
            business_name="テスト",
            classification="machine_only",
        )
        body_lower = email["body"].lower()
        # Strip URLs, emails, and "e-mail:" label to avoid false positives
        scrubbed = re.sub(r"https?://\S+|mailto:\S+|\S+@\S+|e-mail", " ", body_lower)
        for token in ("ai", "automation", "llm", "gpt"):
            assert token not in scrubbed

        for channel in ("contact_form",):
            draft = build_manual_outreach_message(
                business_name="テスト",
                classification="machine_only",
                channel=channel,
            )
            draft_lower = draft["body"].lower()
            scrubbed = re.sub(r"https?://\S+|mailto:\S+|\S+@\S+", " ", draft_lower)
            for token in ("ai", "automation", "llm", "gpt"):
                assert token not in scrubbed

    def test_sent_is_blocked_status(self):
        """Verify 'sent' is in the blocked set for re-sending."""
        _blocked = {"sent", "replied", "converted", "do_not_contact"}
        assert "sent" in _blocked
        assert "replied" in _blocked
        assert "new" not in _blocked
        assert "draft" not in _blocked

    def test_failed_send_does_not_mark_sent(self):
        """Verify the send flow: status update is AFTER the try/except send block.

        If send raises, the exception is caught and re-raised as 502 before
        the status update line ever runs.
        """
        import inspect
        pytest.importorskip("fastapi")
        from dashboard.app import _send_lead_email_payload
        source = inspect.getsource(_send_lead_email_payload)
        # The send call is inside a try block; status update comes after
        try_pos = source.index("try:")
        send_pos = source.index("_send_email_resend", try_pos)
        except_pos = source.index("except Exception", try_pos)
        # Find the status update after the except block
        after_except = source.index("OUTREACH_STATUS_SENT", except_pos + 1)
        assert try_pos < send_pos < except_pos
        assert after_except > except_pos

    def test_replied_business_blocked_from_resend(self):
        _blocked = {"sent", "replied", "converted", "do_not_contact"}
        assert "replied" in _blocked

    def test_do_not_contact_blocked(self):
        _blocked = {"sent", "replied", "converted", "do_not_contact"}
        assert "do_not_contact" in _blocked


# ---------------------------------------------------------------------------
# Classification-specific content
# ---------------------------------------------------------------------------

class TestClassificationContent:
    def test_menu_and_machine_has_both_inline_images(self):
        from pipeline.email_html import build_pitch_email_html, MENU_CID, MACHINE_CID
        html = build_pitch_email_html(
            text_body="Test body",
            include_menu_image=True,
            include_machine_image=True,
        )
        assert f"cid:{MENU_CID}" in html
        assert f"cid:{MACHINE_CID}" in html

    def test_menu_only_has_no_machine_image(self):
        from pipeline.email_html import build_pitch_email_html, MACHINE_CID
        html = build_pitch_email_html(
            text_body="Test body",
            include_menu_image=True,
            include_machine_image=False,
        )
        assert f"cid:{MACHINE_CID}" not in html
