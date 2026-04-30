# WebRefurbMenu Handoff

Updated: 2026-04-30

This file is intentionally compact. Do not use it as a running changelog. Record only the current checkpoint, next action, safety boundaries, and verification results. Put detailed logs in generated reports or small targeted docs so new chats do not start with stale context bloat.

## Source Of Truth

- Active product plan: `PLAN.md`
- Source audit: `PRODUCT_AUDIT_2026-04-29.md`
- Current no-send hardening plan: `PRODUCTION_SIMULATION_TEST_PLAN.md`

`PRODUCTION_SIMULATION_TEST_PLAN.md` is subordinate to `PLAN.md`; it does not replace the product audit plan. Do not resume from obsolete P0/P1/P2/P3/P4/P5/P6/P7 plan text.

## Safety Boundaries

- ABSOLUTE OUTBOUND RULE: do not send any real email, submit any real contact form, or otherwise contact a business unless the user explicitly requests that exact outbound send/contact action in the current chat. The word "continue" is not enough permission for real outreach.
- Treat future continuation as permission to keep executing every non-outbound step that is technically and plan-wise unblocked. Selection, scoring, validation, draft generation, simulations, audits, reviews, state repairs, and test-backed hardening are safe; real email/contact-form submission is not safe without explicit user approval.
- Japan only.
- Ramen and izakaya only.
- Binary lead semantics: `lead: true|false`, never "maybe".
- Customer-facing copy must not mention AI, automation, or internal tools.
- Approved outreach/contact routes are email and contact forms only.
- Phone, Instagram, LINE, and walk-in routes are reference-only metadata. They never make a lead launch-ready and cannot be selected for outreach.
- Do not consider phone-only leads launch-ready.
- Real outreach has occurred for selected Batch 1 and Batch 2 through approved routes only: Batch 1 had one email and four contact forms; Batch 2 had one email and three submitted contact forms. No phone call, Instagram DM, LINE message, or walk-in contact has been performed.
- Production simulation must use isolated state and mocked send paths.
- `production_ready=true` in a simulation report is a no-send readiness signal only. It is not permission to send real outreach.
- Do not start Batch 2 before Phase 12.
- When the user pastes resume instructions or says "continue", treat that as approval to continue no-send work as far as safely possible across the active `PLAN.md` and `PRODUCTION_SIMULATION_TEST_PLAN.md` tracks. Run the next pass as a long work block; do not stop after one numbered substep, one verification run, one small bugfix, one commit, or one outbound-only gate if more no-send work is available.
- Outbound gates are not general stop points. If the next real email/contact-form action is blocked, switch to the next safe no-send task: reply/bounce/opt-out checks, batch review reconciliation, route-validation hardening, simulation coverage, dashboard QA, state audit repair, candidate preparation without contact, or tests.
- Stop only at a failing verification gate, an unavailable external credential/channel required for no-send work, a required human-only decision with no safe parallel no-send task, a user redirect, severe context bloat, or after all useful no-send work in the current plan slice is exhausted.
- Stop early if context bloat is noticeably affecting output quality, accuracy, or the ability to preserve the current state. Before stopping, update this handoff with the current checkpoint and next action.

## Current Checkpoint

`PLAN.md` Phase 13 Batch 2 send/contact and repeat review are complete. The follow-on no-send hardening block is also complete: Batch 1/2 outcomes were reconciled, route preflight was hardened, the stale broad simulation was replayed under the current email/contact-form-only policy, and a Batch 3 no-send decision brief was generated.

Current decision: hold real Batch 3 outbound. Do not send Batch 3 email/contact forms or submit any new real contact without an explicit user request for that exact outbound action. The no-send Batch 3 decision brief found `9` prior contacts, `0` owner responses, `1` route failure, `0` matched reply artifacts, and `0` eligible live Batch 3 candidates after excluding already-contacted leads, fixtures, unsupported routes, and review-required records.

Controlled Batch 1 remains reviewed:

- Batch ID: `launch-18ce5c756f`
- Reviewed at: `2026-04-29T23:52:39+00:00`
- Summary: `5/5` contacted, `0` replies, `0` positives, `0` objections, `0` opt-outs, `0` bounces.

Controlled Batch 2 review:

- Batch ID: `launch-6f594101ca`
- Batch path: `state/launch_batches/launch-6f594101ca.json`
- Created at: `2026-04-30T00:13:54+00:00`
- Reviewed at: `2026-04-30T00:57:43+00:00`
- Lead count: `5`
- Contacted count: `4`
- Response rate: `0/4` (`0.0`)
- Positive replies: `0`
- Objections: `0`
- Opt-outs: `0`
- Bounces: `0`
- No replies/waiting: `4`
- Operator time counted for contacted leads: `13` total minutes, `3.25` average minutes per contacted lead
- Channel performance: email `1 contacted / 0 responses`; contact forms `3 contacted / 0 responses`; contact-form channel failure `1`
- Package mix contacted: Package 1 `2`, Package 2 `1`, Package 3 `1`

Batch 2 final lead outcomes:

- `wrm-lead-492-1-d7a2` — 黄金トマトのカル麺, BASE contact form submitted, `reply_status=no_reply`, artifacts `state/contact_form_submissions/20260430T005242Z/`.
- `wrm-lead-605-0083-416-6d57` — らーめん錦, email sent through dashboard/Resend, `reply_status=no_reply`, sent record `state/sent/wrm-lead-605-0083-416-6d57_20260430004333.json`.
- `wrm-kyoto-ramen-kinzan-japan-a54f` — Kyoto Ramen KINZAN, BASE contact form submitted, `reply_status=no_reply`, artifacts `state/contact_form_submissions/20260430T005242Z/`.
- `wrm-ichinohajimari-kyoto-izakaya-7f4a` — いちのはじまり, official contact form submitted, `reply_status=no_reply`, artifacts `state/contact_form_submissions/20260430T005546Z/`.
- `wrm-lead-lead-fb50` — 創作個室居酒屋すぎうら, not contacted; official form required phone data, no phone data was invented, no restaurant form submission POST was observed, lead is now `do_not_contact` / `manual_review`.

Batch 2 replacements and route repairs:

- `wrm-hakoya-meieki-shop-japan-a49c` removed before send because the official page exposed phone/HotPepper reservation paths, not an approved inquiry/contact form.
- `wrm-lead-605-0083-416-6d57` らーめん錦 added as Hakoya replacement with approved email route.
- `wrm-tokyo-underground-ramen-japan-6dda` removed before external send because the dashboard guard identified it as `smoke_rehearsal_only=true`.
- `wrm-ichinohajimari-kyoto-izakaya-7f4a` いちのはじまり added as Tokyo replacement with approved contact-form route.
- Latest repaired no-send smoke ID: `smoke-850d05261f`.

Phase 13 repeat-review decision:

- Scoring update: no change; zero owner replies, objections, opt-outs, bounces, or conversions.
- Search terms update: no change; no owner-response signal yet.
- Outreach wording update: no change; no reply or objection identified a copy issue.
- Package recommendation update: no change; no package-fit objection or conversion.
- Proof asset update: no change; no proof path produced a reply yet.
- Contact-route validation update: preflight now treats phone-required, reservation/booking, recruiting, commerce/order, account/login, and social-profile "forms" as unsupported outreach routes unless a real supported inquiry route is present.
- Batch 3 guidance: do not send any Batch 3 email/contact form unless the user explicitly asks for that exact outbound action. No-send Batch 3 preparation is allowed: checking replies/bounces/opt-outs, finding candidates, validating routes, drafting copy, running smoke tests, and writing a human decision brief, as long as no business is contacted.

Current no-send simulation signal:

- Latest route-policy replay ID: `production-sim-route-policy-screenshots-fixed-20260430T000000Z`
- Report result: `production_ready=false` because `P2=1`; `P0=0`, `P1=0`
- Replay decisions after route-policy reconciliation: `6 ready`, `66 manual_review`, `521 disqualified`
- External send performed: `false`
- Real launch batch created: `false`
- Remaining P2: supported-route expected-ready coverage is too thin after removing phone/social/walk-in labels (`6` expected-ready labels; required minimum is `20` and profile coverage is short).

Next safe no-send work block:

1. Fix or replace the Serper maps collection path, which returned HTTP 400 for the targeted no-send expansion run `production-sim-supported-route-expansion-20260430T0135Z`.
2. Collect or materialize more Japan ramen/izakaya candidates with real email/contact-form inquiry routes; do not contact them.
3. Promote only evidence-reviewed supported-route candidates into high-confidence labels until the simulation has at least `20` expected-ready labels across the required positive profiles.
4. Rerun production simulation with screenshots and keep `P0=0`, `P1=0`; then rerun `launch-decision`.

