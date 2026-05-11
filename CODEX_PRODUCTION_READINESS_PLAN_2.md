# WebRefurbMenu — Production Readiness Plan 2

**Purpose:** This is the next large checklist after `CODEX_FULL_AUDIT_PLAN.md`. The prior audit cleaned drift and restored the active QR-menu product. This plan is about making the product reliable, sellable, operable, and low-risk enough to run repeatedly for real restaurants.

**Active product constraint:** Japan only. Active categories are `ramen`, `izakaya`, and `skip`. One active product: `english_qr_menu_65k` / English QR Menu + Show Staff List / 65,000 yen. Customer-facing copy must stay QR-first and must not describe the product as an ordering system, POS, checkout, payment, or order-submission flow.

**How to use this plan:**
- Work phase by phase.
- Keep every completed change covered by tests or an explicit verification command.
- Do not resurrect old package IDs, old print/design-first package logic, old samples, or stale lead-specific drafts.
- If a task touches customer-facing copy, run the banned-term checks before considering it done.
- If a task touches sending, keep test sends limited to `chris@webrefurb.com`; real sends require explicit manual approval.

**Implementation pass started:** 2026-05-11. This pass keeps the interactive demo's coral/white look locked and focuses on production workflow, safety gates, tests, release checks, and operating docs. Manual-only items remain manual: native phone testing, native Japanese review, DNS changes, and real pilot outreach.

---

## PHASE 0: Baseline, Ownership, And Release Hygiene

### Step 0.1: Establish a clean release branch
- [ ] Create a new branch with the `codex/` prefix.
- [ ] Confirm `git status --short` only contains intentional files.
- [ ] Decide whether `CODEX_FULL_AUDIT_PLAN.md` should remain untracked, be committed as internal planning, or be ignored.
- [ ] Decide whether this file should be committed as the active production-readiness plan.

### Step 0.2: Record the current production baseline
- [ ] Run `.venv/bin/python -m pytest tests/ -q`.
- [ ] Run `.venv/bin/python -m pipeline.cli audit-state`.
- [ ] Check all 7 live public URLs return `200`.
- [ ] Verify `webrefurb.com` and `www.webrefurb.com` behavior is intentional.
- [ ] Record the current live deployment branch/source in a short internal note.

### Step 0.3: Define production-ready for this project
- [ ] Write a short "Production Ready Means" section in `HANDOFF.codex.md` or a new internal doc.
- [ ] Include: live site health, demo usability, send safety, trial workflow, owner confirmation, data retention, recovery, and test suite expectations.
- [ ] Keep it under 40 lines if updating `HANDOFF.codex.md`.

### Step 0.4: Lock down the public source of truth
- [ ] Decide whether the canonical public site source is root files or `docs/`.
- [ ] If GitHub Pages must keep serving root, keep root and `docs/` mirrored with a test.
- [ ] If GitHub Pages can be moved to `docs/`, remove root duplication after live verification.
- [ ] Document the chosen setup in `docs/TRIAL_WORKFLOW.md` or a new deployment note.

### Step 0.5: Add a release checklist
- [ ] Create `docs/RELEASE_CHECKLIST.md` or `RELEASE_CHECKLIST.md`.
- [ ] Include tests, state audit, link check, live URL check, banned-term scan, and send-safety spot check.
- [ ] Include rollback instructions for a bad public-site deployment.

---

## PHASE 1: Customer Journey And Conversion Quality

### Step 1.1: Map the real owner journey
- [ ] Write the intended owner journey from cold email to paid setup.
- [ ] Include first contact, demo view, reply, trial setup, owner confirmation, trial week, keep-or-decline decision, invoice, and post-launch support.
- [ ] Identify which steps are currently manual, semi-automated, or unsupported.

### Step 1.2: Improve the homepage conversion path
- [ ] Verify the homepage answers "what is this?" within the first viewport.
- [ ] Verify the homepage answers "does it disrupt my staff?" before the first CTA.
- [ ] Verify the homepage explains the staff handoff without using order-system language.
- [ ] Add or refine one trust-oriented proof point that is true today.
- [ ] Avoid fake testimonials, fake client logos, or unverifiable claims.

