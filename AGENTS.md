# WebRefurbMenu

After this file, read `HANDOFF.codex.md` only.

## Startup Context

- Keep handoffs compact: target 40 lines or fewer; replace stale facts; do not append logs, raw data, command output, search counts, or plan text.
- Do not use old execution plans, old product package docs, raw lead files, or generated reports as active context unless the current task explicitly asks to audit or migrate that artifact.

## Quick Commands

- `.venv/bin/python -m pytest tests/ -v` — run pipeline tests
- `.venv/bin/python -m pipeline.cli audit-state` — fail on stale lead assets, poisoned names, or launch-state drift
- `.venv/bin/python -m pipeline.cli audit-state --repair` — normalize deterministic lead-state drift, then audit again
- `.venv/bin/python -m pipeline.cli <command>` — CLI entry point

## Rules

- Japan only; active categories are `ramen`, `izakaya`, and `skip`.
- One active product: `english_qr_menu_65k` / English QR Menu + Show Staff List / 65,000 yen.
- Old package IDs and old print/design-first package logic are legacy-only; they must not appear in active recommendations, customer-facing UI, outbound copy, or dashboard primary UI.
- No HVAC references anywhere in this project.
- Lead semantics are binary: `lead: true|false`, never `maybe`.
- Approved outreach/contact routes are email and contact forms only. Phone, LINE, Instagram, reservations, map URLs, walk-ins, and websites are reference-only.
- Customer-facing copy never mentions AI, automation, scraping, crawler, classifier, internal tools, source policy, or pipeline mechanics.
- Customer-facing copy must not call the product an ordering system, QR ordering system, POS, checkout, place order, submit order, or payment flow.
- First contact is QR-first, links the generic demo, asks for a reply only, does not ask for menu photos, and does not claim a sample was made from the restaurant's menu.
- Test sends only go to `chris@webrefurb.com`; real sends require explicit manual approval.
- Prices, descriptions, ingredients, and allergy notes publish only after owner confirmation.
- Old outreach drafts and old lead-specific samples are stale unless manually regenerated or approved for the QR product workflow.
