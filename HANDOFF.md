# WebRefurbMenu Handoff
Updated: 2026-05-02. Compact resume file; replace stale facts instead of appending logs.
Startup read path: read `AGENTS.md`, then this file only. Open long docs, raw leads, reports, or state artifacts only for a specific blocker.
## Safety Boundary
- No real email, contact-form submit, or other business contact unless explicitly requested in the current chat; "continue" means no-send work only.
- Approved routes are email and contact forms only; phone, LINE, Instagram, reservation links, social DMs, phone-required forms, walk-ins, map URLs, and websites are reference-only.
- During no-send inventory/review, do not set `pitch_ready=true`, `ready_for_outreach`, or `outreach_status=new`.
- Customer-facing copy must not mention AI, automation, scraping, or internal tools.
## Current Snapshot
- Branch: `codex/phase11-contact-form-batch`; unrelated pre-existing dirty files remain, so stage only mission files.
- Active workstream: no-send restaurant pitch-card inventory; all records remain manual-review blocked and unsendable.
- Live state: 596 records, 401 openable pitch cards, 193 hard blocked, 2 unsupported route.
- Pitch-card breakdown: 355 needs_email_review, 20 needs_name_review, 26 needs_scope_review.
- Safety counters: all 596 `launch_readiness_status=manual_review` and `outreach_status=needs_review`; 0 ready_for_outreach, 0 pitch_ready, 0 `outreach_status:new`.
- Dashboard server is live at `http://127.0.0.1:8000/` on PID 76776.
## Resume Phase State
- P0 Safety always active; no-send/no-promotion/manual-review constraints unchanged.
- P1 Corpus done through current imports; future imports keep manifest discipline.
- P2 Verification done for current queue; unresolved email/name/scope cases stay manual review.
- P3 Dashboard review active; no-send outcome workflow uses hold/needs_more_info/reject only.
- P4 Promotion not built; approve/promote-to-pitch_ready remains out of scope.
- P5 GLM category counts/routing active; locked profile asset mapping active.
- P6 Pitch packs active for review planning only; all batch/wave artifacts remain no-send.
- P7 Outreach readiness not started.
## Implementation State
- No-key `duckduckgo-contact` acquisition, Tabelog subarea scanning, and Japanese inquiry/contact route recovery remain available; provider-backed search is blocked.
- Live acquisition reached the 400-card target earlier: 401 openable cards across 596 records.
- `pipeline.cli review-batch` emits selected-batch GLM briefs, pitch-pack policies, and operator packs for one selected no-send batch.
- New `pipeline.cli review-wave` chunks all unreviewed approved-route pitch cards into no-send review batches and operator packs.
- Latest ignored artifacts: batch `pitch-card-review-20260502T145502Z.*` has 120 cards/7 GLM briefs/9 packs; wave `pitch-card-review-wave-20260502T150010Z.*` has 401 cards/4 batches/38 packs/10 GLM briefs.
- Wave GLM routing: 209 izakaya asset references, 192 ramen asset references; all review-only/no-send.
## Blockers / Next Work
- Serper still returns `Not enough credits`; Google Places key is unavailable; five-city directory source remains exhausted through page 100.
- Ignored `state/` inventory and review-batch artifacts changed locally; tracked code/handoff changes are the durable commit artifacts.
- `audit-state` previously reported pre-existing launch/smoke asset-profile drift; live no-send safety counters remain clean.
- Next lane: operator review wave batches in order, saving only hold/needs_more_info/reject outcomes.
## Last Verification
- Tests: `tests/test_website.py -q` 12 passed; `tests/test_api.py -q` 117 passed; `tests/test_restaurant_lead_verification.py -q` 40 passed; `tests/test_review_batches.py -q` 4 passed.
- Dashboard: PID 76776 listening on `127.0.0.1:8000`; GET `/` returned dashboard HTML.
- Live safety audit: 596 manual-review records; 0 ready_for_outreach, 0 pitch_ready, 0 `outreach_status:new`; no outreach happened.
