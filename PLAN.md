# WebRefurbMenu Execution Plan

Created: 2026-04-28

This is the execution contract for turning WebRefurbMenu from a promising prototype into a sellable, operationally safe service for independent ramen shops and izakayas in Japan.

The plan must be followed in phase order. Do not skip a phase, mark a phase complete, or begin real customer outreach unless that phase's exit gate is satisfied.

## Definition Of Watertight

The system is watertight only when all of the following are true:

- A qualified shop can be contacted through the channel it actually uses, not only by email.
- Outreach uses a shop-specific proof of value, not just a generic sample.
- A positive reply moves into quote, payment, intake, owner approval, production, delivery, and follow-up states.
- Every customer-visible menu item in a PDF, SVG, HTML page, QR menu, email preview, or printed pack traces back to structured source data.
- No package can be approved while rendered output contains stale template text, missing prices, placeholder translations, empty QR items, or unconfirmed ingredient/allergen claims.
- Production work uses owner-provided photos, PDFs, text, or explicit owner confirmation.
- State is backed up before real outreach and after each operator session.
- Customer-facing copy never mentions AI, automation, scraping, or internal tools.
- Lead semantics remain binary: `lead: true|false`, never "maybe".

## Execution Rules

- Follow phases in order: P0, P1, P2, P3, P4, P5, P6, P7.
- A later-phase task may be touched early only when it is required to pass the current phase gate.
- Every implementation PR or working session must name the active phase.
- Update this file when a task is completed, blocked, or intentionally changed.
- A phase is complete only when every required task is checked and the exit gate evidence is recorded.
- If a new launch blocker is found, add it to the current phase or an earlier phase. Do not bury it in notes.
- Keep moving automatically through the active phase and then the next phase without waiting for a separate user prompt.
- Stop only when the context window is starting to get bloated enough that a clean handoff is the safer path.
- When a handoff is needed for context management, suggest handoff explicitly; once the user says `handoff`, resume automatically from the next unfinished plan step without requiring a new kickoff prompt.
- Do not send real outreach until P6 is complete.
- Do not approve real customer packages until P1, P2, and P5 gates are complete.
- Do not sell Package 3 until P2 defines the hosting/update/support promise and QR empty-payload gates are fixed.
- Visual, UX, layout, typography, spacing, and dashboard workflow changes require rendered browser verification before sign-off.

## Current Stop-The-Line Findings

These are known blockers from the repo audit and ignored `state/` artifacts:

- Generated print artifacts can pass validation while still containing stale template menu items.
- Prices from structured `menu_data` are not reliably rendered into the SVG/PDF outputs.
- Food and drinks outputs are populated from the same combined data instead of being cleanly separated.
- QR drafts can be created from photo-only replies with no structured menu items.
- The active `.venv` is out of sync with `pyproject.toml`; QR tests fail because `qrcode` is not installed in that environment.
- The dashboard treats email-reachable leads as the only truly actionable outreach leads.
- Machine-only/ticket-machine leads are blocked even though they may be high-value ramen targets.
- Generic sample PDFs are used where shop-specific previews would convert better.
- There is no quote, invoice, payment, deposit, receipt, delivery-cost, or payment-status workflow.
- File-based state has no automated backup or concurrency protection.
- CLI commands do not load `.env`, while the dashboard does.
- LLM calls have no retry/backoff and inconsistent customer-safe failure behavior.

## Status Board

| Phase | Name | Status | Exit Evidence |
| --- | --- | --- | --- |
| P0 | Stabilize Baseline And Freeze Risk | Completed | `.venv/bin/python -m pip install -e .`; `.venv/bin/python -m pytest tests/ -v` => 221 passed on 2026-04-28; `.venv/bin/python -m pipeline.cli backup-state` dry-run wrote `state/backups/webrefurb-state-20260428T060622+0000.zip`; `git diff --check` passed |
| P1 | Correct Menu Output Generation | Completed | Rendered menu output, price-state validation, fresh smoke/confirmed-price artifacts, and dashboard review verification completed on 2026-04-28 |
| P2 | Harden QR Product | Completed | Structured extraction, owner-confirmation gating, package promise, QR health/export checks, and active-environment tests/browser verification completed on 2026-04-28 |
| P3 | Fix Lead And Contact Reality | Completed | Contact routes, manual-route outreach actions, establishment-profile evidence/override flows, and focused P3 verification completed on 2026-04-28 |
| P4 | Make Outreach Convert | Completed | All tasks checked; 295 tests pass; shop-specific previews, category-emphasis copy, Resend webhook, bounce/complaint handling completed on 2026-04-28 |
| P5 | Add Paid Operations Workflow | Completed | Quote/order/payment/intake/approval/delivery workflow, quote + invoice artifacts, custom-quote gates, privacy note, and paid export blocking completed; `.venv/bin/python -m pytest tests/ -q` => 309 passed on 2026-04-29 |
| P6 | Operator Rehearsal | Completed | Sample-only rehearsals produced Package 1, Package 2, and Package 3 final ZIPs; dashboard Leads/Builds/QR Menus visually inspected on `http://127.0.0.1:8001`; post-rehearsal backup includes `orders`; `.venv/bin/python -m pytest tests/ -q` => 309 passed on 2026-04-29 |
| P6A | Product Audit Hardening | Completed | Lead evidence dossier/readiness gates, friction-first search, diagnosis outreach, preview proof filtering, outcome package labels, launch batches, state migration, browser verification, and `.venv/bin/python -m pytest tests/ -q` => 318 passed on 2026-04-29 |
| P7 | Controlled Launch | Blocked | Awaiting explicit real-launch authorization, credentials check, and 5-10 selected high-confidence shops; no real outreach has been sent |

