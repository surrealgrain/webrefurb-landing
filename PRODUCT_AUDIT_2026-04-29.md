# WebRefurbMenu Product Audit

Date: 2026-04-29
Active launch constraint: real outreach remains frozen until the `PLAN.md` gates allow it.

## Product Thesis

WebRefurbMenu should not be sold as "menu translation." That is too generic, too cheap in the market, and too easy for an owner to compare against translation marketplaces or low-cost QR tools.

The product should be sold as a done-for-you English ordering system for independent ramen shops and izakayas where foreign guests already create ordering friction:

- Ramen: ticket machines, toppings, set menus, add-ons, noodle/soup choices, rush-hour pressure.
- Izakaya: drinks, courses, nomihodai rules, shared plates, ingredients, staff explanation load.
- QR: only when the menu changes often or the shop needs a live mobile version, not as a generic "website menu."

The no-brainer customer is an independent shop in a tourist-exposed area with clear Japanese-only ordering friction and no usable English menu. The product becomes weak when it targets chains, shops that already have good English support, or shops where the ordering problem is not proven.

## Market Reality

- JNTO reported 42,683,600 visitor arrivals to Japan in 2025, a new annual high.
- Japan Tourism Agency reported 2025 inbound visitor spend of JPY 9.4549 trillion, including JPY 2.0688 trillion on food and beverages; general visitors spent about JPY 50,221 per person on food and drink.
- Generic alternatives are cheap: menu translation marketplace offers can sit around JPY 12,000 to JPY 24,000, while QR/menu SaaS products advertise low monthly prices. WebRefurbMenu's fixed prices only make sense if the offer is framed as done-for-you, shop-specific operational help, not raw translation.
- Cold email is legally and trust-sensitive in Japan. The anti-spam regime is opt-in by default, with exceptions for published business addresses when no refusal is shown. Any email path still needs sender identity, opt-out handling, and careful one-to-one targeting.

Sources:

- JNTO 2025 arrivals: https://www.jnto.go.jp/news/press/20260121_monthly.html
- Japan Tourism Agency 2025 spend summary: https://www.mlit.go.jp/kankocho/content/001992584.pdf
- Japan Tourism Agency survey page: https://www.mlit.go.jp/kankocho/tokei_hakusyo/gaikokujinshohidoko.html
- Anti-spam law summary: https://www.dekyo.or.jp/soudan/contents/taisaku/1-2.html
- Guideline PDF on public-address exceptions: https://www.caa.go.jp/policies/policy/consumer_transaction/specifed_email/pdf/110831kouhyou_2.pdf
- NAIway menu translation benchmark: https://www.naiway.jp/en/translation-fields/category-media/menus/
- Lingualn QR menu benchmark: https://lingualn.com/
- SORENA QR menu benchmark: https://www.sorena-menu.com/
- Lancers menu translation benchmark: https://www.lancers.jp/menu/detail/1256310

## Current Product Audit

What is strong:

- Scope is tight: Japan only, ramen and izakaya only, three fixed packages.
- P1-P4 work made the pipeline much safer: structured menu data, price confirmation gates, QR gating, non-email contact routes, profile-aware outreach, ticket-machine support, and safety tests.
- The best positioning already exists in pieces: "not generic translation," order-confidence, ticket machine clarity, drinks/courses/nomihodai clarity.
- The fixed prices can work if the owner sees operational value. One extra group at an izakaya or a few extra tourist covers at a ramen shop can plausibly justify the service.

What is still weak:

