# WebRefurb QR Menu Studio — Design Brief

## Product Definition

**One sentence:** WebRefurb creates hosted English QR menus for Japanese restaurants — customers scan a QR code, browse the menu in English, add items to a simple list, and show the list to staff in Japanese.

**What it is NOT:** Not an ordering system. No POS, checkout, payment, order submission, table numbers, or staff dashboard.

**Current offer:** `english_qr_menu_65k` / English QR Menu / 65,000 yen tax excluded, with a free 1-week trial before the owner decides whether to continue.

**Four surfaces:**
1. **Operator workflow** — QR Menu Studio where Chris builds menus
2. **Customer experience** — mobile QR menu that restaurant customers see
3. **Owner review** — secure link for restaurant owners to approve their menu
4. **Publish lifecycle** — draft → review → published; superseded/rollback handling is planned

---

## Implementation Status

This document is a product/design direction brief. Public site pages, the generic demo hub, ramen/sushi demo pages, and the QR Menu Studio baseline exist today. Larger workflow ideas such as rollback, the bulk spreadsheet editor, keyboard shortcuts, auto-save, owner self-service editing, and advanced published-menu management are planned unless code and tests explicitly show them as implemented.

First contact remains QR-first, links the generic demo, asks for a reply only, and does not ask for menu photos. Test sends go only to `chris@webrefurb.com`; real sends require explicit manual approval.

## Design System — StyleSeed Alignment

This project follows the StyleSeed design language (`.claude/DESIGN-LANGUAGE.md`). Key rules applied:

### Information Pyramid (Section 20)
- **Top of page:** current status and primary action
- **Middle:** explanation, comparison, editable details
- **Bottom:** logs, secondary settings, support context
- Larger type = higher importance

### Section Types (Section 14)
- **Type A:** constrained standard section (forms, tables, dense content)
- **Type B:** full-width band with constrained inner content
- **Type C:** horizontal carousel for comparison
- **Type D:** hero workspace — first viewport should be visually led
- Never repeat the same section type consecutively

### Prohibitions (Section 18)
- No decorative gradient/orb backgrounds
- No hover-only interactions for required actions
- No visible instructional copy describing obvious UI mechanics
- No hardcoded colors when project tokens exist
- No hidden overflow that clips important text

### Composition Recipe (Section 63)
> WebRefurbMenu operator dashboard: lead readiness lanes, proof/contact/package diagnostics, blocked reasons, preview/send gate, audit/report links.

### Button Hierarchy (Section 46)
Primary → Secondary → Destructive → Icon → Ghost → Disabled. Labels short and action-specific.

### Card Rules (Section 8)
Header/content/footer structure. Do not nest cards inside cards.

### Accent Distribution (Section 65)
Accent color scarce: selected state, primary CTA, few meaningful highlights only.

### Operator Tone (Section 34)
Direct, plain language. Verbs over vague labels. No AI/automation/internal-tool terms in customer-facing copy.

---

## Design Tokens

WebRefurb uses two related visual systems:

- **Operator dashboard:** teal/dark operational palette for dense workflow screens.
- **Public site and demos:** coral/white menu palette that matches the customer-facing QR experience.

Operator palette (carry forward):

| Token | Value | Use |
|-------|-------|-----|
| `--page-bg` | `#f7f7f5` | Main background |
| `--sidebar-bg` | `#03141D` | Sidebar, dark surfaces |
| `--accent` | `#0E7490` | Primary actions, links, active states |
| `--accent-hover` | `#0B5E73` | Hover state |
| `--success` | `#22C55E` | Published, healthy, confirmed |
| `--error` | `#C43D2F` | Failed validation, broken health |
| `--warning` | `#F59E0B` | Needs attention, pending |
| `--text-primary` | `#1A1A1A` | Body text |
| `--text-secondary` | `#6B7280` | Labels, metadata |
| `--border` | `#E5E7EB` | Card borders, dividers |
| `--card-bg` | `#FFFFFF` | Card surfaces |
| `--radius-sm` | `6px` | Buttons, badges |
| `--radius-md` | `10px` | Cards, modals |
| `--radius-lg` | `14px` | Panels, drawers |
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.05)` | Subtle elevation |
| `--shadow-md` | `0 4px 12px rgba(0,0,0,0.08)` | Cards |
| `--shadow-lg` | `0 12px 32px rgba(0,0,0,0.12)` | Modals, drawers |

Public palette:

| Token | Value | Use |
|-------|-------|-----|
| `--coral` | `#E94560` | Public primary CTA, selected states |
| `--coral-dark` | `#C73550` | Public CTA hover |
| `--coral-soft` | `#FFF0F2` | Public soft highlight backgrounds |
| `--navy` | `#1a1f36` | Public dark CTA bands and phone frame |
| `--ink` | `#111827` | Public headings/body emphasis |
| `--body` | `#374151` | Public body text |
| `--border` | `#e5e7eb` | Public dividers and controls |

