"""Adapters between WebRefurb lead records and email discovery models."""

from __future__ import annotations

import concurrent.futures
import re
from copy import deepcopy
from typing import Any

from pipeline.contact_crawler import is_usable_business_email
from pipeline.contact_policy import normalise_contact_actionability
from pipeline.record import normalise_lead_contacts
from pipeline.utils import utc_now

from .config import DiscoveryConfig, load_config
from .contact_form_detector import detect_contact_form, detect_contact_forms_from_links
from .email_classifier import classify_email, rank_emails
from .email_extractor import extract_emails_from_page
from .models import DiscoveredContactForm, DiscoveredEmail, EmailType, EnrichedLead, InputLead
from .pipeline import _extract_links, _html_to_text, process_lead
from .tokushoho import find_tokushoho_links, is_tokushoho_page, parse_tokushoho_page


_ACTIONABLE_EMAIL_TYPES = {
    EmailType.GENERAL_BUSINESS,
    EmailType.OPERATOR_COMPANY,
    EmailType.ONLINE_SHOP,
    EmailType.MEDIA_PR,
}

_PREFECTURES = (
    "北海道",
    "青森県",
    "岩手県",
    "宮城県",
    "秋田県",
    "山形県",
    "福島県",
    "茨城県",
    "栃木県",
    "群馬県",
    "埼玉県",
    "千葉県",
    "東京都",
    "神奈川県",
    "新潟県",
    "富山県",
    "石川県",
    "福井県",
    "山梨県",
    "長野県",
    "岐阜県",
    "静岡県",
    "愛知県",
    "三重県",
    "滋賀県",
    "京都府",
    "大阪府",
    "兵庫県",
    "奈良県",
    "和歌山県",
    "鳥取県",
    "島根県",
    "岡山県",
    "広島県",
    "山口県",
    "徳島県",
    "香川県",
    "愛媛県",
    "高知県",
    "福岡県",
    "佐賀県",
    "長崎県",
    "熊本県",
    "大分県",
    "宮崎県",
    "鹿児島県",
    "沖縄県",
)

_ENGLISH_PREFECTURES = {
    "hokkaido": "北海道",
    "aomori": "青森県",
    "iwate": "岩手県",
    "miyagi": "宮城県",
    "akita": "秋田県",
    "yamagata": "山形県",
    "fukushima": "福島県",
    "ibaraki": "茨城県",
    "tochigi": "栃木県",
    "gunma": "群馬県",
    "saitama": "埼玉県",
    "chiba": "千葉県",
    "tokyo": "東京都",
    "kanagawa": "神奈川県",
    "niigata": "新潟県",
    "toyama": "富山県",
    "ishikawa": "石川県",
    "fukui": "福井県",
    "yamanashi": "山梨県",
    "nagano": "長野県",
    "gifu": "岐阜県",
    "shizuoka": "静岡県",
    "aichi": "愛知県",
    "mie": "三重県",
    "shiga": "滋賀県",
    "kyoto": "京都府",
    "osaka": "大阪府",
    "hyogo": "兵庫県",
    "nara": "奈良県",
    "wakayama": "和歌山県",
    "tottori": "鳥取県",
    "shimane": "島根県",
    "okayama": "岡山県",
    "hiroshima": "広島県",
    "yamaguchi": "山口県",
    "tokushima": "徳島県",
    "kagawa": "香川県",
    "ehime": "愛媛県",
    "kochi": "高知県",
    "fukuoka": "福岡県",
    "saga": "佐賀県",
    "nagasaki": "長崎県",
    "kumamoto": "熊本県",
    "oita": "大分県",
    "miyazaki": "宮崎県",
    "kagoshima": "鹿児島県",
    "okinawa": "沖縄県",
}


