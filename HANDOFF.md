# WebRefurbMenu Handoff
Updated: 2026-05-02. Compact resume file. Keep it under roughly 40 lines. Replace stale facts instead of appending logs.
Startup read path: read `AGENTS.md`, then this file only. Open long docs, raw leads, or reports only for a specific blocker.
## Safety Boundary
- No real email, contact-form submit, or other business contact unless explicitly requested in the current chat; "continue" means no-send work only.
- Approved outreach routes are email and contact forms only; phone, LINE, Instagram, reservation links, social DMs, phone-required forms, walk-ins, map URLs, and websites are reference-only.
- During no-send inventory/review, do not set `pitch_ready=true`, `ready_for_outreach`, or `outreach_status=new`.
- Customer-facing copy must not mention AI, automation, scraping, or internal tools.
## Current Snapshot
- Branch: `codex/phase11-contact-form-batch`; tree also has unrelated pre-existing dirty files, so stage only mission files.
- Active workstream: no-send restaurant pitch-card inventory for Tokyo, Osaka, Kyoto, Sapporo, and Fukuoka; all records remain manual-review blocked and unsendable.
- Live `list-leads`/API state: 520 records, 326 dashboard-reviewable pitch cards, 193 hard blocked, 1 unsupported route.
- Pitch-card breakdown: 281 needs_email_review, 19 needs_name_review, 26 needs_scope_review.
- Safety counters: all 520 `launch_readiness_status=manual_review` and `outreach_status=needs_review`; 0 ready_for_outreach, 0 pitch_ready, 0 `outreach_status:new`.
- Dashboard server is live at `http://127.0.0.1:8000/`.
## Resume Phase Plan
- P0 Safety: always active; no-send/no-promotion/manual-review constraints unchanged.
- P1 Corpus: 1.1 import queue done; 1.2 duplicate preservation done; 1.3 import/idempotency safety done; 1.4 future imports keep manifest discipline.
- P2 Verification: 2.1 fields done; 2.2 verifier pass done; 2.3 hard blocks quarantined; 2.4 unresolved email/name/scope cases stay manual review.
- P3 Dashboard review: 3.1 previews done; 3.2 filters done; 3.3 route/profile filters done; 3.4 lanes done; 3.5 no-send outcome workflow improved and active.
- P4 Promotion: 4.1 hold/needs-info/reject outcomes only; 4.2 approve/promote-to-pitch_ready not built; 4.3 launch readiness remains blocked.
- P5 GLM: 5.1 category counts pending; 5.2 briefs not started; 5.3 locked profile asset mapping pending.
- P6 Pitch packs: 6.1 batch dimensions pending; 6.2 GLM-locked asset routing pending; 6.3 draft generation/review pending.
- P7 Outreach readiness: 7.1 draft review pending; 7.2 send route confirmation pending; 7.3 final gate not started.
## Implementation State
- Dashboard sidebar now restates P0-P7 with substeps; active work is P3.5/P4.1 manual review only.
- Queue review support now includes outcome filter, unreviewed lane, review progress stats, outcome badges, fixed Reviewable filtering, and Save & Next/Next Unreviewed controls.
- Preview modal now receives saved no-send review outcome fields; saving an outcome reloads live API queue state instead of reusing stale embedded data.
- Review outcome API still enforces `manual_review`, `outreach_status=needs_review`, and `pitch_ready=false`; reject hard-blocks only the pitch card.
- Directory crawler and generic search remain checkpointed/resumable; all-search-failure jobs are not marked complete.
## Blockers / Next Work
- Five-city directory source is exhausted through page 100 below the 400-card target.
- Serper failed with not-enough-credits; webserper degraded into search failures, so provider-backed organic fallback is unreliable until provider access recovers.
- `audit-state` currently reports pre-existing launch/smoke asset-profile drift; no no-send safety drift was found in live counters.
- Next lane: manually review the 326 cards using unreviewed/email/form/name/scope lanes and next-card controls, then consider a narrow no-send organic/contact fallback or second directory source.
## Last Verification
- Tests: `tests/test_website.py -q` 12 passed; `tests/test_api.py -q` 117 passed; `tests/test_restaurant_lead_verification.py -q` 40 passed; dashboard script parse passed.
- Dashboard script parse check passed; live `GET /` returned 200 and `/api/leads` returned 520 records with the expected card counts.
- Live safety audit: all records manual-review blocked; 0 ready_for_outreach, 0 pitch_ready, 0 `outreach_status:new`.
- No outreach happened.
