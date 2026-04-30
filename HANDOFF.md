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
- Stop only at a phase gate, a failing verification gate, an unavailable external credential/channel, a required human-only action, a user redirect, or any Batch 2 send/contact step the user has not explicitly directed.
- Stop early if context bloat is noticeably affecting output quality, accuracy, or the ability to preserve the current state. Before stopping, update this handoff with the current checkpoint and next action.

## Current Checkpoint

`PLAN.md` Phase 13 Batch 2 pre-send selection is complete. Batch 1 Phase 12 review is saved, no new Batch 1 replies/bounces/opt-outs were found, and Batch 2 has been created as a local launch-batch record with no external contact performed. Stop here before any Batch 2 email or contact-form submission unless the user explicitly directs a Batch 2 send/contact slice.

Current controlled Batch 1 review:

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

Current controlled Batch 2 pre-send record:

- Batch ID: `launch-6f594101ca`
- Batch path: `state/launch_batches/launch-6f594101ca.json`
- Created at: `2026-04-30T00:13:54+00:00`
- Active lead count: `5`
- Reviewed at: empty, because no Batch 2 outreach or measurement has occurred
- No-send smoke ID: `smoke-c1bae62975`
- Required mix satisfied: `ramen_ticket_machine=true`, `izakaya_drink_or_course=true`
- External send/contact performed: `false`
- Batch 2 lead records now carry `launch_batch_id=launch-6f594101ca`; all keep `launch_outcome={}`, `contacted_at=""`, and `reply_status=not_contacted`.

Active Batch 2 selected leads:

- `wrm-lead-492-1-d7a2` — 黄金トマトのカル麺, contact form, ramen ticket-machine lead, Package 2, no contact performed.
- `wrm-hakoya-meieki-shop-japan-a49c` — Hakoya Meieki shop, contact form, izakaya drink/nomihodai lead, Package 3, no contact performed.
- `wrm-kyoto-ramen-kinzan-japan-a54f` — Kyoto Ramen KINZAN, contact form, ramen-only lead, Package 1, no contact performed.
- `wrm-tokyo-underground-ramen-japan-6dda` — 東京アンダーグラウンドラーメン 頑者（TOKYO UNDERGROUND RAMEN 頑者） - 池袋（つけ麺）, email, ramen-only lead, Package 2, no contact performed.
- `wrm-lead-lead-fb50` — 創作個室居酒屋すぎうら, contact form, izakaya course/drink lead, Package 3, no contact performed.

Batch 2 exclusions recorded in `phase_13_selection_review`:

- `wrm-jikaseimen-223-okubo-ramen-japan-0b38`: Twitter/X URL was previously treated as a contact form; unsupported route.
- `wrm-lead-312-6-f1c0`: prior official contact-form attempt failed server-side; not safe for Batch 2.
- `wrm-qa-phase10-ramen`: QA/test fixture.
- `wrm-smoke-mensaibo-nakano`: smoke rehearsal only.
- Batch 1 leads: already contacted in controlled Batch 1.

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
- Phase 13 Batch 2 was selected at the minimum controlled size after confirming the Batch 1 review and no new replies/bounces/opt-outs.
- Batch 2 no-send smoke `smoke-c1bae62975` and launch batch `launch-6f594101ca` were recorded without any external email or contact-form submission.

Positive effect: Batch 2 is now constrained to a measured pre-send record, so the next operator can send only the selected leads and then review outcomes instead of improvising volume.

## Key Runtime Artifacts

- Corpus: `state/search-replay/production-sim-live-pilot-20260429T142841Z/`
- Report JSON: `state/production-sim/production-sim-live-pilot-20260429T142841Z/report.json`
- Decisions: `state/production-sim/production-sim-live-pilot-20260429T142841Z/decisions.json`
- Controlled Batch 1: `state/launch_batches/launch-18ce5c756f.json`
- Controlled Batch 2 pre-send record: `state/launch_batches/launch-6f594101ca.json`
- Repair no-send smoke: `state/launch_smoke_tests/smoke-12995a1657.json`
- Batch 2 no-send smoke: `state/launch_smoke_tests/smoke-c1bae62975.json`
- Sent email record: `state/sent/wrm-kuraichi-286-sengokuhara-fb03_20260429173017.json`
- Contact-form submission artifacts: `state/contact_form_submissions/20260429T185616Z/`
- Active Batch 1 leads: `state/leads/wrm-kuraichi-286-sengokuhara-fb03.json`, `state/leads/wrm-lead-2-12-5-2392.json`, `state/leads/wrm-koshitsu-sosakuryori-musubi-namba-japan-ee35.json`, `state/leads/wrm-guusan-chi-a-home-style-izakaya-2-chome-9-16-hosai-f672.json`, `state/leads/wrm-tonkotsu-ramen-tatsu-9-18-konohanamachi-d2b8.json`
- Failed contact-form artifacts: `state/contact_form_submissions/20260429T184640Z/`
- Removed unsupported leads: `state/leads/wrm-halal-ramen-ueno-japan-dd61.json`, `state/leads/wrm-goen-japan-df06.json`, `state/leads/wrm-hokkai-ramen-sapporo-station-japan-05d0.json`, `state/leads/wrm-sake-to-sakana-to-otokomae-shokudo-kyoto-station-japan-8039.json`

## Last Verified Commands

- `.venv/bin/python -m pytest tests/ -q` passed with `477 passed`
- `.venv/bin/python -m pipeline.cli audit-state` passed with `ok=true`, `checked=51`, `findings=[]`, `readiness_report=[]`
- `git diff --check` was clean
- Batch 1 Phase 12 review remains recorded in `state/launch_batches/launch-18ce5c756f.json`.
- Batch 2 pre-send record is `state/launch_batches/launch-6f594101ca.json`; all selected leads are `not_contacted` with no external send/contact performed.

## Resume Instructions

1. Read `PLAN.md`.
2. Read `PRODUCTION_SIMULATION_TEST_PLAN.md` only for the current simulation gate and acceptance criteria.
3. Use this file as the compact current checkpoint, not as proof that a phase is complete.
4. Treat the current production simulation report as a no-send readiness signal only; Batch 1 selection exists separately in live state.
5. Continue mode: if the user pasted these resume instructions or says "continue", proceed through all remaining actionable work in the current phase, not just the next numbered step.
6. Next action: stop at the Phase 13 pre-send gate. Do not submit Batch 2 email/contact forms unless the user explicitly directs a Batch 2 send/contact slice.
7. Do not use phone, Instagram, LINE, or walk-in routes for outreach. Do not select phone-only leads.
8. Phase 12 review is recorded; Batch 2 selection has been recorded under `launch-6f594101ca` and preserves the email/contact-form-only route policy.
9. Before any Batch 2 send/contact action, check for new Batch 1 replies/bounces/opt-outs and update `state/launch_batches/launch-18ce5c756f.json` plus the corresponding lead files if anything changed.
10. If context bloat starts affecting output quality or accuracy, stop after updating this handoff rather than continuing the next work slice.
11. After each completed phase, simulation slice, or real-send slice, update this handoff by replacing stale checkpoint details instead of appending a long diary.
