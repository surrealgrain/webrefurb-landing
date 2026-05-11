from __future__ import annotations

from pipeline.lead_quality import duplicate_key, lead_quality_summary, normalise_business_name_key
from pipeline.send_policy import apply_opt_out, batch_send_policy


def test_duplicate_key_prefers_email_then_domain_then_name():
    assert duplicate_key({"email": "INFO@EXAMPLE.JP"}) == "email:info@example.jp"
    assert duplicate_key({"website": "https://www.example.jp/menu"}) == "domain:example.jp"
    assert duplicate_key({"business_name": "日の出ラーメン 本店", "city": "Tokyo"}) == "name:tokyo:日の出ラーメン"


def test_lead_quality_explains_supported_and_stale_leads():
    record = {
        "lead_id": "wrm-1",
        "category": "ramen",
        "recommended_primary_package": "english_qr_menu_65k",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "contacts": [{"type": "email", "value": "info@example.jp", "actionable": True}],
    }

    summary = lead_quality_summary(record, now="2026-05-11T00:00:00+00:00")

    assert summary["supported"] is True
    assert summary["stale"] is True
    assert "active_category:ramen" in summary["positive_signals"]
    assert "stale_lead_requires_reverification" in summary["negative_signals"]


def test_normalise_business_name_key_removes_branch_noise():
    assert normalise_business_name_key("Hinode Ramen Main Store") == "hinode-ramen"
    assert normalise_business_name_key("日の出ラーメン 支店") == "日の出ラーメン"


def test_opt_out_blocks_future_send_and_clears_approval():
    record = apply_opt_out(
        {"lead_id": "wrm-1", "outreach_status": "needs_review", "manual_real_send_approved": True},
        now="2026-05-11T00:00:00+00:00",
    )

    assert record["outreach_status"] == "do_not_contact"
    assert record["manual_real_send_approved"] is False
    assert record["send_ready_checked"] is False


def test_batch_send_policy_requires_manual_approval_and_domain_cooldown():
    records = [{"lead_id": "a", "email": "info@example.jp"}]
    history = [{"to": "owner@example.jp", "sent_at": "2026-05-11T00:00:00+00:00"}]

    blocked = batch_send_policy(records, approved=False, sent_history=history, now="2026-05-11T01:00:00+00:00")
    approved = batch_send_policy(records, approved=True, sent_history=[], now="2026-05-11T01:00:00+00:00")

    assert blocked["ok"] is False
    assert "manual_batch_approval_missing" in blocked["reasons"]
    assert "domain_cooldown_active" in blocked["reasons"]
    assert approved["ok"] is True


def test_batch_send_policy_checks_contact_email_domain_cooldown():
    records = [{"lead_id": "a", "contacts": [{"type": "email", "value": "info@example.jp"}]}]
    history = [{"to": "owner@example.jp", "sent_at": "2026-05-11T00:00:00+00:00"}]

    result = batch_send_policy(records, approved=True, sent_history=history, now="2026-05-11T01:00:00+00:00")

    assert result["ok"] is False
    assert result["cooldown_hits"] == ["example.jp"]
