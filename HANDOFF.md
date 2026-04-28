# WebRefurbMenu Handoff

Updated: 2026-04-28

## Current State

- Branch: `main`
- Active execution plan: `PLAN.md`
- Active phase: `P4 - Make Outreach Convert`
- Phase status: in progress
- Working tree is dirty
- `P1` is complete and recorded in `PLAN.md`.
- `P2` is complete and recorded in `PLAN.md`.
- `P3` is complete and recorded in `PLAN.md`.
- Current focus has moved to outreach conversion work, starting with the machine-only / ticket-machine path.

## Working Tree Snapshot

Uncommitted changes present right now:

- `PLAN.md`: P3 completion recorded; P4 machine-only outreach progress recorded
- `pipeline/record.py`: contact metadata normalization now persists `confidence`, `discovered_at`, `status`, and `map_url`
- `pipeline/search.py`: discovered contacts now carry metadata and include first-class `map_url` contact support
- `pipeline/email_templates.py`: added dedicated machine-only outreach subject/body copy
- `pipeline/outreach.py`: machine-only outreach now builds a real draft and attaches the ticket-machine sample instead of failing
- `pipeline/outreach.py`: outreach copy and asset selection are now profile-aware for ramen-only, ramen-with-sides, ramen-with-drinks, ramen-ticket-machine, and izakaya drink/course-heavy leads
- `pipeline/record.py`: verified business names now promote into a locked authoritative field so downstream outreach/reply flows reuse the confirmed restaurant name instead of later drift
- `pipeline/constants.py`: profile-specific outreach sample PDF paths now point at the browser-verified ramen and food/drinks sample artifacts
- `dashboard/app.py`: outreach preview/send flow now supports machine-only drafts and menu-image-less preview sends
- `dashboard/templates/index.html`: preview modal no longer hard-blocks machine-only leads and now shows profile-aware sample-strategy labels/notes
- `tests/test_api.py`, `tests/test_outreach.py`, `tests/test_safety.py`, `tests/test_search.py`: updated regression coverage for contact metadata, machine-only outreach, and locked business-name precedence
- `docs/index.html`: homepage hero heading `line-height` changed from `0.9` to `1`
- `docs/ja/index.html`: Japanese homepage hero heading `line-height` changed from `0.9` to `1`
- untracked generated QR draft artifacts exist under `docs/menus/_drafts/`
- untracked `assets/templates_v3_original/` directory exists

Notes:

- the tracked homepage HTML edits still look like a small visual refinement, not product-logic work
- the `docs/menus/_drafts/` files appear to be generated preview/output artifacts, not source files
- `docs/menus/` is currently about `188K`
- decide before committing whether those draft QR artifacts belong in version control or should stay ignored/generated-only
- the new product-logic edits are concentrated in outreach/contact files, not the docs homepage files
- the machine-only browser verification used a temporary lead fixture that has already been removed; no verification-only lead record remains in `state/leads`

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

## P3 Complete

Lead/contact-route hardening now in the tree:

- first-class normalized `contacts` support exists for email, contact form, LINE, Instagram, phone, walk-in, map URL, and website routes
- contacts now persist `source_url`, `confidence`, `discovered_at`, and `status`
- no-email leads with another supported route now stay actionable in the dashboard instead of being dropped
- lead cards now show the primary saved contact route
- outreach draft modal now shows the saved contact-route summary and disables dashboard email sending for non-email routes instead of pretending they are sendable
- dashboard manual outreach copy + `mark contacted` flow now persists route-specific statuses for non-email channels
- `QualificationResult` and persisted leads now carry `establishment_profile` plus evidence
- dashboard establishment-profile override flow is live before outreach asset selection

Business-name hardening now in the tree:

- new helper file [pipeline/business_name.py](/Users/chrisparker/Desktop/WebRefurbMenu/pipeline/business_name.py) sanitizes suspicious names and compares cross-source name candidates
- outreach drafting now blocks if the stored business name looks contact-derived or otherwise unsafe for customer-facing copy
- search now resolves and verifies business names before persisting a lead
- current rule is: require two-source agreement on the business name
- preferred combination is `Tabelog + Google`
- acceptable fallback is `Google + official site` when Tabelog is unavailable
- this was intentionally relaxed from a too-strict `Tabelog required` version after browser/test verification
- once a name is verified, `locked_business_name` is now the authoritative downstream value for outreach/reply usage even if a later mutable `business_name` field drifts

## Current P4 Progress

Machine-only / ticket-machine outreach hardening now in the tree:

- `machine_only` leads no longer fail immediately in outreach preview
- machine-only outreach now uses dedicated subject/body copy focused on ticket machines and ordering guidance
- machine-only outreach now attaches the ticket-machine sample PDF instead of returning no assets
- outreach preview/send flow now supports drafts with `include_menu_image = false` and `include_machine_image = true`
- dashboard preview modal no longer swaps machine-only leads into the old “not implemented yet” blocker state
- browser-rendered verification confirmed a machine-only lead now opens a normal outreach draft modal with ticket-machine copy and attachment

Profile-aware outreach conversion work now in the tree:

- e-mail plus manual-channel drafts are now segmented by `establishment_profile`, not only by menu/machine evidence
- ramen-only leads now use ramen-focused copy plus a one-page ramen sample
- ramen-with-sides and ramen-with-drinks leads now use matching copy/sample language instead of the generic menu pitch
- drink-heavy and course-heavy izakaya leads now use drinks/course-focused copy and photo requests
- outreach asset selection now chooses from the browser-verified ramen-only, ramen+sides, ramen+drinks, and split food/drinks sample PDFs instead of always defaulting to one generic menu PDF
- the preview modal now shows operator-facing asset labels like `Ramen Menu Sample (One Page)` and `Drink-Forward Izakaya Sample`
- the preview modal now shows a sample-strategy rationale block so operators can see why the chosen proof-of-value matches the lead profile

