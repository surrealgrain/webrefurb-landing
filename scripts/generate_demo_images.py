#!/usr/bin/env python3
"""Generate consistent AI food images for the _demo_prototype.html ramen menu.

Uses Pollinations.ai (free, no API key) powered by FLUX to create
ingredient-accurate food photos with consistent Japanese restaurant styling.
"""
from __future__ import annotations

import re
import sys
import time
import urllib.parse
import urllib.request
import io
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets" / "templates" / "_demo_images"
HTML_FILE = ROOT / "assets" / "templates" / "_demo_prototype.html"

TARGET_W, TARGET_H = 800, 450
DELAY_S = 12  # seconds between requests to avoid rate limiting
MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# Menu items — exact descriptions and ingredients from the HTML
# ---------------------------------------------------------------------------
MENU_ITEMS = [
    {
        "id": "tonkotsu_ramen",
        "name": "Tonkotsu Ramen",
        "alt": "Tonkotsu Ramen",
        "prompt": (
            "Professional Japanese restaurant food photography. "
            "A bowl of tonkotsu ramen from 45-degree angle. "
            "Rich milky white opaque pork bone broth, thin straight noodles, "
            "two slices of rolled chashu pork belly, one marinated soft-boiled egg "
            "cut in half showing bright orange yolk (ajitsuke tamago), "
            "fresh green onions, nori seaweed sheets sticking out, sesame seeds. "
            "Dark ceramic ramen bowl on a dark wooden restaurant table. "
            "Warm natural lighting, shallow depth of field. "
            "No people, no hands, no chopsticks, no text, no watermarks."
        ),
    },
    {
        "id": "spicy_miso_ramen",
        "name": "Spicy Miso Ramen",
        "alt": "Spicy Miso Ramen",
        "prompt": (
            "Professional Japanese restaurant food photography. "
            "A bowl of spicy miso ramen from 45-degree angle. "
            "Orange-red tinted miso broth with red chili oil droplets on surface, "
            "thick wavy noodles, seasoned ground pork scattered on top, "
            "sweet corn kernels, bean sprouts, a pat of butter, minced garlic. "
            "Dark ceramic ramen bowl on a dark wooden restaurant table. "
            "Warm natural lighting, shallow depth of field. "
            "No people, no hands, no chopsticks, no text, no watermarks."
        ),
    },
    {
        "id": "shoyu_ramen",
        "name": "Shoyu Ramen",
        "alt": "Shoyu Ramen",
        "prompt": (
            "Professional Japanese restaurant food photography. "
            "A bowl of shoyu ramen from 45-degree angle. "
            "CLEAR light brown transparent soy sauce broth (NOT cloudy, NOT milky, NOT white). "
            "Thin curly noodles, sliced roast chicken breast (NOT pork), "
            "menma bamboo shoots, nori seaweed sheets, chopped green onions. "
            "NO egg anywhere in this image. "
            "Dark ceramic ramen bowl on a dark wooden restaurant table. "
            "Warm natural lighting, shallow depth of field. "
            "No people, no hands, no chopsticks, no text, no watermarks."
        ),
    },
    {
        "id": "gyoza",
        "name": "Gyoza (6 pcs)",
        "alt": "Gyoza",
        "prompt": (
            "Professional Japanese restaurant food photography. "
            "Six pan-fried gyoza dumplings on a white plate from 45-degree angle. "
            "Crescent-shaped with golden crispy brown bottoms visible. "
            "Small dish of soy-vinegar dipping sauce with red chili oil drops beside the plate. "
            "Dark wooden restaurant table. "
            "Warm natural lighting, shallow depth of field. "
            "No people, no hands, no chopsticks, no text, no watermarks."
        ),
    },
    {
        "id": "chashu_rice_bowl",
        "name": "Chashu Rice Bowl",
        "alt": "Chashu Rice Bowl",
        "prompt": (
            "Professional Japanese restaurant food photography. "
            "A Japanese rice bowl (donburi) from 45-degree angle. "
            "Steamed white rice topped with thick slices of braised chashu pork belly "
            "fanned across the top, chashu sauce drizzle, sliced green onions, sesame seeds. "
            "Ceramic bowl on a dark wooden restaurant table. "
            "Warm natural lighting, shallow depth of field. "
            "No people, no hands, no chopsticks, no text, no watermarks."
        ),
    },
    {
        "id": "edamame",
        "name": "Edamame",
        "alt": "Edamame",
        "prompt": (
            "Professional Japanese restaurant food photography. "
            "Steamed edamame pods in a small ceramic bowl from overhead angle. "
            "Bright green edamame pods with coarse salt sprinkled on top. "
            "Clean minimalist Japanese presentation on a dark wooden table. "
            "Warm natural lighting. "
            "No people, no hands, no chopsticks, no text, no watermarks."
        ),
    },
    {
        "id": "draft_beer",
        "name": "Draft Beer (Asahi)",
        "alt": "Draft Beer",
        "prompt": (
            "Professional Japanese restaurant food photography. "
            "A tall glass of golden draft beer with thick white foam head. "
            "Condensation droplets on the glass. "
            "Dark neutral background, Japanese izakaya atmosphere. "
            "Warm natural lighting, shallow depth of field. "
            "No people, no hands, no text, no watermarks."
        ),
    },
    {
        "id": "whisky_highball",
        "name": "Whisky Highball",
        "alt": "Highball",
        "prompt": (
            "Professional Japanese restaurant food photography. "
            "A tall highball glass with light amber whisky and sparkling water over ice cubes. "
            "Bubbles rising in the glass. No garnish. "
            "Clean dark background, Japanese bar style. "
            "Warm natural lighting, shallow depth of field. "
            "No people, no hands, no text, no watermarks."
        ),
    },
    {
        "id": "iced_green_tea",
        "name": "Iced Green Tea",
        "alt": "Green Tea",
        "prompt": (
            "Professional Japanese restaurant food photography. "
            "A tall glass of iced green tea, pale green color, with ice cubes. "
            "Condensation droplets on the glass. Clean refreshing look. "
            "Dark neutral background. "
            "Warm natural lighting, shallow depth of field. "
            "No people, no hands, no text, no watermarks."
        ),
    },
    {
        "id": "coca_cola",
        "name": "Coca Cola",
        "alt": "Coca Cola",
        "prompt": (
            "Professional Japanese restaurant food photography. "
            "A classic glass Coca Cola bottle with a glass of Coca Cola poured with ice. "
            "Dark cola color, condensation on the glass. "
            "Simple clean presentation on a dark wooden table. "
            "Warm natural lighting. "
            "No people, no hands, no text, no watermarks."
        ),
    },
]


