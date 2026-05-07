# WebRefurbMenu Codex Handoff
Updated: 2026-05-07.
Startup read path: `AGENTS.md` -> `HANDOFF.codex.md` only.

## Current Product
- Clean reset to one product: `english_qr_menu_65k` / English QR Menu / 65,000 yen.
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
- Dashboard simplified around active category, active product, generic demo, QR draft/review actions.

## Validation
- Focused reset suite passed: `tests/test_qr.py tests/test_outreach.py tests/test_website.py tests/test_search_scope.py tests/test_scoring.py tests/test_state_audit.py`.
- Full remaining suite passed during reset review: `.venv/bin/python -m pytest tests/ -q` -> 468 passed.
- State audit passed: `.venv/bin/python -m pipeline.cli audit-state`.

## Caveats
- Many legacy product tests were deleted because they encoded the removed print/design/template system.
- Existing lead state was repaired to mark stale old drafts/manual-review; no real-send path was enabled.
- Worktree already had broad unrelated changes before this reset; do not revert unrelated user/model work.