## Verified Today

- `.venv/bin/python -m pytest tests/test_custom_build.py -q` => `39 passed`
- `.venv/bin/python -m pytest tests/test_p0_baseline.py -q` => `4 passed`
- `.venv/bin/python -m pytest tests/test_qr.py -q` => `10 passed`
- `.venv/bin/python -m pytest tests/test_api.py -q` => `74 passed`
- `.venv/bin/python -m pytest tests/ -q` => `236 passed`
- `git diff --check` => passing

Fresh `P3` verification completed from the current code:

- `.venv/bin/python -m pytest tests/test_api.py tests/test_search.py tests/test_search_scope.py -q` => `97 passed`
- `.venv/bin/python -m py_compile pipeline/business_name.py pipeline/search.py dashboard/app.py` => passing
- browser-rendered dashboard verification completed after the contact-route changes
- browser-rendered outreach modal verification confirmed:
  - non-email leads now show saved contact-route guidance and disable dashboard email sending
  - email leads still prefill the recipient field and keep the normal send button flow
- browser-rendered name-verification verification confirmed:
  - a `Google + official site` lead can still open a draft
  - a `Tabelog + Google` lead can open a draft with the corrected restaurant name instead of contact-route text

Fresh contact-metadata verification completed after that:

- `.venv/bin/python -m pytest tests/test_search.py -q` => `10 passed`
- `.venv/bin/python -m pytest tests/test_api.py -q` => `88 passed`
- contact normalization now preserves metadata for new records while safely backfilling sane defaults for legacy reads

Fresh `P4` machine-only verification completed from the current code:

- `.venv/bin/python -m pytest tests/test_outreach.py tests/test_api.py tests/test_safety.py -q` => `142 passed`
- `.venv/bin/python -m py_compile pipeline/outreach.py dashboard/app.py` => passing
- browser-rendered dashboard verification on `http://127.0.0.1:8001` confirmed:
  - a machine-only lead opens a normal outreach draft modal
  - the modal shows machine-only subject/copy instead of the previous blocker warning
  - the included-file panel shows the ticket-machine guide attachment
  - the preview flow works with no menu image and a machine image only

Fresh profile-aware outreach verification completed after that:

- `.venv/bin/python -m pytest tests/test_outreach.py tests/test_api.py tests/test_safety.py -q` => `163 passed`
- `.venv/bin/python -m py_compile pipeline/outreach.py dashboard/app.py` => passing
- `git diff --check` => passing
- browser-rendered dashboard verification on `http://127.0.0.1:8001` confirmed:
  - a ramen-only lead shows `Ramen Menu Sample (One Page)` plus a ramen-only sample-strategy note
  - the ramen-only Japanese/English draft copy is explicitly ramen-focused instead of generic
  - a drink-heavy izakaya lead shows `Drink-Forward Izakaya Sample` plus a drink/nomihodai-focused sample-strategy note
  - the izakaya Japanese/English draft copy now requests food/drink/nomihodai materials instead of the generic menu-only ask

Full-suite note:

- the last full-suite run still failed in `tests/test_website.py`
- that failure appears unrelated to the outreach/contact work and comes from a pre-existing mismatch between homepage assertions and the current `docs/index.html` / `docs/ja/index.html` contents
- the homepage `line-height: 1` tweak is not the cause of that failure; even `HEAD` lacks the pricing-link/pricing-copy assertions those tests expect

Fresh business-name lock verification completed after that:

- `.venv/bin/python -m pytest tests/test_api.py tests/test_safety.py tests/test_outreach.py -q` => `156 passed`
- `.venv/bin/python -m py_compile pipeline/record.py dashboard/app.py pipeline/outreach.py` => passing
- browser-rendered dashboard verification confirmed a lead with a suspicious mutable `business_name` but a valid `locked_business_name` still renders and drafts with the locked restaurant name instead of the drifted value

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

Continue `P4 - Make Outreach Convert`:

1. decide whether the new two-source business-name rule should surface explicit source details in the dashboard/operator UI
2. decide whether `business_name_verified_by` and related provenance should be backfilled/migrated for existing leads in `state/leads`
3. generate a more truly shop-specific partial outreach preview from public evidence instead of relying mainly on profile-matched sample families
4. reduce reliance on generic PDF attachments as the primary conversion asset; keep them secondary where helpful
5. if outreach sample selection needs stronger source normalization later, extend the search/source pipeline beyond homepage + Serper/Tabelog heuristics

Immediate practical follow-up from the current tree:

1. either keep, revert, or browser-verify the `line-height: 1` homepage tweak in both language variants before it gets folded into unrelated phase work
2. decide whether the QR draft files in `docs/menus/_drafts/` are intentional fixtures, temporary preview output, or cleanup candidates
3. decide whether `assets/templates_v3_original/` is an intentional checked-in reference set or cleanup/ignore candidate
4. if the next session touches name verification again, keep the current intent: `Tabelog + Google` is preferred as a double-check, but Tabelog is not a hard requirement when `Google + official site` already agrees

## Execution Freeze

Until `P5` gate evidence is truly satisfied:

- do not approve real customer packages
- do not send real outreach
