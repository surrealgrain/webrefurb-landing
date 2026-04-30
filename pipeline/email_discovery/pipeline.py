"""Main discovery pipeline orchestrator.

Coordinates all modules to discover emails and qualify leads:
  1. Load input leads from CSV
  2. Normalize and deduplicate
  3. For each lead, generate Japanese search queries
  4. Execute searches (via Serper or local provider)
  5. Crawl discovered pages
  6. Extract emails with obfuscation normalization
  7. Detect contact forms
  8. Parse 特商法 pages for operator info
  9. Resolve operator companies
  10. Classify genres
  11. Detect menu presence
  12. Check compliance (refusal warnings)
  13. Score leads (0-100)
  14. Determine launch readiness
  15. Write output (CSV, JSONL, SQLite)
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from .config import DiscoveryConfig, load_config, TOKUSHOHO_INDICATORS, ONLINE_SHOP_INDICATORS
from .models import (
    InputLead, EnrichedLead, DiscoveredEmail, DiscoveredContactForm,
    EmailType, NextBestAction, ReasonCode,
)
from .input_loader import load_leads_csv
from .query_generator import generate_lead_queries
from .email_extractor import extract_emails_from_page
from .email_classifier import classify_email, rank_emails
from .contact_form_detector import detect_contact_form, detect_contact_forms_from_links
from .tokushoho import is_tokushoho_page, parse_tokushoho_page, find_tokushoho_links
from .operator_resolver import resolve_from_tokushoho, resolve_from_page, company_info_to_operator
from .genre_classifier import classify_genre
from .menu_detector import detect_menu_in_html, detect_menu_in_text, detect_menu_url
from .compliance import check_compliance, is_email_safe_to_contact
from .scorer import score_lead
from .output_writer import write_outputs
from .db import DiscoveryDB

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Page fetching
# ---------------------------------------------------------------------------

def _fetch_page(url: str, timeout: float = 10.0, user_agent: str = "") -> tuple[str, str, str]:
    """Fetch a URL. Returns (html, text, final_url).

    Returns empty strings on failure.
    """
    if not url or not url.startswith(("http://", "https://")):
        return "", "", url

    headers = {"User-Agent": user_agent or "Mozilla/5.0 (compatible; EmailDiscovery/1.0)"}
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, verify=False) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text
            text = _html_to_text(html)
            return html, text, str(resp.url)
    except Exception as e:
        logger.debug("Failed to fetch %s: %s", url, e)
        return "", "", url


def _html_to_text(html: str) -> str:
    """Simple HTML to text conversion."""
    # Remove scripts and styles
    text = re.sub(r"<(?:script|style)[^>]*>.*?</(?:script|style)>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_links(html: str, base_url: str = "") -> list[str]:
    """Extract href links from HTML."""
    links = re.findall(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE)
    # Filter to http links only
    return [l for l in links if l.startswith(("http://", "https://"))]


# ---------------------------------------------------------------------------
# Search execution
# ---------------------------------------------------------------------------

def _execute_search(query: str, config: DiscoveryConfig) -> list[dict]:
    """Execute a search query using the configured provider.

    Returns list of result dicts: {title, url, snippet}.
    """
    results: list[dict] = []

    if config.search.provider == "serper" and config.search.serper_api_key:
        results = _serper_search(query, config)
    else:
        # Fallback: no search provider configured, return empty
        logger.warning("No search provider configured. Query: %s", query[:80])

    return results


def _serper_search(query: str, config: DiscoveryConfig) -> list[dict]:
    """Execute search via Serper API."""
    try:
        with httpx.Client(timeout=config.search.page_timeout) as client:
            resp = client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": config.search.serper_api_key},
                json={"q": query, "gl": "jp", "hl": "ja", "num": config.search.max_results_per_query},
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get("organic", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })
            return results
    except Exception as e:
        logger.error("Serper search failed for '%s': %s", query[:50], e)
        return []


# ---------------------------------------------------------------------------
# Single-lead processing
# ---------------------------------------------------------------------------

def process_lead(
    lead: InputLead,
    config: DiscoveryConfig,
) -> EnrichedLead:
    """Process a single lead through the full discovery pipeline.

    This is the core function that coordinates all modules.
    """
    start = time.time()
    now = datetime.now(timezone.utc).isoformat()

    enriched = EnrichedLead(
        lead_id=lead.lead_id,
        shop_name=lead.shop_name,
        normalized_shop_name=lead.normalized_shop_name,
        genre=lead.genre,
        address=lead.address,
        prefecture=lead.prefecture,
        city=lead.city,
        phone=lead.phone,
        official_site_url=lead.official_site_url,
        menu_url=lead.menu_url,
        crawl_timestamp=now,
    )

    # ---- Step 1: Genre classification ----
    genre_result = classify_genre(
        genre_text=lead.genre,
        shop_name=lead.shop_name,
    )
    enriched.genre = genre_result.genre or lead.genre
    enriched.genre_confidence = genre_result.confidence

    if genre_result.category == "excluded":
        enriched.reason_codes.append(ReasonCode.GENRE_MISMATCH.value)
        enriched.next_best_action = NextBestAction.SKIP_GENRE.value
        _finalize(enriched, config, start)
        return enriched

    # ---- Step 2: Generate search queries ----
    queries = generate_lead_queries(
        lead,
        max_queries=config.search.max_queries_per_lead,
    )

    # ---- Step 3: Execute searches ----
    all_results: list[dict] = []
    if not config.dry_run:
        for query in queries:
            results = _execute_search(query, config)
            all_results.extend(results)
            time.sleep(config.search.rate_limit_delay)
    enriched.raw_search_results = all_results

    # ---- Step 4: Crawl official site (if known) ----
    crawled_pages: list[tuple[str, str, str]] = []  # (url, html, text)

    if lead.official_site_url and not config.dry_run:
        html, text, final_url = _fetch_page(
            lead.official_site_url,
            timeout=config.search.page_timeout,
            user_agent=config.search.user_agent,
        )
        if html:
            crawled_pages.append((final_url, html, text))

            # Extract links from official site
            links = _extract_links(html, lead.official_site_url)

            # Crawl important sub-pages (contact, company, tokushoho, etc.)
            priority_links = _prioritize_links(links, lead.official_site_url)
            for link_url in priority_links[:config.search.max_page_crawls_per_lead - 1]:
                p_html, p_text, p_final = _fetch_page(
                    link_url,
                    timeout=config.search.page_timeout,
                    user_agent=config.search.user_agent,
                )
                if p_html:
                    crawled_pages.append((p_final, p_html, p_text))
                time.sleep(config.search.rate_limit_delay * 0.5)

    # Also crawl top search results
    seen_urls = {url for url, _, _ in crawled_pages}
    for result in all_results[:5]:
        url = result.get("url", "")
        if url and url not in seen_urls and not config.dry_run:
            p_html, p_text, p_final = _fetch_page(
                url,
                timeout=config.search.page_timeout,
                user_agent=config.search.user_agent,
            )
            if p_html:
                crawled_pages.append((p_final, p_html, p_text))
                seen_urls.add(url)
            time.sleep(config.search.rate_limit_delay * 0.5)

    # ---- Step 5: Extract emails from all pages ----
    all_emails: list[tuple[DiscoveredEmail, str]] = []  # (email, page_url)

    for page_url, page_html, page_text in crawled_pages:
        extracted = extract_emails_from_page(
            html=page_html,
            visible_text=page_text,
            source_url=page_url,
        )
        for ext in extracted:
            classified_type = classify_email(
                ext,
                source_page_type=_detect_page_type(page_url, page_html, page_text),
                source_snippet=ext.context,
            )
            discovered = DiscoveredEmail(
                email=ext.email,
                email_type=classified_type,
                source_url=page_url,
                source_snippet=ext.context[:200],
                source_page_type=_detect_page_type(page_url, page_html, page_text),
                confidence=_email_confidence(ext.method, classified_type),
            )
            all_emails.append((discovered, page_url))

    # ---- Step 6: Detect contact forms ----
    all_forms: list[DiscoveredContactForm] = []
    for page_url, page_html, page_text in crawled_pages:
        form_detection = detect_contact_form(page_url, html=page_html, page_title=_extract_title(page_html))
        if form_detection.is_contact_form:
            all_forms.append(DiscoveredContactForm(
                url=page_url,
                form_type=form_detection.form_type,
                page_title=form_detection.page_title,
                confidence=form_detection.confidence,
                source_url=page_url,
            ))

        # Also detect form links
        links = _extract_links(page_html, page_url)
        form_links = detect_contact_forms_from_links(links, _extract_title(page_html), page_url)
        all_forms.extend(form_links)

    # ---- Step 7: Parse 特商法 pages ----
    for page_url, page_html, page_text in crawled_pages:
        if is_tokushoho_page(page_url, title=_extract_title(page_html), text=page_text):
            tokushoho_data = parse_tokushoho_page(page_url, html=page_html, text=page_text, title=_extract_title(page_html))
            if tokushoho_data.is_tokushoho:
                enriched.tokushoho_page_url = page_url

                # Extract operator company from tokushoho
                company_info = resolve_from_tokushoho(tokushoho_data)
                if company_info:
                    enriched.operator_company_name = company_info.name
                    enriched.operator_company_url = company_info.url or enriched.operator_company_url
                    enriched.operator_company = company_info_to_operator(company_info)

                # Add tokushoho emails
                if tokushoho_data.email:
                    all_emails.append((
                        DiscoveredEmail(
                            email=tokushoho_data.email,
                            email_type=EmailType.ONLINE_SHOP if _is_online_shop_page(page_text) else EmailType.GENERAL_BUSINESS,
                            source_url=page_url,
                            source_snippet=tokushoho_data.email,
                            source_page_type="tokushoho",
                            confidence=0.85,
                        ),
                        page_url,
                    ))

                # Online shop detection
                if _is_online_shop_page(page_text):
                    enriched.online_shop_detected = True

    # ---- Step 8: Resolve operator company from other pages ----
    if not enriched.operator_company_name:
        for page_url, page_html, page_text in crawled_pages:
            page_type = _detect_page_type(page_url, page_html, page_text)
            if page_type in ("company", "recruitment", "pr"):
                company_info = resolve_from_page(page_url, page_text, page_type)
                if company_info and company_info.name:
                    enriched.operator_company_name = company_info.name
                    enriched.operator_company_url = company_info.url or enriched.operator_company_url
                    enriched.operator_company = company_info_to_operator(company_info)
                    if page_type == "recruitment":
                        enriched.recruitment_page_url = page_url
                    elif page_type == "pr":
                        enriched.pr_page_url = page_url
                    break

    # ---- Step 9: Crawl operator company site (if resolved) ----
    if enriched.operator_company_url and not config.dry_run:
        op_html, op_text, op_final = _fetch_page(
            enriched.operator_company_url,
            timeout=config.search.page_timeout,
            user_agent=config.search.user_agent,
        )
        if op_html:
            # Extract emails from operator site
            op_extracted = extract_emails_from_page(html=op_html, visible_text=op_text, source_url=op_final)
            for ext in op_extracted:
                classified_type = classify_email(ext, source_page_type="company")
                all_emails.append((
                    DiscoveredEmail(
                        email=ext.email,
                        email_type=classified_type,
                        source_url=op_final,
                        source_snippet=ext.context[:200],
                        source_page_type="operator",
                        confidence=0.7,
                    ),
                    op_final,
                ))

            # Crawl operator contact page
            op_links = _extract_links(op_html, op_final)
            for link in op_links:
                link_lower = link.lower()
                if any(t in link_lower for t in ("contact", "inquiry", "お問い合わせ", "company", "会社")):
                    c_html, c_text, c_final = _fetch_page(link, timeout=config.search.page_timeout)
                    if c_html:
                        c_extracted = extract_emails_from_page(html=c_html, visible_text=c_text, source_url=c_final)
                        for ext in c_extracted:
                            classified_type = classify_email(ext, source_page_type="company")
                            all_emails.append((
                                DiscoveredEmail(
                                    email=ext.email,
                                    email_type=classified_type,
                                    source_url=c_final,
                                    source_snippet=ext.context[:200],
                                    source_page_type="operator",
                                    confidence=0.75,
                                ),
                                c_final,
                            ))
                    time.sleep(config.search.rate_limit_delay * 0.5)

    # ---- Step 10: Detect menu ----
    for page_url, page_html, page_text in crawled_pages:
        menu_result = detect_menu_in_html(page_html, page_text)
        if menu_result.has_menu:
            enriched.menu_detected = True
            if not enriched.menu_url:
                enriched.menu_url = page_url
            break

    if not enriched.menu_detected and enriched.menu_url:
        enriched.menu_detected = True

    # ---- Step 11: Compliance check ----
    for page_url, page_html, page_text in crawled_pages:
        compliance = check_compliance(page_text)
        if compliance.has_refusal_warning:
            enriched.no_sales_warning = True
            break

    # ---- Step 12: Select best email ----
    ranked = rank_emails(all_emails)
    # Deduplicate emails
    seen_emails: dict[str, DiscoveredEmail] = {}
    for email, page_url in ranked:
        if email.email not in seen_emails:
            seen_emails[email.email] = email

    enriched.all_emails = list(seen_emails.values())

    # Check compliance for each email
    best_safe_email = None
    for email in enriched.all_emails:
        is_safe, reason = is_email_safe_to_contact(
            email.email,
            email.source_snippet,
            email.source_snippet,
        )
        if is_safe and best_safe_email is None:
            best_safe_email = email
        if not is_safe:
            # Downgrade type
            email.email_type = EmailType.DO_NOT_CONTACT

    if best_safe_email:
        enriched.best_email = best_safe_email.email
        enriched.best_email_type = best_safe_email.email_type.value
        enriched.email_source_url = best_safe_email.source_url
        enriched.email_source_snippet = best_safe_email.source_snippet

    # Select best contact form
    official_forms = [f for f in all_forms if f.form_type == "official"]
    if official_forms:
        enriched.contact_form_url = official_forms[0].url

    # ---- Step 13: Score ----
    score_lead(enriched, config)

    # ---- Step 14: Launch readiness ----
    _determine_launch_readiness(enriched, config)

    # ---- Step 15: Next best action ----
    _determine_next_action(enriched)

    _finalize(enriched, config, start)
    return enriched


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prioritize_links(links: list[str], base_url: str) -> list[str]:
    """Prioritize links for crawling: contact, company, tokushoho, menu pages first."""
    priority_terms = [
        # Contact pages (highest priority)
        "contact", "お問い合わせ", "inquiry", "toiawase",
        # Tokushoho pages
        "tokushoho", "特定商取引", "特商法", "legal",
        # Company pages
        "company", "会社概要", "about", "運営会社",
        # Online shop
        "shop", "online", "通販", "store",
        # Menu
        "menu", "メニュー",
    ]

    scored: list[tuple[str, int]] = []
    base_domain = ""
    try:
        from urllib.parse import urlparse
        base_domain = urlparse(base_url).netloc
    except Exception:
        pass

    for link in links:
        link_lower = link.lower()
        score = 0

        # Prefer same-domain links
        if base_domain and base_domain in link:
            score += 100

        for i, term in enumerate(priority_terms):
            if term.lower() in link_lower:
                score += (len(priority_terms) - i) * 10
                break

        scored.append((link, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [link for link, _ in scored]


def _detect_page_type(url: str, html: str, text: str) -> str:
    """Detect the type of a page based on URL and content."""
    url_lower = url.lower()
    text_lower = (text or "").lower()
    combined = url_lower + " " + text_lower[:500]

    if any(t in combined for t in TOKUSHOHO_INDICATORS):
        return "tokushoho"
    if any(t in combined for t in ("求人", "採用", "recruit", "career", "job")):
        return "recruitment"
    if any(t in combined for t in ("会社概要", "company", "about", "運営会社", "企業情報")):
        return "company"
    if any(t in combined for t in ("お問い合わせ", "contact", "inquiry")):
        return "contact"
    if any(t in combined for t in ONLINE_SHOP_INDICATORS):
        return "online_shop"
    if any(t in combined for t in ("pr", "press", "media", "release", "プレス")):
        return "pr"
    if any(t in combined for t in ("menu", "メニュー", "品書き")):
        return "menu"

    return "unknown"


def _is_online_shop_page(text: str) -> bool:
    """Check if a page is an online shop page."""
    text_lower = text.lower()
    return any(term in text_lower for term in ONLINE_SHOP_INDICATORS)


def _extract_title(html: str) -> str:
    """Extract page title from HTML."""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _email_confidence(method: str, email_type: EmailType) -> float:
    """Calculate email confidence based on extraction method and type."""
    method_score = {
        "mailto": 0.9,
        "prefix": 0.85,
        "fullwidth": 0.8,
        "bracket": 0.75,
        "star": 0.7,
        "standard": 0.6,
    }.get(method, 0.5)

    type_score = {
        EmailType.GENERAL_BUSINESS: 0.9,
        EmailType.OPERATOR_COMPANY: 0.8,
        EmailType.ONLINE_SHOP: 0.75,
        EmailType.MEDIA_PR: 0.6,
        EmailType.RECRUITMENT: 0.4,
        EmailType.RESERVATION: 0.3,
        EmailType.PERSONAL_OR_UNCLEAR: 0.3,
        EmailType.LOW_CONFIDENCE: 0.2,
        EmailType.DO_NOT_CONTACT: 0.0,
    }.get(email_type, 0.3)

    return (method_score + type_score) / 2


def _determine_launch_readiness(lead: EnrichedLead, config: DiscoveryConfig) -> None:
    """Determine if a lead is launch-ready."""
    threshold = config.scoring.launch_ready_threshold

    ready = True

    # Genre must be approved
    if not lead.genre or lead.genre_confidence < config.scoring.genre_confidence_threshold:
        # If genre wasn't classified but we have genre text, check if it's at least somewhat matching
        if not lead.genre:
            ready = False

    # Must have approved contact route
    if not lead.best_email and not lead.contact_form_url:
        ready = False

    # No refusal warning
    if lead.no_sales_warning:
        ready = False

    # Score must exceed threshold
    if lead.confidence_score < threshold:
        ready = False

    lead.launch_ready = ready


def _determine_next_action(lead: EnrichedLead) -> None:
    """Determine the next best action for a lead."""
    if lead.no_sales_warning:
        lead.next_best_action = NextBestAction.SKIP_DNC.value
        return

    if lead.confidence_score < 30:
        if not lead.best_email and not lead.contact_form_url:
            if not lead.operator_company_name:
                lead.next_best_action = NextBestAction.RESEARCH_OPERATOR.value
            else:
                lead.next_best_action = NextBestAction.SKIP_NO_CONTACT.value
            return

    if lead.best_email:
        lead.next_best_action = NextBestAction.SEND_EMAIL.value
        return

    if lead.contact_form_url:
        lead.next_best_action = NextBestAction.USE_CONTACT_FORM.value
        return

    if not lead.operator_company_name:
        lead.next_best_action = NextBestAction.RESEARCH_OPERATOR.value
        return

    lead.next_best_action = NextBestAction.SKIP_NO_CONTACT.value


def _finalize(lead: EnrichedLead, config: DiscoveryConfig, start_time: float) -> None:
    """Final scoring pass and logging."""
    if not lead.reason_codes:
        lead.reason_codes = [ReasonCode.NO_EMAIL_FOUND.value]

    elapsed = time.time() - start_time
    logger.info(
        "[%s] %s — score %.1f, email=%s, form=%s, ready=%s (%.1fs)",
        lead.lead_id, lead.shop_name, lead.confidence_score,
        lead.best_email or "none",
        "yes" if lead.contact_form_url else "no",
        lead.launch_ready,
        elapsed,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def discover_emails(
    input_csv: str,
    config_path: Optional[str] = None,
    config: Optional[DiscoveryConfig] = None,
) -> list[EnrichedLead]:
    """Run the full email discovery pipeline.

    Args:
        input_csv: Path to input CSV file.
        config_path: Optional path to config YAML.
        config: Pre-loaded config (overrides config_path).

    Returns:
        List of enriched leads.
    """
    if config is None:
        config = load_config(config_path)

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    logger.info("=== Email Discovery Pipeline ===")
    logger.info("Config: provider=%s, dry_run=%s", config.search.provider, config.dry_run)

    # Load leads
    leads = load_leads_csv(input_csv)
    if not leads:
        logger.warning("No leads loaded from %s", input_csv)
        return []

    if config.max_leads > 0:
        leads = leads[:config.max_leads]

    logger.info("Processing %d leads", len(leads))

    # Process each lead
    results: list[EnrichedLead] = []
    db = DiscoveryDB(config.persistence.sqlite_path)

    try:
        for i, lead in enumerate(leads):
            logger.info("Processing lead %d/%d: %s", i + 1, len(leads), lead.shop_name)

            enriched = process_lead(lead, config)
            results.append(enriched)

            # Persist to SQLite
            db.upsert_lead(enriched)
            for email in enriched.all_emails:
                db.insert_email(enriched.lead_id, email)

    finally:
        db.close()

    # Write output files
    output_paths = write_outputs(
        results,
        csv_path=config.persistence.csv_output_path,
        jsonl_path=config.persistence.jsonl_output_path,
    )
    logger.info("Output: %s", output_paths)

    # Summary
    launch_ready = sum(1 for r in results if r.launch_ready)
    with_email = sum(1 for r in results if r.best_email)
    with_form = sum(1 for r in results if r.contact_form_url)
    avg_score = sum(r.confidence_score for r in results) / len(results) if results else 0

    logger.info("=== Summary ===")
    logger.info("Total: %d, Launch-ready: %d, With email: %d, With form: %d, Avg score: %.1f",
                len(results), launch_ready, with_email, with_form, avg_score)

    return results
