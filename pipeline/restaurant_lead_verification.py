from __future__ import annotations

import json
import re
import urllib.parse
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .business_name import business_name_is_suspicious
from .constants import SOLVED_ENGLISH_SUPPORT_TERMS
from .contact_crawler import is_usable_business_email
from .evidence import chain_or_franchise_signal_reason, is_chain_business, is_excluded_business
from .lead_dossier import READINESS_MANUAL
from .pitch_cards import apply_pitch_card_state, pitch_card_counts
from .record import list_leads, persist_lead_record
from .utils import utc_now, write_json


VERIFICATION_VERSION = "restaurant_lead_verification_v1_1"

TARGET_CITY_HINTS = {
    "Tokyo": ("Tokyo", "東京都"),
    "Osaka": ("Osaka", "大阪府", "大阪市"),
    "Sapporo": ("Sapporo", "北海道", "札幌市"),
    "Fukuoka": ("Fukuoka", "福岡県", "福岡市"),
    "Kyoto": ("Kyoto", "京都府", "京都市"),
}

SUPPORTED_MENU_TYPES = {
    "ramen",
    "tsukemen",
    "abura_soba",
    "mazesoba",
    "tantanmen",
    "chuka_soba",
    "izakaya",
    "kushiyaki",
    "yakiton",
}

DIRECTORY_HOST_TOKENS = (
    "tabelog.com",
    "hotpepper.jp",
    "gnavi.co.jp",
    "gorp.jp",
    "retty.me",
    "tripadvisor.",
    "ubereats.com",
    "menu.st",
    "gurusuguri.com",
    "ktquest.com",
    "e-ekichika.com",
    "fukui291.jp",
    "kyobashi.com",
    "raqmo.com",
    "umakamon.city.fukuoka.lg.jp",
    "fukuoka-furusato.jp",
    "o-2.jp",
    "atod.co.jp",
)

OWNED_PAGE_HOST_TOKENS = (
    "linktr.ee",
    "lit.link",
    "instagram.com",
    "facebook.com",
    "ameblo.jp",
    "peraichi.com",
    "themedia.jp",
    "wixsite.com",
    "stores.jp",
    "thebase.in",
    "goope.jp",
    "my.coocan.jp",
)

WEAK_SOURCE_HOST_TOKENS = (
    "ameba.jp",
    "blogspot.",
    "fooddiversity.today",
    "gourmetpress.net",
    "lalalapo-osaka.com",
    "motion-gallery.net",
    "moshicom.com",
    "omonomi.com",
    "passmarket.yahoo.co.jp",
    "susurulab.co.jp",
    "youtube.com",
    "youtu.be",
    "search.yahoo.co.jp",
    "rssing.com",
    "twitter.com",
    "x.com",
    "note.com",
    "prtimes.jp",
    "value-press.com",
    "infoseek.co.jp",
    "lemon8-app.com",
    "japanhalal.or.jp",
    "japanuu.com",
    "books.gr.jp",
    "kyotobank.co.jp",
    "sotokoto-online.jp",
    "menroku.com",
    "livepocket.jp",
    "taishi-juku.jp",
    "tokujunin.jp",
    "ohtakasho-yu.co.jp",
    "seesaa.net",
    "uplink-app-v3.com",
    "youroad.com",
    "google.com",
)

FREE_MAIL_DOMAINS = {
    "gmail.com",
    "yahoo.co.jp",
    "yahoo.com",
    "icloud.com",
    "outlook.com",
    "hotmail.com",
    "live.jp",
    "outlook.jp",
    "ezweb.ne.jp",
    "i.softbank.jp",
    "mail.com",
    "nifty.ne.jp",
    "nifty.com",
    "att.net",
    "ymail.ne.jp",
    "aol.com",
}

FREE_MAIL_DOMAIN_SUFFIXES = (
    ".ocn.ne.jp",
    ".alpha-net.ne.jp",
    ".or.jp",
)

BAD_EMAIL_LOCAL_PARTS = {
    "sample",
    "example",
    "test",
    "dummy",
    "abcdefg",
    "pr",
    "sendonly",
    "server",
    "wix",
    "x-cloak",
    "xxx",
    "yourmail",
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "support",
    "press",
    "media",
    "recruit",
    "career",
    "job",
    "nfo",
    "saiyo",
    "privacy",
    "abuse",
    "postmaster",
    "webmaster",
    "admin",
}

BAD_EMAIL_LOCAL_PREFIXES = (
    "support",
    "press",
    "media",
    "recruit",
    "career",
    "job",
    "saiyo",
    "u003e",
)

BAD_EMAIL_DOMAINS = {
    "aaaaa.com",
    "domain.com",
    "gamil.com",
}

BAD_EMAIL_DOMAIN_TOKENS = (
    "example.",
    "sample.",
    "tabelog",
    "gnavi",
    "hotpepper",
    "recruit",
    "career",
    "prtimes",
    "instagram",
    "facebook",
    "youtube",
    "kakaku",
    "lemon8-app",
    "kyotobank",
    "city.",
    "city.fukuoka",
)