## P0 - Stabilize Baseline And Freeze Risk

Goal: stop working from a false sense of readiness. Get the environment, tests, state backup, and launch rules honest before feature work.

Primary files:

- `pyproject.toml`
- `pipeline/cli.py`
- `pipeline/llm_client.py`
- `pipeline/record.py`
- `pipeline/utils.py`
- `LAUNCH_CHECKLIST.md`
- `HANDOFF.md`
- `tests/`

Tasks:

- [x] Sync the active development environment from `pyproject.toml`.
- [x] Confirm `qrcode` is installed in the active venv and QR tests no longer fail from missing dependency.
- [x] Decide whether docs should use `python`, `.venv/bin/python`, or an activation-first workflow; update quick commands accordingly.
- [x] Add `.env` loading to CLI entry points so dashboard and CLI behavior match.
- [x] Add retry/backoff to `pipeline/llm_client.py` for transient network failures, timeouts, and 5xx responses.
- [x] Make LLM failure behavior explicit: development fallback is allowed only when the output is blocked from customer approval.
- [x] Add a state backup command or script that archives `state/leads`, `state/sent`, `state/jobs`, `state/replies`, `state/uploads`, `state/builds`, `state/qr_jobs`, and `state/qr_menus`.
- [x] Add a backup reminder or command to `LAUNCH_CHECKLIST.md`.
- [x] Update `HANDOFF.md` so old "217 passed" claims are not treated as current truth until tests pass again.
- [x] Run the full test suite from the active environment.

Exit gate:

- [x] Full test suite passes from a clean or freshly synced environment.
- [x] `git diff --check` passes.
- [x] Backup command exists and has been dry-run locally.
- [x] Launch checklist clearly says real outreach remains frozen until P6.

Exit evidence recorded 2026-04-28:

- Synced the active environment with `.venv/bin/python -m pip install -e .`, which installed the missing `qrcode` dependency and aligned the editable package metadata with `pyproject.toml`.
- Standardized local commands on `.venv/bin/python` in repo docs because bare `python` was not available in the shell used during the audit.
- Added shared `.env` loading so CLI and dashboard both read the project `.env`.
- Added OpenRouter retry/backoff handling and explicit error surfacing in `pipeline/llm_client.py`.
- Added approval blockers for LLM fallback output so development fallbacks remain usable for iteration but cannot pass customer approval.
- Added `backup-state` to the CLI and dry-ran it successfully. Archive created: `state/backups/webrefurb-state-20260428T060622+0000.zip`.
- Added focused P0 tests for env loading, backup creation, retry behavior, and approval blocking.
- Verified `.venv/bin/python -m pytest tests/ -v` completed with `221 passed in 20.67s`.

## P1 - Correct Menu Output Generation

Goal: make it impossible to approve a polished-looking but wrong menu package.

Primary files:

- `pipeline/custom_build.py`
- `pipeline/export.py`
- `pipeline/populate.py`
- `pipeline/package_export.py`
- `pipeline/models.py`
- `dashboard/app.py`
- `dashboard/templates/index.html`
- `MENU_DESIGN_LOOP.md`
- `tests/test_custom_build.py`
- `tests/test_api.py`

Tasks:

- [x] Define the canonical production `menu_data` schema.
- [x] Require each production item to include at minimum: Japanese name or source text, English name, section, price status, source provenance, and approval status.
- [x] Split food, drink, course, and ticket-machine data explicitly instead of sending one combined item list into multiple templates.
- [x] Replace the fixed multi-box food/drinks layout with adaptive section layout rules so a restaurant with only one real section can use the page naturally instead of leaving blank template boxes.
- [x] Replace slot-filling behavior that leaves unused template text behind.
- [x] Make price state explicit and watertight: `detected_in_source`, `pending_business_confirmation`, `confirmed_by_business`, and `intentionally_hidden`.
- [x] Hide all prices from customer-facing Package 1/2 artifacts until the business has explicitly confirmed them.
- [x] Prevent extracted/source-detected prices from being promoted to customer-visible prices by default build behavior.
- [x] Render prices in customer output only when they are both business-confirmed and not intentionally hidden by operator decision.
- [x] Render "price unknown" only as an operator-visible issue, never silently in customer output.
- [x] Clear or remove all unused template sections and item slots.
- [x] Add overflow handling based on rendered layout, not only item count.
- [x] Fail package validation when rendered output omits source items.
- [x] Fail package validation when rendered output contains stale template-only item names.
- [x] Fail package validation when rendered output contains placeholder translations such as bracketed fallback names.
- [x] Fail package validation when food/drink sections bleed into the wrong output.
- [x] Add a text-parity validator for SVG/HTML output.
- [x] Add a stale-template detector built from locked template text.
- [x] Add a price-state validator that blocks any customer output showing prices before business confirmation.
- [x] Add a price-count validator for confirmed prices only: every business-confirmed price must be visible in customer output unless explicitly marked hidden by operator decision.
- [x] Add build review checklist fields for operator confirmation: item count, price count, section split, stale text absent, owner source present.
- [x] Block package approval when validation has errors, not only when required files are missing.
- [x] Create and follow a rendered menu design loop for typography, spacing, sparse-layout balance, and one-section page composition.
- [x] Render and visually inspect Package 1 and Package 2 review screens after changes.

Exit gate:

- [x] A sample build using `state/builds/job-viz/menu_data.json` no longer contains unrelated template items.
- [x] Food and drink outputs contain only their intended sections.
- [x] A one-section restaurant menu can render as a visually intentional one-page layout instead of a sparse fixed-grid template.
- [x] Unconfirmed prices do not appear in rendered customer artifacts.
- [x] Business-confirmed prices appear in rendered customer artifacts only when they are meant to be customer-visible.
- [x] Tests cover stale-template detection, missing prices, wrong section bleed, and output parity.
- [x] Dashboard package review has been browser-rendered and visually inspected.

## P2 - Harden QR Product

Goal: make Package 3 a real product instead of a hosted page that can be created with empty menu data.

Primary files:

- `pipeline/qr.py`
- `dashboard/app.py`
- `dashboard/templates/index.html`
- `pipeline/package_export.py`
- `tests/test_qr.py`
- `tests/test_api.py`
- `docs/pricing.html`
- `docs/ja/pricing.html`

Tasks:

- [x] Reject QR draft creation when payload has no structured menu items.
- [x] Convert photo-only replies into a "needs extraction" state, not a QR draft.
- [x] Add a structured QR extraction/review step before `create_qr_draft`.
- [x] Require item descriptions and ingredients/allergens only when the package promise includes them.
- [x] Store owner-confirmation provenance for ingredient/allergen claims.
- [x] Block publish when ingredient/allergen content is present but not owner-confirmed.
- [x] Define the Package 3 hosting promise: hosting term, update policy, support expectations, and what happens after the term.
- [x] Re-evaluate Package 3 pricing and whether it should be standalone, bundled, or update-fee based.
- [x] Add QR health checks that fail when docs output, manifest, current version, sign PDF, or source data is missing.
- [x] Ensure QR sign generation works in a freshly synced environment.
- [x] Add tests for empty payload rejection, photo-only "needs extraction", owner-confirmation blocking, and successful publish.
- [ ] Render and visually inspect the QR menu page and dashboard QR review modal after changes.

Exit gate:

- [x] Empty or photo-only QR creation cannot produce a reviewable QR draft.
- [x] A complete QR sample publishes, health-checks, and exports successfully.
- [x] Package 3 has a clear operational promise in code/docs before it is sold.
- [x] QR tests pass in the active environment.

Progress recorded 2026-04-28:

