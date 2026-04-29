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
- Approved outreach/contact routes are email and contact forms only.
- Phone, Instagram, LINE, and walk-in routes are reference-only metadata. They never make a lead launch-ready and cannot be selected for outreach.
- Do not consider phone-only leads launch-ready.
- Real outreach has occurred only for selected Batch 1 through approved routes: one email and four contact forms. No phone call, Instagram DM, LINE message, or walk-in contact has been performed.
- Production simulation must use isolated state and mocked send paths.
- `production_ready=true` in a simulation report is a no-send readiness signal only. Do not start more real outreach until Phase 12 review allows it.
- Do not start Batch 2 before Phase 12.
- When the user pastes resume instructions or says "continue", treat that as approval to continue the current `PLAN.md` phase as far as safely possible. Do not stop after one small substep if the next same-phase action is unblocked.
- Stop only at a phase gate, a failing verification gate, an unavailable external credential/channel, a required human-only action, a user redirect, any action that would start Batch 2, or any real send/contact step the user has not explicitly directed.
- Stop early if context bloat is noticeably affecting output quality, accuracy, or the ability to preserve the current state. Before stopping, update this handoff with the current checkpoint and next action.

## Current Checkpoint

`PLAN.md` Phase 12 Batch Review is complete for Batch 1. The Batch 1 review is saved in the local launch batch record; no Batch 2 selection, creation, send, contact, phone call, Instagram DM, LINE message, or walk-in contact has been performed.

Current controlled Batch 1:

- Batch ID: `launch-18ce5c756f`
- Batch path: `state/launch_batches/launch-18ce5c756f.json`
- Active lead count: `5`
- Reviewed at: `2026-04-29T23:52:39+00:00`
- No-send repair smoke ID: `smoke-12995a1657`
- Required mix satisfied: `ramen_ticket_machine=true`, `izakaya_drink_or_course=true`
- Backup before repair: `state/backups/webrefurb-state-20260429T180437+0000.zip`

Phase 12 review summary:

- Contacted leads: `5/5`
- Response rate: `0/5` (`0.0`)
- Positive replies: `0`
- Objections: `0`
- Opt-outs: `0`
- Bounces: `0`
- No replies/waiting: `5`
- Operator time: `17` total minutes, `3.4` average minutes per contacted lead
- Channel performance: email `1 contacted / 0 responses`; contact forms `4 contacted / 0 responses`
- Package mix reviewed: Package 1 `2`, Package 2 `1`, Package 3 `2`
- Proof performance: no proof asset or customer-safe proof path produced a reply yet

Phase 12 iteration decision:

- Scoring update: no change; zero replies, objections, opt-outs, or bounces provide no scoring signal.
- Search terms update: no change; no-reply outcomes alone do not identify stronger or weaker search terms.
- Outreach wording update: no change; no owner reply or objection identified a wording issue.
- Package recommendation update: no change; no package-fit objection or conversion was observed.
- Proof asset update: no change; contact-form leads used customer-safe proof context without attachments.
- Batch 2 guidance if Phase 13 proceeds: keep volume at the minimum controlled size until replies create a stronger profile signal.

Active Batch 1 measured leads:

- `wrm-kuraichi-286-sengokuhara-fb03` — Kuraichi, email, `reply_status=no_reply`, `operator_minutes=1`, `bounce=false`, `opt_out=false`.
- `wrm-lead-2-12-5-2392` — つけ麺さか田, contact form, ramen ticket-machine replacement, `reply_status=no_reply`, `operator_minutes=4`, `bounce=false`, `opt_out=false`.
- `wrm-koshitsu-sosakuryori-musubi-namba-japan-ee35` — Koshitsu Sosakuryori MUSUBI Namba, contact form, izakaya drink/nomihodai replacement, `reply_status=no_reply`, `operator_minutes=4`, `bounce=false`, `opt_out=false`.
- `wrm-guusan-chi-a-home-style-izakaya-2-chome-9-16-hosai-f672` — Guusan-chi, contact form, izakaya drink/nomihodai replacement, `reply_status=no_reply`, `operator_minutes=4`, `bounce=false`, `opt_out=false`.
- `wrm-tonkotsu-ramen-tatsu-9-18-konohanamachi-d2b8` — Tonkotsu-Ramen Tatsu, contact form, ramen replacement, `reply_status=no_reply`, `operator_minutes=4`, `bounce=false`, `opt_out=false`.

Current simulation signal remains no-send only:

- Run ID: `production-sim-live-pilot-20260429T142841Z`
- Report result: `production_ready=true` for simulation only
- Findings: `P0=0`, `P1=0`, `P2=0`
- Replay decisions: `63 ready`, `9 manual_review`, `521 disqualified`
- The simulation report is not proof that any real-send phase is complete.

## What Changed Recently

