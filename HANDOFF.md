# WebRefurbMenu Handoff

Updated: 2026-04-28

## Current State

- Branch: `main`
- Active execution plan: `PLAN.md`
- Active phase: `P3 - Fix Lead And Contact Reality`
- Phase status: in progress
- `P1` is complete and recorded in `PLAN.md`.
- `P2` is complete and recorded in `PLAN.md`.
- Current focus has moved to contact-route and establishment-profile hardening.

## What Landed

`P0` is complete.

Active `P1` work now in the tree:

- canonical production `menu_data` shape now includes split `food` and `drinks` panels
- production items carry source/provenance and approval metadata
- food/drinks render paths are separated instead of reusing one combined list
- stale template text is actively cleared instead of silently surviving in unused slots
- source-detected prices stay hidden until the business explicitly confirms them
- package validation now checks rendered parity, stale template text, wrong-panel bleed, placeholder translations, approval blockers, invalid price states, and leaked unconfirmed prices
- dashboard review shows operator checklist fields
- `MENU_DESIGN_LOOP.md` now defines the required rendered UI/UX loop for menu layout work

## Visual Direction

Browser-verified direction from the layout refinement pass:

- one-section menus can render into a single full-width food box
- empty drinks content can be removed from the combined preview when there are no drinks sections
- adaptive item-capacity logic follows layout mode instead of assuming the old fixed `8 items per box`
- one-section typography now scales dynamically based on item count
- single-section ramen menus now render as `RAMEN MENU` without a redundant `RAMEN` section heading
- ramen menus with sides/add-ons fold those supporting items into the lower part of the ramen panel instead of creating a separate competing box
- drinks pages now render as `DRINKS MENU` without a redundant `DRINKS` section heading
- empty panel sections are hidden safely
- `PLAN.md` now includes an evidence-backed `establishment_profile` requirement so the system can select ramen-only vs izakaya food/drinks outreach samples appropriately

Current sample-selection direction:

- small ramen shops should default to a simple `RAMEN MENU`
- ramen and sides/add-ons are the star
- drinks should only appear for ramen shops when evidence says they matter
- izakayas should generally include drinks by default
- the system must accurately recognise establishment type before choosing outreach sample/layout

Accepted menu-family constraints:

- same menu family
- same font family, line character, border style, stroke feel, and overall look
- no “new design”
- avoid duplicate page/section headings such as `RAMEN MENU` plus `RAMEN` or `DRINKS MENU` plus `DRINKS`
- typography and spacing must dynamically scale to avoid dead space
- sparse ramen menus should feel intentionally composed, not like a stretched four-box template

## Verified Today

- `.venv/bin/python -m pytest tests/test_custom_build.py -q` => `39 passed`
- `.venv/bin/python -m pytest tests/test_p0_baseline.py -q` => `4 passed`
- `.venv/bin/python -m pytest tests/test_qr.py -q` => `10 passed`
- `.venv/bin/python -m pytest tests/test_api.py -q` => `74 passed`
- `.venv/bin/python -m pytest tests/ -q` => `236 passed`
- `git diff --check` => passing

Fresh `P1` smoke verification completed from current code:

- rebuilt [p1-smoke](/Users/chrisparker/Desktop/WebRefurbMenu/state/builds/p1-smoke) from CLI instead of relying on the stale earlier artifact
- regenerated [p1-smoke menu data](/Users/chrisparker/Desktop/WebRefurbMenu/state/builds/p1-smoke/menu_data.json) now uses `detected_in_source` plus `pending_business_confirmation`, not the old `pending_owner_confirmation` drift
- Package 1 validation on the rebuilt smoke artifact now passes
- Package 2 review on the rebuilt smoke artifact blocks only for missing delivery contact details, which is the expected operator gate
- browser-rendered review checks were completed for Package 1 and Package 2 in the dashboard
- browser-rendered menu preview confirmed that the rebuilt smoke artifact shows zero customer-visible prices while still rendering the approved `RAMEN MENU`, folded `SIDES / ADD-ONS`, and `DRINKS MENU` layout

Additional price-state verification completed after that smoke rebuild:

