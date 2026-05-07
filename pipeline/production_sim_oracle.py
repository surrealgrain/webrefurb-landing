from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .constants import (
    PACKAGE_1_KEY,
    PACKAGE_2_KEY,
    PACKAGE_3_KEY,
    TARGET_CATEGORIES,
)
from .evidence import has_chain_or_franchise_infrastructure, is_chain_business
from .lead_dossier import (
    READINESS_DISQUALIFIED,
    READINESS_MANUAL,
    READINESS_READY,
    record_explicitly_not_japan,
)
from .record import get_primary_contact


PRIORITIES = ("P0", "P1", "P2")
PACKAGE_KEYS = {PACKAGE_1_KEY, PACKAGE_2_KEY, PACKAGE_3_KEY, "custom_quote", "none"}
READINESS_STATES = {READINESS_READY, READINESS_MANUAL, READINESS_DISQUALIFIED}
PROOF_STRENGTH_RANK = {"none": 0, "operator_only": 1, "gold": 2}

FORBIDDEN_CUSTOMER_TERMS = (
    " ai ",
    "artificial intelligence",
    "automation",
    "automated",
    "scraping",
    "scraped",
    "internal tool",
    "llm",
    "gpt",
)
PRICE_CLAIM_RE = re.compile(r"(?:¥|JPY\s*)(?:30,?000|45,?000|65,?000)|(?:30,?000|45,?000|65,?000)\s*円", re.I)
UNVERIFIED_ALLERGEN_TERMS = ("allergen", "allergy", "allergies", "アレルギ")


@dataclass(frozen=True)
class ProductionGoalContract:
    market: str = "Japan"
    categories: tuple[str, ...] = TARGET_CATEGORIES
    package_keys: tuple[str, ...] = (PACKAGE_1_KEY, PACKAGE_2_KEY, PACKAGE_3_KEY)
    readiness_states: tuple[str, ...] = (READINESS_READY, READINESS_MANUAL, READINESS_DISQUALIFIED)
    broad_candidate_minimum: int = 300
    broad_label_minimum: int = 100
    expected_ready_minimum: int = 20
    positive_profile_minimum: int = 10
    required_positive_profiles: tuple[str, ...] = (
        "ramen_ticket_machine",
        "ramen_meal_ticket",
        "simple_ramen_without_ticket_machine",
        "ramen_menu_photo_or_official_menu",
        "izakaya_nomihodai_or_course",
        "izakaya_oshinagaki_or_printed_menu",
        "izakaya_menu_photo_or_official_menu",
    )
    required_screenshot_states: tuple[str, ...] = (
        "dashboard_overview",
        "ready_lead_card",
        "manual_review_card",
        "disqualified_card",
        "outreach_editor",
        "inline_menu_sample",
    )


@dataclass
class FindingBuilder:
    findings: list[dict[str, Any]] = field(default_factory=list)

    def add(
        self,
        *,
        priority: str,
        code: str,
        lead_id: str,
        business_name: str,
        expected: Any,
        actual: Any,
        fix_hint: str,
        evidence: list[str] | None = None,
        disposition: str | None = None,
    ) -> None:
        if priority not in PRIORITIES:
            raise ValueError(f"invalid priority: {priority}")
        self.findings.append({
            "id": "",
            "priority": priority,
            "code": code,
            "lead_id": lead_id,
            "business_name": business_name,
            "expected": expected,
            "actual": actual,
            "evidence": evidence or [],
            "fix_hint": fix_hint,
            "disposition": disposition or ("blocker" if priority in {"P0", "P1"} else "observation"),
        })