**Typography:** Inter 400 body / 600-700 headings. Fira Code for IDs/codes. Line height 1.5 body, 1.2 headings.

**Spacing rule:** 6px multiples throughout (p-1.5, p-3, p-6, p-9, p-12).

---

## Terminology

### Allowed (customer-facing)
"Add to list", "View list", "Show to staff", "Show Staff List", "My list", "Items I want", "Menu", "Browse menu"

### Forbidden (customer-facing)
"Order", "Cart", "Checkout", "Place order", "Submit order", "Send order", "POS", "Table number", "Payment", "Bill"

### Operator-facing
"Draft", "Ready for review", "Published", "Archived", "Extract items", "Confirm content", "Create QR sign", "Approve package", "Owner confirmation"

---

## Screen 1: Leads

**Purpose:** Discover and qualify restaurants for QR menu outreach.
**Section type:** Type A (constrained, table-dense)
**Primary question:** "Which leads are ready to become QR menus?"

### Layout
- Full-width data table with sticky header
- Filter bar above: genre (ramen/izakaya/skip), city, send readiness
- Batch action bar appears when rows selected

### Columns

| Column | Width | Sortable | Notes |
|--------|-------|----------|-------|
| Checkbox | 40px | No | Bulk select |
| Restaurant | 2fr | Yes | Name + address; kanji secondary line |
| Genre | 80px | Yes | Badge: ramen(teal)/izakaya(warm)/skip(gray) |
| City | 100px | Yes | |
| Evidence | 1fr | No | Thumbnail count + quality score |
| Send Readiness | 120px | Yes | Green/amber/red badge |
| Last Action | 120px | Yes | Date + action type |
| Actions | 120px | No | "Draft QR" (if qr_ready), "View" |

### Actions
- Row click → Lead detail slide-over (right, 480px)
- "Draft QR" → POST /api/qr/{reply_id} (only when qr_ready)
- Bulk: "Mark skip", "Queue for outreach"

### Lead Detail Slide-Over
- Restaurant name (large), kanji, address, genre badge
- Evidence: photo thumbnails, website URL, Maps link
- Source metadata: search query, discovery date
- Send readiness checklist with pass/fail per item
- Primary CTA: "Draft QR menu" (accent, if ready)
- Secondary: "Skip lead", "Re-evaluate"

### Empty State
"No leads yet. Run a search or import to get started." + CTA: "Search for leads"

---

## Screen 2: QR Menu Studio Workspace

**Purpose:** Main workspace for building a QR menu. Operator's home base.
**Section type:** Type D (hero workspace — first viewport visually led)
**Primary question:** "What does this menu look like and what needs work?"

### Three-Panel Layout
- **Left (280px):** Section navigator
- **Center (flex):** Item list for active section
- **Right (320px, collapsible):** Context panel

### Left Panel — Section Navigator
- Vertical list of sections (e.g., "Ramen", "Side Dishes", "Drinks")
- Each: editable name, item count badge
- Drag handles for reorder
- "Add section" at bottom
- Active section: accent background highlight

### Center — Item List
- Card-rows (not dense table rows) within active section
- Each item card:
  - English name (bold), Japanese name (secondary text-secondary)
  - Price (right-aligned)
  - Description preview (truncated 2 lines, expandable)
  - Availability toggle
  - Quick actions: edit → modal, duplicate, delete
