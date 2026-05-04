# WebRefurbMenu

English menu translation pipeline for Japanese ramen and izakaya shops.
Scope: Japan only; ramen + izakaya only; packages are ¥30,000 online delivery, ¥45,000 printed + delivered, and ¥65,000 QR menu system.

## Startup Context

- After this file, read `HANDOFF.md` only.
- Open `PLAN.md`, `PRODUCTION_SIMULATION_TEST_PLAN.md`, raw lead files, or generated reports only when the current task needs that specific detail.
- Keep handoffs compact: target 40 lines or fewer; replace stale facts; do not append logs, raw data, command output, search counts, or plan text.

## Quick Commands

- `.venv/bin/python -m pytest tests/ -v` — run pipeline tests
- `.venv/bin/python -m pipeline.cli audit-state` — fail on stale lead assets, poisoned names, or launch-state drift
- `.venv/bin/python -m pipeline.cli audit-state --repair` — normalize deterministic lead-state drift, then audit again
- `.venv/bin/python -m pipeline.cli <command>` — CLI entry point

## Rules

- No HVAC references anywhere in this project
- Binary lead semantics: `lead: true|false`, never "maybe"
- Approved outreach/contact routes are email and contact forms only. Phone, LINE, Instagram, and walk-ins are reference-only and never make a lead launch-ready.
- Customer-facing copy never mentions AI, automation, or internal tools
- Preview is illustrative only — production uses owner's photos
- Follow `PLAN.md` exactly for product hardening work. Do not skip phase gates or begin real outreach before the plan allows it.
