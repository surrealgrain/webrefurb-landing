from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

from .utils import PROJECT_ROOT, ensure_dir, utc_now

STATE_BACKUP_DIRS = (
    "leads",
    "sent",
    "jobs",
    "orders",
    "replies",
    "uploads",
    "builds",
    "qr_jobs",
    "qr_menus",
)


def backup_state(
    *,
    state_root: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Archive operational state directories into a timestamped ZIP."""
    state_root = (state_root or (PROJECT_ROOT / "state")).resolve()
    backup_dir = state_root / "backups"
    ensure_dir(backup_dir)

    archive_path = output_path.resolve() if output_path else (backup_dir / f"webrefurb-state-{_backup_timestamp()}.zip")
    ensure_dir(archive_path.parent)

    included: list[str] = []
    missing: list[str] = []

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in STATE_BACKUP_DIRS:
            path = state_root / name
            if not path.exists():
                missing.append(name)
                continue
            included.append(name)
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    archive.write(child, arcname=str(child.relative_to(state_root)))

    return {
        "archive_path": str(archive_path),
        "state_root": str(state_root),
        "included_directories": included,
        "missing_directories": missing,
    }


def _backup_timestamp() -> str:
    return utc_now().replace(":", "").replace("-", "")
