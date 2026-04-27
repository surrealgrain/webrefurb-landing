"""Tests for API endpoints."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


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
        (tmp_path / "leads").mkdir()
        (tmp_path / "jobs").mkdir()
        (tmp_path / "sent").mkdir()
        (tmp_path / "uploads").mkdir()

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
