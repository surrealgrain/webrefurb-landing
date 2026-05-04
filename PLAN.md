# Product Audit Implementation Plan

Source audit: `PRODUCT_AUDIT_2026-04-29.md`

This is the active production-readiness checklist. It replaces older phase plans and prior completion checklists. Treat every partial implementation as untrusted until it passes the relevant checklist and verification gates below.

## Operating Rules

- [ ] Work this checklist top-to-bottom unless a blocker makes the next item impossible.
- [ ] Do not mark a checkbox complete from memory, prior handoff text, or commit history; mark complete only after inspecting the current working tree and state.
- [ ] Do not begin real outreach until every pre-pilot gate in this plan is complete.
- [ ] Do not scale beyond the first controlled batch until the batch review checklist is complete.
- [ ] Treat the current `259` final-checked / `260` ready-for-outreach pool as untrusted until regenerated.
- [ ] Preserve binary lead semantics: `lead: true|false`; never add `maybe`.
- [ ] Approved outreach/contact routes are email and contact forms only; phone, LINE, Instagram, reservations, map URLs, walk-ins, and websites are reference-only.
- [ ] Customer-facing copy must not mention AI, automation, scraping, internal tools, internal source policy, or pipeline mechanics.
- [ ] Public business emails visible online are acceptable unless they are placeholder/guessed-looking or paired with sales/ad/refusal language.
- [ ] Keep backend rigor, but expose only simple operator states in the main UI: `Ready`, `Review`, `Skipped`, `Done`.
- [ ] Keep `HANDOFF.md` compact, target 40 lines or fewer, and replace stale facts instead of appending logs.
- [ ] At each large run checkpoint, complete focused tests, `git diff --check`, and `.venv/bin/python -m pipeline.cli audit-state` when lead state, outreach preview, send behavior, package export, or render/export behavior is touched.
- [ ] Commit only after the checkpoint is internally consistent; stage only relevant files because unrelated dirty files may exist.

## Known Blockers To Clear

- [x] `audit-state` currently fails and must pass before pilot outreach.
- [x] Current ready lane includes stale draft markers and must be regenerated.
- [x] Current ready lane includes entity-quality flags such as article titles, usernames, and media/blog/PR source artifacts.
- [x] Current package distribution collapses nearly everything to Package 1 and must be re-scored.
- [x] Dashboard exposes backend states such as verified, confirmed, send-ready, and accepted source policy; primary UI must be simplified.
- [x] Old and new menu templates do not share one contract.
- [x] Rendering still relies on brittle HTML regex replacement and must become structured-slot based.
- [x] Public site needs stronger proof of actual outputs, not mostly abstract tiles.
- [x] Reply-to-production workflow is not yet clear enough for owner photos, menu extraction, build, approval, export, and print delivery.
- [x] Final downloadable artifacts need strict print, QR, ZIP, checksum, and open-after-download validation.

## Run 1: Baseline, Freeze, Backup, And State Repair

Goal: stop accidental launch, preserve current state, and make the state truth inspectable before changing lead logic.

- [x] Run `git status --short` and identify unrelated dirty files that must not be staged.
- [x] Create a timestamped backup of `state/` under `state/backups/`.
- [x] Add or verify a launch freeze guard that blocks batch sending while production-readiness gates are failing.
- [x] Invalidate current final checks by clearing `send_ready_checked`, `send_ready_checked_at`, and final-check artifacts for records that need regenerated copy or package review.
- [x] Generate a current lead-state report with counts for `lead`, `operator_state` once added, `launch_readiness_status`, `outreach_status`, `review_status`, `verification_status`, `email_verification_status`, category, profile, and package.
- [x] Quarantine suspicious ready records into review, not delete by default:
  - [x] article/list/news/review titles posing as business names;
  - [x] reviewer usernames posing as business names;
  - [x] media/blog/PR/video pages posing as restaurants;
  - [x] placeholder/guessed-looking emails missed by earlier cleanup;
  - [x] out-of-scope categories;
  - [x] chain/franchise/operator records;
  - [x] already-solved English or multilingual ordering records.