- built [p1-confirmed-visible](/Users/chrisparker/Desktop/WebRefurbMenu/state/builds/p1-confirmed-visible) from the same current-schema payload with every price set to `confirmed_by_business` plus `customer_visible`
- built [p1-confirmed-hidden](/Users/chrisparker/Desktop/WebRefurbMenu/state/builds/p1-confirmed-hidden) with every price set to `confirmed_by_business` plus `intentionally_hidden`
- direct review payload check now shows `p1-confirmed-visible` as `price_count: 7 / source_price_count: 7`
- direct review payload check now shows `p1-confirmed-hidden` as `price_count: 0 / source_price_count: 7`
- browser-rendered preview for `p1-confirmed-visible` shows visible customer prices on ramen, sides, and drinks as intended
- browser-rendered preview for `p1-confirmed-hidden` keeps all confirmed prices hidden while preserving the same approved layout
- `get_package_review()` now derives the operator checklist from current `menu_data` plus current validation instead of trusting a stale stored `review_checklist`
- [job-viz](/Users/chrisparker/Desktop/WebRefurbMenu/state/builds/job-viz) has been rebuilt from the current `p1-smoke` schema so it no longer depends on the old flat `menu_data` shape

Rendered samples already checked during the layout pass:

- job file: [p1-single-section-layout.json](/Users/chrisparker/Desktop/WebRefurbMenu/state/jobs/p1-single-section-layout.json)
- ramen-only output dir: [p1-single-section-layout](/Users/chrisparker/Desktop/WebRefurbMenu/state/builds/p1-single-section-layout)
- ramen+sides output dir: [p1-two-section-layout](/Users/chrisparker/Desktop/WebRefurbMenu/state/builds/p1-two-section-layout)
- split food/drinks output dir: [p1-split-food-drinks-layout](/Users/chrisparker/Desktop/WebRefurbMenu/state/builds/p1-split-food-drinks-layout)

Direct file previews used because dashboard preview artifacts can go stale:

- [single ramen preview](/Users/chrisparker/Desktop/WebRefurbMenu/state/builds/p1-single-section-layout/restaurant_menu_print_master.html)
- [ramen sides preview](/Users/chrisparker/Desktop/WebRefurbMenu/state/builds/p1-two-section-layout/restaurant_menu_print_master.html)
- [split food drinks preview](/Users/chrisparker/Desktop/WebRefurbMenu/state/builds/p1-split-food-drinks-layout/restaurant_menu_print_master.html)

If the preview URL is not reachable in the next chat, restart the dashboard with:

- `.venv/bin/python -m uvicorn dashboard.app:app --host 127.0.0.1 --port 8001`

`P2` QR hardening is now complete:

- `create_qr_draft()` no longer falls back to reply-body parsing as a route into a QR review draft
- photo-only QR requests with no structured payload now return a persisted `needs_extraction` job instead of creating a reviewable QR draft
- no public draft HTML/QR files are written for that `needs_extraction` state
- QR/API regression coverage now includes the photo-only `needs_extraction` path
- `complete_qr_extraction()` now converts a `needs_extraction` QR job into a real reviewable draft once structured items exist
- structured QR extraction can now come from direct `items`, `menu_data`, pasted raw text, or extraction from stored menu photos
- dashboard QR review now shows an explicit `Needs extraction` state until a real draft exists, then transitions into the normal review flow
- browser-rendered verification confirmed the `Needs extraction -> Run Photo Extraction -> reviewable draft` modal flow
- browser-rendered verification confirmed the generated extracted draft page loads and shows review-only gaps instead of pretending it is publishable
- QR items now carry explicit owner-confirmation provenance for descriptions and ingredient/allergen content
- QR publish now blocks when description or ingredient/allergen content exists without recorded owner confirmation
- dashboard QR review now shows owner-confirmation counts plus a Package 3 promise block in the modal
- Package 3 promise is now defined in code and pricing docs: 12 months of hosting, one bundled update round in the first 30 days, basic support scope, and a renew-or-retire path after the term
- browser-rendered verification confirmed the updated QR review modal plus the English and Japanese pricing pages
- QR health now fails loudly when the live manifest, checksums, current version docs output, publish manifest, source data, or approved-package sign PDF/export is missing
- Package 3 is now positioned as a standalone `¥65,000` hosted service with one bundled 30-day update round; later updates move into paid update work while combined-package deals remain quote-only

## Next Step

Continue `P3 - Fix Lead And Contact Reality`:

1. add first-class `contacts` records so form, LINE, Instagram, phone, website, and walk-in routes are stored alongside email
2. preserve qualified no-email leads when another contact route exists and expose them as actionable in the dashboard
3. add evidence-backed `establishment_profile` classification before outreach asset selection
4. keep duplicate prevention and current send safety rules intact while widening the outreach-ready definition

## Execution Freeze

Until `P5` gate evidence is truly satisfied:

- do not approve real customer packages
- do not send real outreach