def lead_record_to_input_lead(record: dict[str, Any]) -> InputLead:
    """Convert a persisted WebRefurb lead record into an email discovery lead."""
    address = str(record.get("address") or "")
    source_urls = record.get("source_urls") if isinstance(record.get("source_urls"), dict) else {}
    evidence_urls = list(record.get("evidence_urls") or source_urls.get("evidence_urls") or [])
    website = str(record.get("website") or source_urls.get("website") or "")

    return InputLead(
        shop_name=str(record.get("business_name") or ""),
        genre=str(record.get("primary_category_v1") or record.get("lead_category") or ""),
        address=address,
        city=_extract_city(address),
        prefecture=_extract_prefecture(address),
        phone=str(record.get("phone") or ""),
        portal_url=str(record.get("map_url") or source_urls.get("map_url") or ""),
        official_site_url=website,
        menu_url=_find_menu_url(evidence_urls),
        notes=str(record.get("rejection_reason") or ""),
    )


def enriched_to_contact_records(enriched: EnrichedLead) -> list[dict[str, Any]]:
    """Convert discovered contacts into WebRefurb contact route dicts."""
    contacts: list[dict[str, Any]] = []
    discovered_at = str(enriched.crawl_timestamp or utc_now())

    for email in enriched.all_emails:
        contact = _email_to_contact(email, discovered_at=discovered_at)
        if contact:
            contacts.append(contact)

    form = _best_contact_form(enriched)
    if form:
        contacts.append(_form_to_contact(form, discovered_at=discovered_at))

    return contacts


def enrich_lead(
    record: dict[str, Any],
    config: DiscoveryConfig | None = None,
) -> dict[str, Any]:
    """Run email discovery for a lead record and merge additive results."""
    updated = deepcopy(record)
    if config is None:
        config = load_config("email_discovery.yaml")

    enriched = process_lead(lead_record_to_input_lead(updated), config)
    _merge_enrichment(updated, enriched)
    return updated


def enrich_lead_inline(
    *,
    business_name: str,
    website: str,
    html: str = "",
    address: str = "",
    phone: str = "",
    genre: str = "",
    timeout_seconds: float = 5.0,
    max_extra_pages: int = 3,
    config: DiscoveryConfig | None = None,
) -> list[dict[str, Any]]:
    """Lightweight contact discovery used as a gated search fallback."""
    if not website and not html:
        return []

    enriched = _extract_inline_contacts(
        business_name=business_name,
        website=website,
        html=html,
        address=address,
        phone=phone,
        genre=genre,
    )
    contacts = enriched_to_contact_records(enriched)
    if any(contact.get("actionable") for contact in contacts):
        return contacts

    if not website:
        return []

    if config is None:
        config = load_config("email_discovery.yaml")
    else:
        config = deepcopy(config)
    config.search.max_queries_per_lead = min(config.search.max_queries_per_lead, 3)
    config.search.max_results_per_query = min(config.search.max_results_per_query, 3)
    config.search.max_page_crawls_per_lead = max(1, min(max_extra_pages, 3))
    config.search.page_timeout = min(float(config.search.page_timeout), float(timeout_seconds))
    config.search.rate_limit_delay = min(float(config.search.rate_limit_delay), 0.2)

    lead = InputLead(
        shop_name=business_name,
        genre=genre,
        address=address,
        prefecture=_extract_prefecture(address),
        phone=phone,
        official_site_url=website,
    )
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future: concurrent.futures.Future[EnrichedLead] | None = None
    try:
        future = executor.submit(process_lead, lead, config)
        enriched = future.result(timeout=timeout_seconds)
    except Exception:
        if future is not None:
            future.cancel()
        return []
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return enriched_to_contact_records(enriched)


