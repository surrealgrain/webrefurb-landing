# Menu Template v4c — Complete Redesign

Updated: 2026-04-28
Commit: `f76ac71` — "Replace cream/off-white menu templates with dark izakaya v4c designs"

## Status: COMPLETE

The v4c dark izakaya design was accepted and has replaced all previous templates.

## Design Language

- **Style**: Dark izakaya — aged wood surface, light text, kanji prominent, red vermillion accent
- **Palette**: `#0f0d0b` bg, `#1c1917` surface, `#f0ebe3` text, `#c53d43` accent
- **Fonts**: Outfit (English headings/body), Shippori Mincho (kanji — traditional Mincho style)
- **Print size**: A5 portrait (148mm × 210mm) — chosen for narrow ramen counter display
- **Texture**: SVG film grain at 0.12 opacity, warm radial glow from top

## Templates

| File | Use Case | Sections |
|---|---|---|
| `izakaya_food_menu.html` | Full izakaya food (double-sided front) | Ramen 8, Small Plates 8, Grilled Skewers 8, Rice & Noodles 8 |
| `izakaya_drinks_menu.html` | Izakaya drinks (double-sided back) | Beer 5, Sake 6, Highball & Shochu 5, Soft Drinks 5 |
| `ramen_food_menu.html` | Ramen-only single-sided A5 | Ramen 8, Sides & Add-ons 6 |
| `ramen_drinks_menu.html` | Ramen shop drinks (simple) | Beer & Highballs 6, Soft Drinks & Tea 6 |
| `ticket_machine_guide.html` | Visual 食券機 mirror | 5×5 grid: 10 ramen, 5 sides, 5 drinks, 5 toppings |
| `qr_code_sign.html` | A6 table/counter sign for QR package | Seal + headline + QR placeholder + camera hint |

## Ticket Machine Guide Details

Mirrors real 食券機 (Glory VT-B series):
- 5-column grid (standard layout for most machines)
- No section labels — visual mapping only
- `grid-spacer` dividers mimic blank/block buttons on real machines
- Standard buttons (72px min-height) for ramen/sides/drinks
- Mini buttons (56px min-height) for toppings (mirrors 3連ミニ)
- Top-left button = best seller with "Popular" tag
- Steps merged into header (seal → title → steps → grid)
- Button text enlarged to 14px English / 11.5px kanji for wall readability

## Japanese Translation Audit

All translations verified and corrected. Key fixes applied:
- 焼き鳥 → もも (Grilled Chicken Thigh — 焼き鳥 is generic, not thigh-specific)
- サッポロプレミアム → サッポロ黒ラベル (export name replaced with domestic product)
- ジャパニーズラガー → オリオンビール (back-translation replaced with real brand)
- ハウスレモネード → メロンソーダ (unnatural katakana replaced with common ramen shop drink)

## Design Decisions Log

1. **v4 warm brown** → rejected ("same vibe problem, squiggly line out of place")
2. **v4b indigo + paper texture** → rejected ("still looks like a wine menu")
3. **v4c dark izakaya** → ACCEPTED
4. Section titles: left-aligned for food menus, center-aligned for ticket guide
9. QR sign is English-only (no kanji except seal stamp) — audience is tourists who can't read Japanese
10. QR sign print size: A6 portrait (105mm × 148mm) — half the ticket machine guide, fits table stands
6. English translations (not romanized Japanese) — tourists need to know what they're ordering
7. Seal stamp auto-sizes via `data-length` attribute (1-6 character scaling)
8. Seal name sourced from `locked_business_name` only (never mutable `business_name`)

## Pipeline Changes

- `render.py`: default template changed from `master_menu.html` to `izakaya_food_menu.html`
- `cli.py`: help text updated to remove `master_menu.html` reference
- Pipeline renderer uses `data-slot` architecture — compatible with all new templates
- **Note**: Pipeline still expects v1/v2 section structure. The v4c templates use a different HTML structure (sections-stack, section-header with section-title + section-kanji). The renderer's `_replace_section()` regex patterns may need updating to match the new structure. This is a known gap.

## Backups

- Original v3 templates preserved at `assets/templates_v3_original/`

## Pending / Next Steps

1. **Pipeline renderer update** — `_replace_section()` regex needs updating for v4c HTML structure
2. **Seal checksum verification** — SHA256 checksum of `locked_business_name` at render/send time (see memory: `seal_name_checksum.md`)
3. **Template selection logic** — pipeline should auto-select template based on `establishment_profile` (izakaya vs ramen)
4. **Consider izakaya section reordering** — for pure izakaya, Small Plates should lead instead of Ramen
5. **Multi-language variants** — if expanding beyond English, template architecture supports it via data-slots

## Key Constraints

- Market: Japan izakayas and ramen shops only
- No prices on templates (longevity)
- English descriptions (not romanized Japanese names)
- Data-slot driven architecture must be preserved
- Seal name must use `locked_business_name` exclusively
