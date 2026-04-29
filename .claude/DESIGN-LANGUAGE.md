# StyleSeed Design Language

Compact project-local reference for StyleSeed skills. This file replaces the former long generic rulebook so project startup context stays small. Use it only when a StyleSeed skill explicitly asks for `DESIGN-LANGUAGE.md`; otherwise follow `AGENTS.md`, `PLAN.md`, and the current product handoff.

For WebRefurbMenu menu-template work, `MENU_DESIGN_LOOP.md` is the more specific visual QA loop.

## Table Of Contents

- 1-12: Core visual rules
- 13-14: Page layout and section types
- 18-20: Prohibitions, checklist, and information pyramid
- 28-30: Scroll, loading, empty, and error states
- 34: Microcopy and UX writing
- 38: Chart selection
- 40: Applying to projects
- 45-46: Dark mode and buttons
- 50: Dark-pattern prevention
- 59: Animation wrapper rules
- 61-69: Page composition and visual rhythm

## 1. Color Philosophy

Use one accent color for active/selected states. Keep structure, text, borders, and inactive UI mostly grayscale. Warning/success/destructive colors should be small and semantic, not decorative page-wide washes.

## 2. Number/Currency Display Rules

Important numbers should have a clear hierarchy: large value, smaller unit/label, nearby context. Keep numeric formatting locale-aware and avoid mixing competing large numbers in one card.

## 3. Text Hierarchy Rules

Use a small hierarchy: page title, section title, body, caption, metadata. Text inside dense panels should be tighter and smaller than hero-scale text. Do not scale font size with viewport width.

## 4. Trend Indicator Rules

Use arrows, short labels, and semantic color together. Color alone is not enough. Keep trend indicators small and adjacent to the metric they explain.

## 5. Gauge/Progress Bar Rules

Use linear progress for completion and segmented progress for milestones. Always pair progress with a label or value so meaning does not depend on color alone.

## 6. Donut Chart Rules

Use sparingly. Highlight the key segment with the accent color and keep secondary segments muted. Include a visible legend or direct labels.

## 7. Icon Badge Rules

Icons should clarify scanning, not decorate. Use familiar icon libraries when available. Badge backgrounds should be subtle and sized to the surrounding text.

## 8. Card Structure

Cards are for individual repeated items, modals, or genuinely framed tools. Prefer header, content, footer structure. Do not nest cards inside cards.

## 9. List Item Rules

List rows need predictable alignment, clear primary text, secondary metadata, and a visible status affordance when status matters. Keep row heights stable.

## 10. Selection UI Rules

Use segmented controls for small mutually exclusive modes, checkboxes/toggles for binary settings, menus for larger option sets, and tabs for view changes.

## 11. Briefing/Alert Card Rules

Alerts should explain what happened and what the operator can do next. Keep them dismissable unless they block unsafe action.

## 12. Shadow System

Use subtle shadows or borders to separate surfaces. Avoid heavy floating panels. Radius should stay modest unless the app already has a different system.

## 13. Page Layout Structure

Use full-width page bands or unframed constrained layouts. Prioritize scannability and repeated-use ergonomics for dashboards and operational tools. Keep controls and state near the content they affect.

## 14. Four Section Types

- A: constrained standard section for forms, tables, and dense content.
- B: full-width band with constrained inner content.
- C: horizontal carousel or overflow region when comparison benefits from side-by-side scanning.
- D: true hero or primary workspace; use only when the first viewport should be visually led.

Avoid repeating the same section type too many times in a row.

## 15. Card Internal Division Rules

Use dividers only when content groups need scanning separation. Prefer spacing and hierarchy first. Do not over-box every row.

## 16. Title Margin Rules

Section titles should sit close to the content they name and farther from the previous section. Dense tool panels need smaller headings than pages.

## 17. Chart Style Rules

Charts need labeled axes or direct labels, clear empty/loading/error states, and accessible contrast. Do not use charts where a list or table communicates better.

## 18. Prohibition Rules

- No decorative gradient/orb backgrounds for operational UI.
- No hidden overflow that clips important text.
- No horizontal page overflow.
- No button text that wraps awkwardly or overflows.
- No hover-only interactions for required actions.
- No invisible focus states.
- No hardcoded colors when project tokens exist.
- No generic landing page when the task is to build an actual app/tool.
- No visible instructional copy describing obvious UI mechanics.

## 19. New Page Creation Checklist

