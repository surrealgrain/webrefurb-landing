# WebRefurbMenu Handoff

Updated: 2026-05-01

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

- Branch: `codex/phase11-contact-form-batch`.
- **Uncommitted changes** — do NOT commit without review.
- `PLAN.md` Phases 0-12 are complete. Phase 13 is active, not complete.
- Controlled Batch 1 and Batch 2 have already had real approved-route outreach. Do not start Batch 3.
- Current decision: hold real Batch 3 outbound. Reason: Batch 1/2 have 0 replies/positives and the eligible candidate pool is not strong enough.

## What Changed This Session (2026-05-01)

### 1. Scrapling integrated into pipeline page fetching (`pipeline/search.py`)
- **`_fetch_page()` now uses Scrapling `Fetcher`** (TLS fingerprint impersonation) as primary, urllib as fallback
- This is the core page fetching function used by the entire pipeline
- Scrapling 0.4.7 already installed from previous session

### 2. Bulk lead gen script (`scripts/bulk_lead_gen.py`) — NEW
- Standalone script for bulk lead generation with preview + inline pitch
- Email-only filtering — leads must have email addresses
- Generates preview HTML pages with inline pitches
- Tokyo-specific delivery language: laminated in-person delivery offered
- Non-Tokyo: email delivery only, laminating by negotiation
- Uses directory_discovery + contact extraction + evidence assessment + preview generation
- **Problem identified**: only 4 leads from 228 Tokyo candidates — homepage-only email extraction misses most emails

### 3. Multi-source collection attempted
- Ran `collect_replay_corpus()` for Tokyo, Osaka, Kyoto, Sapporo, Fukuoka
- Uses WebSerper + Google Maps + Tabelog directory discovery simultaneously
- Corpus saved to `state/search-replay/spray-pray-v1/`
- **Yield was too low** — user switched to Codex for lead finding

### 4. Target cities confirmed
- **Tokyo, Osaka, Kyoto, Sapporo, Fukuoka** (tourist hotspots only)
- User explicitly confirmed these 5 and no others

### Key Insight This Session
- Japanese restaurant websites rarely put emails on homepage. Need multi-page probing (/contact/, /access/, /info/, etc.) to extract emails. The `_probe_deterministic_contact_paths()` function exists in `search_replay.py` but hasn't been integrated into the bulk lead gen flow.
- User is now using **Codex** to find leads externally — it's working better than the pipeline approach.

## Files Modified/Created This Session

- `pipeline/search.py` — `_fetch_page()` rewritten to use Scrapling Fetcher with urllib fallback
- `scripts/bulk_lead_gen.py` — **NEW** — bulk lead gen with preview + pitch (homepage-only email extraction, low yield)
- `HANDOFF.md` — this update

### Previous Session Changes Still Uncommitted
- `pipeline/search_scope.py` — replaced directory jobs with contact discovery queries
- `pipeline/search_replay.py` — solution-check caps, deterministic contact probing, directory discovery integration
- `pipeline/search_provider.py` — raised limits, organic merge triggers, stronger blocked hosts
- `pipeline/contact_crawler.py` — full-width @ detection, `recover_contact_routes()` function
- `pipeline/directory_discovery.py` — **REWRITTEN** — Scrapling-based Tabelog crawler
- `pipeline/lead_qualifier/` — **NEW MODULE** — queue-based batch qualification (queue.py, pain_signals.py, review_scraper.py, models.py, run.py)
- `pipeline/manual_import.py` — **NEW** — manual lead import
- `scripts/webserper_benchmark_loop.py` — **NEW** — benchmark loop mechanism
- `dashboard/app.py` + `dashboard/templates/index.html` — dashboard updates
- `tests/test_lead_qualifier_*.py` — **NEW** — lead qualifier tests
- `tests/test_production_simulation.py`, `tests/test_search_scope.py` — updated

### Untracked Files
- `assets/templates/ramen_food_menu_email_preview.jpg`
- `restaurant_email_leads.md`

## Batch Snapshot

- Batch 1: `launch-18ce5c756f`, reviewed, `5/5` contacted, `0` replies, `0` positives, `0` bounces/opt-outs.
- Batch 2: `launch-6f594101ca`, reviewed, `4/5` contacted, `0` replies, `0` positives, `0` bounces/opt-outs.
- Batch 2 non-contact: `wrm-lead-lead-fb50` / 創作個室居酒屋すぎうら. Form required phone data; no phone was invented; no submission was made; now manual/do-not-contact.

## What the User Wants for Search Results (Package Fit Checklist)

User asked for a checklist of what search results should include to fit our packages. This is pending — user will continue in new chat.

## Next Steps

1. **User is using Codex to find leads externally** — pipeline approach had low email yield. May need to:
   - Integrate multi-page email probing into bulk_lead_gen.py
   - Accept Codex-found leads via `pipeline/manual_import.py`
2. **Define package-fit criteria** for search results (user's pending request)
3. **Generate 50+ pitchable leads** with emails + preview pages with inline pitches
4. **Do NOT start Batch 3** outbound until user explicitly requests it

## Key Artifacts

- Bulk lead gen script: `scripts/bulk_lead_gen.py`
- Directory discovery module: `pipeline/directory_discovery.py`
- Lead qualifier module: `pipeline/lead_qualifier/`
- Manual import: `pipeline/manual_import.py`
- Benchmark loop script: `scripts/webserper_benchmark_loop.py`
- Batch 1 record: `state/launch_batches/launch-18ce5c756f.json`
- Batch 2 record: `state/launch_batches/launch-6f594101ca.json`
- Latest benchmark: `state/search-replay/production-sim-webserper-optimized-google-yahoo-independent-neighborhoods-20260430T000000Z/benchmarks/optimized-google-yahoo-focused-20260430.json`

## Last Verification

- `.venv/bin/python -m pytest tests/ -v` — 689 passed, 7 failed (pre-existing dashboard/state failures, not caused by Scrapling change).
- Scrapling 0.4.7 installed: `pip install "scrapling[fetchers]"` + `scrapling install`.
- Provider config: default is `webserper`; `webserper` requires no key.

## Context Hygiene

- In a new chat, read this file first, then targeted sections of `PLAN.md` and `PRODUCTION_SIMULATION_TEST_PLAN.md`.
- Avoid broad `rg` over the whole repo without excludes; embedded assets can dump huge base64 output.
- Prefer targeted commands and small output windows.