### Step 1.3: Improve the pricing page decision path
- [ ] Confirm price appears once in the main offer and is tax-clear.
- [ ] Confirm the free trial has no-obligation wording.
- [ ] Add a simple "What happens after the trial?" section if not already clear enough.
- [ ] Add a simple "What you need to send us" section for after the owner replies.
- [ ] Keep first contact reply-only; do not ask for menu photos in cold outreach.

### Step 1.4: Make the generic demo hub more useful
- [ ] Check whether the demo hub should show only active target categories or keep sushi as a generic food-service demo.
- [ ] If sushi remains, clearly treat it as a demo, not an active lead category.
- [ ] Add a short "scan on your phone" affordance without adding instructional clutter.
- [ ] Confirm links from outreach go to the best demo entry point.

### Step 1.5: Validate Japanese copy with owner mindset
- [ ] Review Japanese homepage and pricing copy for natural business tone.
- [ ] Remove any phrase that sounds like software replacement, staff workflow replacement, or customer ordering.
- [ ] Verify "free trial" language does not create implied obligation.
- [ ] Verify tax wording feels normal for Japanese B2B.
- [ ] Verify the CTA asks for a reply, not a complex form submission.

### Step 1.6: Add conversion instrumentation without tracking excess data
- [ ] Decide whether any lightweight analytics are acceptable.
- [ ] If yes, document what is collected and why.
- [ ] Avoid collecting restaurant-owner personal data without a clear need.
- [ ] Add privacy copy only if instrumentation is added.

---

## PHASE 2: Mobile Demo And In-Restaurant Usability

### Step 2.1: Test demo as an actual guest
- [ ] Open ramen demo on iPhone Safari.
- [ ] Open ramen demo on Android Chrome.
- [ ] Add 3 items, change quantity, remove 1 item, open Show Staff List.
- [ ] Toggle English/Japanese and confirm the list remains accurate.
- [ ] Confirm all touch targets are comfortable with one hand.

### Step 2.2: Test demo as a restaurant staff handoff
- [ ] Confirm Japanese item names are first or immediately visible in staff view.
- [ ] Confirm quantities are impossible to miss.
- [ ] Confirm options/toppings are shown in Japanese where needed.
- [ ] Confirm the staff view cannot be confused with a submitted order.
- [ ] Confirm no payment, table, checkout, or send action appears.

### Step 2.3: Handle empty and edge states
- [ ] Empty list state should be clear and calm.
- [ ] Quantity cannot go below 1.
- [ ] Add buttons should show feedback without shifting layout.
- [ ] Long item names should not overflow on 320-375px screens.
- [ ] Staff list should handle 8-12 items without breaking.

### Step 2.4: Improve demo asset performance
- [ ] Audit food image sizes in `docs/demo/_demo_images/`.
- [ ] Convert oversized PNG/JPG assets to WebP if quality remains acceptable.
- [ ] Add width/height attributes or CSS aspect-ratio guards for images.
- [ ] Add `loading="lazy"` for below-fold demo images.
- [ ] Verify root mirror assets stay in sync if root remains the Pages source.

### Step 2.5: Make the demo resilient without JavaScript
- [ ] Confirm page content still communicates the menu concept if JS fails.
- [ ] Add a noscript fallback only if current experience is blank or misleading.
- [ ] Ensure the fallback still avoids banned customer-facing terms.

### Step 2.6: Add browser-based demo tests
- [ ] Add Playwright tests for add-to-list flow.
- [ ] Add Playwright tests for language toggle.
- [ ] Add Playwright tests for staff overlay open/close.
- [ ] Run tests against both `docs/demo/ramen.html` and `docs/demo/sushi.html`.
- [ ] Run at mobile and desktop viewport sizes.

---

## PHASE 3: Trial Workflow And Fulfillment

### Step 3.1: Define trial states
- [ ] Add or document trial states: requested, accepted, intake-needed, build-started, owner-review, live-trial, trial-ending, converted, declined, archived.
- [ ] Decide whether trial state belongs in existing lead records or a separate trial record.
- [ ] Ensure declined trials do not remain publicly discoverable unless approved.

### Step 3.2: Create a trial intake checklist
- [ ] Define what information is needed only after the owner replies.
- [ ] Include restaurant name, menu source, owner-confirmed price policy, allergy policy, contact email, and desired public name.
- [ ] Avoid asking for anything not needed for a trial.
- [ ] Include a privacy note for received menu information.

