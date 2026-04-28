from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Project root
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# V1 scope
# ---------------------------------------------------------------------------
TARGET_CATEGORIES = ("ramen", "izakaya")

JP_AREAS = (
    "Tokyo", "Kyoto", "Osaka", "Nara", "Kanazawa", "Hakone", "Sapporo",
    "Fukuoka", "Hiroshima", "Okinawa", "Kamakura", "Kobe", "Nagoya",
    "Takayama", "Nikko", "Arashiyama", "Gion", "Asakusa", "Shinjuku",
    "Shibuya", "Ueno",
)

EXCLUDED_BUSINESS_TOKENS = (
    "sushi", "寿司", "鮨", "yakiniku", "焼肉", "kaiseki", "懐石",
    "cafe", "カフェ", "珈琲", "コーヒー", "bakery", "パン屋",
    "hotel restaurant", "ホテル", "ryokan", "旅館",
    "tempura", "天ぷら", "tonkatsu", "とんかつ",
)

# ---------------------------------------------------------------------------
# Packages
# ---------------------------------------------------------------------------
PACKAGE_1_KEY = "package_1_remote_30k"
PACKAGE_2_KEY = "package_2_printed_delivered_45k"
PACKAGE_3_KEY = "package_3_qr_menu_65k"

PACKAGE_1_PRICE_YEN = 30000
PACKAGE_2_PRICE_YEN = 45000
PACKAGE_3_PRICE_YEN = 65000

PACKAGE_1_LABEL = "Online Delivery"
PACKAGE_2_LABEL = "Printed and Delivered"
PACKAGE_3_LABEL = "QR Menu System"

PACKAGE_REGISTRY: dict[str, dict[str, Any]] = {
    PACKAGE_1_KEY: {
        "key": PACKAGE_1_KEY,
        "number": 1,
        "label": PACKAGE_1_LABEL,
        "price_yen": PACKAGE_1_PRICE_YEN,
        "workflow": "remote_delivery",
        "description": "Print-ready English menu files delivered online.",
    },
    PACKAGE_2_KEY: {
        "key": PACKAGE_2_KEY,
        "number": 2,
        "label": PACKAGE_2_LABEL,
        "price_yen": PACKAGE_2_PRICE_YEN,
        "workflow": "printed_delivered",
        "description": "Printed and laminated menus delivered to the restaurant.",
    },
    PACKAGE_3_KEY: {
        "key": PACKAGE_3_KEY,
        "number": 3,
        "label": PACKAGE_3_LABEL,
        "price_yen": PACKAGE_3_PRICE_YEN,
        "workflow": "qr_menu",
        "description": "Hosted English menu page with QR code and printable QR sign.",
    },
}

# Backward-compatible aliases for older scoring/outreach modules.
PACKAGE_A_KEY = PACKAGE_2_KEY
PACKAGE_B_KEY = PACKAGE_1_KEY
PACKAGE_A_PRICE_YEN = PACKAGE_2_PRICE_YEN
PACKAGE_B_PRICE_YEN = PACKAGE_1_PRICE_YEN
PACKAGE_A_LABEL = PACKAGE_2_LABEL
PACKAGE_B_LABEL = PACKAGE_1_LABEL

# ---------------------------------------------------------------------------
# Lead categories (ramen + izakaya only)
# ---------------------------------------------------------------------------
LEAD_CATEGORY_RAMEN_MACHINE_MAPPING = "ramen_machine_mapping"
LEAD_CATEGORY_RAMEN_MENU_TRANSLATION = "ramen_menu_translation"
LEAD_CATEGORY_RAMEN_MENU_AND_MACHINE = "ramen_menu_and_machine"
LEAD_CATEGORY_IZAKAYA_MENU_TRANSLATION = "izakaya_menu_translation"
LEAD_CATEGORY_IZAKAYA_DRINK_COURSE_GUIDE = "izakaya_drink_course_guide"
LEAD_CATEGORY_NONE = "none"

