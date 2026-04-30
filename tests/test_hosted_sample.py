from __future__ import annotations

from pathlib import Path

from pipeline.hosted_sample import ensure_hosted_menu_sample
from pipeline.outreach import build_manual_outreach_message


def _lead(**overrides):
    lead = {
        "lead_id": "wrm-hosted-sample",
        "lead": True,
        "business_name": "青空ラーメン",
        "primary_category_v1": "ramen",
        "establishment_profile": "ramen_only",
        "menu_evidence_found": True,
        "machine_evidence_found": False,
        "english_menu_issue": True,
        "address": "東京都渋谷区1-1-1",
        "phone": "03-0000-0000",
        "evidence_snippets": ["醤油ラーメン 味玉 トッピング メニュー"],
        "proof_items": [
            {
                "snippet": "醤油ラーメン 味玉 トッピング メニュー",
                "customer_preview_eligible": True,
            }
        ],
    }
    lead.update(overrides)
    return lead


def test_ensure_hosted_menu_sample_publishes_stable_noindex_page(tmp_path):
    updated, result = ensure_hosted_menu_sample(_lead(), docs_root=tmp_path / "docs")

    assert result["ok"] is True
    assert result["published"] is True
    assert result["sample_menu_url"].startswith("https://webrefurb.com/s/")
    assert updated["sample_menu_url"] == result["sample_menu_url"]
    assert updated["hosted_menu_sample_url"] == result["sample_menu_url"]
    assert updated["hosted_menu_sample_status"] == "published"

    page = Path(result["path"])
    assert page.exists()
    html = page.read_text(encoding="utf-8")
    assert '<meta name="robots" content="noindex, nofollow">' in html
    assert "WebRefurb" in html
    assert "青空ラーメン" in html
    assert "ご興味があれば、このお問い合わせフォームへの返信でご連絡ください。" in html
    assert "03-0000-0000" not in html
    assert "東京都渋谷区1-1-1" not in html

    again, again_result = ensure_hosted_menu_sample(updated, docs_root=tmp_path / "docs")
    assert again["hosted_menu_sample_token"] == updated["hosted_menu_sample_token"]
    assert again_result["sample_menu_url"] == result["sample_menu_url"]


def test_hosted_menu_sample_dry_run_does_not_write_page(tmp_path):
    updated, result = ensure_hosted_menu_sample(_lead(), docs_root=tmp_path / "docs", dry_run=True)

    assert result["dry_run"] is True
    assert result["published"] is False
    assert "html" in result
    assert updated["hosted_menu_sample_status"] == "dry_run"
    assert not Path(result["path"]).exists()


def test_contact_form_message_references_hosted_sample_url():
    draft = build_manual_outreach_message(
        business_name="青空ラーメン",
        classification="menu_only",
        channel="contact_form",
        establishment_profile="ramen_only",
        sample_menu_url="https://webrefurb.com/s/testtoken1234567890abcd",
    )

    assert "https://webrefurb.com/s/testtoken1234567890abcd" in draft["body"]
    assert "添付ではなく、こちらのページからご確認いただけます" in draft["body"]
    assert draft["include_menu_image"] is False
    assert draft["include_machine_image"] is False