### Step 3.3: Document the trial build process
- [ ] Create a step-by-step internal workflow from owner reply to live trial URL.
- [ ] Include menu extraction, translation, owner confirmation, QR sign generation, and live-page check.
- [ ] Include who prints the QR sign.
- [ ] Include what to do if the owner has no printer.

### Step 3.4: Add trial end handling
- [ ] Define what happens on day 5, day 7, and day 10.
- [ ] Draft a follow-up email for "keep it".
- [ ] Draft a follow-up email for "not a fit".
- [ ] Ensure no follow-up implies obligation or pressure.

### Step 3.5: Add trial archive/takedown rules
- [ ] Decide when a trial page is removed after decline.
- [ ] Decide whether a paid customer's page stays indefinitely.
- [ ] Add a CLI or dashboard action for archive/takedown.
- [ ] Add tests proving archived trials are not included in public indexes.

### Step 3.6: Add trial metrics
- [ ] Track number of trial requests.
- [ ] Track number of accepted trials.
- [ ] Track trial-to-paid conversion.
- [ ] Track reasons for decline.
- [ ] Keep metrics internal and privacy-light.

---

## PHASE 4: Menu Data Model And Owner Confirmation

### Step 4.1: Audit menu JSON schema
- [ ] Identify the canonical menu data format used by `pipeline/qr.py` and templates.
- [ ] Document required fields for item name, Japanese name, English name, price, category, options, allergens, and owner confirmation.
- [ ] Add a schema file if one does not exist.

### Step 4.2: Add owner-confirmation flags
- [ ] Add explicit fields for price confirmed, description confirmed, ingredient confirmed, allergy confirmed.
- [ ] Block public publish if required confirmation fields are false.
- [ ] Add tests for publish blocking.
- [ ] Ensure previews can still be generated before confirmation with a clear internal status.

### Step 4.3: Improve translation review
- [ ] Identify where English translations are generated or edited.
- [ ] Add a review status per translated item.
- [ ] Add a simple way to mark an item as "owner approved".
- [ ] Add tests that unreviewed translations do not publish as final.

### Step 4.4: Handle price display safely
- [ ] Support tax-included and tax-excluded price notes per restaurant.
- [ ] Support market-price or ask-staff items without inventing a price.
- [ ] Support no-price menus if the owner confirms that is their normal menu.
- [ ] Add tests for all three cases.

### Step 4.5: Handle allergens conservatively
- [ ] Do not infer allergy notes as final facts.
- [ ] Add "owner confirmation required" logic for allergy display.
- [ ] Decide whether to omit allergens entirely until confirmed.
- [ ] Add a visible internal warning for missing allergy confirmation.

### Step 4.6: Handle options and toppings
- [ ] Support ramen toppings, noodle firmness, spice level, size, drink size, and set options.
- [ ] Support izakaya shared plates and drink categories.
- [ ] Ensure options appear clearly in Show Staff List.
- [ ] Add tests for option rendering in customer and staff views.

---

## PHASE 5: QR Page Generation And Publish Lifecycle

### Step 5.1: Define page environments
- [ ] Separate draft, owner-review, trial-live, paid-live, archived, and deleted page states.
- [ ] Ensure internal drafts are not linked from sitemap.
- [ ] Ensure archived pages are not linked from public pages.
- [ ] Decide whether archived pages return 404, 410, or a private archived notice.

### Step 5.2: Add deterministic URL strategy
- [ ] Decide final URL pattern for trial pages.
- [ ] Avoid exposing lead IDs, private names, or raw scraped identifiers in URLs.
- [ ] Ensure URLs are stable after owner approval.
- [ ] Add collision tests.

### Step 5.3: Improve QR code and sign generation
- [ ] Verify generated QR codes resolve to the final public URL.
- [ ] Verify QR sign includes enough restaurant-specific context after owner approval.
- [ ] Add print-size checks for A4.
- [ ] Add tests for QR SVG existence, target URL, and sign readability.

### Step 5.4: Add rollback support
- [ ] Keep previous published versions.
- [ ] Add a way to restore the prior version.
- [ ] Add tests that rollback changes the live version pointer.
- [ ] Document rollback steps in the release checklist.

### Step 5.5: Add publish audit log
- [ ] Record who published, when, source version, and confirmation status.
- [ ] Record archive/takedown events.
- [ ] Avoid logging sensitive raw menu data unless necessary.
- [ ] Add tests for audit log writes.