- Search is too generic. Queries such as `ramen restaurants Kyoto` and `izakaya restaurants Tokyo` produce broad candidates, not high-friction candidates.
- Machine and English-menu evidence are not yet strong enough as launch gates. The system records `machine_evidence_found` and `english_availability`, but it needs a stricter "known/unknown/already solved" evidence dossier before outreach copy is selected.
- State has stale warning examples. One lead record for Tsukada Nojo is chain-like, has old package keys/pricing, mismatched sample assets, and poor scraped preview snippets. Even if stale, this is exactly the failure mode the product must prevent.
- Outreach is polite but still feels like a service introduction. It should feel like a specific diagnosis: "I found this ordering friction at your shop; here is the exact fix."
- Shop-specific previews can contain bad scraped snippets and bracketed fallback translations if not aggressively filtered. That hurts trust.
- Package pricing is defensible only when the scope and outcome are crisp. "English menu files" at JPY 30,000 sounds expensive against translation marketplaces; "counter/ticket-machine ordering kit ready to use" sounds much stronger.
- The public site and sample proof are not yet doing enough conversion work. Current screenshots show a polished brand but not enough first-viewport evidence of actual menus, ticket-machine guides, QR signs, and before/after ordering clarity.
- Menu design is tasteful, but it must be judged by order speed, readability under shop lighting, and guest confidence, not by aesthetic polish alone.
- P5 operations appear partially implemented in the working tree while `PLAN.md` still says P5 is not started. That mismatch must be reconciled before launch.
- Email compliance and deliverability should be first-class product constraints, not just send mechanics.

## Audit Framework

Every lead should receive a launch-readiness audit before outreach. The audit result should be operator-visible and should decide whether to contact, which channel to use, which package to recommend, and which proof asset to show.

### 1. Restaurant Fit

Pass only when:

- Japan physical location is confirmed.
- Category is ramen or izakaya.
- Independent/small operator is likely, or multi-location status is explicitly reviewed.
- Current business status appears active.
- Tourist exposure is meaningful: hotspot proximity, station/tourist district, review volume, or foreign-review signals.

Fail or manual review when:

- Chain or franchise is likely.
- Hotel/cafe/sushi/yakiniku/kaiseki/etc. outside v1 scope.
- Website or listing looks stale, placeholder, or directory-only with no corroboration.

### 2. Ordering Friction

Record evidence states separately:

- `ticket_machine_state`: `present`, `absent`, `unknown`, `already_english_supported`.
- `english_menu_state`: `missing`, `weak_partial`, `image_only`, `usable_complete`, `unknown`.
- `menu_complexity_state`: `simple`, `medium`, `large_custom_quote`.
- `izakaya_rules_state`: `none_found`, `drinks_found`, `courses_found`, `nomihodai_found`, `unknown`.

Do not pitch ticket-machine help unless `ticket_machine_state=present` or the message is explicitly phrased as a check, not an assumption.

### 3. Proof Strength

Gold proof:

- Official menu, official PDF, owner site, Google Business photo, Tabelog/Hotpepper page, RamenDB for ramen, Instagram/shop social, or clear Maps photo.
- At least one evidence URL and one screenshot/snippet that an operator can inspect.
- No bracketed fallback translations in customer-visible preview.

Reject proof:

- Scraped boilerplate, calendar/header/footer text, old chain pages, or source snippets unrelated to actual menu/order flow.

### 4. Channel Fit

Rank contact routes by likely owner response, not by automation convenience:

1. Existing direct relationship or reply.
2. Official contact form with business inquiry allowance.
3. Published business email without ad-mail refusal text.
4. LINE or Instagram when clearly used by the shop.
5. Phone/walk-in for very high-value local leads.

Any commercial email must include clear sender identity, contact info, and opt-out handling.

### 5. Offer Fit

Default recommendations:

- Ramen with ticket machine: Package 2 as the strongest "ready-to-use ordering kit"; Package 1 only if they can print themselves.
- Ramen without machine: Package 1 for simple menu, Package 2 when the shop lacks printed material or wants counter-ready cards.
- Izakaya with drinks/courses: Package 3 when menus change often; Package 2 when printed table menus are stable and staff explanation burden is high.
- Large izakaya/menu complexity: custom quote gate before promising a fixed package.

### 6. Outreach Fit

The pitch should answer four questions in the first screen:

- Why this shop?
- What exact ordering friction was found?
- What small sample/proof is attached or linked?
- What is the low-effort next step?

