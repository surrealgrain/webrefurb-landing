# Production Simulation Test Execution Plan

Status: planned for the next hardening pass.

This plan does not replace `PLAN.md`. `PLAN.md` remains the active product audit implementation plan and real outreach remains blocked until its gates allow it. This document defines the production-readiness simulation and optimization loop needed before controlled launch work can be trusted.

## Goal

Build a repeatable, evidence-producing simulation that proves the pipeline can do the real job:

1. Search broadly enough across Japan ramen and izakaya candidates.
2. Identify the correct businesses for the fixed-price packages.
3. Reject businesses that are outside scope, already solved, too risky, or not launch-ready.
4. Show the operator exactly why each important candidate is ready, manual review, or disqualified.
5. Generate shop-specific cold outreach with the correct package fit and correct inline sample images.
6. Block every path that could email the wrong business, wrong contact route, wrong package, wrong proof asset, or unsafe claim.
7. Produce screenshots, replay data, mocked email payloads, and structured reports that make failures concrete.
8. Keep optimizing until the report says `production_ready=true` with zero launch-blocking findings.

## Non-Negotiables

- No real outreach is sent during any simulation phase.
- No test may rely on ten random restaurants as proof of production readiness.
- Broad discovery must be stratified by market, category, search job, package profile, and rejection class.
- Every important dashboard state must have a screenshot artifact.
- Every ready lead must have machine-checkable evidence for identity, Japan location, category, friction, proof, contact route, package fit, and inline assets.
- Every mocked email send must capture recipient, subject, body, HTML, CID attachments, and selected package/profile metadata.
- The final report may not say "done with caveats." Any caveat must be classified as a blocker, a non-blocking observation, or an explicitly deferred item outside the launch gate.
- `production_ready=true` requires zero P0 and zero P1 findings.

## Definition Of Production-Ready

The simulation may report `production_ready=true` only when all required gates pass:

- No non-Japan, wrong-category, chain/franchise, already-English, multilingual QR/mobile-order, thin-menu, or bad-contact candidate is `ready_for_outreach`.
- Every expected-ready lead is Japan-only, ramen or izakaya, independent or likely small operator, and has concrete ordering friction.
- Every ready lead has customer-safe proof, a supported contact route, an explainable package recommendation, and correct inline sample assets.
- Package recommendation matches evidence:
  - ramen ticket-machine default: Package 2, unless explicit print-yourself fit supports Package 1;
  - simple ramen without ticket machine: Package 1;
  - ramen without machine but counter-ready need: Package 2;
  - izakaya drinks/courses/nomihodai with frequent updates: Package 3;
  - stable izakaya table menu/staff explanation burden: Package 2;
  - large/complex menus: custom quote/manual review.
- Outreach is shop-specific diagnosis copy, not a generic price-led pitch.
- Outreach does not mention AI, automation, scraping, internal tools, or unverified price/allergen claims.
- Inline images match the lead profile:
  - ramen menu lead: ramen menu sample;
  - ramen ticket-machine lead: ramen menu sample plus ticket-machine guide, or machine-only guide when classification is machine-only;
  - izakaya lead: izakaya food/drinks sample;
  - contact-form route: no attachment/inline-sample claims.
- The dashboard visually exposes readiness, rejection reason, proof strength, evidence score, package fit, ticket-machine state, English-menu state, selected contact route, and selected sample assets.
- Mocked send cannot proceed for non-ready, disqualified, manual-review, missing-contact, missing-proof, or missing-required-asset leads.
- `audit-state`, the full test suite, and `git diff --check` pass at the end.

## Severity Model

P0: must be fixed before any controlled launch.

- Wrong or unqualified business can be sent cold outreach.
- Wrong contact route or recipient is selected.
- Non-Japan, chain/franchise, already-solved, wrong-category, or unsafe lead is `ready_for_outreach`.
- Package recommendation is wrong in a way that would materially mis-sell the offer.
- Inline samples do not match lead profile or stale/legacy sample assets are used.
- Send path bypasses readiness/proof/contact/package/asset gates.
- Outreach contains forbidden customer-facing terms or asserts unverified facts.

P1: must be fixed before production-ready claim.

- Operator cannot see why a lead is ready or rejected.
- Dashboard hides proof/contact/package/asset state needed to make a send decision.
- Search report cannot explain accepted/rejected candidates.
- Simulation screenshots are missing for an important state.
- Manual-review cases are too broad to tune or lack actionable reason codes.

P2: optimization target after P0/P1 are zero.

