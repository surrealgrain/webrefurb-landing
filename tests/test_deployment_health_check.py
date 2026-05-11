from __future__ import annotations

from pathlib import Path

from scripts.deployment_health_check import check_static


def test_static_deployment_health_check_passes_docs_and_root():
    assert check_static(Path("docs"))["ok"] is True
    assert check_static(Path("."))["ok"] is True


def test_static_deployment_health_check_detects_banned_visible_terms(tmp_path):
    for rel in ["ja", "demo"]:
        (tmp_path / rel).mkdir(parents=True)
    pages = {
        "index.html": ("en", "https://webrefurb.com/"),
        "pricing.html": ("en", "https://webrefurb.com/pricing.html"),
        "ja/index.html": ("ja", "https://webrefurb.com/ja/"),
        "ja/pricing.html": ("ja", "https://webrefurb.com/ja/pricing.html"),
        "demo/index.html": ("en", "https://webrefurb.com/demo/"),
        "demo/ramen.html": ("ja", "https://webrefurb.com/demo/ramen.html"),
        "demo/sushi.html": ("ja", "https://webrefurb.com/demo/sushi.html"),
    }
    for rel, (lang, canonical) in pages.items():
        body = "QR menu"
        if rel == "index.html":
            body = "QR ordering system"
        (tmp_path / rel).write_text(
            f'<!doctype html><html lang="{lang}"><head><title>x</title>'
            f'<link rel="canonical" href="{canonical}">'
            '<meta property="og:title" content="x">'
            '<meta property="og:description" content="x"></head>'
            f"<body>{body}</body></html>",
            encoding="utf-8",
        )

    result = check_static(tmp_path)

    assert result["ok"] is False
    assert any(finding["code"] == "banned_term" for finding in result["findings"])
