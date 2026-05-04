from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .constants import PROJECT_ROOT
from .utils import read_json


UNLOCK_FILE = "production_readiness_unlock.json"


class LaunchFreezeError(RuntimeError):
    pass


def launch_freeze_status(*, state_root: str | Path) -> dict[str, Any]:
    """Return the real-outreach freeze status for a state root.

    The default project state stays frozen until a deliberate unlock exists.
    Temporary test or rehearsal state roots are not frozen by this guard.
    """
    if os.environ.get("WEBREFURB_ALLOW_REAL_OUTREACH", "").lower() in {"1", "true", "yes", "on"}:
        return {"active": False, "reason": "environment_override"}

    root = Path(state_root).resolve()
    production_root = (PROJECT_ROOT / "state").resolve()
    if root != production_root:
        return {"active": False, "reason": "non_production_state_root"}

    unlock = read_json(root / UNLOCK_FILE, default={})
    if (
        isinstance(unlock, dict)
        and unlock.get("pre_pilot_gates_complete") is True
        and unlock.get("real_outreach_allowed") is True
    ):
        return {"active": False, "reason": "production_readiness_unlocked", "unlock_file": str(root / UNLOCK_FILE)}

    return {
        "active": True,
        "reason": "production_readiness_gates_incomplete",
        "detail": "Real outreach is frozen until pre-pilot production-readiness gates are explicitly unlocked.",
        "unlock_file": str(root / UNLOCK_FILE),
    }


def assert_launch_not_frozen(*, state_root: str | Path) -> None:
    status = launch_freeze_status(state_root=state_root)
    if status["active"]:
        raise LaunchFreezeError(str(status["reason"]))
