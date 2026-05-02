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
- Pitch-card breakdown: 355 needs_email_review, 20 needs_name_review, 26 needs_scope_review.
- Safety counters: all 596 `launch_readiness_status=manual_review` and `outreach_status=needs_review`; 0 ready_for_outreach, 0 pitch_ready, 0 `outreach_status:new`.
- Dashboard server is live at `http://127.0.0.1:8000/` on PID 76776.
## Current Work State
- GLM locked templates exist for all five specific izakaya profiles: yakitori/kushiyaki, kushiage, seafood/sake/oden, tachinomi, robatayaki.
- Codex routing now maps those profiles to dedicated locked HTML templates in outreach selection, state audit expectations, review guidance, manual import, and execution-plan artifacts.
- Generic profiles still use existing assets: ramen food, izakaya food/drinks, izakaya drinks, and ticket-machine guide as applicable.
- Latest no-send artifacts after routing: `state/review_batches/pitch-card-review-20260502T162216Z.*`, `pitch-card-review-wave-20260502T162216Z.*`, and `state/execution_plans/restaurant-lead-execution-plan-20260502T162216Z.*`.
- Review wave remains 4 batches / 38 operator packs / 401 cards; all artifact policies are review-only/no-send.
## Acquisition / Search Notes
- `webserper` is the intended no-key acquisition path and does not require Serper credits; Scrapling/local fetch paths remain available.
- Paid `serper` is unavailable due to credits, Google Places key is unavailable, and the five-city directory source is exhausted through page 100.
## Next Work
- Work operator review-wave batches in order, saving only hold/needs_more_info/reject outcomes.
- Regenerate review/execution artifacts after review outcomes change.
- Do not promote records or begin outbound without an explicit current-chat instruction.
## Last Verification
- Tests passed: `tests/test_website.py -q` 12, `tests/test_api.py -q` 117, `tests/test_restaurant_lead_verification.py -q` 40, `tests/test_review_batches.py -q` 4.
- Additional routing/audit tests passed: outreach, restaurant_email_import, state_audit, restaurant_execution_plan, review_batches (78 total).
- `pipeline.cli audit-state` passed: 604 checked, 0 findings; dashboard GET `/` returned HTML.
