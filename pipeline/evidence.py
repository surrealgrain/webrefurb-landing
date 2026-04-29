from __future__ import annotations

import re
import urllib.parse
from typing import Any

from .constants import (
    RAMEN_MENU_TERMS, RAMEN_CATEGORY_TERMS, TICKET_MACHINE_TERMS,
    TICKET_MACHINE_ABSENCE_TERMS,
    IZAKAYA_MENU_TERMS, IZAKAYA_CATEGORY_TERMS, COURSE_DRINK_PLAN_TERMS,
    _FOOD_DRINK_TOKENS, _DIRECTORY_HOST_TOKENS, _PURCHASE_CRITICAL_TOKENS,
    _IMAGE_LOCKED_TOKENS, _MENU_LINK_TOKENS, _ENGLISH_LINK_TOKENS,
    _CHAIN_SEED_NAMES, _BRANCH_PATTERN_RE, _ROMAJI_BRANCH_SUFFIXES,
    _CAPTCHA_TOKENS,
    _JS_EMPTY_INDICATORS, _FILENAME_MENU_PATTERNS, _UNREADABLE_IMAGE_TOKENS,
    _MENU_ITEM_SEP_RE, PRICE_RE, EXCLUDED_BUSINESS_TOKENS,
)
from .models import EvidenceAssessment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalize_item(item: str) -> str:
    return re.sub(r"[^\w\s]", "", item.strip().lower())


