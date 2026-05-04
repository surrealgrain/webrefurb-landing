from __future__ import annotations

import json

import pytest

from pipeline.constants import PROJECT_ROOT
from pipeline.launch_freeze import LaunchFreezeError, assert_launch_not_frozen, launch_freeze_status


def test_launch_freeze_blocks_default_project_state_without_unlock(monkeypatch):
    monkeypatch.delenv("WEBREFURB_ALLOW_REAL_OUTREACH", raising=False)

    status = launch_freeze_status(state_root=PROJECT_ROOT / "state")

    assert status["active"] is True
    assert status["reason"] == "production_readiness_gates_incomplete"
    with pytest.raises(LaunchFreezeError, match="production_readiness_gates_incomplete"):
        assert_launch_not_frozen(state_root=PROJECT_ROOT / "state")


def test_launch_freeze_allows_temp_state_roots(tmp_path):
    status = launch_freeze_status(state_root=tmp_path)

    assert status["active"] is False
    assert status["reason"] == "non_production_state_root"


def test_launch_freeze_requires_explicit_unlock_file(tmp_path, monkeypatch):
    production_root = PROJECT_ROOT / "state"
    monkeypatch.delenv("WEBREFURB_ALLOW_REAL_OUTREACH", raising=False)
    unlock_path = production_root / "production_readiness_unlock.json"
    original = unlock_path.read_text(encoding="utf-8") if unlock_path.exists() else None
    unlock_path.write_text(
        json.dumps({"pre_pilot_gates_complete": True, "real_outreach_allowed": True}),
        encoding="utf-8",
    )
    try:
        status = launch_freeze_status(state_root=production_root)
    finally:
        if original is None:
            unlock_path.unlink(missing_ok=True)
        else:
            unlock_path.write_text(original, encoding="utf-8")

    assert status["active"] is False
    assert status["reason"] == "production_readiness_unlocked"
