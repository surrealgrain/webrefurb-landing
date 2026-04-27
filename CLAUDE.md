# WebRefurbMenu

English menu translation pipeline for Japanese ramen and izakaya shops.
Japan only. Ramen + izakaya only. Two fixed-price packages.

## Quick Commands

- `python -m pytest tests/ -v` — run pipeline tests
- `python -m pipeline.cli <command>` — CLI entry point

## Scope

- **Market**: Japan only
- **Categories**: Ramen and izakaya only (v1)
- **Packages**: ¥30,000 remote / ¥48,000 in-person delivery + lamination

## Rules

- No HVAC references anywhere in this project
- Binary lead semantics: `lead: true|false`, never "maybe"
- Customer-facing copy never mentions AI, automation, or internal tools
- Preview is illustrative only — production uses owner's photos