def _distinct_items(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        norm = _normalize_item(item)
        if norm and norm not in seen:
            seen.add(norm)
            result.append(item)
    return result


def _unique_snippets(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        cleaned = re.sub(r"\s+", " ", str(item or "")).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        output.append(cleaned[:260])
    return output


def _is_readable_image_source(src: str, alt: str, title: str) -> bool:
    haystack = f"{src} {alt} {title}".lower()
    return not any(token in haystack for token in _UNREADABLE_IMAGE_TOKENS)


def _min_text_for_menu_evidence(text: str, *, min_chars: int = 40) -> bool:
    return len(text.strip()) >= min_chars


def _multiple_menu_items_detected(text: str) -> bool:
    if not text:
        return False
    prices = _distinct_items(PRICE_RE.findall(text))
    ramen_items = _distinct_items([term for term in RAMEN_MENU_TERMS if term in text])
    izakaya_items = _distinct_items([term for term in IZAKAYA_MENU_TERMS if term in text])
    food_items = ramen_items + izakaya_items
    separators = len(_MENU_ITEM_SEP_RE.findall(text))
    return (
        len(prices) >= 2
        or len(_distinct_items(food_items)) >= 3
        or separators >= 3
    )


def _has_orderable_menu_detail(
    text: str,
    *,
    page_has_prices: bool,
    page_ramen_terms: list[str],
    page_izakaya_terms: list[str],
) -> bool:
    """Require concrete menu detail, not just a generic "menu" reference."""
    if not text:
        return False
    if page_has_prices and (page_ramen_terms or page_izakaya_terms):
        return True
    if _multiple_menu_items_detected(text):
        return True
    if len(_distinct_items(page_ramen_terms + page_izakaya_terms)) >= 3:
        return True
    return False


def _is_review_or_directory_url(url: str) -> bool:
    lowered = str(url or "").lower()
    return any(token in lowered for token in ("google.", "maps.", "tabelog.", "tripadvisor.", "yelp.", "review", "口コミ"))


def _sentences_near(text: str, tokens: set[str]) -> str:
    sentences = re.split(r"(?<=[。！？.!?])\s+|\n+", text or "")
    found: list[str] = []
    lowered_tokens = {token.lower() for token in tokens}
    for sentence in sentences:
        lowered = sentence.lower()
        if any(token in lowered for token in lowered_tokens):
            found.append(sentence.strip())
        if len(found) >= 8:
            break
    return " ".join(found)


def _best_sentence(text: str, tokens: set[str]) -> str:
    return _sentences_near(text, tokens).split("。")[0][:220]


def _count_japanese_chars(text: str) -> int:
    return len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff]", text or ""))


def _count_latin_words(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z'-]{2,}\b", text or ""))


# ---------------------------------------------------------------------------
# Page-level guards
# ---------------------------------------------------------------------------
def is_invalid_page(payload: dict[str, Any]) -> bool:
    """Return True if the page is placeholder, captcha, JS-empty, or content-too-short."""
    text = str(payload.get("text") or "").strip()
    html = str(payload.get("html") or "").lower()
    combined = f"{text}\n{html}".lower()
    placeholder_tokens = (
        "password protected", "enter password", "this shop will be powered by",
        "coming soon", "under construction", "opening soon", "site coming soon",
        "placeholder page", "site placeholder", "パスワード", "準備中", "工事中", "近日公開",
    )
    if any(token in combined for token in placeholder_tokens) and not _has_substantive_restaurant_content(text):
        return True
    if any(token in combined for token in _CAPTCHA_TOKENS):
        return True
    if any(token in combined for token in _JS_EMPTY_INDICATORS):
        return True
    if len(text) < 24 and not (payload.get("images") or payload.get("links")):
        return True
    return False


def is_chain_business(business_name: str) -> bool:
    lowered = business_name.strip().lower()
    if any(chain in lowered for chain in _CHAIN_SEED_NAMES):
        return True
    if _BRANCH_PATTERN_RE.search(business_name):
        return True
    if any(suffix in business_name for suffix in _ROMAJI_BRANCH_SUFFIXES):
        return True
    return False


_CHAIN_INFRA_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("franchise_recruiting", re.compile(r"(?i)(fc募集|franchise|フランチャイズ|加盟店募集|加盟募集)")),
    ("numbered_branch_store", re.compile(r"\d+\s*号店")),
    ("store_directory_with_chain_context", re.compile(
        r"((店舗一覧|店舗検索|店舗リスト|全店舗|店舗情報一覧).{0,32}(全国|チェーン|フランチャイズ|ブランド|店舗数|\d{2,}\s*店舗)"
        r"|(全国|チェーン|フランチャイズ|ブランド|店舗数|\d{2,}\s*店舗).{0,32}(店舗一覧|店舗検索|店舗リスト|全店舗|店舗情報一覧))"
    )),
    ("store_directory_standalone", re.compile(r"(店舗一覧|店舗情報一覧|全店舗)")),
    ("chain_expansion", re.compile(r"(チェーン店|チェーン展開|全国展開|多店舗展開)")),
    ("multi_location_expansion", re.compile(r"(全国|各地|複数|多店舗).{0,24}(店舗|展開|運営)")),
    ("large_store_count", re.compile(r"(店舗数|全国).{0,16}\d{2,}\s*店舗|\d{2,}\s*店舗.{0,18}(展開|運営)")),
    ("brand_portfolio", re.compile(r"(ブランド一覧|外食ブランド|運営店舗|系列店舗|グループ店舗)")),
)


def chain_or_franchise_signal_reason(text: str, *, business_name: str = "") -> str:
    """Return a strong chain/franchise signal reason from page/search text."""
    haystack = re.sub(r"\s+", " ", str(text or "")).strip()
    if not haystack and not business_name:
        return ""

    # Check business name against seed names and romaji branch suffixes
    lowered_name = business_name.lower()
    if any(chain in lowered_name for chain in _CHAIN_SEED_NAMES):
        return "known_chain_brand"
    if _BRANCH_PATTERN_RE.search(business_name):
        return "branch_name_suffix"
    if any(suffix in business_name for suffix in _ROMAJI_BRANCH_SUFFIXES):
        return "romaji_branch_suffix"

    # Check text content
    lowered = haystack.lower()
    if any(chain in lowered for chain in _CHAIN_SEED_NAMES):
        return "known_chain_brand"
    for reason, pattern in _CHAIN_INFRA_PATTERNS:
        if pattern.search(haystack):
            return reason
    if _looks_like_multi_store_listing(haystack):
        return "multi_store_listing"
    return ""


def has_chain_or_franchise_infrastructure(text: str, *, business_name: str = "") -> bool:
    return bool(chain_or_franchise_signal_reason(text, business_name=business_name))


def _looks_like_multi_store_listing(text: str) -> bool:
    """Catch official pages that list several branches without saying franchise."""
    if not text:
        return False
    context = ("店舗一覧", "店舗紹介", "店舗情報", "店舗リスト", "会社概要", "株式会社", "有限会社", "展開", "グループ")
    if not any(token in text for token in context):
        return False
    if "店舗一覧" in text and "展開" in text:
        return True

    store_names = {
        match.group(0)
        for match in re.finditer(r"[\w\u3040-\u30ff\u3400-\u9fff]{2,18}(?:本店|店)", text)
    }
    tel_blocks = re.findall(r"(?i)(?:tel|電話|電話番号)\s*[:：]?\s*\d{2,4}[-ー−]?\d{2,4}", text)
    address_blocks = re.findall(r"(?:東京都|大阪府|京都府|北海道|福岡県|神奈川県|千葉県|埼玉県|兵庫県|愛知県).{0,24}(?:区|市|町|村)", text)
    return len(store_names) >= 3 and (len(tel_blocks) >= 2 or len(address_blocks) >= 2)


def is_excluded_business(business_name: str, category: str = "") -> bool:
    """Detect sushi, yakiniku, kaiseki, cafe, bakery, hotel, etc."""
    haystack = f"{business_name} {category}".lower()
    return any(token in haystack for token in EXCLUDED_BUSINESS_TOKENS)


def classify_primary_category(text: str, category: str = "") -> str:
    """Return 'ramen', 'izakaya', or 'other'."""
    category_value = str(category or "").strip().lower()
    haystack = f"{text} {category}".lower()
    text_haystack = str(text or "").lower()
    has_ramen = any(term.lower() in text_haystack for term in RAMEN_CATEGORY_TERMS)
    has_izakaya = any(term.lower() in text_haystack for term in IZAKAYA_CATEGORY_TERMS)
    if category_value in {"ramen", "ラーメン"} and not (has_izakaya and not has_ramen):
        return "ramen"
    if category_value in {"izakaya", "居酒屋"} and not (has_ramen and not has_izakaya):
        return "izakaya"
    if any(term.lower() in haystack for term in RAMEN_CATEGORY_TERMS):
        return "ramen"
    if any(term.lower() in haystack for term in IZAKAYA_CATEGORY_TERMS):
        return "izakaya"
    return "other"


# ---------------------------------------------------------------------------
# Website / URL helpers
# ---------------------------------------------------------------------------
def has_public_website(website: str) -> bool:
    parsed = urllib.parse.urlparse(website if website.startswith(("http://", "https://")) else f"https://{website}")
    host = (parsed.netloc or "").lower()
    return bool(host) and not any(token in host for token in _DIRECTORY_HOST_TOKENS)


def has_social_url_only(website: str) -> bool:
    parsed = urllib.parse.urlparse(website if website.startswith(("http://", "https://")) else f"https://{website}")
    host = (parsed.netloc or "").lower()
    return any(token in host for token in ("facebook.com", "instagram.com", "x.com", "twitter.com", "tiktok.com"))


def has_english_intent(website: str, payloads: list[dict[str, Any]]) -> bool:
    haystack = website.lower()
    for payload in payloads:
        haystack += " " + str(payload.get("url") or "").lower()
        for link in payload.get("links") or []:
            haystack += " " + str(link.get("href") or "").lower() + " " + str(link.get("text") or "").lower()
    return any(token in haystack for token in _ENGLISH_LINK_TOKENS)


def looks_high_quality_english(payloads: list[dict[str, Any]]) -> bool:
    all_html = "\n".join(str(payload.get("html") or "") for payload in payloads)
    if any(marker in all_html for marker in ("skiptranslate", "goog-te-", "google_translate_element")):
        return False
    relevant = "\n".join(
        _sentences_near(str(payload.get("text") or ""), _PURCHASE_CRITICAL_TOKENS)
        for payload in payloads
        if any(token in str(payload.get("url") or "").lower() for token in _ENGLISH_LINK_TOKENS)
    )
    if not relevant:
        relevant = "\n".join(str(payload.get("text") or "") for payload in payloads)
    source_chars = _count_japanese_chars(relevant)
    latin = _count_latin_words(relevant)
    critical_english = sum(1 for token in ("menu", "ingredients", "allergen", "hours", "order", "reservation") if token in relevant.lower())
    return latin >= 60 and source_chars < 20 and critical_english >= 3


# ---------------------------------------------------------------------------
# Image-locked evidence
# ---------------------------------------------------------------------------
def image_locked_evidence(payloads: list[dict[str, Any]]) -> list[str]:
    evidence: list[str] = []
    for payload in payloads:
        url = str(payload.get("url") or "")
        for image in payload.get("images") or []:
            haystack = " ".join(str(image.get(key) or "") for key in ("src", "alt", "title")).lower()
            if any(token in haystack for token in _IMAGE_LOCKED_TOKENS):
                evidence.append(f"Image-locked content on {url}: {haystack[:120]}")
        for link in payload.get("links") or []:
            href = str(link.get("href") or "").lower()
            text = str(link.get("text") or "").lower()
            if href.endswith(".pdf") and any(token in f"{href} {text}" for token in _IMAGE_LOCKED_TOKENS):
                evidence.append(f"PDF content on {url}: {(text or href)[:120]}")
    return _unique_snippets(evidence)


# ---------------------------------------------------------------------------
# Main evidence assessment
# ---------------------------------------------------------------------------
def assess_evidence(
    *,
    business_name: str,
    website: str,
    category: str,
    payloads: list[dict[str, Any]],
) -> EvidenceAssessment:
    combined_text = "\n".join(str(payload.get("text") or "") for payload in payloads)
    combined_html = "\n".join(str(payload.get("html") or "") for payload in payloads)
    haystack = " ".join([business_name, website, category, combined_text, combined_html]).lower()

    evidence_classes: list[str] = []
    snippets: list[str] = []
    evidence_urls: list[str] = []
    score = 0
    menu_evidence_found = False
    machine_evidence_found = False
    course_or_drink_plan_evidence_found = False
    is_ramen_candidate = any(term.lower() in haystack for term in RAMEN_CATEGORY_TERMS)
    is_izakaya_candidate = any(term.lower() in haystack for term in IZAKAYA_CATEGORY_TERMS)

    # Hard reject check (placeholder/password pages)
    hard_reject = _hard_reject_reason(payloads)
    if hard_reject:
        return EvidenceAssessment(
            is_ramen_candidate=is_ramen_candidate,
            is_izakaya_candidate=is_izakaya_candidate,
            evidence_classes=["placeholder_or_password_page"],
            menu_evidence_found=False,
            machine_evidence_found=False,
            course_or_drink_plan_evidence_found=False,
            score=-10,
            evidence_urls=[str(p.get("url") or "") for p in payloads if p.get("url")],
            best_evidence_url=None,
            best_evidence_reason=hard_reject,
            false_positive_risk="high",
            hard_reject_reason=hard_reject,
        )

    # Filter out invalid pages per-page
    valid_payloads = [p for p in payloads if not is_invalid_page(p)]
    if not valid_payloads:
        return EvidenceAssessment(
            is_ramen_candidate=is_ramen_candidate,
            is_izakaya_candidate=is_izakaya_candidate,
            evidence_classes=["invalid_page_filtered"],
            menu_evidence_found=False,
            machine_evidence_found=False,
            course_or_drink_plan_evidence_found=False,
            score=-10,
            evidence_urls=[str(p.get("url") or "") for p in payloads if p.get("url")],
            best_evidence_url=None,
            best_evidence_reason="All pages are invalid (captcha, JS-empty, placeholder, or content too short).",
            false_positive_risk="high",
            hard_reject_reason="all pages invalid",
        )

    for payload in valid_payloads:
        url = str(payload.get("url") or website)
        text = str(payload.get("text") or "")
        page_haystack = f"{url} {text}".lower()
        source_chars = _count_japanese_chars(text)
        page_has_prices = bool(PRICE_RE.search(text))
        page_ramen_terms = [term for term in RAMEN_MENU_TERMS if term in text]
        page_izakaya_terms = [term for term in IZAKAYA_MENU_TERMS if term in text]
        page_menu_tokens = any(token in page_haystack for token in ("menu", "メニュー", "お品書き", "品書き", "料理", "税込", "商品"))
        page_ticket_absence_tokens = any(token.lower() in page_haystack for token in TICKET_MACHINE_ABSENCE_TERMS)
        page_machine_tokens = (
            any(token.lower() in page_haystack for token in TICKET_MACHINE_TERMS)
            and not page_ticket_absence_tokens
        )
        page_course_tokens = any(token.lower() in page_haystack for token in COURSE_DRINK_PLAN_TERMS)

        if page_ticket_absence_tokens:
            evidence_classes.append("ticket_machine_absence_evidence")
            snippets.append(_best_sentence(text, set(TICKET_MACHINE_ABSENCE_TERMS)) or "Ticket machine absence evidence found.")
            score += 1

        if page_machine_tokens:
            machine_evidence_found = True
            evidence_classes.append("official_ticket_machine_photo" if not _is_review_or_directory_url(url) else "review_ticket_machine_photo")
            evidence_urls.append(url)
            snippets.append(_best_sentence(text, set(TICKET_MACHINE_TERMS)) or f"Ticket machine evidence on {url}")
            score += 4
            if page_ramen_terms:
                score += 3
            if page_has_prices:
                score += 2

        if page_course_tokens:
            course_or_drink_plan_evidence_found = True
            menu_evidence_found = True
            evidence_classes.append("nomihodai_menu" if any(term in text for term in ("飲み放題", "nomihodai", "all-you-can-drink")) else "course_menu")
            evidence_urls.append(url)
            snippets.append(_best_sentence(text, set(COURSE_DRINK_PLAN_TERMS)) or text[:180])
            score += 3

        has_orderable_detail = _has_orderable_menu_detail(
            text,
            page_has_prices=page_has_prices,
            page_ramen_terms=page_ramen_terms,
            page_izakaya_terms=page_izakaya_terms,
        )
        if page_menu_tokens and (page_ramen_terms or page_izakaya_terms or page_has_prices or source_chars >= 12):
            if not _min_text_for_menu_evidence(text):
                pass
            elif not has_orderable_detail:
                evidence_classes.append("thin_menu_reference")
                snippets.append(_best_sentence(text, {"メニュー", "お品書き", "menu"}) or text[:180])
                score -= 1
            elif _is_review_or_directory_url(url):
                if _multiple_menu_items_detected(text):
                    menu_evidence_found = True
                    evidence_urls.append(url)
                    evidence_classes.append("review_menu_photo")
                    score += 2
                    snippets.append(_best_sentence(text, set(RAMEN_MENU_TERMS) | set(IZAKAYA_MENU_TERMS) | {"メニュー", "お品書き", "menu", "税込"}) or text[:180])
            else:
                menu_evidence_found = True
                evidence_urls.append(url)
                if url.lower().endswith(".pdf"):
                    evidence_classes.append("official_pdf_menu")
                    score += 4
                else:
                    evidence_classes.append("official_html_menu")
                    score += 4
                snippets.append(_best_sentence(text, set(RAMEN_MENU_TERMS) | set(IZAKAYA_MENU_TERMS) | {"メニュー", "お品書き", "menu", "税込"}) or text[:180])

        if page_ramen_terms:
            score += 2
        if page_izakaya_terms:
            score += 2
        if page_has_prices:
            score += 2
        if _multiple_menu_items_detected(text):
            score += 2
        if text and not page_menu_tokens and not page_machine_tokens and not page_ramen_terms:
            evidence_classes.append("generic_business_page")

        # Image evidence
        for image in payload.get("images") or []:
            image_haystack = " ".join(str(image.get(key) or "") for key in ("src", "alt", "title")).lower()
            image_label = " ".join(str(image.get(key) or "") for key in ("src", "alt", "title"))
            image_url = urllib.parse.urljoin(url, str(image.get("src") or ""))

            if any(term.lower() in image_haystack for term in TICKET_MACHINE_TERMS):
                machine_evidence_found = True
                evidence_classes.append("official_ticket_machine_photo" if not _is_review_or_directory_url(url) else "review_ticket_machine_photo")
                evidence_urls.append(image_url or url)
                snippets.append(f"Ticket machine image: {image_label[:180]}")
                score += 4
                if any(term in image_label for term in RAMEN_MENU_TERMS):
                    score += 3
                if PRICE_RE.search(image_label):
                    score += 2
            elif any(term.lower() in image_haystack for term in COURSE_DRINK_PLAN_TERMS):
                menu_evidence_found = True
                course_or_drink_plan_evidence_found = True
                evidence_urls.append(image_url or url)
                evidence_classes.append("nomihodai_menu" if any(term in image_label for term in ("飲み放題", "nomihodai", "all-you-can-drink")) else "course_menu")
                snippets.append(f"Course/drink plan menu image: {image_label[:180]}")
                score += 3
            elif any(token in image_haystack for token in ("menu", "メニュー", "お品書き", "wall menu", "printed menu", "menu board")):
                menu_evidence_found = True
                evidence_urls.append(image_url or url)
                if any(token in image_haystack for token in ("drink", "beer", "sake", "生ビール", "日本酒", "サワー", "ドリンク")):
                    evidence_classes.append("drink_menu_photo")
                    score += 3
                elif any(token in image_haystack for token in ("handwritten", "手書き")):
                    evidence_classes.append("handwritten_menu_photo")
                    score += 3
                elif any(token in image_haystack for token in ("wall", "board", "掲示", "店内")):
                    evidence_classes.append("wall_menu_photo")
                    score += 3
                elif any(token in image_haystack for token in ("printed", "paper", "紙", "卓上")):
                    evidence_classes.append("printed_menu_photo")
                    score += 3
                else:
                    evidence_classes.append("official_menu_image" if not _is_review_or_directory_url(url) else "review_menu_photo")
                    score += 2 if _is_review_or_directory_url(url) else 3
                snippets.append(f"Menu image: {image_label[:180]}")
            elif any(token in image_haystack for token in ("ramen", "ラーメン", "food", "dish", "bowl", "麺", "sashimi", "yakitori", "刺身", "焼き鳥")):
                evidence_classes.append("food_only_photo")
                score -= 3
            elif any(token in image_haystack for token in ("storefront", "exterior", "入口", "外観", "front")):
                evidence_classes.append("storefront_only_photo")
                score -= 3
            else:
                src_lower = str(image.get("src") or "").lower()
                src_filename = src_lower.split("/")[-1].split("?")[0] if src_lower else ""
                if src_filename and any(p in src_filename for p in _FILENAME_MENU_PATTERNS):
                    if _is_readable_image_source(str(image.get("src") or ""), str(image.get("alt") or ""), str(image.get("title") or "")):
                        menu_evidence_found = True
                        evidence_classes.append("menu_image_by_filename")
                        evidence_urls.append(image_url or url)
                        snippets.append(f"Menu image detected by filename: {src_filename[:120]}")
                        score += 1
            if any(token in image_haystack for token in ("blur", "blurry", "unreadable", "不鮮明")):
                score -= 3

        # PDF menu links
        for link in payload.get("links") or []:
            href = str(link.get("href") or "")
            link_text = str(link.get("text") or "")
            link_haystack = f"{href} {link_text}".lower()
            if href.lower().endswith(".pdf") and any(token in link_haystack for token in ("menu", "メニュー", "お品書き")):
                menu_evidence_found = True
                evidence_classes.append("official_pdf_menu")
                evidence_urls.append(urllib.parse.urljoin(url, href))
                score += 4

    # Risk assessment
    if "generic_business_page" in evidence_classes and not (menu_evidence_found or machine_evidence_found):
        score -= 3
    if not menu_evidence_found and not machine_evidence_found:
        evidence_classes.append("no_menu_evidence")
    if menu_evidence_found and any(cls in evidence_classes for cls in ("official_html_menu", "official_pdf_menu", "nomihodai_menu", "course_menu")):
        score = max(score, 7)
    if machine_evidence_found:
        score = max(score, 7)

    best_url = evidence_urls[0] if evidence_urls else (str(payloads[0].get("url") or website) if payloads else website)
    reason = "Ticket machine evidence is strongest." if machine_evidence_found else "Menu evidence is strongest." if menu_evidence_found else "No usable menu or machine evidence was found."
    risk = "low" if score >= 9 and (menu_evidence_found or machine_evidence_found) else "medium"
    if "food_only_photo" in evidence_classes or "storefront_only_photo" in evidence_classes or "generic_business_page" in evidence_classes:
        risk = "high" if not (menu_evidence_found or machine_evidence_found) else "medium"
    if "review_menu_photo" in evidence_classes:
        risk = "medium" if risk == "low" else risk

    return EvidenceAssessment(
        is_ramen_candidate=is_ramen_candidate,
        is_izakaya_candidate=is_izakaya_candidate,
        evidence_classes=_unique_snippets(evidence_classes),
        menu_evidence_found=menu_evidence_found,
        machine_evidence_found=machine_evidence_found,
        course_or_drink_plan_evidence_found=course_or_drink_plan_evidence_found,
        score=score,
        evidence_urls=_unique_snippets(evidence_urls),
        best_evidence_url=best_url,
        best_evidence_reason=reason,
        false_positive_risk=risk,
        hard_reject_reason=None,
        snippets=_unique_snippets(snippets),
    )


def _hard_reject_reason(payloads: list[dict[str, Any]]) -> str | None:
    text = "\n".join(str(payload.get("text") or "") for payload in payloads)
    html = "\n".join(str(payload.get("html") or "") for payload in payloads)
    lowered = f"{text}\n{html}".lower()
    hard_tokens = (
        "password protected", "enter password", "this shop will be powered by",
        "coming soon", "under construction", "opening soon", "site coming soon",
        "placeholder page", "site placeholder", "パスワード", "準備中", "工事中", "近日公開",
    )
    if any(token in lowered for token in hard_tokens) and not _has_substantive_restaurant_content(text):
        return "placeholder/password/coming-soon page"
    if len(text.strip()) < 24 and not any((payload.get("images") or payload.get("links")) for payload in payloads):
        return "no meaningful body content"
    return None


def _has_substantive_restaurant_content(text: str) -> bool:
    if _count_japanese_chars(text) >= 40 and any(token in text for token in ("メニュー", "料理", "営業時間", "住所", "電話", "ラーメン", "居酒屋", "飲み放題", "コース")):
        return True
    if PRICE_RE.search(text) and any(token in text for token in ("ラーメン", "餃子", "生ビール", "飲み放題", "コース", "メニュー")):
        return True
    return False