- "Add item" button at section bottom
- Items drag-reorderable within section

### Right Panel — Context
- Menu metadata: restaurant name, kanji, menu ID, created date
- QR code thumbnail (click to enlarge)
- Live URL (copyable, if published)
- Status badge: current lifecycle state
- Actions: "Preview menu" (new tab), "Create QR sign", "Publish"

### Item Edit Modal (560px)
Opened by "edit" on item card or "Add item":

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| English name | Text | Yes | |
| Japanese name | Text | Yes | For Show Staff List |
| Section | Dropdown | Yes | Current section default |
| Price | Text | No | ¥ prefix, numeric |
| Description (EN) | Textarea | No | Character count |
| Description (JA) | Textarea | No | Owner review reference |
| Photo | Upload | No | Drag-drop, preview |
| Dietary tags | Tag pills | No | Vegetarian, spicy, contains nuts |
| Availability | Toggle | No | Default: on |

Buttons: "Save" (primary), "Cancel" (secondary), "Delete" (destructive, requires confirmation)
Auto-save on field blur with "Saved" indicator.

### Keyboard Shortcuts
N (new item), E (edit selected), ↑/↓ (navigate), S (new section), Esc (close/deselect)

### Empty Section
"No items yet. Add your first item." + "Add item" CTA

---

## Screen 3: Materials

**Purpose:** Manage source materials — photos, documents, reference URLs.
**Section type:** Type A (constrained, grid-dense)
**Primary question:** "What source materials are available for this menu?"

### Layout
- Upload zone at top (drag-drop, dashed border, large)
- Filter tabs: "Photos" / "Documents" / "References" / "All"
- 3-column grid of material cards

### Material Card
- Thumbnail (photo) or file icon (PDF, URL)
- Filename/URL (truncated)
- Source badge: "Uploaded" / "Google Maps" / "Website"
- Date added
- Actions: "Use for extraction", "Open", "Remove"

### Upload Zone
- "Drop photos or documents here" + "Browse files"
- Accepts: JPG, PNG, PDF, HEIC (auto-convert)
- Upload progress per file

### Empty State
"No materials yet. Upload menu photos to start building." + Upload zone as primary CTA

---

## Screen 4: Menu Items Editor

**Purpose:** Bulk editing — spreadsheet efficiency for many items.
**Section type:** Type A (constrained, table-dense)
**Primary question:** "How do all items look at a glance, and what needs changing?"

### Layout
- Full-width table, inline editing
- Sticky section headers (section names as divider rows)
- Horizontal scroll for wide views

### Columns (editable inline)

| Column | Editable | Type |
|--------|----------|------|
| English name | Yes | Text input |
| Japanese name | Yes | Text input |
| Section | Yes | Dropdown |
| Price | Yes | Text (¥) |
| Description | Yes | Click → textarea overlay |
| Dietary tags | Yes | Tag pill editor |
| Available | Yes | Toggle |
| Photo | No | Thumbnail, click to view |

### Interactions
- Click cell → inline edit
- Tab → next cell, Shift+Tab → previous
- Enter → save + next row
- Escape → cancel
- Double-click description → expanded textarea

### Bulk Operations
- Checkbox row selection
- Floating action bar: "Change section", "Set availability", "Delete selected"
- Confirmation: "Delete 5 items from Ramen section?"

### Section Management
- Divider rows: drag reorder, inline rename
- "Delete empty section" (0 items only)

---

## Screen 5: Preview

**Purpose:** See exactly what customers will see on their phone.
**Section type:** Type D (hero — the preview IS the viewport)
**Primary question:** "Is this menu ready for customers?"

### Layout
- **Center:** Phone mockup frame (375×812, iPhone-shaped)
- **Top bar:** Device toggle (iPhone/Android/Tablet), orientation
- **Right sidebar (collapsible):** Preview settings

### Phone Mockup
- Renders actual HTML template from assets/templates/
- Scrollable within frame
- Language toggle (EN/JA) in phone's top-right
- "Show Staff List" visible and functional in mockup
- "Add to list" updates list count in mockup

