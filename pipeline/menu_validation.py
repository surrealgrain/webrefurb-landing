"""Menu data validation for owner-confirmed public QR menus."""

from __future__ import annotations

from typing import Any


MENU_CONFIRMATION_FIELDS = (
    "price",
    "description",
    "ingredients",
    "allergens",
)


def menu_item_confirmation_gaps(item: dict[str, Any], *, index: int = 0) -> list[str]:
    """Return publish-blocking confirmation gaps for one menu item."""
    gaps: list[str] = []
    if str(item.get("price") or "").strip() and not _confirmed(item, "price"):
        gaps.append(f"item_{index}_price_owner_confirmation_required")
    if str(item.get("description") or "").strip() and not _confirmed(item, "description"):
        gaps.append(f"item_{index}_description_owner_confirmation_required")
    if _has_list_or_text(item.get("ingredients")) and not _confirmed(item, "ingredients"):
        gaps.append(f"item_{index}_ingredients_owner_confirmation_required")
    if (_has_list_or_text(item.get("allergens")) or str(item.get("allergy_notes") or "").strip()) and not _confirmed(item, "allergens"):
        gaps.append(f"item_{index}_allergens_owner_confirmation_required")
    if str(item.get("approval_status") or "pending_review") not in {"approved", "owner_approved", "confirmed_by_owner"}:
        gaps.append(f"item_{index}_translation_review_required")
    return gaps


def menu_publish_validation(source: dict[str, Any]) -> dict[str, Any]:
    """Validate source menu data before it becomes a public final menu."""
    errors: list[str] = []
    warnings: list[str] = []
    if not str(source.get("restaurant_name") or "").strip():
        errors.append("restaurant_name_missing")
    items = source.get("items") or []
    if not items:
        errors.append("menu_items_missing")
    for index, item in enumerate(items):
        if not str(item.get("english_name") or item.get("name") or "").strip():
            errors.append(f"item_{index}_english_name_missing")
        if not str(item.get("japanese_name") or "").strip():
            errors.append(f"item_{index}_japanese_name_missing")
        errors.extend(menu_item_confirmation_gaps(item, index=index))
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def confirmation_summary(source: dict[str, Any]) -> dict[str, Any]:
    items = source.get("items") or []
    totals = {field: 0 for field in MENU_CONFIRMATION_FIELDS}
    required = {field: 0 for field in MENU_CONFIRMATION_FIELDS}
    for item in items:
        if str(item.get("price") or "").strip():
            required["price"] += 1
            totals["price"] += int(_confirmed(item, "price"))
        if str(item.get("description") or "").strip():
            required["description"] += 1
            totals["description"] += int(_confirmed(item, "description"))
        if _has_list_or_text(item.get("ingredients")):
            required["ingredients"] += 1
            totals["ingredients"] += int(_confirmed(item, "ingredients"))
        if _has_list_or_text(item.get("allergens")) or str(item.get("allergy_notes") or "").strip():
            required["allergens"] += 1
            totals["allergens"] += int(_confirmed(item, "allergens"))
    return {
        "total_items": len(items),
        "required": required,
        "confirmed": totals,
        "complete": all(totals[field] == required[field] for field in MENU_CONFIRMATION_FIELDS),
    }


def _confirmed(item: dict[str, Any], field: str) -> bool:
    if bool(item.get(f"{field}_confirmed")):
        return True
    if field == "description" and bool(item.get("desc_confirmed")):
        return True
    if field in {"ingredients", "allergens"} and bool(item.get("ingredient_allergen_confirmed")):
        return True
    if field in {"ingredients", "allergens"}:
        combined = item.get("ingredient_allergen_confirmation")
        if isinstance(combined, dict) and str(combined.get("status") or "") == "confirmed_by_owner":
            return True
        if isinstance(combined, bool):
            return combined
    record = item.get(f"{field}_confirmation")
    if isinstance(record, dict):
        return str(record.get("status") or "") == "confirmed_by_owner"
    return bool(record)


def _has_list_or_text(value: Any) -> bool:
    if isinstance(value, list):
        return any(str(item).strip() for item in value)
    return bool(str(value or "").strip())
