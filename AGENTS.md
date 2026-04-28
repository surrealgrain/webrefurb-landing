# WebRefurbMenu

English menu translation pipeline for Japanese ramen and izakaya shops.
Japan only. Ramen + izakaya only. Three fixed-price packages.

## Quick Commands

- `python -m pytest tests/ -v` — run pipeline tests
- `python -m pipeline.cli <command>` — CLI entry point

## Scope

- **Market**: Japan only
- **Categories**: Ramen and izakaya only (v1)
- **Packages**: ¥30,000 online delivery / ¥45,000 printed + delivered / ¥65,000 QR menu system

## Rules

- No HVAC references anywhere in this project
- Binary lead semantics: `lead: true|false`, never "maybe"
- Customer-facing copy never mentions AI, automation, or internal tools
- Preview is illustrative only — production uses owner's photos
