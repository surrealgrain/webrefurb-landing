#!/usr/bin/env python3
"""Record a professional usage flow GIF of the MENYA HIBIKI prototype.

- Small coral tap flash (industry standard for mobile demo recordings)
- ffmpeg two-pass palette for quality
- gifsicle lossy compression for email-safe file size
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROTOTYPE = ROOT / "assets" / "templates" / "_demo_prototype.html"
OUT_GIF = ROOT / "assets" / "templates" / "demo_flow.gif"
OUT_RAW = Path("/tmp/demo_flow_raw.gif")
FRAMES_DIR = Path("/tmp/gif_frames")

VIEWPORT_W, VIEWPORT_H = 390, 844
DEVICE_SCALE = 2
FPS = 15
FRAME_MS = int(1000 / FPS)
GIF_WIDTH = 280


def main() -> None:
    if FRAMES_DIR.exists():
        for f in FRAMES_DIR.glob("frame_*.png"):
            f.unlink()
    FRAMES_DIR.mkdir(exist_ok=True)

    frame_idx = [0]

    def snap(page, count=1, interval_ms=0):
        for _ in range(count):
            path = FRAMES_DIR / f"frame_{frame_idx[0]:05d}.png"
            page.screenshot(path=str(path))
            frame_idx[0] += 1
            if interval_ms > 0:
                page.wait_for_timeout(interval_ms)

    def scroll_smooth(page, y_start, y_end, steps=35):
        for i in range(steps + 1):
            frac = i / steps
            frac = frac * frac * (3 - 2 * frac)
            y = y_start + (y_end - y_start) * frac
            page.evaluate(f"window.scrollTo(0, {y})")
            snap(page)

    def scroll_to(page, selector, offset=80, steps=25):
        target_y = page.evaluate(f'''
            () => {{
                const el = document.querySelector('{selector}');
                if (!el) return window.scrollY;
                const rect = el.getBoundingClientRect();
                return window.scrollY + rect.top - {offset};
            }}
        ''')
        current_y = page.evaluate("window.scrollY")
        scroll_smooth(page, current_y, max(0, target_y), steps)

    def tap(page, locator):
        """Industry-standard tap flash: appear → press → fade."""
        box = locator.bounding_box()
        if not box:
            locator.click()
            return
        x = box['x'] + box['width'] / 2
        y = box['y'] + box['height'] / 2

        # Appear small
        page.evaluate(f"""
            var d=document.getElementById('tap-ind');
            d.style.left='{x}px';d.style.top='{y}px';
            d.style.opacity='1';
            d.style.transform='translate(-50%,-50%) scale(0.5)';
            d.style.background='rgba(233,69,96,0.75)';
        """)
        snap(page, count=2, interval_ms=FRAME_MS)

        # Press — scale up
        page.evaluate("""
            var d=document.getElementById('tap-ind');
            d.style.transform='translate(-50%,-50%) scale(1.3)';
            d.style.background='rgba(233,69,96,0.5)';
        """)
        locator.click()
        snap(page, count=2, interval_ms=FRAME_MS)

        # Fade out, expand
        page.evaluate("""
            var d=document.getElementById('tap-ind');
            d.style.opacity='0';
            d.style.transform='translate(-50%,-50%) scale(2)';
            d.style.background='rgba(233,69,96,0.1)';
        """)
        snap(page, count=2, interval_ms=FRAME_MS)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
            device_scale_factor=DEVICE_SCALE,
        )
        page = ctx.new_page()
        page.goto(PROTOTYPE.as_uri())
        page.wait_for_timeout(600)

        # Inject tap indicator
        page.evaluate("""
            var td = document.createElement('div');
            td.id = 'tap-ind';
            td.style.cssText = 'position:fixed;z-index:9999;width:20px;height:20px;border-radius:50%;background:rgba(233,69,96,0.75);pointer-events:none;opacity:0;transform:translate(-50%,-50%) scale(0.5);transition:opacity 0.08s,transform 0.08s,background 0.08s;box-shadow:0 0 14px rgba(233,69,96,0.35)';
            document.body.appendChild(td);
        """)

        # ── SCENE 1: Ramen — scroll down, back up ──
        snap(page, count=12, interval_ms=FRAME_MS)  # look at menu

        scroll_smooth(page, 0, 950, steps=40)
        snap(page, count=10, interval_ms=FRAME_MS)  # reading at bottom

        scroll_smooth(page, 950, 0, steps=35)
        snap(page, count=12, interval_ms=FRAME_MS)  # back at tonkotsu

        # ── SCENE 2: Tonkotsu toppings ──
        tonkotsu = page.locator(".item").nth(0)

        snap(page, count=15, interval_ms=FRAME_MS)  # reading toppings

        tap(page, tonkotsu.locator(".topping-pill").nth(0))  # Chashu
        snap(page, count=15, interval_ms=FRAME_MS)  # watch animation

        snap(page, count=15, interval_ms=FRAME_MS)  # considering next

        tap(page, tonkotsu.locator(".topping-pill").nth(1))  # Egg
        snap(page, count=15, interval_ms=FRAME_MS)  # watch animation

        snap(page, count=12, interval_ms=FRAME_MS)  # decide to add

        tap(page, tonkotsu.locator(".add-btn"))  # Add to list
        snap(page, count=20, interval_ms=FRAME_MS)  # watch fly ball + badge

        # ── SCENE 3: Sides → Edamame ──
        snap(page, count=12, interval_ms=FRAME_MS)
        tap(page, page.locator("button.tab:nth-child(2)"))
        snap(page, count=12, interval_ms=FRAME_MS)  # reading sides

        scroll_to(page, '.section[data-tab="sides"] .item:nth-child(3) .add-btn', offset=120, steps=20)
        snap(page, count=12, interval_ms=FRAME_MS)  # reading edamame

        edamame = page.locator(".section[data-tab='sides'] .item").nth(2)
        tap(page, edamame.locator(".add-btn"))
        snap(page, count=15, interval_ms=FRAME_MS)

        # ── SCENE 4: Drinks → Draft Beer ──
        snap(page, count=12, interval_ms=FRAME_MS)
        tap(page, page.locator("button.tab:nth-child(3)"))
        snap(page, count=12, interval_ms=FRAME_MS)  # reading drinks

        scroll_smooth(page, 0, 450, steps=22)
        snap(page, count=10, interval_ms=FRAME_MS)  # browsing

        scroll_smooth(page, 450, 0, steps=22)
        snap(page, count=12, interval_ms=FRAME_MS)  # back at beer

        snap(page, count=10, interval_ms=FRAME_MS)  # deciding

        beer = page.locator(".section[data-tab='drinks'] .item").nth(0)
        tap(page, beer.locator(".add-btn"))
        snap(page, count=15, interval_ms=FRAME_MS)

        # ── SCENE 5: Staff overlay ──
        snap(page, count=10, interval_ms=FRAME_MS)
        scroll_smooth(page, page.evaluate("window.scrollY"), 0, steps=14)
        snap(page, count=12, interval_ms=FRAME_MS)  # looking at badge

        tap(page, page.locator("#staffBtn"))
        snap(page, count=50, interval_ms=FRAME_MS)  # long hold on overlay

        browser.close()

    total = frame_idx[0]
    print(f"Captured {total} frames")

    # ── Step 1: ffmpeg two-pass high-quality GIF ──
    palette_path = FRAMES_DIR / "palette.png"
    print("Step 1: ffmpeg palette generation...")
    subprocess.run([
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(FRAMES_DIR / "frame_%05d.png"),
        "-vf", f"scale={GIF_WIDTH}:-1:flags=lanczos,palettegen=max_colors=256:stats_mode=diff",
        str(palette_path),
    ], capture_output=True, check=True)

    print("Step 2: ffmpeg encoding...")
    subprocess.run([
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(FRAMES_DIR / "frame_%05d.png"),
        "-i", str(palette_path),
        "-lavfi", f"scale={GIF_WIDTH}:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
        "-gifflags", "+transdiff",
        str(OUT_RAW),
    ], capture_output=True, check=True)

    raw_mb = OUT_RAW.stat().st_size / (1024 * 1024)
    print(f"  Raw GIF: {raw_mb:.1f} MB")

    # ── Step 2: gifsicle lossy optimization ──
    print("Step 3: gifsicle lossy optimization...")
    subprocess.run([
        "gifsicle",
        "--lossy=200",
        "--optimize=3",
        "-o", str(OUT_GIF),
        str(OUT_RAW),
    ], capture_output=True, check=True)

    size_mb = OUT_GIF.stat().st_size / (1024 * 1024)
    duration_s = total / FPS
    print(f"\nFinal: {OUT_GIF}")
    print(f"  {total} frames, {duration_s:.1f}s, {FPS}fps, {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
