# Profile Template Routing Map

Locked menu template assets for Codex routing. GLM-owned; Codex wires code routing separately.

## Handoff Status

- GLM: templates are final and locked. Do not edit HTML content without a new GLM commit.
- Codex: routing code not yet wired. Codex should map `establishment_profile` IDs below to the template files in `pipeline/outreach.py` and `pipeline/state_audit.py`.
- No live records should be promoted or made send-ready by this template work alone. Codex routing is required first.

## New Izakaya Profile Templates

| establishment_profile          | Template File                                              | Preview Render                                                | Priority | Volume |
|--------------------------------|------------------------------------------------------------|---------------------------------------------------------------|----------|--------|
| `izakaya_yakitori_kushiyaki`   | `assets/templates/izakaya_yakitori_kushiyaki_menu.html`    | `assets/templates/previews/izakaya_yakitori_kushiyaki_menu.png`  | high     | 44     |
| `izakaya_kushiage`             | `assets/templates/izakaya_kushiage_menu.html`              | `assets/templates/previews/izakaya_kushiage_menu.png`            | high     | 10     |
| `izakaya_seafood_sake_oden`    | `assets/templates/izakaya_seafood_sake_oden_menu.html`     | `assets/templates/previews/izakaya_seafood_sake_oden_menu.png`   | high     | 24     |
| `izakaya_tachinomi`            | `assets/templates/izakaya_tachinomi_menu.html`             | `assets/templates/previews/izakaya_tachinomi_menu.png`           | initial  | 7      |

## Existing Templates (unchanged)

| establishment_profile | Template File                                           |
|-----------------------|---------------------------------------------------------|
| `ramen`               | `assets/templates/ramen_food_menu.html`                  |
| `ramen_drinks`        | `assets/templates/ramen_drinks_menu.html`                |
| `izakaya_general`     | `assets/templates/izakaya_food_menu.html`                |
| `izakaya_drinks`      | `assets/templates/izakaya_drinks_menu.html`              |
| `izakaya_combined`    | `assets/templates/izakaya_food_drinks_menu.html`         |

## Template Design Contract

Every new template listed above meets these criteria:

- Exactly one `<html>`, `<body>`, `</body>`, `</html>` per file.
- `<body data-profile="{profile_id}">` matches the target profile ID exactly.
- Visual system: dark warm palette (`--bg: #0f0d0b`, `--surface: #1c1917`, `--accent: #c53d43`), Outfit + Shippori Mincho fonts, grain texture, radial warm glow.
- `data-slot` attributes on editable elements: `seal`, `seal-text`, `section-items`, `item`.
- A4 print styles and 760px mobile breakpoint included.
- Customer-facing footer note present: confirms sample is illustrative, states owner's confirmed items/photos are used in production, notes allergen and availability verification required.
- No prices, no fake restaurant claims, no real-shop claims.
- No mentions of AI, automation, scraping, internal tools, outreach, lead sourcing, or Codex.

## Preview Renders

All four previews generated via Playwright at 1200px viewport, full-page screenshot. Filenames follow the convention `assets/templates/previews/{profile_id}_menu.png`.