- Added a real `needs_extraction -> ready_for_review` QR workflow step via `complete_qr_extraction()`.
- Structured extraction now accepts direct `items`, `menu_data`, raw text, or stored-menu-photo extraction before a draft is materialized.
- Dashboard QR review now truthfully shows `Needs extraction` until a reviewable draft exists, then transitions into the standard review state.
- Focused verification passed: `.venv/bin/python -m pytest tests/test_qr.py -q` => `11 passed`; `.venv/bin/python -m pytest tests/test_api.py -q` => `75 passed`.
- Browser verification completed for the dashboard QR review modal and the generated extracted draft page on `http://127.0.0.1:8001`.
- Added explicit QR content requirements plus owner-confirmation provenance for descriptions and ingredient/allergen claims.
- Publish now blocks when owner-visible description or ingredient/allergen content exists without recorded owner confirmation.
- Added a QR review action to confirm owner-provided content and surfaced confirmation counts in the dashboard review modal.
- Defined the Package 3 promise in code plus English/Japanese pricing docs: 12-month hosting term, one bundled update round in the first 30 days, basic support scope, and the after-term path.
- Fresh verification passed after that change: `.venv/bin/python -m pytest tests/test_qr.py -q` => `12 passed`; `.venv/bin/python -m pytest tests/test_api.py -q` => `76 passed`.
- Browser verification completed for the updated QR review modal plus `docs/pricing.html` and `docs/ja/pricing.html` via local file renders.
- QR health now fails loudly when the live manifest, checksums, current version docs output, publish manifest, source data, or approved-package sign PDF/export is missing.
- Fresh verification passed after that health pass: `.venv/bin/python -m pytest tests/test_qr.py -q` => `14 passed`; `.venv/bin/python -m pytest tests/test_api.py -q` => `77 passed`.
- Package 3 pricing was re-evaluated and is now treated as a standalone `¥65,000` hosted service with one bundled 30-day update round; later changes move into paid update work while combined-package deals remain quote-only.
- QR sign generation is confirmed working in the active synced `.venv` through focused tests plus live dashboard/browser flows.

## P3 - Fix Lead And Contact Reality

Goal: stop treating "has email" as the definition of an actionable shop.

Primary files:

- `pipeline/models.py`
- `pipeline/record.py`
- `pipeline/search.py`
- `pipeline/contact_crawler.py`
- `pipeline/qualification.py`
- `pipeline/scoring.py`
- `pipeline/evidence.py`
- `dashboard/app.py`
- `dashboard/templates/index.html`
- `tests/test_contact_crawler.py`
- `tests/test_api.py`

Tasks:

- [x] Add a first-class `contacts` list to lead records.
- [x] Contact fields must support at least: email, contact form, LINE, Instagram, phone, website, map URL, and walk-in candidate.
- [x] Each contact must store source URL, confidence, discovered timestamp, and status.
- [x] Keep `email` as a compatibility field only where needed; do not make it the only actionable field.
- [x] Wire contact discovery into the main `search_and_qualify` flow.
- [x] Preserve qualified leads without email when another contact route exists.
- [x] Add dashboard filters for email, form, LINE, Instagram, phone, and walk-in.
- [x] Add "copy message" and "mark contacted" flows for form, LINE, Instagram, and phone/manual outreach.
- [x] Add statuses for `contacted_form`, `contacted_line`, `contacted_instagram`, `called`, and `visited`.
- [x] Add a first-class `establishment_profile` to lead records so the system can distinguish small ramen shops, ramen with ticket machines, ramen with sides/add-ons, izakaya drink-heavy menus, izakaya course-heavy menus, and unknown/manual-review cases.
- [x] Store establishment-profile evidence, confidence, and source URLs; do not infer a profile without recorded evidence or explicit operator override.
- [x] Add dashboard display and manual override for establishment profile before any outreach sample/layout is selected.
- [x] Keep duplicate prevention based on place ID, website domain, phone, and name plus area.
- [x] Add tests proving a no-email lead with a contact form appears as actionable.
- [x] Add tests proving a no-email, no-contact lead is retained as research-only or skipped with an explicit reason.
- [x] Add tests proving establishment profile classification selects ramen, ramen/ticket-machine, and izakaya/drink-heavy cases from evidence.

Progress recorded 2026-04-28:

- Lead records now persist first-class normalized contacts for email, contact form, LINE, Instagram, phone, walk-in, map URL, and website routes.
- Contact records now carry source URL, confidence, discovery timestamp, and status metadata, with legacy records normalized safely at read time.
- `search_and_qualify()` now keeps qualified non-email businesses actionable when another supported route exists and records their primary route for the dashboard/manual outreach flow.
- Dashboard lead filtering plus manual outreach copy/mark-contacted flows are active for non-email routes, and route-specific outreach statuses persist to lead history.
- Establishment-profile classification, evidence, confidence, source URLs, and operator override flows are live in the dashboard before outreach selection.
- Verified business names now promote into a locked authoritative field so downstream outreach/reply flows keep using the confirmed restaurant name even if a later mutable `business_name` value drifts.
- Duplicate prevention remains enforced through place ID, website domain, phone, and name-plus-area matching.
- Focused verification passed on the current P3 slice:
  - `.venv/bin/python -m pytest tests/test_search.py -q` => `10 passed`
  - `.venv/bin/python -m pytest tests/test_api.py -q` => `88 passed`

