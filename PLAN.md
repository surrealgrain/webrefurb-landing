# Product Audit Implementation Plan

Source audit: `PRODUCT_AUDIT_2026-04-29.md`

This is the active plan. It replaces every older phase plan and every prior completion checklist.

## Operating Rules

- Treat all prior implementation as untrusted until re-verified against this plan.
- Do not mark a phase complete from memory, commit history, or previous handoff text.
- Complete phases in order.
- Each phase must end with:
  - code/state changes, if needed;
  - focused tests for that phase;
  - evidence recorded in `HANDOFF.md`;
  - `git diff --check`;
  - a commit.
- Real outreach is not a separate permission problem anymore; it is a later phase in this plan. It happens only after the audit gates in Phases 0-10 pass.
- Do not scale beyond the first controlled batch until Phase 12 review is complete.

## Phase 0: Source Lock And Baseline Audit

Goal: prove the plan is based on `PRODUCT_AUDIT_2026-04-29.md` and establish the current repo truth.

Exact steps:

1. Read `PRODUCT_AUDIT_2026-04-29.md` completely.
2. Confirm `PLAN.md` names `PRODUCT_AUDIT_2026-04-29.md` as the source audit.
3. Confirm `HANDOFF.md`, `AGENTS.md`, and `CLAUDE.md` do not point agents back to the obsolete old plan.
4. Run `git status --short` and record whether the tree is clean.
5. Run `.venv/bin/python -m pytest tests/ -q`.
6. Run `git diff --check`.
7. Record the test count, diff-check result, and any dirty files in `HANDOFF.md`.

Acceptance criteria:

- `PLAN.md` is the only active plan.
- `HANDOFF.md` says this plan is based on `PRODUCT_AUDIT_2026-04-29.md`.
- Current repo status and test baseline are recorded.
- No phase after Phase 0 is marked done yet.

## Phase 1: State Backup And Stale-State Reconciliation

Goal: eliminate stale state failure modes called out by the audit before any launch work.

Exact steps:

1. Create a timestamped zip backup of `state/` under `state/backups/`.
2. Inspect every file under `state/leads/`.
3. For each lead, verify:
   - package keys use only current package keys;
   - no old package price or label is customer-facing;
   - `lead` remains strictly boolean;
   - stale warning examples are quarantined.
4. Specifically inspect the Tsukada Nojo record.
5. Mark chain-like, already-solved, bad-preview, or stale unsafe records as `do_not_contact`, `disqualified`, or `manual_review` with explicit reasons.
6. Add or update migration code so future stale records are repaired automatically.
7. Add tests proving:
   - legacy package keys map to current keys;
   - chain-like records cannot remain launch-ready;
   - already-solved English/multilingual records cannot remain launch-ready;
   - bracketed preview records cannot remain customer-visible.

Acceptance criteria:

- `state/backups/` contains a fresh backup.
- Tsukada Nojo is quarantined with an explicit reason.
- No launch-ready lead contains stale package keys, bad preview snippets, or chain-like status.
- Focused migration tests pass.

## Phase 2: Lead Evidence Dossier Gate

Goal: implement the audit's launch-readiness audit as the required gate before outreach.

Exact steps:

1. Add or verify persisted lead fields:
   - `lead_evidence_dossier`;
   - `proof_items`;
   - `launch_readiness_status`;
   - `launch_readiness_reasons`;
   - `message_variant`;
   - `launch_outcome`.
2. Preserve binary `lead: true|false`; never add `maybe`.
3. Implement the required dossier states:
   - `ticket_machine_state`: `present`, `absent`, `unknown`, `already_english_supported`;
   - `english_menu_state`: `missing`, `weak_partial`, `image_only`, `usable_complete`, `unknown`;
   - `menu_complexity_state`: `simple`, `medium`, `large_custom_quote`;
   - `izakaya_rules_state`: `none_found`, `drinks_found`, `courses_found`, `nomihodai_found`, `unknown`.
4. Proof items must store:
   - source type;
   - URL;
   - snippet or screenshot path;
   - operator visibility;
   - customer-preview eligibility;
   - rejection reason.
