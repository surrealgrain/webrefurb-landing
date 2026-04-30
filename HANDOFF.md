# WebRefurbMenu Handoff

Updated: 2026-04-30

This is the compact resume file. Keep it short. Do not append a running diary; replace stale checkpoint details after each meaningful work block.

## Read First

- Active product plan: `PLAN.md`.
- Simulation criteria: `PRODUCTION_SIMULATION_TEST_PLAN.md`.
- Repo rules: Japan only, ramen + izakaya only, three fixed-price packages.
- No HVAC references.
- Binary lead semantics only: `lead: true|false`, never "maybe".
- Customer-facing copy must not mention AI, automation, scraping, or internal tools.

## Safety Boundary

- Do not send real email, submit real contact forms, or otherwise contact a business unless the user explicitly requests that exact outbound action in the current chat.
- "Continue" means no-send work only.
- Approved outreach routes are email and contact forms only.
- Phone, LINE, Instagram, reservation links, booking forms, social DMs, and phone-required forms are not outreach routes; do not emit them as contact-route records. Walk-ins/map URLs/websites may appear only as non-actionable location/source metadata.
- `production_ready=true` in simulation is only a no-send signal, not send permission.

## Current Status

- Branch: `codex/phase11-contact-form-batch`, ahead of origin by 5 commits.
- Worktree is intentionally dirty. Do not revert user or prior-agent changes.
- `PLAN.md` Phases 0-12 are complete. Phase 13 is active, not complete.
- Controlled Batch 1 and Batch 2 have already had real approved-route outreach. Do not start Batch 3.
- Current decision: hold real Batch 3 outbound. Reason: Batch 1/2 have 0 replies/positives and the eligible candidate pool is not strong enough.

## Batch Snapshot

- Batch 1: `launch-18ce5c756f`, reviewed, `5/5` contacted, `0` replies, `0` positives, `0` bounces/opt-outs.
- Batch 2: `launch-6f594101ca`, reviewed, `4/5` contacted, `0` replies, `0` positives, `0` bounces/opt-outs.
- Batch 2 non-contact: `wrm-lead-lead-fb50` / 創作個室居酒屋すぎうら. Form required phone data; no phone was invented; no submission was made; now manual/do-not-contact.

## Current Code State

Uncommitted hardening is in progress:

- Chain/category gates now prefer first-party page text over third-party review/directory text.
- Large first-party store directories are treated as chain/multi-store infrastructure.
- First-party out-of-scope restaurant/hospitality text can override noisy search category hints.
- Route policy blocks unsupported "forms" such as phone-required, booking/reservation, recruiting, commerce/order, account/login, and social-profile routes.
- Phone routes and booking/reservation/phone-required/hidden-only/newsletter/order/recruit forms are omitted from contact-route lists instead of being kept as reference-only routes.
- Serper collection now preserves HTTP response bodies and exposes missing credits/credential failures clearly.
- JavaScript-rendered contact forms without literal `<form>` tags are recognized when they expose contact/inquiry controls.
- Contact form extraction now profiles forms as `supported_inquiry`, `reservation_only`, `phone_required`, `hidden_only`, `newsletter`, `commerce`, `recruiting`, or `unknown`; only `supported_inquiry` can launch-ready.
- Single-shop "店舗情報"/"お店"/"ご来店" copy no longer trips the multi-store infrastructure gate.
- Local WebSerper search provider is implemented and wired into the CLI. `webserper` is the default provider, requires no `SERPER_API_KEY`, and `serper` remains available only when explicitly selected. WebSerper now combines Google Maps with Yahoo Japan + DuckDuckGo organic fallback and writes retry/fallback metadata.
- Production-sim now has a WebSerper benchmark command and label review shortlist.

Worktree remains intentionally dirty and includes prior unrelated edits. Do not revert user or prior-agent changes.

## Latest No-Send Simulation

Latest focused Google+Yahoo WebSerper corpus:

- `state/search-replay/production-sim-webserper-google-yahoo-independent-neighborhoods-20260430T000000Z/`
- Command used explicit `--search-provider webserper`; no API key was passed or logged. Tuned verification env used shorter local waits: `WEBREFURB_LOCAL_MAPS_BATCH_WAIT_MS=1000`, `WEBREFURB_SEARCH_RETRY_ATTEMPTS=1`, `WEBREFURB_LOCAL_SEARCH_RESULT_LIMIT=12`, `WEBREFURB_LOCAL_SEARCH_PLACE_LIMIT=8`, and `--fetch-timeout-seconds 4`.
- Captured `282` raw candidates, `110` deduped candidates, `172` duplicates, `123` fetched pages, `16` fetch failures, `0` search failures.
- Markets: Sangenjaya, Kichijoji, Kagurazaka, Jinbocho.
- Label workflow created `110` draft labels and `labeling/review-shortlist.json`. Finalized strict labels: `1 ready`, `1 manual_review`, `1 disqualified`.
- Promoted ready: `wrm-replay-oilmen-e264c2f2` / らぁ麺ゃ 煮干しのRYOMA — first-party ramen, published email `info@ryoma-5.com`, Package 1.
- Manual: `wrm-replay-marco-70431f73` / 食堂かど。 — first-party page, but stricter route policy materializes no supported route and proof is operator-only/no customer-safe proof item.
- Disqualified: `wrm-replay-nakano-aoba-4ef37644` / 中華そば 中野 青葉 吉祥寺店 — first-party shop list shows chain/multi-store infrastructure.
- Benchmark artifacts:
  - `state/search-replay/production-sim-webserper-google-yahoo-independent-neighborhoods-20260430T000000Z/benchmarks/google-yahoo-focused-labeled-20260430.json`
  - `state/search-replay/production-sim-webserper-google-yahoo-independent-neighborhoods-20260430T000000Z/benchmarks/google-yahoo-focused-labeled-20260430.md`
- Benchmark status: not passed. Improved `0` search failures, `100%` first-party-site rate, `11.51%` fetch failure rate, and `0` unsupported ready labels. Still below target on candidate yield (`1.31` deduped candidates/job vs `1.60`) and reviewed-ready count (`1` vs target `6`).

Latest replay:

- Run ID: `production-sim-webserper-google-yahoo-independent-neighborhoods-labeled-20260430T000000Z`
- Result: `production_ready=false`, `P0=0`, `P1=0`, `P2=1`
- Counts: `1 ready`, `1 manual_review`, `1 disqualified`, `1` mocked send verified.
- `external_send_performed=false`, `real_launch_batch_created=false`.
- Dashboard screenshot coverage passed for required ready/manual/disqualified/editor/inline states.

Strict reviewed labels across credited + focused WebSerper corpora:

- Total `19`: `8 ready`, `3 manual_review`, `8 disqualified`.
- Current expected-ready labels:
  - `wrm-replay-izakaya-gussanchi-190acb60` — izakaya course/nomihodai, contact form, Package 3.
  - `wrm-replay-torisoba-salt-32897741` — ramen, email, Package 2.
  - `wrm-replay-momokichi-kichijoji-6cebd6d4` — izakaya menu/course, contact form, Package 3.
  - `wrm-replay-oilmen-a4e94f47` — ramen ticket-machine profile, email, Package 2.
  - `wrm-replay-jimbocho-ton-be6980fa` — izakaya course/menu, contact form, Package 3.
  - `wrm-replay-marco-5bd65206` — Sangenjaya izakaya/sakaba, first-party contact form, Package 2.
  - `wrm-replay-kushinikomi-maruni-4600161b` — Kichijoji izakaya course/nomihodai, first-party contact form, Package 3.
  - `wrm-replay-oilmen-e264c2f2` — ramen, first-party published email, Package 1.

Google+Yahoo replay materialization found only `1` current-rule ready record (`RYOMA`). Many high-scoring shortlist items were chain/multi-store, website-only, already-solved, or reservation/booking-adjacent. Continue reviewing only legitimate high-confidence first-party ramen/izakaya records with email or supported general inquiry forms.