### Step 5.6: Keep generated files organized
- [ ] Decide where generated menu pages live.
- [ ] Decide which generated artifacts are committed and which are ignored.
- [ ] Add `.gitignore` rules for temporary render outputs.
- [ ] Add a cleanup command for stale local artifacts.

---

## PHASE 6: Lead Pipeline Quality And Qualification

### Step 6.1: Revalidate lead categories
- [ ] Confirm `ramen`, `izakaya`, and `skip` are the only active categories in code.
- [ ] Confirm sushi, yakiniku, yakitori, tonkatsu, cafes, bars, chains, and unrelated categories normalize correctly.
- [ ] Add tests for borderline categories.

### Step 6.2: Improve lead deduplication
- [ ] Identify current duplicate-key logic.
- [ ] Normalize Japanese business names, English names, whitespace, branch markers, and common suffixes.
- [ ] Deduplicate by domain/email/contact URL where available.
- [ ] Add tests for duplicate restaurant variants.

### Step 6.3: Strengthen chain filtering
- [ ] Audit chain-name lists and franchise patterns.
- [ ] Add tests for large chain names in Japanese and English.
- [ ] Add an escape hatch for independent-looking branches that require manual review.

### Step 6.4: Improve QR-menu detection
- [ ] Audit `pipeline/qr_menu_detection.py`.
- [ ] Detect existing digital menus without disqualifying every restaurant with a simple website menu.
- [ ] Add tests for "already has multilingual QR menu" vs "has PDF menu" vs "has normal website menu".
- [ ] Ensure output is manual-review friendly.

### Step 6.5: Improve contact route classification
- [ ] Confirm only email and contact forms are approved outreach routes.
- [ ] Classify phone, LINE, Instagram, reservation platforms, map links, and social DMs as reference-only.
- [ ] Add tests for each route type.
- [ ] Add dashboard labels that make route status unambiguous.

### Step 6.6: Add lead freshness checks
- [ ] Mark stale leads if source data is older than a chosen threshold.
- [ ] Require re-verification before sending to stale leads.
- [ ] Add audit-state failures for stale send-ready records.

### Step 6.7: Add lead quality score explanations
- [ ] Make scoring reasons human-readable.
- [ ] Separate positive signals, negative signals, and missing data.
- [ ] Keep scores internal and never include them in customer-facing copy.

---

## PHASE 7: Outreach, Compliance, And Deliverability

### Step 7.1: Audit first-contact templates
- [ ] Verify first contact links only to the generic demo.
- [ ] Verify first contact asks for a reply only.
- [ ] Verify it does not mention price, menu photos, custom sample, or generated-from-their-menu claims.
- [ ] Verify Japanese and English templates match policy.

### Step 7.2: Add legal sender details
- [ ] Confirm sender identity requirements for Japanese cold commercial email.
- [ ] Add a compliant sender address or acceptable location detail if needed.
- [ ] Keep copy short and natural.
- [ ] Add tests for required footer fields.

### Step 7.3: Improve opt-out handling
- [ ] Standardize opt-out phrasing in Japanese and English.
- [ ] Add a durable do-not-contact flag.
- [ ] Ensure do-not-contact blocks future sends even if a lead is otherwise qualified.
- [ ] Add tests for opt-out state transitions.

### Step 7.4: Add send batching limits
- [ ] Add daily test-send and real-send limits.
- [ ] Add cooldown windows by domain and business.
- [ ] Add manual approval gates for every real-send batch.
- [ ] Add tests that batch send cannot bypass individual readiness.

### Step 7.5: Add deliverability safety
- [ ] Verify SPF, DKIM, and DMARC status for the sending domain.
- [ ] Document DNS records in an internal note.
- [ ] Add bounce handling if provider supports it.
- [ ] Add suppression for bounced addresses.

### Step 7.6: Add contact-form workflow
- [ ] Define what gets pasted into contact forms.
- [ ] Ensure contact-form copy follows the same first-contact rules.
- [ ] Add dashboard support for marking contact-form submitted.
- [ ] Add tests that contact-form routes never use email-only fields incorrectly.