- [x] Remove stale saved outreach copy containing obsolete first-contact language:
  - [x] `突然のご連絡`;
  - [x] `添付のサンプル`;
  - [x] `ラミネート加工や店舗へのお届け`;
  - [x] any first-contact attachment claim;
  - [x] any first-contact pricing dump.
- [x] Normalize deterministic drift with repair code, not one-off manual edits.
- [x] Add state-audit findings for stale draft markers, suspicious entity names, placeholder emails, package-collapse defaults, and unsafe current-ready records.
- [x] Run `.venv/bin/python -m pipeline.cli audit-state --repair` only for deterministic fixes.
- [x] Re-run `.venv/bin/python -m pipeline.cli audit-state`.
- [x] Add tests for every repair and quarantine rule.
- [x] Update `HANDOFF.md` with only the new truth, not raw counts from command output unless they matter.

Completion gate:

- [x] No launch-ready record contains stale first-contact copy.
- [x] No launch-ready record has a suspicious entity-quality flag.
- [x] No launch-ready record has a placeholder/guessed-looking email.
- [x] `audit-state` either passes or has only explicitly documented non-launch findings.
- [x] `git diff --check` passes.

## Run 2: Lead Eligibility, Contact Policy, And Operator State

Goal: keep strict backend evidence while making the operator decision model simple and safe.

- [x] Implement computed `operator_state` for every lead:
  - [x] `ready`: real target, supported route, clean copy, package set, no blocker;
  - [x] `review`: one human decision is needed;
  - [x] `skip`: out of scope, DNC, placeholder, chain, already solved, unsafe route, or not a lead;
  - [x] `done`: sent, replied, bounced, converted, unsubscribed, or closed.
- [x] Implement `operator_reason` as one plain-language reason, not a list of internal status names.
- [x] Keep detailed backend fields for audit/debug:
  - [x] `lead_evidence_dossier`;
  - [x] `proof_items`;
  - [x] `launch_readiness_status`;
  - [x] `launch_readiness_reasons`;
  - [x] `verification_status`;
  - [x] `email_verification_status`;
  - [x] `pitch_readiness_status`;
  - [x] `send_ready_checked`;
  - [x] `tailoring_audit`.
- [x] Gate for Japan physical-location evidence.
- [x] Gate for v1 categories only:
  - [x] ramen;
  - [x] izakaya.
- [x] Gate active-business evidence when available.
- [x] Gate independent or likely small operators; chain/franchise-like records become skip or review.
- [x] Disqualify or skip hotel, cafe, sushi, yakiniku, kaiseki, generic bar/lounge-only, non-restaurant pages, and other non-v1 categories.
- [x] Disqualify or skip already-solved shops:
  - [x] usable complete English menu;
  - [x] multilingual QR ordering system;
  - [x] English-supported ticket machine;
  - [x] chain infrastructure that already solves ordering.
- [x] Implement current contact policy:
  - [x] public business email visible online can be used;
  - [x] business owner's personal-domain email can be used if publicly listed for the business;
  - [x] third-party listing email can be used if it is clearly for the restaurant and not a placeholder;
  - [x] explicit sales/ad/refusal text blocks email;
  - [x] scraped private, guessed, generated, placeholder, example, test, or artifact emails are skipped;
  - [x] contact forms must be real contact forms, not reservation, recruiting, commerce/order, newsletter, or login forms.
- [x] Persist source evidence for contact policy decisions without exposing source-policy jargon in the main UI.
- [x] Ensure outreach generation APIs reject non-ready records with clear operator reasons.
- [x] Add tests for ready, review, skip, done, contact policy, entity-quality detection, and disqualification paths.

Completion gate:

- [x] Main lead list can be driven entirely by `operator_state`.
- [x] Raw backend status names are not needed to make ordinary operator decisions.
- [x] Every blocked record has one actionable `operator_reason`.
- [x] Unit and API tests cover all state transitions.