`SERPER_API_KEY` is no longer required for the default WebSerper path. Do not use, echo, write, or log it for WebSerper runs.

## Latest Batch 3 Decision

- Command run: `.venv/bin/python -m pipeline.cli launch-decision --label batch3-no-send-google-yahoo-webserper-20260430T000000Z`
- Recommendation: `hold_real_outbound_prepare_more_candidates`
- `real_outbound_allowed=false`
- `eligible_count=0`
- Artifacts:
  - `state/launch_decisions/batch3-no-send-google-yahoo-webserper-20260430T000000Z-20260430T064907Z.json`
  - `state/launch_decisions/batch3-no-send-google-yahoo-webserper-20260430T000000Z-20260430T064907Z.md`

## Key Artifacts

- Latest replay report: `state/production-sim/production-sim-webserper-google-yahoo-independent-neighborhoods-labeled-20260430T000000Z/report.json`
- Latest replay decisions: `state/production-sim/production-sim-webserper-google-yahoo-independent-neighborhoods-labeled-20260430T000000Z/decisions.json`
- Latest replay screenshots: `state/qa-screenshots/production-sim-webserper-google-yahoo-independent-neighborhoods-labeled-20260430T000000Z/`
- Batch 1 record: `state/launch_batches/launch-18ce5c756f.json`
- Batch 2 record: `state/launch_batches/launch-6f594101ca.json`

## Last Verification

- `.venv/bin/python -m pytest tests/ -q` passed with `611 passed`.
- Provider config check: default provider is `webserper`; `webserper` requires no key; `serper` still requires a key.
- `.venv/bin/python -m pipeline.cli production-sim replay --corpus state/search-replay/production-sim-webserper-google-yahoo-independent-neighborhoods-20260430T000000Z --run-id production-sim-webserper-google-yahoo-independent-neighborhoods-labeled-20260430T000000Z --screenshots --fail-on p0,p1` passed with `P0=0`, `P1=0`, `P2=1`.
- `git diff --check` passed.
- `.venv/bin/python -m pipeline.cli audit-state` passed with `ok=true`, `checked=55`, `findings=[]`, `readiness_report=[]`.
- `audit-state --repair` previously repaired deterministic drift for `wrm-tonkotsu-ramen-tatsu-9-18-konohanamachi-d2b8` from ready to disqualified because current chain-like evidence gates now apply; rerun audit passed.

## Next Safe Work

1. Improve Google+Yahoo candidate yield without weakening first-party and route safety. Current benchmark misses candidate/job target (`1.31` vs `1.60`) even though reliability and fetch rate pass.
2. Continue no-send evidence review for legitimate supported-route false negatives in existing corpora. Promote only high-confidence first-party ramen/izakaya records with email or supported general inquiry forms.
3. Keep phone numbers, reservation/booking forms, hidden-only forms, newsletters, order/commerce, recruiting, LINE, and Instagram out of contact-route records.
4. When more labels are added, rerun:

```bash
.venv/bin/python -m pipeline.cli production-sim collect --run-id <new-webserper-run-id> --city-set launch-markets --category all --stage pilot --search-provider webserper --contact-pages-per-candidate 2 --evidence-pages-per-candidate 4 --fail-on p0,p1
.venv/bin/python -m pipeline.cli production-sim label --corpus state/search-replay/<new-webserper-run-id>
.venv/bin/python -m pipeline.cli production-sim replay --corpus state/search-replay/<new-webserper-run-id> --run-id <new-replay-run-id> --screenshots --fail-on p0,p1
.venv/bin/python -m pipeline.cli launch-decision --label <new-label>
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m pipeline.cli audit-state
git diff --check
```

## Context Hygiene

- In a new chat, read this file first, then targeted sections of `PLAN.md` and `PRODUCTION_SIMULATION_TEST_PLAN.md`.
- Avoid broad `rg` over the whole repo without excludes; embedded assets can dump huge base64 output.
- Prefer targeted commands and small output windows.