BAD_EMAIL_DOMAIN_SUFFIXES = (
    ".ac.jp",
    ".lg.jp",
)

BAD_EMAIL_TLDS = {
    "ago",
    "agodashi",
    "cultuurstad",
    "example",
    "gion",
    "invalid",
    "kagurazaka",
    "lard",
    "outside",
    "raz",
    "sai",
    "sanstarholiday",
    "swich",
    "xxx",
}

BAD_NAME_FRAGMENTS = (
    "レポート",
    "求人",
    "採用",
    "ランキング",
    "まとめ",
    "ブログ",
    "ニュース",
    "記事",
    "イベント",
    "特集",
    "検索結果",
    "プレスリリース",
    "ふるさと納税",
    "商業組合",
    "特定商取引法",
    "店舗直送便",
    "優先入場券",
    "マラニック",
    "オープン",
    "OPEN",
    "厳選",
    "オススメ",
    "おすすめ",
    "POPUP",
    "ラーメン企画",
    "グルメウォーク",
    "ハラールレストランを訪ねて",
    "お問い合わせ",
    "問い合わせ",
    "会社概要",
    "企業情報",
    "店舗情報",
    "しょうゆ・つゆ・たれ",
)

BAD_NAME_EXACT = {
    "ABOUT",
    "About",
    "概要",
    "ホーム",
    "店舗案内",
    "お店募集",
    "TAKEOUTのお店",
    "お店のご案内",
    "アクセス・お問い合わせ",
    "問い合わせ",
    "お問い合わせ",
    "会社概要",
    "企業情報・概要",
    "特定商取引法に基づく表記",
}

REVIEW_ARTIFACT_NAME_FRAGMENTS = (
    "もっとも、遅い夏休み",
    "夏休み、の、秋休み",
    "めちゃくちゃ美味しい",
    "抜群に美味しい",
    "リピート必至",
    "SNS映え",
    "完全予約・紹介制",
    "自分で選べる日本酒",
    "新店？",
    "全てに優しい",
    "旬の食材の料理が絶品",
    "生姜の効いた無水パキスタンカレー",
    "確かな味を受け継ぐ",
    "テイクアウトで楽しむ",
    "星陵会館のビュッフェレストラン",
    "フォアグラもなか",
    "トマティカちゃんに逢いに",
)

CLEAR_OUT_OF_SCOPE_CATEGORY_ARTIFACTS = (
    "BEER BAR",
    "Beer Bar",
    "韓国料理",
    "台湾料理",
    "メキシコ料理",
    "スペイン料理",
    "ベネチア料理",
    "バーベキュー",
    "しゃぶしゃぶ",
    "喫茶店",
    "洋菓子",
    "スイーツ",
    "ジェラート",
    "アイスクリーム",
    "パブ",
    "ビアバー",
    "ジャズバー",
    "ゴルフラウンジ",
    "Golf Lounge",
    "ビュッフェ",
    "ロティサリー",
    "かつ丼",
    "上生菓子",
    "雪餅",
    "餃子製造",
    "鮓",
    "寿し",
    "天婦羅",
    "天麩羅",
    "パフェ",
)

DIRECTORY_PARENT_CATEGORY_REJECTS = (
    "バー",
    "パブ",
    "カフェ",
    "喫茶店",
    "バル",
    "パン",
    "洋菓子",
    "スイーツ",
    "ジェラート",
    "アイスクリーム",
    "イタリアン",
    "スペイン料理",
    "フレンチ",
    "バーベキュー",
    "しゃぶしゃぶ",
    "韓国料理",
    "台湾料理",
    "天婦羅",
    "天ぷら",
    "カレー",
    "ワインバー",
    "ダーツ",
    "うどん",
    "立ち食いそば",
)

GENERIC_JAPANESE_CUISINE_SCOPE_REVIEW_TERMS = (
    "割烹",
    "日本料理",
    "和食",
    "食堂",
)

EXPLICIT_IZAKAYA_SCOPE_TERMS = (
    "居酒屋",
    "酒場",
    "焼鳥",
    "焼き鳥",
    "やきとり",
    "串焼",
    "串カツ",
    "串かつ",
    "串揚",
    "おでん",
    "炉端",
    "もつ鍋",
    "もつ焼",
    "やきとん",
)

CORE_SCOPE_NAME_TERMS = (
    "ラーメン",
    "らーめん",
    "中華そば",
    "つけ麺",
    "まぜそば",
    "油そば",
    "担々麺",
    "坦々麺",
    "鶏そば",
    "鳥そば",
    *EXPLICIT_IZAKAYA_SCOPE_TERMS,
)

BRANCH_REVIEW_NAME_RE = re.compile(
    r"(?:本店|支店|"
    r"(?:KITTE|PARCO|ルクア|グランフロント|モール|横丁)[^　\s）)]{0,12}店|"
    r"[^　\s）)]{1,12}(?:駅|口|前|内)[^　\s）)]{0,8}店|"
    r"[^　\s）)]{1,12}(?:博多|梅田|難波|新橋|池袋|金閣寺|新横浜|西中島|山科)[^　\s）)]{0,8}店)"
)

