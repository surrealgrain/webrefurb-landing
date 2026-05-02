# WebRefurbMenu Handoff

Updated: 2026-05-02

Compact resume file. Keep it under 90 lines. Replace stale facts instead of appending logs.

## Startup Read Path

1. Read `AGENTS.md`.
2. Read this file.
3. Do not read long docs at startup; open `PLAN.md`, `PRODUCTION_SIMULATION_TEST_PLAN.md`, `EXECUTION_PLAN_RESTAURANT_LEADS.md`, raw lead files, or generated reports only for a specific blocker.

## Safety Boundary

- No real email, contact-form submit, or other business contact unless explicitly requested in the current chat.
- "Continue" means no-send work only.
- Approved outreach routes are email and contact forms only.
- Phone, LINE, Instagram, reservation links, social DMs, phone-required forms, walk-ins, map URLs, and websites are not outreach routes.
- Do not set `pitch_ready=true`, `ready_for_outreach`, or `outreach_status=new` during no-send inventory work.
- Customer-facing copy must not mention AI, automation, scraping, or internal tools.

## Current State

- Branch: `codex/phase11-contact-form-batch`.
- Tree is dirty; several unrelated files pre-existed. Do not revert user/unrelated changes.
- Active workstream: no-send restaurant pitch-card inventory for Tokyo, Osaka, Kyoto, Sapporo, and Fukuoka.
- Product goal clarified: create dashboard-reviewable pitch cards while all records remain manual-review blocked and unsendable.
- Target reached: 300 reviewable pitch cards.

## Queue Snapshot

- Total records: 493 in `state/leads`; all are `launch_readiness_status=manual_review`.
- Existing baseline preserved: 484 snapshot records preserved, 0 missing, 0 changed existing email fields, 0 changed existing email contacts.
- Imported restaurant queue preserved: verifier still selects 483 imported records.
- No-send inventory over the 484-record baseline: 9 records total; this final pass added 8 review-blocked records.
- Full queue pitch-card counts: 300 reviewable pitch cards, 300 needs review, 193 hard blocked, 0 unsupported route, 0 ready for outreach.
- Full queue review breakdown: 255 needs_email_review, 19 needs_name_review, 26 needs_scope_review.
- Safety counters: 0 `ready_for_outreach`, 0 `pitch_ready`, 0 `outreach_status:new`.

## Implementation State

- Pitch-card state is implemented in `pipeline/pitch_cards.py` and applied on record create/load/list/persist.
- Dashboard/API now separates pitch-card reviewability from launch readiness:
  - `/api/leads` returns `leads` plus `card_counts`.
  - Manual-review email/contact-form records can open review-only GET pitch previews when not hard-blocked.
  - POST/regenerate/send paths remain blocked unless launch-ready.
  - Hard blocks are quarantined by pitch-card status instead of counted as reviewable.
- Existing imported records were rehydrated into pitch-card states without deleting emails.
- Directory crawler is checkpointed/resumable and persists supported email/contact-form candidates immediately as manual-review pitch cards.
- Search loosening remains in force:
  - `--max-candidates 0` means no cap.
  - Ambiguous/no-record English-menu gap is acceptable inventory.
  - Single-source names can be review-blocked inventory.
  - Weak/menu-evidence failures from directory pages can become scope-review cards.
  - Chains/operators, invalid email artifacts, solved English/multilingual cases, non-restaurant names, and clear out-of-scope cuisine remain hard-blocked.

## Final Search Counts

- Final target-reaching runs searched 162 directory pages and 4,222 candidates.
- Usable email/contact-form routes found: 27.
- New records persisted: 8.
- Duplicates skipped: 2,238.
- Hard-blocked chains/operators: 503.
- Hard-blocked invalid email/artifacts: 0.
- Hard-blocked scope: 14.
- Review-blocked ambiguous records: 8.
- Fetch failures: 103.
- No supported route: 364.
- Target stop happened during Tokyo izakaya page 17 of the pages-11-to-20 recovery loop.
- Latest summaries:
  - `state/lead_imports/five_city_directory_pitch_cards_target300_loop2.json`
  - `state/lead_imports/five_city_directory_pitch_cards_target300_recovery_v2.json`
  - `state/lead_imports/five_city_directory_pitch_cards_target300_recovery_v2_p20.json`

## Remaining Blockers

- The directory lane reached the 300-card target before true five-city/category exhaustion; deeper pages remain for full exhaustion if desired.
- Supported-route discovery is sparse: many Tabelog official-site candidates have no usable email/contact form or are already duplicates.
- Some supported routes still hard-block as clear scope mismatches; inspect reasons before loosening further.
- Serper/provider failures previously limited the Codex Tabelog email-query lane; use checkpointed organic/contact fallback only if the next target exceeds 300 cards.

## Next Recommended Lane

1. Use dashboard manual review on the 300 pitch cards; do not promote records automatically.
2. If a higher target is needed, continue the checkpointed directory crawl past page 17 for Tokyo izakaya and pages 11+ for remaining city/categories.
3. Add a narrow organic/contact fallback only after directory depth is consumed: official contact/email queries for ramen/izakaya family terms, still no-send and checkpointed.

## Last Verification

- Focused tests: `.venv/bin/python -m pytest tests/test_api.py tests/test_restaurant_lead_verification.py tests/test_restaurant_email_import.py tests/test_search.py tests/test_pipeline.py -q` -> 317 passed.
- `verify-restaurant-leads`: `state/lead_imports/restaurant_lead_verification_pitch_cards_final_300.json`; 483 selected, 26 verified, 107 needs_review, 350 rejected, 0 ready_for_outreach, 0 pitch_ready.
- Whole-queue preservation audit: 493 records, 300 reviewable pitch cards, all manual-review blocked, existing emails/contact emails preserved, 0 `ready_for_outreach`, 0 `pitch_ready`, 0 `outreach_status:new`.
- No outreach happened.