# ---------------------------------------------------------------------------
# Menu term tokens (JP only, no TW/cafe tokens)
# ---------------------------------------------------------------------------
RAMEN_MENU_TERMS = (
    "ラーメン", "らーめん", "中華そば", "つけ麺", "まぜそば", "味玉",
    "チャーシュー", "替玉", "大盛", "餃子", "ご飯", "ライス",
    "トッピング", "醤油", "塩", "味噌", "豚骨",
    "家系", "二郎", "背脂", "煮干し", "油そば",
)

RAMEN_CATEGORY_TERMS = (
    "ramen", "ラーメン", "らーめん", "中華そば", "つけ麺", "まぜそば",
    "油そば", "担々麺", "台湾ラーメン",
)

TICKET_MACHINE_TERMS = (
    "券売機", "食券", "発券", "ticket machine", "vending machine",
    "machine button", "button layout", "自販機",
)

IZAKAYA_MENU_TERMS = (
    "居酒屋", "お通し", "刺身", "焼き鳥", "串焼き", "揚げ物", "唐揚げ",
    "一品料理", "おすすめ", "本日のおすすめ", "〆", "ご飯もの",
    "飲み放題", "コース", "宴会", "生ビール", "ハイボール", "焼酎",
    "日本酒", "サワー",
    "梅酒", "カクテル", "ワイン", "ウーロン茶", "ノンアル",
)

IZAKAYA_CATEGORY_TERMS = (
    "izakaya", "居酒屋", "飲み屋", "酒場", "yakitori", "焼き鳥",
    "dining bar", "ダイニングバー", "立ち飲み", "tachinomi",
    "もつ焼き", "ホルモン",
)

COURSE_DRINK_PLAN_TERMS = (
    "飲み放題", "コース", "宴会", "all-you-can-drink", "nomihodai",
    "course menu", "食べ放題", "tabehodai", "all-you-can-eat",
    "bottomless", "飲み会", "女子会",
)

# ---------------------------------------------------------------------------
# Detection tokens
# ---------------------------------------------------------------------------
_FOOD_DRINK_TOKENS = {
    "restaurant", "noodle", "dumpling", "hot pot", "ramen", "food", "drink",
    "dining", "izakaya", "soba", "udon", "ramen shop",
    "dining bar", "tachinomi", "standing bar",
    "レストラン", "喫茶", "喫茶店", "ラーメン", "居酒屋", "そば",
    "蕎麦", "うどん", "食堂", "料理",
    "ダイニングバー", "立ち飲み", "もつ焼き", "ホルモン",
}

_DIRECTORY_HOST_TOKENS = {
    "facebook.com", "instagram.com", "tripadvisor.", "ubereats.", "foodpanda.",
    "google.", "maps.", "yelp.", "opentable.", "inline.app", "linktr.ee",
    "retty.me", "tabelog.", "hotpepper.", "gurunavi.", "eatnavi.",
    "guilty.", "tabelog.co.jp",
}

_PURCHASE_CRITICAL_TOKENS = {
    "ingredients", "ingredient", "allergen", "allergy", "nutrition", "menu",
    "order", "reservation", "reserve", "pickup", "delivery", "shipping",
    "storage", "hours", "price", "cart", "checkout",
    "メニュー", "料理", "品", "商品", "注文", "予約", "持ち帰り", "テイクアウト",
    "券売機", "食券", "成分", "原材料", "アレルギー", "栄養", "保存", "税込", "税別",
}

_IMAGE_LOCKED_TOKENS = {
    "menu", "nutrition", "allergen", "ingredients",
    "メニュー", "栄養", "アレルギー", "成分", "原材料", "お品書き",
}

_MENU_LINK_TOKENS = (
    "menu", "product", "products", "order", "shop", "reservation", "booking",
    "drink",
    "メニュー", "商品", "品書き", "料理", "注文", "予約",
)

_ENGLISH_LINK_TOKENS = ("/en", "lang=en", "english")

