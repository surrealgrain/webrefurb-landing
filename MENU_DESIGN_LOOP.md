# Menu Design Loop

Created: 2026-04-28

This is the required UI/UX refinement loop for customer-facing menu layout work.

Use this loop for:

- menu SVG layout changes
- menu HTML preview changes
- one-section, two-section, and sparse-layout handling
- typography, spacing, alignment, density, and empty-space decisions

SeedStyle baseline:

- `ss-review`
- `ss-audit`
- `baseline-ui`

These skills are the baseline guardrails for every menu UI pass. Do not trust code inspection alone.

## Loop

1. Render the actual menu in the browser.
2. Audit the rendered result against the checklist below.
3. Identify the most obvious visual failure first.
4. Change layout, type scale, spacing, or composition.
5. Re-render the exact scenario that exposed the problem.
6. Repeat until the layout passes the checklist.

Do not sign off based only on tests, SVG text output, or implementation logic.
Do not guess from code when deciding whether a layout is good. Visual confirmation is mandatory on every pass.

## Visual Checklist

The layout is acceptable only when all of these are true:

- It still feels like the same menu family as the approved template.
- Borders, line weights, colors, and type families remain consistent with the current design.
- Empty space feels intentional, not leftover.
- Content density matches the amount of content on the page.
- A one-section menu reads like a designed featured page, not a stretched four-box template.
- A sparse menu does not leave most of the usable panel visually dead.
- Section title, item labels, and Japanese text feel proportionate to each other.
- English item text is readable at arm's-length print scale.
- Japanese support text is visually subordinate but still readable.
- No empty second page appears when the restaurant has no content for it.

## Typography Targets

Use these as the house standard for this menu system.

One-section featured layout:

- `1-3` items: English item text about `19-20pt`, Japanese about `14-15pt`, section title about `25-26pt`
- `4-5` items: English item text about `17-18pt`, Japanese about `13-14pt`, section title about `23-25pt`
- `6-7` items: English item text about `16-17pt`, Japanese about `12-13pt`, section title about `22-23pt`
- `8-10` items: English item text about `14-15pt`, Japanese about `11-12pt`, section title about `21-22pt`
- `11+` items: reduce only as needed to preserve readability and balance

Multi-section layouts:

- Keep the current template family as the baseline
- Increase only when the page becomes too sparse
- Do not introduce a new type system

## Spacing Targets

- Sparse featured layouts should use visibly larger line rhythm than dense multi-box layouts.
- Vertical placement should be optically centered for sparse one-section pages.
- Line spacing should scale with item size instead of staying fixed.
- Boxes may change in count and placement, but not in stylistic character.

## Failure Examples

These count as failures and require another pass:

- giant box with a tiny top-stacked list
- one section filling only the top quarter of the usable area
- empty drinks page on a ramen-only sample
- type that technically fits but feels under-scaled
- whitespace that looks accidental rather than composed

## Verification Requirement

For every meaningful menu-layout change:

- run targeted tests
- regenerate a representative sample build
- visually inspect the result in the in-app browser

Current mandatory samples:

- one-section ramen-only menu
- two-section food menu
- split food/drinks menu
