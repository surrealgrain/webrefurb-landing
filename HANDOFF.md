# WebRefurbMenu Handoff
Updated: 2026-05-02. Compact resume file; replace stale facts instead of appending logs.
Startup read path: read `AGENTS.md`, then this file only. Open long docs, raw leads, or reports only for a specific blocker.
## Safety Boundary
- No real email, contact-form submit, or other business contact unless explicitly requested in the current chat; "continue" means no-send work only.
- Approved routes are email and contact forms only; phone, LINE, Instagram, reservation links, social DMs, phone-required forms, walk-ins, map URLs, and websites are reference-only.
- During no-send inventory/review, do not set `pitch_ready=true`, `ready_for_outreach`, or `outreach_status=new`.
- Customer-facing copy must not mention AI, automation, scraping, or internal tools.
## Current Snapshot
- Branch: `codex/phase11-contact-form-batch`; unrelated pre-existing dirty files remain, so stage only mission files.
- Active workstream: no-send restaurant pitch-card inventory; all records remain manual-review blocked and unsendable.
- Live state: 522 records, 328 openable pitch cards, 193 hard blocked, 1 unsupported route.
- Pitch-card breakdown: 283 needs_email_review, 19 needs_name_review, 26 needs_scope_review.
- Safety counters: all 522 `launch_readiness_status=manual_review` and `outreach_status=needs_review`; 0 ready_for_outreach, 0 pitch_ready, 0 `outreach_status:new`.
- Dashboard server is live at `http://127.0.0.1:8000/` (PID 76776 last checked).
## Resume Phase Plan
- P0 Safety: always active; no-send/no-promotion/manual-review constraints unchanged.
- P1 Corpus: 1.1 import queue done; 1.2 duplicate preservation done; 1.3 import/idempotency safety done; 1.4 future imports keep manifest discipline.
- P2 Verification: 2.1 fields done; 2.2 verifier pass done; 2.3 hard blocks quarantined; 2.4 unresolved email/name/scope cases stay manual review.
- P3 Dashboard review: 3.1 previews done; 3.2 filters done; 3.3 route/profile filters done; 3.4 lanes done; 3.5 no-send outcome workflow active.
- P4 Promotion: 4.1 hold/needs-info/reject outcomes only; 4.2 approve/promote-to-pitch_ready not built; 4.3 launch readiness remains blocked.
- P5 GLM: 5.1 category counts pending; 5.2 briefs not started; 5.3 locked profile asset mapping pending.
- P6 Pitch packs: 6.1 batch dimensions pending; 6.2 GLM-locked asset routing pending; 6.3 draft generation/review pending.
- P7 Outreach readiness: 7.1 draft review pending; 7.2 send route confirmation pending; 7.3 final gate not started.
## Implementation State
- Added checkpointed Tabelog subarea scanning behind `--directory-scope subarea|both`; default city-wide directory behavior remains unchanged.
- Directory route recovery now follows same-site Japanese inquiry/contact links and expanded deterministic probes before persisting review-only cards.
- Live acquisition added 2 safe review cards, but expanded city/subarea directory yield remains low; ignored `state/` inventory changed locally, with no tracked state files.
- Dashboard review support from prior commits remains: outcome filter, unreviewed lane, progress stats, outcome badges, Save & Next/Next Unreviewed controls.
## Blockers / Next Work
- Five-city city-wide Tabelog source is exhausted through page 100 below the 400-card target; subarea probing improved route discovery but did not materially solve volume.
- Serper/webserper/Google Places API keys are missing or unavailable in this shell; provider-backed organic fallback is unavailable until access is restored.
- `audit-state` has reported pre-existing launch/smoke asset-profile drift; live no-send safety counters remain clean.
- Next lane: unlock a higher-yield source/provider or explicitly authorize use of blocked raw lead sources; otherwise keep no-send manual review of the 328 openable cards.
## Last Verification
- Tests: `tests/test_search.py -q` 56 passed; `tests/test_contact_crawler.py -q` 17 passed.
- Requested focused tests: `tests/test_website.py -q` 12 passed; `tests/test_api.py -q` 117 passed; `tests/test_restaurant_lead_verification.py -q` 40 passed.
- Live safety audit: 522 manual-review records; 0 ready_for_outreach, 0 pitch_ready, 0 `outreach_status:new`; no outreach happened.