### Step 7.7: Add reply handling workflow
- [ ] Define how replies are logged.
- [ ] Add statuses for interested, not interested, asked question, requested trial, and wrong contact.
- [ ] Add response templates for common questions.
- [ ] Keep real replies manual unless explicitly approved.

---

## PHASE 8: Operator Dashboard And Internal Workflow

### Step 8.1: Audit dashboard routes
- [ ] List every Flask route in `dashboard/app.py`.
- [ ] Identify which routes are production-critical.
- [ ] Add route-level tests for critical APIs.
- [ ] Remove or hide routes that belong to retired workflows.

### Step 8.2: Improve dashboard state visibility
- [ ] Show lead status, send readiness, trial status, owner confirmation, and publish status separately.
- [ ] Avoid one overloaded status field.
- [ ] Add clear blockers and next actions.
- [ ] Add tests for status serialization.

### Step 8.3: Add safe action buttons
- [ ] Disable send buttons until readiness is true.
- [ ] Disable publish buttons until owner confirmation is complete.
- [ ] Add confirmation modals for real send, publish, archive, and delete.
- [ ] Add tests for disabled-state logic.

### Step 8.4: Add operator feedback states
- [ ] Add loading state for long-running actions.
- [ ] Add success state for send/test-send/publish/archive.
- [ ] Add error state with actionable next step.
- [ ] Add empty state for no leads/no trials.

### Step 8.5: Add dashboard accessibility pass
- [ ] Verify keyboard navigation.
- [ ] Verify focus states.
- [ ] Verify labels on controls.
- [ ] Verify contrast.
- [ ] Add basic accessibility tests where practical.

### Step 8.6: Improve internal audit logs
- [ ] Log state changes with actor/action/timestamp.
- [ ] Log failed sends without marking sent.
- [ ] Log blocked sends with blocker reason.
- [ ] Keep logs concise and avoid private payload dumps.

---

## PHASE 9: Infrastructure, Deployment, And Recovery

### Step 9.1: Make local setup reproducible
- [ ] Verify `.venv` setup is documented.
- [ ] Verify `pyproject.toml` includes every imported runtime dependency.
- [ ] Add a single bootstrap command or documented setup sequence.
- [ ] Test setup from a clean checkout if practical.

### Step 9.2: Docker and compose audit
- [ ] Build the Dockerfile.
- [ ] Run the dashboard container locally.
- [ ] Verify environment variables are documented.
- [ ] Remove stale Docker instructions if the container is not maintained.

### Step 9.3: Add deployment health checks
- [ ] Add a script that checks all public URLs.
- [ ] Check status code, title, lang, canonical, OG tags, and banned terms.
- [ ] Check that demo image paths return `200`.
- [ ] Include this script in the release checklist.

### Step 9.4: Add backup and restore plan
- [ ] Identify all state files and generated data that matter.
- [ ] Add backup command documentation.
- [ ] Add restore command documentation.
- [ ] Run a restore rehearsal with test data.

### Step 9.5: Add failure-mode runbooks
- [ ] What to do if live site is broken.
- [ ] What to do if a wrong menu is published.
- [ ] What to do if an email is sent to the wrong recipient.
- [ ] What to do if owner asks for takedown.
- [ ] What to do if the email provider fails.

### Step 9.6: Add version and environment visibility
- [ ] Show current git commit in dashboard footer or diagnostics endpoint.
- [ ] Show environment mode: local/test/production.
- [ ] Ensure production mode cannot send test-only payloads to real recipients by accident.

---

## PHASE 10: Privacy, Security, And Data Retention

### Step 10.1: Inventory stored data
- [ ] List what data is stored for leads.
- [ ] List what data is stored for trial customers.
- [ ] List what data is stored for paid customers.
- [ ] Classify each field as public, internal, sensitive, or delete-after-use.

### Step 10.2: Add data retention rules
- [ ] Decide how long to keep rejected leads.
- [ ] Decide how long to keep declined trial data.
- [ ] Decide how long to keep raw menu photos or source files.
- [ ] Add cleanup tooling or manual procedure.

### Step 10.3: Protect secrets
- [ ] Search for API keys, provider tokens, SMTP credentials, and private URLs.
- [ ] Move secrets to environment variables if needed.
- [ ] Add `.env` patterns to `.gitignore`.
- [ ] Add a secret-scan command to release checklist.

