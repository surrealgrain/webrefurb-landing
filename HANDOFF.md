# WebRefurbMenu Handoff
Updated: 2026-05-03. Compact resume file; replace stale facts instead of appending logs.
Startup read path: read `AGENTS.md`, then this file only. Open long docs, raw leads, reports, or state artifacts only for a specific blocker.
## Safety Boundary
- No real email, contact-form submit, or other business contact unless explicitly requested in the current chat; "continue" means no-send work only.
- Approved review routes are email/contact forms only; phone, LINE, Instagram, reservations, map URLs, walk-ins, and websites are reference-only.
- During no-send inventory/review, do not set `pitch_ready=true`, `ready_for_outreach`, or `outreach_status=new`.
- Customer-facing copy must not mention AI, automation, scraping, or internal tools.
## Current Snapshot
- Branch: `codex/phase11-contact-form-batch`; unrelated dirty files remain, so stage only mission files.
- Live queue: 596 records, 401 openable pitch cards, 193 hard blocked, 2 unsupported route.
- Operator review wave is drained: 401/401 openable cards have no-send `needs_more_info` outcomes; 0 unreviewed approved-route cards remain.
- Safety counters: all 596 `launch_readiness_status=manual_review` and `outreach_status=needs_review`; 0 ready_for_outreach, 0 pitch_ready, 0 `outreach_status:new`.
- Dashboard server is live at `http://127.0.0.1:8000/` on PID 89260.
## Current Work State
- GLM locked templates exist for all five specific izakaya profiles: yakitori/kushiyaki, kushiage, seafood/sake/oden, tachinomi, robatayaki.
- Codex routing now maps those profiles to dedicated locked HTML templates in outreach selection, state audit expectations, review guidance, manual import, and execution-plan artifacts.
- Generic profiles still use existing assets: ramen food, izakaya food/drinks, izakaya drinks, and ticket-machine guide as applicable.
- Dashboard primary UI is simplified: no visible phase plan/build nav/queue-filter block; filters are under Advanced Filters; lead cards show route/profile/package, evidence, next action/outcome, and Preview.
- Latest no-send artifacts after review outcomes: `state/review_batches/pitch-card-review-20260502T162943Z.*`, `pitch-card-review-wave-20260502T162943Z.*`, and `state/execution_plans/restaurant-lead-execution-plan-20260502T162944Z.*`.
- Needs-more-info enrichment lane is active: `state/review_batches/needs-more-info-enrichment-20260502T164825Z.*` has 401 cards / 4 batches / 7 packs.
- Latest execution artifact `state/execution_plans/restaurant-lead-execution-plan-20260502T164833Z.*` includes the enrichment summary.
## Acquisition / Search Notes
- `webserper` is the intended no-key acquisition path and does not require Serper credits; Scrapling/local fetch paths remain available.
- Paid `serper` is unavailable due to credits, Google Places key is unavailable, and the five-city directory source is exhausted through page 100.
## Next Work
- Work needs-more-info enrichment batches without outbound: email owner-route, name-source, scope, and contact-form-route checks.
- Regenerate enrichment/review/execution artifacts after enrichment outcomes change.
- Do not promote records or begin outbound without an explicit current-chat instruction.
## Last Verification
- Tests passed: `tests/test_website.py -q` 12, `tests/test_api.py -q` 117, `tests/test_restaurant_lead_verification.py -q` 40, `tests/test_review_batches.py -q` 4.
- Latest safety/audit check: 596 leads, all `manual_review` + `needs_review`; 0 pitch_ready, 0 ready_for_outreach, 0 `outreach_status:new`; `pipeline.cli audit-state` checked 604 with 0 findings.
