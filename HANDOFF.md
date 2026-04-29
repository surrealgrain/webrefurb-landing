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
- No real outreach was sent.

## Resume Instructions

1. Read `PLAN.md`.
2. Start at Phase 0.
3. Compare implemented code against `PRODUCT_AUDIT_2026-04-29.md` and the exact phase acceptance criteria.
4. Do not use the obsolete long phase plan as guidance.
5. Do not start Phase 11 outreach until Phases 0-10 pass.