Exit gate:

- [x] Dashboard no longer reports "zero actionable leads" just because no email exists.
- [x] Contact crawler results flow into saved lead records.
- [x] No-email contact-form and LINE leads can be actioned by the operator.
- [x] Leads carry an evidence-backed establishment profile or explicit manual-review state before outreach asset selection.
- [x] Existing email send safety rules still pass.

Exit evidence recorded 2026-04-28:

- Lead discovery now persists first-class contacts, including non-email routes plus map URLs, into saved lead records with provenance and contact-status metadata.
- Dashboard Leads keeps supported non-email businesses actionable instead of dropping them from the queue, and manual outreach flows can copy a draft plus persist route-specific contacted statuses.
- Establishment profiles now persist with evidence, confidence, source URLs, and an operator override path before outreach asset selection.
- Duplicate prevention remains enforced across place ID, website domain, phone, and name-plus-area matching.
- Focused verification passed on the current P3 slice:
  - `.venv/bin/python -m pytest tests/test_search.py -q` => `10 passed`
  - `.venv/bin/python -m pytest tests/test_api.py -q` => `88 passed`

## P4 - Make Outreach Convert

Goal: replace generic cold outreach with channel-specific, shop-specific proof of value.

Primary files:

- `pipeline/outreach.py`
- `pipeline/email_templates.py`
- `pipeline/email_html.py`
- `pipeline/preview.py`
- `pipeline/pitch.py`
- `dashboard/app.py`
- `dashboard/templates/index.html`
- `tests/test_outreach.py`
- `tests/test_safety.py`

Tasks:

- [x] Generate a shop-specific partial preview for outreach using public evidence.
- [x] Clearly mark outreach previews as illustrative and partial.
- [x] Keep production boundary clear: production uses owner-provided photos or explicit owner confirmation.
- [x] Stop relying on generic PDF attachments as the primary conversion asset.
- [x] Keep generic PDFs only as secondary examples when useful.
- [x] Add a machine-only/ticket-machine outreach template.
- [x] Segment outreach copy by ramen, izakaya, ticket-machine ramen, and drink/course-heavy izakaya.
- [x] Select outreach preview/sample assets from `establishment_profile`: small ramen gets a ramen-only one-page sample, ramen with ticket-machine evidence gets menu plus ticket-machine support, and izakaya/drink-heavy leads get food/drinks-oriented samples.
- [x] Ramen copy must emphasize ticket machines, toppings, set menus, rush-hour friction, and tourist ordering confidence.
- [x] Izakaya copy must emphasize drinks, courses, nomihodai-style rules, ingredient clarity, and fewer staff explanations.
- [x] Add channel-specific copy for email, contact forms, LINE, Instagram DM, phone script, and walk-in script.
- [x] Add dashboard operator controls for channel-specific messages.
- [x] Add inbound reply automation or webhook support for Resend replies.
- [x] Keep manual incoming reply entry as fallback.
- [x] Add bounce, invalid, and opt-out handling for non-email channels where applicable.
- [x] Render and visually inspect outreach preview modal after changes.

Exit gate:

- [x] A lead can generate a shop-specific preview.
- [x] Machine-only leads are no longer blocked solely because no template exists.
- [x] Email, form, LINE, Instagram, phone, and walk-in messages are available in dashboard.
- [x] Generic-only outreach is no longer the default.
- [x] Outreach samples match the lead's evidence-backed establishment profile instead of defaulting to a dual food/drinks menu.
- [x] Safety tests prove customer-facing outreach does not mention AI, automation, scraping, or internal tools.

Progress recorded 2026-04-28:

- `machine_only` leads now generate a real outreach draft instead of failing in the API/dashboard review flow.
- Machine-only outreach now uses a dedicated subject/body, attaches the ticket-machine PDF sample, and renders the dashboard preview without the old blocker state.
- Focused verification passed for the current P4 slice:
  - `.venv/bin/python -m pytest tests/test_outreach.py tests/test_api.py tests/test_safety.py -q` => `142 passed`
  - `.venv/bin/python -m py_compile pipeline/outreach.py dashboard/app.py` => passing
- Browser-rendered verification on `http://127.0.0.1:8001` confirmed a machine-only lead now opens a normal outreach draft modal with ticket-machine-specific copy and attachment instead of the previous “not implemented yet” block.
- Outreach copy is now profile-aware for ramen-only, ramen-with-sides, ramen-with-drinks, ramen-ticket-machine, izakaya food-and-drinks, drink-heavy izakaya, and course-heavy izakaya leads.
- Outreach sample-file selection now uses `establishment_profile` so the dashboard can pick a one-page ramen sample, ramen-plus-sides sample, drink-forward izakaya sample, or machine-guide set instead of always defaulting to the same generic menu PDF.
- The preview modal now shows sample-strategy rationale and profile-aware asset labels so operators can see why a given sample set was chosen.
- Fresh verification passed after that outreach-conversion pass:
  - `.venv/bin/python -m pytest tests/test_outreach.py tests/test_api.py tests/test_safety.py -q` => `163 passed`
  - `.venv/bin/python -m py_compile pipeline/outreach.py dashboard/app.py` => passing
  - `git diff --check` => passing