OUT_OF_SCOPE_SOURCE_URL_TOKENS = (
    "/mochishop",
)

KNOWN_CHAIN_NAME_FRAGMENTS = (
    "博多もつ鍋おおやま",
    "SCHMATZ",
    "シュマッツ",
)

KNOWN_CHAIN_DOMAIN_TOKENS = (
    "ajino-tokeidai.co.jp",
    "anacpsapporo.com",
    "bairdbeer.com",
    "daiwa-j.com",
    "dank1.co.jp",
    "doteightcompany.co.jp",
    "eishin-corporation.com",
    "foodee.co.jp",
    "htmc-group.jp",
    "edmont.metropolitan.jp",
    "koko-hotels.com",
    "kushikatsuittoku.com",
    "maidoya.jp",
    "mars-gardenhotel.jp",
    "menya-takei.com",
    "mister-x.jp",
    "minminhonten.com",
    "motu-ooyama.com",
    "nagamitsufarm.com",
    "nihonichi.jp",
    "oizumifoods.co.jp",
    "ohshoclub.jp",
    "opefac.com",
    "parkhotelgroup.com",
    "presidenthotel-hakata.co.jp",
    "restaurant-bank.jp",
    "sapporo-kotetsu.com",
    "schmatz.jp",
    "so-corporation.com",
    "span-co.jp",
    "tcbn.co.jp",
    "teraokagroup.co.jp",
    "theatres.co.jp",
    "toyocamerahouse.com",
)

OPERATOR_REVIEW_DOMAIN_TOKENS = (
    "fun-no1.com",
    "kamolabo.com",
    "seseri.jp",
    "taisyusakaba-sanma.com",
)

OPERATOR_REVIEW_SOURCE_PATH_TOKENS = (
    "/brands/",
    "/business/",
    "/service/",
)

TERMINAL_OUTREACH_STATUSES = {
    "sent",
    "replied",
    "converted",
    "bounced",
    "invalid",
    "skipped",
    "do_not_contact",
    "contacted_form",
}


@dataclass(frozen=True)
class CheckResult:
    status: str
    reason: str
    score: int = 0
    sources: list[str] | None = None


def normalize_email(value: str) -> str:
    cleaned = str(value or "").strip().lower()
    cleaned = re.sub(r"^mailto:", "", cleaned)
    cleaned = cleaned.split("?", 1)[0].strip()
    return cleaned.strip(" \t\r\n<>[](){}.,;:'\"")


def is_restaurant_email_queue_record(record: dict[str, Any]) -> bool:
    lead_id = str(record.get("lead_id") or "")
    source_query = str(record.get("source_query") or "")
    source_file = str(record.get("source_file") or "")
    return (
        lead_id.startswith("wrm-email-")
        or source_query == "restaurant_email_import"
        or "restaurant_email_leads" in source_file
    )


def verify_restaurant_lead_record(record: dict[str, Any], *, checked_at: str | None = None) -> dict[str, Any]:
    checked_at = checked_at or utc_now()
    updated = deepcopy(record)

    source_strength, source_reason = source_strength_for(updated)
    email = _verify_email(updated, source_strength=source_strength)
    name = _verify_name(updated)
    city = _verify_city(updated)
    category = _verify_category(updated)
    english = _verify_english_menu(updated)
    chain = _verify_chain(updated)

    score = min(
        100,
        email.score
        + name.score
        + city.score
        + category.score
        + english.score
        + chain.score
        + _source_strength_score(source_strength),
    )

    rejected_checks = [
        result.reason
        for result in (email, name, city, category, english, chain)
        if result.status == "rejected"
    ]
    if rejected_checks:
        verification_status = "rejected"
        verification_reason = "; ".join(rejected_checks)
    elif (
        email.status == "verified"
        and name.status in {"two_source_verified", "manually_accepted"}
        and city.status == "verified"
        and category.status == "verified"
        and english.status == "no_hard_reject"
        and chain.status == "clear"
        and source_strength != "weak_source"
    ):
        verification_status = "verified"
        verification_reason = "All verification checks passed."
    else:
        verification_status = "needs_review"
        verification_reason = "One or more imported-record checks still need manual confirmation."

    explicitly_promoted = (
        str(updated.get("candidate_inbox_status") or "") == "pitch_ready"
        and str(updated.get("review_status") or "") == "approved"
        and verification_status == "verified"
    )
    pitch_status, pitch_reasons = _pitch_readiness(email, name, city, category, english, chain, verification_status, explicitly_promoted)
    if _needs_import_scope_review(updated) and pitch_status in {"needs_name_review", "review_blocked"}:
        pitch_status = "needs_scope_review"
        pitch_reasons = ["imported tier or source flags require scope review", *pitch_reasons]

    updated.update({
        "verification_version": VERIFICATION_VERSION,
        "verification_checked_at": checked_at,
        "email_verification_status": email.status,
        "email_verification_reason": email.reason,
        "name_verification_status": name.status,
        "name_verification_reason": name.reason,
        "name_verification_sources": name.sources or [],
        "category_verification_status": category.status,
        "category_verification_reason": category.reason,
        "city_verification_status": city.status,
        "city_verification_reason": city.reason,
        "english_menu_check_status": english.status,
        "english_menu_check_reason": english.reason,
        "chain_verification_status": chain.status,
        "chain_verification_reason": chain.reason,
        "source_strength": source_strength,
        "source_strength_reason": source_reason,
        "verification_status": verification_status,
        "verification_reason": verification_reason,
        "verification_score": score,
        "pitch_readiness_status": pitch_status,
        "pitch_readiness_reasons": pitch_reasons,
        "pitch_ready": bool(explicitly_promoted),
        "candidate_inbox_status": "pitch_ready" if explicitly_promoted else pitch_status,
        "needs_scope_review": pitch_status in {"needs_scope_review", "review_blocked"},
    })

    _apply_manual_review_hold(updated, checked_at=checked_at, verification_status=verification_status)
    return apply_pitch_card_state(updated)


