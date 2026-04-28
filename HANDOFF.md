# WebRefurbMenu Handoff

Updated: 2026-04-28

## Current State

- Branch: `main`
- Active execution plan: `PLAN.md`
- Active phase: `P4 - Make Outreach Convert`
- Phase status: in progress
- Working tree is dirty (uncommitted changes from this session)
- `P1` is complete and recorded in `PLAN.md`.
- `P2` is complete and recorded in `PLAN.md`.
- `P3` is complete and recorded in `PLAN.md`.
- Current focus: outreach template rewrite, reply translation, Japanese website copy audit, v4c menu design

## Completed This Session

### 1. Menu Design v4c — COMPLETE
All templates redesigned to dark izakaya style. See `MENU_DESIGN_V4_HANDOFF.md` for full details.
- Palette: `#0f0d0b` bg, `#1c1917` surface, `#f0ebe3` text, `#c53d43` accent
- Fonts: Outfit (English), Shippori Mincho (kanji)
- Templates: izakaya food, izakaya drinks, ramen food, ramen drinks, ticket machine guide, QR code sign

### 2. Outreach Template Rewrite — COMPLETE
- **Old**: 8 per-profile email body variants in `email_templates.py`
- **New**: 5 situation-based templates in `outreach.py` keyed on physical ordering problem:
  - `ramen_menu` — ramen shop with paper menu
  - `ramen_menu_and_machine` — ramen shop with both menu and ticket machine
  - `izakaya_menu` — izakaya with paper menu
  - `machine_only` — shop with ticket machine only
  - `unknown` — generic fallback
- Profile still determines which sample PDF gets attached
- `email_templates.py` stripped to: subjects + LINE short-form templates + contact form body
- `build_outreach_email()` in `outreach.py` assembles from shared structure + situation parts
- All outreach copy passed 5-pass Japanese verification

### 3. Reply Translation System — COMPLETE
- **`pipeline/translate_reply.py`** — LLM-powered English→Japanese translation for operator replies
  - `translate_reply(english_text, business_name=None, model="google/gemini-2.0-flash-001")`
  - System prompt encodes 5-pass verification rules (grammar, naturalness, politeness, tone, formatting)
  - Uses OpenRouter API via `pipeline/llm_client.py`
- **`dashboard/app.py`** — `POST /api/translate-reply` endpoint
- **`dashboard/templates/index.html`** — "Translate to Japanese" button in reply compose area

### 4. Japanese Website Copy Audit — COMPLETE
All Japanese copy on `docs/ja/` verified and corrected for natural language.

**index.html fixes (7):**
- 「接客や注文時の負担を減らす」→「海外からのお客様へのご説明の手間を減らし、お客様ご自身でメニュー内容をご確認いただけるようにします」
- 「スムーズな注文導線」→「スムーズな注文の流れ」(導線 is UX jargon)
- Rewrote insight about ordering confusion — warmer tone, confident phrasing
- 「一般的な翻訳サービスではありません」→「単なる翻訳サービスではありません」
- 「3つの固定料金パッケージです」→「3つの料金プランをご用意しています」
- 「印刷用の英語メニューデータをオンラインで納品します」→「印刷用データをオンラインでお届けします」
- 「別途お見積りできます」→「別途ご相談に応じます」(fixed 謙譲語 mismatch)

**pricing.html fixes (6):**
- 「内容量」→「メニューの内容」(内容量 = net weight, wrong compound)
- 「ホスティング」→「Web掲載」(tech jargon restaurant owners won't know)
- Simplified dense QR description
- 「軽微修正」→「軽微な修正」(missing particle)
- 「書き出しデータ引き渡し後の公開終了を選べます」→「データをお渡ししての公開終了をお選びいただけます」
- 「別途お見積もりとなります」→「別途お見積もりいたします」(謙譲語 for speaker's action)

### 5. QR Code Sign Template — COMPLETE
- `assets/templates/qr_code_sign.html` — A6 (105mm × 148mm) table/counter sign
- English-only (no kanji except seal stamp) — audience is tourists
- "Scan for English Menu" headline, camera icon hint, QR placeholder

## Test Results (Last Run)

- 295 passed, 2 pre-existing website test failures (unrelated to changes)

## Files Changed This Session

| File | Change |
|---|---|
| `pipeline/outreach.py` | Rewritten — situation-based templates |
| `pipeline/email_templates.py` | Stripped to subjects + LINE + contact form |
| `pipeline/translate_reply.py` | New — LLM reply translation |
| `dashboard/app.py` | Added translate-reply endpoint |
| `dashboard/templates/index.html` | Translate button in replies area |
| `assets/templates/qr_code_sign.html` | New — A6 QR sign |
| `assets/templates/*.html` | All menu templates replaced with v4c dark designs |
| `docs/ja/index.html` | Japanese copy corrections (7 edits) |
| `docs/ja/pricing.html` | Japanese copy corrections (6 edits) |
| `tests/test_outreach.py` | Rewritten for situation-based approach |
| `tests/test_api.py` | Updated assertions for new template labels |
| `MENU_DESIGN_V4_HANDOFF.md` | Updated with QR sign + design decisions |

## Uncommitted Changes in Working Tree

- `MENU_DESIGN_V4_HANDOFF.md` — staged edits
- `assets/templates/v4c_food_mockup.html` — deleted
- All files listed above in "Files Changed This Session" are uncommitted

## Key Architecture Notes

- **Translation 5-pass system** saved as memory reference (`translation_verification.md`)
- **FROM name**: always `Chris（クリス）` — never plain "Chris" (see memory: `from_name_japanese.md`)
- **Outreach situations**: 5 types, not 8 profiles — see `_SITUATIONS` dict in `outreach.py`
- **Seal stamp**: auto-sizes via `data-length`, name from `locked_business_name` only
- **v4c design tokens**: `#0f0d0b` / `#1c1917` / `#f0ebe3` / `#c53d43`

## Pending / Next Steps

1. **Commit** — all changes from this session are uncommitted
2. **Pipeline renderer regex update** — `_replace_section()` in `render.py` still expects v1/v2 HTML structure. v4c templates use different section markup. Known gap that will break automated PDF generation.
3. **Seal checksum verification** — SHA256 of `locked_business_name` at render/send time (see memory: `seal_name_checksum.md`)
4. **Template auto-selection** — pipeline should auto-select template based on `establishment_profile`
5. **Preview.py CSS** — still uses old cream/off-white palette, not v4c dark style
6. **Consider izakaya section reordering** — for pure izakaya, Small Plates should lead instead of Ramen
7. **Continue P4** — generate more shop-specific outreach previews, reduce reliance on generic PDF attachments

## Previous Session History

- P0 complete, P1 complete, P2 complete, P3 complete
- Business name hardening: `locked_business_name` is authoritative, two-source verification
- Contact routes: email, LINE, Instagram, phone, walk-in, contact form, map URL
- Profile-aware outreach with sample-strategy labels in dashboard
- QR hardening: needs-extraction state, owner confirmation, Package 3 promise
- See git log for full history

## Execution Freeze

Until `P5` gate evidence is truly satisfied:
- do not approve real customer packages
- do not send real outreach