def evaluate_simulation(
    *,
    records: list[dict[str, Any]],
    labels: dict[str, dict[str, Any]],
    mock_payloads: list[dict[str, Any]] | None = None,
    screenshots: list[dict[str, Any]] | None = None,
    contract: ProductionGoalContract | None = None,
) -> dict[str, Any]:
    """Compare observed replay decisions to labels and return schema counts."""
    contract = contract or ProductionGoalContract()
    payload_by_lead = {str(payload.get("lead_id") or ""): payload for payload in mock_payloads or []}
    builder = FindingBuilder()
    decisions: list[dict[str, Any]] = []
    strict_labels = {
        candidate_id: label
        for candidate_id, label in labels.items()
        if _label_is_strict(label)
    }

    for record in records:
        candidate_id = str(record.get("production_sim_candidate_id") or record.get("lead_id") or "")
        label = labels[candidate_id]
        payload = payload_by_lead.get(str(record.get("lead_id") or ""))
        decisions.append(_decision_summary(record=record, label=label, payload=payload))
        if candidate_id in strict_labels:
            _evaluate_candidate(record=record, label=label, payload=payload, builder=builder)

    _evaluate_screenshot_coverage(
        screenshots=screenshots or [],
        labels=strict_labels,
        records=records,
        builder=builder,
        contract=contract,
    )
    _evaluate_label_review_gate(labels=labels, strict_labels=strict_labels, builder=builder)
    _evaluate_broad_corpus_gate(records=records, labels=strict_labels, builder=builder, contract=contract)
    _evaluate_positive_profile_coverage_gate(labels=strict_labels, builder=builder, contract=contract)

    findings = _number_findings(builder.findings)
    p0 = sum(1 for item in findings if item["priority"] == "P0")
    p1 = sum(1 for item in findings if item["priority"] == "P1")
    p2 = sum(1 for item in findings if item["priority"] == "P2")
    deferred = [item for item in findings if item.get("disposition") == "deferred"]

    return {
        "production_ready": p0 == 0 and p1 == 0 and not deferred,
        "p0": p0,
        "p1": p1,
        "p2": p2,
        "candidate_count": len(records),
        "labeled_count": len(labels),
        "strict_labeled_count": len(strict_labels),
        "diagnostic_labeled_count": len(labels) - len(strict_labels),
        "ready_count": sum(1 for item in decisions if item["actual_readiness"] == READINESS_READY),
        "manual_review_count": sum(1 for item in decisions if item["actual_readiness"] == READINESS_MANUAL),
        "disqualified_count": sum(1 for item in decisions if item["actual_readiness"] == READINESS_DISQUALIFIED),
        "mock_sends_verified": len(mock_payloads or []),
        "screenshots": screenshots or [],
        "findings": findings,
        "next_required_fixes": _next_required_fixes(findings),
        "decisions": decisions,
    }


def _evaluate_candidate(
    *,
    record: dict[str, Any],
    label: dict[str, Any],
    payload: dict[str, Any] | None,
    builder: FindingBuilder,
) -> None:
    lead_id = str(record.get("lead_id") or label["candidate_id"])
    business_name = str(record.get("business_name") or label.get("business_name") or "")
    expected_readiness = str(label["readiness_expected"])
    actual_readiness = str(record.get("launch_readiness_status") or "")

    if record.get("lead") not in {True, False}:
        builder.add(
            priority="P0",
            code="LEAD-NOT-BINARY",
            lead_id=lead_id,
            business_name=business_name,
            expected="lead must be true or false",
            actual=record.get("lead"),
            fix_hint="Normalize replay/search records through create_lead_record or ensure_lead_dossier before reporting.",
        )

    if expected_readiness not in READINESS_STATES:
        builder.add(
            priority="P1",
            code="LABEL-READINESS-INVALID",
            lead_id=lead_id,
            business_name=business_name,
            expected=sorted(READINESS_STATES),
            actual=expected_readiness,
            fix_hint="Fix the fixture label readiness_expected value.",
        )
    elif actual_readiness != expected_readiness:
        builder.add(
            priority="P0" if expected_readiness != READINESS_READY and actual_readiness == READINESS_READY else "P1",
            code="READINESS-MISMATCH",
            lead_id=lead_id,
            business_name=business_name,
            expected=expected_readiness,
            actual=actual_readiness,
            fix_hint="Tune lead_dossier.assess_launch_readiness or the replay label so ready/manual/disqualified semantics match.",
        )

    if actual_readiness == READINESS_READY:
        _assert_ready_record_safe(record=record, label=label, builder=builder)

    if expected_readiness == READINESS_READY:
        _assert_ready_label_contract(record=record, label=label, payload=payload, builder=builder)
    elif payload is not None:
        builder.add(
            priority="P0",
            code="SEND-PAYLOAD-FOR-NON-READY",
            lead_id=lead_id,
            business_name=business_name,
            expected="no send payload for manual-review/disqualified candidates",
            actual=payload.get("recipient"),
            evidence=[str(payload.get("payload_path") or "")],
            fix_hint="Route mock send generation through the same launch_readiness_status gate used by dashboard api_send.",
        )


