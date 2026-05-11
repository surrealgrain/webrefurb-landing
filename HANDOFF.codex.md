# WebRefurbMenu Codex Handoff
Updated: 2026-05-11.
Startup read path: `AGENTS.md` -> `HANDOFF.codex.md` only.

## Current Product
- Clean reset to one product: `english_qr_menu_65k` / English QR Menu + Show Staff List / 65,000 yen.
- Customer flow: scan QR, read English menu, Add to list, review list, Show Staff List with Japanese item names first.
- This is not a staff-side order flow; no checkout, POS, table workflow, or list submission in customer-facing copy.
- Active lead categories are only `ramen`, `izakaya`, and `skip`.

## Active Rules
- Qualified ramen/izakaya leads recommend `english_qr_menu_65k`.
- First contact uses QR-first copy, generic demo `https://webrefurb.com/demo/`, reply-only CTA, no price, no menu-photo ask, no sample-from-menu claim.
- No first-contact attachments; old samples/drafts are stale and blocked.
- Test sends only to `chris@webrefurb.com`; real sends require explicit manual approval.
- Prices, descriptions, ingredients, and allergy notes publish only when owner-confirmed.

## Key Changes
- Product/scoring/state/send gates: `pipeline/constants.py`, `pipeline/scoring.py`, `pipeline/state_audit.py`, `dashboard/app.py`.
- Outreach reset: `pipeline/outreach.py`, `pipeline/email_templates.py`, `pipeline/evidence_classifier.py`.
- Hosted QR menu and export: `pipeline/qr.py`, `pipeline/package_export.py`, `pipeline/final_export_qa.py`, `pipeline/production_workflow.py`.
- Public site and generic demo: `docs/index.html`, `docs/pricing.html`, `docs/ja/*`, `docs/demo/index.html`.
- Dashboard supports lead -> workspace -> owner review -> QR assets -> publish -> trial -> archive, with browser E2E coverage.

## Validation
- Release gate: `.venv/bin/python scripts/release_gate.py` -> 458 passed, state audit ok, static health ok, secret scan ok.
- Live health: `.venv/bin/python scripts/deployment_health_check.py --mode live --base-url https://webrefurb.com` -> ok.

## Production Ready Target
- Release gate: tests, state audit, static/live site health, banned-term scan, and secret scan all pass.
- Trial lifecycle is tracked from request through live trial, converted/declined, and archive.
- Publish remains blocked until owner confirms prices, descriptions, ingredients, and allergy notes.
- Demo coral/white look is treated as locked unless explicitly redesigned.

## Caveats
- Legacy product tests, old generated package artifacts, old sample templates, and old simulation/review command modules were removed because they encoded the retired print/design/template system.
- Existing lead state is QR-reset audited: old drafts/manual-review are blocked; no real-send path is enabled.
- Keep future cleanup scoped to QR menu, generic demo, send safety, state audit, and owner-confirmed publish/export paths.