- Added structured Phase 12 launch-batch review metrics to `pipeline.launch.review_launch_batch` and the dashboard review API.
- Recorded the Batch 1 Phase 12 review in `state/launch_batches/launch-18ce5c756f.json`.
- Outreach policy was corrected across code, tests, plan docs, dashboard labels, and contact crawling: only email and contact forms are supported outreach routes.
- Phone, Instagram, LINE, and walk-in routes were made non-actionable/reference-only; unsupported manual copy/status paths were removed.
- Runtime lead state was repaired so zero phone/Instagram/LINE/walk-in contacts remain raw-actionable.
- Batch 1 live state was repaired to remove unsupported phone/Instagram selections, then sent through one email and four contact forms.
- らーめん次郎冠者 was materialized from official pages and attempted through its official contact form, but the form failed server-side and the lead was replaced.
- つけ麺さか田 was materialized from official pages with official menu/ticket-machine evidence and an official contact-form route.
- Three replacements were materialized from the prior no-send simulation state.
- A no-send smoke test validated the repaired five-lead batch without external contact.

Positive effect: Phase 12 now gates Batch 2 on recorded outcome data instead of volume pressure or assumptions.

## Key Runtime Artifacts

- Corpus: `state/search-replay/production-sim-live-pilot-20260429T142841Z/`
- Report JSON: `state/production-sim/production-sim-live-pilot-20260429T142841Z/report.json`
- Decisions: `state/production-sim/production-sim-live-pilot-20260429T142841Z/decisions.json`
- Controlled Batch 1: `state/launch_batches/launch-18ce5c756f.json`
- Repair no-send smoke: `state/launch_smoke_tests/smoke-12995a1657.json`
- Sent email record: `state/sent/wrm-kuraichi-286-sengokuhara-fb03_20260429173017.json`
- Contact-form submission artifacts: `state/contact_form_submissions/20260429T185616Z/`
- Active Batch 1 leads: `state/leads/wrm-kuraichi-286-sengokuhara-fb03.json`, `state/leads/wrm-lead-2-12-5-2392.json`, `state/leads/wrm-koshitsu-sosakuryori-musubi-namba-japan-ee35.json`, `state/leads/wrm-guusan-chi-a-home-style-izakaya-2-chome-9-16-hosai-f672.json`, `state/leads/wrm-tonkotsu-ramen-tatsu-9-18-konohanamachi-d2b8.json`
- Failed contact-form artifacts: `state/contact_form_submissions/20260429T184640Z/`
- Removed unsupported leads: `state/leads/wrm-halal-ramen-ueno-japan-dd61.json`, `state/leads/wrm-goen-japan-df06.json`, `state/leads/wrm-hokkai-ramen-sapporo-station-japan-05d0.json`, `state/leads/wrm-sake-to-sakana-to-otokomae-shokudo-kyoto-station-japan-8039.json`

## Last Verified Commands

- `.venv/bin/python -m pytest tests/test_launch.py -q` passed with `5 passed`
- `.venv/bin/python -m pytest tests/test_api.py -q -k 'launch_batch_api_blocks_second_batch_until_review'` passed with `1 passed, 107 deselected`
- `.venv/bin/python -m pytest tests/ -q` passed with `477 passed`
- `.venv/bin/python -m pipeline.cli audit-state` passed with `ok=true`, `checked=45`, `findings=[]`, `readiness_report=[]`
- `git diff --check` was clean
- Real Batch 1 sends and the Phase 12 review are recorded in `state/launch_batches/launch-18ce5c756f.json`: one email and four contact forms, all currently `no_reply`.

## Resume Instructions

1. Read `PLAN.md`.
2. Read `PRODUCTION_SIMULATION_TEST_PLAN.md` only for the current simulation gate and acceptance criteria.
3. Use this file as the compact current checkpoint, not as proof that a phase is complete.
4. Treat the current production simulation report as a no-send readiness signal only; Batch 1 selection exists separately in live state.
5. Continue mode: if the user pasted these resume instructions or says "continue", proceed through all remaining actionable work in the current phase, not just the next numbered step.
6. Next action: Phase 13 Batch 2 And Repeatable Launch Loop, only if explicitly continuing past this phase gate.
7. Do not use phone, Instagram, LINE, or walk-in routes for outreach. Do not select phone-only leads.
8. Phase 12 review is recorded; any Batch 2 work must follow `PLAN.md` Phase 13 and preserve the email/contact-form-only route policy.
9. Before any Batch 2 selection or send, check for new Batch 1 replies/bounces/opt-outs and update `state/launch_batches/launch-18ce5c756f.json` plus the corresponding lead files if anything changed.
10. If context bloat starts affecting output quality or accuracy, stop after updating this handoff rather than continuing the next work slice.
11. After each completed phase, simulation slice, or real-send slice, update this handoff by replacing stale checkpoint details instead of appending a long diary.
