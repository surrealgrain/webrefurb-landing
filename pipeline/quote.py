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
    PAYMENT_TERMS_DESCRIPTION,
    OWNER_UPLOAD_PRIVACY_NOTE,
    INVOICE_REGISTRATION_NUMBER,
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
        "English Ordering Files: menu structure, ordering copy, and print-ready "
        "PDF/image files delivered online. Includes a ticket-machine guide when applicable. "
        "Owner approval is required before final delivery; prices, ingredients, and allergens "
        "are only shown when confirmed by the restaurant."
    ),
    "package_2_printed_delivered_45k": (
        "Counter-Ready Ordering Kit: everything in English Ordering Files, plus "
        "professional printing, lamination, and courier delivery to your restaurant. "
        "Materials are prepared to match the current menu and order flow after owner approval."
    ),
    "package_3_qr_menu_65k": (
        "Live QR English Menu: hosted English ordering menu accessible by QR code. "
        "Includes QR code generation, printable QR sign, 12-month hosting, one bundled "
        "update round in the first 30 days, and owner confirmation before publish."
    ),
}

_DELIVERY_TERMS = {
    "package_1_remote_30k": "Print-ready ordering files delivered by email or download link within 5 business days of intake completion and owner approval.",
    "package_2_printed_delivered_45k": "Printed and laminated ordering materials delivered by domestic courier within 7 business days of intake completion and owner approval.",
    "package_3_qr_menu_65k": "QR ordering menu published within 5 business days of intake completion and owner approval. QR sign PDF delivered with Package 2 if bundled, or by email.",
}