_CHAIN_SEED_NAMES = (
    "ichiran", "ippudo", "afuri", "menya musashi", "tenkaippin",
    "santouka", "fuunji", "nakiryu", "kikanbo",
    "gyukaku", "watami", "torikizoku",
    "matsuya", "sukiya", "yoshinoya",
    "kura sushi", "hamazushi",
    "saizeriya", "gusto", "jonathan's", "royal host",
    "dennys", "joyfull", "bamiyan",
    # Japanese variants
    "一蘭", "一風堂", "afuri", "麺屋武蔵", "天下一品",
    "山頭火", "風雲児", "凪", "鬼金棒",
    "牛角", "わたみ", "鳥貴族",
    "松屋", "すき家", "吉野家",
    "くら寿司", "はま寿司",
    "サイゼリヤ", "ガスト", "ジョナサン", "ロイヤルホスト",
    "デニーズ", "ジョイフル", "バーミヤン",
)

_BRANCH_PATTERN_RE = __import__("re").compile(r"\d+号店|支店|[市區町村駅]\w{1,6}店")

_CAPTCHA_TOKENS = (
    "captcha", "recaptcha", "cf-challenge", "please verify",
    "are you human", "bot protection", "challenge-form", "hcaptcha",
)

_JS_EMPTY_INDICATORS = (
    "enable javascript", "requires javascript", "javascript is required",
    "please enable js", "please enable javascript",
)

_FILENAME_MENU_PATTERNS = (
    "menu", "kaken", "syokken", "kenbaiki", "ticket", "food", "drink",
    "course", "osusume", "menu_",
)

_UNREADABLE_IMAGE_TOKENS = (
    "blur", "blurry", "unreadable", "不鮮明", "thumbnail", "thumb",
    "crop", "cropped", "icon", "avatar", "logo", "badge",
)

_MENU_ITEM_SEP_RE = __import__("re").compile(r"[、/／・\n]")

PRICE_RE = __import__("re").compile(
    r"(?:¥\s?\d[\d,]*|\d{2,5}\s?円|\$\s?\d[\d,.]*)"
)

# ---------------------------------------------------------------------------
# Template package paths (locked, never modified at outreach stage)
# ---------------------------------------------------------------------------
TEMPLATE_PACKAGE_MENU = (
    PROJECT_ROOT / "glm_menu_template_package_BROWSER_CHECKED_bilingual_right_verified"
)
TEMPLATE_PACKAGE_MACHINE = (
    PROJECT_ROOT / "ticket_machine_guide_template_package_MATCHED_STYLE"
)
GENERIC_MENU_PDF = TEMPLATE_PACKAGE_MENU / "restaurant_menu_print_ready_combined.pdf"
GENERIC_MACHINE_PDF = TEMPLATE_PACKAGE_MACHINE / "ticket_machine_guide_print_ready.pdf"

# ---------------------------------------------------------------------------
# Contact details for email signatures
# ---------------------------------------------------------------------------
CHRIS_CONTACT = os.environ.get("CHRIS_CONTACT", "")

# ---------------------------------------------------------------------------
# Outreach status values
# ---------------------------------------------------------------------------
OUTREACH_STATUS_NEW = "new"
OUTREACH_STATUS_DRAFT = "draft"
OUTREACH_STATUS_SENT = "sent"
OUTREACH_STATUS_REPLIED = "replied"
OUTREACH_STATUS_CONVERTED = "converted"
OUTREACH_STATUS_REJECTED = "rejected"
OUTREACH_STATUS_DO_NOT_CONTACT = "do_not_contact"

OUTREACH_STATUSES = (
    OUTREACH_STATUS_NEW,
    OUTREACH_STATUS_DRAFT,
    OUTREACH_STATUS_SENT,
    OUTREACH_STATUS_REPLIED,
    OUTREACH_STATUS_CONVERTED,
    OUTREACH_STATUS_REJECTED,
    OUTREACH_STATUS_DO_NOT_CONTACT,
)

# ---------------------------------------------------------------------------
# Opt-out detection tokens (incoming replies)
# ---------------------------------------------------------------------------
OPT_OUT_TOKENS = (
    "不要です", "結構です", "配信停止", "不要", "やめてください",
    "お断り", "興味がありません", "結構です。",
)

# ---------------------------------------------------------------------------
# Send rate limit
# ---------------------------------------------------------------------------
MAX_SENDS_PER_DAY = 50
