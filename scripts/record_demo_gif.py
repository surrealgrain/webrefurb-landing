#!/usr/bin/env python3
"""Record the _demo_prototype.html ghost animation as a looping GIF.

Captures via Playwright at full viewport resolution (390px × 2x device scale),
quantizes to a shared 256-color palette, deduplicates identical frames,
and writes a GIF with per-frame durations for correct playback timing.
"""
from __future__ import annotations

import io
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROTOTYPE = ROOT / "assets" / "templates" / "_demo_prototype.html"
OUT_GIF = ROOT / "assets" / "templates" / "_demo_prototype_demo.gif"

CAPTURE_FPS = 15
DURATION_S = 12.0
VIEWPORT_W, VIEWPORT_H = 390, 844
DEVICE_SCALE = 2
TARGET_W = 390
FRAME_MS = int(1000 / CAPTURE_FPS)


def main() -> None:
    # Phase 1: Capture all frames at full resolution
    raw_frames: list[Image.Image] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
            device_scale_factor=DEVICE_SCALE,
        )
        page = ctx.new_page()
        page.goto(PROTOTYPE.as_uri() + "?demo")
        page.wait_for_timeout(600)

        total = int(DURATION_S * CAPTURE_FPS)
        for i in range(total):
            data = page.screenshot(type="png")
            img = Image.open(io.BytesIO(data)).convert("RGB")
            raw_frames.append(img)
            time.sleep(1 / CAPTURE_FPS)

        browser.close()

    print(f"Captured {len(raw_frames)} frames at {raw_frames[0].size}")

    # Phase 2: Resize to target width (390px — native viewport, crisp text)
    target_h = int(raw_frames[0].height * TARGET_W / raw_frames[0].width)
    frames = [f.resize((TARGET_W, target_h), Image.LANCZOS) for f in raw_frames]
    print(f"Resized to {TARGET_W}×{target_h}")

    # Phase 3: Build a shared 256-color palette from multiple sample frames
    # Sample every 20th frame for a representative palette
    sample_indices = list(range(0, len(frames), max(1, len(frames) // 8)))
    sample_images = [frames[i] for i in sample_indices]
    # Build palette from a representative mid-animation frame
    palette_src = frames[len(frames) // 3].quantize(colors=256, method=Image.Quantize.MEDIANCUT)

    # Quantize all frames to shared palette with Floyd-Steinberg dithering for smooth gradients
    quantized = [f.quantize(palette=palette_src, dither=1) for f in frames]

    # Phase 4: Deduplicate at the quantized level
    unique_frames: list[Image.Image] = []
    durations: list[int] = []

    for qf in quantized:
        if unique_frames and qf.tobytes() == unique_frames[-1].tobytes():
            durations[-1] += FRAME_MS
        else:
            unique_frames.append(qf)
            durations.append(FRAME_MS)

    print(f"Unique frames after quantize: {len(unique_frames)} (from {len(raw_frames)} captured)")
    for i, d in enumerate(durations):
        print(f"  Frame {i:3d}: {d:5d} ms")

    # Phase 5: Save with per-frame durations
    OUT_GIF.parent.mkdir(parents=True, exist_ok=True)
    unique_frames[0].save(
        OUT_GIF,
        save_all=True,
        append_images=unique_frames[1:],
        duration=durations,
        loop=0,
        optimize=False,
    )

    size_kb = OUT_GIF.stat().st_size / 1024
    total_ms = sum(durations)
    print(f"\nSaved {len(unique_frames)} frames, total {total_ms/1000:.1f}s → {size_kb:.0f} KB")

    # Verify
    result = Image.open(OUT_GIF)
    print(f"Verification: {result.n_frames} frames, {result.size[0]}×{result.size[1]}")


if __name__ == "__main__":
    main()