_UPDATE_TERMS = {
    "package_1_remote_30k": "One correction window is included after owner review. Menu changes after approval are quoted separately.",
    "package_2_printed_delivered_45k": "One correction window is included before print approval. Reprints after approval are quoted separately.",
    "package_3_qr_menu_65k": "One bundled update round is included within 30 days of publish. Later updates are quoted separately.",
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
    cost_assumptions: dict[str, Any] = {}
    if package_key == "package_2_printed_delivered_45k":
        cost_assumptions = {
            "print_cost_estimate_yen": PACKAGE_2_PRINT_COST_ESTIMATE_YEN,
            "delivery_cost_estimate_yen": PACKAGE_2_DELIVERY_COST_ESTIMATE_YEN,
        }

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
        payment_terms=PAYMENT_TERMS_DESCRIPTION,
        expiry_date=expiry.strftime("%Y-%m-%d"),
        quote_date=now.strftime("%Y-%m-%d"),
        privacy_data_retention_note=OWNER_UPLOAD_PRIVACY_NOTE,
        is_custom=is_custom,
        custom_reason=custom_reason,
        notes=notes,
        operator_cost_assumptions=cost_assumptions,
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


def order_from_dict(data: dict[str, Any]) -> Order:
    """Rehydrate an order dict for validation helpers."""
    quote_data = data.get("quote") or {}
    payment_data = data.get("payment") or {}
    intake_data = data.get("intake") or {}
    approval_data = data.get("approval") or {}
    revisions_data = data.get("revisions") or {}
    return Order(
        order_id=str(data.get("order_id") or ""),
        lead_id=str(data.get("lead_id") or ""),
        business_name=str(data.get("business_name") or ""),
        package_key=str(data.get("package_key") or ""),
        state=str(data.get("state") or ORDER_STATE_QUOTED),
        quote=QuoteDetails(**quote_data) if quote_data else None,
        payment=PaymentDetails(**payment_data) if payment_data else None,
        intake=IntakeChecklist(
            full_menu_photos=bool(intake_data.get("full_menu_photos")),
            ticket_machine_photos=bool(intake_data.get("ticket_machine_photos")),
            price_confirmation=bool(intake_data.get("price_confirmation")),
            dietary_ingredient_notes=bool(intake_data.get("dietary_ingredient_notes")),
            delivery_details=bool(intake_data.get("delivery_details")),
            business_contact_confirmed=bool(intake_data.get("business_contact_confirmed")),
            notes=str(intake_data.get("notes") or ""),
        ) if intake_data else None,
        approval=OwnerApproval(
            approved=bool(approval_data.get("approved")),
            approver_name=str(approval_data.get("approver_name") or ""),
            approved_package=str(approval_data.get("approved_package") or ""),
            approved_at=approval_data.get("approved_at"),
            source_data_checksum=str(approval_data.get("source_data_checksum") or ""),
            artifact_checksum=str(approval_data.get("artifact_checksum") or ""),
            notes=str(approval_data.get("notes") or ""),
        ) if approval_data else None,
        revisions=RevisionRecord(
            current_round=int(revisions_data.get("current_round") or 0),
            limit=int(revisions_data.get("limit") or DEFAULT_REVISION_LIMIT),
            history=list(revisions_data.get("history") or []),
        ) if revisions_data else None,
        delivery_tracking=str(data.get("delivery_tracking") or ""),
        created_at=str(data.get("created_at") or ""),
        updated_at=str(data.get("updated_at") or ""),
        state_history=list(data.get("state_history") or []),
        privacy_note_accepted=bool(data.get("privacy_note_accepted")),
        custom_quote_triggers=list(data.get("custom_quote_triggers") or []),
        artifact_paths=dict(data.get("artifact_paths") or {}),
    )


def invoice_ready_data(order: Order) -> dict[str, Any]:
    """Generate invoice-ready data for manual invoicing/accounting."""
    quote = order.quote
    payment = order.payment
    return {
        "invoice_number": payment.invoice_number if payment else "",
        "invoice_registration_number": (payment.invoice_registration_number if payment else "") or INVOICE_REGISTRATION_NUMBER,
        "restaurant_name": order.business_name,
        "order_id": order.order_id,
        "lead_id": order.lead_id,
        "package_key": order.package_key,
        "package_label": quote.package_label if quote else "",
        "amount_yen": quote.price_yen if quote else 0,
        "payment_terms": quote.payment_terms if quote else PAYMENT_TERMS_DESCRIPTION,
        "payment_method": payment.method if payment else "",
        "payment_status": payment.status if payment else "pending",
        "payment_reference": payment.reference if payment else "",
        "paid_at": payment.paid_at if payment else None,
        "quote_date": quote.quote_date if quote else "",
        "expiry_date": quote.expiry_date if quote else "",
    }


def render_quote_markdown(order: Order) -> str:
    """Render an operator-inspectable quote artifact."""
    if not order.quote:
        raise ValueError("Order has no quote")
    quote = order.quote
    lines = [
        f"# Quote: {quote.restaurant_name}",
        "",
        f"- Order ID: {order.order_id}",
        f"- Package: {quote.package_label} ({quote.package_key})",
        f"- Price: JPY {quote.price_yen:,}",
        f"- Quote date: {quote.quote_date}",
        f"- Expires: {quote.expiry_date}",
        f"- Payment terms: {quote.payment_terms}",
        f"- Revision limit: {quote.revision_limit} rounds",
        "",
        "## Scope",
        quote.scope_description,
        "",
        "## Delivery",
        quote.delivery_terms,
        "",
        "## Updates",
        quote.update_terms,
        "",
        "## Payment Instructions",
        quote.payment_instructions,
        "",
        "## Data Retention",
        quote.privacy_data_retention_note,
    ]
    if quote.is_custom:
        lines.extend(["", "## Custom Quote Reason", quote.custom_reason])
    if quote.operator_cost_assumptions:
        lines.extend(["", "## Operator Cost Assumptions"])
        for key, value in quote.operator_cost_assumptions.items():
            lines.append(f"- {key}: JPY {int(value):,}")
    return "\n".join(lines) + "\n"


def write_order_artifacts(*, state_root: Any, order: Order) -> dict[str, str]:
    """Write quote and invoice-ready artifacts under state/orders/artifacts."""
    from pathlib import Path
    from .utils import write_json, write_text

    artifacts_dir = Path(state_root) / "orders" / "artifacts" / order.order_id
    quote_path = artifacts_dir / "quote.md"
    invoice_path = artifacts_dir / "invoice.json"
    write_text(quote_path, render_quote_markdown(order))
    write_json(invoice_path, invoice_ready_data(order))
    return {
        "quote_markdown": str(quote_path),
        "invoice_json": str(invoice_path),
    }


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

    if order.state not in {ORDER_STATE_OWNER_REVIEW, ORDER_STATE_OWNER_APPROVED}:
        blockers.append(f"Order must be in owner review/approval state, currently '{order.state}'")

    if not order.approval or not order.approval.approved:
        blockers.append("Owner has not approved the output")
    elif not all([
        order.approval.approver_name,
        order.approval.approved_package,
        order.approval.source_data_checksum,
        order.approval.artifact_checksum,
    ]):
        blockers.append("Owner approval record is incomplete")

    if not order.payment or order.payment.status != "confirmed":
        blockers.append("Payment has not been confirmed")

    if not order.privacy_note_accepted:
        blockers.append("Privacy/data retention note has not been accepted")

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
    print_size: str = "standard",
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
    if print_size.lower() in {"oversized", "b4", "a3", "non_standard", "non-standard"}:
        triggers.append(CUSTOM_QUOTE_TRIGGERS["oversized_print"])
    if print_copies > 3:
        triggers.append(CUSTOM_QUOTE_TRIGGERS["extra_copies"])
    if expected_updates not in ("none", "rare"):
        triggers.append(CUSTOM_QUOTE_TRIGGERS["frequent_updates"])

    return triggers
