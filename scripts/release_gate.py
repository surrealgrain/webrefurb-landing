#!/usr/bin/env python3
"""Run the local release gate for WebRefurbMenu."""

from __future__ import annotations

import argparse
import subprocess
import sys


COMMANDS = (
    (".venv/bin/python", "-m", "pytest", "tests/", "-q"),
    (".venv/bin/python", "-m", "pipeline.cli", "audit-state"),
    (".venv/bin/python", "scripts/deployment_health_check.py", "--mode", "static", "--root", "docs"),
    (".venv/bin/python", "scripts/deployment_health_check.py", "--mode", "static", "--root", "."),
    (".venv/bin/python", "scripts/secret_scan.py", "--root", "."),
)


def run(*, include_live: bool) -> int:
    for command in COMMANDS:
        print("+", " ".join(command), flush=True)
        completed = subprocess.run(command)
        if completed.returncode != 0:
            return completed.returncode
    if include_live:
        command = (".venv/bin/python", "scripts/deployment_health_check.py", "--mode", "live", "--base-url", "https://webrefurb.com")
        print("+", " ".join(command), flush=True)
        completed = subprocess.run(command)
        if completed.returncode != 0:
            return completed.returncode
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run tests and production-readiness release checks.")
    parser.add_argument("--include-live", action="store_true", help="Also check deployed webrefurb.com URLs.")
    args = parser.parse_args(argv)
    return run(include_live=args.include_live)


if __name__ == "__main__":
    raise SystemExit(main())