def _assert_ready_record_safe(*, record: dict[str, Any], label: dict[str, Any], builder: FindingBuilder) -> None:
    lead_id = str(record.get("lead_id") or "")
    business_name = str(record.get("business_name") or "")
    category = str(record.get("primary_category_v1") or "")

    unsafe_reasons: list[str] = []
    if category not in TARGET_CATEGORIES:
        unsafe_reasons.append("outside_v1_category")
    if record_explicitly_not_japan(record):
        unsafe_reasons.append("not_in_japan")
    if is_chain_business(business_name) or has_chain_or_franchise_infrastructure(_record_text(record), business_name=business_name):
        unsafe_reasons.append("chain_or_franchise_like_business")
    if str(record.get("english_menu_state") or "") == "usable_complete":
        unsafe_reasons.append("already_has_usable_english_solution")
    if _record_has_multilingual_solution(record):
        unsafe_reasons.append("multilingual_qr_or_ordering_solution_present")

    if unsafe_reasons:
        builder.add(
            priority="P0",
            code="UNSAFE-READY-LEAD",
            lead_id=lead_id,
            business_name=business_name,
            expected="ready lead must satisfy Japan/category/independence/unsolved gates",
            actual=unsafe_reasons,
            fix_hint="Harden qualification or lead_dossier disqualification rules so unsafe records cannot remain ready_for_outreach.",
        )


def _assert_ready_label_contract(
    *,
    record: dict[str, Any],
    label: dict[str, Any],
    payload: dict[str, Any] | None,
    builder: FindingBuilder,
) -> None:
    lead_id = str(record.get("lead_id") or "")
    business_name = str(record.get("business_name") or "")

    _compare_package(record=record, label=label, builder=builder)
    _compare_contact(record=record, label=label, builder=builder)
    _compare_assets(record=record, label=label, builder=builder)
    _compare_dossier_states(record=record, label=label, builder=builder)
    _compare_proof_strength(record=record, label=label, builder=builder)
    _assert_customer_copy_safe(record=record, payload=payload, label=label, builder=builder)

    if str(label["contact_route_expected"]) != "email":
        if payload is not None:
            builder.add(
                priority="P0",
                code="SEND-PAYLOAD-FOR-NON-EMAIL-ROUTE",
                lead_id=lead_id,
                business_name=business_name,
                expected="no email payload for non-email ready route",
                actual=payload.get("recipient"),
                evidence=[str(payload.get("payload_path") or "")],
                fix_hint="Generate mock email payloads only for expected-ready email labels; verify other routes through dashboard blocking/route metadata.",
            )
        return

    if payload is None:
        builder.add(
            priority="P1",
            code="MOCK-SEND-MISSING",
            lead_id=lead_id,
            business_name=business_name,
            expected="mock send payload captured for expected-ready email lead",
            actual="missing",
            fix_hint="Build the mock email payload after outreach generation and before report writing.",
        )
        return

    expected_recipient = _expected_recipient(record=record, label=label)
    if payload.get("recipient") != expected_recipient:
        builder.add(
            priority="P0",
            code="MOCK-SEND-WRONG-RECIPIENT",
            lead_id=lead_id,
            business_name=business_name,
            expected=expected_recipient,
            actual=payload.get("recipient"),
            evidence=[str(payload.get("payload_path") or "")],
            fix_hint="Use get_primary_contact/get_primary_email_contact from the persisted lead record at send time.",
        )

    expected_cids = _expected_cids(label)
    actual_cids = sorted(set(payload.get("cid_references") or []))
    missing_cids = sorted(set(expected_cids) - set(actual_cids))
    if missing_cids:
        builder.add(
            priority="P0",
            code="MOCK-SEND-MISSING-CID",
            lead_id=lead_id,
            business_name=business_name,
            expected=expected_cids,
            actual=actual_cids,
            evidence=[str(payload.get("payload_path") or "")],
            fix_hint="Align outreach include_menu_image/include_machine_image with selected lead profile assets.",
        )

    file_attachments = payload.get("file_attachments") or []
    if file_attachments:
        builder.add(
            priority="P0",
            code="COLD-EMAIL-FILE-ATTACHMENT",
            lead_id=lead_id,
            business_name=business_name,
            expected="cold email uses inline CID images only",
            actual=file_attachments,
            evidence=[str(payload.get("payload_path") or "")],
            fix_hint="Keep PDFs and other files out of cold email payloads; only CID inline images are allowed.",
        )