5. Dashboard lead cards must show readiness:
   - `ready_for_outreach`;
   - `manual_review`;
   - `disqualified`.
6. Outreach generation APIs must reject non-ready leads with explicit reasons.

Acceptance criteria:

- A lead cannot generate outreach from only `menu_evidence_found` or `machine_evidence_found`.
- Unknown or unsafe dossier states become manual review unless the outreach is explicitly check-phrased.
- Unit and API tests cover ready, manual review, and disqualified paths.

## Phase 3: Restaurant Fit And Disqualification Rules

Goal: make the target market match the audit's no-brainer customer.

Exact steps:

1. Gate for Japan physical location evidence.
2. Gate for v1 categories only:
   - ramen;
   - izakaya.
3. Gate for active business status when evidence exists.
4. Add independence/multi-location review:
   - independent or likely small operator can continue;
   - chain/franchise-like records disqualify or require manual review.
5. Add out-of-scope disqualification for hotel, cafe, sushi, yakiniku, kaiseki, and other non-v1 categories.
6. Add already-solved disqualification for:
   - usable complete English menu;
   - multilingual QR ordering system;
   - English-supported ticket machine or ordering flow;
   - chain infrastructure that already solves ordering.
7. Add tests for each pass, manual review, and hard disqualification case.

Acceptance criteria:

- The system favors independent ramen/izakaya shops in Japan.
- Chains, out-of-scope categories, and already-solved shops do not receive generic outreach.
- Tsukada Nojo-style failures are impossible to mark launch-ready.

## Phase 4: Friction-First Search

Goal: replace generic lead generation with fewer, stronger high-friction candidates.

Exact steps:

1. Replace generic search defaults such as `ramen restaurants Kyoto`.
2. Add ramen search jobs:
   - `券売機 ラーメン {area}`;
   - `食券 ラーメン {area}`;
   - `ラーメン メニュー 写真 {area}`;
   - `RamenDB {area}`;
   - official site/menu/photo lookups.
3. Add izakaya search jobs:
   - `飲み放題 コース 居酒屋 {area}`;
   - `お品書き 居酒屋 {area}`;
   - `居酒屋 メニュー 写真 {area}`;
   - Hotpepper/Tabelog/official/social lookups.
4. Add English-solution checks:
   - English menu;
   - multilingual QR;
   - existing mobile order support;
   - English ticket-machine support.
5. Store the search job and matched friction evidence on each candidate.
6. Add tests for generated queries and candidate evidence classification.

Acceptance criteria:

- Search is optimized for proven ordering friction, not raw lead volume.
- Every candidate carries source evidence for why it was found.
- Tests prove friction-first queries are generated for ramen and izakaya.

## Phase 5: Offer Fit And Package Recommendation

Goal: recommend the package that matches the proven operational problem.

Exact steps:

1. Preserve package keys and prices:
   - `package_1_remote_30k`: JPY 30,000;
   - `package_2_printed_delivered_45k`: JPY 45,000;
   - `package_3_qr_menu_65k`: JPY 65,000.
2. Use customer-facing labels:
   - English Ordering Files;
   - Counter-Ready Ordering Kit;
   - Live QR English Menu.
3. Implement recommendation defaults:
   - ramen with ticket machine: Package 2 by default;
   - ramen with ticket machine and clear print-yourself fit: Package 1;
   - ramen without machine and simple menu: Package 1;
   - ramen without machine but counter-ready need: Package 2;
   - izakaya with drinks/courses/nomihodai and frequent changes: Package 3;
   - izakaya with stable table menus and staff explanation burden: Package 2;
   - large/complex menus: custom quote gate.
4. Store recommendation reason and custom-quote reason.
5. Add tests for every recommendation branch.

Acceptance criteria:

- Cold outreach does not lead with all three prices.
- Internal dashboard shows the recommended package and reason.
- Large or complex menus cannot be forced into a fixed package without review.

## Phase 6: Shop-Specific Diagnosis Outreach

