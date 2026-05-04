#!/usr/bin/env python3
"""Audit that WebRefurbMenu is not wired to Neon/Postgres."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "state",
    "webrefurb_menu.egg-info",
}

SKIP_FILES = {
    Path(".dockerignore"),
    Path("compose.no-neon.yml"),
    Path("NO_NEON.md"),
    Path("scripts/no_neon_audit.py"),
}

TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".css",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}

PATTERNS = [
    re.compile(r"\bneon\b", re.IGNORECASE),
    re.compile(r"\bDATABASE_URL\b"),
    re.compile(r"\bPOSTGRES(?:QL)?\b", re.IGNORECASE),
    re.compile(r"\bPGHOST\b"),
    re.compile(r"\bPGUSER\b"),
    re.compile(r"\bPGPASSWORD\b"),
    re.compile(r"\bpsycopg\b", re.IGNORECASE),
    re.compile(r"\basyncpg\b", re.IGNORECASE),
    re.compile(r"\bsqlalchemy\b", re.IGNORECASE),
]


def iter_project_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.is_dir() or rel in SKIP_FILES:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        files.append(path)
    return sorted(files)


def env_keys() -> list[str]:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return []
    keys: list[str] = []
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key:
            keys.append(key)
    return sorted(keys)


def scan_files() -> list[tuple[Path, int, str]]:
    findings: list[tuple[Path, int, str]] = []
    for path in iter_project_files():
        rel = path.relative_to(ROOT)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(lines, start=1):
            if any(pattern.search(line) for pattern in PATTERNS):
                findings.append((rel, lineno, line.strip()[:160]))
    for key in env_keys():
        if any(pattern.search(key) for pattern in PATTERNS):
            findings.append((Path(".env"), 0, f"{key}=<redacted>"))
    return findings


def count_files(path: Path, glob: str) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.glob(glob) if item.is_file())


def print_state_summary() -> None:
    state = ROOT / "state"
    print("Local persistence summary:")
    print(f"  state root: {state}")
    print(f"  leads: {count_files(state / 'leads', '*.json')}")
    print(f"  orders: {count_files(state / 'orders', '*.json')}")
    print(f"  sent records: {count_files(state / 'sent', '*.json')}")
    print(f"  incoming replies: {count_files(state / 'incoming_replies', '*.json')}")
    print(f"  launch batches: {count_files(state / 'launch_batches', '*.json')}")
    print(f"  email discovery sqlite: {'present' if (state / 'email_discovery.db').exists() else 'not present'}")
    print(f"  QR/static menu files: {count_files(ROOT / 'docs' / 'menus', '**/*')}")


def main() -> int:
    findings = scan_files()
    if findings:
        print("Found possible Neon/Postgres database wiring:")
        for path, lineno, snippet in findings:
            location = str(path) if lineno == 0 else f"{path}:{lineno}"
            print(f"  {location}: {snippet}")
        print()
        print_state_summary()
        return 1

    print("No Neon/Postgres database wiring found.")
    print()
    print_state_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