def generate_image_pollinations(item: dict, seed: int = 42) -> Image.Image | None:
    """Generate a food image via Pollinations.ai (FLUX model, free, no API key)."""
    prompt = item["prompt"]
    encoded = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={TARGET_W}&height={TARGET_H}&nologo=true&seed={seed}"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=90).read()
            img = Image.open(io.BytesIO(data)).convert("RGB")
            if img.size[0] < 100 or img.size[1] < 100:
                raise ValueError(f"Image too small: {img.size}")
            return img
        except Exception as exc:
            print(f"    Attempt {attempt}/{MAX_RETRIES} failed: {exc}")
            if attempt < MAX_RETRIES:
                wait = DELAY_S * attempt
                print(f"    Retrying in {wait}s...")
                time.sleep(wait)
    return None


def update_html(image_map: dict[str, str]) -> None:
    """Replace Unsplash URLs in the HTML with local image paths."""
    html = HTML_FILE.read_text(encoding="utf-8")
    updated = 0

    for item in MENU_ITEMS:
        if item["id"] not in image_map:
            continue
        local_path = image_map[item["id"]]
        old_pattern = f'alt="{item["alt"]}"'
        if old_pattern not in html:
            print(f"  WARNING: Could not find alt='{item['alt']}' in HTML")
            continue

        idx = html.index(old_pattern)
        tag_start = html.rfind("<img", 0, idx)
        tag_end = html.index(">", idx) + 1
        old_tag = html[tag_start:tag_end]

        new_tag = re.sub(
            r'src="[^"]*"',
            f'src="{local_path}"',
            old_tag,
        )
        html = html[:tag_start] + new_tag + html[tag_end:]
        updated += 1
        print(f"  Updated: {item['name']} -> {local_path}")

    HTML_FILE.write_text(html, encoding="utf-8")
    print(f"\nUpdated {updated} image references in HTML")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    image_map: dict[str, str] = {}

    for i, item in enumerate(MENU_ITEMS):
        out_path = OUT_DIR / f"{item['id']}.jpg"

        if out_path.exists():
            print(f"  SKIP (exists): {item['name']}")
            image_map[item["id"]] = f"_demo_images/{item['id']}.jpg"
            continue

        print(f"  [{i+1}/{len(MENU_ITEMS)}] Generating: {item['name']}...")
        img = generate_image_pollinations(item, seed=42)
        if img is None:
            print(f"  FAILED: {item['name']}")
            continue

        # Resize to exact target dimensions
        img = img.resize((TARGET_W, TARGET_H), Image.LANCZOS)
        img.save(out_path, "JPEG", quality=90)
        size_kb = out_path.stat().st_size / 1024
        print(f"  Saved: {out_path.name} ({size_kb:.0f} KB, {img.size})")

        image_map[item["id"]] = f"_demo_images/{item['id']}.jpg"

        if i < len(MENU_ITEMS) - 1:
            print(f"  Waiting {DELAY_S}s to avoid rate limit...")
            time.sleep(DELAY_S)

    print(f"\n{'='*50}")
    print(f"Generated {len(image_map)}/{len(MENU_ITEMS)} images")

    if image_map:
        update_html(image_map)


if __name__ == "__main__":
    main()