def _compare_package(*, record: dict[str, Any], label: dict[str, Any], builder: FindingBuilder) -> None:
    expected = str(label["package_expected"])
    actual = str(record.get("recommended_primary_package") or "none")
    if expected not in PACKAGE_KEYS:
        priority = "P1"
        code = "LABEL-PACKAGE-INVALID"
        hint = "Fix the fixture label package_expected to one of the supported package keys."
    elif actual != expected:
        priority = "P0"
        code = "PACKAGE-MISMATCH"
        hint = "Tune scoring.recommend_package_details or qualification evidence states for this package branch."
    else:
        return
    builder.add(
        priority=priority,
        code=code,
        lead_id=str(record.get("lead_id") or ""),
        business_name=str(record.get("business_name") or ""),
        expected=expected,
        actual=actual,
        fix_hint=hint,
    )


def _compare_contact(*, record: dict[str, Any], label: dict[str, Any], builder: FindingBuilder) -> None:
    expected = str(label["contact_route_expected"])
    primary = get_primary_contact(record)
    actual = str((primary or {}).get("type") or "none")
    if expected != actual:
        builder.add(
            priority="P0",
            code="CONTACT-ROUTE-MISMATCH",
            lead_id=str(record.get("lead_id") or ""),
            business_name=str(record.get("business_name") or ""),
            expected=expected,
            actual=actual,
            fix_hint="Normalize contact extraction and primary-route ranking before allowing send payload creation.",
        )


def _compare_assets(*, record: dict[str, Any], label: dict[str, Any], builder: FindingBuilder) -> None:
    expected = [] if str(label.get("contact_route_expected") or "") == "contact_form" else sorted(str(item) for item in label.get("inline_assets_expected") or [])
    actual = _logical_inline_asset_names_for_record(record)
    if expected != actual:
        builder.add(
            priority="P0",
            code="INLINE-ASSET-MISMATCH",
            lead_id=str(record.get("lead_id") or ""),
            business_name=str(record.get("business_name") or ""),
            expected=expected,
            actual=actual,
            evidence=[str(path) for path in record.get("outreach_assets_selected") or []],
            fix_hint="Update outreach include_menu_image/include_machine_image selection so inline previews match the lead profile.",
        )


def _compare_dossier_states(*, record: dict[str, Any], label: dict[str, Any], builder: FindingBuilder) -> None:
    checks = (
        ("ticket_machine_state_expected", "ticket_machine_state", "DOSSIER-TICKET-MACHINE-MISMATCH"),
        ("english_menu_state_expected", "english_menu_state", "DOSSIER-ENGLISH-MENU-MISMATCH"),
    )
    for label_key, record_key, code in checks:
        expected = str(label[label_key])
        actual = str(record.get(record_key) or (record.get("lead_evidence_dossier") or {}).get(record_key) or "")
        if expected != actual:
            builder.add(
                priority="P1",
                code=code,
                lead_id=str(record.get("lead_id") or ""),
                business_name=str(record.get("business_name") or ""),
                expected=expected,
                actual=actual,
                fix_hint="Persist dossier state from lead_dossier.ensure_lead_dossier before report/dashboard rendering.",
            )


def _compare_proof_strength(*, record: dict[str, Any], label: dict[str, Any], builder: FindingBuilder) -> None:
    expected_minimum = str(label.get("proof_strength_minimum") or "none")
    actual = str((record.get("lead_evidence_dossier") or {}).get("proof_strength") or "none")
    if PROOF_STRENGTH_RANK.get(actual, 0) < PROOF_STRENGTH_RANK.get(expected_minimum, 0):
        builder.add(
            priority="P0",
            code="PROOF-STRENGTH-BELOW-LABEL",
            lead_id=str(record.get("lead_id") or ""),
            business_name=str(record.get("business_name") or ""),
            expected=f">={expected_minimum}",
            actual=actual,
            fix_hint="Attach a customer-preview-eligible proof item or demote the lead to manual_review.",
        )