### Step 10.4: Harden dashboard access
- [ ] Confirm dashboard is not accidentally public.
- [ ] Add authentication if dashboard can be exposed beyond localhost.
- [ ] Add CSRF protection for state-changing form routes if browser-accessible.
- [ ] Add tests for unauthorized access where relevant.

### Step 10.5: Privacy copy and owner trust
- [ ] Add a short privacy note to trial workflow pages if customer data is requested.
- [ ] Make clear restaurant menu information is used only for QR menu creation and operation.
- [ ] Avoid broad claims that are not backed by code/process.

### Step 10.6: File permission and generated artifact audit
- [ ] Ensure generated public files do not contain internal notes.
- [ ] Ensure generated QR pages do not include source URLs or lead metadata.
- [ ] Add tests scanning generated public HTML for internal terms.

---

## PHASE 11: Test Strategy And Quality Gates

### Step 11.1: Expand unit coverage where business risk is highest
- [ ] Add direct tests for `pipeline/qualification.py`.
- [ ] Add direct tests for `pipeline/evidence_classifier.py`.
- [ ] Add direct tests for `pipeline/production_workflow.py`.
- [ ] Add direct tests for `pipeline/contact_policy.py`.
- [ ] Add direct tests for `pipeline/qr_menu_detection.py`.

### Step 11.2: Add integration tests for core flows
- [ ] Lead record -> qualification -> manual review.
- [ ] Lead record -> test send -> no real sent status.
- [ ] Trial intake -> QR menu draft -> owner-review state.
- [ ] Owner-confirmed menu -> publish artifact.
- [ ] Archived trial -> no public index entry.

### Step 11.3: Add public-site regression tests
- [ ] Root and `docs/` mirror stays identical where required.
- [ ] All public pages avoid banned customer-facing terms.
- [ ] All public pages have canonical, title, description, OG tags.
- [ ] All local links resolve.
- [ ] All images referenced from public HTML exist.

### Step 11.4: Add browser visual checks
- [ ] Use Playwright to screenshot all public pages at 375, 414, 768, 1024, and 1440 widths.
- [ ] Check pages are not blank.
- [ ] Check no horizontal overflow.
- [ ] Check key CTAs are visible.
- [ ] Check staff overlay is usable on mobile.

### Step 11.5: Add accessibility checks
- [ ] Run automated accessibility checks on public pages.
- [ ] Run keyboard-only checks on demo and dashboard.
- [ ] Verify `lang` attributes change correctly on demo language toggle.
- [ ] Verify buttons and links have accessible names.

### Step 11.6: Add release-blocking checks
- [ ] Make a single command that runs tests, audit-state, banned-term scan, link check, and live/static site checks.
- [ ] Document that command in the release checklist.
- [ ] Make failures actionable and concise.

---

## PHASE 12: Business Operations And Payment

### Step 12.1: Define paid conversion process
- [ ] Decide invoice format.
- [ ] Decide payment method: bank transfer, card, or both.
- [ ] Decide when work starts relative to payment for non-trial customers.
- [ ] Decide what happens if payment is late.

### Step 12.2: Add quotation and invoice details
- [ ] Ensure quote includes product name, price, tax, scope, revision count, and update policy.
- [ ] Add Japanese quote wording if needed.
- [ ] Add invoice template or process note.
- [ ] Avoid promising services not currently deliverable.

### Step 12.3: Clarify post-launch update pricing
- [ ] Decide a simple update price or quote-on-request policy.
- [ ] Add policy to pricing page if it improves trust.
- [ ] Add internal workflow for update requests.
- [ ] Add tests for quote copy if update pricing is generated.

### Step 12.4: Clarify print support
- [ ] Decide whether QR sign printing is owner-only, optional paid add-on, or convenience-store workflow.
- [ ] If optional add-on, define price and fulfillment steps.
- [ ] Keep public copy simple and avoid distracting from the core product.

### Step 12.5: Clarify multi-location policy
- [ ] Define whether multiple locations require separate setup fees.
- [ ] Define whether identical menus can share one QR page.
- [ ] Define how location-specific hours, pricing, and availability are handled.
- [ ] Add FAQ copy only if this becomes a realistic sales case.

### Step 12.6: Create common-question responses
- [ ] "Does this replace my current menu?"
- [ ] "Do I need an app?"
- [ ] "Can I change prices later?"
- [ ] "Can you translate allergies?"
- [ ] "What happens after the free trial?"
- [ ] "Can you print the QR sign?"

