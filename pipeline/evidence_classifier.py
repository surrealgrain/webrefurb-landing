"""Evidence-gated lead classifier and template selector.

Core principle: Do not choose templates by restaurant type alone.
Choose them based on verified lead attributes.  Every personalized
email claim must be backed by evidence strong enough to justify it.

Absence of evidence means "unknown," not "false."
Weak evidence must never trigger a highly specific template.
If uncertain, fall back to a safer template or skip the lead.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

RAMEN_TYPE_THRESHOLD = 0.75
IZAKAYA_TYPE_THRESHOLD = 0.75
TICKET_MACHINE_THRESHOLD = 0.85
TICKET_MACHINE_HUMAN_REVIEW_LOW = 0.70
TICKET_MACHINE_HUMAN_REVIEW_HIGH = 0.84
NOMIHODAI_THRESHOLD = 0.85
COURSE_THRESHOLD = 0.75
MENU_READABILITY_THRESHOLD = 0.70


# ---------------------------------------------------------------------------
# Allowed-value sets
# ---------------------------------------------------------------------------

RESTAURANT_TYPES = {"ramen", "izakaya", "other_japanese_restaurant", "unknown"}

MENU_SOURCE_TYPES = {
    "official_website", "official_social", "google_business_profile",
    "google_review_photo", "third_party_listing", "other", "none",
}

TICKET_MACHINE_EVIDENCE_TYPES = {
    "explicit_text", "clear_photo", "review_text", "official_listing",
    "third_party_listing", "multiple_medium_signals", "weak_or_ambiguous",
    "none",
}

ENGLISH_MENU_QUALITIES = {"none_found", "partial", "unclear", "comprehensive"}

CONTACT_CHANNELS = {"public_email", "official_contact_form", "none"}

VALID_MENU_TOPICS = {
    "ramen_types", "toppings", "set_items", "ordering_rules",
    "food_items", "drink_items", "course_items", "nomihodai",
    "last_order", "extra_charges", "ticket_machine_buttons", "purchase_steps",
}

VALID_TEMPLATES = {
    "ramen_visible_menu", "ramen_visible_menu_neutral_ordering",
    "ramen_menu_plus_ticket_machine", "ramen_ticket_machine_only",
    "ramen_needs_menu_photo", "ramen_needs_ticket_machine_photo",
    "izakaya_standard", "izakaya_food_drink_only",
    "izakaya_course_only", "izakaya_nomihodai_only",
    "izakaya_nomihodai_course", "izakaya_needs_menu_photo",
    "contact_form_public_menu", "contact_form_needs_menu_photo",
    "skip",
}


# ---------------------------------------------------------------------------
# Keywords for evidence detection
# ---------------------------------------------------------------------------

RAMEN_KEYWORDS = {"ラーメン", "ラーメン店", "ramen", "拉麺", "らーめん"}
IZAKAYA_KEYWORDS = {"居酒屋", "izakaya", "酒場", "バー"}

STRONG_TICKET_MACHINE_KEYWORDS = {
    "券売機", "食券", "食券機", "食券制", "食券を購入",
    "ticket machine", "meal ticket", "buy a ticket first",
}

NOMIHODAI_KEYWORDS = {
    "飲み放題", "食べ放題", "all-you-can-drink", "all you can drink",
    "nomihodai", "nomihoudai",
}

COURSE_KEYWORDS = {
    "コース", "-course", "course menu", "set menu", "宴会コース",
    "コース料理", "コース内容",
}

SALES_PROHIBITION_KEYWORDS = {
    "営業メールお断り", "セールスお断り", "広告メールお断り",
    "勧誘お断り", "営業目的の問い合わせ不可", "営業お断り",
    "営業目的不可", "勧誘不可", "営業不可", "販売目的お断り",
    "営業・勧誘お断り", "営業メール不可",
}


# ---------------------------------------------------------------------------
# Main classifier
# ---------------------------------------------------------------------------

def classify_lead(lead_data: dict[str, Any]) -> dict[str, Any]:
    """Classify a lead and select an evidence-gated template.

    Accepts either raw enrichment data or partially-classified data.
    Any recognised key is honoured; missing keys fall back to safe
    defaults ("unknown" / 0.0 / False).

    Returns the structured classification object described in the spec.
    """
    c = _init_classification(lead_data)

    _classify_restaurant_type(lead_data, c)
    _evaluate_contact(lead_data, c)
    _evaluate_menu(lead_data, c)
    _evaluate_ticket_machine(lead_data, c)
    _evaluate_nomihodai(lead_data, c)
    _evaluate_course(lead_data, c)
    _evaluate_english_menu(lead_data, c)
    _generate_claims(c)
    _select_template(c)
    _check_human_review(c)

    return c


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def _init_classification(lead_data: dict[str, Any]) -> dict[str, Any]:
    """Build the skeleton classification dict, seeding from lead_data
    when a matching key is present."""

    defaults: dict[str, Any] = {
        "business_name": "",
        "business_name_confidence": 0.0,
        "restaurant_type": "unknown",
        "restaurant_type_confidence": 0.0,
        "contact_channel": "none",
        "public_contact_source": "",
        "no_sales_or_solicitation_notice_found": False,
        "no_sales_or_solicitation_notice_text": "",
        "should_skip_due_to_contact_policy": False,
        "public_menu_found": False,
        "public_menu_usable_for_sample": False,
        "public_menu_source_type": "none",
        "public_menu_evidence_notes": "",
        "menu_readability_confidence": 0.0,
        "observed_menu_topics": [],
        "ticket_machine_confidence": 0.0,
        "ticket_machine_evidence_type": "none",
        "ticket_machine_content_usable": False,
        "ticket_machine_evidence_notes": "",
        "ticket_machine_source_url_or_reference": "",
        "nomihodai_confidence": 0.0,
        "nomihodai_evidence_notes": "",
        "course_confidence": 0.0,
        "course_evidence_notes": "",
        "existing_english_menu_confidence": 0.0,
        "existing_english_menu_quality": "none_found",
        "should_skip_due_to_existing_english_menu": False,
        "selected_template": "skip",
        "selected_template_reason": "",
        "allowed_claims": [],
        "blocked_claims": [],
        "human_review_required": False,
    }

    # Seed from lead_data when keys match
    for key in defaults:
        if key in lead_data:
            defaults[key] = lead_data[key]

    defaults["business_name"] = str(lead_data.get("business_name", defaults["business_name"]))

    # Normalise observed_menu_topics
    topics = defaults["observed_menu_topics"]
    defaults["observed_menu_topics"] = [t for t in topics if t in VALID_MENU_TOPICS]

    return defaults


# ---------------------------------------------------------------------------
# 1. Restaurant type
# ---------------------------------------------------------------------------

def _classify_restaurant_type(lead_data: dict[str, Any], c: dict[str, Any]) -> None:
    # Allow direct override
    if c["restaurant_type"] in RESTAURANT_TYPES and c["restaurant_type"] != "unknown":
        return  # already classified by caller

    category = str(lead_data.get("category") or "").lower()
    name = str(lead_data.get("business_name") or "").lower()
    description = str(lead_data.get("description") or "").lower()
    primary_category = str(lead_data.get("primary_category_v1") or "").lower()
    establishment_profile = str(lead_data.get("establishment_profile") or "").lower()

    text = f"{category} {name} {description}"

    has_ramen = any(kw in text for kw in RAMEN_KEYWORDS)
    has_izakaya = any(kw in text for kw in IZAKAYA_KEYWORDS)

    # Also check primary_category_v1 and establishment_profile
    is_ramen_profile = primary_category == "ramen" or establishment_profile.startswith("ramen")
    is_izakaya_profile = primary_category == "izakaya" or establishment_profile.startswith("izakaya")

    if has_ramen or is_ramen_profile:
        c["restaurant_type"] = "ramen"
        c["restaurant_type_confidence"] = 0.90 if (has_ramen and is_ramen_profile) else 0.80
    elif has_izakaya or is_izakaya_profile:
        c["restaurant_type"] = "izakaya"
        c["restaurant_type_confidence"] = 0.90 if (has_izakaya and is_izakaya_profile) else 0.80
    else:
        c["restaurant_type"] = "unknown"
        c["restaurant_type_confidence"] = 0.0


# ---------------------------------------------------------------------------
# 2. Contact channel
# ---------------------------------------------------------------------------

def _evaluate_contact(lead_data: dict[str, Any], c: dict[str, Any]) -> None:
    if c["contact_channel"] != "none":
        return  # already set

    contacts = lead_data.get("contacts") or []
    email = str(lead_data.get("email") or lead_data.get("contact_email") or "").strip()
    contact_form_url = str(lead_data.get("contact_form_url") or "").strip()

    # Check for public email
    has_public_email = False
    for contact in contacts:
        if isinstance(contact, dict):
            ctype = str(contact.get("type") or "").lower()
            if ctype == "email" and contact.get("actionable") is True:
                has_public_email = True
                c["public_contact_source"] = str(contact.get("source") or "")
                break

    if not has_public_email and email:
        has_public_email = True
        c["public_contact_source"] = str(lead_data.get("contact_email_source") or "unknown")

    # Check for official contact form
    has_contact_form = bool(contact_form_url)

    if has_public_email:
        c["contact_channel"] = "public_email"
    elif has_contact_form:
        c["contact_channel"] = "official_contact_form"
    else:
        c["contact_channel"] = "none"

    # Check for sales prohibition
    site_text = str(lead_data.get("site_text") or "")
    form_text = str(lead_data.get("contact_form_text") or "")
    no_sales_text = str(lead_data.get("no_sales_notice") or "")
    combined_text = f"{site_text} {form_text} {no_sales_text}"

    for kw in SALES_PROHIBITION_KEYWORDS:
        if kw in combined_text:
            c["no_sales_or_solicitation_notice_found"] = True
            c["no_sales_or_solicitation_notice_text"] = kw
            c["should_skip_due_to_contact_policy"] = True
            break


# ---------------------------------------------------------------------------
# 3. Menu evidence
# ---------------------------------------------------------------------------

def _evaluate_menu(lead_data: dict[str, Any], c: dict[str, Any]) -> None:
    if c["public_menu_found"]:
        pass  # already set
    else:
        menu_found = bool(lead_data.get("menu_evidence_found"))
        lead_dossier = lead_data.get("lead_evidence_dossier") or {}
        menu_state = str(lead_dossier.get("english_menu_state") or "")

        if menu_found or menu_state in ("usable_complete", "weak_partial"):
            c["public_menu_found"] = True

    if c["public_menu_found"]:
        source_type = c["public_menu_source_type"]
        if source_type == "none":
            c["public_menu_source_type"] = _infer_menu_source_type(lead_data)

        readability = c["menu_readability_confidence"]
        if readability == 0.0:
            readability = float(lead_data.get("menu_readability_confidence") or 0.0)
            c["menu_readability_confidence"] = readability

        c["public_menu_usable_for_sample"] = (
            c["public_menu_found"]
            and readability >= MENU_READABILITY_THRESHOLD
        )
    else:
        c["public_menu_usable_for_sample"] = False
        c["menu_readability_confidence"] = 0.0


def _infer_menu_source_type(lead_data: dict[str, Any]) -> str:
    source_urls = lead_data.get("source_urls") or {}
    evidence_urls = lead_data.get("evidence_urls") or []
    source = str(lead_data.get("menu_source") or "").lower()

    if source in MENU_SOURCE_TYPES and source != "none":
        return source

    # Heuristic from URLs
    all_urls = list(evidence_urls) + list(source_urls.values()) if isinstance(source_urls, dict) else list(evidence_urls)
    for url in all_urls:
        url_str = str(url).lower()
        if not url_str:
            continue
        if "google.com/maps" in url_str or "maps.google" in url_str:
            return "google_business_profile"
        if "tabelog" in url_str or "gurunavi" in url_str or "hotpepper" in url_str:
            return "third_party_listing"
        # If the URL domain matches the business website, it's likely official
        website = str(lead_data.get("website") or "")
        if website and website in url_str:
            return "official_website"

    return "other"


# ---------------------------------------------------------------------------
# 4. Ticket machine evidence
# ---------------------------------------------------------------------------

def _evaluate_ticket_machine(lead_data: dict[str, Any], c: dict[str, Any]) -> None:
    if c["ticket_machine_confidence"] > 0.0:
        pass  # already set by caller
    else:
        lead_dossier = lead_data.get("lead_evidence_dossier") or {}
        tm_state = str(lead_dossier.get("ticket_machine_state") or "")
        machine_found = bool(lead_data.get("machine_evidence_found"))
        evidence_classes = lead_data.get("evidence_classes") or []
        snippets = lead_data.get("evidence_snippets") or []

        confidence = 0.0
        evidence_type = "none"
        notes = ""

        if tm_state == "present":
            confidence = 0.90
            evidence_type = "official_listing"
            notes = "Ticket machine state marked present in lead dossier"
        elif machine_found:
            # Check for strong keyword signals
            all_text = " ".join(str(s) for s in snippets + evidence_classes).lower()
            has_strong_keyword = any(kw in all_text for kw in STRONG_TICKET_MACHINE_KEYWORDS)

            if has_strong_keyword:
                confidence = 0.92
                evidence_type = "explicit_text"
                notes = "Strong ticket-machine keyword found in evidence"
            else:
                # Check evidence_classes for machine-related items
                machine_classes = [e for e in evidence_classes if "machine" in str(e).lower() or "ticket" in str(e).lower() or "券売" in str(e) or "食券" in str(e)]
                if machine_classes:
                    confidence = 0.85
                    evidence_type = "multiple_medium_signals"
                    notes = f"Machine-related evidence classes: {', '.join(machine_classes)}"

        c["ticket_machine_confidence"] = confidence
        c["ticket_machine_evidence_type"] = evidence_type
        c["ticket_machine_evidence_notes"] = notes

    # Content usability
    c["ticket_machine_content_usable"] = (
        c["ticket_machine_confidence"] >= TICKET_MACHINE_THRESHOLD
        and c["ticket_machine_evidence_type"] in (
            "explicit_text", "clear_photo", "official_listing",
            "multiple_medium_signals",
        )
        and "ticket_machine_buttons" in c["observed_menu_topics"]
    )


# ---------------------------------------------------------------------------
# 5. Nomihodai evidence
# ---------------------------------------------------------------------------

def _evaluate_nomihodai(lead_data: dict[str, Any], c: dict[str, Any]) -> None:
    if c["nomihodai_confidence"] > 0.0:
        return  # already set

    snippets = lead_data.get("evidence_snippets") or []
    dossier = lead_data.get("lead_evidence_dossier") or {}
    izakaya_state = str(dossier.get("izakaya_rules_state") or "")
    profile = str(lead_data.get("establishment_profile") or "")

    confidence = 0.0
    notes = ""

    # Strong: dossier says nomihodai found
    if izakaya_state == "nomihodai_found":
        confidence = 0.92
        notes = "Lead dossier reports nomihodai_found"

    # Strong: profile is drink_heavy or course_heavy
    elif profile in ("izakaya_drink_heavy", "izakaya_course_heavy"):
        confidence = 0.88
        notes = f"Establishment profile: {profile}"

    else:
        # Check snippets for keywords
        all_text = " ".join(str(s) for s in snippets).lower()
        if any(kw in all_text for kw in NOMIHODAI_KEYWORDS):
            confidence = 0.87
            notes = "Nomihodai keyword found in evidence snippets"

    c["nomihodai_confidence"] = confidence
    c["nomihodai_evidence_notes"] = notes


# ---------------------------------------------------------------------------
# 6. Course evidence
# ---------------------------------------------------------------------------

def _evaluate_course(lead_data: dict[str, Any], c: dict[str, Any]) -> None:
    if c["course_confidence"] > 0.0:
        return

    snippets = lead_data.get("evidence_snippets") or []
    dossier = lead_data.get("lead_evidence_dossier") or {}
    izakaya_state = str(dossier.get("izakaya_rules_state") or "")
    course_found = bool(lead_data.get("course_or_drink_plan_evidence_found"))

    confidence = 0.0
    notes = ""

    if izakaya_state == "courses_found":
        confidence = 0.90
        notes = "Lead dossier reports courses_found"
    elif course_found:
        all_text = " ".join(str(s) for s in snippets).lower()
        has_course_kw = any(kw in all_text for kw in COURSE_KEYWORDS)
        if has_course_kw:
            confidence = 0.88
            notes = "Course keyword found in evidence snippets"
        else:
            confidence = 0.78
            notes = "course_or_drink_plan_evidence_found flag set"

    c["course_confidence"] = confidence
    c["course_evidence_notes"] = notes


# ---------------------------------------------------------------------------
# 7. English menu evidence
# ---------------------------------------------------------------------------

def _evaluate_english_menu(lead_data: dict[str, Any], c: dict[str, Any]) -> None:
    # If quality was already set by caller (via seed), honour it
    if c["existing_english_menu_quality"] in ("comprehensive", "partial", "unclear"):
        c["should_skip_due_to_existing_english_menu"] = (
            c["existing_english_menu_quality"] == "comprehensive"
        )
        return

    if c["existing_english_menu_confidence"] > 0.0:
        return

    dossier = lead_data.get("lead_evidence_dossier") or {}
    menu_state = str(dossier.get("english_menu_state") or "")
    english_issue = bool(lead_data.get("english_menu_issue"))
    english_availability = str(lead_data.get("english_availability") or "").lower()

    confidence = 0.0
    quality = "none_found"

    if menu_state == "usable_complete":
        confidence = 0.90
        quality = "comprehensive"
    elif menu_state == "image_only":
        confidence = 0.70
        quality = "partial"
    elif menu_state == "weak_partial":
        confidence = 0.60
        quality = "partial"
    elif english_issue:
        # english_menu_issue means we found problems with their English
        confidence = 0.50
        quality = "partial"
    elif english_availability == "none":
        confidence = 0.0
        quality = "none_found"

    c["existing_english_menu_confidence"] = confidence
    c["existing_english_menu_quality"] = quality
    c["should_skip_due_to_existing_english_menu"] = quality == "comprehensive"


# ---------------------------------------------------------------------------
# 8. Claims generation
# ---------------------------------------------------------------------------

def _generate_claims(c: dict[str, Any]) -> None:
    allowed: list[str] = []
    blocked: list[str] = []

    # --- Menu claims ---
    if c["public_menu_found"]:
        allowed.append("mention_public_menu")
    else:
        blocked.append("mention_public_menu")

    if c["public_menu_usable_for_sample"]:
        allowed.append("offer_sample_from_public_menu")
    else:
        blocked.append("offer_sample_from_public_menu")

    # --- Topic-specific claims ---
    for topic in c["observed_menu_topics"]:
        allowed.append(f"mention_{topic}")

    # Block topics not observed
    for topic in VALID_MENU_TOPICS:
        if topic not in c["observed_menu_topics"]:
            blocked.append(f"mention_{topic}")

    # --- Ticket machine claims ---
    if c["ticket_machine_confidence"] >= TICKET_MACHINE_THRESHOLD:
        allowed.append("mention_ticket_machine")
        if c["ticket_machine_content_usable"]:
            allowed.append("offer_ticket_machine_sample")
        else:
            blocked.append("offer_ticket_machine_sample")
    else:
        blocked.append("mention_ticket_machine")
        blocked.append("offer_ticket_machine_sample")

    # Neutral ordering allowed when some machine suspicion exists
    if TICKET_MACHINE_HUMAN_REVIEW_LOW <= c["ticket_machine_confidence"] < TICKET_MACHINE_THRESHOLD:
        allowed.append("neutral_ordering_wording")
    else:
        blocked.append("neutral_ordering_wording")

    # --- Nomihodai claims ---
    if c["nomihodai_confidence"] >= NOMIHODAI_THRESHOLD:
        allowed.append("mention_nomihodai")
        for topic in ("last_order", "extra_charges"):
            if topic in c["observed_menu_topics"]:
                allowed.append(f"mention_{topic}")
    else:
        blocked.append("mention_nomihodai")

    # --- Course claims ---
    if c["course_confidence"] >= COURSE_THRESHOLD:
        allowed.append("mention_course")
    else:
        blocked.append("mention_course")

    # --- English menu claims ---
    if c["existing_english_menu_quality"] != "none_found":
        allowed.append("graceful_exit_existing_menu")
    if c["existing_english_menu_quality"] == "comprehensive":
        blocked.append("send_email")  # should skip

    # --- Contact claims ---
    if c["should_skip_due_to_contact_policy"]:
        blocked.append("send_email")

    # --- Photo request claims ---
    if not c["public_menu_usable_for_sample"] and not c["ticket_machine_content_usable"]:
        allowed.append("request_photo")

    c["allowed_claims"] = allowed
    c["blocked_claims"] = blocked


# ---------------------------------------------------------------------------
# 9. Template selection
# ---------------------------------------------------------------------------

def _select_template(c: dict[str, Any]) -> None:
    # --- Skip checks (order matters) ---
    if c["should_skip_due_to_contact_policy"]:
        c["selected_template"] = "skip"
        c["selected_template_reason"] = "Sales/solicitation prohibition found"
        return

    if c["existing_english_menu_quality"] == "comprehensive":
        c["selected_template"] = "skip"
        c["selected_template_reason"] = "Existing English menu is comprehensive"
        return

    if c["contact_channel"] == "none":
        c["selected_template"] = "skip"
        c["selected_template_reason"] = "No public email or official contact form"
        return

    if c["restaurant_type"] not in ("ramen", "izakaya") or c["restaurant_type_confidence"] < 0.75:
        c["selected_template"] = "skip"
        c["selected_template_reason"] = (
            f"Restaurant type '{c['restaurant_type']}' confidence "
            f"{c['restaurant_type_confidence']:.2f} below threshold 0.75"
        )
        return

    # --- Contact form path ---
    if c["contact_channel"] == "official_contact_form":
        _select_contact_form_template(c)
        return

    # --- Type-specific paths ---
    if c["restaurant_type"] == "ramen":
        _select_ramen_template(c)
    elif c["restaurant_type"] == "izakaya":
        _select_izakaya_template(c)


def _select_ramen_template(c: dict[str, Any]) -> None:
    has_menu = c["public_menu_usable_for_sample"]
    tm_confident = c["ticket_machine_confidence"] >= TICKET_MACHINE_THRESHOLD
    tm_content = c["ticket_machine_content_usable"]

    if has_menu and tm_confident:
        c["selected_template"] = "ramen_menu_plus_ticket_machine"
        c["selected_template_reason"] = (
            "Ramen + usable public menu + ticket machine confidence "
            f"{c['ticket_machine_confidence']:.2f}"
        )
    elif has_menu and not tm_confident:
        if "neutral_ordering_wording" in c["allowed_claims"]:
            c["selected_template"] = "ramen_visible_menu_neutral_ordering"
            c["selected_template_reason"] = (
                "Ramen + usable public menu + weak ticket-machine signals "
                f"(confidence {c['ticket_machine_confidence']:.2f})"
            )
        else:
            c["selected_template"] = "ramen_visible_menu"
            c["selected_template_reason"] = "Ramen + usable public menu, no ticket-machine evidence"
    elif not has_menu and tm_confident and tm_content:
        c["selected_template"] = "ramen_ticket_machine_only"
        c["selected_template_reason"] = "Ramen + no usable menu + ticket machine content usable"
    elif not has_menu and tm_confident and not tm_content:
        c["selected_template"] = "ramen_needs_ticket_machine_photo"
        c["selected_template_reason"] = (
            "Ramen + no usable menu + ticket machine detected but content not readable"
        )
    else:
        # No usable menu, no ticket machine
        c["selected_template"] = "ramen_needs_menu_photo"
        c["selected_template_reason"] = "Ramen + no usable public menu + no ticket-machine evidence"


def _select_izakaya_template(c: dict[str, Any]) -> None:
    has_menu = c["public_menu_usable_for_sample"]
    has_nomihodai = c["nomihodai_confidence"] >= NOMIHODAI_THRESHOLD
    has_course = c["course_confidence"] >= COURSE_THRESHOLD
    topics = c["observed_menu_topics"]

    if not has_menu:
        c["selected_template"] = "izakaya_needs_menu_photo"
        c["selected_template_reason"] = "Izakaya + no usable public menu"
        return

    if has_nomihodai and has_course:
        c["selected_template"] = "izakaya_nomihodai_course"
        c["selected_template_reason"] = "Izakaya + nomihodai + course evidence"
    elif has_nomihodai and not has_course:
        c["selected_template"] = "izakaya_nomihodai_only"
        c["selected_template_reason"] = "Izakaya + nomihodai, no course evidence"
    elif has_course and not has_nomihodai:
        c["selected_template"] = "izakaya_course_only"
        c["selected_template_reason"] = "Izakaya + course, no nomihodai evidence"
    elif "food_items" in topics and "drink_items" in topics:
        c["selected_template"] = "izakaya_food_drink_only"
        c["selected_template_reason"] = "Izakaya + food + drink menu, no course/nomihodai"
    elif "food_items" in topics and "drink_items" not in topics:
        c["selected_template"] = "izakaya_standard"
        c["selected_template_reason"] = "Izakaya + food menu only"
    elif "drink_items" in topics and "food_items" not in topics:
        c["selected_template"] = "izakaya_standard"
        c["selected_template_reason"] = "Izakaya + drink menu only"
    else:
        c["selected_template"] = "izakaya_standard"
        c["selected_template_reason"] = "Izakaya + usable public menu, general"


def _select_contact_form_template(c: dict[str, Any]) -> None:
    if c["should_skip_due_to_contact_policy"]:
        c["selected_template"] = "skip"
        c["selected_template_reason"] = "Contact form prohibits sales inquiries"
        return

    if c["public_menu_usable_for_sample"]:
        c["selected_template"] = "contact_form_public_menu"
        c["selected_template_reason"] = "Contact form + usable public menu"
    else:
        c["selected_template"] = "contact_form_needs_menu_photo"
        c["selected_template_reason"] = "Contact form + no usable public menu"


# ---------------------------------------------------------------------------
# 10. Human review
# ---------------------------------------------------------------------------

def _check_human_review(c: dict[str, Any]) -> None:
    review = False

    if TICKET_MACHINE_HUMAN_REVIEW_LOW <= c["ticket_machine_confidence"] <= TICKET_MACHINE_HUMAN_REVIEW_HIGH:
        review = True

    if 0.60 <= c["restaurant_type_confidence"] < 0.75:
        review = True

    if c["public_menu_found"] and not c["public_menu_usable_for_sample"]:
        if c["menu_readability_confidence"] > 0:
            review = True  # menu exists but readability unclear

    if c["selected_template"] in (
        "ramen_menu_plus_ticket_machine",
        "ramen_ticket_machine_only",
        "izakaya_nomihodai_course",
        "izakaya_nomihodai_only",
    ):
        # Specialized template based mainly on evidence interpretation
        if c["ticket_machine_evidence_type"] in ("review_text", "third_party_listing"):
            review = True
        if not c["nomihodai_evidence_notes"] and c["nomihodai_confidence"] >= NOMIHODAI_THRESHOLD:
            review = True

    if c["no_sales_or_solicitation_notice_found"] and not c["should_skip_due_to_contact_policy"]:
        review = True  # ambiguous wording

    c["human_review_required"] = review