## What Changed Recently

- Phase 13 Batch 2 was selected, repaired, sent/contacted through approved routes, measured, and reviewed.
- Hakoya was removed for unsupported route; Tokyo Underground was removed because it was a smoke-only fixture.
- らーめん錦 and いちのはじまり were materialized from official pages as Batch 2 replacements.
- Three Batch 2 contact forms were submitted successfully; one Batch 2 email was sent successfully.
- Sugiura’s form was not submitted because it required phone data; it is now reference-only/do-not-contact.
- `pipeline.lead_dossier` now treats contact forms marked phone-required as unsupported outreach routes, with test coverage.
- Future sent email records now persist attachment metadata: requested source paths, render-source flags, inline attachment filename/MIME/content-id/disposition/size/SHA-256, and file-attachment metadata. The existing らーめん錦 sent record was backfilled from local renderer state.
- Important correction: prior "continue" handling was too broad. Future sessions must keep "continue" as no-send continuation only unless the user explicitly asks to send real outreach.
- Route preflight is now centralized in `pipeline.contact_policy` and preserves form metadata from crawled HTML. Unsupported forms include phone-required, reservation/booking, recruiting, commerce/order, account/login, and social-profile masquerading as contact-form routes.
- Production-sim labels were reconciled to the current outreach route policy; unsupported legacy `phone`, `LINE`, `Instagram`, and `walk_in` ready labels were moved to `manual_review`/`none`.
- Dashboard screenshot simulation now selects actual dashboard-renderable ready/manual/disqualified records instead of stale expected labels.
- Batch 3 no-send decision artifacts were written under `state/launch_decisions/`.

Positive effect: The system no longer treats unsupported route labels as production-ready, and the remaining blocker is now the real supported-route coverage gap rather than hidden phone/social/walk-in drift.

## Key Runtime Artifacts

- Corpus: `state/search-replay/production-sim-live-pilot-20260429T142841Z/`
- Report JSON: `state/production-sim/production-sim-live-pilot-20260429T142841Z/report.json`
- Decisions: `state/production-sim/production-sim-live-pilot-20260429T142841Z/decisions.json`
- Current route-policy report JSON: `state/production-sim/production-sim-route-policy-screenshots-fixed-20260430T000000Z/report.json`
- Current route-policy decisions: `state/production-sim/production-sim-route-policy-screenshots-fixed-20260430T000000Z/decisions.json`
- Current route-policy screenshots: `state/qa-screenshots/production-sim-route-policy-screenshots-fixed-20260430T000000Z/`
- Batch 3 no-send decision brief: `state/launch_decisions/batch3-no-send-route-policy-20260430T013047Z.json`, `state/launch_decisions/batch3-no-send-route-policy-20260430T013047Z.md`
- Failed targeted collection run: `state/production-sim/production-sim-supported-route-expansion-20260430T0135Z/report.json`, `state/search-replay/production-sim-supported-route-expansion-20260430T0135Z/search-failures.json`
- Controlled Batch 1: `state/launch_batches/launch-18ce5c756f.json`
- Controlled Batch 2 reviewed record: `state/launch_batches/launch-6f594101ca.json`
- Repair no-send smoke: `state/launch_smoke_tests/smoke-12995a1657.json`
- Batch 2 no-send smokes: `state/launch_smoke_tests/smoke-c1bae62975.json`, `state/launch_smoke_tests/smoke-f34f36c4f6.json`, `state/launch_smoke_tests/smoke-850d05261f.json`
- Sent email record: `state/sent/wrm-kuraichi-286-sengokuhara-fb03_20260429173017.json`
- Batch 2 sent email record with backfilled inline attachment metadata: `state/sent/wrm-lead-605-0083-416-6d57_20260430004333.json`
- Batch 1 contact-form submission artifacts: `state/contact_form_submissions/20260429T185616Z/`
- Batch 2 contact-form submission artifacts: `state/contact_form_submissions/20260430T005242Z/`, `state/contact_form_submissions/20260430T005455Z/`, `state/contact_form_submissions/20260430T005546Z/`
- Active Batch 1 leads: `state/leads/wrm-kuraichi-286-sengokuhara-fb03.json`, `state/leads/wrm-lead-2-12-5-2392.json`, `state/leads/wrm-koshitsu-sosakuryori-musubi-namba-japan-ee35.json`, `state/leads/wrm-guusan-chi-a-home-style-izakaya-2-chome-9-16-hosai-f672.json`, `state/leads/wrm-tonkotsu-ramen-tatsu-9-18-konohanamachi-d2b8.json`
- Active/reviewed Batch 2 leads: `state/leads/wrm-lead-492-1-d7a2.json`, `state/leads/wrm-lead-605-0083-416-6d57.json`, `state/leads/wrm-kyoto-ramen-kinzan-japan-a54f.json`, `state/leads/wrm-ichinohajimari-kyoto-izakaya-7f4a.json`, `state/leads/wrm-lead-lead-fb50.json`
- Removed unsupported/smoke Batch 2 candidates: `state/leads/wrm-hakoya-meieki-shop-japan-a49c.json`, `state/leads/wrm-tokyo-underground-ramen-japan-6dda.json`

