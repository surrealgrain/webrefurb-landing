from __future__ import annotations

import json
import zipfile
from pathlib import Path

from pipeline.constants import PACKAGE_1_KEY
from pipeline.final_export_qa import (
    EXPORT_QA_VERSION,
    delivery_export_qa_blockers,
    validate_pdf_artifact,
    validate_zip_package,
)
from pipeline.package_export import approve_package1_export


def _pdf_bytes(width_pt: float = 594.96, height_pt: float = 841.92) -> bytes:
    return (
        "%PDF-1.4\n"
        f"1 0 obj\n<< /Type /Page /MediaBox [0 0 {width_pt:.2f} {height_pt:.2f}] >>\nendobj\n"
        "%%EOF\n"
    ).encode("ascii")


def _write_paid_order(state_root: Path, order_id: str = "ord-final") -> None:
    (state_root / "orders").mkdir(parents=True, exist_ok=True)
    (state_root / "orders" / f"{order_id}.json").write_text(
        json.dumps({
            "order_id": order_id,
            "state": "owner_review",
            "quote": {"quote_date": "2026-05-04"},
            "payment": {"status": "confirmed"},
            "intake": {
                "full_menu_photos": True,
                "price_confirmation": True,
                "delivery_details": True,
                "business_contact_confirmed": True,
                "is_complete": True,
            },
            "approval": {
                "approved": True,
                "approver_name": "Tanaka",
                "approved_package": PACKAGE_1_KEY,
                "source_data_checksum": "source123",
                "artifact_checksum": "artifact123",
            },
            "privacy_note_accepted": True,
        }),
        encoding="utf-8",
    )


def _write_package_output(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "food_menu_print_ready.pdf").write_bytes(_pdf_bytes())
    (output_dir / "food_menu.html").write_text(
        '<html><body><div data-section="ramen"><span class="section-title">RAMEN</span>'
        '<span class="item-en">Shoyu</span><span class="item-jp">醤油</span></div></body></html>',
        encoding="utf-8",
    )
    (output_dir / "menu_data.json").write_text(
        json.dumps({
            "sections": [{"title": "RAMEN", "items": [{
                "name": "Shoyu",
                "japanese_name": "醤油",
                "section": "RAMEN",
                "price_status": "unknown",
                "source_provenance": "owner_text",
                "approval_status": "pending_review",
            }]}],
            "food": {"sections": [{"title": "RAMEN", "items": [{
                "name": "Shoyu",
                "japanese_name": "醤油",
                "section": "RAMEN",
                "price_status": "unknown",
                "source_provenance": "owner_text",
                "approval_status": "pending_review",
            }]}]},
            "drinks": {"sections": []},
        }),
        encoding="utf-8",
    )


def test_package1_final_zip_has_manifest_checksums_and_export_qa(tmp_path):
    output_dir = tmp_path / "builds" / "job-final"
    _write_package_output(output_dir)
    (tmp_path / "jobs").mkdir()
    (tmp_path / "jobs" / "job-final.json").write_text(
        json.dumps({
            "job_id": "job-final",
            "restaurant_name": "Hinode Ramen",
            "status": "ready_for_review",
            "output_dir": str(output_dir),
            "order_id": "ord-final",
        }),
        encoding="utf-8",
    )
    _write_paid_order(tmp_path)

    result = approve_package1_export(state_root=tmp_path, job_id="job-final")

    assert result["export_qa"]["ok"] is True
    qa_report = Path(result["export_qa"]["report_path"])
    assert qa_report.exists()
    report = json.loads(qa_report.read_text(encoding="utf-8"))
    assert report["export_qa_version"] == EXPORT_QA_VERSION

    with zipfile.ZipFile(result["final_export_path"]) as package:
        names = set(package.namelist())
        manifest = json.loads(package.read("PACKAGE_MANIFEST.json"))
        food_pdf = package.read("food_menu_print_ready.pdf")
    assert {"OWNER_APPROVED_CONTENT.json", "PRINT_YOURSELF_NOTE.md", "PACKAGE_MANIFEST.json"} <= names
    assert manifest["export_version"] == EXPORT_QA_VERSION
    assert manifest["checksums"]["food_menu_print_ready.pdf"]
    assert manifest["artifact_list"]
    assert validate_zip_package(
        zip_path=Path(result["final_export_path"]),
        manifest=manifest,
        package_key=PACKAGE_1_KEY,
    )["ok"] is True
    assert food_pdf.startswith(b"%PDF")


def test_zip_validation_rejects_checksum_drift(tmp_path):
    zip_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(zip_path, "w") as package:
        package.writestr("food_menu_print_ready.pdf", b"%PDF-1.4\n")
        package.writestr("menu_data.json", "{}")
        package.writestr("OWNER_APPROVED_CONTENT.json", "{}")
        package.writestr("PRINT_YOURSELF_NOTE.md", "note")
        package.writestr("PACKAGE_MANIFEST.json", "{}")
    manifest = {
        "artifact_list": [
            "food_menu_print_ready.pdf",
            "menu_data.json",
            "OWNER_APPROVED_CONTENT.json",
            "PRINT_YOURSELF_NOTE.md",
        ],
        "checksums": {"food_menu_print_ready.pdf": "wrong"},
    }

    result = validate_zip_package(zip_path=zip_path, manifest=manifest, package_key=PACKAGE_1_KEY)

    assert result["ok"] is False
    assert "checksum_mismatch:food_menu_print_ready.pdf" in result["errors"]


def test_pdf_validation_checks_media_box_against_profile(tmp_path):
    a4_pdf = tmp_path / "a4.pdf"
    b4_pdf = tmp_path / "b4.pdf"
    a4_pdf.write_bytes(_pdf_bytes())
    b4_pdf.write_bytes(_pdf_bytes(width_pt=708.96, height_pt=1001.04))

    assert validate_pdf_artifact(
        a4_pdf,
        print_profile={"paper_size": "A4", "orientation": "portrait"},
    )["ok"] is True
    mismatch = validate_pdf_artifact(
        a4_pdf,
        print_profile={"paper_size": "B4", "orientation": "portrait"},
    )
    assert mismatch["ok"] is False
    assert mismatch["checks"]["page_size_matches_print_profile"] is False
    assert validate_pdf_artifact(
        b4_pdf,
        print_profile={"paper_size": "B4", "orientation": "portrait"},
    )["ok"] is True


def test_delivery_blockers_require_export_qa_and_customer_handoff():
    blockers = delivery_export_qa_blockers({
        "package_key": "package_2_printed_delivered_45k",
        "export_qa": {"ok": True},
        "customer_download_url": "/api/build/job/download",
        "final_customer_message": "Final files are ready.",
    })

    assert blockers == ["package_2_print_handoff_missing"]

    ready = delivery_export_qa_blockers({
        "package_key": "package_2_printed_delivered_45k",
        "export_qa": {"ok": True},
        "customer_download_url": "/api/build/job/download",
        "final_customer_message": "Final files are ready.",
        "print_handoff_record": {"created_at": "2026-05-04T00:00:00+00:00"},
    })

    assert ready == []