Goal: replace service-introduction copy with audit-specific diagnosis copy.

Exact steps:

1. Rewrite outreach generation so the first message answers:
   - why this shop;
   - what exact ordering friction was found;
   - what proof/sample is available;
   - what low-effort next step the owner should take.
2. Do not lead with all three prices in cold outreach.
3. If `ticket_machine_state` is unknown, use check phrasing.
4. If `english_menu_state` is unknown, use check phrasing.
5. Never mention AI, automation, scraping, internal tools, or pipeline mechanics in customer-facing copy.
6. Commercial email paths must include:
   - sender identity;
   - contact info;
   - opt-out wording;
   - do-not-contact handling.
7. Alternate channels must be route-appropriate:
   - contact form;
   - LINE;
   - Instagram;
   - phone;
   - walk-in.
8. Log message variant for controlled launch measurement.
9. Add tests for diagnosis copy, check phrasing, no all-price cold pitch, sender identity, opt-out, and forbidden terms.

Acceptance criteria:

- Outreach feels like a shop-specific diagnosis, not a mass pitch.
- Unknown evidence is never asserted as fact.
- Do-not-contact records cannot generate outreach.

## Phase 7: Preview And Proof Quality Gates

Goal: make customer-visible proof safe enough to build trust.

Exact steps:

1. Harden preview generation to reject:
   - calendar text;
   - headers/footers;
   - search/tel boilerplate;
   - reservation-only copy;
   - unrelated chain pages;
   - bracketed fallback translations;
   - stale or mismatched sample assets.
2. Do not show prices in outreach previews unless owner-confirmed.
3. If no safe proof item exists, require manual review.
4. Ramen samples must show operational clarity:
   - toppings;
   - sets;
   - noodle/soup choices;
   - add-ons;
   - ticket-machine mapping when proven.
5. Izakaya samples must show:
   - drinks;
   - courses;
   - nomihodai rules;
   - shared plates;
   - owner-confirmed ingredient notes only.
6. QR samples must show:
   - hosted menu flow;
   - QR sign;
   - update-policy clarity.
7. Add tests proving unsafe snippets and previews are blocked.

Acceptance criteria:

- No bracketed fallback or scraped junk reaches a customer preview.
- Proof shown to owners is tied to actual safe evidence.
- Preview tests cover unsafe and safe paths.

## Phase 8: Public Positioning, Package Copy, And Risk Reversal

Goal: make the website and quote/order copy match the audit thesis.

Exact steps:

1. Replace customer-facing "translation service" framing with "English ordering system/materials."
2. Keep translation described only as one included component.
3. Update homepage first viewport to show actual outputs:
   - menu;
   - ticket-machine guide;
   - QR sign;
   - before/after ordering clarity.
4. Update pricing pages in English and Japanese.
5. Update quote scope, invoice artifacts, order flow, dashboard selectors, and package descriptions.
6. Add risk reversal everywhere relevant:
   - owner approval before delivery;
   - one correction window;
   - no price claims without owner confirmation;
   - no allergen claims without owner confirmation;
   - clear custom-quote limits.
7. Add tests for package names, prices, positioning, no HVAC references, and forbidden customer-facing terms.

Acceptance criteria:

- Public copy sells operational ordering clarity, not generic translation.
- Package labels and fixed prices are stable.
- Risk reversal is present in site, quote, order, and delivery artifacts.

## Phase 9: Paid Operations And P5 Reconciliation

Goal: make the quote-to-delivery path launch-ready before real orders.

Exact steps:

1. Inspect quote, invoice, payment, intake, privacy, revision, production, owner review, approval, delivery, and follow-up code.
2. Reconcile any mismatch between current implementation and this plan.
3. Ensure every package can move through:
   - lead;
   - contact;
   - reply;
   - quote;
   - payment pending;
   - paid;
   - intake;
   - production;
   - owner review;
   - approval;
   - delivery/follow-up.
4. Rehearse Package 1, Package 2, and Package 3 with safe test data.
5. Verify privacy and owner-confirmation gates before final export.
6. Add or update integration tests for the full flow.