def source_strength_for(record: dict[str, Any]) -> tuple[str, str]:
    hosts = [_url_host(url) for url in _source_urls(record)]
    hosts = [host for host in hosts if host]
    if not hosts:
        return "weak_source", "No source URL recorded."
    if any(_is_official_site_host(host) for host in hosts):
        return "official_site", "At least one source URL appears to be a first-party restaurant site."
    if any(_host_has_token(host, OWNED_PAGE_HOST_TOKENS) for host in hosts):
        return "restaurant_owned_page", "Source URL appears to be a restaurant-owned profile page."
    if any(_host_has_token(host, DIRECTORY_HOST_TOKENS) for host in hosts):
        return "directory", "Source URL is a restaurant directory or listing page."
    return "weak_source", "Source URL is weak or not clearly restaurant-owned."


def verify_restaurant_lead_queue(
    *,
    state_root: Path,
    dry_run: bool = False,
    summary_path: Path | None = None,
) -> dict[str, Any]:
    checked_at = utc_now()
    selected: list[dict[str, Any]] = []
    updated_records: list[dict[str, Any]] = []

    for record in list_leads(state_root=state_root):
        if not is_restaurant_email_queue_record(record):
            continue
        selected.append(record)
        updated = verify_restaurant_lead_record(record, checked_at=checked_at)
        updated_records.append(updated)
        if not dry_run:
            persist_lead_record(updated, state_root=state_root)

    summary = _summary(updated_records, checked_at=checked_at, dry_run=dry_run)
    if summary_path is not None:
        write_json(summary_path, summary)
    return summary


def _verify_email(record: dict[str, Any], *, source_strength: str) -> CheckResult:
    email = normalize_email(str(record.get("email") or ""))
    if not email:
        return CheckResult("rejected", "missing direct email", 0)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return CheckResult("rejected", "invalid normalized email", 0)
    if not is_usable_business_email(email):
        return CheckResult("rejected", "email is not a usable business email", 0)

    local, domain = email.rsplit("@", 1)
    domain_parts = domain.rsplit(".", 1)
    tld = domain_parts[-1] if len(domain_parts) > 1 else ""
    if not re.match(r"^[a-z0-9]", local):
        return CheckResult("rejected", "email local part starts with an extraction artifact", 0)
    if local in BAD_EMAIL_LOCAL_PARTS:
        return CheckResult("rejected", f"blocked email local part: {local}", 0)
    if any(local.startswith(prefix) for prefix in BAD_EMAIL_LOCAL_PREFIXES):
        return CheckResult("rejected", f"blocked email local prefix: {local}", 0)
    if len(local) >= 4 and len(set(local)) == 1:
        return CheckResult("rejected", "placeholder repeated-character email local part", 0)
    if set(local) == {"0"}:
        return CheckResult("rejected", "placeholder numeric email local part", 0)
    if domain in BAD_EMAIL_DOMAINS:
        return CheckResult("rejected", f"blocked placeholder email domain: {domain}", 0)
    if any(domain.endswith(suffix) for suffix in BAD_EMAIL_DOMAIN_SUFFIXES):
        return CheckResult("rejected", "blocked institutional email domain", 0)
    if tld in BAD_EMAIL_TLDS:
        return CheckResult("rejected", f"blocked placeholder email tld: {tld}", 0)
    if any(token in domain for token in BAD_EMAIL_DOMAIN_TOKENS):
        return CheckResult("rejected", "blocked email domain token", 0)

    manual_sources = _manual_review_sources(record, "email")
    if _manual_review_rejects(record, "email") and len(manual_sources) >= 2:
        return CheckResult("rejected", "email manually rejected with two source confirmations", 0, manual_sources)

    source_url = str(record.get("email_source_url") or "").strip()
    if not source_url:
        return CheckResult("needs_review", "email source URL missing", 10)
    if source_strength == "weak_source":
        return CheckResult("needs_review", "email source is weak", 12)
    if source_strength == "directory":
        return CheckResult("needs_review", "directory email needs direct restaurant confirmation", 12)
    if domain in FREE_MAIL_DOMAINS or any(domain.endswith(suffix) for suffix in FREE_MAIL_DOMAIN_SUFFIXES):
        return CheckResult("needs_review", "free-mail address needs owner confirmation", 14)
    if len(local) <= 2 and local.isalpha():
        return CheckResult("needs_review", "short email local part needs owner confirmation", 14)
    if source_strength == "official_site" and not _email_domain_matches_recorded_source(domain, record):
        if _manual_review_accepts(record, "email") and len(manual_sources) >= 2:
            return CheckResult("verified", "email domain manually accepted with two source confirmations", 25, manual_sources)
        return CheckResult("needs_review", "email domain differs from recorded official source host", 14)
    return CheckResult("verified", "direct email is syntactically valid with a recorded source URL", 25)


