from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path
from urllib.error import HTTPError

from pipeline.backup import backup_state
from pipeline.llm_client import call_llm
from pipeline.package_export import validate_package_output
from pipeline.utils import load_project_env


def test_load_project_env_reads_dotenv_file(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("WRM_TEST_ENV=loaded\n", encoding="utf-8")
    monkeypatch.delenv("WRM_TEST_ENV", raising=False)

    assert load_project_env(env_path) is True
    assert os.environ["WRM_TEST_ENV"] == "loaded"


def test_backup_state_archives_required_directories(tmp_path):
    state_root = tmp_path / "state"
    for name in ("leads", "sent", "jobs", "orders", "replies", "uploads", "builds", "qr_jobs", "qr_menus", "launch_batches", "launch_smoke_tests"):
        path = state_root / name
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{name}.txt").write_text(name, encoding="utf-8")

    result = backup_state(state_root=state_root)
    archive_path = Path(result["archive_path"])

    assert archive_path.exists()
    assert set(result["included_directories"]) == {
        "leads", "sent", "jobs", "orders", "replies", "uploads", "builds", "qr_jobs", "qr_menus", "launch_batches", "launch_smoke_tests"
    }
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
    assert "leads/leads.txt" in names
    assert "orders/orders.txt" in names
    assert "qr_menus/qr_menus.txt" in names
    assert "launch_smoke_tests/launch_smoke_tests.txt" in names


def test_validate_package_output_blocks_approval_when_fallback_used(tmp_path):
    output_dir = tmp_path / "build"
    output_dir.mkdir(parents=True, exist_ok=True)

    for name in (
        "restaurant_menu_print_ready_combined.pdf",
        "food_menu_print_ready.pdf",
        "drinks_menu_print_ready.pdf",
    ):
        (output_dir / name).write_bytes(b"%PDF-1.4\n% test\n")
    for name in (
        "food_menu_editable_vector.svg",
        "drinks_menu_editable_vector.svg",
    ):
        (output_dir / name).write_text("<svg></svg>", encoding="utf-8")
    for name in (
        "restaurant_menu_print_master.html",
        "food_menu_browser_preview.html",
    ):
        (output_dir / name).write_text("<html>preview</html>", encoding="utf-8")

    (output_dir / "menu_data.json").write_text(json.dumps({
        "sections": [{"title": "RAMEN", "items": [{"name": "[特製ラーメン]"}]}],
        "approval_blockers": ["llm_fallback_requires_operator_review"],
    }), encoding="utf-8")

    validation = validate_package_output(output_dir=output_dir)

    assert validation["ok"] is False
    assert "approval_blockers_present" in validation["errors"]


def test_call_llm_retries_transient_http_errors(monkeypatch):
    attempts = {"count": 0}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": "translated"}}],
            }).encode("utf-8")

    def fake_urlopen(request, timeout):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise HTTPError(
                url=request.full_url,
                code=500,
                msg="server error",
                hdrs=None,
                fp=None,
            )
        return _Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("pipeline.llm_client.time.sleep", lambda _: None)

    result = call_llm(
        model="test-model",
        system="system",
        user="user",
        api_key="test-key",
        timeout_seconds=1,
    )

    assert result == "translated"
    assert attempts["count"] == 3