---

## PHASE 13: Competitive Positioning And Trust

### Step 13.1: Define positioning against monthly QR tools
- [ ] State internally why one-time setup is better for this target segment.
- [ ] Decide whether "no monthly fees" should be more prominent.
- [ ] Avoid attacking competitors by name in customer-facing copy.

### Step 13.2: Add proof without fabrication
- [ ] Identify real proof that can be shown today.
- [ ] Examples: working demo, clear price, no app install, owner confirmation, bilingual staff list.
- [ ] Do not add fake case studies.
- [ ] Do not claim existing restaurant customers unless true and approved.

### Step 13.3: Improve founder trust signals
- [ ] Decide whether to add a short founder line.
- [ ] Include Tokyo/Japan context only if accurate.
- [ ] Keep it modest and direct.
- [ ] Avoid over-personalizing the landing page.

### Step 13.4: Japanese credibility review
- [ ] Ask a native or near-native reviewer to read the Japanese public pages.
- [ ] Ask specifically about trust, clarity, and unnatural phrasing.
- [ ] Apply only changes that preserve active product constraints.

### Step 13.5: Owner objection list
- [ ] Create an internal list of the top 20 objections.
- [ ] Map each objection to page copy, FAQ, reply template, or product change.
- [ ] Prioritize objections that block trial acceptance.

---

## PHASE 14: Launch Execution And Continuous Improvement

### Step 14.1: Build a small real-world pilot batch
- [ ] Select 10 high-quality ramen/izakaya leads.
- [ ] Manually review every lead.
- [ ] Send only after explicit manual approval.
- [ ] Track replies and objections.
- [ ] Do not scale until the first batch is reviewed.

### Step 14.2: Create weekly operating rhythm
- [ ] Monday: review leads and pipeline health.
- [ ] Tuesday-Thursday morning: send approved outreach.
- [ ] Friday: review replies, trials, and product issues.
- [ ] Keep batch sizes small until conversion and deliverability are understood.

### Step 14.3: Add learning loop
- [ ] Record each owner question.
- [ ] Record each confusion point from demo or pricing.
- [ ] Convert repeated confusion into copy/product fixes.
- [ ] Keep changes test-backed.

### Step 14.4: Define scale gates
- [ ] Gate 1: first trial request.
- [ ] Gate 2: first completed trial page.
- [ ] Gate 3: first paid conversion.
- [ ] Gate 4: 5 paid customers without major workflow breakage.
- [ ] Gate 5: repeatable weekly outreach and fulfillment cadence.

### Step 14.5: Stop conditions
- [ ] Stop sending if bounce rate is high.
- [ ] Stop sending if real owners report confusion about ordering/payment.
- [ ] Stop publishing if owner confirmation workflow is unclear.
- [ ] Stop scaling if trial fulfillment takes too long manually.

---

## Summary Of Highest-Priority Work

1. [ ] Decide and document the public site source of truth: root vs `docs/`.
2. [ ] Build a real trial-state workflow from request to archive/paid.
3. [ ] Add owner-confirmation gates for prices, descriptions, ingredients, and allergy notes.
4. [ ] Add Playwright tests for demo interaction and staff handoff.
5. [ ] Add publish lifecycle states: draft, owner-review, trial-live, paid-live, archived.
6. [ ] Strengthen outreach compliance, opt-out, bounce, and batching safeguards.
7. [ ] Add dashboard route and action tests for send/publish/archive safety.
8. [ ] Add deployment health-check script for all public URLs and assets.
9. [ ] Define payment, invoice, update, print, and multi-location policies.
10. [ ] Run a 10-lead manually reviewed pilot before scaling.

## Definition Of Done For This Plan

- [ ] Full test suite passes.
- [ ] State audit passes.
- [ ] Live public URL health check passes.
- [ ] Demo interaction tests pass on mobile viewport.
- [ ] Real-send path is manually gated and tested.
- [ ] Publish path blocks unconfirmed menu facts.
- [ ] Trial lifecycle is documented and represented in code or dashboard state.
- [ ] Deployment source of truth is documented and protected by tests.
- [ ] Privacy, opt-out, and sender identity rules are documented and enforced.
- [ ] First pilot batch can be run without inventing process during execution.
