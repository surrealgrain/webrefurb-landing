"""Tests for reliable QR menu hosting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.qr import (
    QRMenuError,
    approve_qr_package,
    assess_reply_qr_readiness,
    check_qr_health,
    complete_qr_extraction,
    confirm_qr_content,
    create_edit_draft,
    create_qr_draft,
    create_qr_sign,
    detect_qr_intent,
    publish_qr_job,
    rollback_qr_menu,
    stable_menu_id,
)


def _pdf_bytes(width_pt: float = 594.96, height_pt: float = 841.92) -> bytes:
    return (
        "%PDF-1.4\n"
        f"1 0 obj\n<< /Type /Page /MediaBox [0 0 {width_pt:.2f} {height_pt:.2f}] >>\nendobj\n"
        "%%EOF\n"
    ).encode("ascii")


def _reply(tmp_path: Path, *, body: str = "QRコード付き英語メニューページをお願いします。") -> dict:
    photo = tmp_path / "uploads" / "reply-attachments" / "reply-ready" / "menu.jpg"
    photo.parent.mkdir(parents=True, exist_ok=True)
    photo.write_bytes(b"photo")
    return {
        "reply_id": "reply-ready",
        "lead_id": "wrm-hinode",
        "business_name": "Hinode Ramen",
        "subject": "QR menu",
        "body": body,
        "attachments": [
            {
                "filename": "menu.jpg",
                "content_type": "image/jpeg",
                "stored_path": str(photo),
                "stored_url": "/uploads/reply-attachments/reply-ready/menu.jpg",
            }
        ],
        "stored_photo_count": 1,
        "photo_count": 1,
        "has_photos": True,
    }


def _complete_payload() -> dict:
    return {
        "items": [
            {
                "name": "Shoyu Ramen",
                "japanese_name": "醤油ラーメン",
                "price": "¥900",
                "description": "Classic soy sauce ramen with a clear, savory broth.",
                "ingredients": ["noodles", "soy sauce broth", "pork chashu", "green onion"],
                "price_confirmation": True,
                "description_confirmation": True,
                "ingredient_allergen_confirmation": True,
                "section": "Ramen",
            }
        ]
    }


def test_qr_intent_detection_english_and_japanese():
    assert detect_qr_intent("Could we use the QR menu service?")
    assert detect_qr_intent("QRコード付き英語メニューページをお願いします。")
    assert not detect_qr_intent("詳しく教えてください。")


def test_qr_readiness_requires_stored_photos_and_intent(tmp_path):
    ready = _reply(tmp_path)
    assert assess_reply_qr_readiness(ready)["qr_ready"] is True

    no_intent = {**ready, "subject": "メニュー写真", "body": "メニュー写真を送ります。"}
    assert assess_reply_qr_readiness(no_intent)["qr_ready"] is False

    no_photos = {**ready, "stored_photo_count": 0}
    assert assess_reply_qr_readiness(no_photos)["qr_ready"] is False


def test_stable_menu_id_prefers_restaurant_slug():
    assert stable_menu_id(business_name="Hinode Ramen", lead_id="wrm-123") == "hinode-ramen"
    assert stable_menu_id(business_name="", lead_id="wrm-123") == "wrm-123"


def test_create_draft_writes_source_and_public_artifacts(tmp_path):
    state_root = tmp_path / "state"
    docs_root = tmp_path / "docs"

    job = create_qr_draft(
        reply=_reply(tmp_path),
        state_root=state_root,
        docs_root=docs_root,
        payload=_complete_payload(),
    )

    assert job["status"] == "ready_for_review"
    assert (state_root / "qr_menus" / "hinode-ramen" / "versions" / job["version_id"] / "source.json").exists()
    assert (docs_root / "menus" / "_drafts" / job["job_id"] / "index.html").exists()
    assert (docs_root / "menus" / "_drafts" / job["job_id"] / "qr.svg").exists()
    assert not (docs_root / "menus" / "_drafts" / job["job_id"] / "qr_sign.html").exists()


def test_photo_only_reply_becomes_needs_extraction_not_reviewable_draft(tmp_path):
    state_root = tmp_path / "state"
    docs_root = tmp_path / "docs"

    job = create_qr_draft(
        reply=_reply(tmp_path),
        state_root=state_root,
        docs_root=docs_root,
        payload={},
    )

    assert job["status"] == "needs_extraction"
    assert job["extraction_required"] is True
    assert job["validation"]["errors"] == ["structured_menu_items_required"]
    assert not (docs_root / "menus" / "_drafts" / job["job_id"] / "index.html").exists()
    source = json.loads((state_root / "qr_menus" / "hinode-ramen" / "versions" / job["version_id"] / "source.json").read_text())
    assert source["status"] == "needs_extraction"
    assert source["items"] == []


def test_complete_qr_extraction_turns_needs_extraction_job_into_reviewable_draft(tmp_path):
    state_root = tmp_path / "state"
    docs_root = tmp_path / "docs"

    job = create_qr_draft(
        reply=_reply(tmp_path),
        state_root=state_root,
        docs_root=docs_root,
        payload={},
    )

    extracted = complete_qr_extraction(
        state_root=state_root,
        docs_root=docs_root,
        job_id=job["job_id"],
        payload={"raw_text": "醤油ラーメン ¥900\n餃子 ¥450"},
    )

    assert extracted["status"] == "ready_for_review"
    assert extracted["extraction_method"] == "structured_payload"
    assert (docs_root / "menus" / "_drafts" / job["job_id"] / "index.html").exists()
    source = json.loads((state_root / "qr_menus" / "hinode-ramen" / "versions" / job["version_id"] / "source.json").read_text())
    assert source["status"] == "draft"
    assert len(source["items"]) == 2
    assert source["items"][0]["japanese_name"] == "醤油ラーメン"
    assert source["items"][0]["name"] == "Shoyu Ramen"


def test_publish_blocks_unconfirmed_owner_content_until_confirmed(tmp_path):
    state_root = tmp_path / "state"
    docs_root = tmp_path / "docs"
    job = create_qr_draft(
        reply=_reply(tmp_path),
        state_root=state_root,
        docs_root=docs_root,
        payload={
            "items": [
                {
                    "name": "Shoyu Ramen",
                    "japanese_name": "醤油ラーメン",
                    "price": "¥900",
                    "description": "Classic soy sauce ramen with a clear, savory broth.",
                    "ingredients": ["noodles", "soy sauce broth"],
                    "section": "Ramen",
                }
            ]
        },
    )

    with pytest.raises(QRMenuError, match="description_owner_confirmation_required"):
        publish_qr_job(state_root=state_root, docs_root=docs_root, job_id=job["job_id"])

    confirm_qr_content(state_root=state_root, docs_root=docs_root, job_id=job["job_id"])
    published = publish_qr_job(state_root=state_root, docs_root=docs_root, job_id=job["job_id"])
    assert published["status"] == "published"


def test_publish_creates_immutable_version_and_stable_live_url(tmp_path):
    state_root = tmp_path / "state"
    docs_root = tmp_path / "docs"
    job = create_qr_draft(
        reply=_reply(tmp_path),
        state_root=state_root,
        docs_root=docs_root,
        payload=_complete_payload(),
    )
    create_qr_sign(state_root=state_root, docs_root=docs_root, job_id=job["job_id"])

    published = publish_qr_job(state_root=state_root, docs_root=docs_root, job_id=job["job_id"])

    menu_root = docs_root / "menus" / "hinode-ramen"
    assert published["status"] == "published"
    assert published["live_url"] == "https://webrefurb.com/menus/hinode-ramen/"
    assert (menu_root / "index.html").exists()
    assert (menu_root / "manifest.json").exists()
    assert (menu_root / "versions" / published["published_version_id"] / "index.html").exists()
    assert (menu_root / "versions" / published["published_version_id"] / "qr_sign.html").exists()
    assert "WRM_REVIEW_ONLY" not in (menu_root / "versions" / published["published_version_id"] / "index.html").read_text()


def test_create_qr_sign_returns_draft_sign_links(tmp_path):
    state_root = tmp_path / "state"
    docs_root = tmp_path / "docs"
    job = create_qr_draft(
        reply=_reply(tmp_path),
        state_root=state_root,
        docs_root=docs_root,
        payload=_complete_payload(),
    )

    sign = create_qr_sign(state_root=state_root, docs_root=docs_root, job_id=job["job_id"])

    assert sign["qr_sign_url"] == f"/menus/_drafts/{job['job_id']}/qr_sign.html"
    assert (docs_root / "menus" / "_drafts" / job["job_id"] / "qr_sign.html").exists()
    assert "Scan QR for English Menu" in (docs_root / "menus" / "_drafts" / job["job_id"] / "qr_sign.html").read_text()
    assert (docs_root / "menus" / "_drafts" / job["job_id"] / "qr_sign.svg").exists()


def test_publish_blocks_incomplete_draft_and_leaves_live_pointer(tmp_path):
    state_root = tmp_path / "state"
    docs_root = tmp_path / "docs"
    complete = create_qr_draft(
        reply=_reply(tmp_path),
        state_root=state_root,
        docs_root=docs_root,
        payload=_complete_payload(),
    )
    first = publish_qr_job(state_root=state_root, docs_root=docs_root, job_id=complete["job_id"])

    incomplete = create_qr_draft(
        reply=_reply(tmp_path),
        state_root=state_root,
        docs_root=docs_root,
        payload={"items": [{"name": "Miso Ramen", "japanese_name": "味噌ラーメン", "price": "¥1000", "section": "Ramen"}]},
    )
    with pytest.raises(QRMenuError):
        publish_qr_job(state_root=state_root, docs_root=docs_root, job_id=incomplete["job_id"])

    manifest = json.loads((docs_root / "menus" / "hinode-ramen" / "manifest.json").read_text())
    assert manifest["current_version"] == first["published_version_id"]


def test_edit_draft_does_not_change_live_and_rollback_restores_previous(tmp_path):
    state_root = tmp_path / "state"
    docs_root = tmp_path / "docs"
    first_job = create_qr_draft(
        reply=_reply(tmp_path),
        state_root=state_root,
        docs_root=docs_root,
        payload=_complete_payload(),
    )
    first = publish_qr_job(state_root=state_root, docs_root=docs_root, job_id=first_job["job_id"])
    edit = create_edit_draft(
        state_root=state_root,
        docs_root=docs_root,
        menu_id="hinode-ramen",
        payload={
            "items": [
                {
                    "name": "Miso Ramen",
                    "japanese_name": "味噌ラーメン",
                    "description": "Rich miso ramen.",
                    "ingredients": ["noodles", "miso broth"],
                    "description_confirmation": True,
                    "ingredient_allergen_confirmation": True,
                    "section": "Ramen",
                }
            ]
        },
    )

    manifest_before = json.loads((docs_root / "menus" / "hinode-ramen" / "manifest.json").read_text())
    assert manifest_before["current_version"] == first["published_version_id"]

    second = publish_qr_job(state_root=state_root, docs_root=docs_root, job_id=edit["job_id"])
    assert second["published_version_id"] != first["published_version_id"]
    rolled = rollback_qr_menu(
        state_root=state_root,
        docs_root=docs_root,
        menu_id="hinode-ramen",
        version_id=first["published_version_id"],
    )
    assert rolled["current_version"] == first["published_version_id"]
    assert rolled["ok"] is True


def test_health_detects_checksum_drift(tmp_path):
    state_root = tmp_path / "state"
    docs_root = tmp_path / "docs"
    job = create_qr_draft(
        reply=_reply(tmp_path),
        state_root=state_root,
        docs_root=docs_root,
        payload=_complete_payload(),
    )
    published = publish_qr_job(state_root=state_root, docs_root=docs_root, job_id=job["job_id"])
    index = docs_root / "menus" / "hinode-ramen" / "versions" / published["published_version_id"] / "index.html"
    index.write_text(index.read_text() + "\n<!-- corrupted -->", encoding="utf-8")

    health = check_qr_health(state_root=state_root, docs_root=docs_root, menu_id="hinode-ramen")
    assert health["ok"] is False
    assert "index.html" in health["checksum_drift"]


def test_health_detects_missing_source_data(tmp_path):
    state_root = tmp_path / "state"
    docs_root = tmp_path / "docs"
    job = create_qr_draft(
        reply=_reply(tmp_path),
        state_root=state_root,
        docs_root=docs_root,
        payload=_complete_payload(),
    )
    published = publish_qr_job(state_root=state_root, docs_root=docs_root, job_id=job["job_id"])
    source_path = state_root / "qr_menus" / "hinode-ramen" / "versions" / published["published_version_id"] / "source.json"
    source_path.unlink()

    health = check_qr_health(state_root=state_root, docs_root=docs_root, menu_id="hinode-ramen")
    assert health["ok"] is False
    assert "source_data_missing" in health["errors"]


def test_health_detects_missing_sign_pdf_for_approved_package(tmp_path, monkeypatch):
    def fake_html_to_pdf_sync(html_path: Path, pdf_path: Path, *, print_profile=None) -> Path:
        pdf_path.write_bytes(_pdf_bytes())
        return pdf_path

    monkeypatch.setattr("pipeline.qr.html_to_pdf_sync", fake_html_to_pdf_sync)
    state_root = tmp_path / "state"
    docs_root = tmp_path / "docs"
    job = create_qr_draft(
        reply=_reply(tmp_path),
        state_root=state_root,
        docs_root=docs_root,
        payload=_complete_payload(),
    )
    create_qr_sign(state_root=state_root, docs_root=docs_root, job_id=job["job_id"])
    approved = approve_qr_package(state_root=state_root, docs_root=docs_root, job_id=job["job_id"])
    Path(approved["qr_sign_print_ready_pdf"]).unlink()

    health = check_qr_health(state_root=state_root, docs_root=docs_root, menu_id="hinode-ramen")
    assert health["ok"] is False
    assert "sign_pdf_missing" in health["errors"]