def _verify_name(record: dict[str, Any]) -> CheckResult:
    name = str(record.get("business_name") or record.get("locked_business_name") or "").strip()
    sources = _name_sources(record)
    if not name:
        return CheckResult("needs_review", "restaurant name missing", 0, sources)
    manual_sources = _manual_review_sources(record, "name")
    if _manual_review_rejects(record, "name") and len(manual_sources) >= 2:
        return CheckResult("rejected", "restaurant name manually rejected with two source confirmations", 0, manual_sources)
    if len(name) <= 1 or name.startswith((">", "＞")) or name.endswith(("【", "「", "『")):
        return CheckResult("rejected", "restaurant name looks like a malformed extraction artifact", 0, sources)
    if _looks_like_review_artifact_name(name, record):
        return CheckResult("rejected", "restaurant name looks like a review title or reviewer handle", 0, sources)
    if business_name_is_suspicious(name):
        return CheckResult("rejected", "restaurant name looks contact-derived or unsafe", 0, sources)
    if name in BAD_NAME_EXACT or any(fragment in name for fragment in BAD_NAME_FRAGMENTS):
        return CheckResult("rejected", "restaurant name looks like a page title, review, article, event, or hiring artifact", 0, sources)

    verified_by = [source for source in record.get("business_name_verified_by") or [] if str(source or "").strip()]
    source_count = _int_value(record.get("source_count") or (record.get("coverage_signals") or {}).get("source_count"))
    if len(set(verified_by)) >= 2 or source_count >= 2:
        return CheckResult("two_source_verified", "restaurant name has at least two recorded source confirmations", 25, sources)
    if _manual_review_accepts(record, "name") and len(manual_sources) >= 2:
        return CheckResult("manually_accepted", "restaurant name manually accepted with two source confirmations", 25, manual_sources)
    if str(record.get("name_verification_status") or "") == "manually_accepted":
        return CheckResult("manually_accepted", "restaurant name manually accepted by operator", 25, sources)
    return CheckResult("single_source", "restaurant name currently has one recorded source confirmation", 12, sources)


def _verify_city(record: dict[str, Any]) -> CheckResult:
    city = str(record.get("city") or "").strip()
    if city not in TARGET_CITY_HINTS:
        return CheckResult("rejected", "city is outside the approved target-city set", 0)
    address = str(record.get("address") or "").strip()
    haystack = " ".join([city, address, json.dumps(record.get("source_search_job") or {}, ensure_ascii=False)])
    if any(hint in haystack for hint in TARGET_CITY_HINTS[city]):
        return CheckResult("verified", f"target city confirmed as {city}", 15)
    return CheckResult("needs_review", "target city is present but lacks address/source corroboration", 6)


def _verify_category(record: dict[str, Any]) -> CheckResult:
    name = str(record.get("business_name") or record.get("locked_business_name") or "").strip()
    top_level = str(record.get("type_of_restaurant") or record.get("primary_category_v1") or "").strip().lower()
    menu_type = str(record.get("menu_type") or top_level).strip().lower()
    profile = str(record.get("establishment_profile") or "").strip()
    manual_sources = _manual_review_sources(record, "category")
    if _manual_review_rejects(record, "category") and len(manual_sources) >= 2:
        return CheckResult("rejected", "category manually rejected with two source confirmations", 0, manual_sources)
    if top_level not in {"ramen", "izakaya"}:
        return CheckResult("rejected", "top-level restaurant family is outside ramen/izakaya", 0)
    if _has_clear_out_of_scope_category_artifact(name):
        return CheckResult("rejected", "business name contains a clear outside-scope restaurant category", 0)
    if is_excluded_business(name, menu_type):
        return CheckResult("rejected", "business name/category is outside ramen/izakaya scope", 0)
    if any(token in url.lower() for url in _source_urls(record) for token in OUT_OF_SCOPE_SOURCE_URL_TOKENS):
        return CheckResult("rejected", "source URL indicates outside ramen/izakaya scope", 0)
    if top_level == "izakaya" and _needs_generic_japanese_cuisine_scope_review(name):
        if _manual_review_accepts(record, "category") and len(manual_sources) >= 2:
            return CheckResult("verified", "izakaya category manually accepted with two source confirmations", 20, manual_sources)
        return CheckResult("needs_review", "broad Japanese-cuisine name needs izakaya scope confirmation", 8)
    if menu_type not in SUPPORTED_MENU_TYPES or not profile or profile == "unknown":
        return CheckResult("needs_review", "menu type does not map cleanly to a supported dashboard profile", 8)
    return CheckResult("verified", f"{top_level} category maps to {profile}", 20)