## Run 3: Dashboard Operator System

Goal: replace internal-state dashboard work with a practical operating cockpit.

- [x] Replace `All / Review / Confirmed / Final check` with large work modes:
  - [x] `Review`;
  - [x] `Ready`;
  - [x] `Skipped`;
  - [x] `Done`.
- [x] Remove visible primary wording for:
  - [x] verified;
  - [x] confirmed;
  - [x] send-ready;
  - [x] accepted source policy;
  - [x] launch readiness;
  - [x] pitch readiness.
- [x] Move raw audit fields into an optional debug drawer.
- [x] Lead cards must show only:
  - [x] restaurant name;
  - [x] city;
  - [x] category/profile;
  - [x] contact route;
  - [x] recommended package;
  - [x] one proof line;
  - [x] one review reason if blocked;
  - [x] primary action.
- [x] Review queue must group by human decision:
  - [x] is this a real restaurant;
  - [x] is this ramen/izakaya;
  - [x] is the contact route acceptable;
  - [x] is the package fit correct;
  - [x] is the draft/sample current and safe.
- [x] Ready queue must include only records passing backend gates and current final copy checks.
- [x] Batch send UI must only select `operator_state=ready` email records.
- [x] Contact-form records must remain manual unless a verified form-submit workflow exists.
- [x] Add visible launch-freeze banner when production gates fail.
- [x] Add state summary cards:
  - [x] ready count;
  - [x] review count by reason;
  - [x] skipped count by reason;
  - [x] done count by outcome;
  - [x] stale/blocked gate status.
- [x] Add quick actions:
  - [x] approve as real shop;
  - [x] skip;
  - [x] fix name;
  - [x] fix package;
  - [x] regenerate pitch;
  - [x] open proof;
  - [x] mark DNC.
- [x] Add UI tests that assert internal state labels are absent from primary surfaces.
- [x] Run browser checks on desktop and mobile for the new operator system.

Completion gate:

- [x] Operator can understand the next action without reading backend terms.
- [x] Ready queue cannot include stale, suspicious, or blocked records.
- [x] Batch send cannot bypass the simplified state gate.

## Run 4: Search, Lead Quality, Package Fit, And Pitch Regeneration

Goal: replace volume-first acquisition with high-friction, high-fit candidates and regenerate current outreach copy.

- [x] Replace generic search defaults such as `ramen restaurants Kyoto`.
- [x] Add or verify ramen search jobs:
  - [x] `券売機 ラーメン {area}`;
  - [x] `食券 ラーメン {area}`;
  - [x] `ラーメン メニュー 写真 {area}`;
  - [x] RamenDB area checks;
  - [x] official site/menu/photo checks.
- [x] Add or verify izakaya search jobs:
  - [x] `飲み放題 コース 居酒屋 {area}`;
  - [x] `お品書き 居酒屋 {area}`;
  - [x] `居酒屋 メニュー 写真 {area}`;
  - [x] Hotpepper/Tabelog/official/social checks.
- [x] Store search job, matched friction evidence, and source evidence on each candidate.
- [x] Re-score all leads through the real package recommender, not import defaults.
- [x] Stop defaulting imported public-email leads to Package 1.
- [x] Implement package defaults:
  - [x] ramen with ticket machine: Package 2 by default;
  - [x] ramen with ticket machine and clear print-yourself fit: Package 1;
  - [x] ramen without machine and simple menu: Package 1;
  - [x] ramen without machine but counter-ready need: Package 2;
  - [x] izakaya with drinks/courses/nomihodai and frequent changes: Package 3;
  - [x] izakaya with stable table menus and staff explanation burden: Package 2;
  - [x] large/complex menus: custom quote gate.
- [x] Store package recommendation reason and custom-quote reason.
- [x] Cold outreach must answer:
  - [x] why this shop;
  - [x] what ordering friction was found;
  - [x] what proof/sample is available;
  - [x] what low-effort next step the owner should take.
