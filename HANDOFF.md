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
## Resume Phase Plan
- Overall: 40-45% complete. P0 safety guardrails are always active; no-send inventory is 326/400 reviewable cards, directory source exhausted.
- P1 Corpus: 1.1 import queue done; 1.2 duplicate preservation done; 1.3 import/idempotency safety done; 1.4 future imports must keep same manifest discipline.
- P2 Verification: 2.1 fields done; 2.2 verifier pass done; 2.3 hard blocks quarantine done; 2.4 unresolved email/name/scope cases stay manual review.
- P3 Dashboard review: 3.1 review-only previews done; 3.2 filters done; 3.3 route/profile filters done; 3.4 review-lane quick filters + active lane state done; 3.5 human review of 326 cards remains.
- P4 Promotion: 4.1 approval/hold/reject rules not built; 4.2 promote-to-pitch_ready not allowed yet; 4.3 launch readiness remains blocked.
- P5 GLM: 5.1 stable reviewed category counts pending; 5.2 GLM briefs not started; 5.3 locked profile asset mapping pending.
- P6 Pitch packs: 6.1 batch dimensions pending; 6.2 GLM-locked asset routing pending; 6.3 draft generation/review pending.
- P7 Outreach readiness: 7.1 draft review pending; 7.2 send route confirmation pending; 7.3 `ready_for_outreach` final gate not started.
- Resume rule: restate P0-P7, identify active subphase, then run tools.
## Implementation State
- Pitch-card state is applied on record create/load/list/persist; dashboard/API separates reviewability from launch readiness.
- Review-only GET previews work for manual-review cards; POST/regenerate/send remains blocked unless launch-ready.
- Dashboard queue filters include city, menu/category, quality, verification, email/name status, source strength, contact route, profile, pitch-card state, and active review-lane quick filters.
- Directory crawler and generic search are checkpointed/resumable; all-search-failure jobs are not marked complete.
- Search loosening remains in force: ambiguous English-menu gaps can become review-blocked inventory; hard rejection reasons remain blocked.
- Codex organic email fallback can persist recoverable ramen/izakaya candidates as manual-review pitch cards; hard rejection reasons still do not persist.
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
- Latest dashboard checks: `tests/test_website.py -q` 10 passed; `tests/test_api.py -q` 113 passed.
- `verify-restaurant-leads --summary-path state/lead_imports/restaurant_lead_verification_pitch_cards_continued_p100.json`: 0 ready_for_outreach, 0 pitch_ready.
- Live `list-leads` safety audit: all records manual-review blocked; 0 ready_for_outreach, 0 pitch_ready, 0 `outreach_status:new`.
- No outreach happened.