### Preview Settings
- Template selector (auto-selected by genre)
- Language: EN / JA / Both
- Section links → scroll to section
- "Open in new tab" → standalone preview

### Responsive Toggle
375px (phone) → 768px (tablet) → 1024px (desktop)

---

## Screen 6: Show Staff List (Customer Feature)

**Purpose:** The list customer shows to staff. Japanese prominent, English secondary.
**Surface:** Customer-facing (part of Screen 10)

### Customer Flow
1. Browse menu → tap "Add to list" on items
2. Floating badge: "My List (3)" with count
3. Tap badge → full-screen overlay opens
4. List shows Japanese name large, English smaller
5. Staff reads Japanese names from phone screen
6. Customer can remove items or close

### Overlay Design
- **Full-screen overlay** (not separate page)
- **White background** (readable under restaurant lighting)
- **Header:** "Show to Staff" / スタッフに見せる
- **Each item:**
  - Japanese name: 24px, bold, text-primary (what staff reads)
  - English name: 14px, text-secondary (customer reference)
  - Price: right-aligned
  - Remove button (×)
- **Footer:** "Close" button, item count
- **NO submit/send/order buttons**

### Accessibility
- High contrast (black on white)
- Touch targets ≥ 44px
- Clear "Close" action
- Items removable individually

### Empty State
"Your list is empty. Tap 'Add to list' on menu items."

---

## Screen 7: Owner Review

**Purpose:** Restaurant owner reviews menu via secure link. No account.
**Surface:** Separate — owner-facing, mobile-first, bilingual JA/EN

### Entry
- URL: `/review/{review_token}` — one-time, 7-day expiry
- Sent via email
- Opens directly — no login

### Layout
- **Top:** Restaurant name, review deadline, language toggle
- **Main:** Mobile preview (same rendering as Screen 5, read-only)
- **Bottom (sticky):** "Approve" + "Request changes"

### Approve
1. Click "内容を確認しました" (Confirmed)
2. Dialog: "メニューを公開します。よろしいですか？" (Publish menu. OK?)
3. Confirm → `confirmed_by_owner`
4. Success: "ありがとうございます。メニューを公開いたします。"

### Request Changes
1. Click "修正をお願いします" (Please correct)
2. Modal with textarea: "修正したい点をご記入ください"
3. Optional: tap item in preview to auto-reference
4. Submit → `changes_requested`, operator notified

### States

| State | What Owner Sees |
|-------|-----------------|
| Pending | Preview + Approve/Request changes |
| Changes requested | "Your changes are being processed" |
| Approved | "Thank you" + live QR link |
| Expired | "Link expired. Contact us for new link." |

### Constraints
- No account, no editing, no download
- Mobile-first, bilingual JA primary
- Trust signals: WebRefurb branding, contact info

---

## Screen 8: Publish

**Purpose:** Publish gate — operator confirms readiness.
**Section type:** Type D (hero — checklist IS the viewport)
**Primary question:** "Is everything ready to make this menu live?"

### Pre-Publish Checklist

| Check | Pass | Fail | Fixable |
|-------|------|------|---------|
| Menu has items | ✓ ≥1 section with items | ✗ No items | Yes → item editor |
| All items named | ✓ All have English names | ✗ N missing | Yes → highlights items |
| No placeholder text | ✓ No [DRAFT]/[TODO] | ✗ N placeholders | Yes |
| QR code generated | ✓ QR sign exists | ✗ No sign | Yes → "Create QR sign" |
| Owner confirmed | ✓ Prices/descriptions confirmed | ✗ Pending | Yes → confirm panel |
| Preview renders | ✓ Mobile OK | ✗ Template error | Manual |
| Health check | ✓ Assets + checksums OK | ✗ Drift | Yes → re-publish |

### Publish Action
- Enabled only when all checks pass
- "Publish menu" → confirmation dialog:
  - "This menu will be live at [URL]"
  - "Customers scanning the QR code will see this menu"
  - Buttons: "Publish Menu" (primary) / "Go Back" (secondary)
  - **No default button** (Section 46 — force conscious choice)