- [x] First email must use current locked copy rules:
  - [x] `初めてご連絡いたします`;
  - [x] one shop-specific observation;
  - [x] one free one-page sample offer;
  - [x] one-word CTA: `希望`;
  - [x] sender identity;
  - [x] contact info;
  - [x] opt-out line;
  - [x] no attachment claim;
  - [x] no pricing dump;
  - [x] no lamination/delivery upsell;
  - [x] no AI/internal wording.
- [x] Contact-form pitch must be short, no attachment/image dependency, and route the reply to email.
- [x] Add stale-copy audit that fails if old phrases appear in any ready or draft-send record.
- [x] Regenerate pitch drafts only after entity, contact, and package checks pass.
- [x] Add tests for search query generation, friction evidence, package branches, pitch copy, forbidden terms, and stale markers.

Completion gate:

- [x] Ready leads have current generated copy only.
- [x] Package distribution reflects actual shop friction instead of import defaults.
- [x] Cold outreach does not lead with all three prices.
- [x] Every ready lead has a package recommendation reason.

## Run 5: Templates, Rendering, Samples, And Public Site

Goal: make samples and public proof look like the product being sold and render safely across profiles.

- [x] Normalize all templates to one contract:
  - [x] `body data-profile`;
  - [x] editable `data-slot` attributes;
  - [x] A4 print styles where print is promised;
  - [x] mobile styles where web/QR is promised;
  - [x] footer note that samples are illustrative and production uses owner-confirmed content;
  - [x] no fake prices;
  - [x] no fake restaurant claims;
  - [x] no AI/internal wording.
- [x] Bring old templates up to the new contract:
  - [x] ramen food;
  - [x] ramen drinks;
  - [x] izakaya food;
  - [x] izakaya drinks;
  - [x] izakaya combined;
  - [x] ticket-machine guide;
  - [x] QR sign.
- [x] Preserve locked GLM-owned template designs unless a design edit is explicitly part of the task.
- [x] Replace regex HTML replacement with structured slot rendering.
- [x] Add a shared content schema:
  - [x] business/store name;
  - [x] profile;
  - [x] sections;
  - [x] items;
  - [x] item Japanese name;
  - [x] item English label;
  - [x] description;
  - [x] price and price status;
  - [x] rule/note blocks;
  - [x] photos;
  - [x] QR data;
  - [x] ticket-machine mapping.
- [x] Add dynamic layout rules:
  - [x] long names wrap or shrink within safe bounds;
  - [x] dense sections tighten spacing;
  - [x] sparse sections use balanced whitespace;
  - [x] section overflow creates a new page or blocks export;
  - [x] footer never overlaps content;
  - [x] QR code never crops.
- [x] Add render validation:
  - [x] required slots exist;
  - [x] no text overflow;
  - [x] no missing fonts;
  - [x] no fake prices;
  - [x] no forbidden wording;
  - [x] no broken image paths;
  - [x] print CSS exists for print templates.
- [x] Generate and save previews for:
  - [x] simple ramen menu;
  - [x] ramen with ticket machine;
  - [x] izakaya food/drinks;
  - [x] yakitori/kushiyaki;
  - [x] kushiage;
  - [x] seafood/sake/oden;
  - [x] tachinomi;
  - [x] robatayaki;
  - [x] QR sign;
  - [x] QR mobile menu.
- [x] Improve public site positioning:
  - [x] sell English ordering systems, not generic translation;
  - [x] show actual output previews above the fold;
  - [x] show ramen ticket-machine guide;
  - [x] show izakaya food/drink layout;
  - [x] show QR sign and mobile QR menu;
  - [x] explain owner approval and one correction window;
  - [x] explain prices/allergens only after owner confirmation;
  - [x] keep packages clear: JPY 30,000 / JPY 45,000 / JPY 65,000;
  - [x] no AI/internal language.
- [x] Add tests for template contracts, render output, public copy, package labels, prices, no HVAC references, and forbidden customer-facing terms.

Completion gate:

- [x] Every active template can render from structured content.
- [x] Sample outputs are visually credible enough to sell.
- [x] Public site displays actual product proof, not only abstract feature tiles.