- Search terms could improve yield.
- Some copy is less persuasive but still safe.
- Dashboard grouping could be clearer.
- Additional market coverage would improve confidence.

## Core Artifacts

All generated runtime artifacts should stay under ignored `state/` paths unless explicitly promoted as small deterministic fixtures.

- `state/search-replay/<run_id>/manifest.json`
- `state/search-replay/<run_id>/serper/*.json`
- `state/search-replay/<run_id>/pages/*.html`
- `state/search-replay/<run_id>/labels/*.json`
- `state/production-sim/<run_id>/report.json`
- `state/production-sim/<run_id>/report.md`
- `state/production-sim/<run_id>/decisions.json`
- `state/production-sim/<run_id>/mock-email-payloads.json`
- `state/production-sim/<run_id>/screenshot-manifest.json`
- `state/qa-screenshots/production-sim-<run_id>/*.png`

Small committed fixtures may live under:

- `tests/fixtures/production_sim/`

Only commit fixtures that are deterministic, sanitized, reasonably small, and necessary for CI.

## Proposed Implementation Modules

Add or extend these modules as needed:

- `pipeline/search_replay.py`: read/write replay corpora, mock Serper/search/fetch calls, dedupe candidates, validate manifest schema.
- `pipeline/production_sim.py`: run replay, evaluate labels, produce reports, score findings, enforce `production_ready`.
- `pipeline/production_sim_oracle.py`: compare observed lead decisions to expected readiness/package/contact/asset labels.
- `pipeline/cli.py`: add `production-sim` subcommands.
- `tests/test_production_simulation.py`: offline replay/oracle tests.
- `tests/test_dashboard_production_simulation.py`: Playwright dashboard flow against isolated state.

Prefer adapters over invasive rewrites. The simulation should exercise the real pipeline paths wherever possible.

## CLI Shape

Target CLI shape:

```bash
.venv/bin/python -m pipeline.cli production-sim collect --city-set launch-markets --category all --limit-per-job 20
.venv/bin/python -m pipeline.cli production-sim label --corpus state/search-replay/<run_id> --sample stratified
.venv/bin/python -m pipeline.cli production-sim replay --corpus state/search-replay/<run_id>
.venv/bin/python -m pipeline.cli production-sim dashboard --corpus state/search-replay/<run_id> --screenshots
.venv/bin/python -m pipeline.cli production-sim report --run state/production-sim/<run_id> --fail-on p0,p1
```

The first implementation may use fewer subcommands if needed, but the report schema and pass/fail semantics must be preserved.

## Report Schema

`report.json` should include:

```json
{
  "run_id": "production-sim-YYYYMMDDTHHMMSSZ",
  "production_ready": false,
  "p0": 0,
  "p1": 0,
  "p2": 0,
  "candidate_count": 0,
  "labeled_count": 0,
  "ready_count": 0,
  "manual_review_count": 0,
  "disqualified_count": 0,
  "mock_sends_verified": 0,
  "screenshots": [],
  "findings": [],
  "next_required_fixes": []
}
```

Each finding should include:

```json
{
  "id": "P0-WRONG-PACKAGE-001",
  "priority": "P0",
  "lead_id": "wrm-...",
  "business_name": "...",
  "expected": "...",
  "actual": "...",
  "evidence": ["path/to/screenshot.png", "path/to/payload.json"],
  "fix_hint": "Concrete code or tuning target"
}
```

## Corpus Strategy

The broad test must be stratified, not random.

Minimum broad corpus targets before claiming production readiness:

- 300-500 raw candidates.
- 100-150 manually labeled candidates.
- At least 20 expected-ready leads.
- At least 10 labeled examples per major positive profile:
  - ramen ticket-machine;
  - ramen meal-ticket;
  - simple ramen without ticket machine;
  - ramen menu-photo/official-menu;
  - izakaya nomihodai/course;
  - izakaya oshinagaki/printed menu;
  - izakaya menu-photo/official-menu.
- At least 10 labeled examples per major rejection class:
  - non-Japan false positive;
  - chain/franchise/branch;
  - already usable English menu;
  - multilingual QR/mobile order;
  - wrong category;
  - thin menu/no orderable detail;
  - bad contact route;
  - no supported contact route;
  - no customer-safe proof.

Initial market set:

- Tokyo: Shibuya, Shinjuku, Ikebukuro, Nakano, Akihabara, Asakusa, Ueno.
- Osaka: Namba, Umeda, Shinsekai.
- Kyoto: Gion, Kawaramachi, Kyoto Station.
- Fukuoka: Tenjin, Hakata, Nakasu.
- Sapporo: Susukino, Sapporo Station.
- Nagoya: Sakae, Nagoya Station.
- Yokohama: Kannai, Minatomirai, Yokohama Station.
- Kobe: Sannomiya.
- Hiroshima: Hondori.
- Sendai: Kokubuncho.
- Smaller tourist-heavy areas: Nara, Kanazawa, Hakone, Kamakura.

Search jobs must include every current friction-first search job from `pipeline/search_scope.py`, plus explicit evidence checks for:

- English menu;
- multilingual QR;
- mobile order;
- English ticket-machine support;
- chain/franchise/branch infrastructure.

## Label Schema

Each labeled candidate should capture:

```json
{
  "candidate_id": "stable-id",
  "business_name": "...",
  "website": "...",
  "address": "...",
  "category_expected": "ramen|izakaya|out_of_scope",
  "readiness_expected": "ready_for_outreach|manual_review|disqualified",
  "rejection_reason_expected": "",
  "package_expected": "package_1_remote_30k|package_2_printed_delivered_45k|package_3_qr_menu_65k|custom_quote|none",
  "contact_route_expected": "email|contact_form|line|instagram|phone|walk_in|none",
  "inline_assets_expected": ["ramen_food_menu", "ticket_machine_guide"],
  "ticket_machine_state_expected": "present|absent|unknown|already_english_supported",
  "english_menu_state_expected": "missing|weak_partial|image_only|usable_complete|unknown",
  "proof_strength_minimum": "gold|operator_only|none",
  "label_confidence": "high|medium|low",
  "label_notes": ""
}
```

Low-confidence labels may be used for diagnostics but must not be counted as hard pass/fail unless promoted by manual review.

## Phase 0: Source Lock And Safety Gate

Goal: make sure the simulation cannot send real outreach and does not corrupt operational state.

Steps:

1. Read `PLAN.md`, `HANDOFF.md`, and this file. Read `PRODUCT_AUDIT_2026-04-29.md` only for acceptance criteria or audit details that are not already represented in `PLAN.md`.
2. Confirm real outreach remains blocked.
3. Run:
   - `git status --short`;
   - `.venv/bin/python -m pipeline.cli audit-state`;
   - `.venv/bin/python -m pytest tests/ -q`;
   - `git diff --check`.
4. Create or use isolated simulation state, never the operator's live state:
   - `state/production-sim/<run_id>/state/`
5. Ensure any mocked send path is explicit:
   - no `RESEND_API_KEY` needed;
   - any code path touching Resend must be monkeypatched or simulation-gated.
6. Record the baseline as a compact checkpoint in `HANDOFF.md`; keep detailed evidence in reports or command output.

Acceptance criteria:

- Baseline is known.
- Simulation state is isolated.
- Real send path cannot execute during simulation.

## Phase 1: Production Goal Contract

Goal: encode the actual commercial goal as a strict oracle before building dashboards or screenshots.

Steps:

1. Define a `ProductionGoalContract` covering:
   - market: Japan only;
   - categories: ramen and izakaya only;
   - package keys/prices;
   - readiness states;
   - rejection classes;
   - package recommendation branches;
   - customer-facing copy constraints;
   - inline asset constraints;
   - send-path constraints.
2. Build assertion helpers that compare observed decisions to expected labels.
3. Add tests for the oracle itself using small artificial records.

Acceptance criteria:

- The oracle fails on wrong readiness, wrong package, wrong contact route, wrong assets, unsafe copy, and forbidden send path.
- Every failure has a priority and concrete fix hint.

## Phase 2: Replay Harness

Goal: run broad search/qualification without spending Serper credits or relying on live web variance.

Steps:

1. Implement replay storage for:
   - raw Serper maps responses;
   - raw Serper organic search responses;
   - fetched website/contact/evidence pages;
   - fetch failures;
   - timestamps and source URLs.
2. Implement adapters so `search_and_qualify()` can run from replay data.
3. Preserve real pipeline behavior as much as possible:
   - real qualification;
   - real lead record creation;
   - real dossier generation;
   - real package recommendation;
   - real outreach asset selection;
   - mocked external network only.
4. Add deterministic fixture tests with at least:
   - one ready ramen ticket-machine lead;
   - one ready simple ramen lead;
   - one ready izakaya lead;
   - one chain;
   - one already-English lead;
   - one non-Japan lead;
   - one bad contact lead.

Acceptance criteria:

- Replay mode can run with network disabled.
- Replay decisions match fixture labels.
- Replays are stable across runs.