- After publish: success state with live URL, QR download, sign download

### Post-Publish
- Status badge → "Published" (success green)
- Live URL activates
- Version number increments
- Previous version → "Superseded"

---

## Screen 9: Published Menus

**Purpose:** Post-publish control center.
**Section type:** Type B (full-width band, cards)
**Primary question:** "Which menus are live and healthy?"

### Layout
- 2-column card grid (1 column mobile)
- Filter: status/genre/city, search by name

### Menu Card
- Header: restaurant name, kanji, status badge
- QR code thumbnail
- Metadata: published date, version, item count
- Health indicator: green dot / amber / red
- Actions: "Edit menu" (new draft), "Rollback", "Health check", "Download package"
- Expanded: version history timeline, last audit

### Version History Timeline
- Vertical timeline per version
- Each: version ID, publish date, operator, item count
- Active version: green highlight
- "Rollback to this version" on historical entries

### Health Check Panel
- Manifest exists, HTML renders, assets present, checksums match
- Pass/fail list
- "Auto-repair" for asset drift

### Empty State
"No published menus yet. Complete a menu workflow to publish your first QR menu." → "Go to Leads"

---

## Screen 10: Customer-Facing Mobile QR Menu

**Purpose:** The product. What customers see after scanning QR.
**Surface:** Separate — customer-facing, static HTML, no framework

### Principles
- Static HTML, no build step, fast on restaurant WiFi
- Single-page scroll, no pagination
- Sticky horizontal tabs, scroll-to-section
- English primary, Japanese toggle
- Branded by genre (beige=washoku, dark=izakaya, clean=ramen)

### Layout

```
┌──────────────────────────────┐
│ Restaurant Name              │
│ レストラン名                   │
│                              │
│ [Ramen] [Sides] [Drinks]    │  ← Sticky tab bar
├──────────────────────────────┤
│                              │
│  Tonkotsu Ramen              │
│  豚骨ラーメン                   │
│  Rich pork bone broth        │
│  ¥950              [Add]     │
│                              │
│  Miso Ramen                  │
│  味噌ラーメン                   │
│  Hokkaido-style miso         │
│  ¥900              [Add]     │
│                              │
│  ...                         │
│                              │
│                  [My List 3] │  ← Floating badge
└──────────────────────────────┘
```

### Item Card (Customer)
- English name: 18px, bold
- Japanese name: 14px, text-secondary
- Description: 14px, secondary, max 2 lines truncated
- Price: 16px, right-aligned
- "Add to list" button: accent, 36px height, rounded
- Dietary icons: small pills (vegetarian, spicy, nut warning)
- Photo: optional, 4:3, lazy-loaded, thumbnail-left

### Sticky Tab Bar
- Horizontal scroll, accent underline on active
- Scrolls to section on tap
- Updates active on scroll (Intersection Observer)

### Floating List Badge
- Fixed bottom-right, count in circle
- Tap → Show Staff List overlay (Screen 6)
- Appears only when list has items
- Scale animation on add

### Language Toggle
- Fixed top-right, single tap EN ↔ JA
- localStorage persistent
- CSS class toggle, no reload

### Performance Targets
- FCP < 1.5s on 3G
- Page weight < 100KB HTML+CSS
- No JS framework
- Inline critical CSS, lazy-load rest
- Photos: WebP+JPG fallback, max 200KB each

### Accessibility
- 16px minimum body text
- 4.5:1 contrast minimum
- 44px touch targets
- Alt text on images
- Semantic HTML
- lang attribute switches with language

---

## User Flows

### Flow 1: Create Menu from Lead
```
Leads → qr_ready lead → "Draft QR" →
  Studio (needs_extraction) →
  Materials → Upload photos →
  "Extract items" → Items populate →
  Items Editor → Review/edit →
  Preview → Verify mobile →
  Publish → Checklist → Confirm → Published
```

### Flow 2: Edit Published Menu
```
Published Menus → "Edit menu" →
  New draft (branched from live) →
  Studio → Edit items →
  Preview → Verify →
  Publish → Checklist → Confirm →
  New version live, old superseded
```

