from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright


DOCS_ROOT = Path(__file__).resolve().parents[1] / "docs"


def _demo_url(name: str) -> str:
    return (DOCS_ROOT / "demo" / f"{name}.html").as_uri()


def test_demo_visual_tokens_remain_coral_white():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 375, "height": 812})
        page.goto(_demo_url("ramen"), wait_until="networkidle")

        tokens = page.evaluate(
            """() => {
                const styles = getComputedStyle(document.documentElement);
                return {
                  accent: styles.getPropertyValue('--accent').trim(),
                  accentSoft: styles.getPropertyValue('--accent-soft').trim(),
                  card: styles.getPropertyValue('--card').trim(),
                  bg: styles.getPropertyValue('--bg').trim()
                };
            }"""
        )

        browser.close()

    assert tokens == {
        "accent": "#E94560",
        "accentSoft": "#FFF0F2",
        "card": "#FFFFFF",
        "bg": "#FAFAFA",
    }


def test_ramen_demo_add_to_staff_list_mobile_flow():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 375, "height": 812}, is_mobile=True)
        page.goto(_demo_url("ramen"), wait_until="networkidle")

        assert page.locator("html").get_attribute("lang") == "ja"
        page.locator("#langEn").click()
        assert page.locator("html").get_attribute("lang") == "en"

        page.locator(".add-btn").first.click()
        page.wait_for_function("() => document.querySelector('.staff-badge').textContent === '1'")
        page.locator(".stepper.active .plus").first.click()
        page.wait_for_function("() => document.querySelector('.staff-badge').textContent === '2'")
        page.locator("#staffBtn").click()
        page.wait_for_selector(".overlay.open")

        overlay = page.locator(".overlay").inner_text()
        assert "豚骨ラーメン" in overlay
        assert "×2" in overlay
        assert "checkout" not in overlay.lower()
        assert "payment" not in overlay.lower()
        browser.close()


def test_sushi_demo_staff_overlay_mobile_flow():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True)
        page.goto(_demo_url("sushi"), wait_until="networkidle")

        page.locator(".add-btn").first.click()
        page.wait_for_function("() => document.querySelector('.staff-badge').textContent === '1'")
        page.locator("#staffBtn").click()
        page.wait_for_selector(".overlay.open")

        overlay = page.locator(".overlay").inner_text()
        assert "まぐろ握り" in overlay
        assert "×1" in overlay
        assert "checkout" not in overlay.lower()
        assert "payment" not in overlay.lower()
        browser.close()