1. Identify the user's main task on the page.
2. Put the most important state/action in the first viewport.
3. Choose section types that support scanning and repeated use.
4. Use stable dimensions for boards, grids, toolbars, counters, and tiles.
5. Add loading, empty, error, and success feedback.
6. Check mobile and desktop for overflow, overlap, and text fit.
7. Verify rendered output, not only code.

## 20. Information Pyramid Structure

Top of page: current status and primary action. Middle: explanation, comparison, editable details. Bottom: logs, secondary settings, and support context. Larger type means higher importance.

## 21. Data Density Rules

Show enough information for decisions without forcing raw JSON reading. Use progressive disclosure for secondary diagnostics. Tables can be dense if columns are meaningful and aligned.

## 28. Scroll And Spacing Detail Rules

Use predictable scroll regions. Avoid nested scrolling unless the inner surface is clearly a tool. Keep touch targets at least 44px and leave enough spacing between adjacent actions.

## 29. Loading State Skeleton Rules

Skeletons should match the final layout shape and reserve space to prevent layout shift. Use spinners only for very small inline waits.

## 30. Empty State And Error State Rules

Empty states should state what is missing and offer the next reasonable action. Errors should identify what failed, avoid blame, and provide retry or recovery when possible.

## 34. Microcopy Tone Guide

Use direct, plain language. Prefer verbs over vague labels. Avoid internal terms, implementation details, and over-explaining interface mechanics. In customer-facing WebRefurbMenu copy, never mention AI, automation, scraping, or internal tools.

## 38. Chart Type Selection Guide

Use line/area charts for change over time, bars for comparison, stacked bars for composition, and tables for precise lookup. Avoid donuts for more than a few categories.

## 40. Design System Application Guide

Adapt color, typography, and density to the product domain while preserving the component rules. For WebRefurbMenu operations, prefer quiet, utilitarian, evidence-forward UI over marketing composition.

## 45. Dark Mode Guide

Dark mode needs contrast, not just inverted colors. Background should be darkest, surfaces slightly raised, text readable, borders subtle, and accent use restrained.

## 46. Button Design Rules

Buttons need a clear hierarchy: primary, secondary, destructive, icon, ghost, and disabled. Use icons for familiar tool actions. Keep labels short and action-specific.

## 50. Dark Pattern Prevention Rules

Every modal/sheet should have a clear exit unless legally or operationally blocked. Do not hide opt-out, mislabel destructive actions, fake urgency, or force unrelated actions before dismissal.

## 59. Animation Wrapper Rules

Use short, purposeful transitions. Respect `prefers-reduced-motion`. Animate opacity/transform when possible and avoid motion that shifts layout during reading.

## 61. Visual Rhythm And Breaking Monotony

Vary section scale and density intentionally. Do not create a page made of identical cards unless repeated comparison is the point.

## 62. KPI Card Variation

KPI cards should share a system but vary secondary content based on meaning: trend, progress, status, sparkline, or supporting note. Do not fill all cards with the same formula.

## 63. Composition Recipes

- SaaS dashboard: status summary, KPI grid, main chart/table, alerts, activity list.
- E-commerce: sales/orders summary, inventory or fulfillment risk, product/order table, customer issues.
- Fintech: account/portfolio summary, risk/status indicators, time-series view, transactions.
- Social/content: feed or queue first, creation action, moderation/status, trends.
- Productivity/internal tool: task queue, filters, bulk actions, detail inspector, audit/history.
- WebRefurbMenu operator dashboard: lead readiness lanes, proof/contact/package diagnostics, blocked reasons, preview/send gate, audit/report links.

## 64. Element Diversity Within Cards

Mix labels, values, badges, short notes, and actions according to need. Do not add visual variety that reduces scan speed.

## 65. Accent Distribution

Accent color should be scarce. Use it for selected state, primary CTA, and a few meaningful highlights.

## 66. Card Size Variation

Use size differences to signal importance, not decoration. Primary workspace can be larger; repeated records should stay consistent.

## 67. Progressive Density

Start with high-level status and become denser as the user moves into diagnostics. Dense data is acceptable when labels and grouping stay clear.

## 68. Empty Page Prevention

Avoid pages with a single lonely card. If data is missing, show setup state, sample-safe guidance, recent activity, or next action.

## 69. Chart And Context Pairing

Never show a chart without the conclusion or decision it supports. Pair visualization with a short label, value, or action.