### Flow 3: Owner Review
```
Operator finishes → Sends review link →
  Owner opens on phone →
  (A) Approves → Operator publishes
  (B) Requests changes → Operator edits → Re-sends
```

### Flow 4: Customer QR Menu
```
Scan QR → Menu loads →
  Browse sections →
  "Add to list" on items →
  Badge shows count →
  Tap badge → Show Staff List →
  Show phone to staff → Staff reads Japanese →
  Close list → (optional) add more
```

### Flow 5: Rollback
```
Published Menus → Find issue →
  Expand → Version history →
  "Rollback to v2" →
  Confirm → v2 live, current superseded
```

---

## Component Library

| Component | Screens | Notes |
|-----------|---------|-------|
| StatusBadge | All | draft=amber, published=green, superseded=gray, error=red |
| GenreBadge | Leads, Published | ramen=teal, izakaya=warm, skip=gray |
| QRCodeThumbnail | Studio, Published, Publish | Small preview, click enlarge |
| ItemCard | Studio, Preview | Display + edit mode |
| SectionNav | Studio left panel | Vertical list, drag reorder |
| PreFlightCheck | Publish | Pass/fail row |
| ContextPanel | Studio right panel | Collapsible metadata + actions |
| PhoneMockup | Preview | 375×812 iframe in frame |
| FloatingBadge | Customer menu | List count |
| ShowStaffList | Customer menu | Full-screen overlay |
| OwnerReviewFooter | Owner review | Sticky approve/request |
| UploadZone | Materials | Drag-drop area |
| EmptyState | All | Illustration + CTA |
| ConfirmDialog | Publish, Rollback, Delete | Specific message, descriptive buttons |
| SlideOver | Lead detail | Right, 480px |
| Modal | Item editor, Bulk | Centered, 560px |
| Toast | All | Auto-dismiss 3s |
| CopyButton | Studio, Published | URL copy + feedback |

---

## State Designs

### Empty States

| Screen | Message | CTA |
|--------|---------|-----|
| Leads | "No leads yet. Run a search or import to get started." | "Search for leads" |
| Studio | "No items yet. Add your first item or extract from photos." | "Add item" / "Extract" |
| Materials | "No materials yet. Upload menu photos to start building." | Upload zone |
| Published | "No published menus yet." | "Go to Leads" |
| Customer | Hide empty sections entirely | — |

### Error States

| Error | Display | Recovery |
|-------|---------|----------|
| API failure | Toast: "Failed to save. Check connection and retry." | Retry |
| Extraction failed | Banner: "Could not identify items. Try clearer photos or add manually." | "Add manually" |
| Publish blocked | Checklist highlights failures with "Fix" links | Fix → re-check |
| Health failed | Red dot + failure reason | "Run check" / "Auto-repair" |
| Review expired | "Link expired. Contact us for new link." | Contact info |

### Safety Gates

| Scenario | Guard |
|----------|-------|
| Publish without owner confirmation | Check blocks. Shows "Owner content not confirmed" → confirm panel |
| Delete item | Dialog: "Delete '[name]' from [section]?" → "Delete Item" / "Keep Item" |
| Publish empty sections | Warning (not block): "2 empty sections. Publish anyway?" |
| Rollback | Dialog: "Replace live (v3) with v2? Current will be archived." |
| Bulk delete | "Delete 5 items? Cannot be undone." |

---

## Microcopy

### Operator-Facing

| Context | Copy |
|---------|------|
| Draft created | "Draft created for {restaurant}" |
| Extraction done | "Extracted {n} items from {m} photos" |
| Content confirmed | "Owner content confirmed for {restaurant}" |
| QR sign ready | "QR sign generated — download or print" |
| Publish success | "Published! Live at {url}" |
| Publish blocked | "Publish blocked — {n} issues need attention" |
| Rollback done | "Rolled back to version {n}" |
| Health pass | "All checks passed" |
| Health fail | "{n} issues detected — view details" |

### Owner-Facing (Japanese)