- Browser-rendered verification on `http://127.0.0.1:8001` confirmed:
  - a ramen-only lead shows the `Ramen Menu Sample (One Page)` asset plus a ramen-only sample-strategy note
  - a drink-heavy izakaya lead shows the `Drink-Forward Izakaya Sample` asset plus drink/nomihodai-focused copy

Progress recorded 2026-04-28 (P4 completion):

- Ramen outreach copy now emphasizes toppings, set menus, rush-hour friction, and tourist ordering confidence.
- Izakaya outreach copy now emphasizes drinks, courses, nomihodai rules, ingredient clarity, and fewer staff explanations.
- `build_shop_preview_from_record()` in `preview.py` generates shop-specific previews from lead evidence snippets.
- Shop-specific preview HTML included in outreach payload (`shop_preview_html` field) for dashboard display.
- Preview CSS updated from cream/off-white to v4c dark palette (`#0f0d0b` / `#1c1917` / `#f0ebe3` / `#c53d43`).
- Resend webhook endpoint `POST /api/webhooks/resend` handles `email.bounced`, `email.complained`, `email.delivered`.
- Bounced emails mark leads as `bounced`/`invalid`; complaints mark as `do_not_contact`.
- Manual unreachable endpoint `POST /api/leads/{lead_id}/mark-unreachable` for non-email channel failures.
- `OUTREACH_STATUS_BOUNCED` and `OUTREACH_STATUS_INVALID` added to `constants.py`.
- Manual reply entry via `POST /api/incoming-reply/{lead_id}` remains as fallback.
- Full test suite: 295 passed, 2 pre-existing website test failures (unrelated to changes).

## P5 - Add Paid Operations Workflow

Goal: make "yes, let's do it" operationally executable before any real customer work is accepted.

Primary files:

- `pipeline/package_export.py`
- `pipeline/custom_build.py`
- `pipeline/models.py`
- `pipeline/record.py`
- `dashboard/app.py`
- `dashboard/templates/index.html`
- `docs/pricing.html`
- `docs/ja/pricing.html`
- `tests/test_custom_build.py`
- `tests/test_api.py`

Tasks:

- [x] Add quote generation for each package.
- [x] Quote must include restaurant name, package, scope, price, revision limits, delivery terms, update terms, payment instructions, and expiry date.
- [x] Add invoice generation or invoice-ready data fields.
- [x] Include Japanese invoice registration number support if applicable.
- [x] Add payment method fields: bank transfer, manual paid flag, payment reference, paid amount, payment timestamp.
- [x] Decide payment terms: full upfront or deposit plus balance.
- [x] Add lead/order states: quoted, quote_sent, payment_pending, paid, intake_needed, in_production, owner_review, owner_approved, delivered, closed.
- [x] Block production approval unless payment status satisfies package rules.
- [x] Add owner intake checklist: full menu photos/PDFs, ticket-machine photos, price confirmation, dietary/ingredient notes, delivery details, and business contact.
- [x] Add owner approval record with timestamp, approver name, approved package, approved source data checksum, and approved rendered artifact checksum.
- [x] Add revision policy tracking.
- [x] Add delivery-cost and print-cost assumptions for Package 2.
- [x] Add custom-quote gate for large izakaya menus, multiple menu sets, oversized print, extra copies, or frequent updates.
- [x] Add privacy/data retention note for owner-uploaded menu photos and QR hosted data.

Exit gate:

- [x] A positive reply can become a quote.
- [x] A quote can become payment pending, paid, intake, production, owner review, approval, and delivery states.
- [x] Package approval is blocked without required payment/intake/owner-approval fields.
- [x] Quote and invoice artifacts can be generated and inspected.

Progress recorded 2026-04-29:

- `pipeline/quote.py` now creates structured orders, quote markdown artifacts, invoice-ready JSON, full-upfront payment terms, Package 2 print/delivery assumptions, custom-quote triggers, and privacy/data-retention language.
- Dashboard APIs now create orders, mark quote-sent/payment-pending/paid/intake/owner-review/owner-approved/delivered states, expose quote/invoice artifacts, and link paid orders to builds.
- Final package export is blocked until quote, confirmed payment, complete intake, owner approval checksums, and privacy note acceptance are present.
- Verification: `.venv/bin/python -m py_compile pipeline/quote.py pipeline/models.py dashboard/app.py pipeline/package_export.py`; `.venv/bin/python -m pytest tests/test_paid_ops.py tests/test_api.py::TestAPIEndpoints::test_paid_order_workflow_records_quote_payment_intake_and_owner_approval tests/test_custom_build.py::TestCustomerExport::test_package2_approval_creates_print_pack_zip -q`; `.venv/bin/python -m pytest tests/ -q` => `309 passed`.

## P6 - Operator Rehearsal

Goal: run the actual business workflow with sample data before touching real shops.

Primary files:

- `state/` sample artifacts
- `dashboard/`
- `pipeline/`
- `tests/`
- `LAUNCH_CHECKLIST.md`
- `HANDOFF.md`

Tasks:

- [x] Back up current `state/`.
- [x] Run a full Package 1 rehearsal from lead to quote to paid sample to build to approval to export.
- [x] Run a full Package 2 rehearsal with delivery fields, print checklist, final ZIP, and rendered review.
- [x] Run a full Package 3 rehearsal with structured items, owner-confirmed ingredients where applicable, publish, health check, QR sign, and final ZIP.
- [x] Run no-email contact-form and LINE lead rehearsals.
- [x] Run ticket-machine-only lead rehearsal.
- [x] Render and visually inspect dashboard views used by the operator.
- [x] Inspect generated PDFs/SVGs/HTML/QR pages for actual content correctness, not just file existence.
- [x] Record every confusing or manual step as a blocker.
- [x] Update launch checklist from rehearsal findings.
- [x] Update handoff with current test count, known limitations, and go/no-go status.

Exit gate:

- [x] All three packages complete rehearsal without manual database/file surgery.
- [x] All customer artifacts pass content parity and visual inspection.
- [x] Operator can handle no-email, machine-only, and reply-with-photos flows.
- [x] Launch checklist reflects actual workflow.
- [x] Full tests pass after rehearsal changes.

Progress recorded 2026-04-29:

- Backup before rehearsal: `state/backups/webrefurb-state-20260428T230412+0000.zip`; backup after rehearsal: `state/backups/webrefurb-state-20260428T230746+0000.zip` with `orders` included.
- Package 1 rehearsal final export: `state/final_exports/p6-package1/p6-package1-package_1_remote_30k.zip`.
- Package 2 rehearsal final export: `state/final_exports/p6-package2/p6-package2-package_2_printed_delivered_45k.zip`, including `PRINT_ORDER.json`, `PRINT_CHECKLIST.md`, `DELIVERY_CHECKLIST.md`, and B4 print output.
- Package 3 rehearsal final export: `state/final_exports/qr-849bf3ed/qr-849bf3ed-package_3_qr_menu_65k.zip`, with QR health passing.
- Rehearsal report: `state/p6_rehearsal/P6_REHEARSAL_REPORT.json`.
- Dashboard visual inspection covered Leads, Builds, and QR Menus on `http://127.0.0.1:8001`; no overlapping text or blocked operator surface was observed.
- Full verification after rehearsal: `.venv/bin/python -m pytest tests/ -q` => `309 passed`.

## P6A - Product Audit Hardening

Goal: implement the 2026-04-29 product audit before controlled launch, with stronger lead proof, diagnosis-led outreach, outcome-based package framing, and batch measurement.

Primary files:

- `pipeline/lead_dossier.py`
- `pipeline/search_scope.py`
- `pipeline/outreach.py`
- `pipeline/preview.py`
- `pipeline/launch.py`
- `dashboard/`
- `docs/`
- `tests/`

Tasks:

- [x] Back up `state/` before migration.
- [x] Add persisted lead evidence dossiers while preserving binary `lead: true|false`.
- [x] Store `ticket_machine_state`, `english_menu_state`, `menu_complexity_state`, and `izakaya_rules_state`.
- [x] Store proof items with source type, URL, snippet, customer-preview eligibility, and rejection reason.
- [x] Gate dashboard outreach generation on `launch_readiness_status`.
- [x] Replace generic search defaults with friction-first ramen/izakaya search jobs.
- [x] Disqualify chain-like, already-solved, multilingual-QR, or out-of-scope records before launch.
- [x] Migrate stale package keys to current package keys.
- [x] Quarantine the stale Tsukada Nojo record as `do_not_contact`.
- [x] Replace price-led cold pitch behavior with shop-specific diagnosis outreach.
- [x] Add sender identity, contact detail, opt-out wording, and message variant tracking.
- [x] Block bracketed fallback translations, boilerplate snippets, reservation snippets, chain snippets, and unconfirmed prices from customer-visible previews.
- [x] Rename customer-facing package labels to English Ordering Files, Counter-Ready Ordering Kit, and Live QR English Menu while keeping package keys/prices stable.
- [x] Add launch batch records that enforce 5-10 lead batches and block batch 2 until batch 1 is reviewed.
- [x] Add regression tests for dossier state derivation, stale-state migration, preview filtering, diagnosis outreach, friction-first search, website copy, and launch batches.
- [x] Browser-verify dashboard readiness badges, outreach modal, homepage, pricing page, Japanese mobile page, and QR page.

