# Profile Template Routing Map

Maps `establishment_profile` IDs to locked menu template files.

## New Izakaya Profile Templates

| establishment_profile          | Template File                                    | Priority | Volume |
|--------------------------------|--------------------------------------------------|----------|--------|
| `izakaya_yakitori_kushiyaki`   | `assets/templates/izakaya_yakitori_kushiyaki_menu.html` | high     | 44     |
| `izakaya_kushiage`             | `assets/templates/izakaya_kushiage_menu.html`           | high     | 10     |
| `izakaya_seafood_sake_oden`    | `assets/templates/izakaya_seafood_sake_oden_menu.html`  | high     | 24     |
| `izakaya_tachinomi`            | `assets/templates/izakaya_tachinomi_menu.html`          | initial  | 7      |

## Existing Templates (unchanged)

| establishment_profile | Template File                                    |
|-----------------------|--------------------------------------------------|
| `ramen`               | `assets/templates/ramen_food_menu.html`           |
| `ramen_drinks`        | `assets/templates/ramen_drinks_menu.html`         |
| `izakaya_general`     | `assets/templates/izakaya_food_menu.html`         |
| `izakaya_drinks`      | `assets/templates/izakaya_drinks_menu.html`       |
| `izakaya_combined`    | `assets/templates/izakaya_food_drinks_menu.html`  |

## Routing Notes

- All new templates use the same dark warm palette (`--bg: #0f0d0b`, `--surface: #1c1917`, `--accent: #c53d43`), Outfit + Shippori Mincho fonts, and grain texture as the existing set.
- Each template has `data-profile="{profile_id}"` on `<body>` and `data-slot` attributes on editable elements for content injection.
- Content slots: `seal`, `seal-text`, `section-items`, `item`.
- All include A4 print styles and 760px mobile breakpoint.
- Customer-facing footer note is present in all templates.