| Context | Copy |
|---------|------|
| Review invite | "{restaurant}の英語メニューをご確認ください" |
| Approve button | "内容を確認しました" |
| Request changes | "修正をお願いします" |
| Changes note | "修正したい点をご記入ください" |
| Approved thanks | "ありがとうございます。メニューを公開いたします。" |
| Link expired | "このリンクは有効期限が切れています。新しいリンクをご希望の場合はご連絡ください。" |

### Customer-Facing

| Context | Copy |
|---------|------|
| Add button | "Add to list" |
| List badge | "My List ({n})" |
| Show header | "Show to Staff" / "スタッフに見せる" |
| Empty list | "Your list is empty" |
| Remove | "Remove" |
| Close | "Close" |
| Language | "日本語" / "English" |

---

## Excluded from v1

1. No ordering/checkout/payment
2. No table numbers
3. No staff dashboard
4. No customer accounts
5. No analytics
6. No A/B testing
7. No multi-language beyond EN/JA
8. No automatic real sending
9. No owner self-service editing
10. No inventory/availability sync
11. No push notifications
12. No SEO optimization
13. No customer reviews/ratings
14. No POS integration
15. No automated translation pipeline

## Future Parking Lot

- Owner self-service portal
- Seasonal menu variants
- Customer allergen filter
- Photo upload by owner
- Multi-restaurant chains
- Analytics dashboard
- Google Business Profile integration
- Automated menu change detection
- Custom domain hosting
- Printed QR sign templates

---

## Data Requirements

### Per-Screen Data Sources

| Screen | Primary Data | API | Refresh |
|--------|-------------|-----|---------|
| Leads | Lead list + readiness | GET /api/leads | On load + manual |
| Studio | Menu source + items | GET /api/qr/{job_id}/review | On load |
| Materials | Photo/document assets | GET /api/qr/{job_id}/review | On load |
| Items Editor | Items by section | GET /api/qr/{job_id}/review | On load |
| Preview | Rendered template | GET /menus/{menu_id}/ | On change |
| Show Staff List | localStorage items | Client-side | Real-time |
| Owner Review | Preview + status | GET /api/qr/{job_id}/review (token) | On load |
| Publish | Checklist + validation | POST /api/qr/{job_id}/publish | On action |
| Published Menus | Menu list + health | GET /api/qr-menus | On load + manual |
| Customer Menu | Static HTML | docs/menus/{menu_id}/ | On load |

### Actions Per Screen

| Screen | Primary | Destructive |
|--------|---------|-------------|
| Leads | Search, import, draft QR, skip | Delete lead (confirm) |
| Studio | Add/edit/delete items, extract, preview | Delete item (confirm) |
| Materials | Upload, extract, remove | Remove (confirm) |
| Items Editor | Inline edit, bulk edit, reorder | Delete items (confirm) |
| Preview | Switch template, language, device | — |
| Show Staff List | Add/remove items | Clear list (confirm) |
| Owner Review | Approve, request changes | — |
| Publish | Run checks, publish | — (gate) |
| Published Menus | Edit, rollback, health, download | Rollback (confirm) |
| Customer Menu | Add to list, view list, toggle lang | — |

---

## Information Architecture

```
QR Menu Studio
├── Leads
│   ├── Lead list (table)
│   └── Lead detail (slide-over)
├── Studio (per-menu workspace)
│   ├── Workspace
│   │   ├── Section navigator (left)
│   │   ├── Item list (center)
│   │   └── Context panel (right)
│   ├── Materials
│   │   ├── Upload zone
│   │   └── Material grid
│   ├── Items Editor (bulk)
│   │   └── Inline-editable table
│   └── Preview
│       ├── Phone mockup
│       └── Preview settings
├── Publish
│   ├── Pre-flight checklist
│   └── Confirmation gate
└── Published Menus
    ├── Menu cards (grid)
    ├── Version history
    └── Health check panel

Owner Review (separate surface)
├── Mobile preview
├── Approve / Request changes
└── Confirmation / feedback

Customer Menu (separate surface)
├── Restaurant header
├── Section tab bar (sticky)
├── Menu items (scrollable)
├── "Add to list" buttons
├── Floating list badge
└── Show Staff List (overlay)
```
