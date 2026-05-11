from __future__ import annotations

from dashboard.app import _is_test_recipient_email, _send_readiness_for_record
from pipeline.constants import ENGLISH_QR_MENU_KEY


def _record(**overrides):
    record = {
        "lead_id": "",
        "lead": True,
        "business_name": "Safety Ramen",
        "email": "owner@safety-ramen.jp",
        "contacts": [{"type": "email", "value": "owner@safety-ramen.jp", "actionable": True}],
        "category": "ramen",
        "primary_category_v1": "ramen",
        "recommended_primary_package": ENGLISH_QR_MENU_KEY,
        "launch_readiness_status": "ready_for_outreach",
        "lead_evidence_dossier": {"ready_to_contact": True},
        "operator_state": "ready",
        "outreach_status": "draft",
        "manual_real_send_approved": True,
        "outreach_draft_subject": "英語QRメニューのご案内",
        "outreach_draft_body": "英語QRメニューです。Show Staff Listでスタッフに見せるリストを確認できます。",
        "outreach_draft_english_body": "English QR Menu. Customers add items to a list and use Show Staff List.",
    }
    record.update(overrides)
    return record


def test_test_sends_only_allow_chris():
    assert _is_test_recipient_email("chris@webrefurb.com")
    assert not _is_test_recipient_email("owner@example.jp")


def test_send_readiness_requires_active_product_and_manual_approval(monkeypatch):
    ready = _send_readiness_for_record(_record(), final_check=True)
    assert ready["status"] == "ready_to_send"

    old_package = _send_readiness_for_record(_record(recommended_primary_package="package_1_remote_30k"), final_check=True)
    assert old_package["status"] == "not_ready"
    assert "active_product_missing" in old_package["reasons"]

    monkeypatch.setattr("dashboard.app._is_lead_business_recipient", lambda lead_id, email: True)
    unapproved = _send_readiness_for_record(_record(lead_id="wrm-safety", manual_real_send_approved=False), final_check=True)
    assert unapproved["status"] == "not_ready"
    assert "manual_real_send_approval_missing" in unapproved["reasons"]


def test_send_readiness_blocks_stale_or_banned_copy():
    stale = _send_readiness_for_record(_record(outreach_draft_body="昔のメニュー案内です。"), final_check=True)
    assert stale["status"] == "not_ready"
    assert "stale_or_non_qr_first_draft" in stale["reasons"]

    banned = _send_readiness_for_record(_record(outreach_draft_body="This is a QR ordering system with POS."), final_check=True)
    assert banned["status"] == "not_ready"
    assert "banned_customer_copy_term" in banned["reasons"]


def test_send_readiness_blocks_skip_and_unsafe_route():
    skipped = _send_readiness_for_record(_record(lead=False, category="skip"), final_check=True)
    assert skipped["status"] == "not_ready"
    assert "skipped_or_not_true_lead" in skipped["reasons"]

    no_route = _send_readiness_for_record(_record(email="", contacts=[]), final_check=True)
    assert no_route["status"] == "not_ready"
    assert "email_not_verified" in no_route["reasons"]
