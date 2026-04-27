# GLM Menu Template Package — browser-checked corrected version

This package fixes the issue where the direct SVG preview showed a large blank/dead area to the right in an in-app/browser viewer.

## What was fixed

The editable SVG templates now render responsively in a browser/app preview:
- direct SVG files fill the browser/app width
- no large right-side dead space in browser preview
- the actual artwork/layout/viewBox remains the approved 8.5 x 11 menu design
- PDFs are preserved as the correct print proofs

## Use these editable source files

- `food_menu_editable_vector.svg`
- `drinks_menu_editable_vector.svg`

These are the templates to give to GLM/the renderer as the editable source.

## Use these print proof files

- `food_menu_print_ready.pdf`
- `drinks_menu_print_ready.pdf`
- `restaurant_menu_print_ready_combined.pdf`

The PDFs are the final print proof/reference.

## Use these browser-check files

- `food_menu_browser_preview.html`
- `drinks_menu_browser_preview.html`
- `restaurant_menu_print_master.html`
- `browser_checked_previews/`

The `browser_checked_previews` folder contains screenshots rendered with Chromium from the actual SVG/HTML files in this package.

## GLM instruction

Do not redesign the menu. Do not change the borders, colors, spacing, fonts, section box positions, or layout system.

GLM should only extract/normalize menu content into JSON. The app/template renderer should inject the JSON text into the SVG or HTML template.

## Output rules

- Keep editable source as SVG.
- Output print-ready PDF when finalizing for print.
- Do not use PNG as editable source.
- If text is too long, wrap or reduce font size deterministically.
- Never allow overlap or clipping.


## Verified bilingual right-side Japanese update
This package adds verified Japanese item labels to the right side of each English item.

Rules applied:
- English remains primary.
- Japanese appears to the right of English on the same baseline.
- Japanese is smaller, lighter, and set to 65% opacity.
- Section boxes are widened slightly and centered to preserve the same spacing rhythm while allowing the bilingual line to fit.
- Titles, section names, page frame, color palette, and overall menu identity are preserved.
- Japanese labels use standard Japanese menu equivalents.
