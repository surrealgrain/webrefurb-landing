# Product Audit Hardening Plan

## Summary

Implement the 2026-04-29 audit as a pre-launch hardening pass before `P7 Controlled Launch`. Real outreach remains frozen until every gate below passes, `PLAN.md` is updated, state is backed up, and launch authorization is explicit.

This plan keeps the three fixed prices and existing package keys, but changes the product framing from “translation service” to “English ordering system” across qualification, outreach, quotes, dashboard, and public pages.

## Execution Checklist

### Done

- [x] Saved this Product Audit Hardening Plan in `PLAN.md` as the only active plan.
- [x] Marked the older phase plan obsolete in `HANDOFF.md`.
- [x] Backed up `state/` before migration.
- [x] Migrated stale lead state to current package keys/readiness fields.
- [x] Quarantined the stale Tsukada Nojo record as disqualified / do-not-contact.
- [x] Added tests proving stale package keys, bracketed previews, and chain-like records cannot remain launch-ready.
- [x] Added persisted `lead_evidence_dossier`, `proof_items`, and `launch_readiness_status` while preserving binary `lead: true|false`.
- [x] Added required dossier states for ticket machines, English menus, menu complexity, and izakaya rules.
- [x] Added dashboard readiness display and outreach gating based on dossier readiness.
- [x] Reworked search defaults and qualification toward friction-first ramen/izakaya evidence.
- [x] Added hard disqualification for already-solved English/multilingual QR, chain/franchise-like, and out-of-scope records.
- [x] Updated package recommendation logic for ramen ticket machines, ramen without machines, izakaya drink/course friction, and custom quote gates.
- [x] Reworked outreach to shop-specific diagnosis copy instead of price-led cold pitches.
- [x] Added unknown-evidence check phrasing, sender identity, opt-out wording, do-not-contact preservation, and message variant logging.
- [x] Hardened previews against bad snippets, boilerplate, reservation-only copy, bracketed fallbacks, unconfirmed prices, and no-proof previews.
- [x] Removed unsafe stale public QR draft placeholders.
- [x] Added dashboard lead dossier modal visibility and browser screenshots for the dossier view.
- [x] Updated customer-facing package labels while preserving package keys and prices.
- [x] Updated quote/order/dashboard/site copy toward English ordering systems/materials and risk reversal.
- [x] Added controlled launch batch records under `state/launch_batches/`.
- [x] Added batch 2 blocking until batch 1 is reviewed.
- [x] Added per-lead launch measurement fields: dossier states, selected channel, message variant, proof asset, package, contacted timestamp, reply status, objection, opt-out/bounce, operator minutes, and outcome.
- [x] Verified current code with `.venv/bin/python -m pytest tests/ -q` (`332 passed`) and `git diff --check`.

### Next

- [ ] Wait for explicit launch authorization from the user. No real outreach starts before this.
- [ ] After authorization, select the first controlled launch batch of 5-10 launch-ready shops.
- [ ] Ensure the first batch includes at least one ramen ticket-machine lead and one izakaya drink/course lead.
- [ ] Create the first batch record under `state/launch_batches/`.
- [ ] Manually review every selected lead dossier, proof item, channel, message variant, and recommended package before contact.
- [ ] Run the final gate again before contact: `.venv/bin/python -m pytest tests/ -q` and `git diff --check`.

### Left To Do After Authorized Batch 1

- [ ] Send only the authorized first controlled batch through approved channels.
- [ ] Record per-lead contacted timestamp, reply/no reply, objection, opt-out/bounce, operator minutes, and outcome.
- [ ] Review batch 1 results before any batch 2 work.
- [ ] Update scoring, search terms, outreach wording, and package recommendation from batch 1 results.
- [ ] Keep batch 2 blocked until batch 1 review is saved.
- [ ] Repeat final tests and diff checks after any scoring/search/outreach/package changes.

### Blocked

