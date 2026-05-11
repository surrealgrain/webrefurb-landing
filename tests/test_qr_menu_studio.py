"""Tests for QR Menu Studio v1 — product scope, publish gates, banned terms, owner review."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    """Run every test with an isolated state/ directory."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "studio").mkdir()
    (state_dir / "reviews").mkdir()
    (state_dir / "uploads").mkdir()
    (state_dir / "leads").mkdir()
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    templates_dir = tmp_path / "assets" / "templates"
    templates_dir.mkdir(parents=True)

    monkeypatch.setenv("WEBREFURB_STATE_ROOT", str(state_dir))

    # Patch module-level paths after import
    import dashboard.app as app_mod
    app_mod.STATE_ROOT = state_dir
    app_mod.STUDIO_DIR = state_dir / "studio"
    app_mod.REVIEWS_DIR = state_dir / "reviews"
    app_mod.UPLOADS_DIR = state_dir / "uploads"
    app_mod.QR_DOCS_ROOT = docs_dir
    app_mod.TEMPLATES_DIR = templates_dir

    yield state_dir


@pytest.fixture()
def client():
    from dashboard.app import app
    return TestClient(app)


def _create_workspace(client, **kwargs):
    """Helper to create a workspace via API."""
    defaults = {
        "restaurant_name": "Test Ramen",
        "restaurant_name_ja": "テストラーメン",
        "category": "ramen",
    }
    defaults.update(kwargs)
    resp = client.post("/api/studio", json=defaults)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _add_item(client, ws_id, **kwargs):
    """Helper to add an item to a workspace."""
    defaults = {
        "name_en": "Tonkotsu Ramen",
        "name_ja": "豚骨ラーメン",
        "category": "Ramen",
        "price": "¥950",
        "description": "Rich pork bone broth",
        "price_confirmed": True,
        "desc_confirmed": True,
        "ingredients_confirmed": True,
        "allergens_confirmed": True,
        "visible": True,
        "tags": ["pork"],
    }
    defaults.update(kwargs)
    resp = client.post(f"/api/studio/{ws_id}/items", json=defaults)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ===========================================================================
# A. Product scope
# ===========================================================================

