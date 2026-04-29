# WebRefurbMenu Handoff

Updated: 2026-04-29 (Codex)

## Current State

- Branch: `main`
- Active execution plan: `PLAN.md`
- Active phase: `P7 - Controlled Launch`
- Phase status: blocked pending explicit real-launch authorization and first-batch lead selection
- Working tree: **dirty** with P5/P6 implementation, rehearsal artifacts, and plan/checklist updates
- `P0` through `P6` complete and recorded in `PLAN.md`.
- Current focus: select 5 to 10 high-confidence independent ramen/izakaya shops for P7, then run the first controlled batch slowly. No real outreach has been sent.

## Codex Session — P5/P6 Completion

### What was done

- Completed paid operations workflow for quotes, invoice-ready data, payment tracking, intake, owner approval, delivery state, custom quote triggers, and privacy/data-retention acceptance.
- Added quote markdown and invoice JSON artifacts under `state/orders/artifacts/<order_id>/`.
- Added dashboard APIs for order creation, quote sent, payment pending, payment confirmation, intake, owner review, owner approval, delivery, artifact inspection, and build-to-order linking.
- Tightened final export blocking so customer ZIP approval requires quote, confirmed payment, complete intake, owner approval fields/checksums, and privacy note acceptance.
- Added paid-ops tests in `tests/test_paid_ops.py`.
- Ran sample-only P6 rehearsals for all three packages. Final ZIPs:
  - `state/final_exports/p6-package1/p6-package1-package_1_remote_30k.zip`
  - `state/final_exports/p6-package2/p6-package2-package_2_printed_delivered_45k.zip`
  - `state/final_exports/qr-849bf3ed/qr-849bf3ed-package_3_qr_menu_65k.zip`
- Wrote rehearsal report: `state/p6_rehearsal/P6_REHEARSAL_REPORT.json`.
- Backed up state after rehearsal: `state/backups/webrefurb-state-20260428T230746+0000.zip`.

### Verification

- `.venv/bin/python -m py_compile pipeline/quote.py pipeline/models.py dashboard/app.py pipeline/package_export.py` passed.
- `.venv/bin/python -m pytest tests/ -q` => `309 passed`.
- Dashboard visual inspection on `http://127.0.0.1:8001` covered Leads, Builds, and QR Menus.

## GLM Session — v4c Pipeline Migration

### What was done
Migrated the entire production pipeline from old cream SVG templates to v4c dark HTML templates. 10 files changed, 673 insertions, 722 deletions. Commit: `8cd0885`.

### Files changed and what they do

| File | Change |
|---|---|
| `pipeline/constants.py` | Template paths now point to `assets/templates/*.html` instead of old SVG/cream paths |
| `pipeline/render.py` | Added v3 regex for v4c HTML sections (`<div class="section-header"><span class="section-title">`), added `_build_v4c_items_html()` for bilingual item rendering, added `_replace_panel_title()` |
| `pipeline/populate.py` | Added `populate_menu_html()` — handles food/drinks split, flat sections, drinks-panel removal, seal text replacement |
| `pipeline/export.py` | `build_custom_package()` now selects ramen vs izakaya template based on `menu_type`, generates A5 PDFs via `html_to_pdf()` with `device_scale_factor=2` and `prefer_css_page_size=True`. Removed SVG pipeline functions kept only for backward compat. |
| `pipeline/package_export.py` | Added `_html_text_report()` (parses v4c HTML for validation), `TEMPLATE_PLACEHOLDER_ITEMS` (loaded from 4 v4c templates at module init), fixed `_write_package2_print_pack()` to use `food_menu.html` not old `food_menu_browser_preview.html` |
| `pipeline/email_templates.py` | Removed "WebRefurbの" from contact form body |
| `pipeline/outreach.py` | Removed "from WebRefurb" from English contact form body |
| `dashboard/app.py` | Email send flow: v4c template selection by profile (ramen/izakaya), CID inline JPEGs only (no PDF attachments), removed WEBREFURB from test email body |
| `tests/test_api.py` | Updated 3 tests for v4c file structure |
| `tests/test_custom_build.py` | Rewrote `_write_package_output` helper, added `_write_validation_output` helper, converted all SVG tests to HTML, fixed mock signatures for new kwargs |

### Test results
- **295 passed, 2 pre-existing website failures** (pricing.html link + pricing content — unrelated to v4c)
- All pipeline, API, and custom build tests pass

### Key design decisions
- v4c HTML templates use `data-section` attributes to match sections (e.g. `data-section="ramen"`, `data-section="sides-add-ons"`)
- `_replace_section()` tries v3 (v4c HTML) first, then v2, then v1 — backward compatible
- `device_scale_factor=2` for print quality; viewport `495x700`; A5 from CSS `@page { size: 148mm 210mm }`
- Email sends CID inline JPEGs only — no file attachments (user feedback: "attachment screams scam")
- WEBREFURB removed from all email body text (headers/footers sufficient)

### Known gaps / things to check in audit
1. `_normalise_build_package()` in `package_export.py` does NOT recognize Package 3 key `package_3_qr_menu_65k` — will fail on Package 3 builds
2. `TEMPLATE_PLACEHOLDER_ITEMS` loaded at module init from template files — if templates missing, set is empty (silent failure)
3. Outreach sample PDFs in `state/builds/` still reference old cream designs — need regeneration
4. `_svg_text_report()`, `_allowed_static_svg_text()`, SVG populate functions in `populate.py` may be dead code now
5. `_ensure_menu_jpeg()` / `_ensure_machine_jpeg()` in dashboard may cache stale JPEGs from old templates — cache invalidation needed
6. No test coverage for izakaya template population (all tests use ramen templates)
7. Preview endpoint in `dashboard/app.py` may still look for old file names like `restaurant_menu_print_master.html`
8. 2 website tests fail: `test_homepage_titles_and_language_links` expects `href="/pricing.html"` not found, `test_homepages_include_pricing_content` expects `30,000円` not found in Japanese page

## Previous Session History

- P0 complete, P1 complete, P2 complete, P3 complete
- Outreach rewrite: 5 situation-based templates replacing 8 per-profile variants
- Reply translation system with 5-pass Japanese verification
- QR code sign template (A6)
- Japanese website copy audit (13 fixes across index.html + pricing.html)
- Business name hardening, contact routes, QR hardening
- See git log for full history

## Execution Freeze

P5 and P6 gates are satisfied for sample data. Until P7 is explicitly started:
- do not send real outreach
- do not contact real shops through forms, LINE, Instagram, phone, or walk-in
- do not approve real customer packages without a real paid order record and owner approval evidence
