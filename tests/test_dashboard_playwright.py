from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import expect, sync_playwright


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_lead_to_published_trial_flow(tmp_path, monkeypatch):
    import dashboard.app as app_mod

    state_root = tmp_path / "state"
    docs_root = tmp_path / "docs"
    for rel in ("studio", "reviews", "uploads", "leads", "trials", "audit", "sent"):
        (state_root / rel).mkdir(parents=True, exist_ok=True)
    docs_root.mkdir()

    lead = {
        "lead_id": "wrm-browser-1",
        "business_name": "Browser Ramen",
        "business_name_ja": "ブラウザーラーメン",
        "category": "ramen",
        "recommended_primary_package": "english_qr_menu_65k",
        "outreach_status": "new",
        "updated_at": "2026-05-11T00:00:00+00:00",
    }
    (state_root / "leads" / "wrm-browser-1.json").write_text(
        json.dumps(lead, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_mod, "STATE_ROOT", state_root)
    monkeypatch.setattr(app_mod, "STUDIO_DIR", state_root / "studio")
    monkeypatch.setattr(app_mod, "REVIEWS_DIR", state_root / "reviews")
    monkeypatch.setattr(app_mod, "UPLOADS_DIR", state_root / "uploads")
    monkeypatch.setattr(app_mod, "AUDIT_DIR", state_root / "audit")
    monkeypatch.setattr(app_mod, "QR_DOCS_ROOT", docs_root)
    monkeypatch.setattr(app_mod, "TEMPLATES_DIR", PROJECT_ROOT / "assets" / "templates")

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app_mod.app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    _wait_for_server(base_url)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.on("dialog", lambda dialog: dialog.accept())

            page.goto(base_url, wait_until="networkidle")
            expect(page.locator("#leads-cards")).to_contain_text("Browser Ramen")
            page.get_by_role("button", name="Build Menu").first.click()
            expect(page.locator("#ws-name")).to_have_text("Browser Ramen")

            page.get_by_role("button", name="Menu Items").click()
            page.get_by_role("button", name="Add item").click()
            page.locator("#item-name-en").fill("Tonkotsu Ramen")
            page.locator("#item-name-ja").fill("豚骨ラーメン")
            page.locator("#item-category").fill("Ramen")
            page.locator("#item-price").fill("¥950")
            page.locator("#item-desc").fill("Rich pork bone broth")
            page.locator("#item-ingredients").fill("pork, wheat")
            page.locator("#item-allergens").fill("wheat")
            for selector in ("#item-price-conf", "#item-desc-conf", "#item-ingr-conf", "#item-allerg-conf"):
                page.locator(selector).check()
            page.get_by_role("button", name="Save").click()
            expect(page.locator("#items-list")).to_contain_text("Tonkotsu Ramen")

            page.get_by_role("button", name="Owner Review").click()
            page.get_by_role("button", name="Generate Review Link").click()
            review_url = page.locator("#owner-panel input").input_value()

            owner_page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True)
            owner_page.goto(review_url, wait_until="networkidle")
            expect(owner_page.locator("body")).to_contain_text("豚骨ラーメン")
            expect(owner_page.locator("body")).to_contain_text("Tonkotsu Ramen")
            owner_page.locator("#btn-confirm").click()
            owner_page.locator("#btn-confirm-submit").click()
            expect(owner_page.locator("body")).to_contain_text("ありがとうございます")
            owner_page.close()

            page.get_by_role("button", name="Publish").click()
            page.get_by_role("button", name="Generate QR Assets").click()
            page.get_by_role("button", name="Publish Menu").click()
            expect(page.locator("#ws-status")).to_have_text("published")
            expect(page.locator("#publish-panel")).to_contain_text("/menus/browser-ramen/")

            page.get_by_role("button", name="Trial").click()
            page.get_by_role("button", name="Create Trial").click()
            for status in ("accepted", "intake_needed", "build_started", "owner_review", "live_trial"):
                page.get_by_role("button", name=status).click()
            expect(page.locator("#trial-panel")).to_contain_text("live_trial")

            page.get_by_role("button", name="Archive Workspace").click()
            expect(page.locator("#ws-status")).to_have_text("archived")
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(base_url: str) -> None:
    import urllib.request

    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("dashboard test server did not start")
