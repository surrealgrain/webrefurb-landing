from __future__ import annotations

import json

from pipeline.constants import PACKAGE_1_KEY, PACKAGE_2_KEY
from pipeline.quote import (
    can_approve_package,
    check_custom_quote_triggers,
    create_order,
    render_quote_markdown,
    write_order_artifacts,
)


def test_quote_includes_paid_ops_scope_terms_and_privacy_note(tmp_path):
    order = create_order(
        lead_id="wrm-hinode",
        business_name="Hinode Ramen",
        package_key=PACKAGE_2_KEY,
    )

    quote = order.quote
    assert quote is not None
    assert quote.price_yen == 45000
    assert quote.payment_terms == "Full payment upfront before production starts."
    assert quote.operator_cost_assumptions["print_cost_estimate_yen"] == 3000
    assert "Owner-uploaded menu photos" in quote.privacy_data_retention_note

    paths = write_order_artifacts(state_root=tmp_path, order=order)
    quote_text = render_quote_markdown(order)
    invoice = json.loads((tmp_path / "orders" / "artifacts" / order.order_id / "invoice.json").read_text())

    assert "Quote: Hinode Ramen" in quote_text
    assert paths["quote_markdown"].endswith("quote.md")
    assert invoice["restaurant_name"] == "Hinode Ramen"
    assert invoice["amount_yen"] == 45000


def test_package_approval_requires_payment_intake_owner_checksums_and_privacy_note():
    order = create_order(
        lead_id="wrm-hinode",
        business_name="Hinode Ramen",
        package_key=PACKAGE_1_KEY,
    )

    ok, blockers = can_approve_package(order)
    assert ok is False
    assert "Owner has not approved the output" in blockers
    assert "Payment has not been confirmed" in blockers
    assert "Privacy/data retention note has not been accepted" in blockers

    order.state = "owner_approved"
    order.payment.status = "confirmed"
    order.approval.approved = True
    order.approval.approver_name = "Tanaka"
    order.approval.approved_package = PACKAGE_1_KEY
    order.approval.source_data_checksum = "source123"
    order.approval.artifact_checksum = "artifact123"
    order.privacy_note_accepted = True

    ok, blockers = can_approve_package(order)
    assert ok is True
    assert blockers == []


def test_custom_quote_triggers_cover_large_izakaya_print_and_update_cases():
    triggers = check_custom_quote_triggers(
        menu_item_count=80,
        section_count=7,
        separate_menus=3,
        print_copies=8,
        print_size="A3",
        expected_updates="monthly",
    )

    assert "Menu exceeds 40 items or 4 sections" in triggers
    assert "Separate food, drink, course, or seasonal menus needed" in triggers
    assert "Non-standard sizes (larger than A4/Letter)" in triggers
    assert "More than 3 printed copies" in triggers
    assert "Expected seasonal or monthly menu changes" in triggers