## Phase 3: Broad Corpus Collection

Goal: collect enough raw candidate data to evaluate behavior across real market variance.

Steps:

1. Implement `production-sim collect`.
2. Use the market set in this plan.
3. Run all friction-first jobs for each market/category.
4. Limit per job conservatively at first, then expand:
   - pilot: 5 per job;
   - broad: 20 per job;
   - extended: 30+ per job if needed.
5. Deduplicate by:
   - Serper place ID;
   - normalized domain;
   - business name + address;
   - phone.
6. Record skipped duplicates with source jobs that found them.
7. Fetch first-party website, likely contact pages, and targeted evidence pages.
8. Store failed fetches as first-class records.

Acceptance criteria:

- Pilot corpus has at least 100 raw candidates.
- Broad corpus has 300-500 raw candidates.
- Every candidate can be replayed offline or is marked with an explicit capture failure.

## Phase 4: Stratified Labeling

Goal: create enough ground truth to calculate whether the system is correct.

Steps:

1. Implement `production-sim label --sample stratified`.
2. Sample across:
   - search job;
   - market;
   - category;
   - suspected ready/manual/disqualified;
   - evidence profile;
   - contact route profile.
3. Build a label template and operator checklist.
4. Labels must identify expected readiness, package, contact route, inline assets, and reason code.
5. Add a second-pass review queue for:
   - low-confidence labels;
   - expected-ready leads;
   - labels that disagree with pipeline output.

Acceptance criteria:

- 100-150 labels before production-ready claim.
- Every expected-ready label has high confidence.
- Every P0/P1 disagreement has a screenshot or source artifact.

## Phase 5: Offline Replay Evaluation

Goal: measure pipeline quality over the broad labeled corpus before using the dashboard.

Steps:

1. Replay the corpus into isolated state.
2. Evaluate candidate decisions against labels.
3. Compute:
   - false-ready count;
   - false-disqualified count;
   - wrong manual-review count;
   - wrong package count;
   - wrong contact route count;
   - wrong inline assets count;
   - unsafe copy count;
   - send-gate bypass count.
4. Produce `decisions.json` and `report.json`.
5. Fail on any P0/P1 finding.

Acceptance criteria:

- No false-ready P0 cases.
- No wrong package P0/P1 cases for expected-ready labels.
- No wrong inline asset cases for expected-ready labels.
- All findings include concrete evidence and fix hints.

## Phase 6: Dashboard Operator Simulation

Goal: visually verify the actual operator workflow, not only backend decisions.

Steps:

1. Start the dashboard against isolated simulation state.
2. Use Playwright to drive the UI:
   - open dashboard;
   - run category `all` search or load replay result;
   - inspect search summary;
   - inspect lead buckets/cards;
   - open dossier;
   - open outreach preview;
   - save/regenerate draft;
   - attempt mocked send where appropriate;
   - verify blocked controls for bad leads.
3. Screenshot every important element:
   - search controls;
   - search progress/result summary;
   - ready lead card;
   - manual-review lead card;
   - disqualified lead card;
   - lead dossier;
   - proof section;
   - package recommendation section;
   - contact route section;
   - outreach editor;
   - inline menu sample;
   - inline ticket-machine sample;
   - mocked-send confirmation;
   - blocked-send error.
4. Save `screenshot-manifest.json` with:
   - screenshot path;
   - lead ID;
   - UI state;
   - expected assertion;
   - actual assertion.

Acceptance criteria:

- Every expected-ready profile has screenshots through preview and mocked send.
- Every rejection class has at least one screenshot of the blocked/diagnostic state.
- Visual screenshots show the operator why each important lead is ready or blocked.

## Phase 7: Mock Email Payload Verification

Goal: prove cold-email output matches the target business and package profile.

Steps:

1. Monkeypatch Resend calls or route through a mock transport.
2. Capture:
   - recipient;
   - reply-to;
   - subject;
   - text body;
   - HTML body;
   - CID references;
   - inline attachments;
   - filenames;
   - MIME types;
   - content IDs;
   - body/business-name seal matches.
3. Assert:
   - recipient matches expected business route;
   - subject/body use authoritative business name;
   - sender/contact/opt-out exists where required;
   - no forbidden customer-facing terms;
   - no unverified prices/allergens;
   - menu/ticket-machine CIDs appear only when expected;
   - no cold-email PDF attachments;
   - no stale cream assets;
   - no SVG fallback in actual send payload;
   - no send is allowed for non-ready records.

Acceptance criteria:

- Mock send payloads prove every ready profile has correct inline assets.
- Blocked profiles cannot produce a send payload.

## Phase 8: Dashboard Quality And Accessibility Checks

Goal: ensure screenshots are not merely present, but usable for real operators.

Steps:

1. Check screenshots for:
   - horizontal overflow;
   - clipped text;
   - overlapping buttons or modal content;
   - hidden readiness reasons;
   - missing package fit;
   - missing proof context;
   - unreadable inline previews.
2. Add automated DOM checks where practical:
   - important labels visible;
   - controls disabled/enabled correctly;
   - modal focus states;
   - mobile viewport coverage.
3. Use screenshots to create concrete UI findings.

Acceptance criteria:

- No P0/P1 operator-confusion findings remain.
- Mobile and desktop paths both show the core decision data.

## Phase 9: Closed-Loop Optimization

Goal: keep fixing until production-ready is true.

Loop:

1. Run offline replay.
2. Run dashboard simulation.
3. Run mocked email verification.
4. Generate report.
5. If P0/P1 findings exist:
   - fix the highest-priority root cause;
   - add/update regression tests;
   - rerun the whole simulation;
   - record the current finding count, report path, and next action in `HANDOFF.md`; keep detailed finding/fix history in the generated report.
6. Repeat until:
   - P0 = 0;
   - P1 = 0;
   - required screenshots exist;
   - mocked sends verified;
   - `audit-state` passes;
   - full tests pass;
   - `git diff --check` passes.

Acceptance criteria:

- No "done with caveats."
- Final report has `production_ready=true`.
- Any remaining P2 items are non-blocking and documented separately.

## Phase 10: No-Send Real-World Smoke

Goal: validate the simulation against a small fresh live set without sending outreach.

Steps:

1. Collect a fresh live mini-corpus after the broad replay loop passes.
2. Select 5-10 expected-ready leads.
3. Run no-send smoke using the same launch readiness gates.
4. Verify:
   - source URLs still load;
   - proof assets exist;
   - drafts exist;
   - inline assets match;
   - no lead is marked contacted;
   - no real launch batch is created.

Acceptance criteria:

- No-send smoke passes.
- Any live-data surprise becomes a new replay fixture or labeled corpus item.

## Phase 11: Controlled Launch Readiness Recommendation

Goal: produce a final recommendation for whether to proceed to real Phase 11 controlled launch.

Steps:

1. Generate final `report.md`.
2. Include:
   - corpus size;
   - labeled sample size;
   - ready/manual/disqualified counts;
   - package distribution;
   - false-ready count;
   - wrong-package count;
   - wrong-inline-assets count;
   - screenshots index;
   - mocked email payload verification;
   - no-send smoke result;
   - remaining P2 observations.
3. State one of:
   - `PROCEED_TO_CONTROLLED_BATCH_1_SELECTION`;
   - `DO_NOT_LAUNCH_REQUIRED_FIXES_REMAIN`.

Acceptance criteria:

- Proceed recommendation requires `production_ready=true`, no-send smoke pass, and no P0/P1 findings.

## First Implementation Slice

The next chat should not attempt the entire broad corpus immediately. Start with a thin but real vertical slice:

1. Add the production simulation report schema and oracle.
2. Add a small deterministic replay fixture with about 12 candidates:
   - 3 expected-ready positives;
   - 9 disqualified/manual-review negatives.
3. Add mocked email payload verification for the 3 positives.
4. Add Playwright dashboard screenshots for those 12 candidates.
5. Make the report fail on any P0/P1 finding.
6. Then expand to pilot live collection and broad corpus.

This prevents building a large collector before the pass/fail contract is correct.

## Verification Commands For Each Completed Slice

Run at minimum:

```bash
.venv/bin/python -m pytest tests/test_production_simulation.py tests/test_dashboard_production_simulation.py -q
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m pipeline.cli audit-state
git diff --check
git status --short
```

For any UI-facing slice, also save screenshots under `state/qa-screenshots/production-sim-<run_id>/` and include the screenshot manifest in the report.

## Handoff Requirements

Every handoff after work on this plan must stay compact. Replace stale checkpoint details instead of appending historical logs. Detailed evidence belongs in generated reports and runtime artifacts.

Record only:

- which phase is active;
- corpus/run ID;
- commands run, summarized if long;
- test/audit result summary;
- screenshots directory, if relevant;
- report paths, if relevant;
- P0/P1/P2 counts;
- whether `production_ready` is true or false;
- next required fix if false;
- one short positive-effect sentence;
- confirmation that no real outreach was sent.