## Run 6: Reply Intake, Paid Flow, Photo Intake, And Build Studio

Goal: when an owner replies and sends menu/ticket-machine photos, the operator has a clear production workspace from reply through approval.

- [x] Attach inbound email/form replies to the lead and order.
- [x] Classify reply intent:
  - [x] interested;
  - [x] price question;
  - [x] menu photos sent;
  - [x] ticket-machine photos sent;
  - [x] other question;
  - [x] not interested;
  - [x] unsubscribe.
- [x] Auto-create draft `order_intake` only for positive replies.
- [x] Show exactly one next action:
  - [x] ask for photos;
  - [x] review uploaded photos;
  - [x] answer question;
  - [x] send quote;
  - [x] build sample;
  - [x] close.
- [x] Ensure every package can move through:
  - [x] lead;
  - [x] contact;
  - [x] reply;
  - [x] quote;
  - [x] payment pending;
  - [x] paid;
  - [x] intake;
  - [x] production;
  - [x] owner review;
  - [x] approval;
  - [x] final export;
  - [x] download;
  - [x] delivery/follow-up.
- [x] Build owner asset inbox:
  - [x] store original files unchanged;
  - [x] generate normalized preview images;
  - [x] track source email/reply;
  - [x] detect duplicates;
  - [x] classify asset types.
- [x] Classify owner assets as:
  - [x] food menu photo;
  - [x] drink menu photo;
  - [x] course/nomihodai rules;
  - [x] ticket machine photo;
  - [x] wall menu/signage;
  - [x] shop logo;
  - [x] food/item photo;
  - [x] storefront/reference photo;
  - [x] irrelevant/unclear.
- [x] Detect photo quality issues:
  - [x] blurry;
  - [x] cropped;
  - [x] glare;
  - [x] low resolution;
  - [x] duplicate;
  - [x] missing page edges;
  - [x] text too small;
  - [x] wrong file;
  - [x] unreadable.
- [x] Main operator UI should expose only:
  - [x] usable;
  - [x] needs better photo;
  - [x] not needed.
- [x] OCR/extract Japanese menu text from usable photos and PDFs.
- [x] Group extraction into sections:
  - [x] ramen;
  - [x] toppings;
  - [x] rice/sides;
  - [x] drinks;
  - [x] courses;
  - [x] rules;
  - [x] specials;
  - [x] set menus;
  - [x] notes.
- [x] Extract menu fields:
  - [x] Japanese item name;
  - [x] tentative English label;
  - [x] description;
  - [x] option/rule text;
  - [x] price;
  - [x] price status;
  - [x] owner-confirmation status.
- [x] Flag extraction issues:
  - [x] low-confidence OCR;
  - [x] duplicate items;
  - [x] unclear item boundaries;
  - [x] missing pages;
  - [x] suspected wrong section;
  - [x] price ambiguity.
- [x] Ticket-machine mapping must detect:
  - [x] rows;
  - [x] columns;
  - [x] groups;
  - [x] colors;
  - [x] button labels;
  - [x] linked menu item;
  - [x] unmapped buttons;
  - [x] duplicate labels.
- [x] Provide visual ticket-machine mapping UI, not raw JSON.
- [x] Recheck package fit after real assets arrive:
  - [x] ticket-machine assets usually move to Package 2;
  - [x] multiple drink/course/rule assets usually move to Package 3 or custom quote;
  - [x] simple one-page menus stay Package 1;
  - [x] huge or unclear menus become custom quote;
  - [x] operator package override requires a reason.
- [x] Build a production workspace:
  - [x] left rail: source assets, extracted content, unresolved questions;
  - [x] center: live rendered preview;
  - [x] right rail: structured controls;
  - [x] controls for profile, template, section order, item density, photo usage, price visibility, QR/print/ticket outputs, and notes.