Avoid leading with all three prices in the first cold message. Price should be available on the site and in quote flow, but the cold pitch should sell the diagnosis and next step.

### 7. Operations Fit

No package is launch-ready unless the lead can move through:

lead -> contact -> reply -> quote -> payment pending -> paid -> intake -> production -> owner review -> approval -> delivery/follow-up.

P5 must be plan-reconciled and rehearsed before paid work.

## Ten High-Level Improvements

1. Reposition the product as an English ordering system, not a translation service.
   The headline offer should be "make tourists able to order without slowing staff down." Translation is one component. The real product is menu structure, ticket-machine mapping, QR clarity, owner approval, and usable physical/digital delivery.

2. Build a Lead Evidence Dossier and make it the gate before outreach.
   Each lead needs visible proof for category, independence, tourist exposure, English-menu state, ticket-machine state, contact channel, and package fit. If ticket machine or English-menu status is unknown, the pitch must say "I wanted to check whether..." instead of assuming.

3. Replace generic search with friction-first lead generation.
   Add search jobs around Japanese evidence terms: `券売機 ラーメン [area]`, `食券 ラーメン [station]`, `英語メニュー 居酒屋 [area]`, `飲み放題 コース 居酒屋 [area]`, `menu photo`, `お品書き`, and official/Maps/social photo sources. The goal is not more leads; it is fewer, stronger leads with proven ordering friction.

4. Add hard "already solved" and "chain/franchise" disqualification.
   A shop with a clear English menu, multilingual QR system, or chain infrastructure should not receive a generic pitch. The Tsukada Nojo stale record shows why this matters: high score and high reviews can still be the wrong target.

5. Turn the cold message into a shop-specific diagnosis.
   The first message should be shorter and more concrete: "I noticed your menu/order flow may be hard for overseas guests because X. I prepared a small illustrative English ordering sample. If useful, please send current menu/ticket-machine photos and I will make a review version." This feels like help, not a mass service pitch.

6. Keep the three fixed prices, but rename/package around outcomes.
   Preserve JPY 30,000 / 45,000 / 65,000, but make the buyer understand the outcome:
   - JPY 30,000: English Ordering Files - print-ready menu/guide data.
   - JPY 45,000: Counter-Ready Ordering Kit - printed, laminated, delivered.
   - JPY 65,000: Live QR English Menu - hosted QR menu with update policy.
   Lead with the best matched package, not the full menu of options.

7. Add risk reversal that matters to restaurant owners.
   Include owner approval before delivery, a fixed correction window, clear scope limits, no price/allergen claims without owner confirmation, and a simple "we make it match your current menu/order flow" promise. This makes the fixed prices feel safer.

8. Redesign samples around operational clarity, not just aesthetics.
   Menus should be tested for glanceability: larger English item names, clear Japanese cross-reference, prices only when confirmed, allergy/ingredient claims only when owner-confirmed, and ticket-machine guides that visually match button layout. For ramen, show toppings/sets/noodle choices. For izakaya, show drinks/courses/nomihodai rules.

9. Reconcile and finish P5 before launch.
   The tree already has quote/order/payment/intake work, but `PLAN.md` still says P5 has not started. Make the plan truthful, finish quote/invoice/payment/intake/privacy/revision gates, and rehearse all three packages before any real order.

10. Run controlled launch as a measurement system, not a send batch.
   For the first 5-10 shops, log evidence state, channel, message variant, package recommendation, reply/no reply, objection, and operator time. After each batch, update search scoring, pitch wording, and package recommendation from observed results. Do not scale volume until a repeatable lead profile emerges.

## Product North Star

The product gets great when the operator can open a lead and immediately see:

> This is an independent ramen/izakaya shop in a tourist-exposed area. It has proven Japanese-only ordering friction, no usable English solution, a reachable channel, a matching proof sample, and a clear package recommendation that pays for itself with a small number of smoother foreign-guest orders.

Anything short of that should either be manual review or skipped.
