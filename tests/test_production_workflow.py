from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.constants import PACKAGE_1_KEY, PACKAGE_2_KEY, PACKAGE_3_KEY
from pipeline.production_workflow import (
    build_correction_task,
    build_production_workspace,
    classify_reply_intent,
    evaluate_pre_owner_preview_qa,
    extract_structured_menu_content,
    ingest_owner_assets,
    next_action_for_reply,
    order_stage_status,
    recheck_package_fit,
    update_asset_operator_status,
)


def test_reply_intent_taxonomy_and_next_action_are_single_action():
    photo_reply = classify_reply_intent(
        "興味があります。券売機の写真を添付します。",
        [{"filename": "ticket-machine.jpg", "content_type": "image/jpeg"}],
    )

    assert photo_reply["intent"] == "ticket_machine_photos_sent"
    assert photo_reply["positive"] is True

    action = next_action_for_reply(
        {"reply_intent": photo_reply["intent"]},
        assets=[{"operator_status": "needs_better_photo"}],
    )
    assert action["key"] == "review_uploaded_photos"
    assert set(action) == {"key", "label", "detail"}

    opt_out = classify_reply_intent("配信停止してください。")
    assert opt_out["intent"] == "unsubscribe"
    assert next_action_for_reply({"reply_intent": "unsubscribe"})["key"] == "close"


def test_owner_asset_inbox_preserves_originals_detects_duplicates_and_review_status(tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    first = upload_dir / "drink-menu.jpg"
    second = upload_dir / "drink-menu-copy.jpg"
    first.write_bytes(b"same-image-bytes")
    second.write_bytes(b"same-image-bytes")

    reply = {
        "reply_id": "reply-test",
        "lead_id": "wrm-test",
        "channel": "email",
        "body": "ドリンクメニューの写真です。",
        "attachments": [
            {"filename": first.name, "content_type": "image/jpeg", "stored_path": str(first)},
            {"filename": second.name, "content_type": "image/jpeg", "stored_path": str(second)},
        ],
    }

    manifest = ingest_owner_assets(reply, state_root=tmp_path)
    assets = manifest["assets"]

    assert len(assets) == 2
    assert assets[0]["asset_type"] == "drink_menu_photo"
    assert Path(assets[0]["original_path"]).read_bytes() == b"same-image-bytes"
    assert Path(assets[0]["preview_path"]).exists()
    assert "duplicate" in assets[1]["quality_issues"]
    assert assets[1]["operator_status"] == "not_needed"

    updated = update_asset_operator_status(
        reply_id="reply-test",
        asset_id=assets[0]["asset_id"],
        status="usable",
        state_root=tmp_path,
    )
    assert updated["assets"][0]["operator_status"] == "usable"
    with pytest.raises(ValueError, match="invalid_operator_asset_status"):
        update_asset_operator_status(
            reply_id="reply-test",
            asset_id=assets[0]["asset_id"],
            status="raw_json_review",
            state_root=tmp_path,
        )


def test_extraction_workspace_package_recheck_and_qa_gate():
    extracted = extract_structured_menu_content(raw_text="【ラーメン】\n醤油ラーメン ¥900\n餃子 ¥450")
    assert extracted["sections"][0]["section"] == "ramen"
    assert extracted["sections"][0]["items"][0]["japanese_item_name"] == "醤油ラーメン"
    assert extracted["sections"][0]["items"][0]["price_status"] == "detected_in_source"

    package_fit = recheck_package_fit(
        assets=[{"asset_type": "ticket_machine_photo", "operator_status": "usable"}],
        current_package_key=PACKAGE_1_KEY,
    )
    assert package_fit["package_key"] == PACKAGE_1_KEY
    assert package_fit["reason"] == "ticket_machine_guide_fits_english_ordering_files"

    qr_fit = recheck_package_fit(
        assets=[
            {"asset_type": "drink_menu_photo", "operator_status": "usable"},
            {"asset_type": "course_nomihodai_rules", "operator_status": "usable"},
        ],
    )
    assert qr_fit["package_key"] == PACKAGE_3_KEY

    preserved_qr_fit = recheck_package_fit(
        assets=[{"asset_type": "drink_menu_photo", "operator_status": "usable"}],
        current_package_key=PACKAGE_3_KEY,
    )
    assert preserved_qr_fit["package_key"] == PACKAGE_3_KEY

    override = recheck_package_fit(
        assets=[],
        current_package_key=PACKAGE_1_KEY,
        override_package_key=PACKAGE_2_KEY,
    )
    assert override["blockers"] == ["operator_package_override_reason_missing"]

    workspace = build_production_workspace(
        reply={"reply_id": "reply-test", "establishment_profile": "ramen_ticket_machine"},
        assets=[{"asset_id": "asset-1", "asset_type": "ticket_machine_photo", "operator_status": "usable"}],
        extracted_content=extracted,
        ticket_mapping={"rows": [{"buttons": [{"linked_menu_item": ""}]}], "ui": {"type": "ticket_machine_grid"}, "unmapped_buttons": [{}]},
        package_fit=package_fit,
    )
    assert workspace["left_rail"]["source_assets"]
    assert workspace["center"]["ticket_machine_mapping_ui"]["type"] == "ticket_machine_grid"
    assert "structured_controls" in workspace["right_rail"]

    blocked = evaluate_pre_owner_preview_qa({"all_source_photos_reviewed": True})
    assert blocked["ok"] is False
    passed = evaluate_pre_owner_preview_qa({key: True for key in blocked["checklist"]})
    assert passed["ok"] is True


def test_correction_tasks_are_structured():
    task = build_correction_task("fix_price", {"item_id": "item-1", "requested_value": "¥950"})
    assert task["task_type"] == "fix_price"
    assert task["status"] == "open"
    with pytest.raises(ValueError, match="unsupported_correction_type"):
        build_correction_task("freeform_redesign", {})


def test_order_stage_status_covers_each_package_from_reply_to_follow_up():
    for package_key in (PACKAGE_1_KEY, PACKAGE_2_KEY, PACKAGE_3_KEY):
        stages = order_stage_status({
            "lead_id": "wrm-test",
            "business_name": "Stage Ramen",
            "package_key": package_key,
            "state": "delivered",
            "reply_ids": ["reply-test"],
            "payment": {"status": "confirmed"},
            "intake": {"is_complete": True},
            "approval": {"approved": True},
            "final_export_status": "ready",
            "downloaded_at": "2026-05-04T00:00:00+00:00",
            "follow_up_due_at": "2026-05-18",
        }, has_reply=True, has_download=True)

        assert [stage["stage"] for stage in stages] == [
            "lead",
            "contact",
            "reply",
            "quote",
            "payment_pending",
            "paid",
            "intake",
            "production",
            "owner_review",
            "approval",
            "final_export",
            "download",
            "delivery_follow_up",
        ]
        assert all(stage["complete"] for stage in stages)