- [ ] Real outreach is blocked until explicit launch authorization.
- [ ] Controlled launch batch 1 is blocked until explicit launch authorization.
- [ ] Controlled launch batch 2 is blocked until batch 1 has been reviewed.
- [ ] Any lead without customer-safe proof remains manual review or skipped, not contacted.

## Phases

### Phase 1: Reconcile Plan And State

- Update [PLAN.md](/Users/chrisparker/Desktop/WebRefurbMenu/PLAN.md) with new audit-hardening phases between completed P6 and blocked P7.
- Back up `state/` before any migration.
- Migrate stale lead records:
  - Map obsolete package keys/prices to current package keys.
  - Flag any chain-like, already-solved, or bad-preview records as `do_not_contact` or `needs_manual_review`.
  - Specifically quarantine the Tsukada Nojo stale record from outreach and mark why.
- Add tests proving stale package keys, bracketed previews, and chain-like records cannot remain launch-ready.

### Phase 2: Lead Evidence Dossier

- Add a persisted `lead_evidence_dossier` / `launch_readiness` structure while preserving binary `lead: true|false`.
- Required states:
  - `ticket_machine_state`: `present`, `absent`, `unknown`, `already_english_supported`
  - `english_menu_state`: `missing`, `weak_partial`, `image_only`, `usable_complete`, `unknown`
  - `menu_complexity_state`: `simple`, `medium`, `large_custom_quote`
  - `izakaya_rules_state`: `none_found`, `drinks_found`, `courses_found`, `nomihodai_found`, `unknown`
- Store proof items with source type, URL, snippet/screenshot path, operator visibility, customer-preview eligibility, and rejection reason.
- Make dashboard lead cards show readiness: `ready_for_outreach`, `manual_review`, or `disqualified`.
- Gate outreach generation on dossier readiness, not just `menu_evidence_found` or `machine_evidence_found`.

### Phase 3: Friction-First Search And Qualification

- Replace generic search defaults in [pipeline/search_scope.py](/Users/chrisparker/Desktop/WebRefurbMenu/pipeline/search_scope.py) with friction-first jobs:
  - Ramen: `券売機 ラーメン {area}`, `食券 ラーメン {area}`, `ラーメン メニュー 写真 {area}`, RamenDB/official-site lookups.
  - Izakaya: `飲み放題 コース 居酒屋 {area}`, `お品書き 居酒屋 {area}`, `居酒屋 メニュー 写真 {area}`, Hotpepper/Tabelog/official/social lookups.
  - English-solution checks: English menu, multilingual QR, and existing ordering support.
- Add hard disqualification for `english_menu_state=usable_complete`, multilingual QR already present, known chain/franchise infrastructure, or out-of-scope category.
- Treat unknown machine/English/menu-complexity evidence as manual review or check-phrased outreach, never as a positive assumption.
- Update package recommendation logic:
  - Ramen + ticket machine: Package 2 by default, Package 1 only when print-yourself is clearly acceptable.
  - Ramen without machine: Package 1 for simple menus, Package 2 for counter-ready printed use.
  - Izakaya with drink/course/nomihodai friction: Package 3 if updates are likely, Package 2 if printed table menus are stable.
  - Large/complex menus: custom quote gate.

### Phase 4: Shop-Specific Diagnosis Outreach

- Replace the old price-led pitch path in [pipeline/outreach.py](/Users/chrisparker/Desktop/WebRefurbMenu/pipeline/outreach.py) and retire or rewrite `pipeline/pitch.py`.
- First message must answer: why this shop, what friction was found, what proof/sample is available, and the low-effort next step.
- Do not lead with all three prices in cold outreach. Show only the recommended outcome internally and let pricing live on the site/quote flow.
- If evidence is unknown, use check phrasing such as “I wanted to check whether...” instead of asserting ticket machines or English gaps.
- Add sender identity, contact info, and opt-out wording to commercial email paths; preserve do-not-contact handling for all channels.
- Add message variant logging for controlled launch measurement.

### Phase 5: Preview And Sample Quality Gates