def _assert_customer_copy_safe(
    *,
    record: dict[str, Any],
    payload: dict[str, Any] | None,
    label: dict[str, Any],
    builder: FindingBuilder,
) -> None:
    text = "\n".join([
        str(record.get("outreach_draft_subject") or ""),
        str(record.get("outreach_draft_body") or ""),
        str(record.get("outreach_draft_english_body") or ""),
        str((payload or {}).get("subject") or ""),
        str((payload or {}).get("text_body") or ""),
        str((payload or {}).get("html_body") or ""),
    ])
    normalized = f" {text.lower()} "
    forbidden = [term.strip() for term in FORBIDDEN_CUSTOMER_TERMS if term in normalized]
    if forbidden:
        builder.add(
            priority="P0",
            code="FORBIDDEN-CUSTOMER-COPY",
            lead_id=str(record.get("lead_id") or ""),
            business_name=str(record.get("business_name") or ""),
            expected="no AI/automation/scraping/internal-tool wording",
            actual=forbidden,
            evidence=[str((payload or {}).get("payload_path") or "")],
            fix_hint="Remove internal process wording from pipeline.outreach customer-facing templates.",
        )
    if PRICE_CLAIM_RE.search(text):
        builder.add(
            priority="P0",
            code="UNVERIFIED-PRICE-CLAIM",
            lead_id=str(record.get("lead_id") or ""),
            business_name=str(record.get("business_name") or ""),
            expected="cold outreach does not assert package/source prices",
            actual="price text found",
            evidence=[str((payload or {}).get("payload_path") or "")],
            fix_hint="Keep prices out of first cold outreach and show package fit in the operator dashboard instead.",
        )
    if any(term in normalized for term in UNVERIFIED_ALLERGEN_TERMS):
        builder.add(
            priority="P0",
            code="UNVERIFIED-ALLERGEN-CLAIM",
            lead_id=str(record.get("lead_id") or ""),
            business_name=str(record.get("business_name") or ""),
            expected="no allergen claims before restaurant confirmation",
            actual="allergen/allergy wording found",
            evidence=[str((payload or {}).get("payload_path") or "")],
            fix_hint="Replace allergen claims in outreach with owner-confirmation language or remove them from cold copy.",
        )


def _evaluate_screenshot_coverage(
    *,
    screenshots: list[dict[str, Any]],
    labels: dict[str, dict[str, Any]],
    records: list[dict[str, Any]],
    builder: FindingBuilder,
    contract: ProductionGoalContract,
) -> None:
    if not labels:
        return
    states = {str(item.get("ui_state") or "") for item in screenshots}
    required = set(contract.required_screenshot_states)
    expected_ready_labels = [label for label in labels.values() if label["readiness_expected"] == READINESS_READY]
    if any("ticket_machine_guide" in label.get("inline_assets_expected", []) for label in expected_ready_labels):
        required.add("inline_ticket_machine_sample")
    if any("izakaya_food_drinks" in label.get("inline_assets_expected", []) for label in expected_ready_labels):
        required.add("inline_izakaya_sample")

    missing = sorted(required - states)
    if missing:
        builder.add(
            priority="P1",
            code="DASHBOARD-SCREENSHOTS-MISSING",
            lead_id="",
            business_name="",
            expected=sorted(required),
            actual=sorted(states),
            fix_hint="Run production-sim replay with --screenshots and capture each required operator state.",
            evidence=[str(item.get("path") or "") for item in screenshots],
        )


def _evaluate_broad_corpus_gate(
    *,
    records: list[dict[str, Any]],
    labels: dict[str, dict[str, Any]],
    builder: FindingBuilder,
    contract: ProductionGoalContract,
) -> None:
    if len(records) >= contract.broad_candidate_minimum and len(labels) >= contract.broad_label_minimum:
        return
    builder.add(
        priority="P2",
        code="BROAD-CORPUS-DEFERRED",
        lead_id="",
        business_name="",
        expected={
            "candidate_minimum": contract.broad_candidate_minimum,
            "label_minimum": contract.broad_label_minimum,
        },
        actual={"candidates": len(records), "labels": len(labels)},
        fix_hint="Expand from the first-slice fixture to the stratified pilot and broad replay corpus before claiming production readiness.",
        disposition="deferred",
    )