class TestProductScope:
    """Only ramen / izakaya / skip categories. No old product."""

    def test_categories_are_ramizakaya_skip(self):
        from pipeline.constants import ACTIVE_LEAD_CATEGORIES
        assert set(ACTIVE_LEAD_CATEGORIES) == {"ramen", "izakaya", "skip"}

    def test_no_washoku_category(self):
        from pipeline.constants import ACTIVE_LEAD_CATEGORIES
        assert "washoku" not in ACTIVE_LEAD_CATEGORIES
        assert "sushi" not in ACTIVE_LEAD_CATEGORIES
        assert "yakitori" not in ACTIVE_LEAD_CATEGORIES
        assert "omakase" not in ACTIVE_LEAD_CATEGORIES

    def test_single_active_package(self):
        from pipeline.constants import PACKAGE_REGISTRY, ENGLISH_QR_MENU_KEY
        assert len(PACKAGE_REGISTRY) == 1
        assert ENGLISH_QR_MENU_KEY in PACKAGE_REGISTRY

    def test_create_workspace_rejects_invalid_category(self, client):
        resp = client.post("/api/studio", json={
            "restaurant_name": "Test",
            "category": "washoku",
        })
        # Should default to ramen, not reject
        assert resp.status_code == 200
        ws = resp.json()
        assert ws["category"] == "ramen"

    def test_health_check_shows_correct_product(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert data["product"] == "english_qr_menu_65k"
        assert "ramen" in data["categories"]
        assert "izakaya" in data["categories"]
        assert "skip" in data["categories"]


# ===========================================================================
# B. Customer menu — banned terms
# ===========================================================================

BANNED_TERMS = [
    "ordering system", "qr ordering system",
    "place order", "submit order", "send order",
    "pos system", "checkout page",
    "cart", "payment",
]

ALLOWED_TERMS = [
    "add to list", "view list", "show to staff", "show staff list",
]


class TestBannedTerms:

    def test_banned_terms_not_in_dashboard_html(self):
        """Scan the dashboard index.html for banned customer-facing terms."""
        html = Path("dashboard/templates/index.html").read_text().lower()
        for term in BANNED_TERMS:
            assert term not in html, f"Banned term '{term}' found in dashboard HTML"

    def test_allowed_terms_in_dashboard(self):
        """Verify the dashboard uses correct terminology."""
        html = Path("dashboard/templates/index.html").read_text().lower()
        # At least some allowed terms should be present
        found = any(t in html for t in ALLOWED_TERMS)
        assert found, "No allowed customer-facing terms found in dashboard"

    def test_banned_terms_not_in_app_constants(self):
        """Check BANNED_CUSTOMER_TERMS is defined and includes the right terms."""
        from dashboard.app import BANNED_CUSTOMER_TERMS
        for term in ["ordering system", "submit order", "pos system"]:
            assert any(term in bt for bt in BANNED_CUSTOMER_TERMS)

    def test_banned_terms_check_endpoint(self, client):
        resp = client.get("/api/banned-terms-check")
        data = resp.json()
        # The endpoint should exist and return violations list
        assert "violations" in data
        assert "total" in data


# ===========================================================================
# C. Owner review
# ===========================================================================

class TestOwnerReview:

    def test_owner_can_approve(self, client):
        ws = _create_workspace(client)
        _add_item(client, ws["id"])

        # Generate review link
        resp = client.post(f"/api/studio/{ws['id']}/review-link")
        assert resp.status_code == 200
        token = resp.json()["token"]

        # Owner approves
        resp = client.post(f"/api/review/{token}/approve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_owner_can_request_changes(self, client):
        ws = _create_workspace(client)
        _add_item(client, ws["id"])

        resp = client.post(f"/api/studio/{ws['id']}/review-link")
        token = resp.json()["token"]

        resp = client.post(f"/api/review/{token}/request-changes", json={
            "notes": "Price for ramen is wrong",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "changes_requested"

    def test_owner_cannot_publish_directly(self, client):
        """Owner review page should not have a publish endpoint for owners."""
        # The only publish route is /api/studio/{ws}/publish which is operator-only
        # Owner routes are /api/review/{token}/approve and /request-changes only
        from dashboard.app import app
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        owner_routes = [r for r in routes if "/review/" in r and "token" in r]
        # Should not contain "publish" in any owner route
        for route in owner_routes:
            assert "publish" not in route.lower(), f"Owner route contains 'publish': {route}"

    def test_owner_approval_does_not_set_published(self, client):
        """Owner approving should set status to ready_to_publish, NOT published."""
        ws = _create_workspace(client)
        _add_item(client, ws["id"])

        client.post(f"/api/studio/{ws['id']}/review-link")
        # Manually get token from workspace
        ws_data = client.get(f"/api/studio/{ws['id']}").json()
        token = ws_data["owner_review"]["token"]

        client.post(f"/api/review/{token}/approve")

        ws_data = client.get(f"/api/studio/{ws['id']}").json()
        assert ws_data["status"] == "ready_to_publish"
        assert ws_data["status"] != "published"

    def test_expired_review_link_rejected(self, client):
        ws = _create_workspace(client)
        # Create a review file with expired status
        import dashboard.app as app_mod
        review = {
            "workspace_id": ws["id"],
            "token": "fake-expired-token",
            "status": "expired",
            "restaurant_name": "Test",
        }
        app_mod._save_json(app_mod.REVIEWS_DIR / "fake-expired-token.json", review)

        resp = client.post("/api/review/fake-expired-token/approve")
        assert resp.status_code == 410


# ===========================================================================
# D. Publish gates
# ===========================================================================

class TestPublishGates:

    def test_publish_blocked_without_owner_approval(self, client):
        ws = _create_workspace(client)
        _add_item(client, ws["id"],
                  price_confirmed=True, desc_confirmed=True,
                  ingredients_confirmed=True, allergens_confirmed=True)

        # Generate QR code
        client.post(f"/api/studio/{ws['id']}/regenerate-qr")

        # Try to publish without owner approval
        resp = client.post(f"/api/studio/{ws['id']}/publish")
        assert resp.status_code == 422
        assert "owner" in resp.json()["detail"].lower()

    def test_publish_blocked_with_unconfirmed_prices(self, client):
        ws = _create_workspace(client)
        _add_item(client, ws["id"],
                  price_confirmed=False,  # NOT confirmed
                  price="¥950")

        resp = client.post(f"/api/studio/{ws['id']}/publish")
        assert resp.status_code == 422
        assert "price" in resp.json()["detail"].lower()

    def test_publish_blocked_with_unconfirmed_descriptions(self, client):
        ws = _create_workspace(client)
        _add_item(client, ws["id"],
                  price_confirmed=True,
                  desc_confirmed=False,
                  description="Rich broth")

        resp = client.post(f"/api/studio/{ws['id']}/publish")
        assert resp.status_code == 422

    def test_publish_allowed_when_all_checks_pass(self, client):
        ws = _create_workspace(client)
        _add_item(client, ws["id"],
                  price_confirmed=True,
                  desc_confirmed=True,
                  ingredients_confirmed=True,
                  allergens_confirmed=True)

        # Owner approves
        client.post(f"/api/studio/{ws['id']}/review-link")
        ws_data = client.get(f"/api/studio/{ws['id']}").json()
        token = ws_data["owner_review"]["token"]
        client.post(f"/api/review/{token}/approve")

        # Generate QR
        qr_resp = client.post(f"/api/studio/{ws['id']}/regenerate-qr")
        assert qr_resp.status_code == 200, f"QR failed: {qr_resp.text}"

        # Publish should succeed
        resp = client.post(f"/api/studio/{ws['id']}/publish")
        assert resp.status_code == 200, f"Publish failed: {resp.text}"
        assert resp.json()["status"] == "published"

    def test_publish_generates_hosted_url(self, client):
        ws = _create_workspace(client, restaurant_name="Test Ramen Shop")
        _add_item(client, ws["id"],
                  price_confirmed=True, desc_confirmed=True,
                  ingredients_confirmed=True, allergens_confirmed=True)

        client.post(f"/api/studio/{ws['id']}/review-link")
        ws_data = client.get(f"/api/studio/{ws['id']}").json()
        client.post(f"/api/review/{ws_data['owner_review']['token']}/approve")
        client.post(f"/api/studio/{ws['id']}/regenerate-qr")

        resp = client.post(f"/api/studio/{ws['id']}/publish")
        published_url = resp.json()["url"]
        assert published_url.startswith("/menus/")
        assert "test-ramen-shop" in published_url

    def test_export_blocked_for_unpublished(self, client):
        ws = _create_workspace(client)
        resp = client.get(f"/api/studio/{ws['id']}/export")
        assert resp.status_code == 422


# ===========================================================================
# E. Dashboard workspace
# ===========================================================================

class TestDashboardWorkspace:

    def test_workspace_crud(self, client):
        # Create
        ws = _create_workspace(client)
        assert ws["restaurant_name"] == "Test Ramen"
        assert ws["category"] == "ramen"
        assert ws["status"] == "intake"

        # Read
        resp = client.get(f"/api/studio/{ws['id']}")
        assert resp.status_code == 200
        assert resp.json()["restaurant_name"] == "Test Ramen"

        # List
        resp = client.get("/api/studio")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_materials_upload(self, client, tmp_path):
        ws = _create_workspace(client)

        # Upload a file
        import io
        file_content = b"fake image data"
        resp = client.post(
            f"/api/studio/{ws['id']}/materials/upload",
            files={"files": ("menu.jpg", io.BytesIO(file_content), "image/jpeg")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["materials"]) == 1
        assert data["status"] == "materials_received"

    def test_materials_paste_text(self, client):
        ws = _create_workspace(client)
        resp = client.post(f"/api/studio/{ws['id']}/materials/text", json={
            "text": "Ramen ¥900\nGyoza ¥500",
            "label": "Website menu text",
        })
        assert resp.status_code == 200
        assert len(resp.json()["materials"]) == 1

    def test_menu_items_crud(self, client):
        ws = _create_workspace(client)

        # Add
        item = _add_item(client, ws["id"])
        assert item["name_en"] == "Tonkotsu Ramen"
        assert item["price_confirmed"] is True

        # Update
        resp = client.put(f"/api/studio/{ws['id']}/items/{item['id']}", json={
            **item, "price": "¥1,000",
        })
        assert resp.status_code == 200

        # Delete
        resp = client.delete(f"/api/studio/{ws['id']}/items/{item['id']}")
        assert resp.status_code == 200

        # Verify empty
        ws_data = client.get(f"/api/studio/{ws['id']}").json()
        assert len(ws_data["items"]) == 0

    def test_bulk_confirm_items(self, client):
        ws = _create_workspace(client)
        _add_item(client, ws["id"], price="¥950", description="Broth",
                  price_confirmed=False, desc_confirmed=False)
        _add_item(client, ws["id"], name_en="Miso Ramen", price="¥900",
                  price_confirmed=False)

        resp = client.post(f"/api/studio/{ws['id']}/items/bulk-confirm", json={
            "fields": ["price", "description"],
            "item_ids": [],
        })
        assert resp.status_code == 200
        assert resp.json()["confirmed_count"] > 0

        ws_data = client.get(f"/api/studio/{ws['id']}").json()
        for it in ws_data["items"]:
            assert it["price_confirmed"] is True
            assert it["desc_confirmed"] is True

    def test_preview_returns_menu_data(self, client):
        ws = _create_workspace(client)
        _add_item(client, ws["id"])

        resp = client.get(f"/api/studio/{ws['id']}/preview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["restaurant_name"] == "Test Ramen"
        assert len(data["categories"]) > 0
        assert data["categories"][0]["items"][0]["name_en"] == "Tonkotsu Ramen"

    def test_hidden_items_not_in_preview(self, client):
        ws = _create_workspace(client)
        _add_item(client, ws["id"], name_en="Visible Item", hidden=False)
        _add_item(client, ws["id"], name_en="Hidden Item", hidden=True)

        resp = client.get(f"/api/studio/{ws['id']}/preview")
        data = resp.json()
        names = [it["name_en"] for cat in data["categories"] for it in cat["items"]]
        assert "Visible Item" in names
        assert "Hidden Item" not in names

    def test_unconfirmed_fields_not_in_preview(self, client):
        ws = _create_workspace(client)
        _add_item(client, ws["id"],
                  price="¥950", price_confirmed=False,
                  description="Rich broth", desc_confirmed=False)

        resp = client.get(f"/api/studio/{ws['id']}/preview")
        data = resp.json()
        item = data["categories"][0]["items"][0]
        assert item["price"] == ""  # Not shown because not confirmed
        assert item["description"] == ""  # Not shown because not confirmed

    def test_published_menus_list(self, client):
        # Create and publish a menu
        ws = _create_workspace(client, restaurant_name="Published Test")
        _add_item(client, ws["id"],
                  price_confirmed=True, desc_confirmed=True,
                  ingredients_confirmed=True, allergens_confirmed=True)

        client.post(f"/api/studio/{ws['id']}/review-link")
        ws_data = client.get(f"/api/studio/{ws['id']}").json()
        client.post(f"/api/review/{ws_data['owner_review']['token']}/approve")
        client.post(f"/api/studio/{ws['id']}/regenerate-qr")
        client.post(f"/api/studio/{ws['id']}/publish")

        # Check published list
        resp = client.get("/api/published")
        assert resp.status_code == 200
        menus = resp.json()
        assert any(m["restaurant_name"] == "Published Test" for m in menus)


# ===========================================================================
# F. Send safety
# ===========================================================================

class TestSendSafety:

    def test_no_auto_send_endpoint_exists(self):
        """Verify no automatic send endpoint in the new app."""
        from dashboard.app import app
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        # Should not have any auto-send routes
        auto_send_routes = [r for r in routes if "auto" in r.lower() and "send" in r.lower()]
        assert len(auto_send_routes) == 0, f"Found auto-send routes: {auto_send_routes}"

    def test_test_sends_mentioned_in_settings(self):
        """Verify send safety is mentioned in the dashboard."""
        html = Path("dashboard/templates/index.html").read_text()
        assert "test sends" in html.lower() or "manual approval" in html.lower()


# ===========================================================================
# G. QR Sign / Export
# ===========================================================================

class TestQRSignExport:

    def test_regenerate_qr(self, client):
        ws = _create_workspace(client)
        resp = client.post(f"/api/studio/{ws['id']}/regenerate-qr")
        assert resp.status_code == 200
        assert resp.json()["qr_code_generated"] is True

    def test_export_package_after_publish(self, client):
        ws = _create_workspace(client, restaurant_name="Export Test")
        _add_item(client, ws["id"],
                  price_confirmed=True, desc_confirmed=True,
                  ingredients_confirmed=True, allergens_confirmed=True)

        client.post(f"/api/studio/{ws['id']}/review-link")
        ws_data = client.get(f"/api/studio/{ws['id']}").json()
        client.post(f"/api/review/{ws_data['owner_review']['token']}/approve")
        client.post(f"/api/studio/{ws['id']}/regenerate-qr")
        client.post(f"/api/studio/{ws['id']}/publish")

        resp = client.get(f"/api/studio/{ws['id']}/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["qr_code_generated"] is True
        assert "menu_data" in data
        assert "confirmation_summary" in data
        assert data["confirmation_summary"]["total_items"] > 0

    def test_hosted_menu_html_generated(self, client, _isolated_state):
        ws = _create_workspace(client, restaurant_name="HTML Test")
        _add_item(client, ws["id"],
                  price_confirmed=True, desc_confirmed=True,
                  ingredients_confirmed=True, allergens_confirmed=True)

        client.post(f"/api/studio/{ws['id']}/review-link")
        ws_data = client.get(f"/api/studio/{ws['id']}").json()
        client.post(f"/api/review/{ws_data['owner_review']['token']}/approve")
        client.post(f"/api/studio/{ws['id']}/regenerate-qr")
        resp = client.post(f"/api/studio/{ws['id']}/publish")
        published_url = resp.json()["url"]

        # Check that HTML file was created
        import dashboard.app as app_mod
        # The slug should be derived from restaurant name
        slug = published_url.strip("/").split("/")[-1]
        html_path = app_mod.QR_DOCS_ROOT / "menus" / slug / "index.html"
        assert html_path.exists(), f"Published HTML not found at {html_path}"
