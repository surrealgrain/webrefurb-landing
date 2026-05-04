# Restaurant Lead Queue Execution Plan

## Goal

Turn the restaurant email corpus into a clean, reviewable dashboard queue, then promote verified leads into pitch-pack generation without changing the GLM-locked template content.

Current baseline:

- Dashboard queue: 483 imported records in `state/leads`
- Queue status: all records are `manual_review`
- Send-ready records: 0
- Template policy: GLM-locked, `locked_glm_seedstyle_only`

## Non-Negotiables

- Do not begin outreach from research/import records.
- Do not edit GLM-locked template body copy or menu design content in Codex.
- Only GLM should revise locked menu/template designs, using the seedstyle workflow.
- Low-tier records are not junk. They can stay in review only if they remain pitchable and menu-compatible.
- English-menu hard failures remain rejects.
- Chain/franchise/corporate/operator artifacts stay out of the clean queue.

## Phase 1: Corpus Consolidation

Status: In progress.

Tasks:

- Keep all imported queue records under `state/leads`.
- Keep import summaries under `state/lead_imports`.
- Preserve source tier metadata:
  - `v1_clean`
  - `high`
  - `medium`
  - `low`
- Preserve source import round:
  - `v1_clean`
  - `v2_round_2`
  - `v3_email_first`
- Maintain duplicate checks by normalized email.
- Maintain skipped-record manifests with skip reasons.

Acceptance criteria:

- One dashboard queue contains all importable records.
- Re-running import produces 0 new records and all current records as duplicates.
- No record is `ready_for_outreach` immediately after import.

## Phase 2: Verification System

Status: Next.

Purpose:

Separate imported leads from verified leads. The queue should make it obvious why a record is trustworthy or why it needs review.

Verification checks:

- Email check:
  - direct email present
  - normalized email valid
  - email is not junk, placeholder, platform, recruiter, press, social, or support-only
  - email source URL recorded
- Restaurant name check:
  - name from source file
  - name confirmed by at least 2 sources where possible
  - reject reviewer usernames, blog titles, event pages, shopping streets, and article titles
- Location check:
  - target city confirmed
  - address or city evidence recorded
- Category check:
  - top-level family is `ramen` or `izakaya`
  - `menu_type` maps to a dashboard-supported profile
- English-menu check:
  - reject hard English-menu signals
  - keep ambiguous cases in review, not pitch-ready
- Chain/franchise check:
  - reject known chains and clear branch/franchise infrastructure
  - hold uncertain branch names for manual review

Suggested verification fields:

- `email_verification_status`: `verified`, `needs_review`, `rejected`
- `email_verification_reason`
- `name_verification_status`: `two_source_verified`, `single_source`, `needs_review`, `rejected`
- `name_verification_sources`
- `category_verification_status`
- `city_verification_status`
- `english_menu_check_status`
- `verification_status`: `verified`, `needs_review`, `rejected`
- `verification_score`

Acceptance criteria:

- Each lead has explicit verification status fields.
- Records with uncertain name/email/category are easy to filter.
- Rejected records are not shown as active pitch candidates.

## Phase 3: Dashboard Pill System

Status: Next after verification fields.

Purpose:

Make the queue scannable without opening every record.

Core pills:

- Quality:
  - `V1 Clean`
  - `High`
  - `Medium Review`
  - `Low Review`
- Verification:
  - `Email Verified`
  - `Email Review`
  - `Name 2x Verified`
  - `Name Review`
  - `City Verified`
  - `Category Verified`
- Source:
  - `Official Site`
  - `Restaurant-Owned Page`
  - `Directory`
  - `Weak Source`
- Menu profile:
  - `Ramen`
  - `Tsukemen`
  - `Abura Soba`
  - `Mazesoba`
  - `Tantanmen`
  - `Chuka Soba`
  - `Yakitori`
  - `Kushiyaki`
  - `Kushikatsu`
  - `Kushiage`
  - `Tachinomi`
  - `Seafood / Sake / Oden`
  - `Robatayaki`
- Workflow:
  - `Pitch Ready`
  - `Needs Scope Review`
  - `Needs Name Review`
  - `Needs Email Review`
  - `Rejected`

Dashboard filters to add or confirm:

- Quality tier
- Verification status
- Email source
- City
- Menu type
- Needs scope review
- Pitch ready
- GLM template profile

Acceptance criteria:

- A reviewer can identify the next best records without reading raw JSON.
- High-confidence records are visually distinct from review records.
- No record implies sendability unless it is explicitly promoted.

## Phase 4: Promotion Workflow

Status: After dashboard pills.

Purpose:

Move records from imported/reviewed state into pitch-pack readiness only after verification.

Promotion rules:

- A record can become `pitch_ready` only if:
  - email is verified
  - restaurant name is verified or manually accepted
  - city is verified
  - menu profile is supported
  - no English-menu hard reject
  - no chain/franchise reject
- Promotion should not send anything.
- Promotion should create or update:
  - `candidate_inbox_status: pitch_ready`
  - `verification_status: verified`
  - `review_status: approved`
  - `launch_readiness_status` stays blocked until draft/sample review is complete, unless we explicitly decide otherwise.

Acceptance criteria:

- Reviewers can approve, hold, or reject records.
- Approved records are batchable by city, quality tier, and menu profile.
- No send flow bypasses review.

## Phase 5: GLM Menu Design Requests

Status: After verified category counts.

Purpose:

Ask GLM for new locked menu designs only where category volume and menu structure justify it.

Opportune moment:

- Do **not** ask GLM during raw import cleanup or while the best lanes are still being reduced by deterministic verification rules.
- Ask GLM after Phase 2 verification and Phase 3 dashboard triage have produced stable, reviewed category counts from records with:
  - verified or manually accepted restaurant name
  - verified email or a clearly reviewable owned contact path
  - verified city
  - verified `menu_type` / `establishment_profile`
  - no English-menu hard reject
  - no chain/franchise/operator reject
- The practical trigger is when a category has enough reviewed examples to show GLM the real menu structure without guessing. Use this threshold:
  - `5+` strong reviewed examples: enough to request an initial locked template.
  - `10+` strong reviewed examples: high-priority template request.
  - fewer than `5`: keep using the existing generic ramen/izakaya assets unless the category is strategically important and visually distinct.
- Make the GLM request **before** promoting records from that category into pitch-pack generation. Promotion can proceed for categories already covered by existing locked assets; categories needing new designs should stay blocked at `needs_scope_review` or equivalent until GLM returns locked assets.
- This gate can run in parallel with Phase 4 promotion workflow implementation, but GLM-dependent records must not become `pitch_ready` until the locked profile assets exist and are mapped.

Trigger:

- Run category counts after verification.
- Prioritize categories with enough leads and a distinct ordering/menu structure.
- Select 3-5 representative verified examples per category for GLM.
- Include only examples that are safe to show internally: no rejected names, no directory-only emails, and no unresolved chain/operator risk.

Likely GLM priority:

1. Yakitori / Kushiyaki
2. Kushikatsu / Kushiage
3. Seafood / Sake / Oden
4. Tachinomi
5. Robatayaki

Lower priority:

- Ramen subtypes unless the existing ramen template feels too generic:
  - Tsukemen
  - Abura Soba
  - Mazesoba
  - Tantanmen
  - Chuka Soba

GLM request format:

- Category/profile
- Real examples from verified leads
- Menu structure requirements
- Existing locked design constraints
- Seedstyle reference
- Required output assets and profile IDs

Acceptance criteria:

- New GLM assets are locked and mapped by `establishment_profile`.
- Codex only updates routing/mapping to use the new locked assets.
- Existing send flow remains unchanged.

## Phase 6: Inline Pitch Packs

Status: After GLM assets and promotion workflow.

Purpose:

Generate category-aware pitches and preview packs in controlled batches.

Batch dimensions:

- City
- Quality tier
- Menu type
- Verification score
- Template profile

Pitch-pack requirements:

- Use locked GLM template assets.
- Use verified restaurant name only.
- Use verified source notes only.
- Do not overclaim English-menu absence.
- Keep email drafts blocked until human review.

Acceptance criteria:

- Pitch packs are generated only for promoted records.
- Drafts are reviewable in dashboard before any send.
- Category-specific sample/menu asset matches the record profile.

## Phase 7: Outreach Readiness

Status: Final gate.

Purpose:

Only after verification, GLM assets, and draft review should records become sendable.

Readiness gates:

- Verified lead
- Approved dashboard review
- Correct GLM asset profile
- Draft reviewed
- Send route confirmed
- No suppression/rejection flags

Acceptance criteria:

- `ready_for_outreach` is only assigned after all gates pass.
- Send flow uses existing dashboard controls.
- No imported record is sendable by default.

## Immediate Next Work

1. Add verification fields and a verification pass over the 483 queued records.
2. Add dashboard pills and filters for quality, verification, source, city, and menu profile.
3. Produce reviewed category counts.
4. Use those counts to prepare the GLM menu-design brief.
5. After GLM locks new designs, wire the new profile assets into the dashboard.
6. Generate inline pitch packs only for promoted records.