## Last Verified Commands

- `.venv/bin/python -m pytest tests/ -q` passed with `486 passed`
- `.venv/bin/python -m pipeline.cli audit-state` passed with `ok=true`, `checked=55`, `findings=[]`, `readiness_report=[]`
- `.venv/bin/python -m pipeline.cli audit-state --repair` repaired deterministic asset drift for `wrm-jikaseimen-223-okubo-ramen-japan-0b38` and `wrm-maguro-mart-nakano-seafood-5-chome-50-3-nakano-13f7`, then `audit-state` passed.
- `git diff --check` passed.
- `.venv/bin/python -m pipeline.cli production-sim replay --corpus state/search-replay/production-sim-live-pilot-20260429T142841Z --run-id production-sim-route-policy-screenshots-fixed-20260430T000000Z --screenshots --fail-on p0,p1` passed with `P0=0`, `P1=0`, `P2=1`, `external_send_performed=false`, `real_launch_batch_created=false`.
- `.venv/bin/python -m pipeline.cli launch-decision --label batch3-no-send-route-policy` wrote the Batch 3 no-send decision brief with `real_outbound_allowed=false`, `eligible_count=0`.
- `.venv/bin/python -m pipeline.cli production-sim collect --run-id production-sim-supported-route-expansion-20260430T0135Z ... --fail-on p0,p1` returned `P0=0`, `P1=0`, but collected `0` candidates because all `84` Serper maps jobs returned HTTP 400.
- Batch 1 Phase 12 review remains recorded in `state/launch_batches/launch-18ce5c756f.json`.
- Batch 2 Phase 13 repeat review is recorded in `state/launch_batches/launch-6f594101ca.json`.

## Resume Instructions

1. Read `PLAN.md`.
2. Read `PRODUCTION_SIMULATION_TEST_PLAN.md` only for the current simulation gate and acceptance criteria.
3. Use this file as the compact current checkpoint, not as proof that a phase is complete.
4. Treat the current production simulation report as a no-send readiness signal only. The latest route-policy replay is not production-ready because supported-route expected-ready coverage is short.
5. Continue mode: if the user pasted these resume instructions or says "continue", proceed through all remaining no-send actionable work as one long work block, not just the next numbered step. Do not stop just because a commit is made, a small bug is fixed, or the next outbound action requires permission. Do not send real emails or submit real contact forms from "continue" alone.
6. Next action: fix or bypass the failing Serper maps collection path, expand supported-route no-send candidate/label coverage, rerun production simulation with screenshots, and rerun `launch-decision`. Do not send Batch 3 or any new outbound contact without an explicit user request for the exact real send/contact action.
7. Do not use phone, Instagram, LINE, or walk-in routes for outreach. Do not select phone-only leads.
8. Phase 12 review is recorded for Batch 1; Phase 13 repeat review is recorded for Batch 2 under `launch-6f594101ca`.
9. Before any Batch 3 contact or human approval brief, check for new Batch 1/Batch 2 replies, bounces, opt-outs, or objections and update the relevant launch batch plus lead files if anything changed. This check must be no-send.
10. If context bloat starts affecting output quality or accuracy, stop after updating this handoff with a concrete next no-send task rather than continuing the next work slice.
11. After each completed phase, simulation slice, or real-send slice, update this handoff by replacing stale checkpoint details instead of appending a long diary.
