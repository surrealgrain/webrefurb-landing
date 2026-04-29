# WebRefurbMenu Handoff

Updated: 2026-04-29 (Codex)

## Source Of Truth

Use `PLAN.md` only. It now contains the `Product Audit Implementation Plan` based directly on `PRODUCT_AUDIT_2026-04-29.md`, the original audit from 2026-04-29.

Do not resume from the obsolete P0/P1/P2/P3/P4/P5/P6/P7 plan text. That plan was intentionally replaced because it was interfering with the current audit-hardening workflow.

## Active Plan

Current plan: `Product Audit Implementation Plan`

Start at Phase 0 in `PLAN.md`. The plan intentionally treats prior implementation as untrusted until each phase is re-verified against `PRODUCT_AUDIT_2026-04-29.md`.

Phases:

0. Source Lock And Baseline Audit
1. State Backup And Stale-State Reconciliation
2. Lead Evidence Dossier Gate
3. Restaurant Fit And Disqualification Rules
4. Friction-First Search
5. Offer Fit And Package Recommendation
6. Shop-Specific Diagnosis Outreach
7. Preview And Proof Quality Gates
8. Public Positioning, Package Copy, And Risk Reversal
9. Paid Operations And P5 Reconciliation
10. Browser And Render Verification
11. Controlled Launch Batch 1
12. Batch Review And Iteration
13. Batch 2 And Repeatable Launch Loop

Real outreach is Phase 11. Do not start it early; complete the preceding plan gates first.

## Current Repo State

- Active branch now follows the new step-by-step Product Audit Implementation Plan in `PLAN.md`.
- Do not trust older completion claims. Re-verify implementation phase by phase.
- Real outreach has not been sent in this thread.
- Phase 0 source lock and baseline audit has been run against the new plan.
- At Phase 0 start, `git status --short` was clean.
- `PLAN.md` names `PRODUCT_AUDIT_2026-04-29.md` as the source audit.
- `HANDOFF.md`, `AGENTS.md`, and `CLAUDE.md` do not point back to the obsolete old plan as active guidance.

## Last Verified State