def _verify_english_menu(record: dict[str, Any]) -> CheckResult:
    manual_sources = _manual_review_sources(record, "english_menu")
    if (
        _manual_review_rejects(record, "english_menu")
        or _manual_review_accepts(record, "english_menu", accepted_values={"english_available", "already_english_supported", "usable_complete"})
    ) and len(manual_sources) >= 2:
        return CheckResult("rejected", "manual English-menu hard reject with source confirmations", 0, manual_sources)

    dossier = record.get("lead_evidence_dossier") or {}
    state = str(record.get("english_menu_state") or dossier.get("english_menu_state") or "").strip()
    if state in {"usable_complete", "already_english_supported"}:
        return CheckResult("rejected", f"hard English-menu signal: {state}", 0)
    if any(_url_has_english_language_path(url) for url in _source_urls(record)):
        return CheckResult("needs_review", "English-language source URL needs menu availability review", 3)

    haystack = "\n".join([
        "\n".join(str(item or "") for item in record.get("evidence_snippets") or []),
        "\n".join(str(item or "") for item in record.get("matched_friction_evidence") or []),
        "\n".join(str(item or "") for item in record.get("english_menu_issue_evidence") or []),
    ]).lower()
    haystack = haystack.replace("no hard english-menu reject was present", "")
    if any(token.lower() in haystack for token in SOLVED_ENGLISH_SUPPORT_TERMS):
        return CheckResult("rejected", "hard English-menu solution signal found in evidence", 0)
    if state in {"missing", "weak_partial", "image_only"} or record.get("english_menu_issue") is True:
        return CheckResult("no_hard_reject", "no hard English-menu reject is recorded", 10)
    return CheckResult("needs_review", "English-menu availability remains ambiguous", 3)


def _verify_chain(record: dict[str, Any]) -> CheckResult:
    name = str(record.get("business_name") or "").strip()
    chain_haystack = " ".join([
        name,
        str(record.get("website") or ""),
        str(record.get("email_source_url") or ""),
        str(record.get("email") or ""),
        " ".join(str(url) for url in _source_urls(record)),
    ]).lower()
    manual_sources = _manual_review_sources(record, "chain")
    if _manual_review_rejects(record, "chain") and len(manual_sources) >= 2:
        return CheckResult("rejected", "chain/operator risk manually rejected with two source confirmations", 0, manual_sources)
    if any(fragment.lower() in chain_haystack for fragment in KNOWN_CHAIN_NAME_FRAGMENTS):
        return CheckResult("rejected", "known restaurant chain or multi-branch brand", 0)
    if any(token in chain_haystack for token in KNOWN_CHAIN_DOMAIN_TOKENS):
        return CheckResult("rejected", "known restaurant chain or multi-branch domain", 0)
    if is_chain_business(name):
        return CheckResult("rejected", "known chain or branch-like business name", 0)
    if _has_operator_review_source(record):
        if _manual_review_accepts(record, "chain", accepted_values={"clear", "accepted", "operator_clear", "independent"}) and len(manual_sources) >= 2:
            return CheckResult("clear", "operator source manually cleared with two source confirmations", 5, manual_sources)
        return CheckResult("needs_review", "operator or multi-location source needs confirmation", 2)
    if _looks_like_branch_or_storefront_name(name):
        if _manual_review_accepts(record, "chain", accepted_values={"clear", "accepted", "operator_clear", "independent"}) and len(manual_sources) >= 2:
            return CheckResult("clear", "branch/operator risk manually cleared with two source confirmations", 5, manual_sources)
        return CheckResult("needs_review", "branch-like store name needs operator confirmation", 2)
    reason = chain_or_franchise_signal_reason(
        " ".join([
            name,
            str(record.get("website") or ""),
            str(record.get("email_source_url") or ""),
            " ".join(str(url) for url in _source_urls(record)),
            " ".join(str(snippet) for snippet in record.get("evidence_snippets") or []),
        ]),
        business_name=name,
    )
    if reason:
        return CheckResult("rejected", f"chain/franchise signal: {reason}", 0)
    return CheckResult("clear", "no chain/franchise reject signal recorded", 5)


def _pitch_readiness(
    email: CheckResult,
    name: CheckResult,
    city: CheckResult,
    category: CheckResult,
    english: CheckResult,
    chain: CheckResult,
    verification_status: str,
    explicitly_promoted: bool,
) -> tuple[str, list[str]]:
    if explicitly_promoted:
        return "pitch_ready", []
    if verification_status == "rejected":
        return "rejected", ["verification_rejected"]
    if email.status != "verified":
        return "needs_email_review", [email.reason]
    if name.status not in {"two_source_verified", "manually_accepted"}:
        return "needs_name_review", [name.reason]
    if city.status != "verified" or category.status != "verified" or english.status != "no_hard_reject" or chain.status != "clear":
        return "needs_scope_review", [
            result.reason
            for result in (city, category, english, chain)
            if result.status not in {"verified", "no_hard_reject", "clear"}
        ]
    return "review_blocked", ["explicit_operator_promotion_required"]