Acceptance criteria:

- Paid work cannot begin without quote, payment, intake, and owner-confirmation gates.
- Final exports cannot ship without owner approval.
- All three packages have rehearsal evidence.

## Phase 10: Browser And Render Verification

Goal: verify the product visually and operationally, not just by unit tests.

Exact steps:

1. Start the local dashboard/site as needed.
2. Capture desktop and mobile screenshots for:
   - dashboard lead card;
   - lead evidence dossier view;
   - outreach modal;
   - homepage;
   - pricing pages;
   - sample ramen preview;
   - sample izakaya preview;
   - QR menu;
   - QR sign.
3. Check for:
   - unreadable text;
   - overlapping UI;
   - missing proof;
   - stale placeholders;
   - bracketed fallback text;
   - forbidden customer-facing language.
4. Save screenshots under `state/qa-screenshots/`.
5. Fix every visual or content defect found.

Acceptance criteria:

- Browser verification covers the actual screens owners/operators will see.
- Screenshots are saved and named clearly.
- No known visual/content defect remains untracked.

## Phase 11: Controlled Launch Batch 1

Goal: run the first launch as a measurement system, not a send blast.

Exact steps:

0. Run a no-send real-world smoke test before external contact:
   - use real public shop evidence;
   - use the same launch-readiness gates as a real batch;
   - create a rehearsal record outside `state/launch_batches/`;
   - do not mark any lead contacted;
   - do not let rehearsal records satisfy or block real Batch 1.
1. Select 5-10 launch-ready shops.
2. Batch must include:
   - at least one ramen ticket-machine lead;
   - at least one izakaya drink/course/nomihodai lead.
3. For each selected lead, manually inspect:
   - restaurant fit;
   - ordering friction;
   - proof strength;
   - channel fit;
   - offer fit;
   - outreach copy;
   - sample/proof asset.
4. Create a launch batch record under `state/launch_batches/`.
5. Run `.venv/bin/python -m pytest tests/ -q`.
6. Run `git diff --check`.
7. Send only the selected batch through approved channels.
8. Record for each lead:
   - dossier states;
   - selected channel;
   - message variant;
   - proof asset;
   - recommended package;
   - contacted timestamp;
   - reply/no reply;
   - objection;
   - opt-out/bounce;
   - operator minutes;
   - outcome.

Acceptance criteria:

- Batch 1 contains 5-10 reviewed leads.
- Every contacted lead has a measurement record.
- No batch 2 work starts before Phase 12.

## Phase 12: Batch Review And Iteration

Goal: learn from batch 1 before scaling.

Exact steps:

1. Review every batch 1 outcome.
2. Summarize:
   - response rate;
   - positive replies;
   - objections;
   - opt-outs/bounces;
   - channel performance;
   - operator time;
   - package fit;
   - proof asset performance.
3. Update scoring from observed outcomes.
4. Update search terms from observed lead quality.
5. Update outreach wording from replies and objections.
6. Update package recommendation if package fit was wrong.
7. Record the review in the batch record.
8. Run tests and diff check.

Acceptance criteria:

- Batch 1 review is recorded before batch 2.
- Search, scoring, outreach, or recommendation changes are made when evidence supports them.
- Scaling is based on observed lead profile, not volume pressure.

## Phase 13: Batch 2 And Repeatable Launch Loop

Goal: scale only after the repeatable lead profile is clearer.

Exact steps:

1. Confirm batch 1 review is saved.
2. Select batch 2 using updated scoring/search/outreach rules.
3. Repeat Phase 11 measurement.
4. Repeat Phase 12 review.
5. Continue only while lead quality and owner response justify volume.

Acceptance criteria:

- Batch 2 cannot be created until batch 1 review exists.
- Every batch produces measurement and a recorded decision.

## Final Verification Command Set

Run these before every commit that claims a phase is complete:

```bash
.venv/bin/python -m pytest tests/ -q
git diff --check
git status --short
```

For UI-facing phases, also run browser/render verification and save screenshots under `state/qa-screenshots/`.
