# Menu Template v4 Redesign — Session Handoff

Updated: 2026-04-28

## Task

UI/UX improvement pass on the master menu template (`assets/templates/master_menu.html`) for izakaya/ramen target market. Use StyleSeed skills exclusively. Original must stay untouched until confirmed.

## What Was Done

1. **Backup created**: `assets/templates_v3_original/` — verified copy of the original templates
2. **2026 design trend research completed** (DuckDuckGo + webReader):
   - Creative Bloq (Dec 2025): "Texture, warmth and tactile rebellion"
   - YoungMindInteractive (Apr 2026): "Imperfection as aesthetic choice, tactile/sensory design, type as design"
   - Key trends: anti-AI crafting (handmade marks), emotional color, bold minimalism updated with warmth, tactile/sensory surfaces
3. **StyleSeed audit run**: Scored B- — Cormorant Garamond reads "European luxury hotel," not izakaya
4. **Two mockups produced and rejected**:
   - `v4_food_mockup.html` — warm brown palette, DM Sans, brush-stroke motif → "same vibe problem, squiggly line out of place"
   - `v4b_food_mockup.html` — restored indigo, paper texture, lighter heading weight → "still looks like a wine menu"

## Core Problem (Unresolved)

The current template design language is fundamentally **European fine dining**:
- Cormorant Garamond serif → wine list / luxury hotel
- Cream surface + indigo border → formal restaurant card
- Rigid 2x2 section grid → corporate / hotel minibar list
- Symmetrical layout with flanking rules → traditional European print

**Incremental tweaks (font weight, texture opacity, section borders) do NOT fix this.** The entire visual language needs to change to something that reads "izakaya / ramen" — warm, casual, approachable, Japanese — not "French bistro."

## What the User Said

- "it still looks like a wine menu"
- "we need to try a completely different design style"
- "don't japanese love blue?" — indigo blue IS culturally appropriate, keep it
- "didn't the research say add texture?" — texture should be the hero change, not barely visible
- The user likes "minimalist, elegant simplicity" but it needs to feel appropriate for izakayas/ramen spots
- The squiggly brush-stroke motif was rejected — clashing with the professional look

## What a Fresh Approach Should Try

A **completely different design style** — not tweaks to the current template. Options worth exploring:

1. **Japanese stamp/seal aesthetic** — hanko-inspired marks, washi paper texture as the dominant surface, indigo + red accents, more playful asymmetry
2. **Kraft/brown paper casual** — textured kraft background, stamp-style type, hand-drawn section dividers, warm and unpretentious
3. **Japanese newspaper/woodblock** — traditional print aesthetic, vertical elements, sumi-e influenced, serif but a Japanese serif
4. **Modern Japanese minimal** — stark but warm, lots of negative space, single accent, but with Japanese aesthetic cues (not European)
5. **Chalkboard/casual** — dark textured background, handwritten-style fonts, casual and approachable

The design should still be print-ready (A3 landscape for dual-panel, A4 for single panel) and use the data-slot architecture.

## Files

- Original (untouched): `assets/templates/master_menu.html`
- Backup: `assets/templates_v3_original/`
- Rejected mockup 1: `assets/templates/v4_food_mockup.html`
- Rejected mockup 2: `assets/templates/v4b_food_mockup.html`

## Key Constraints

- Market: Japan izakayas and ramen shops only
- Original template must stay untouched until user confirms
- Use StyleSeed skills (ss-audit, ss-lint, ss-review, ss-tokens, etc.)
- Print-ready: A3 landscape dual-panel, A4 single panel
- Data-slot driven architecture must be preserved
- DuckDuckGo search installed: `.venv/bin/python -c "from ddgs import DDGS; ..."` (no API key needed)