def _needs_import_scope_review(record: dict[str, Any]) -> bool:
    quality_tier = str(record.get("quality_tier") or "").strip().lower()
    if quality_tier and quality_tier != "high":
        return True
    return bool(record.get("source_rejection_flags") or record.get("import_review_flags"))


def _apply_manual_review_hold(updated: dict[str, Any], *, checked_at: str, verification_status: str) -> None:
    if str(updated.get("outreach_status") or "") not in TERMINAL_OUTREACH_STATUSES:
        if updated.get("outreach_status") != "needs_review":
            history = list(updated.get("status_history") or [])
            history.append({
                "status": "needs_review",
                "timestamp": checked_at,
                "reason": "restaurant_lead_verification_hold",
            })
            updated["status_history"] = history
        updated["outreach_status"] = "needs_review"

    updated["launch_readiness_status"] = READINESS_MANUAL
    reasons = [str(reason) for reason in updated.get("launch_readiness_reasons") or [] if str(reason).strip()]
    for reason in [
        "restaurant_email_verification_not_promoted",
        "restaurant_email_verification_rejected" if verification_status == "rejected" else "restaurant_email_verification_needs_review",
    ]:
        if reason not in reasons:
            reasons.append(reason)
    updated["launch_readiness_reasons"] = reasons