def _evaluate_positive_profile_coverage_gate(
    *,
    labels: dict[str, dict[str, Any]],
    builder: FindingBuilder,
    contract: ProductionGoalContract,
) -> None:
    if len(labels) < contract.broad_candidate_minimum:
        return

    ready_labels = [label for label in labels.values() if label["readiness_expected"] == READINESS_READY]
    profile_counts = {profile: 0 for profile in contract.required_positive_profiles}
    for label in ready_labels:
        for profile in _positive_profiles_for_label(label):
            if profile in profile_counts:
                profile_counts[profile] += 1

    missing_profiles = {
        profile: count
        for profile, count in profile_counts.items()
        if count < contract.positive_profile_minimum
    }
    if len(ready_labels) >= contract.expected_ready_minimum and not missing_profiles:
        return

    builder.add(
        priority="P2",
        code="EXPECTED-READY-PROFILE-COVERAGE-DEFERRED",
        lead_id="",
        business_name="",
        expected={
            "expected_ready_minimum": contract.expected_ready_minimum,
            "positive_profile_minimum": contract.positive_profile_minimum,
            "required_positive_profiles": list(contract.required_positive_profiles),
        },
        actual={
            "expected_ready_labels": len(ready_labels),
            "positive_profile_counts": profile_counts,
            "missing_or_short_profiles": missing_profiles,
        },
        fix_hint="Expand expected-ready labels across ramen ticket-machine, meal-ticket, simple ramen, ramen menu, izakaya course/nomihodai, oshinagaki, and official/menu-photo profiles before claiming production readiness.",
        disposition="deferred",
    )


def _positive_profiles_for_label(label: dict[str, Any]) -> set[str]:
    if label["readiness_expected"] != READINESS_READY:
        return set()

    profiles: set[str] = set()
    category = str(label.get("category_expected") or "")
    package = str(label.get("package_expected") or "")
    ticket_state = str(label.get("ticket_machine_state_expected") or "")
    assets = set(str(item) for item in label.get("inline_assets_expected") or [])
    sample_strata = label.get("sample_strata") if isinstance(label.get("sample_strata"), dict) else {}
    search_job = str((sample_strata or {}).get("search_job") or "")
    evidence_profile = str((sample_strata or {}).get("evidence_profile") or "")
    profile_text = f"{search_job} {evidence_profile}".lower()

    if category == "ramen":
        if "ticket_machine_guide" in assets or ticket_state == "present" or "ramen_ticket_machine" in profile_text:
            profiles.add("ramen_ticket_machine")
        if "ramen_meal_ticket" in profile_text:
            profiles.add("ramen_meal_ticket")
        if "ticket_machine_guide" not in assets and ticket_state in {"absent", "unknown"} and package == PACKAGE_1_KEY:
            profiles.add("simple_ramen_without_ticket_machine")
        if "ramen_menu_photo" in profile_text or "ramen_official_menu" in profile_text or "menu_photo" in profile_text or "official_menu" in profile_text:
            profiles.add("ramen_menu_photo_or_official_menu")

    if category == "izakaya":
        if "nomihodai" in profile_text or "course" in profile_text or package == PACKAGE_3_KEY:
            profiles.add("izakaya_nomihodai_or_course")
        if "oshinagaki" in profile_text or package == PACKAGE_2_KEY:
            profiles.add("izakaya_oshinagaki_or_printed_menu")
        if "izakaya_menu_photo" in profile_text or "izakaya_official_menu" in profile_text or "menu_photo" in profile_text or "official_menu" in profile_text:
            profiles.add("izakaya_menu_photo_or_official_menu")

    return profiles


def _label_is_strict(label: dict[str, Any]) -> bool:
    if str(label.get("label_confidence") or "") == "high":
        return True
    review = label.get("second_pass_review") if isinstance(label.get("second_pass_review"), dict) else {}
    status = str((review or {}).get("status") or "").strip().lower()
    return status in {"approved", "complete", "completed"} or (review or {}).get("approved") is True


def _evaluate_label_review_gate(
    *,
    labels: dict[str, dict[str, Any]],
    strict_labels: dict[str, dict[str, Any]],
    builder: FindingBuilder,
) -> None:
    pending = len(labels) - len(strict_labels)
    if pending <= 0:
        return
    builder.add(
        priority="P2",
        code="LABEL-REVIEW-PENDING",
        lead_id="",
        business_name="",
        expected="low/medium-confidence diagnostic labels promoted by high confidence or approved second-pass review before hard pass/fail",
        actual={"diagnostic_labels": pending, "strict_labels": len(strict_labels)},
        fix_hint="Complete label review and promote only high-confidence or approved second-pass labels into the hard oracle set.",
        disposition="deferred",
    )


