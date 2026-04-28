"""Tests for API endpoints."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock


# ---------------------------------------------------------------------------
# We test the API endpoints by importing the FastAPI app and using
# the TestClient. These tests require fastapi + httpx installed.
# ---------------------------------------------------------------------------

try:
    from fastapi.testclient import TestClient
    from dashboard.app import app
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestAPIEndpoints:
    """Test API endpoints with a mock pipeline."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        self.client = TestClient(app)
        # Override state root to temp directory
        import dashboard.app as dash_app
        monkeypatch.setattr(dash_app, "STATE_ROOT", tmp_path)
        monkeypatch.setattr(dash_app, "QR_DOCS_ROOT", tmp_path / "docs")
        (tmp_path / "leads").mkdir()
        (tmp_path / "jobs").mkdir()
        (tmp_path / "sent").mkdir()
        (tmp_path / "uploads").mkdir()
        (tmp_path / "docs").mkdir()

    def test_get_leads_empty(self):
        response = self.client.get("/api/leads")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_leads_with_data(self, tmp_path):
        lead = {
            "lead_id": "wrm-test-001",
            "business_name": "Test Ramen",
            "lead": True,
            "lead_score_v1": 75,
            "outreach_status": "new",
            "menu_evidence_found": True,
            "machine_evidence_found": False,
        }
        (tmp_path / "leads" / "wrm-test-001.json").write_text(
            json.dumps(lead), encoding="utf-8"
        )

        response = self.client.get("/api/leads")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["business_name"] == "Test Ramen"

    def test_delete_lead_removes_record(self, tmp_path):
        lead = {
            "lead_id": "wrm-test-delete",
            "business_name": "Delete Ramen",
            "lead": True,
            "email": "owner@delete-ramen.test",
            "lead_score_v1": 75,
            "outreach_status": "new",
            "menu_evidence_found": True,
            "machine_evidence_found": False,
        }
        path = tmp_path / "leads" / "wrm-test-delete.json"
        path.write_text(json.dumps(lead), encoding="utf-8")

        response = self.client.delete("/api/leads/wrm-test-delete")
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"
        assert not path.exists()
        assert self.client.get("/api/leads").json() == []

    def test_delete_lead_not_found(self):
        response = self.client.delete("/api/leads/nonexistent")
        assert response.status_code == 404

    def test_main_page_hides_non_sendable_statuses(self, tmp_path):
        active = {
            "lead_id": "wrm-test-active",
            "business_name": "Active Ramen",
            "lead": True,
            "email": "owner@active-ramen.test",
            "lead_score_v1": 75,
            "outreach_status": "new",
            "menu_evidence_found": True,
            "machine_evidence_found": False,
        }
        sent = {**active, "lead_id": "wrm-test-sent", "business_name": "Sent Ramen", "outreach_status": "sent"}
        dnc = {**active, "lead_id": "wrm-test-dnc-hidden", "business_name": "DNC Ramen", "outreach_status": "do_not_contact"}
        for lead in (active, sent, dnc):
            (tmp_path / "leads" / f"{lead['lead_id']}.json").write_text(
                json.dumps(lead), encoding="utf-8"
            )

        response = self.client.get("/")
        assert response.status_code == 200
        assert "Active Ramen" in response.text
        assert "Sent Ramen" not in response.text
        assert "DNC Ramen" not in response.text

    def test_main_page_keeps_non_email_leads_with_supported_contact_routes(self, tmp_path):
        with_email = {
            "lead_id": "wrm-test-email",
            "business_name": "Email Ramen",
            "lead": True,
            "email": "owner@email-ramen.test",
            "lead_score_v1": 75,
            "outreach_status": "new",
            "menu_evidence_found": True,
            "machine_evidence_found": False,
        }
        no_email_supported = {
            **with_email,
            "lead_id": "wrm-test-no-email-supported",
            "business_name": "No Email Ramen",
            "email": "",
            "contacts": [
                {"type": "contact_form", "value": "https://no-email-ramen.test/contact", "label": "Contact form", "href": "https://no-email-ramen.test/contact", "actionable": True},
                {"type": "website", "value": "https://no-email-ramen.test", "label": "Official website", "href": "https://no-email-ramen.test", "actionable": False},
            ],
        }
        no_email_unsupported = {
            **with_email,
            "lead_id": "wrm-test-no-email-unsupported",
            "business_name": "Website Only Ramen",
            "email": "",
            "phone": "",
            "address": "",
            "contacts": [
                {"type": "website", "value": "https://website-only-ramen.test", "label": "Official website", "href": "https://website-only-ramen.test", "actionable": False},
            ],
        }
        for lead in (with_email, no_email_supported, no_email_unsupported):
            (tmp_path / "leads" / f"{lead['lead_id']}.json").write_text(
                json.dumps(lead), encoding="utf-8"
            )

        response = self.client.get("/")
        assert response.status_code == 200
        assert "Email Ramen" in response.text
        assert "No Email Ramen" in response.text
        assert "Website Only Ramen" not in response.text

    def test_main_page_renders_establishment_profile_summary(self, tmp_path):
        lead = {
            "lead_id": "wrm-test-profile",
            "business_name": "Profile Ramen",
            "lead": True,
            "email": "owner@profile-ramen.test",
            "lead_score_v1": 75,
            "outreach_status": "new",
            "menu_evidence_found": True,
            "machine_evidence_found": False,
            "establishment_profile": "ramen_ticket_machine",
            "establishment_profile_confidence": "high",
            "establishment_profile_evidence": ["ticket_machine_evidence"],
            "establishment_profile_source_urls": ["https://profile-ramen.test/menu"],
        }
        (tmp_path / "leads" / "wrm-test-profile.json").write_text(
            json.dumps(lead), encoding="utf-8"
        )

        response = self.client.get("/")
        assert response.status_code == 200
        assert "Ramen With Ticket Machine" in response.text

    def test_profile_override_endpoint_persists_override(self, tmp_path):
        self._create_lead(
            tmp_path,
            lead_id="wrm-test-profile-override",
            establishment_profile="ramen_only",
            establishment_profile_confidence="medium",
            establishment_profile_evidence=["primary_category:ramen"],
            establishment_profile_source_urls=["https://example.test/menu"],
        )

        response = self.client.post(
            "/api/leads/wrm-test-profile-override/profile",
            json={"profile": "ramen_with_sides_add_ons", "note": "Sides visible on official menu"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["establishment_profile_effective"] == "ramen_with_sides_add_ons"
        assert data["establishment_profile_mode"] == "operator_override"
        assert data["establishment_profile_override_note"] == "Sides visible on official menu"

        stored = json.loads((tmp_path / "leads" / "wrm-test-profile-override.json").read_text(encoding="utf-8"))
        assert stored["establishment_profile_override"] == "ramen_with_sides_add_ons"
        assert stored["establishment_profile_override_note"] == "Sides visible on official menu"

    def test_profile_override_endpoint_clears_override(self, tmp_path):
        self._create_lead(
            tmp_path,
            lead_id="wrm-test-profile-clear",
            establishment_profile="ramen_only",
            establishment_profile_override="ramen_with_sides_add_ons",
            establishment_profile_override_note="Operator correction",
        )

        response = self.client.post(
            "/api/leads/wrm-test-profile-clear/profile",
            json={"clear_override": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["establishment_profile_effective"] == "ramen_only"
        assert data["establishment_profile_mode"] == "evidence"

        stored = json.loads((tmp_path / "leads" / "wrm-test-profile-clear.json").read_text(encoding="utf-8"))
        assert stored["establishment_profile_override"] == ""
        assert stored["establishment_profile_override_note"] == ""

    def test_outreach_preview_marks_non_email_route_as_manual(self, tmp_path):
        self._create_lead(
            tmp_path,
            lead_id="wrm-test-form-route",
            email="",
            contacts=[
                {"type": "contact_form", "value": "https://form-route.test/contact", "label": "Contact form", "href": "https://form-route.test/contact", "actionable": True},
                {"type": "website", "value": "https://form-route.test", "label": "Official website", "href": "https://form-route.test", "actionable": False},
            ],
        )

        response = self.client.get("/api/outreach/wrm-test-form-route")
        assert response.status_code == 200
        data = response.json()
        assert data["send_enabled"] is False
        assert data["contact_action"] == "use_contact_form"
        assert data["primary_contact"]["type"] == "contact_form"

    def test_mark_manual_contacted_sets_route_specific_status(self, tmp_path):
        self._create_lead(
            tmp_path,
            lead_id="wrm-test-manual-contact",
            email="",
            contacts=[
                {"type": "contact_form", "value": "https://form-route.test/contact", "label": "Contact form", "href": "https://form-route.test/contact", "actionable": True},
            ],
        )

        response = self.client.post(
            "/api/leads/wrm-test-manual-contact/contacted",
            json={"note": "Submitted contact form"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["outreach_status"] == "contacted_form"
        assert data["contact_type"] == "contact_form"

        stored = json.loads((tmp_path / "leads" / "wrm-test-manual-contact.json").read_text(encoding="utf-8"))
        assert stored["outreach_status"] == "contacted_form"
        assert stored["outreach_contacted_via"] == "contact_form"
        assert stored["status_history"][-1]["status"] == "contacted_form"

    def test_mark_manual_contacted_rejects_email_only_lead(self, tmp_path):
        self._create_lead(
            tmp_path,
            lead_id="wrm-test-email-only",
            email="owner@email-only.test",
            contacts=[
                {"type": "email", "value": "owner@email-only.test", "label": "owner@email-only.test", "href": "mailto:owner@email-only.test", "actionable": True},
            ],
        )

        response = self.client.post(
            "/api/leads/wrm-test-email-only/contacted",
            json={},
        )
        assert response.status_code == 400

    def test_outreach_lead_not_found(self):
        response = self.client.post("/api/outreach/nonexistent")
        assert response.status_code == 404

    def test_send_lead_not_found(self):
        response = self.client.post(
            "/api/send/nonexistent",
            json={"email": "test@test.com", "subject": "Test", "body": "Test"},
        )
        assert response.status_code == 404

    def test_sent_empty(self):
        response = self.client.get("/api/sent")
        assert response.status_code == 200
        assert response.json() == []

    def test_sent_endpoint_hides_test_sends(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RESEND_FROM_EMAIL", "chris@webrefurb.com")
        real = {
            "lead_id": "wrm-real",
            "to": "owner@restaurant.test",
            "subject": "Real send",
            "body": "body",
            "sent_at": "2026-01-01T00:00:00+00:00",
            "status": "sent",
            "test_send": False,
        }
        test = {**real, "lead_id": "wrm-test", "to": "chris@webrefurb.com", "subject": "Test send", "test_send": True}
        old_test = {**real, "lead_id": "wrm-old-test", "to": "chris@webrefurb.com", "subject": "Old test send"}
        lead = {
            "lead_id": "wrm-real",
            "business_name": "Restaurant",
            "lead": True,
            "email": "owner@restaurant.test",
            "outreach_status": "sent",
        }
        (tmp_path / "leads" / "wrm-real.json").write_text(json.dumps(lead), encoding="utf-8")
        (tmp_path / "sent" / "real.json").write_text(json.dumps(real), encoding="utf-8")
        (tmp_path / "sent" / "test.json").write_text(json.dumps(test), encoding="utf-8")
        (tmp_path / "sent" / "old-test.json").write_text(json.dumps(old_test), encoding="utf-8")

        response = self.client.get("/api/sent")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["lead_id"] == "wrm-real"

    def test_build_status_not_found(self):
        response = self.client.get("/api/build/nonexistent/status")
        assert response.status_code == 404

    def test_main_page_renders(self):
        response = self.client.get("/")
        assert response.status_code == 200
        assert "WebRefurbMenu" in response.text

    def _create_lead(self, tmp_path, lead_id="wrm-test-dnc", **overrides):
        """Helper to create a lead record for testing."""
        lead = {
            "lead_id": lead_id,
            "business_name": "Test Ramen",
            "lead": True,
            "lead_score_v1": 75,
            "outreach_status": "new",
            "outreach_classification": None,
            "outreach_assets_selected": [],
            "outreach_sent_at": None,
            "outreach_draft_body": None,
            "outreach_include_inperson": True,
            "status_history": [],
            "menu_evidence_found": True,
            "machine_evidence_found": False,
            "primary_category_v1": "ramen",
            "establishment_profile": "ramen_only",
            "establishment_profile_confidence": "medium",
            "establishment_profile_evidence": ["primary_category:ramen"],
            "establishment_profile_source_urls": ["https://example.test/menu"],
            "rejection_reason": None,
        }
        lead.update(overrides)
        (tmp_path / "leads" / f"{lead_id}.json").write_text(
            json.dumps(lead), encoding="utf-8"
        )
        return lead

    def test_outreach_blocked_for_do_not_contact(self, tmp_path):
        self._create_lead(tmp_path, outreach_status="do_not_contact")
        response = self.client.post("/api/outreach/wrm-test-dnc")
        assert response.status_code == 403
        assert "Do Not Contact" in response.json()["detail"]

    def test_send_blocked_for_do_not_contact(self, tmp_path):
        self._create_lead(tmp_path, outreach_status="do_not_contact")
        response = self.client.post(
            "/api/send/wrm-test-dnc",
            json={"email": "test@test.com", "subject": "T", "body": "T"},
        )
        assert response.status_code == 403
        assert "Do Not Contact" in response.json()["detail"]

    def test_flag_dnc(self, tmp_path):
        self._create_lead(tmp_path)
        response = self.client.post(
            "/api/flag-dnc/wrm-test-dnc",
            json={"flag": True},
        )
        assert response.status_code == 200
        assert response.json()["outreach_status"] == "do_not_contact"

        # Verify persisted
        stored = json.loads((tmp_path / "leads" / "wrm-test-dnc.json").read_text())
        assert stored["outreach_status"] == "do_not_contact"

    def test_unflag_dnc(self, tmp_path):
        self._create_lead(tmp_path, outreach_status="do_not_contact")
        response = self.client.post(
            "/api/flag-dnc/wrm-test-dnc",
            json={"flag": False},
        )
        assert response.status_code == 200
        assert response.json()["outreach_status"] == "new"

    def test_opt_out_detection(self, tmp_path):
        self._create_lead(tmp_path, outreach_status="sent")
        response = self.client.post(
            "/api/incoming-reply/wrm-test-dnc",
            json={"body": "不要です。ありがとうございました。"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "opted_out"

        # Verify persisted
        stored = json.loads((tmp_path / "leads" / "wrm-test-dnc.json").read_text())
        assert stored["outreach_status"] == "do_not_contact"

    def test_opt_out_no_match(self, tmp_path):
        self._create_lead(tmp_path, outreach_status="sent")
        response = self.client.post(
            "/api/incoming-reply/wrm-test-dnc",
            json={"body": "興味があります！もっと教えてください。"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["outreach_status"] == "sent"

    def test_incoming_reply_detects_photo_attachments(self, tmp_path):
        self._create_lead(tmp_path, outreach_status="sent", business_name="Photo Reply Ramen")
        response = self.client.post(
            "/api/incoming-reply/wrm-test-dnc",
            json={
                "channel": "form",
                "from": "owner@example.test",
                "subject": "メニュー写真",
                "body": "メニュー写真を添付します。",
                "attachments": [
                    {
                        "filename": "menu.jpg",
                        "content_type": "image/jpeg",
                        "content": "/9j/4AAQSkZJRgABAQAAAQABAAD/2w==",
                    },
                    {"filename": "notes.txt", "content_type": "text/plain"},
                ],
            },
        )

        assert response.status_code == 200
        assert response.json()["channel"] == "form"

        replies = self.client.get("/api/replies?channel=form").json()["replies"]
        assert len(replies) == 1
        assert replies[0]["business_name"] == "Photo Reply Ramen"
        assert replies[0]["has_photos"] is True
        assert replies[0]["photo_count"] == 1
        assert replies[0]["stored_photo_count"] == 1
        assert replies[0]["attachments"][0]["stored_path"]

    def test_incoming_reply_without_photos_has_no_menu_handoff(self, tmp_path):
        self._create_lead(tmp_path, outreach_status="sent")
        response = self.client.post(
            "/api/incoming-reply/wrm-test-dnc",
            json={
                "channel": "email",
                "from": "owner@example.test",
                "subject": "Re:",
                "body": "興味があります。詳細を教えてください。",
            },
        )

        assert response.status_code == 200
        replies = self.client.get("/api/replies?channel=email").json()["replies"]
        assert len(replies) == 1
        assert replies[0]["has_photos"] is False
        assert replies[0]["photo_count"] == 0

    def test_incoming_reply_detects_japanese_photo_send_language(self, tmp_path):
        self._create_lead(tmp_path, outreach_status="sent")
        response = self.client.post(
            "/api/incoming-reply/wrm-test-dnc",
            json={
                "channel": "email",
                "from": "owner@example.test",
                "subject": "メニュー写真",
                "body": "メニューの写真を送付します。確認をお願いします。",
            },
        )

        assert response.status_code == 200
        replies = self.client.get("/api/replies?channel=email").json()["replies"]
        assert len(replies) == 1
        assert replies[0]["has_photos"] is True
        assert replies[0]["photo_count"] == 0

    def test_qr_create_requires_ready_reply(self, tmp_path):
        self._create_lead(tmp_path, outreach_status="sent", business_name="QR Ramen")
        reply_response = self.client.post(
            "/api/incoming-reply/wrm-test-dnc",
            json={
                "channel": "email",
                "from": "owner@example.test",
                "subject": "QRメニュー",
                "body": "QRコード付き英語メニューページをお願いします。",
                "attachments": [
                    {
                        "filename": "menu.jpg",
                        "content_type": "image/jpeg",
                        "content": "/9j/4AAQSkZJRgABAQAAAQABAAD/2w==",
                    }
                ],
            },
        )
        reply_id = reply_response.json()["reply_id"]

        response = self.client.post(
            f"/api/qr/{reply_id}",
            json={
                "items": [
                    {
                        "name": "Shoyu Ramen",
                        "japanese_name": "醤油ラーメン",
                        "price": "¥900",
                        "description": "Classic soy sauce ramen.",
                        "ingredients": ["noodles", "soy sauce broth"],
                        "description_confirmation": True,
                        "ingredient_allergen_confirmation": True,
                        "section": "Ramen",
                    }
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready_for_review"
        assert (tmp_path / "docs" / "menus" / "_drafts" / data["job_id"] / "index.html").exists()

        sign = self.client.post(f"/api/qr/{data['job_id']}/sign")
        assert sign.status_code == 200
        assert sign.json()["qr_sign_url"].endswith("/qr_sign.html")
        assert (tmp_path / "docs" / "menus" / "_drafts" / data["job_id"] / "qr_sign.html").exists()

    def test_qr_publish_and_health(self, tmp_path):
        self._create_lead(tmp_path, outreach_status="sent", business_name="QR Ramen")
        reply_response = self.client.post(
            "/api/incoming-reply/wrm-test-dnc",
            json={
                "channel": "email",
                "from": "owner@example.test",
                "subject": "QR menu",
                "body": "Please make the hosted QR menu.",
                "attachments": [
                    {
                        "filename": "menu.jpg",
                        "content_type": "image/jpeg",
                        "content": "/9j/4AAQSkZJRgABAQAAAQABAAD/2w==",
                    }
                ],
            },
        )
        reply_id = reply_response.json()["reply_id"]
        create = self.client.post(
            f"/api/qr/{reply_id}",
            json={
                "items": [
                    {
                        "name": "Shoyu Ramen",
                        "japanese_name": "醤油ラーメン",
                        "description": "Classic soy sauce ramen.",
                        "ingredients": ["noodles", "soy sauce broth"],
                        "description_confirmation": True,
                        "ingredient_allergen_confirmation": True,
                        "section": "Ramen",
                    }
                ]
            },
        ).json()

        published = self.client.post(f"/api/qr/{create['job_id']}/publish")
        assert published.status_code == 200
        assert published.json()["live_url"] == "https://webrefurb.com/menus/qr-ramen/"

        health = self.client.get("/api/qr/qr-ramen/health")
        assert health.status_code == 200
        assert health.json()["ok"] is True

    def test_qr_photo_only_reply_returns_needs_extraction_job(self, tmp_path):
        self._create_lead(tmp_path, outreach_status="sent", business_name="QR Ramen")
        reply_response = self.client.post(
            "/api/incoming-reply/wrm-test-dnc",
            json={
                "channel": "email",
                "from": "owner@example.test",
                "subject": "QR menu",
                "body": "Please make the hosted QR menu.",
                "attachments": [
                    {
                        "filename": "menu.jpg",
                        "content_type": "image/jpeg",
                        "content": "/9j/4AAQSkZJRgABAQAAAQABAAD/2w==",
                    }
                ],
            },
        )
        reply_id = reply_response.json()["reply_id"]

        response = self.client.post(f"/api/qr/{reply_id}", json={})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "needs_extraction"
        assert data["extraction_required"] is True
        assert data["validation"]["errors"] == ["structured_menu_items_required"]
        assert not (tmp_path / "docs" / "menus" / "_drafts" / data["job_id"] / "index.html").exists()

    def test_qr_extract_endpoint_turns_needs_extraction_job_into_reviewable_draft(self, tmp_path):
        self._create_lead(tmp_path, outreach_status="sent", business_name="QR Ramen")
        reply_response = self.client.post(
            "/api/incoming-reply/wrm-test-dnc",
            json={
                "channel": "email",
                "from": "owner@example.test",
                "subject": "QR menu",
                "body": "Please make the hosted QR menu.",
                "attachments": [
                    {
                        "filename": "menu.jpg",
                        "content_type": "image/jpeg",
                        "content": "/9j/4AAQSkZJRgABAQAAAQABAAD/2w==",
                    }
                ],
            },
        )
        reply_id = reply_response.json()["reply_id"]
        create = self.client.post(f"/api/qr/{reply_id}", json={}).json()

        extract = self.client.post(
            f"/api/qr/{create['job_id']}/extract",
            json={"raw_text": "醤油ラーメン ¥900\n餃子 ¥450"},
        )

        assert extract.status_code == 200
        data = extract.json()
        assert data["status"] == "ready_for_review"
        assert data["extraction_method"] == "structured_payload"
        assert (tmp_path / "docs" / "menus" / "_drafts" / create["job_id"] / "index.html").exists()

        review = self.client.get(f"/api/qr/{create['job_id']}/review")
        assert review.status_code == 200
        assert review.json()["extraction_required"] is False
        assert review.json()["completeness"]["item_count"] == 2

    def test_qr_confirm_endpoint_unlocks_publish(self, tmp_path):
        self._create_lead(tmp_path, outreach_status="sent", business_name="QR Ramen")
        reply_response = self.client.post(
            "/api/incoming-reply/wrm-test-dnc",
            json={
                "channel": "email",
                "from": "owner@example.test",
                "subject": "QR menu",
                "body": "Please make the hosted QR menu.",
                "attachments": [
                    {
                        "filename": "menu.jpg",
                        "content_type": "image/jpeg",
                        "content": "/9j/4AAQSkZJRgABAQAAAQABAAD/2w==",
                    }
                ],
            },
        )
        reply_id = reply_response.json()["reply_id"]
        create = self.client.post(
            f"/api/qr/{reply_id}",
            json={
                "items": [
                    {
                        "name": "Shoyu Ramen",
                        "japanese_name": "醤油ラーメン",
                        "description": "Classic soy sauce ramen.",
                        "ingredients": ["noodles", "soy sauce broth"],
                        "section": "Ramen",
                    }
                ]
            },
        ).json()

        blocked = self.client.post(f"/api/qr/{create['job_id']}/publish")
        assert blocked.status_code == 422
        assert "description_owner_confirmation_required" in blocked.json()["detail"]

        confirmed = self.client.post(f"/api/qr/{create['job_id']}/confirm", json={})
        assert confirmed.status_code == 200

        published = self.client.post(f"/api/qr/{create['job_id']}/publish")
        assert published.status_code == 200
        assert published.json()["status"] == "published"

    def test_qr_package_approve_and_download(self, tmp_path, monkeypatch):
        def fake_html_to_pdf_sync(html_path: Path, pdf_path: Path, *, print_profile=None) -> Path:
            pdf_path.write_bytes(b"%PDF-1.4\n% qr sign\n")
            return pdf_path

        monkeypatch.setattr("pipeline.qr.html_to_pdf_sync", fake_html_to_pdf_sync)
        self._create_lead(tmp_path, outreach_status="sent", business_name="QR Ramen")
        reply_response = self.client.post(
            "/api/incoming-reply/wrm-test-dnc",
            json={
                "channel": "email",
                "from": "owner@example.test",
                "subject": "QR menu",
                "body": "Please make the hosted QR menu.",
                "attachments": [
                    {
                        "filename": "menu.jpg",
                        "content_type": "image/jpeg",
                        "content": "/9j/4AAQSkZJRgABAQAAAQABAAD/2w==",
                    }
                ],
            },
        )
        reply_id = reply_response.json()["reply_id"]
        create = self.client.post(
            f"/api/qr/{reply_id}",
            json={
                "items": [
                    {
                        "name": "Shoyu Ramen",
                        "japanese_name": "醤油ラーメン",
                        "description": "Classic soy sauce ramen.",
                        "ingredients": ["noodles", "soy sauce broth"],
                        "description_confirmation": True,
                        "ingredient_allergen_confirmation": True,
                        "section": "Ramen",
                    }
                ]
            },
        ).json()
        self.client.post(f"/api/qr/{create['job_id']}/sign")

        approved = self.client.post(f"/api/qr/{create['job_id']}/approve")
        assert approved.status_code == 200
        assert approved.json()["package_key"] == "package_3_qr_menu_65k"
        assert approved.json()["final_export_status"] == "ready"

        download = self.client.get(f"/api/qr/{create['job_id']}/download")
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/zip"

    def test_qr_health_endpoint_flags_missing_sign_pdf_after_approval(self, tmp_path, monkeypatch):
        def fake_html_to_pdf_sync(html_path: Path, pdf_path: Path, *, print_profile=None) -> Path:
            pdf_path.write_bytes(b"%PDF-1.4\n% qr sign\n")
            return pdf_path

        monkeypatch.setattr("pipeline.qr.html_to_pdf_sync", fake_html_to_pdf_sync)
        self._create_lead(tmp_path, outreach_status="sent", business_name="QR Ramen")
        reply_response = self.client.post(
            "/api/incoming-reply/wrm-test-dnc",
            json={
                "channel": "email",
                "from": "owner@example.test",
                "subject": "QR menu",
                "body": "Please make the hosted QR menu.",
                "attachments": [
                    {
                        "filename": "menu.jpg",
                        "content_type": "image/jpeg",
                        "content": "/9j/4AAQSkZJRgABAQAAAQABAAD/2w==",
                    }
                ],
            },
        )
        reply_id = reply_response.json()["reply_id"]
        create = self.client.post(
            f"/api/qr/{reply_id}",
            json={
                "items": [
                    {
                        "name": "Shoyu Ramen",
                        "japanese_name": "醤油ラーメン",
                        "description": "Classic soy sauce ramen.",
                        "ingredients": ["noodles", "soy sauce broth"],
                        "description_confirmation": True,
                        "ingredient_allergen_confirmation": True,
                        "section": "Ramen",
                    }
                ]
            },
        ).json()
        self.client.post(f"/api/qr/{create['job_id']}/sign")
        approved = self.client.post(f"/api/qr/{create['job_id']}/approve").json()
        Path(approved["qr_sign_print_ready_pdf"]).unlink()

        health = self.client.get("/api/qr/qr-ramen/health")
        assert health.status_code == 200
        assert health.json()["ok"] is False
        assert "sign_pdf_missing" in health.json()["errors"]


# ---------------------------------------------------------------------------
# Dashboard QA tests — draft, send safety, classification, status persistence
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestDraftSaveAndLoad:
    """Test draft persistence and retrieval."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        self.client = TestClient(app)
        import dashboard.app as dash_app
        monkeypatch.setattr(dash_app, "STATE_ROOT", tmp_path)
        (tmp_path / "leads").mkdir()
        (tmp_path / "jobs").mkdir()
        (tmp_path / "sent").mkdir()
        (tmp_path / "uploads").mkdir()
        self.tmp_path = tmp_path

    def _create_lead(self, lead_id="wrm-draft-test", **overrides):
        lead = {
            "lead_id": lead_id,
            "business_name": "Draft Test Ramen",
            "lead": True,
            "lead_score_v1": 80,
            "outreach_status": "draft",
            "outreach_classification": "menu_only",
            "outreach_assets_selected": [],
            "outreach_sent_at": None,
            "outreach_draft_body": None,
            "outreach_include_inperson": True,
            "status_history": [{"status": "new", "timestamp": "2026-01-01T00:00:00"}],
            "menu_evidence_found": True,
            "machine_evidence_found": False,
            "primary_category_v1": "ramen",
            "establishment_profile": "ramen_only",
            "establishment_profile_confidence": "medium",
            "establishment_profile_evidence": ["primary_category:ramen"],
            "establishment_profile_source_urls": ["https://example.test/menu"],
            "rejection_reason": None,
        }
        lead.update(overrides)
        (self.tmp_path / "leads" / f"{lead_id}.json").write_text(
            json.dumps(lead), encoding="utf-8"
        )
        return lead

    def test_save_draft(self):
        self._create_lead()
        response = self.client.post(
            "/api/draft/wrm-draft-test",
            json={
                "body": "Edited body content",
                "english_body": "Edited English content",
                "subject": "テスト件名",
                "include_inperson": False,
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "saved"

        # Verify persisted to disk
        stored = json.loads(
            (self.tmp_path / "leads" / "wrm-draft-test.json").read_text()
        )
        assert stored["outreach_draft_body"] == "Edited body content"
        assert stored["outreach_draft_english_body"] == "Edited English content"
        assert stored["outreach_draft_subject"] == "テスト件名"
        assert stored["outreach_draft_manually_edited"] is True

    def test_save_draft_lead_not_found(self):
        response = self.client.post(
            "/api/draft/nonexistent",
            json={"body": "test", "subject": "test"},
        )
        assert response.status_code == 404

    def test_outreach_returns_business_name(self):
        """Outreach endpoint should include business_name and email for preview."""
        self._create_lead()
        response = self.client.post("/api/outreach/wrm-draft-test")
        assert response.status_code == 200
        data = response.json()
        assert data["business_name"] == "Draft Test Ramen"
        assert "subject" in data
        assert "body" in data
        assert "english_body" in data
        assert "preview_html" in data
        assert "classification" in data
        assert "assets" in data

    def test_preview_get_loads_saved_draft(self):
        """Opening preview should load the persisted draft, not regenerate."""
        self._create_lead(
            outreach_draft_body="Saved draft body",
            outreach_draft_english_body="Saved English draft",
            outreach_draft_subject="Saved subject",
            outreach_draft_manually_edited=True,
        )
        response = self.client.get("/api/outreach/wrm-draft-test")
        assert response.status_code == 200
        data = response.json()
        assert data["body"] == "Saved draft body"
        assert data["english_body"] == "Saved English draft"
        assert data["subject"] == "Saved subject"

    def test_regenerate_post_clears_saved_draft(self):
        self._create_lead(
            outreach_draft_body="Saved draft body",
            outreach_draft_subject="Saved subject",
            outreach_draft_manually_edited=True,
        )
        response = self.client.post("/api/outreach/wrm-draft-test")
        assert response.status_code == 200
        data = response.json()
        assert data["body"] != "Saved draft body"

        stored = json.loads(
            (self.tmp_path / "leads" / "wrm-draft-test.json").read_text()
        )
        assert stored["outreach_draft_body"] is None
        assert stored["outreach_draft_english_body"] is None
        assert stored["outreach_draft_subject"] is None
        assert stored["outreach_draft_manually_edited"] is False

    def test_translate_default_english_draft_to_japanese_preview(self):
        self._create_lead()
        preview = self.client.get("/api/outreach/wrm-draft-test").json()
        response = self.client.post(
            "/api/translate-draft",
            json={
                "english_body": preview["english_body"],
                "business_name": preview["business_name"],
                "classification": preview["classification"],
                "include_inperson": preview["include_inperson"],
                "include_machine_image": preview["include_machine_image"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "突然のご連絡にて失礼いたします。" in data["body"]
        assert "menu-sample.jpg" in data["preview_html"]

    def test_draft_status_persists_after_save(self):
        self._create_lead()
        # Save a draft
        self.client.post(
            "/api/draft/wrm-draft-test",
            json={"body": "saved draft", "subject": "test"},
        )
        # Verify the file still has draft status, not overwritten
        stored = json.loads(
            (self.tmp_path / "leads" / "wrm-draft-test.json").read_text()
        )
        assert stored["outreach_status"] == "draft"
        assert stored["outreach_draft_body"] == "saved draft"


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestSendSafety:
    """Test send blocking, double-send prevention, and status guards."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        self.client = TestClient(app)
        import dashboard.app as dash_app
        monkeypatch.setattr(dash_app, "STATE_ROOT", tmp_path)
        (tmp_path / "leads").mkdir()
        (tmp_path / "jobs").mkdir()
        (tmp_path / "sent").mkdir()
        (tmp_path / "uploads").mkdir()
        self.tmp_path = tmp_path

    def _create_lead(self, lead_id="wrm-send-test", **overrides):
        lead = {
            "lead_id": lead_id,
            "business_name": "Send Test Ramen",
            "lead": True,
            "email": "test@test.com",
            "lead_score_v1": 80,
            "outreach_status": "draft",
            "outreach_classification": "menu_only",
            "outreach_assets_selected": [],
            "outreach_sent_at": None,
            "outreach_draft_body": "Test body",
            "outreach_include_inperson": True,
            "status_history": [{"status": "draft", "timestamp": "2026-01-01T00:00:00"}],
            "menu_evidence_found": True,
            "machine_evidence_found": False,
            "primary_category_v1": "ramen",
            "establishment_profile": "ramen_only",
            "establishment_profile_confidence": "medium",
            "establishment_profile_evidence": ["primary_category:ramen"],
            "establishment_profile_source_urls": ["https://example.test/menu"],
            "rejection_reason": None,
        }
        lead.update(overrides)
        (self.tmp_path / "leads" / f"{lead_id}.json").write_text(
            json.dumps(lead), encoding="utf-8"
        )
        return lead

    def test_send_blocked_for_sent_status(self):
        self._create_lead(outreach_status="sent")
        response = self.client.post(
            "/api/send/wrm-send-test",
            json={"email": "test@test.com", "subject": "T", "body": "T"},
        )
        assert response.status_code == 409
        assert "cannot re-send" in response.json()["detail"]

    def test_send_blocked_for_replied_status(self):
        self._create_lead(outreach_status="replied")
        response = self.client.post(
            "/api/send/wrm-send-test",
            json={"email": "test@test.com", "subject": "T", "body": "T"},
        )
        assert response.status_code == 409

    def test_send_blocked_for_converted_status(self):
        self._create_lead(outreach_status="converted")
        response = self.client.post(
            "/api/send/wrm-send-test",
            json={"email": "test@test.com", "subject": "T", "body": "T"},
        )
        assert response.status_code == 409

    @pytest.mark.parametrize("status", ["bounced", "invalid", "skipped", "rejected", "needs_review", "contacted_form", "contacted_line", "contacted_instagram", "called", "visited"])
    def test_send_blocked_for_non_sendable_statuses(self, status):
        self._create_lead(outreach_status=status)
        response = self.client.post(
            "/api/send/wrm-send-test",
            json={"email": "test@test.com", "subject": "T", "body": "T"},
        )
        assert response.status_code == 409

    def test_send_requires_email(self):
        self._create_lead()
        response = self.client.post(
            "/api/send/wrm-send-test",
            json={"email": "", "subject": "T", "body": "T"},
        )
        assert response.status_code == 400
        assert "Email address required" in response.json()["detail"]

    def test_send_rejects_invalid_email(self):
        self._create_lead()
        response = self.client.post(
            "/api/send/wrm-send-test",
            json={"email": "not-an-email", "subject": "T", "body": "T"},
        )
        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

    def test_send_requires_subject(self):
        self._create_lead()
        response = self.client.post(
            "/api/send/wrm-send-test",
            json={"email": "test@test.com", "subject": "", "body": "T"},
        )
        assert response.status_code == 400

    def test_send_requires_body(self):
        self._create_lead()
        response = self.client.post(
            "/api/send/wrm-send-test",
            json={"email": "test@test.com", "subject": "T", "body": ""},
        )
        assert response.status_code == 400

    def test_send_blocks_missing_required_attachment(self):
        self._create_lead(outreach_classification="menu_only")
        response = self.client.post(
            "/api/send/wrm-send-test",
            json={"email": "test@test.com", "subject": "T", "body": "T", "assets": []},
        )
        assert response.status_code == 400
        assert "Required attachment missing" in response.json()["detail"]

    def test_send_uses_saved_draft_when_body_omitted(self):
        from pipeline.constants import GENERIC_MENU_PDF

        self._create_lead(
            outreach_classification="menu_only",
            outreach_assets_selected=[str(GENERIC_MENU_PDF)],
            outreach_draft_subject="Saved subject",
            outreach_draft_body="Saved body",
        )
        with patch("dashboard.app._send_email_resend", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"id": "mock-send"}
            response = self.client.post(
                "/api/send/wrm-send-test",
                json={"email": "test@test.com"},
            )
        assert response.status_code == 200
        stored = json.loads(
            (self.tmp_path / "leads" / "wrm-send-test.json").read_text()
        )
        assert stored["outreach_status"] == "sent"
        assert stored["outreach_draft_body"] == "Saved body"

    def test_self_test_send_does_not_mark_lead_sent(self, monkeypatch):
        from pipeline.constants import GENERIC_MENU_PDF

        monkeypatch.setenv("RESEND_FROM_EMAIL", "chris@webrefurb.com")
        self._create_lead(
            outreach_classification="menu_only",
            outreach_assets_selected=[str(GENERIC_MENU_PDF)],
            outreach_draft_subject="Saved subject",
            outreach_draft_body="Saved body",
        )
        with patch("dashboard.app._send_email_resend", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"id": "mock-send"}
            response = self.client.post(
                "/api/send/wrm-send-test",
                json={"email": "chris@webrefurb.com"},
            )
        assert response.status_code == 200
        assert response.json()["status"] == "test_sent"

        stored = json.loads(
            (self.tmp_path / "leads" / "wrm-send-test.json").read_text()
        )
        assert stored["outreach_status"] == "draft"
        assert stored["outreach_sent_at"] is None

    def test_non_business_recipient_does_not_mark_lead_sent(self):
        from pipeline.constants import GENERIC_MENU_PDF

        self._create_lead(
            email="owner@restaurant.test",
            outreach_classification="menu_only",
            outreach_assets_selected=[str(GENERIC_MENU_PDF)],
            outreach_draft_subject="Saved subject",
            outreach_draft_body="Saved body",
        )
        with patch("dashboard.app._send_email_resend", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"id": "mock-send"}
            response = self.client.post(
                "/api/send/wrm-send-test",
                json={"email": "someone-else@test.com"},
            )
        assert response.status_code == 200
        assert response.json()["status"] == "test_sent"

        stored = json.loads(
            (self.tmp_path / "leads" / "wrm-send-test.json").read_text()
        )
        assert stored["outreach_status"] == "draft"
        assert stored["outreach_sent_at"] is None

    def test_test_sends_do_not_count_against_daily_limit(self, monkeypatch):
        import dashboard.app as dash_app
        from pipeline.utils import write_json

        monkeypatch.setenv("RESEND_FROM_EMAIL", "chris@webrefurb.com")
        write_json(
            self.tmp_path / "sent" / "test.json",
            {
                "lead_id": "wrm-send-test",
                "to": "owner@restaurant.test",
                "sent_at": "2026-01-01T00:00:00+00:00",
                "test_send": True,
            },
        )
        write_json(
            self.tmp_path / "sent" / "old-test.json",
            {
                "lead_id": "wrm-send-old-test",
                "to": "chris@webrefurb.com",
                "sent_at": "2026-01-01T00:00:00+00:00",
            },
        )
        assert dash_app._count_today_sends() == 0

    def test_attachment_names_are_professional(self):
        import dashboard.app as dash_app
        from pipeline.constants import GENERIC_MENU_PDF, GENERIC_MACHINE_PDF

        assert dash_app._professional_attachment_name(GENERIC_MENU_PDF) == "WebRefurb-English-Menu-Sample.pdf"
        assert dash_app._professional_attachment_name(GENERIC_MACHINE_PDF) == "WebRefurb-Ticket-Machine-Guide-Sample.pdf"

    def test_outreach_blocked_for_sent_lead(self):
        """Sent leads should not be able to regenerate outreach."""
        self._create_lead(outreach_status="sent")
        response = self.client.post("/api/outreach/wrm-send-test")
        assert response.status_code == 409

    def test_outreach_blocked_for_replied_lead(self):
        self._create_lead(outreach_status="replied")
        response = self.client.post("/api/outreach/wrm-send-test")
        assert response.status_code == 409

    def test_outreach_blocked_for_converted_lead(self):
        self._create_lead(outreach_status="converted")
        response = self.client.post("/api/outreach/wrm-send-test")
        assert response.status_code == 409


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestClassificationSpecificBehavior:
    """Test classification-specific preview and send behavior."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        self.client = TestClient(app)
        import dashboard.app as dash_app
        monkeypatch.setattr(dash_app, "STATE_ROOT", tmp_path)
        (tmp_path / "leads").mkdir()
        (tmp_path / "jobs").mkdir()
        (tmp_path / "sent").mkdir()
        (tmp_path / "uploads").mkdir()
        self.tmp_path = tmp_path

    def _create_lead(self, lead_id="wrm-class-test", **overrides):
        lead = {
            "lead_id": lead_id,
            "business_name": "Class Test Ramen",
            "lead": True,
            "lead_score_v1": 80,
            "outreach_status": "new",
            "outreach_classification": None,
            "outreach_assets_selected": [],
            "outreach_sent_at": None,
            "outreach_draft_body": None,
            "outreach_include_inperson": True,
            "status_history": [],
            "menu_evidence_found": True,
            "machine_evidence_found": False,
            "primary_category_v1": "ramen",
            "establishment_profile": "ramen_only",
            "establishment_profile_confidence": "medium",
            "establishment_profile_evidence": ["primary_category:ramen"],
            "establishment_profile_source_urls": ["https://example.test/menu"],
            "rejection_reason": None,
        }
        lead.update(overrides)
        (self.tmp_path / "leads" / f"{lead_id}.json").write_text(
            json.dumps(lead), encoding="utf-8"
        )
        return lead

    def test_menu_only_classification(self):
        """menu_only leads get one PDF asset and no machine content."""
        self._create_lead(
            menu_evidence_found=True,
            machine_evidence_found=False,
        )
        response = self.client.post("/api/outreach/wrm-class-test")
        assert response.status_code == 200
        data = response.json()
        assert data["classification"] == "menu_machine_unconfirmed"
        assert data["include_machine_image"] is False
        # Should have exactly one asset (menu PDF)
        assert len(data["assets"]) == 1
        assert "machine" not in data["assets"][0].lower()

    def test_menu_and_machine_classification(self):
        """menu_and_machine leads get two PDFs and machine content."""
        self._create_lead(
            menu_evidence_found=True,
            machine_evidence_found=True,
        )
        response = self.client.post("/api/outreach/wrm-class-test")
        assert response.status_code == 200
        data = response.json()
        assert data["classification"] == "menu_and_machine"
        assert data["include_machine_image"] is True
        assert len(data["assets"]) == 2
        # Body should contain machine line
        assert "券売機用の英語ガイド" in data["body"]

    def test_machine_only_blocked(self):
        """machine_only leads should get a clear error, not a server crash."""
        self._create_lead(
            menu_evidence_found=False,
            machine_evidence_found=True,
        )
        response = self.client.post("/api/outreach/wrm-class-test")
        assert response.status_code == 422
        assert "machine" in response.json()["detail"].lower()
        assert "not supported" in response.json()["detail"].lower()

    def test_default_no_evidence_classifies_as_menu_only(self):
        """No evidence at all defaults to menu_only."""
        self._create_lead(
            menu_evidence_found=False,
            machine_evidence_found=False,
        )
        response = self.client.post("/api/outreach/wrm-class-test")
        assert response.status_code == 200
        data = response.json()
        assert data["classification"] == "menu_only"
        assert data["include_machine_image"] is False


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestStatusPersistence:
    """Test that status changes persist after refresh."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        self.client = TestClient(app)
        import dashboard.app as dash_app
        monkeypatch.setattr(dash_app, "STATE_ROOT", tmp_path)
        (tmp_path / "leads").mkdir()
        (tmp_path / "jobs").mkdir()
        (tmp_path / "sent").mkdir()
        (tmp_path / "uploads").mkdir()
        self.tmp_path = tmp_path

    def _create_lead(self, lead_id="wrm-status-test", **overrides):
        lead = {
            "lead_id": lead_id,
            "business_name": "Status Test Ramen",
            "lead": True,
            "email": "owner@status-test-ramen.test",
            "lead_score_v1": 80,
            "outreach_status": "new",
            "outreach_classification": None,
            "outreach_assets_selected": [],
            "outreach_sent_at": None,
            "outreach_draft_body": None,
            "outreach_include_inperson": True,
            "status_history": [],
            "menu_evidence_found": True,
            "machine_evidence_found": False,
            "primary_category_v1": "ramen",
            "establishment_profile": "ramen_only",
            "establishment_profile_confidence": "medium",
            "establishment_profile_evidence": ["primary_category:ramen"],
            "establishment_profile_source_urls": ["https://example.test/menu"],
            "rejection_reason": None,
        }
        lead.update(overrides)
        (self.tmp_path / "leads" / f"{lead_id}.json").write_text(
            json.dumps(lead), encoding="utf-8"
        )
        return lead

    def test_flag_dnc_persists_after_reload(self):
        self._create_lead()
        # Flag DNC
        self.client.post("/api/flag-dnc/wrm-status-test", json={"flag": True})
        # Reload leads via API (simulates page refresh)
        response = self.client.get("/api/leads")
        leads = response.json()
        lead = next(l for l in leads if l["lead_id"] == "wrm-status-test")
        assert lead["outreach_status"] == "do_not_contact"

    def test_unflag_dnc_persists_after_reload(self):
        self._create_lead(outreach_status="do_not_contact")
        # Unflag DNC
        self.client.post("/api/flag-dnc/wrm-status-test", json={"flag": False})
        # Reload
        response = self.client.get("/api/leads")
        leads = response.json()
        lead = next(l for l in leads if l["lead_id"] == "wrm-status-test")
        assert lead["outreach_status"] == "new"

    def test_draft_status_set_by_outreach(self):
        """Calling outreach on a 'new' lead should set status to 'draft'."""
        self._create_lead(outreach_status="new")
        self.client.post("/api/outreach/wrm-status-test")
        stored = json.loads(
            (self.tmp_path / "leads" / "wrm-status-test.json").read_text()
        )
        assert stored["outreach_status"] == "draft"

    def test_status_history_records_dnc_flag(self):
        self._create_lead()
        self.client.post("/api/flag-dnc/wrm-status-test", json={"flag": True})
        stored = json.loads(
            (self.tmp_path / "leads" / "wrm-status-test.json").read_text()
        )
        assert len(stored["status_history"]) == 1
        assert stored["status_history"][0]["status"] == "do_not_contact"
        assert "Manually flagged" in stored["status_history"][0].get("note", "")

    def test_main_page_shows_edited_draft_badge(self):
        """Leads with manually edited drafts should show in rendered page."""
        self._create_lead(outreach_draft_manually_edited=True)
        response = self.client.get("/")
        assert response.status_code == 200
        assert "Edited draft" in response.text

    def test_main_page_shows_menu_and_vending_tags(self):
        self._create_lead(menu_evidence_found=True, machine_evidence_found=True)
        response = self.client.get("/")
        assert response.status_code == 200
        assert '<span class="evidence-pill evidence-pill-menu">Menu</span>' in response.text
        assert '<span class="evidence-pill evidence-pill-vending">Vending</span>' in response.text

    def test_main_page_shows_single_evidence_tag(self):
        self._create_lead(menu_evidence_found=True, machine_evidence_found=False)
        response = self.client.get("/")
        assert response.status_code == 200
        assert '<span class="evidence-pill evidence-pill-menu">Menu</span>' in response.text
        assert '<span class="evidence-pill evidence-pill-vending">Vending</span>' not in response.text

    def test_project_root_is_not_exposed_as_assets(self):
        response = self.client.get("/assets/.env")
        assert response.status_code == 404

    def test_build_preview_survives_memory_reset(self):
        output_dir = self.tmp_path / "builds" / "job123"
        output_dir.mkdir(parents=True)
        (output_dir / "restaurant_menu_print_master.html").write_text("<html>preview</html>", encoding="utf-8")
        (self.tmp_path / "jobs" / "job123.json").write_text(
            json.dumps({"job_id": "job123", "status": "completed", "output_dir": str(output_dir)}),
            encoding="utf-8",
        )

        response = self.client.get("/api/build/job123/preview")
        assert response.status_code == 200
        assert "preview" in response.text

    def test_build_preview_allows_ready_for_review(self):
        output_dir = self.tmp_path / "builds" / "job123"
        output_dir.mkdir(parents=True)
        (output_dir / "restaurant_menu_print_master.html").write_text("<html>preview</html>", encoding="utf-8")
        (self.tmp_path / "jobs" / "job123.json").write_text(
            json.dumps({"job_id": "job123", "status": "ready_for_review", "output_dir": str(output_dir)}),
            encoding="utf-8",
        )

        response = self.client.get("/api/build/job123/preview")
        assert response.status_code == 200
        assert "preview" in response.text

    def test_build_review_reports_validation_errors(self):
        output_dir = self.tmp_path / "builds" / "job123"
        output_dir.mkdir(parents=True)
        (output_dir / "restaurant_menu_print_master.html").write_text("<html>preview</html>", encoding="utf-8")
        (self.tmp_path / "jobs" / "job123.json").write_text(
            json.dumps({"job_id": "job123", "status": "ready_for_review", "output_dir": str(output_dir)}),
            encoding="utf-8",
        )

        response = self.client.get("/api/build/job123/review")

        assert response.status_code == 200
        data = response.json()
        assert data["package_key"] == "package_1_remote_30k"
        assert data["validation"]["ok"] is False
        assert "restaurant_menu_print_ready_combined.pdf_missing" in data["validation"]["errors"]

    def test_build_review_derives_current_price_checklist_from_menu_data(self):
        output_dir = self.tmp_path / "builds" / "job123"
        output_dir.mkdir(parents=True)
        for name in (
            "restaurant_menu_print_ready_combined.pdf",
            "food_menu_print_ready.pdf",
            "drinks_menu_print_ready.pdf",
        ):
            (output_dir / name).write_bytes(b"%PDF-1.4\n% test\n")
        (output_dir / "restaurant_menu_print_master.html").write_text(
            '<html><body><img src="food_menu_editable_vector.svg"><img src="drinks_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "food_menu_browser_preview.html").write_text(
            '<html><body><img src="food_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "drinks_menu_browser_preview.html").write_text(
            '<html><body><img src="drinks_menu_editable_vector.svg"></body></html>',
            encoding="utf-8",
        )
        (output_dir / "food_menu_editable_vector.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text class="title">RAMEN MENU</text>'
            '<text class="item-en">Shoyu Ramen  ¥900</text>'
            '<text class="item-jp">醤油ラーメン</text>'
            '</svg>',
            encoding="utf-8",
        )
        (output_dir / "drinks_menu_editable_vector.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text class="title">DRINKS MENU</text>'
            '<text class="item-en">Draft Beer  ¥600</text>'
            '<text class="item-jp">生ビール</text>'
            '</svg>',
            encoding="utf-8",
        )
        (output_dir / "menu_data.json").write_text(
            json.dumps({
                "food": {
                    "title": "FOOD MENU",
                    "sections": [{
                        "title": "RAMEN",
                        "items": [{
                            "name": "Shoyu Ramen",
                            "english_name": "Shoyu Ramen",
                            "japanese_name": "醤油ラーメン",
                            "source_text": "醤油ラーメン",
                            "section": "RAMEN",
                            "price": "¥900",
                            "price_status": "confirmed_by_business",
                            "price_visibility": "customer_visible",
                            "source_provenance": "owner_text",
                            "approval_status": "pending_review",
                        }],
                    }],
                },
                "drinks": {
                    "title": "DRINKS MENU",
                    "sections": [{
                        "title": "DRINKS",
                        "items": [{
                            "name": "Draft Beer",
                            "english_name": "Draft Beer",
                            "japanese_name": "生ビール",
                            "source_text": "生ビール",
                            "section": "DRINKS",
                            "price": "¥600",
                            "price_status": "confirmed_by_business",
                            "price_visibility": "customer_visible",
                            "source_provenance": "owner_text",
                            "approval_status": "pending_review",
                        }],
                    }],
                },
                "show_prices": True,
                "review_checklist": {"price_count": 0, "source_price_count": 2},
                "sections": [{
                    "title": "RAMEN",
                    "items": [{"name": "Shoyu Ramen", "japanese_name": "醤油ラーメン"}],
                }, {
                    "title": "DRINKS",
                    "items": [{"name": "Draft Beer", "japanese_name": "生ビール"}],
                }],
            }),
            encoding="utf-8",
        )
        (self.tmp_path / "jobs" / "job123.json").write_text(
            json.dumps({
                "job_id": "job123",
                "status": "ready_for_review",
                "output_dir": str(output_dir),
            }),
            encoding="utf-8",
        )

        response = self.client.get("/api/build/job123/review")

        assert response.status_code == 200
        data = response.json()
        assert data["validation"]["ok"] is True
        assert data["review_checklist"]["price_count"] == 2
        assert data["review_checklist"]["source_price_count"] == 2

    def test_build_preview_serves_relative_assets(self):
        output_dir = self.tmp_path / "builds" / "job123"
        output_dir.mkdir(parents=True)
        (output_dir / "food_menu_editable_vector.svg").write_text("<svg></svg>", encoding="utf-8")
        (self.tmp_path / "jobs" / "job123.json").write_text(
            json.dumps({"job_id": "job123", "status": "ready_for_review", "output_dir": str(output_dir)}),
            encoding="utf-8",
        )

        response = self.client.get("/api/build/job123/food_menu_editable_vector.svg")

        assert response.status_code == 200
        assert response.text == "<svg></svg>"

    def test_build_asset_blocks_path_traversal(self):
        output_dir = self.tmp_path / "builds" / "job123"
        output_dir.mkdir(parents=True)
        (self.tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
        (self.tmp_path / "jobs" / "job123.json").write_text(
            json.dumps({"job_id": "job123", "status": "ready_for_review", "output_dir": str(output_dir)}),
            encoding="utf-8",
        )

        response = self.client.get("/api/build/job123/../../secret.txt")

        assert response.status_code == 404

    def test_build_approve_blocks_until_review_passes(self):
        output_dir = self.tmp_path / "builds" / "job123"
        output_dir.mkdir(parents=True)
        (output_dir / "restaurant_menu_print_master.html").write_text("<html>preview</html>", encoding="utf-8")
        (self.tmp_path / "jobs" / "job123.json").write_text(
            json.dumps({"job_id": "job123", "status": "ready_for_review", "output_dir": str(output_dir)}),
            encoding="utf-8",
        )

        response = self.client.post("/api/build/job123/approve")

        assert response.status_code == 422
        assert "review blocked" in response.json()["detail"].lower()

    def test_build_approve_and_download_final_export(self):
        output_dir = self.tmp_path / "builds" / "job123"
        output_dir.mkdir(parents=True)
        for name in (
            "restaurant_menu_print_ready_combined.pdf",
            "food_menu_print_ready.pdf",
            "drinks_menu_print_ready.pdf",
        ):
            (output_dir / name).write_bytes(b"%PDF-1.4\n% test\n")
        (output_dir / "food_menu_editable_vector.svg").write_text("<svg></svg>", encoding="utf-8")
        (output_dir / "drinks_menu_editable_vector.svg").write_text("<svg></svg>", encoding="utf-8")
        (output_dir / "restaurant_menu_print_master.html").write_text("<html>preview</html>", encoding="utf-8")
        (output_dir / "menu_data.json").write_text(
            json.dumps({"sections": [{"title": "RAMEN", "items": [{"name": "Shoyu"}]}]}),
            encoding="utf-8",
        )
        (self.tmp_path / "jobs" / "job123.json").write_text(
            json.dumps({"job_id": "job123", "status": "ready_for_review", "output_dir": str(output_dir)}),
            encoding="utf-8",
        )

        approved = self.client.post("/api/build/job123/approve")
        assert approved.status_code == 200
        assert approved.json()["final_export_status"] == "ready"

        download = self.client.get("/api/build/job123/download")
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/zip"

    def test_packages_and_build_history_endpoints(self):
        (self.tmp_path / "jobs" / "job123.json").write_text(
            json.dumps({
                "job_id": "job123",
                "restaurant_name": "Hinode Ramen",
                "status": "ready_for_review",
                "package_key": "package_2_printed_delivered_45k",
                "package_validation": {"ok": False, "errors": ["delivery_address_missing"], "warnings": []},
            }),
            encoding="utf-8",
        )

        packages = self.client.get("/api/packages")
        assert packages.status_code == 200
        assert [package["price_yen"] for package in packages.json()["packages"]] == [30000, 45000, 65000]

        builds = self.client.get("/api/builds")
        assert builds.status_code == 200
        assert builds.json()["builds"][0]["package_key"] == "package_2_printed_delivered_45k"
