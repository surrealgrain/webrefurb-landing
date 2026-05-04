# WebRefurbMenu Handoff
Updated: 2026-05-04. Compact resume file; replace stale facts instead of appending logs.
Startup read path: read `AGENTS.md`, then this file only. Open long docs, raw leads, reports, or state artifacts only for a specific blocker.

## Safety Boundary
- No restaurant email, contact-form submit, launch batch, or business contact unless explicitly requested in the current chat and production gates are unlocked.
- Approved routes are email/contact forms only; phone, LINE, Instagram, reservations, map URLs, walk-ins, and websites are reference-only.
- Customer-facing copy must not mention AI, automation, scraping, internal tools, source policy, or pipeline mechanics.

## Current Snapshot
- Branch per prior handoff: `codex/phase11-contact-form-batch`; unrelated dirty files exist, so stage only mission files.
- `audit-state` passes: 579 checked; 261 `lead=true` all `manual_review`; 310 disqualified/do-not-contact; 0 `ready_for_outreach`.
- Operator state: 248 `review`, 323 `skip`; no operator-ready launch candidates.
- Package distribution: none 79, Package 1 394, Package 2 1, Package 3 97.
- Controlled pilot remains blocked: `ready_for_outreach_count_below_5`, `missing_ramen_ticket_machine_candidate`, `missing_izakaya_drink_or_course_candidate`.

## Latest Audit
- Report: `state/audits/system-dashboard-audit-20260503T234743Z/AUDIT_REPORT.md`.
- Browser evidence: `state/audits/system-dashboard-audit-20260503T234743Z/screenshots/` plus Run 8 screenshots in `state/qa-screenshots/system-dashboard-audit-20260503T234743Z/`.
- Browser/API audit captured 24 desktop/mobile screens: no console/page errors, no non-font request failures, no horizontal overflow, no public link failures.
- Customer-facing copy scan: 61 HTML surfaces + 5 generated email variants; 0 forbidden-term or stale-placeholder findings.
- Audit findings fixed in current uncommitted tree: frozen `POST /api/launch-batches` now returns controlled `423 launch_frozen:*`; audited public/dashboard controls render at least 44px.
- Latest uncommitted checks also fixed evidence-gated dashboard/send compatibility plus owner-experience gaps: Japanese free-sample CTAs, one-correction policy consistency, ticket-machine guides staying eligible for Package 1 online delivery, and visible sample caveats in active templates.
- 2026-05-04 no-send production sim: `state/production-sim/production-sim-codex-realworld-20260504-fixed/report.md` -> P0/P1 zero, P2 broad-corpus expansion still deferred, no external send, no real launch batch.
- Browser reply-flow simulation found and fixed Package 3 QR replies downgrading to Package 1 in workspace/build modal; evidence screenshot: `state/qa-screenshots/production-sim-codex-realworld-20260504-fixed-reply-flow/reply-build-modal.png`.
- Run 8 readiness: `state/run8-readiness/system-dashboard-audit-20260503T234743Z.json` with `ok_until_send_gate=true`, no external send, no real launch batch.
- Export QA: `state/export-qa/system-dashboard-audit-20260503T234743Z-package1.json`, `state/export-qa/system-dashboard-audit-20260503T234743Z-package2.json`, `state/export-qa/qr-cdc592e3.json`.

## Email Smoke
- Exactly 5 real fixture emails were sent through Resend to `chris@webrefurb.com` only, all with `[WEBREFURB TEST]` subjects.
- Variants covered: ramen menu, ramen ticket-machine, izakaya food/drinks, izakaya nomihodai/course, and machine-only ordering guide.
- Evidence: `state/test-email-smoke/test-email-smoke-20260503T235037Z/smoke-report.json`; state digests prove no lead, launch-batch, or dashboard sent-record mutation.

## Last Verification
- Focused owner-experience tests: `tests/test_website.py tests/test_render_templates.py tests/test_paid_ops.py tests/test_production_workflow.py tests/test_final_export_qa.py tests/test_qr.py -q` -> 48 passed.
- Full tests: `.venv/bin/python -m pytest tests/ -q` -> 951 passed.
- `.venv/bin/python -m pipeline.cli audit-state` -> pass.
- `git diff --check` -> pass.
