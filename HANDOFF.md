# WebRefurbMenu Handoff

Updated: 2026-05-02

Compact resume file. Keep it short. Replace stale facts instead of appending logs.

## Startup Read Path

1. Read `AGENTS.md`.
2. Read this file.
3. Open long docs, raw leads, or reports only for a specific blocker.

## Safety Boundary

- No real email, contact-form submit, or other business contact unless explicitly requested in the current chat.
- "Continue" means no-send work only.
- Approved outreach routes are email and contact forms only.
- Phone, LINE, Instagram, reservation links, social DMs, phone-required forms, walk-ins, map URLs, and websites are not outreach routes.
- Do not set `pitch_ready=true`, `ready_for_outreach`, or `outreach_status=new` during no-send inventory work.
- Customer-facing copy must not mention AI, automation, scraping, or internal tools.

## Current State

- Branch: `codex/phase11-contact-form-batch`.
- Tree is dirty with unrelated pre-existing files. Do not revert user/unrelated changes.
- Active workstream: no-send restaurant pitch-card inventory for Tokyo, Osaka, Kyoto, Sapporo, and Fukuoka.
- Product goal clarified: create dashboard-reviewable pitch cards while all records remain manual-review blocked and unsendable.
- Page-50 directory pass finished; 320 reviewable pitch cards exist. The attempted 400-card target was not reached because supported routes became duplicate/sparse.

## Queue Snapshot

- Total records: 514 in `state/leads`; all are `launch_readiness_status=manual_review`.
- Existing baseline preserved: 484 snapshot records preserved, 0 missing, 0 changed existing email fields, 0 changed existing email contacts.
- Imported restaurant queue preserved: verifier still selects 483 imported records.
- No-send inventory over the 484-record baseline: 30 records total.
- Full queue pitch-card counts: 320 reviewable pitch cards, 320 needs review, 193 hard blocked, 1 unsupported route, 0 ready for outreach.
- Full queue review breakdown: 275 needs_email_review, 19 needs_name_review, 26 needs_scope_review.
- Safety counters: 0 `ready_for_outreach`, 0 `pitch_ready`, 0 `outreach_status:new`.

## Implementation State

- Pitch-card state is implemented in `pipeline/pitch_cards.py` and applied on record create/load/list/persist.
- Dashboard/API now separates pitch-card reviewability from launch readiness:
  - `/api/leads` returns `leads` plus `card_counts`.
  - Non-hard-blocked manual-review email/contact-form records can open review-only GET previews.
  - POST/regenerate/send remains blocked unless launch-ready; hard blocks are quarantined.
- Existing imported records were rehydrated into pitch-card states without deleting emails.
- Directory crawler is checkpointed/resumable and persists supported email/contact-form candidates immediately as manual-review pitch cards.
- Search loosening remains in force:
  - `--max-candidates 0` means no cap.
  - Ambiguous English-menu gaps, single-source names, and weak/menu-evidence directory failures can become review-blocked inventory.
  - Chains/operators, invalid email artifacts, solved English/multilingual cases, non-restaurant names, and clear out-of-scope cuisine remain hard-blocked.

## Search Counts

- Latest page-50 continuation searched 383 directory pages and 9,383 candidates.
- Usable email/contact-form routes found: 66.
- New records persisted: 21.
- Duplicates skipped: 5,823.
- Hard-blocked chains/operators: 893.
- Hard-blocked invalid email/artifacts: 0.
- Hard-blocked scope: 18.
- Review-blocked ambiguous records: 21.
- Fetch failures: 187.
- No supported route: 661.
- City/category new records in latest pass: Tokyo ramen 0, Tokyo izakaya 1, Osaka ramen 3, Osaka izakaya 5, Kyoto ramen 2, Kyoto izakaya 2, Sapporo ramen 1, Sapporo izakaya 5, Fukuoka ramen 0, Fukuoka izakaya 2.
- Latest summaries:
  - `state/lead_imports/five_city_directory_pitch_cards_target400_recovery_v2_p50.json`
  - `state/lead_imports/restaurant_lead_verification_pitch_cards_continued_400.json`

## Remaining Blockers

- The five-city directory lane has been consumed through page 50 per city/category but stopped below 400 cards.
- Supported-route discovery is sparse: many candidates have no usable email/contact form, are already duplicates, or have dead/TLS/DNS-failing official sites.
- Some supported routes still hard-block as clear scope mismatches; inspect reasons before loosening further.
- Serper/provider failures previously limited the Tabelog email-query lane; use checkpointed organic/contact fallback for the next growth target.

## Next Recommended Lane

1. Use dashboard manual review on the 320 pitch cards; do not promote records automatically.
2. Add a narrow organic/contact fallback: official contact/email queries for ramen/izakaya family terms, still no-send and checkpointed.
3. Consider a second directory source only if organic/contact fallback cannot reach the next card target.

## Last Verification

- Focused tests: `.venv/bin/python -m pytest tests/test_api.py tests/test_restaurant_lead_verification.py tests/test_restaurant_email_import.py tests/test_search.py tests/test_pipeline.py -q` -> 317 passed.
- `verify-restaurant-leads`: `state/lead_imports/restaurant_lead_verification_pitch_cards_continued_400.json`; 483 selected, 26 verified, 107 needs_review, 350 rejected, 0 ready_for_outreach, 0 pitch_ready.
- Whole-queue preservation audit: 514 records, 320 reviewable pitch cards, all manual-review blocked, baseline emails/contact emails preserved, 0 `ready_for_outreach`, 0 `pitch_ready`, 0 `outreach_status:new`.
- No outreach happened.