- [x] Avoid freeform design editing in first implementation; use structured controls to preserve consistency.
- [x] Add pre-owner-preview QA:
  - [x] all source photos reviewed;
  - [x] low-quality photos resolved or explicitly excluded;
  - [x] Japanese item names checked;
  - [x] English labels reviewed;
  - [x] prices hidden or owner-confirmed;
  - [x] allergens/ingredients hidden or owner-confirmed;
  - [x] ticket-machine buttons mapped or explicitly unresolved;
  - [x] PDF/mobile previews rendered;
  - [x] visual overflow checks passed;
  - [x] forbidden customer-facing language scan passed.
- [x] Add owner approval loop:
  - [x] preview link or PDF sent;
  - [x] approval stored;
  - [x] rejection stored;
  - [x] correction requests stored;
  - [x] corrections converted into structured tasks;
  - [x] included correction window tracked;
  - [x] final export blocked until owner approval.
- [x] Correction tasks must support:
  - [x] rename item;
  - [x] fix price;
  - [x] remove item;
  - [x] add item;
  - [x] change photo;
  - [x] correct rule;
  - [x] change section;
  - [x] approve as-is.
- [x] Add integration tests for reply intake, asset inbox, extraction review, ticket-machine mapping, package recheck, build studio, and owner approval.

Completion gate:

- [x] A positive reply creates a clear workflow with one next action.
- [x] Menu and ticket-machine photos become classified, quality-checked production inputs.
- [x] Operator can build outputs in template style through structured controls.
- [x] Owner preview cannot be sent until production QA passes.

## Run 7: Final Export, Download, Print, QR, And Delivery QA

Goal: ensure every final artifact is downloadable, correct, high-resolution, print-ready, and reproducible.

- [x] Generate package ZIP with:
  - [x] manifest;
  - [x] checksums;
  - [x] package key;
  - [x] restaurant name;
  - [x] approval timestamp;
  - [x] artifact list;
  - [x] source input references;
  - [x] export version.
- [x] Package 1 export must include:
  - [x] print-ready PDF files;
  - [x] high-resolution PNG/JPEG exports when promised;
  - [x] owner-approved content manifest;
  - [x] print-yourself note.
- [x] Package 2 export must include:
  - [x] print-ready PDF files;
  - [x] print profile;
  - [x] copy count;
  - [x] lamination checklist;
  - [x] delivery address confirmation;
  - [x] courier handoff notes.
- [x] Package 3 export must include:
  - [x] hosted QR menu URL;
  - [x] QR sign PDF;
  - [x] QR image;
  - [x] support/hosting record;
  - [x] downloadable backup files;
  - [x] QR link health check.
- [x] Every download endpoint must require approved final export status.
- [x] Every exported artifact must be reproducible from saved order inputs.
- [x] PDF validation must check:
  - [x] page size matches print profile;
  - [x] A4 default is 210 x 297 mm;
  - [x] orientation is explicit;
  - [x] margin is explicit;
  - [x] bleed/no-bleed mode is explicit;
  - [x] safe area is explicit;
  - [x] browser headers/footers are absent;
  - [x] fonts are embedded or converted safely;
  - [x] file opens after export.
- [x] Raster validation must check:
  - [x] 300 DPI target for print assets;
  - [x] minimum pixel dimensions for physical size;
  - [x] no excessive upscaling;
  - [x] no blur introduced by export;
  - [x] transparent/white background matches intended output.
- [x] QR validation must check:
  - [x] minimum physical size;
  - [x] quiet zone;
  - [x] scan success;
  - [x] correct URL;
  - [x] HTTPS;
  - [x] mobile page loads;
  - [x] no cropped code;
  - [x] printed sign text remains readable.
- [x] Visual validation must check:
  - [x] no text overflow;
  - [x] no item overlap;
  - [x] no footer overlap;
  - [x] no clipped images;
  - [x] no missing photo;
  - [x] no broken logo;
  - [x] no forbidden wording;
  - [x] dark-template contrast is readable.
- [x] ZIP validation must check:
  - [x] correct file names;
  - [x] manifest paths match files;
  - [x] checksum verification passes;
  - [x] no hidden system junk files;
  - [x] file opens after download;
  - [x] package contents match package promise.
