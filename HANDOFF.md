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

## Last Verified State

- The previous full test result was `.venv/bin/python -m pytest tests/ -q` with `332 passed`, before this new plan rewrite.
- After this plan rewrite, rerun Phase 0 commands before claiming current baseline.

## Resume Instructions

1. Read `PLAN.md`.
2. Start at Phase 0.
3. Compare implemented code against `PRODUCT_AUDIT_2026-04-29.md` and the exact phase acceptance criteria.
4. Do not use the obsolete long phase plan as guidance.
5. Do not start Phase 11 outreach until Phases 0-10 pass.