def _source_urls(record: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for key in ("email_source_url", "website", "source_file"):
        value = str(record.get(key) or "").strip()
        if value.startswith(("http://", "https://")):
            urls.append(value)
    source_urls = record.get("source_urls") or {}
    if isinstance(source_urls, dict):
        for value in [source_urls.get("website"), source_urls.get("map_url")]:
            if str(value or "").startswith(("http://", "https://")):
                urls.append(str(value))
        for value in source_urls.get("evidence_urls") or []:
            if str(value or "").startswith(("http://", "https://")):
                urls.append(str(value))
    return list(dict.fromkeys(urls))


def _url_host(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(str(url or ""))
    except ValueError:
        return ""
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host.split(":", 1)[0]


def _email_domain_matches_recorded_source(email_domain: str, record: dict[str, Any]) -> bool:
    domain = str(email_domain or "").strip().lower()
    if not domain:
        return False
    return any(
        _is_official_site_host(host) and _domains_match(domain, host)
        for host in (_url_host(url) for url in _source_urls(record))
    )


def _domains_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return left == right or left.endswith(f".{right}") or right.endswith(f".{left}")


def _looks_like_review_artifact_name(name: str, record: dict[str, Any]) -> bool:
    cleaned = str(name or "").strip()
    if re.fullmatch(r"[（(][^）)]{1,64}[）)]", cleaned):
        return True
    if any(fragment in cleaned for fragment in REVIEW_ARTIFACT_NAME_FRAGMENTS):
        return True
    source_path = " ".join(_source_urls(record)).lower()
    if "dtlrvwlst" not in source_path:
        return False
    if len(cleaned) >= 42 and "。" not in cleaned:
        return True
    has_terminal_reviewer_handle = bool(re.search(r"[（(][^）)/]{2,40}[）)]$", cleaned))
    return has_terminal_reviewer_handle and not any(term in cleaned for term in CORE_SCOPE_NAME_TERMS)


def _has_clear_out_of_scope_category_artifact(name: str) -> bool:
    if not name:
        return False
    if any(fragment in name for fragment in CLEAR_OUT_OF_SCOPE_CATEGORY_ARTIFACTS):
        return True
    return _has_rejected_parenthetical_directory_category(name)


def _has_rejected_parenthetical_directory_category(name: str) -> bool:
    for match in re.finditer(r"[（(][^）)]{0,40}/([^）)]{1,24})[）)]", name):
        category = match.group(1)
        if any(term in category for term in DIRECTORY_PARENT_CATEGORY_REJECTS):
            return True
    return False


def _needs_generic_japanese_cuisine_scope_review(name: str) -> bool:
    if not name:
        return False
    if not any(term in name for term in GENERIC_JAPANESE_CUISINE_SCOPE_REVIEW_TERMS):
        return False
    return not any(term in name for term in EXPLICIT_IZAKAYA_SCOPE_TERMS)


def _looks_like_branch_or_storefront_name(name: str) -> bool:
    if not name:
        return False
    cleaned = re.sub(r"[（(]【?旧店名】?[^）)]*[）)]", "", name)
    return bool(BRANCH_REVIEW_NAME_RE.search(cleaned))


def _url_has_english_language_path(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(str(url or ""))
    except ValueError:
        return False
    path = parsed.path.lower().rstrip("/")
    query = parsed.query.lower()
    return path.endswith("/en") or "/en/" in f"{path}/" or "lang=en" in query


def _has_operator_review_source(record: dict[str, Any]) -> bool:
    for url in _source_urls(record):
        host = _url_host(url)
        if any(token in host for token in OPERATOR_REVIEW_DOMAIN_TOKENS):
            return True
        try:
            parsed = urllib.parse.urlparse(str(url or ""))
        except ValueError:
            continue
        path = parsed.path.lower()
        if any(token in path for token in OPERATOR_REVIEW_SOURCE_PATH_TOKENS):
            return True
    return False


def _host_has_token(host: str, tokens: tuple[str, ...]) -> bool:
    return any(token in host for token in tokens)


def _is_official_site_host(host: str) -> bool:
    if not host or "." not in host:
        return False
    if _host_has_token(host, DIRECTORY_HOST_TOKENS + OWNED_PAGE_HOST_TOKENS + WEAK_SOURCE_HOST_TOKENS):
        return False
    return True


def _name_sources(record: dict[str, Any]) -> list[str]:
    sources: list[str] = []
    for source in record.get("business_name_verified_by") or []:
        cleaned = str(source or "").strip()
        if cleaned:
            sources.append(cleaned)
    sources.extend(_source_urls(record))
    sources.extend(_manual_review_sources(record, "name"))
    return list(dict.fromkeys(sources))


def _manual_review(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("restaurant_lead_manual_review") or record.get("manual_restaurant_lead_review") or {}
    return value if isinstance(value, dict) else {}


def _manual_review_accepts(
    record: dict[str, Any],
    field: str,
    *,
    accepted_values: set[str] | None = None,
) -> bool:
    accepted_values = accepted_values or {"accepted", "verified", "manually_accepted"}
    review = _manual_review(record)
    candidates = [
        review.get(f"{field}_status"),
        review.get(f"{field}_verification_status"),
        review.get(f"{field}_review_status"),
    ]
    return any(str(value or "").strip().lower() in accepted_values for value in candidates)


def _manual_review_rejects(record: dict[str, Any], field: str) -> bool:
    return _manual_review_accepts(
        record,
        field,
        accepted_values={"rejected", "reject", "out_of_scope", "chain_rejected", "invalid"},
    )


def _manual_review_sources(record: dict[str, Any], field: str) -> list[str]:
    review = _manual_review(record)
    source_values: list[Any] = []
    for key in (
        "sources",
        "source_urls",
        "review_sources",
        f"{field}_sources",
        f"{field}_source_urls",
        f"{field}_review_sources",
    ):
        value = review.get(key)
        if isinstance(value, list):
            source_values.extend(value)
        elif value:
            source_values.append(value)

    sources: list[str] = []
    for value in source_values:
        if isinstance(value, dict):
            value = value.get("url") or value.get("source_url") or value.get("source")
        cleaned = str(value or "").strip()
        if cleaned:
            sources.append(cleaned)
    return list(dict.fromkeys(sources))


def _source_strength_score(source_strength: str) -> int:
    return {
        "official_site": 5,
        "restaurant_owned_page": 3,
        "directory": 2,
        "weak_source": 0,
    }.get(source_strength, 0)


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _counter(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _nested_counter(records: list[dict[str, Any]], *keys: str) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for record in records:
        outer = str(record.get(keys[0]) or "unknown")
        inner = str(record.get(keys[1]) or "unknown")
        bucket = result.setdefault(outer, {})
        bucket[inner] = bucket.get(inner, 0) + 1
    return {key: dict(sorted(value.items())) for key, value in sorted(result.items())}


def _summary(records: list[dict[str, Any]], *, checked_at: str, dry_run: bool) -> dict[str, Any]:
    return {
        "generated_at": checked_at,
        "dry_run": dry_run,
        "selected_records": len(records),
        "verification_status": _counter(records, "verification_status"),
        "email_status": _counter(records, "email_verification_status"),
        "name_status": _counter(records, "name_verification_status"),
        "city_status": _counter(records, "city_verification_status"),
        "category_status": _counter(records, "category_verification_status"),
        "english_menu_status": _counter(records, "english_menu_check_status"),
        "source_strength": _counter(records, "source_strength"),
        "pitch_readiness_status": _counter(records, "pitch_readiness_status"),
        "pitch_card_status": _counter(records, "pitch_card_status"),
        "pitch_card_counts": pitch_card_counts(records),
        "quality_tier": _counter(records, "quality_tier"),
        "verified_category_counts": _nested_counter(
            [record for record in records if record.get("verification_status") == "verified"],
            "type_of_restaurant",
            "menu_type",
        ),
        "review_category_counts": _nested_counter(
            [record for record in records if record.get("verification_status") == "needs_review"],
            "type_of_restaurant",
            "menu_type",
        ),
        "rejected_category_counts": _nested_counter(
            [record for record in records if record.get("verification_status") == "rejected"],
            "type_of_restaurant",
            "menu_type",
        ),
        "ready_for_outreach": sum(1 for record in records if record.get("launch_readiness_status") == "ready_for_outreach"),
        "pitch_ready": sum(1 for record in records if record.get("pitch_ready") is True),
    }