def _merge_enrichment(record: dict[str, Any], enriched: EnrichedLead) -> None:
    new_contacts = enriched_to_contact_records(enriched)
    record["contacts"] = _merge_contacts(record.get("contacts") or [], new_contacts)

    best_email = _best_usable_email(enriched)
    if best_email:
        record["email"] = best_email.email

    contacts = normalise_lead_contacts(record)
    record["contacts"] = contacts

    email_value = str(record.get("email") or "").strip().lower()
    email_contact = next(
        (
            contact
            for contact in contacts
            if contact.get("type") == "email"
            and str(contact.get("value") or "").strip().lower() == email_value
            and contact.get("actionable")
        ),
        None,
    )
    if email_contact:
        record["primary_contact"] = email_contact
    else:
        record["primary_contact"] = next((contact for contact in contacts if contact.get("actionable")), None)

    first_email = next((contact for contact in contacts if contact.get("type") == "email"), None)
    record["email"] = str((email_contact or first_email or {}).get("value") or "")
    record["has_supported_contact_route"] = bool(record["primary_contact"])

    record["email_discovery_enriched_at"] = enriched.crawl_timestamp or utc_now()
    record["email_discovery_score"] = enriched.confidence_score
    record["email_discovery_reason_codes"] = list(enriched.reason_codes)
    record["email_discovery_best_email_type"] = enriched.best_email_type
    record["email_discovery_tokushoho_url"] = enriched.tokushoho_page_url
    record["email_discovery_operator_company"] = enriched.operator_company_name


def _extract_inline_contacts(
    *,
    business_name: str,
    website: str,
    html: str,
    address: str,
    phone: str,
    genre: str,
) -> EnrichedLead:
    text = _html_to_text(html)
    now = utc_now()
    enriched = EnrichedLead(
        lead_id="inline",
        shop_name=business_name,
        normalized_shop_name=business_name,
        genre=genre,
        address=address,
        prefecture=_extract_prefecture(address),
        phone=phone,
        official_site_url=website,
        crawl_timestamp=now,
    )

    emails: list[tuple[Any, EmailType]] = []
    for extracted in extract_emails_from_page(html=html, visible_text=text, source_url=website):
        emails.append((extracted, classify_email(extracted, source_page_type=_inline_page_type(website, html, text))))

    ranked = rank_emails(emails)
    enriched.all_emails = [
        DiscoveredEmail(
            email=extracted.email,
            email_type=email_type,
            source_url=website,
            source_snippet=extracted.context[:200],
            source_page_type=_inline_page_type(website, html, text),
            confidence=0.75,
        )
        for extracted, email_type in ranked
    ]

    best = _best_usable_email(enriched)
    if best:
        enriched.best_email = best.email
        enriched.best_email_type = best.email_type.value
        enriched.email_source_url = best.source_url
        enriched.email_source_snippet = best.source_snippet

    form_detection = detect_contact_form(website, html=html, page_title=_extract_title(html))
    if form_detection.is_contact_form and form_detection.form_type == "official":
        form = DiscoveredContactForm(
            url=website,
            form_type=form_detection.form_type,
            page_title=form_detection.page_title,
            confidence=form_detection.confidence,
            source_url=website,
        )
        enriched.contact_forms.append(form)
        enriched.contact_form_url = form.url

    links = _extract_links(html, website)
    for form in detect_contact_forms_from_links(links, _extract_title(html), website):
        if form.form_type == "official":
            enriched.contact_forms.append(form)
            if not enriched.contact_form_url:
                enriched.contact_form_url = form.url

    if is_tokushoho_page(website, title=_extract_title(html), text=text):
        tokushoho = parse_tokushoho_page(website, html=html, text=text, title=_extract_title(html))
        if tokushoho.is_tokushoho:
            enriched.tokushoho_page_url = website

    return enriched


def _email_to_contact(email: DiscoveredEmail, *, discovered_at: str) -> dict[str, Any] | None:
    value = str(email.email or "").strip().lower()
    if not value or not is_usable_business_email(value):
        return None
    if email.email_type not in _ACTIONABLE_EMAIL_TYPES:
        return None

    contact = {
        "type": "email",
        "value": value,
        "label": email.email_type.value,
        "href": f"mailto:{value}",
        "source": "email_discovery",
        "source_url": email.source_url,
        "confidence": "high" if email.confidence >= 0.7 else "medium",
        "discovered_at": discovered_at,
        "status": "discovered",
        "actionable": True,
        "email_type": email.email_type.value,
        "email_source_page_type": email.source_page_type,
    }
    return normalise_contact_actionability(contact)


