# WebRefurbMenu Handoff

Updated: 2026-04-30

This file is intentionally compact. Do not use it as a running changelog. Record only the current checkpoint, next action, safety boundaries, and verification results. Put detailed logs in generated reports or small targeted docs so new chats do not start with stale context bloat.

## Source Of Truth

- Active product plan: `PLAN.md`
- Source audit: `PRODUCT_AUDIT_2026-04-29.md`
- Current no-send hardening plan: `PRODUCTION_SIMULATION_TEST_PLAN.md`

`PRODUCTION_SIMULATION_TEST_PLAN.md` is subordinate to `PLAN.md`; it does not replace the product audit plan. Do not resume from obsolete P0/P1/P2/P3/P4/P5/P6/P7 plan text.

## Safety Boundaries

- Japan only.
- Ramen and izakaya only.
- Binary lead semantics: `lead: true|false`, never "maybe".
- Customer-facing copy must not mention AI, automation, or internal tools.
- No real outreach has been sent in this thread.
- No real launch batch has been created in this thread.
- Production simulation must use isolated state and mocked send paths.
- `production_ready=true` in a simulation report is a no-send readiness signal only. Real outreach remains blocked until `PLAN.md` phase gates allow it.

## Current Checkpoint

Active work is at the boundary between the production-simulation/no-send gate and any future controlled launch selection work.

Current run:

- Run ID: `production-sim-live-pilot-20260429T142841Z`
- Stage: no-send real-world smoke and controlled-launch recommendation
- Report result: `production_ready=true` for the no-send simulation only
- Recommendation: `PROCEED_TO_CONTROLLED_BATCH_1_SELECTION`
- Findings: `P0=0`, `P1=0`, `P2=0`
- Corpus size: `1,852` raw candidates, `593` deduped/materialized candidates
- Labels: `593` finalized, `593` strict, `0` diagnostic
- Replay decisions: `63 ready`, `9 manual_review`, `521 disqualified`
- Package distribution for ready leads: `package_1_remote_30k=10`, `package_2_printed_delivered_45k=15`, `package_3_qr_menu_65k=38`
- Mock email payloads verified: `1`
- No-send smoke ID: `smoke-b26ed1e542`
- Smoke lead count: `5`
- Smoke lead IDs: `wrm-halal-ramen-ueno-japan-dd61`, `wrm-goen-japan-df06`, `wrm-kuraichi-286-sengokuhara-fb03`, `wrm-hokkai-ramen-sapporo-station-japan-05d0`, `wrm-sake-to-sakana-to-otokomae-shokudo-kyoto-station-japan-8039`
- Smoke checks: `15` source URLs checked, `0` failures, drafts verified, proof assets verified, inline assets verified, no contact marked
- External send performed: `false`
- Real launch batch created: `false`
- Real outreach performed: `false`
- Isolated simulation state was mutated only to generate no-send drafts and the smoke rehearsal record. No live lead state was mutated.

## What Changed Recently

Keep this section short. The detailed implementation trail lives in tests, generated reports, and git diff.

- `pipeline.cli production-sim recommend` now runs the no-send smoke gate, prepares no-send drafts in isolated state, verifies source URLs/proof assets/inline assets/no-contact status, and writes the controlled-launch recommendation into `report.json` and `report.md`.
- `pipeline.launch_smoke` can prepare no-send draft metadata before applying the same launch lead gates.
- Regression tests cover proceed and block recommendation paths.

Positive effect: the recommendation gate now catches launch-selection readiness gaps that the replay oracle alone can miss, while still proving no send or real launch batch occurred.

## Key Runtime Artifacts

- Corpus: `state/search-replay/production-sim-live-pilot-20260429T142841Z/`
- Final labels: `state/search-replay/production-sim-live-pilot-20260429T142841Z/labels/`
- Labeling summary: `state/search-replay/production-sim-live-pilot-20260429T142841Z/labeling/summary.json`
- Report JSON: `state/production-sim/production-sim-live-pilot-20260429T142841Z/report.json`
- Report Markdown: `state/production-sim/production-sim-live-pilot-20260429T142841Z/report.md`
- Controlled recommendation JSON: `state/production-sim/production-sim-live-pilot-20260429T142841Z/controlled-launch-recommendation.json`
- Decisions: `state/production-sim/production-sim-live-pilot-20260429T142841Z/decisions.json`
- Mock email payloads: `state/production-sim/production-sim-live-pilot-20260429T142841Z/mock-email-payloads.json`
- Screenshot manifest: `state/production-sim/production-sim-live-pilot-20260429T142841Z/screenshot-manifest.json`
- Screenshots: `state/qa-screenshots/production-sim-live-pilot-20260429T142841Z/`
- No-send smoke: `state/production-sim/production-sim-live-pilot-20260429T142841Z/state/launch_smoke_tests/smoke-b26ed1e542.json`
- Supplemental source artifacts: `state/search-replay/production-sim-live-pilot-20260429T142841Z/pages/wrm-replay-supp-*/` and `state/search-replay/production-sim-live-pilot-20260429T142841Z/serper/wrm-replay-supp-*-supplemental-source.json`

## Last Verified Commands

- `.venv/bin/python -m pipeline.cli production-sim recommend --run production-sim-live-pilot-20260429T142841Z --lead-id wrm-halal-ramen-ueno-japan-dd61 --lead-id wrm-goen-japan-df06 --lead-id wrm-kuraichi-286-sengokuhara-fb03 --lead-id wrm-hokkai-ramen-sapporo-station-japan-05d0 --lead-id wrm-sake-to-sakana-to-otokomae-shokudo-kyoto-station-japan-8039 --fail-on p0,p1` passed with `P0=0`, `P1=0`, `P2=0`, `PROCEED_TO_CONTROLLED_BATCH_1_SELECTION`, `source_urls_checked=15`
- `.venv/bin/python -m pipeline.cli production-sim report --run production-sim-live-pilot-20260429T142841Z --fail-on p0,p1` passed with `P0=0`, `P1=0`, `P2=0`, `production_ready=true`, `ready/manual/disqualified=63/9/521`
- `.venv/bin/python -m pytest tests/test_production_simulation.py tests/test_dashboard_production_simulation.py tests/test_launch_smoke.py -q` passed with `20 passed`
- `.venv/bin/python -m pytest tests/ -q` passed with `480 passed`
- `.venv/bin/python -m pipeline.cli audit-state` passed with `ok=true`, `checked=33`, `findings=[]`, `readiness_report=[]`
- `git diff --check` was clean
- `git status --short` shows the implementation worktree is still dirty; real runtime artifacts remain under ignored `state/` paths.

No real outreach was sent. No real launch batch was created. No live lead state was mutated.

## Resume Instructions

1. Read `PLAN.md`.
2. Read `PRODUCTION_SIMULATION_TEST_PLAN.md` only for the current simulation gate and acceptance criteria.
3. Use this file as the compact current checkpoint, not as proof that a phase is complete.
4. Treat the current production simulation report as a no-send readiness signal only. Do not send outreach or create a real launch batch from it.
5. The no-send smoke / controlled-launch recommendation path has passed. The next decision is whether to explicitly begin `PLAN.md` Phase 11 controlled Batch 1 selection.
6. Keep real batch selection/outreach blocked until the user explicitly directs controlled launch work.
7. After each completed phase or simulation slice, update this handoff by replacing stale checkpoint details instead of appending a long diary.