def _decision_summary(*, record: dict[str, Any], label: dict[str, Any], payload: dict[str, Any] | None) -> dict[str, Any]:
    primary = get_primary_contact(record)
    return {
        "candidate_id": str(record.get("production_sim_candidate_id") or record.get("lead_id") or ""),
        "lead_id": str(record.get("lead_id") or ""),
        "business_name": str(record.get("business_name") or ""),
        "expected_readiness": label["readiness_expected"],
        "actual_readiness": str(record.get("launch_readiness_status") or ""),
        "expected_package": label["package_expected"],
        "actual_package": str(record.get("recommended_primary_package") or "none"),
        "expected_contact_route": label["contact_route_expected"],
        "actual_contact_route": str((primary or {}).get("type") or "none"),
        "expected_inline_assets": label.get("inline_assets_expected") or [],
        "actual_inline_assets": _logical_inline_asset_names_for_record(record),
        "mock_payload": bool(payload),
        "readiness_reasons": list(record.get("launch_readiness_reasons") or []),
    }


def _logical_asset_names(paths: list[Any]) -> list[str]:
    result: list[str] = []
    for value in paths:
        name = str(value)
        if "ticket_machine_guide" in name:
            result.append("ticket_machine_guide")
        elif "izakaya_food_drinks_menu" in name:
            result.append("izakaya_food_drinks")
        elif "ramen_food_menu" in name:
            result.append("ramen_food_menu")
        elif name:
            result.append(name)
    return sorted(set(result))


def _logical_inline_asset_names_for_record(record: dict[str, Any]) -> list[str]:
    primary = get_primary_contact(record) or {}
    if str(primary.get("type") or "") == "contact_form":
        return []
    classification = str(record.get("outreach_classification") or "")
    profile = str(record.get("establishment_profile") or "")
    category = str(record.get("primary_category_v1") or record.get("category") or "")
    names: list[str] = []
    if classification != "machine_only":
        if profile.startswith("izakaya") or category == "izakaya":
            names.append("izakaya_food_drinks")
        elif profile.startswith("ramen") or category == "ramen":
            names.append("ramen_food_menu")
    if (
        classification in {"menu_and_machine", "machine_only"}
        or profile == "ramen_ticket_machine"
        or record.get("machine_evidence_found") is True
    ):
        names.append("ticket_machine_guide")
    return sorted(set(names))


def _expected_recipient(*, record: dict[str, Any], label: dict[str, Any]) -> str:
    primary = get_primary_contact(record)
    if str(label["contact_route_expected"]) == "email" and primary:
        return str(primary.get("value") or "").strip().lower()
    return ""


def _expected_cids(label: dict[str, Any]) -> list[str]:
    cids = {"webrefurb-logo"}
    assets = set(label.get("inline_assets_expected") or [])
    if {"ramen_food_menu", "izakaya_food_drinks"} & assets:
        cids.add("menu-preview")
    if "ticket_machine_guide" in assets:
        cids.add("machine-preview")
    return sorted(cids)


def _record_text(record: dict[str, Any]) -> str:
    return " ".join([
        str(record.get("business_name") or ""),
        str(record.get("website") or ""),
        str(record.get("source_query") or ""),
        " ".join(str(item) for item in record.get("evidence_snippets") or []),
        " ".join(str(item) for item in record.get("evidence_urls") or []),
    ])


def _record_has_multilingual_solution(record: dict[str, Any]) -> bool:
    text = _record_text(record).lower()
    return any(term in text for term in ("multilingual qr", "mobile order english", "多言語qr", "モバイルオーダー 英語"))


def _number_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counters: dict[tuple[str, str], int] = {}
    numbered: list[dict[str, Any]] = []
    for finding in findings:
        key = (finding["priority"], finding["code"])
        counters[key] = counters.get(key, 0) + 1
        item = dict(finding)
        item["id"] = f"{finding['priority']}-{finding['code']}-{counters[key]:03d}"
        numbered.append(item)
    return numbered


def _next_required_fixes(findings: list[dict[str, Any]]) -> list[str]:
    blockers = [item for item in findings if item["priority"] in {"P0", "P1"}]
    if blockers:
        return [str(item["fix_hint"]) for item in blockers]
    return [str(item["fix_hint"]) for item in findings if item.get("disposition") == "deferred"]