def _form_to_contact(form: DiscoveredContactForm, *, discovered_at: str) -> dict[str, Any]:
    contact = {
        "type": "contact_form",
        "value": form.url,
        "label": "contact_form",
        "href": form.url,
        "source": "email_discovery",
        "source_url": form.source_url or form.url,
        "confidence": "high" if form.confidence >= 0.7 else "medium",
        "discovered_at": discovered_at,
        "status": "discovered",
        "actionable": form.form_type == "official",
        "has_form": form.confidence >= 0.5,
        "page_title": form.page_title,
    }
    return normalise_contact_actionability(contact)


def _best_contact_form(enriched: EnrichedLead) -> DiscoveredContactForm | None:
    forms = [form for form in enriched.contact_forms if form.url == enriched.contact_form_url]
    if forms:
        return forms[0]
    if enriched.contact_form_url:
        return DiscoveredContactForm(
            url=enriched.contact_form_url,
            form_type="official",
            confidence=0.5,
            source_url=enriched.contact_form_url,
        )
    return None


def _best_usable_email(enriched: EnrichedLead) -> DiscoveredEmail | None:
    preferred = str(enriched.best_email or "").strip().lower()
    for email in enriched.all_emails:
        if preferred and email.email.lower() != preferred:
            continue
        if email.email_type not in _ACTIONABLE_EMAIL_TYPES:
            continue
        if is_usable_business_email(email.email):
            return email
    for email in enriched.all_emails:
        if email.email_type not in _ACTIONABLE_EMAIL_TYPES:
            continue
        if is_usable_business_email(email.email):
            return email
    return None


def _merge_contacts(existing: list[dict[str, Any]], new_contacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for contact in [*existing, *new_contacts]:
        contact_type = str(contact.get("type") or "").strip().lower()
        value = _normalise_contact_value(contact_type, str(contact.get("value") or ""))
        if not contact_type or not value:
            continue
        key = (contact_type, value)
        if key in seen:
            continue
        seen.add(key)
        merged.append(contact)
    return merged


def _normalise_contact_value(contact_type: str, value: str) -> str:
    if contact_type == "email":
        return value.strip().lower()
    if contact_type == "phone":
        return re.sub(r"\D", "", value)
    return value.strip().lower()


def _extract_prefecture(address: str) -> str:
    for prefecture in _PREFECTURES:
        if prefecture in address:
            return prefecture
    lowered = address.lower()
    for token, prefecture in _ENGLISH_PREFECTURES.items():
        if re.search(rf"\b{re.escape(token)}\b", lowered):
            return prefecture
    return ""


def _extract_city(address: str) -> str:
    if not address:
        return ""
    without_pref = address
    prefecture = _extract_prefecture(address)
    if prefecture:
        without_pref = without_pref.replace(prefecture, "", 1)
    match = re.search(r"([^0-9０-９,、\s]+?[市区町村])", without_pref)
    return match.group(1) if match else ""


def _find_menu_url(urls: list[str]) -> str:
    for url in urls:
        lowered = str(url or "").lower()
        if any(token in lowered for token in ("menu", "メニュー", "品書き", "food", "drink")):
            return str(url)
    return ""


def _extract_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html or "", flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def _inline_page_type(url: str, html: str, text: str) -> str:
    title = _extract_title(html)
    if is_tokushoho_page(url, title=title, text=text):
        return "tokushoho"
    if find_tokushoho_links(html, url):
        return "contact"
    lowered = f"{url} {title} {text[:500]}".lower()
    if any(token in lowered for token in ("company", "会社概要", "運営会社")):
        return "company"
    if any(token in lowered for token in ("contact", "inquiry", "お問い合わせ", "問合せ")):
        return "contact"
    return "unknown"
