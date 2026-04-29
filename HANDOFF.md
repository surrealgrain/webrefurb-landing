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

`PLAN.md` Phase 11 step 7/8 is complete for Batch 1. Batch 1 was sent only through approved email/contact-form routes, and every contacted lead has measurement fields recorded. The next phase gate is Phase 12 Batch Review; do not start Batch 2.

Current controlled Batch 1:

- Batch ID: `launch-18ce5c756f`
- Batch path: `state/launch_batches/launch-18ce5c756f.json`
- Active lead count: `5`
- No-send repair smoke ID: `smoke-12995a1657`
- Required mix satisfied: `ramen_ticket_machine=true`, `izakaya_drink_or_course=true`
- Backup before repair: `state/backups/webrefurb-state-20260429T180437+0000.zip`

Measured Batch 1 leads:

- `wrm-kuraichi-286-sengokuhara-fb03` — Kuraichi, email, `contacted_at=2026-04-29T17:30:17.575364+00:00`, `reply_status=no_reply`, `operator_minutes=1`, `outcome=sent_waiting_for_reply`, `bounce=false`, `opt_out=false`.
- `wrm-lead-2-12-5-2392` — つけ麺さか田, contact form, ramen ticket-machine replacement, `contacted_at=2026-04-29T18:58:50+00:00`, `reply_status=no_reply`, `operator_minutes=4`, `outcome=contact_form_submitted_waiting_for_reply`, `bounce=false`, `opt_out=false`.
- `wrm-koshitsu-sosakuryori-musubi-namba-japan-ee35` — Koshitsu Sosakuryori MUSUBI Namba, contact form, izakaya drink/nomihodai replacement, `contacted_at=2026-04-29T18:58:50+00:00`, `reply_status=no_reply`, `operator_minutes=4`, `outcome=contact_form_submitted_waiting_for_reply`, `bounce=false`, `opt_out=false`.
- `wrm-guusan-chi-a-home-style-izakaya-2-chome-9-16-hosai-f672` — Guusan-chi, contact form, izakaya drink/nomihodai replacement, `contacted_at=2026-04-29T18:58:50+00:00`, `reply_status=no_reply`, `operator_minutes=4`, `outcome=contact_form_submitted_waiting_for_reply`, `bounce=false`, `opt_out=false`.
- `wrm-tonkotsu-ramen-tatsu-9-18-konohanamachi-d2b8` — Tonkotsu-Ramen Tatsu, contact form, ramen replacement, `contacted_at=2026-04-29T18:58:50+00:00`, `reply_status=no_reply`, `operator_minutes=4`, `outcome=contact_form_submitted_waiting_for_reply`, `bounce=false`, `opt_out=false`.

Contact-form submission artifact:

- `state/contact_form_submissions/20260429T185616Z`

Failed/replaced contact-form attempt:

- `wrm-lead-312-6-f1c0` — らーめん次郎冠者, attempted via official contact form, server returned a Lolipop CGI/SSI error after submission. It is not counted as contacted and was replaced by `wrm-lead-2-12-5-2392`.
- Artifact directory: `state/contact_form_submissions/20260429T184640Z`

Removed unsupported original selections remain recorded in the batch:

- `wrm-halal-ramen-ueno-japan-dd61`
- `wrm-goen-japan-df06`
- `wrm-hokkai-ramen-sapporo-station-japan-05d0`
- `wrm-sake-to-sakana-to-otokomae-shokudo-kyoto-station-japan-8039`

Current simulation signal remains no-send only:

- Run ID: `production-sim-live-pilot-20260429T142841Z`
- Report result: `production_ready=true` for simulation only
- Findings: `P0=0`, `P1=0`, `P2=0`
- Replay decisions: `63 ready`, `9 manual_review`, `521 disqualified`
- The simulation report is not proof that Phase 11 is complete.

## What Changed Recently

- Outreach policy was corrected across code, tests, plan docs, dashboard labels, and contact crawling: only email and contact forms are supported outreach routes.
- Phone, Instagram, LINE, and walk-in routes were made non-actionable/reference-only; unsupported manual copy/status paths were removed.
- Runtime lead state was repaired so zero phone/Instagram/LINE/walk-in contacts remain raw-actionable.
- Batch 1 live state was repaired to remove unsupported phone/Instagram selections, then sent through one email and four contact forms.
- らーめん次郎冠者 was materialized from official pages and attempted through its official contact form, but the form failed server-side and the lead was replaced.
- つけ麺さか田 was materialized from official pages with official menu/ticket-machine evidence and an official contact-form route.
- Three replacements were materialized from the prior no-send simulation state.
- A no-send smoke test validated the repaired five-lead batch without external contact.

Positive effect: Phase 11 now has a measured five-lead Batch 1 without using any phone, Instagram, LINE, or walk-in outreach path.

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

- `.venv/bin/python -m pytest tests/ -q` passed with `476 passed`
- `.venv/bin/python -m pipeline.cli audit-state` passed with `ok=true`, `checked=45`, `findings=[]`, `readiness_report=[]`
- `git diff --check` was clean
- Real Batch 1 sends are recorded in `state/launch_batches/launch-18ce5c756f.json`: one email and four contact forms.

## Resume Instructions

1. Read `PLAN.md`.
2. Read `PRODUCTION_SIMULATION_TEST_PLAN.md` only for the current simulation gate and acceptance criteria.
3. Use this file as the compact current checkpoint, not as proof that a phase is complete.
4. Treat the current production simulation report as a no-send readiness signal only; Batch 1 selection exists separately in live state.
5. Continue mode: if the user pasted these resume instructions or says "continue", proceed through all remaining actionable work in the current phase, not just the next numbered step.
6. Next action: Phase 12 Batch Review. Review Batch 1 outcomes and replies before any Batch 2 selection or send.
7. Do not use phone, Instagram, LINE, or walk-in routes for outreach. Do not select phone-only leads.
8. Do not start Batch 2 until Phase 12 review is recorded.
9. Watch for replies/bounces/opt-outs and update `state/launch_batches/launch-18ce5c756f.json` plus the corresponding lead files before summarizing Phase 12.
10. If context bloat starts affecting output quality or accuracy, stop after updating this handoff rather than continuing the next work slice.
11. After each completed phase, simulation slice, or real-send slice, update this handoff by replacing stale checkpoint details instead of appending a long diary.