- Harden [pipeline/preview.py](/Users/chrisparker/Desktop/WebRefurbMenu/pipeline/preview.py):
  - Reject snippets that look like calendar text, headers/footers, search/tel boilerplate, reservation-only copy, or unrelated chain pages.
  - Block bracketed fallback translations from all customer-visible previews.
  - Do not show prices in outreach previews unless owner-confirmed.
  - If no safe proof item exists, block customer preview and require manual review.
- Redesign sample proof around operational clarity:
  - Ramen samples show toppings, sets, noodle/soup choices, add-ons, and ticket-machine mapping when proven.
  - Izakaya samples show drinks, courses, nomihodai rules, shared plates, and owner-confirmed ingredient notes only.
  - QR samples show a real hosted menu flow plus QR sign.
- Add rendered/browser verification for homepage, pricing pages, outreach modal, lead dossier view, sample previews, and QR page.

### Phase 6: Positioning, Packages, Risk Reversal

- Keep package keys and prices, but rename customer-facing labels:
  - `package_1_remote_30k`: English Ordering Files, ¥30,000
  - `package_2_printed_delivered_45k`: Counter-Ready Ordering Kit, ¥45,000
  - `package_3_qr_menu_65k`: Live QR English Menu, ¥65,000
- Update constants, quote scope, invoice artifacts, dashboard selectors, website English/Japanese copy, and tests.
- Replace “translation service” language with “English ordering system/materials” while still describing translation as one included component.
- Add explicit risk reversal everywhere relevant: owner approval before delivery, one correction window, no price/allergen claims without owner confirmation, and clear custom-quote limits.
- Public site first viewport should show proof of actual outputs: menu, ticket-machine guide, QR sign, and before/after ordering clarity.

### Phase 7: Controlled Launch Measurement

- Add launch batch records under `state/launch_batches/`.
- Track per lead: dossier states, selected channel, message variant, proof asset, recommended package, contacted timestamp, reply/no reply, objection, opt-out/bounce, operator minutes, and outcome.
- Dashboard must block batch 2 until batch 1 has been reviewed.
- First batch remains 5-10 shops, including at least one ramen ticket-machine lead and one izakaya drink/course lead.
- After batch review, update scoring, search terms, outreach wording, and package recommendation before scaling.

## Public Interfaces And Data Changes

- `QualificationResult` gains dossier/readiness fields, but `lead` remains strictly boolean.
- Lead JSON gains `lead_evidence_dossier`, `launch_readiness_status`, `proof_items`, `message_variant`, and launch outcome fields.
- Package labels change customer-facing names only; package keys and prices remain stable.
- Dashboard APIs for outreach must reject non-ready leads with explicit reasons instead of generating weak drafts.
- Quote/order APIs continue using current package keys, with updated labels, scope text, correction window, and risk-reversal copy.

## Test Plan

- Unit tests for dossier state derivation, already-solved rejection, chain/franchise rejection, package recommendation, stale-state migration, and friction-first search query generation.
- Preview tests proving bad snippets, bracketed fallback translations, unconfirmed prices, and no-proof previews are blocked.
- Outreach tests proving diagnosis copy, unknown-state check phrasing, no all-price cold pitch, sender identity, opt-out handling, and no AI/automation/internal-tool language.
- Website tests for new package names, fixed prices, ordering-system positioning, no HVAC references, and no forbidden customer-facing terms.
- Integration tests for lead -> dossier -> outreach draft -> quote -> payment/intake -> owner approval -> final export.
- Browser/render verification for dashboard lead dossier, outreach modal, homepage, pricing pages, sample menu previews, and QR menu/sign.
- Final gate: `.venv/bin/python -m pytest tests/ -q` and `git diff --check`.

## Assumptions

- No real outreach is sent during this work.
- Fixed prices remain ¥30,000, ¥45,000, and ¥65,000.
- Package keys stay unchanged for compatibility.
- Existing P5/P6 paid operations work is treated as completed, then extended by the new audit gates.
- If proof cannot be safely shown to an owner, the lead is manual review or skipped, not contacted.
