"""Quote and order generation for P5 — Paid Operations Workflow.

Generates structured quotes, manages order state transitions, and enforces
production-approval blocking rules.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from .constants import (
    PACKAGE_REGISTRY,
    DEFAULT_REVISION_LIMIT,
    QUOTE_EXPIRY_DAYS,
    PAYMENT_TERMS_FULL_UPFRONT,
    ORDER_STATE_QUOTED,
    ORDER_STATE_QUOTE_SENT,
    ORDER_STATE_PAYMENT_PENDING,
    ORDER_STATE_PAID,
    ORDER_STATE_INTAKE_NEEDED,
    ORDER_STATE_IN_PRODUCTION,
    ORDER_STATE_OWNER_REVIEW,
    ORDER_STATE_OWNER_APPROVED,
    ORDER_STATE_DELIVERED,
    ORDER_STATE_CLOSED,
    ORDER_STATES,
    ORDER_STATES_BEFORE_PRODUCTION,
    CUSTOM_QUOTE_TRIGGERS,
    PACKAGE_2_PRINT_COST_ESTIMATE_YEN,
    PACKAGE_2_DELIVERY_COST_ESTIMATE_YEN,
)
from .models import (
    Order,
    QuoteDetails,
    PaymentDetails,
    IntakeChecklist,
    OwnerApproval,
    RevisionRecord,
)


# ---------------------------------------------------------------------------
# Valid state transitions
# ---------------------------------------------------------------------------
_VALID_TRANSITIONS: dict[str, set[str]] = {
    ORDER_STATE_QUOTED: {ORDER_STATE_QUOTE_SENT, ORDER_STATE_CLOSED},
    ORDER_STATE_QUOTE_SENT: {ORDER_STATE_PAYMENT_PENDING, ORDER_STATE_CLOSED},
    ORDER_STATE_PAYMENT_PENDING: {ORDER_STATE_PAID, ORDER_STATE_CLOSED},
    ORDER_STATE_PAID: {ORDER_STATE_INTAKE_NEEDED},
    ORDER_STATE_INTAKE_NEEDED: {ORDER_STATE_IN_PRODUCTION},
    ORDER_STATE_IN_PRODUCTION: {ORDER_STATE_OWNER_REVIEW},
    ORDER_STATE_OWNER_REVIEW: {ORDER_STATE_OWNER_APPROVED, ORDER_STATE_IN_PRODUCTION},
    ORDER_STATE_OWNER_APPROVED: {ORDER_STATE_DELIVERED},
    ORDER_STATE_DELIVERED: {ORDER_STATE_CLOSED},
    ORDER_STATE_CLOSED: set(),
}


def can_transition(current: str, target: str) -> bool:
    """Check if an order can transition from current to target state."""
    return target in _VALID_TRANSITIONS.get(current, set())


# ---------------------------------------------------------------------------
# Quote generation
# ---------------------------------------------------------------------------

# Scope descriptions for each package
_SCOPE_DESCRIPTIONS = {
    "package_1_remote_30k": (
        "English menu translation and layout. Print-ready PDF and image files "
        "delivered online. Includes ticket machine guide if applicable."
    ),
    "package_2_printed_delivered_45k": (
        "Everything in Online Delivery, plus professional printing, lamination, "
        "and courier delivery to your restaurant."
    ),
    "package_3_qr_menu_65k": (
        "Hosted English menu page accessible by QR code. Includes QR code generation, "
        "printable QR sign, 12-month hosting, one bundled update round in the first 30 days."
    ),
}

_DELIVERY_TERMS = {
    "package_1_remote_30k": "Print-ready files delivered by email or download link within 5 business days of intake completion.",
    "package_2_printed_delivered_45k": "Printed and laminated menus delivered by domestic courier within 7 business days of intake completion.",
    "package_3_qr_menu_65k": "QR menu page published within 5 business days of intake completion. QR sign PDF delivered with Package 2 if bundled, or by email.",
}

_UPDATE_TERMS = {
    "package_1_remote_30k": "Updated files provided at quoted price for menu changes. No ongoing updates included.",
    "package_2_printed_delivered_45k": "Reprints at quoted price for menu changes. No ongoing updates included.",
    "package_3_qr_menu_65k": "One bundled update round within 30 days of publish. Later updates quoted separately.",
}


def generate_quote(
    *,
    business_name: str,
    package_key: str,
    is_custom: bool = False,
    custom_price_yen: int | None = None,
    custom_reason: str = "",
    notes: str = "",
) -> QuoteDetails:
    """Generate a structured quote for a package."""
    pkg = PACKAGE_REGISTRY.get(package_key)
    if not pkg:
        raise ValueError(f"Unknown package key: {package_key}")

    now = datetime.now(timezone.utc)
    expiry = now + timedelta(days=QUOTE_EXPIRY_DAYS)
    price = custom_price_yen if is_custom and custom_price_yen else pkg["price_yen"]

    return QuoteDetails(
        restaurant_name=business_name,
        package_key=package_key,
        package_label=pkg["label"],
        price_yen=price,
        scope_description=_SCOPE_DESCRIPTIONS.get(package_key, ""),
        revision_limit=DEFAULT_REVISION_LIMIT,
        delivery_terms=_DELIVERY_TERMS.get(package_key, ""),
        update_terms=_UPDATE_TERMS.get(package_key, ""),
        payment_instructions=(
            "お振込先はお見積り送信時にお知らせいたします。\n"
            "お振込確認後、制作を開始いたします。"
        ),
        expiry_date=expiry.strftime("%Y-%m-%d"),
        quote_date=now.strftime("%Y-%m-%d"),
        is_custom=is_custom,
        custom_reason=custom_reason,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Order creation and state management
# ---------------------------------------------------------------------------

def create_order(
    *,
    lead_id: str,
    business_name: str,
    package_key: str,
    is_custom: bool = False,
    custom_price_yen: int | None = None,
    custom_reason: str = "",
) -> Order:
    """Create a new order from a lead with an initial quote."""
    now = datetime.now(timezone.utc).isoformat()
    pkg = PACKAGE_REGISTRY.get(package_key)
    if not pkg:
        raise ValueError(f"Unknown package key: {package_key}")

    # Generate order ID
    raw = f"{lead_id}:{package_key}:{now}"
    short_hash = hashlib.sha256(raw.encode()).hexdigest()[:8]
    order_id = f"ord-{short_hash}"

    quote = generate_quote(
        business_name=business_name,
        package_key=package_key,
        is_custom=is_custom,
        custom_price_yen=custom_price_yen,
        custom_reason=custom_reason,
    )

    return Order(
        order_id=order_id,
        lead_id=lead_id,
        business_name=business_name,
        package_key=package_key,
        state=ORDER_STATE_QUOTED,
        quote=quote,
        payment=PaymentDetails(
            method="",
            status="pending",
            amount_yen=quote.price_yen,
        ),
        intake=IntakeChecklist(),
        approval=OwnerApproval(),
        revisions=RevisionRecord(limit=DEFAULT_REVISION_LIMIT),
        created_at=now,
        updated_at=now,
        state_history=[{
            "state": ORDER_STATE_QUOTED,
            "timestamp": now,
        }],
        custom_quote_triggers=[custom_reason] if is_custom and custom_reason else [],
    )


def transition_order(order: Order, *, target_state: str, note: str = "") -> Order:
    """Transition an order to a new state if valid."""
    if not can_transition(order.state, target_state):
        raise ValueError(
            f"Cannot transition from '{order.state}' to '{target_state}'. "
            f"Valid transitions: {_VALID_TRANSITIONS.get(order.state, set())}"
        )

    now = datetime.now(timezone.utc).isoformat()
    order.state = target_state
    order.updated_at = now
    order.state_history.append({
        "state": target_state,
        "timestamp": now,
        "note": note,
    })
    return order


# ---------------------------------------------------------------------------
# Production approval blocking
# ---------------------------------------------------------------------------

def can_approve_production(order: Order) -> tuple[bool, list[str]]:
    """Check if an order can be approved for production.

    Returns (can_approve, blocking_reasons).
    """
    blockers: list[str] = []

    if order.state in ORDER_STATES_BEFORE_PRODUCTION:
        blockers.append(f"Order state is '{order.state}' — must reach 'in_production' first")

    if not order.payment or order.payment.status != "confirmed":
        blockers.append("Payment has not been confirmed")

    if not order.intake or not order.intake.is_complete():
        blockers.append("Intake checklist is not complete")

    return len(blockers) == 0, blockers


def can_approve_package(order: Order) -> tuple[bool, list[str]]:
    """Check if a package can be approved for delivery.

    Returns (can_approve, blocking_reasons).
    """
    blockers: list[str] = []

    if order.state != ORDER_STATE_OWNER_REVIEW:
        blockers.append(f"Order must be in 'owner_review' state, currently '{order.state}'")

    if not order.approval or not order.approval.approved:
        blockers.append("Owner has not approved the output")

    if not order.payment or order.payment.status != "confirmed":
        blockers.append("Payment has not been confirmed")

    return len(blockers) == 0, blockers


# ---------------------------------------------------------------------------
# Custom-quote detection
# ---------------------------------------------------------------------------

def check_custom_quote_triggers(
    *,
    menu_item_count: int = 0,
    section_count: int = 0,
    separate_menus: int = 1,
    print_copies: int = 1,
    expected_updates: str = "none",
) -> list[str]:
    """Check if a package needs custom quoting based on scope.

    Returns a list of trigger reasons (empty means standard pricing applies).
    """
    triggers: list[str] = []

    if menu_item_count > 40 or section_count > 4:
        triggers.append(CUSTOM_QUOTE_TRIGGERS["large_menu"])
    if separate_menus > 1:
        triggers.append(CUSTOM_QUOTE_TRIGGERS["multiple_sets"])
    if print_copies > 3:
        triggers.append(CUSTOM_QUOTE_TRIGGERS["extra_copies"])
    if expected_updates not in ("none", "rare"):
        triggers.append(CUSTOM_QUOTE_TRIGGERS["frequent_updates"])

    return triggers