- [x] Delivery workflow must check:
  - [x] customer download link generated;
  - [x] final customer email/body generated;
  - [x] Package 2 print handoff record created;
  - [x] Package 2 delivery tracking field exists;
  - [x] Package 3 hosting/support record exists;
  - [x] delivered status cannot be set before export QA passes.
- [x] Save export QA reports under `state/export-qa/`.
- [x] Add tests for final export, download permission, artifact contents, print validation, QR validation, ZIP validation, and delivery status gates.

Completion gate:

- [x] Final exports cannot ship without owner approval.
- [x] Downloaded ZIPs include correct artifacts, manifest, and checksums.
- [x] Print assets pass size, resolution, overflow, font, QR, and open-after-download checks.
- [x] Delivered status is impossible before export QA passes.

## Run 8: Browser, Render, Production Simulation, And Pilot Launch

Goal: verify the whole system visually and operationally before any real outreach, then run a tiny measured launch.

- [x] Start the local dashboard/site as needed.
- [x] Capture desktop and mobile screenshots for:
  - [x] dashboard operator queue;
  - [x] review lane;
  - [x] ready lane;
  - [x] skipped lane;
  - [x] done lane;
  - [x] lead evidence/debug drawer;
  - [x] outreach modal;
  - [x] reply-intake lane;
  - [x] owner asset inbox;
  - [x] extraction review workspace;
  - [x] ticket-machine mapping workspace;
  - [x] build studio;
  - [x] owner preview;
  - [x] homepage;
  - [x] pricing pages;
  - [x] sample ramen preview;
  - [x] sample izakaya preview;
  - [x] QR menu;
  - [x] QR sign.
- [x] Browser screens must have no:
  - [x] unreadable text;
  - [x] overlapping UI;
  - [x] missing proof;
  - [x] stale placeholders;
  - [x] bracketed fallback text;
  - [x] forbidden customer-facing language;
  - [x] broken actions; fixed 2026-05-04: frozen launch-batch API now returns controlled `423 launch_frozen:*`.
  - [x] inaccessible primary controls; fixed 2026-05-04: audited public CTA/theme controls and dashboard delete/asset-review controls now render at least 44px.
- [x] Render and download final sample exports for Package 1, Package 2, and Package 3.
- [x] Validate downloaded artifacts:
  - [x] correct file names;
  - [x] correct manifest;
  - [x] PDF page size and orientation;
  - [x] 300 DPI target for print raster exports;
  - [x] no text overflow;
  - [x] no cropped QR code;
  - [x] QR quiet zone;
  - [x] embedded/usable fonts;
  - [x] readable mobile QR menu;
  - [x] open-after-download success.
- [x] Save screenshots under `state/qa-screenshots/`.
- [x] Save export QA reports under `state/export-qa/`.
- [x] Run a no-send real-world smoke test before external contact:
  - [x] use real public shop evidence;
  - [x] use the same readiness gates as a real batch;
  - [x] create rehearsal records outside real launch batches;
  - [x] do not mark any lead contacted;
  - [x] do not let rehearsal records satisfy or block real Batch 1.
- [x] Run authorized real-world test-email smoke to `chris@webrefurb.com` only:
  - [x] exactly 5 fixture/recipient-overridden emails sent with `[WEBREFURB TEST]` subjects;
  - [x] ramen menu, ramen ticket-machine, izakaya food/drinks, izakaya nomihodai/course, and machine-only/ordering-guide variants covered;
  - [x] no restaurant recipient, contact form, launch batch, sent-record mutation, or lead outreach-state mutation.
- [ ] Select 5-10 pilot shops only after gates pass. Blocked 2026-05-04: `ready_for_outreach_count_below_5`.
- [ ] Pilot must include:
  - [ ] at least one ramen ticket-machine lead; blocked 2026-05-04: `missing_ramen_ticket_machine_candidate`.
  - [ ] at least one izakaya drink/course/nomihodai lead; blocked 2026-05-04: `missing_izakaya_drink_or_course_candidate`.
