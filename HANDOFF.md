# WebRefurbMenu Handoff

Updated: 2026-05-02

Compact resume file. Keep it under 90 lines. Replace stale facts instead of appending history.

## Startup Read Path

1. Read `AGENTS.md`.
2. Read this file.
3. Do not read long docs at startup; open `PLAN.md`, `PRODUCTION_SIMULATION_TEST_PLAN.md`, `EXECUTION_PLAN_RESTAURANT_LEADS.md`, or `restaurant_email_leads.md` only for a specific blocker.

## Safety Boundary

- No real email, contact-form submit, or other business contact unless explicitly requested in the current chat.
- "Continue" means no-send work only.
- Approved outreach routes are email and contact forms only.
- Phone, LINE, Instagram, reservation links, social DMs, phone-required forms, walk-ins, map URLs, and websites are not outreach routes.
- `production_ready=true` is only a no-send simulation signal.
- Customer-facing copy must not mention AI, automation, scraping, or internal tools.

## Current State

- Branch: `codex/phase11-contact-form-batch`.
- Tree is dirty; do not commit without user review.
- `PLAN.md` Phases 0-12 are complete. Phase 13 is active, not complete.
- Controlled Batches 1 and 2 already had approved-route outreach; both have 0 replies/positives. Do not start Batch 3.
- Current decision: hold real Batch 3 outbound because replies are 0 and the candidate pool is not strong enough.
- Active workstream: preserve current email queue, loosen inventory search, and rebuild five-city candidate pool.

## Queue Snapshot

- Total records: 484 in `state/leads`; all remain blocked.
- Existing imported restaurant queue: 483 records preserved; 0 missing existing records; 0 changed existing email records.
- New no-send inventory: 1 Tokyo ramen-family record, `wrm-lead-2-3-9-8385` / `風土木` / `shopmaster@food-ki.jp`; manual-review blocked.
- Status across all records: 484 `manual_review`, 0 `ready_for_outreach`, 0 `pitch_ready`, 0 `outreach_status:new`.
- Imported restaurant queue verification: 26 verified, 107 needs_review, 350 rejected; email status 135 verified, 299 needs_review, 49 rejected.
- Latest verification summary: `state/lead_imports/restaurant_lead_verification_final_no_send_search.json`.

## Implementation State

- Search loosening is implemented and tested:
  - `--max-candidates 0` means no cap.
  - Ambiguous/no-record English-menu gap no longer rejects menu-qualified candidates.
  - Single-source names can pass as review-blocked inventory.
  - Chains/multi-location operators remain blocked.
  - Search-created records get `manual_review_required=true`, `pitch_ready=false`, and `outreach_status=needs_review`.
- `pipeline/search.py` uses Scrapling Fetcher with urllib fallback.
- `pipeline/directory_discovery.py` now uses category-specific Tabelog city pages and explicit Scrapling timeouts.
- `scripts/bulk_lead_gen.py` is patched to no-send inventory mode: no pitch/preview generation, full `qualify_candidate` gates before persistence, general restaurants skipped.
- Do not edit GLM-locked template content in Codex.

## Search Run Status

- Directory smoke slice: Tokyo city-wide Tabelog category pages 1-2; 33 candidates, 3 usable emails, 1 new persisted record, 3 duplicates, 2 chain/operator blocks, 5 fetch failures, 22 no-email.
- Five-city Tabelog email-first lane: 1,700 jobs attempted with `max_candidates=0`; 8 candidates found, all duplicates; 0 new records.
- Serper failed after Tokyo: 1,362 `search_failed` job decisions. Local WebSerper fallback was started for Osaka/Kyoto/Sapporo/Fukuoka but stopped because it was too slow and timed out repeatedly.
- Full five-city exhaustion is not complete. No outreach happened and no records were promoted.

## Remaining Blockers

- Need a resumable, checkpointed five-city crawler before another no-cap run:
  - Use city-wide Tabelog category pages (`/rstLst/ramen/`, `/rstLst/izakaya/`) with page checkpointing.
  - Add concurrent official-site probing with tight per-host timeouts.
  - Persist per-city/category summaries as the run progresses.
- Serper quota/provider failure blocked the explicit Tabelog email-query lane after Tokyo.
- Uncapped maps search is too slow without checkpointing because each job follows every physical-place candidate through source intelligence.

## Next Recommended Lane

1. Resume directory crawl with checkpoints: Tokyo page 3+, then Osaka, Kyoto, Sapporo, Fukuoka.
2. Keep only ramen/izakaya-family records; continue hard-blocking general restaurants, chains, solved English/multilingual cases, and invalid email artifacts.
3. After fresh search quota is available, rerun `scripts/no_send_five_city_lead_search.py --mode codex-tabelog` for failed cities.

## Last Verification

- Search/qualification focused tests: 152 passed.
- Restaurant import/verification focused tests: 46 passed.
- `verify-restaurant-leads`: 483 selected, 26 verified, 107 needs_review, 350 rejected, 0 ready_for_outreach, 0 pitch_ready.
- Existing-email preservation check: 483 baseline records preserved; 0 existing email/contact changes.
- Queue sanity: 484 total records, all manual-review blocked; 0 ready_for_outreach, 0 pitch_ready, 0 outreach_status:new.
- `audit-state` was not rerun in this pass; previous known failures were pre-existing launch-smoke proof-asset mismatches.

## Context Hygiene

- Keep handoffs to active phase/status, blockers, next action, latest verification, and report paths; do not paste raw lead lists/logs.
