# WebRefurbMenu Handoff
Updated: 2026-05-02. Compact resume file. Keep it under roughly 40 lines. Replace stale facts instead of appending logs.
Startup read path: read `AGENTS.md`, then this file only. Open long docs, raw leads, or reports only for a specific blocker.
## Safety Boundary
- No real email, contact-form submit, or other business contact unless explicitly requested in the current chat; "continue" means no-send work only.
- Approved outreach routes are email and contact forms only; phone, LINE, Instagram, reservation links, social DMs, phone-required forms, walk-ins, map URLs, and websites are reference-only.
- During no-send inventory, do not set `pitch_ready=true`, `ready_for_outreach`, or `outreach_status=new`.
- Customer-facing copy must not mention AI, automation, scraping, or internal tools.
## Current Snapshot
- Branch: `codex/phase11-contact-form-batch`.
- Tree is dirty with unrelated pre-existing files. Do not revert user/unrelated changes.
- Active workstream: no-send restaurant pitch-card inventory for Tokyo, Osaka, Kyoto, Sapporo, and Fukuoka; all records remain manual-review blocked and unsendable.
- Page-100 directory pass exhausted all five-city ramen/izakaya lanes below the 400-card target.
- Live `list-leads`: 520 records, 326 dashboard-reviewable pitch cards, 193 hard blocked, 1 unsupported route.
- Pitch-card breakdown: 281 needs_email_review, 19 needs_name_review, 26 needs_scope_review.
- Safety counters: all 520 `launch_readiness_status=manual_review` and `outreach_status=needs_review`; 0 ready_for_outreach, 0 pitch_ready, 0 `outreach_status:new`.
## Implementation State
- Pitch-card state is implemented in `pipeline/pitch_cards.py` and applied on record create/load/list/persist; dashboard/API separates reviewability from launch readiness.
- Review-only GET previews work for eligible manual-review records, but POST/regenerate/send remains blocked unless launch-ready.
- Existing imported records were rehydrated into pitch-card states without deleting emails; hard blocks are quarantined.
- Directory crawler is checkpointed/resumable and persists supported email/contact-form candidates immediately as manual-review pitch cards.
- Search loosening remains in force: `--max-candidates 0` means no cap; ambiguous English-menu gaps can become review-blocked inventory; chains/operators, invalid email artifacts, solved English/multilingual cases, non-restaurant names, and clear out-of-scope cuisine remain hard-blocked.
- Codex organic email fallback can persist recoverable ramen/izakaya candidates as manual-review pitch cards; hard rejection reasons still do not persist.
- Generic search checkpointing tracks completed jobs and does not mark all-search-failure jobs complete.
## Evidence Pointers
- Latest directory summary: `state/lead_imports/five_city_directory_pitch_cards_target400_recovery_v2_p100.json`.
- Latest verifier summary: `state/lead_imports/restaurant_lead_verification_pitch_cards_continued_p100.json`.
## Blockers / Next Work
- Five-city directory source is exhausted through page 100; supported routes are sparse, duplicate-heavy, often fetch-failing, or hard-blocked by scope.
- Serper failed with not-enough-credits; webserper degraded into search failures, so provider-backed organic fallback is unreliable until provider access recovers.
- Next lane: dashboard manual review of the 326 cards, then a narrow no-send organic/contact fallback or a second directory source; keep everything manual_review only.
## Last Verification
- P100 directory crawl completed with 326 reviewable cards and 0 ready_for_outreach in its final summary.
- `tests/test_search.py -q`: 52 passed; focused suite (`test_api`, restaurant verification/import, search, pipeline): 321 passed.
- `verify-restaurant-leads --summary-path state/lead_imports/restaurant_lead_verification_pitch_cards_continued_p100.json`: 0 ready_for_outreach, 0 pitch_ready.
- Live `list-leads` safety audit: all records manual-review blocked; 0 ready_for_outreach, 0 pitch_ready, 0 `outreach_status:new`.
- No outreach happened.