- [ ] Manually inspect each selected lead:
  - [ ] restaurant fit;
  - [ ] ordering friction;
  - [ ] proof strength;
  - [ ] contact route;
  - [ ] offer/package fit;
  - [ ] outreach copy;
  - [ ] sample/proof asset;
  - [ ] final operator state.
  - Blocked 2026-05-04: no 5-10 lead pilot set exists.
- [ ] Create launch batch record under `state/launch_batches/`. Blocked 2026-05-04: controlled launch selection not allowed.
- [ ] Send only the selected batch through approved channels after explicit current-chat approval to send. Blocked 2026-05-04: no selected batch and no send approval; no real outreach performed.
- [ ] Record for each contacted lead:
  - [ ] dossier states;
  - [ ] selected channel;
  - [ ] message variant;
  - [ ] proof asset;
  - [ ] recommended package;
  - [ ] contacted timestamp;
  - [ ] reply/no reply;
  - [ ] objection;
  - [ ] opt-out/bounce;
  - [ ] operator minutes;
  - [ ] outcome.
  - Blocked 2026-05-04: zero contacted leads in this no-send run.

Completion gate:

- [x] Screenshots cover actual owner/operator screens.
- [x] Final exported ZIPs and PDFs are downloaded, opened, and validated.
- [x] No known visual, content, export, or print-readiness defect remains untracked.
- [ ] Batch 1 contains 5-10 reviewed leads. Blocked 2026-05-04: zero ready-for-outreach leads.
- [ ] Every contacted lead has a measurement record. Blocked 2026-05-04: no real outreach/contact occurred.

## Run 9: Batch Review, Iteration, And Repeatable Scale Loop

Goal: scale only if the first measured batch proves the lead profile and offer are working.

- [ ] Review every Batch 1 outcome.
- [ ] Summarize:
  - [ ] response rate;
  - [ ] positive replies;
  - [ ] objections;
  - [ ] opt-outs/bounces;
  - [ ] channel performance;
  - [ ] operator time;
  - [ ] package fit;
  - [ ] proof asset performance;
  - [ ] actual fulfillment questions from owners.
- [ ] Update scoring from observed outcomes.
- [ ] Update search terms from observed lead quality.
- [ ] Update outreach wording from replies and objections.
- [ ] Update package recommendation if package fit was wrong.
- [ ] Update reply-intake workflow if owners send unexpected assets or questions.
- [ ] Update template/build flow if production takes too long or outputs need too much manual repair.
- [ ] Record the review in the batch record.
- [ ] Do not create Batch 2 until Batch 1 review exists.
- [ ] Select Batch 2 using updated scoring, search, outreach, and package rules.
- [ ] Repeat the same measurement and review loop for every later batch.
- [ ] Continue only while lead quality, owner response, fulfillment time, and package economics justify volume.

Completion gate:

- [ ] Batch 1 review is recorded before Batch 2.
- [ ] Search, scoring, outreach, package, or production changes are made when evidence supports them.
- [ ] Scaling is based on observed lead profile and production capacity, not volume pressure.

## Global Production-Ready Verification

Run these before any commit that claims a large run is complete:

```bash
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m pipeline.cli audit-state
git diff --check
git status --short
```

Additional required checks before pilot:

- [x] `0` ready records contain stale draft markers.
- [x] `0` ready records contain suspicious entity-quality flags.
- [x] `0` ready records contain placeholder/guessed-looking emails.
- [x] `0` ready records lack current generated pitch copy.
- [x] `0` ready records lack package recommendation reason.
- [x] `0` primary UI surfaces expose internal status jargon.
- [x] `0` customer-facing surfaces mention forbidden internal wording.
- [x] All active templates pass template contract validation.
- [x] All package exports pass export QA.
- [x] Browser screenshots exist for all production-critical screens.
- [x] `HANDOFF.md` is updated compactly and remains under roughly 40 lines.
