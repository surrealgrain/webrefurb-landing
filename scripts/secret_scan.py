#!/usr/bin/env python3
"""Small repository secret scan for release checks."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEFAULT_EXCLUDES = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    "state",
    ".env",
}

SECRET_PATTERNS = {
    "openai_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "resend_key": re.compile(r"re_[A-Za-z0-9]{20,}"),
    "generic_token_assignment": re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*=\s*['\"][^'\"\n]{12,}['\"]"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
}


def scan(root: Path) -> dict:
    findings: list[dict] = []
    for path in root.rglob("*"):
        if _is_excluded(path):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append({"path": str(path.relative_to(root)), "code": name})
    return {"ok": not findings, "findings": findings}


def _is_excluded(path: Path) -> bool:
    for part in path.parts:
        if part in DEFAULT_EXCLUDES or part.startswith(".env"):
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan repository text files for obvious secrets.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = scan(Path(args.root).resolve())
    if args.json or not result["ok"]:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("ok: secret scan passed")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