- Phase 0 baseline command `.venv/bin/python -m pytest tests/ -q` passed with `332 passed` on 2026-04-29.
- Phase 0 `git diff --check` was clean on 2026-04-29.
- Phase 1 state backup created: `state/backups/webrefurb-state-20260429T011607+0000.zip`.
- Phase 1 inspected both current lead records: `wrm-qr-viz` and `wrm-tsukada-nojo-shibuya-miyamasuzaka-japan-e409`.
- Phase 1 migrated Tsukada stale state: it remains `disqualified` / `do_not_contact`, active `pitch_draft` is now null, `pitch_available=false`, `preview_available=false`, and `preview_blocked_reason=legacy_pitch_contains_bracketed_fallback`.
- Phase 1 readiness migration now tracks blocked legacy pitch/preview fields and keeps bracketed legacy preview records out of launch-ready status.
- Phase 1 focused command `.venv/bin/python -m pytest tests/test_lead_dossier.py -q` passed with `8 passed`.
- Phase 1 full command `.venv/bin/python -m pytest tests/ -q` passed with `334 passed`.
- Phase 1 `git diff --check` was clean.
- Phase 2 verified persisted lead fields for `lead_evidence_dossier`, `proof_items`, `launch_readiness_status`, `launch_readiness_reasons`, `message_variant`, `launch_batch_id`, and `launch_outcome`.
- Phase 2 fixed new lead creation so `message_variant`, `launch_batch_id`, and `launch_outcome` are written at record creation.
- Phase 2 dashboard now shows disqualified lead cards as blocked/read-only cards while ordinary do-not-contact records remain hidden.
- Phase 2 focused command covering readiness persistence, dashboard readiness cards, outreach payload dossiers, non-ready outreach rejection, and dossier tests passed with `13 passed`.
- Phase 2 full command `.venv/bin/python -m pytest tests/ -q` passed with `336 passed`.
- Phase 2 `git diff --check` was clean.
- Phase 3 verified restaurant-fit gates for Japan physical-location evidence, ramen/izakaya-only scope, chain/branch rejection, excluded business types, already-solved English/multilingual ordering rejection, social-only sites, and placeholder/coming-soon pages.
- Phase 3 added explicit audit coverage for cafe, hotel, kaiseki, social-only, and stale placeholder pages.
- Phase 3 focused command covering binary lead, invalid page, already-good-English, chain, and excluded-business tests passed with `28 passed`.
- Phase 3 full command `.venv/bin/python -m pytest tests/ -q` passed with `341 passed`.
- Phase 3 `git diff --check` was clean.
- Phase 4 replaced remaining dashboard generic search query defaults with friction-first scope queries.
- Phase 4 expanded search fan-out with explicit ramen ticket-machine, meal-ticket, menu-photo, RamenDB, official-menu, English-menu, multilingual-QR, mobile-order, and English ticket-machine checks.
- Phase 4 expanded izakaya fan-out with nomihodai/course, oshinagaki, menu-photo, Hotpepper, Tabelog, official-menu, social-menu, English-menu, multilingual-QR, and mobile-order checks.
- Phase 4 stores `source_search_job` and `matched_friction_evidence` on persisted lead records and search decisions.
- Phase 4 rejects old generic override queries like `ramen restaurants Kyoto` as active defaults and preserves only non-generic operator custom searches.
- Phase 4 focused command `.venv/bin/python -m pytest tests/test_search_scope.py tests/test_search.py -q` passed with `29 passed`.
- Phase 4 full command `.venv/bin/python -m pytest tests/ -q` passed with `343 passed`.
- Phase 4 `git diff --check` was clean.
- Phase 5 preserved package keys/prices and added explainable package recommendation details while keeping the existing `recommend_package()` API compatible.
- Phase 5 recommendation branches now cover ramen ticket-machine default, ramen ticket-machine print-yourself fit, simple ramen without machine, ramen counter-ready need, izakaya frequent-update QR fit, izakaya stable table-menu print fit, and large/complex custom quote.
- Phase 5 stores `package_recommendation_reason` and `custom_quote_reason` on qualification results and lead records.
- Phase 5 dashboard lead cards show recommended package label and recommendation reason.
- Phase 5 focused command covering package scoring, search persistence, and dashboard recommendation display passed with `21 passed`.
- Phase 5 full command `.venv/bin/python -m pytest tests/ -q` passed with `350 passed`.
- Phase 5 `git diff --check` was clean.
- Phase 6 verified outreach remains shop-specific diagnosis copy rather than a price-led pitch.
- Phase 6 tightened commercial email contact lines with sender, contact URL/email, and opt-out wording.
- Phase 6 tests cover diagnosis elements, unknown ticket-machine and English-menu check phrasing, no all-price cold pitch, sender/contact/opt-out, forbidden customer-facing terms, do-not-contact blocking, and message variant persistence.
- Phase 6 focused command `.venv/bin/python -m pytest tests/test_outreach.py tests/test_api.py::TestDraftSaveAndLoad::test_outreach_returns_business_name tests/test_api.py::TestAPIEndpoints::test_outreach_blocked_for_do_not_contact -q` passed with `46 passed`.
- Phase 6 full command `.venv/bin/python -m pytest tests/ -q` passed with `353 passed`.
- Phase 6 `git diff --check` was clean.
- Phase 7 expanded preview rejection for header/footer, TEL/phone, search, reservation, unrelated chain, and bracketed fallback snippets.
- Phase 7 customer previews now depend on customer-eligible proof items when proof items exist, and blocked legacy preview/pitch records return no customer preview.
- Phase 7 preview samples now add operational clarity rows for ramen toppings, sets, noodle/soup choices, add-ons, ticket-machine mapping, and izakaya drinks/courses/nomihodai/shared-plate evidence only when proven by safe snippets.
- Phase 7 continues hiding unconfirmed source prices from outreach previews.
- Phase 7 focused command `.venv/bin/python -m pytest tests/test_preview_hardening.py tests/test_search.py -q` passed with `25 passed`.
- Phase 7 full command `.venv/bin/python -m pytest tests/ -q` passed with `357 passed`.
- Phase 7 `git diff --check` was clean.
- Phase 8 updated public homepage proof tiles so the first public flow shows menu files, ticket-machine guides, QR signs, and before/after ordering clarity.
- Phase 8 aligned English and Japanese pricing/homepage copy around English ordering systems/materials, not generic translation.
- Phase 8 added explicit public risk reversal: owner approval before delivery, one correction window, custom-quote limits, and no price/allergen claims without restaurant confirmation.
- Phase 8 aligned quote and messaging copy with the same owner-confirmation and correction-window promises.
- Phase 8 tests cover package names/prices, homepage output proof, positioning, no HVAC/forbidden public terms, pricing risk reversal, and quote risk reversal.
- Phase 8 focused command `.venv/bin/python -m pytest tests/test_website.py tests/test_paid_ops.py -q` passed with `10 passed`.
- Phase 8 full command `.venv/bin/python -m pytest tests/ -q` passed with `360 passed`.
- Phase 8 `git diff --check` was clean.
- Phase 9 tightened paid workflow API gates so owner review requires confirmed payment and complete intake, owner approval requires owner-review state plus privacy acceptance, and delivery requires package approval gates.
- Phase 9 delivery now records `delivered_at`, `follow_up_status`, and `follow_up_due_at`.
- Phase 9 rehearsed Package 1, Package 2, and Package 3 through quote, payment pending, paid, intake, production, owner review, owner approval, and delivered states with safe test data.
- Phase 9 verified final package export gates still block without paid order, payment, intake, privacy note, and owner approval.
- Phase 9 focused command `.venv/bin/python -m pytest tests/test_paid_ops.py tests/test_api.py::TestAPIEndpoints::test_paid_order_workflow_records_quote_payment_intake_and_owner_approval tests/test_api.py::TestAPIEndpoints::test_paid_order_blocks_owner_review_and_delivery_until_gates_pass -q` passed with `6 passed`.
- Phase 9 custom-build gate command `.venv/bin/python -m pytest tests/test_custom_build.py -q` passed with `41 passed`.
- Phase 9 full command `.venv/bin/python -m pytest tests/ -q` passed with `362 passed`.
- Phase 9 `git diff --check` was clean.
- Phase 10 created a local QA-only ready lead `wrm-qa-phase10-ramen` under ignored `state/leads/` for browser verification; no outreach was sent.
- Phase 10 started local dashboard/site servers on `127.0.0.1:8766` and `127.0.0.1:8767` for render checks.
- Phase 10 captured desktop and mobile screenshots under `state/qa-screenshots/phase10-*` for dashboard lead cards, outreach/lead dossier modal, homepage, pricing, Japanese homepage/pricing, sample ramen preview, sample izakaya preview, QR menu, and QR sign.
- Phase 10 browser checks found no forbidden placeholder/fallback text, no HVAC/forbidden public copy, no bracketed fallback text, and no horizontal overflow over 24px on checked pages.
- Phase 10 `git diff --check` was clean.
- Phase 11 hardened launch batch creation so every selected lead must have a selected channel, message variant, proof asset or eligible proof item, and recommended package before it can enter a controlled launch batch.
- Phase 11 batch records now include `batch_number`.
- Phase 11 focused command `.venv/bin/python -m pytest tests/test_launch.py tests/test_api.py::TestAPIEndpoints::test_launch_batch_api_blocks_second_batch_until_review tests/test_api.py::TestAPIEndpoints::test_launch_outcome_api_records_opt_out_and_operator_minutes -q` passed with `6 passed`.
- Phase 11 full command `.venv/bin/python -m pytest tests/ -q` passed with `363 passed`.
- Phase 11 `git diff --check` was clean.
- Phase 11 real Batch 1 outreach was not sent in this thread. Current checked-in code is ready to create the controlled batch, but the local real lead state does not contain 5-10 real launch-ready shops with both required profiles.
- Phase 11 no-send smoke testing was added as a rehearsal gate before external contact.
- No-send smoke test `smoke-65e39d8e3b` was created under ignored state using five public-evidence rehearsal leads; it includes two ramen ticket-machine leads and two izakaya drink/course leads.
- Smoke test `smoke-65e39d8e3b` is reviewed, has `external_send_performed=false`, `send_allowed=false`, `counts_as_launch_batch=false`, and every lead remains `reply_status=not_contacted` with empty `contacted_at`.
- Smoke leads have `launch_batch_id=""`; the smoke test did not create or block a real `state/launch_batches/` record.
- Fresh production-readiness no-send smoke test `smoke-76fde53b8a` was run and reviewed on 2026-04-29.
- Smoke test `smoke-76fde53b8a` checked five public-evidence rehearsal leads: source URLs returned HTTP 200, proof assets exist, drafts exist, sender/opt-out text exists, no lead has `outreach_sent_at`, and no lead has a real launch batch ID.
- After smoke test `smoke-76fde53b8a`, `state/launch_batches/` remained empty.
- Post-smoke verification `.venv/bin/python -m pytest tests/ -q` passed with `366 passed`; `git diff --check` was clean.
- A 10-business production-readiness audit was run for classification, pitch path, seal personalization, preview translation safety, and inline attachment plumbing.
- Audit result saved under ignored state: `state/qa-screenshots/production-readiness-10-business-audit-final2.json`.
- Audit hardening fixed: personalized restaurant-name seals for every inline menu/machine image, no guessed customer-visible preview translations, less brittle placeholder-page detection, category mismatch handling, franchise/FC rejection, and image-heavy page scoring.
- Final 10-business audit summary: 7 qualified/manual-review leads, 3 rejected, 3 ticket-machine profiles, 4 menu/regular-pitch classifications, 3 izakaya profiles, all checked seals correct, zero guessed preview translations.
- Remaining audit caveat: one public page (`https://maki.owst.jp/`) returned HTTP 404 to direct fetch during the local audit, so that candidate was correctly not qualified from empty content.
- Post-hardening verification `.venv/bin/python -m pytest tests/ -q` passed with `373 passed`; `git diff --check` was clean.
- No real outreach was sent.

## Resume Instructions

1. Read `PLAN.md`.
2. Continue from Phase 11 no-send real-world smoke testing, then real batch selection/outreach only after 5-10 real launch-ready leads are available; Phase 12 depends on real Batch 1 outcomes.
3. Compare implemented code against `PRODUCT_AUDIT_2026-04-29.md` and the exact phase acceptance criteria.
4. Do not use the obsolete long phase plan as guidance.
5. Do not start Phase 11 outreach until Phases 0-10 pass.