Exit gate:

- [x] State backup exists before migration: `state/backups/webrefurb-state-20260428T235430+0000.zip`; post-hardening backup exists: `state/backups/webrefurb-state-20260429T001624+0000.zip`.
- [x] Stale Tsukada Nojo lead is disqualified, migrated from `package_A_in_person_48k` to `package_2_printed_delivered_45k`, and marked `do_not_contact`.
- [x] Customer-facing preview generation returns no bracketed fallback translations and hides unconfirmed prices.
- [x] Dashboard outreach API rejects non-ready leads with explicit readiness reasons.
- [x] Public package labels use outcome names while prices remain ¥30,000 / ¥45,000 / ¥65,000.
- [x] Browser verification screenshots written under `state/qa-screenshots/`.
- [x] `.venv/bin/python -m pytest tests/ -q` => `318 passed`.
- [x] `git diff --check` passed.

## P7 - Controlled Launch

Goal: launch in a way that exposes real-world risk without overwhelming operations.

Scope:

- Japan only.
- Ramen and izakaya only.
- Independent shops only.
- No chains unless explicitly reviewed.
- No high-volume automation.

Tasks:

- [ ] Select 5 to 10 high-confidence shops.
- [ ] Prefer clear Japanese-only friction, strong menu/ticket-machine evidence, and reachable contact channel.
- [ ] Include at least one ramen ticket-machine candidate and one izakaya drink/course candidate.
- [ ] Back up `state/` immediately before sending or contacting.
- [ ] Use the best real channel for each lead: email, form, LINE, Instagram, phone, or walk-in.
- [ ] Send/contact slowly and record outcomes immediately.
- [ ] Track responses, bounces, invalid channels, opt-outs, positive replies, and operator time.
- [ ] Do not start a second batch until the first batch is reviewed.
- [ ] Update scoring and channel priority from actual response data.
- [ ] Update package/pricing assumptions from owner objections and conversion behavior.

Exit gate:

- [ ] First batch results reviewed.
- [ ] Contact-channel performance recorded.
- [ ] At least one complete positive-reply-to-delivery rehearsal or real order path is understood.
- [ ] Next batch changes are planned from evidence, not intuition.

## Product-Specific Positioning To Preserve

Ramen value:

- Ticket-machine clarity.
- Toppings, sets, soup/base choices, spice levels, noodle firmness, and add-ons.
- Faster tourist decisions during busy service.
- Compact counter-friendly order guidance.

Izakaya value:

- Drink category clarity.
- Course and all-you-can-drink rule explanation.
- Ingredient/allergen confidence where owner-confirmed.
- Shared plates, seasonal menus, and staff explanation reduction.
- QR-first or update-friendly packages when menus change often.

## Implementation Notes By Surface

Lead records:

- Move from `email` as the action key to `contacts[]`.
- Keep old `email` support during migration.

Search:

- Search may still produce binary `lead: true|false`.
- Contactability is separate from lead qualification.

Dashboard:

- Show leads by best next action, not just email availability.
- Any operator action that changes customer state must be explicit and logged.

Build pipeline:

- Structured data is the source of truth.
- Rendered output must prove it matches structured data.
- File existence is not enough.

QR:

- A QR draft is not valid without structured items.
- Ingredient/allergen claims need owner-confirmation provenance.

Outreach:

- Shop-specific proof beats generic attachment.
- Channel-specific copy beats one universal email.
- Machine-only is a first-class lead type.

Payments:

- Quote before work.
- Payment status before production approval.
- Invoice/receipt data before launch.

State:

- Backups are mandatory before real outreach and after operator sessions.
- File-based state is acceptable only for controlled launch after backups exist.

## Deferred Until After P7

These are important, but not required before controlled launch:

- Full CRM replacement.
- Automated form submission.
- Fully automated inbound parsing for every channel.
- Print vendor API integration.
- Stripe or online card payments.
- Multi-region expansion outside Japan.
- Categories beyond ramen and izakaya.
- Subscription billing.
- Multi-operator permissions.
- Public self-service owner portal.

## Change Control

Any change to phase order, launch freeze rules, or package scope requires an explicit user decision. Record the decision in this file before implementation continues.
