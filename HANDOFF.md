# WebRefurbMenu Handoff

## Latest Checkpoint

- Commit: `11120ea Productionize package workflows`
- Git status after commit: clean on `main`
- Finalized prices are now locked as:
  - `package_1_remote_30k` — Online Delivery — ¥30,000
  - `package_2_printed_delivered_45k` — Printed and Delivered — ¥45,000
  - `package_3_qr_menu_65k` — QR Menu System — ¥65,000

## What Is Implemented

- Canonical package registry used by exports, dashboard/API surfaces, tests, and customer-facing package copy.
- Package 1 final export gate still works for online delivery ZIPs.
- Package 2 print-pack gate is implemented:
  - A4 by default, B4 when menu density requires it.
  - B4 is the largest automatic print size.
  - Blocks with `custom_quote_required` if one food laminate plus one drinks laminate cannot fit cleanly.
  - Requires delivery contact name and address at approval time.
  - Creates `PRINT_ORDER.json`, `PRINT_CHECKLIST.md`, `DELIVERY_CHECKLIST.md`, manifest, and final ZIP.
- Package 3 QR gate is implemented:
  - Requires QR sign creation.
  - Publishes hosted menu.
  - Runs health check.
  - Renders `qr_sign_print_ready.pdf`.
  - Creates final Package 3 ZIP.
- Dashboard now has:
  - Package selector for custom builds.
  - Builds tab.
  - Package 2 review modal with print profile and delivery fields.
  - QR Package 3 approval flow.
- Website copy no longer restricts printed menus to A4; it now says menus are sized compactly for the menu and shop.
- Clean editable install works in a venv.

## Validation Completed

- Full clean-venv test suite: `217 passed`
- `git diff --check`: clean before commit
- Stale package-copy scan found no old `¥48,000`, two-package-only, or A4-only package copy.
- Real Package 2 smoke passed:
  - Generated valid `%PDF` menu PDFs.
  - Approved Package 2.
  - Final ZIP included print order, print checklist, delivery checklist, and print-pack PDFs.
- Real Package 3 smoke passed:
  - Created complete QR draft.
  - Created QR sign.
  - Approved Package 3.
  - Health check passed.
  - Final ZIP included hosted artifacts, QR sign files, health report, manifest, source, and `qr_sign_print_ready.pdf`.
- Dashboard visual verification completed for:
  - Builds tab.
  - Package 2 review modal.
  - Package 2 delivery fields.
  - QR Package 3 review modal.

## Recommended Next Step

Do a staging/operator rehearsal with real sample data:

1. Package 1: create online delivery ZIP and inspect final customer files.
2. Package 2: create print pack with delivery details and inspect physical print instructions.
3. Package 3: create QR package with complete item descriptions/ingredients and inspect live URL, QR sign PDF, and ZIP.
4. Treat any operator confusion or awkward manual step as a launch blocker.
