"""Configuration management for the email discovery pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_ALLOWED_GENRES = [
    "ramen", "ラーメン", "らーめん", "中華そば", "担々麺", "つけ麺",
    "izakaya", "居酒屋", "大衆酒場", "大衆割烹",
    "yakitori", "焼鳥", "焼き鳥",
    "kushikatsu", "串カツ",
    "tachinomi", "立ち飲み",
    "robatayaki", "炉端焼き",
    "motsuyaki", "もつ焼き", "もつ焼",
    "seafood izakaya", "海鮮居酒屋",
    "sake bar", "日本酒バー", "立ち呑み",
    "Japanese pub",
]

DEFAULT_REFUSAL_PHRASES = [
    "営業メールお断り",
    "営業目的のメールはご遠慮ください",
    "営業・勧誘のご連絡はお断り",
    "広告メール禁止",
    "セールスお断り",
    "勧誘お断り",
    "迷惑メール対策",
    "無断営業禁止",
    "当サイトおよび店舗への営業・勧誘は固くお断り",
    "営業・勧誘・スパムメールはお断り",
]

DEFAULT_RESERVATION_ONLY_PHRASES = [
    "予約専用",
    "ご予約のみ",
    "予約受付専用",
]

DEFAULT_RECRUIT_ONLY_PHRASES = [
    "採用専用",
    "求人のみ",
    "採用に関するお問い合わせのみ",
]

# Search query templates per-lead
PER_LEAD_QUERY_TEMPLATES = [
    '{shop_name}" "メールアドレス"',
    '{shop_name}" "お問い合わせ"',
    '{shop_name}" "会社概要"',
    '{shop_name}" "運営会社"',
    '{shop_name}" "特定商取引法"',
    '{shop_name}" "特商法"',
    '{shop_name}" "公式通販"',
    '{shop_name}" "オンラインショップ"',
    '{shop_name}" "お取り寄せ"',
    '{shop_name}" "求人" "メールアドレス"',
]

BROAD_QUERY_TEMPLATES = [
    '"ラーメン" "特定商取引法" "メールアドレス"',
    '"ラーメン" "公式通販" "メールアドレス"',
    '"居酒屋" "会社概要" "メールアドレス"',
    '"居酒屋" "採用" "メールアドレス"',
    '"ラーメン" "運営会社" "お問い合わせ"',
    '"大衆酒場" "メールアドレス"',
    '"焼鳥" "特定商取引法" "メールアドレス"',
]

# Contact-form page indicators
CONTACT_FORM_INDICATORS = [
    "お問い合わせ", "contact", "contact-us", "inquiry",
    "法人のお問い合わせ", "業務提携", "取材のお問い合わせ",
]

# Company-info page indicators
COMPANY_PAGE_INDICATORS = [
    "会社概要", "company", "about-us", "運営会社", "企業情報",
    "company-info", "profile",
]

# Tokushoho page indicators
TOKUSHOHO_INDICATORS = [
    "特定商取引法", "特定商取引法に基づく表記", "特商法",
    "legal", "-commerce",
]

# Menu indicators
MENU_INDICATORS = [
    "メニュー", "お品書き", "フード", "ドリンク", "料理",
    "menu", "food", "drink",
]

MENU_RAMEN_TERMS = [
    "醤油", "味噌", "塩", "豚骨", "つけ麺", "替玉", "チャーシュー", "煮卵",
    "背脂", "煮干し", "鶏白湯", "担々麺", "油そば", "まぜ麺",
]

MENU_IZAKAYA_TERMS = [
    "焼鳥", "唐揚げ", "枝豆", "刺身", "日本酒", "焼酎", "生ビール",
    "飲み放題", "コース", "居酒屋", "お通し", "サラダ", "天ぷら",
]

# Online-shop page indicators
ONLINE_SHOP_INDICATORS = [
    "オンラインショップ", "公式通販", "お取り寄せ", "online shop",
    "thebase.in", "stores.jp", "shop-pro.jp", "BASE",
]

# Online-shop platform domains
ONLINE_SHOP_PLATFORMS = [
    "thebase.in", "stores.jp", "shop-pro.jp", "base.shop",
    "shopify.com", "suzuri.jp", "creema.jp", "minne.com",
]


@dataclass
class SearchConfig:
    provider: str = "serper"  # "serper" | "local"
    serper_api_key: str = ""
    max_queries_per_lead: int = 5
    max_results_per_query: int = 10
    rate_limit_delay: float = 1.0  # seconds between requests
    max_page_crawls_per_lead: int = 15
    page_timeout: float = 10.0
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )


@dataclass
class ScoringConfig:
    launch_ready_threshold: float = 70.0
    genre_confidence_threshold: float = 0.6
    mx_validation_enabled: bool = False  # DNS lookups add latency
    email_type_weights: dict[str, float] = field(default_factory=lambda: {
        "general_business_contact": 1.0,
        "operator_company_contact": 0.85,
        "online_shop_contact": 0.75,
        "media_pr_contact": 0.6,
        "recruitment_contact": 0.3,
        "reservation_contact": 0.2,
        "personal_or_unclear": 0.15,
        "low_confidence": 0.1,
        "do_not_contact": 0.0,
    })


@dataclass
class PersistenceConfig:
    sqlite_path: str = "state/email_discovery.db"
    csv_output_path: str = "state/email_discovery_output.csv"
    jsonl_output_path: str = "state/email_discovery_output.jsonl"


@dataclass
class DiscoveryConfig:
    search: SearchConfig = field(default_factory=SearchConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    persistence: PersistenceConfig = field(default_factory=PersistenceConfig)
    allowed_genres: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED_GENRES))
    refusal_phrases: list[str] = field(default_factory=lambda: list(DEFAULT_REFUSAL_PHRASES))
    reservation_only_phrases: list[str] = field(default_factory=lambda: list(DEFAULT_RESERVATION_ONLY_PHRASES))
    recruit_only_phrases: list[str] = field(default_factory=lambda: list(DEFAULT_RECRUIT_ONLY_PHRASES))
    dry_run: bool = False
    max_leads: int = 0  # 0 = unlimited
    log_level: str = "INFO"


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base recursively."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _config_defaults() -> dict:
    return {
        "search": {
            "provider": "serper",
            "serper_api_key": "",
            "max_queries_per_lead": 5,
            "max_results_per_query": 10,
            "rate_limit_delay": 1.0,
            "max_page_crawls_per_lead": 15,
            "page_timeout": 10.0,
        },
        "scoring": {
            "launch_ready_threshold": 70.0,
            "genre_confidence_threshold": 0.6,
            "mx_validation_enabled": False,
        },
        "persistence": {
            "sqlite_path": "state/email_discovery.db",
            "csv_output_path": "state/email_discovery_output.csv",
            "jsonl_output_path": "state/email_discovery_output.jsonl",
        },
        "allowed_genres": DEFAULT_ALLOWED_GENRES,
        "refusal_phrases": DEFAULT_REFUSAL_PHRASES,
        "reservation_only_phrases": DEFAULT_RESERVATION_ONLY_PHRASES,
        "recruit_only_phrases": DEFAULT_RECRUIT_ONLY_PHRASES,
        "dry_run": False,
        "max_leads": 0,
        "log_level": "INFO",
    }


def load_config(path: Optional[str] = None) -> DiscoveryConfig:
    """Load config from YAML file, falling back to defaults."""
    defaults = _config_defaults()

    if path and Path(path).exists():
        with open(path, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        merged = _deep_merge(defaults, user_cfg)
    else:
        merged = defaults

    # Resolve env-var overrides
    serper_key = os.environ.get("SERPER_API_KEY", "")
    if serper_key:
        merged["search"]["serper_api_key"] = serper_key

    return DiscoveryConfig(
        search=SearchConfig(**merged.get("search", {})),
        scoring=ScoringConfig(
            launch_ready_threshold=merged.get("scoring", {}).get("launch_ready_threshold", 70.0),
            genre_confidence_threshold=merged.get("scoring", {}).get("genre_confidence_threshold", 0.6),
            mx_validation_enabled=merged.get("scoring", {}).get("mx_validation_enabled", False),
            email_type_weights=merged.get("scoring", {}).get("email_type_weights",
                                                              ScoringConfig().email_type_weights),
        ),
        persistence=PersistenceConfig(**merged.get("persistence", {})),
        allowed_genres=merged.get("allowed_genres", DEFAULT_ALLOWED_GENRES),
        refusal_phrases=merged.get("refusal_phrases", DEFAULT_REFUSAL_PHRASES),
        reservation_only_phrases=merged.get("reservation_only_phrases", DEFAULT_RESERVATION_ONLY_PHRASES),
        recruit_only_phrases=merged.get("recruit_only_phrases", DEFAULT_RECRUIT_ONLY_PHRASES),
        dry_run=merged.get("dry_run", False),
        max_leads=merged.get("max_leads", 0),
        log_level=merged.get("log_level", "INFO"),
    )
