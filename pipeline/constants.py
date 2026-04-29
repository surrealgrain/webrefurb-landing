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

PACKAGE_1_LABEL = "English Ordering Files"
PACKAGE_2_LABEL = "Counter-Ready Ordering Kit"
PACKAGE_3_LABEL = "Live QR English Menu"

PACKAGE_REGISTRY: dict[str, dict[str, Any]] = {
    PACKAGE_1_KEY: {
        "key": PACKAGE_1_KEY,
        "number": 1,
        "label": PACKAGE_1_LABEL,
        "price_yen": PACKAGE_1_PRICE_YEN,
        "workflow": "remote_delivery",
        "description": "Print-ready English ordering files for the shop to print or use digitally.",
    },
    PACKAGE_2_KEY: {
        "key": PACKAGE_2_KEY,
        "number": 2,
        "label": PACKAGE_2_LABEL,
        "price_yen": PACKAGE_2_PRICE_YEN,
        "workflow": "printed_delivered",
        "description": "Printed, laminated ordering materials delivered counter-ready to the restaurant.",
    },
    PACKAGE_3_KEY: {
        "key": PACKAGE_3_KEY,
        "number": 3,
        "label": PACKAGE_3_LABEL,
        "price_yen": PACKAGE_3_PRICE_YEN,
        "workflow": "qr_menu",
        "description": "Hosted live English ordering menu with QR code and printable QR sign.",
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

TICKET_MACHINE_ABSENCE_TERMS = (
    "券売機なし", "券売機無し", "券売機はありません", "券売機がありません",
    "食券制ではありません", "口頭注文", "後払い", "席で注文",
    "スタッフにご注文", "店員にご注文", "table order", "order at your seat",
    "pay after", "no ticket machine",
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

SOLVED_ENGLISH_SUPPORT_TERMS = (
    "english menu available", "english menu provided", "english menu here",
    "english ticket machine", "multilingual ticket machine", "multilingual qr",
    "english qr", "mobile order english", "tablet order english",
    "英語メニューあり", "英語メニュー有り", "英語メニューあります",
    "英語メニューをご用意", "英語メニューはこちら", "英語券売機",
    "多言語券売機", "多言語メニュー", "多言語対応", "多言語qr",
    "英語qr", "モバイルオーダー 英語", "スマホオーダー 英語",
    "タブレット注文 英語",
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
    "gyukaku", "watami", "torikizoku", "tsukada nojo",
    "isomaru suisan", "kushikatsu tanaka",
    "matsuya", "sukiya", "yoshinoya",
    "kura sushi", "hamazushi",
    "saizeriya", "gusto", "jonathan's", "royal host",
    "dennys", "joyfull", "bamiyan",
    "jangara", "kyushu jangara",
    "abura gumi", "tokyo abura",
    "ramen gyukaku",
    # Japanese variants
    "一蘭", "一風堂", "afuri", "麺屋武蔵", "天下一品",
    "山頭火", "風雲児", "凪", "鬼金棒",
    "牛角", "わたみ", "和民", "鳥貴族", "塚田農場",
    "磯丸水産", "串カツ田中",
    "松屋", "すき家", "吉野家",
    "くら寿司", "はま寿司",
    "サイゼリヤ", "ガスト", "ジョナサン", "ロイヤルホスト",
    "デニーズ", "ジョイフル", "バーミヤン", "新時代",
    "九州じゃんがら", "じゃんがら", "油そば", "東京油組",
)

_BRANCH_PATTERN_RE = __import__("re").compile(
    r"\d+号店"
    r"|支店"
    r"|[市區町村駅]\w{0,6}店"
    r"|\s+(?!本店)\w{2,8}店$"
    r"|\b\w{2,12}\s+Ten\b"
    r"|\b\w{2,12}\s+Branch\b"
    r"|\b\w{2,12}\s+Shop\b"
)

# Romaji branch suffixes to detect in business names
_ROMAJI_BRANCH_SUFFIXES = (" Ten", " Branch", " Shop")

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
# Template package paths (v4c dark templates)
# ---------------------------------------------------------------------------
TEMPLATE_PACKAGE_MENU = PROJECT_ROOT / "assets" / "templates"
TEMPLATE_PACKAGE_MACHINE = PROJECT_ROOT / "assets" / "templates"
GENERIC_MENU_PDF = TEMPLATE_PACKAGE_MENU / "ramen_food_menu.html"
GENERIC_MACHINE_PDF = TEMPLATE_PACKAGE_MACHINE / "ticket_machine_guide.html"
OUTREACH_SAMPLE_RAMEN_ONE_PAGE_PDF = (
    TEMPLATE_PACKAGE_MENU / "ramen_food_menu.html"
)
OUTREACH_SAMPLE_RAMEN_SIDES_PDF = (
    TEMPLATE_PACKAGE_MENU / "ramen_food_menu.html"
)
OUTREACH_SAMPLE_RAMEN_DRINKS_PDF = (
    TEMPLATE_PACKAGE_MENU / "ramen_food_menu.html"
)
OUTREACH_SAMPLE_IZAKAYA_FOOD_DRINKS_PDF = (
    TEMPLATE_PACKAGE_MENU / "izakaya_food_drinks_menu.html"
)

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
OUTREACH_STATUS_CONTACTED_FORM = "contacted_form"
OUTREACH_STATUS_BOUNCED = "bounced"
OUTREACH_STATUS_INVALID = "invalid"

OUTREACH_STATUSES = (
    OUTREACH_STATUS_NEW,
    OUTREACH_STATUS_DRAFT,
    OUTREACH_STATUS_SENT,
    OUTREACH_STATUS_REPLIED,
    OUTREACH_STATUS_CONVERTED,
    OUTREACH_STATUS_REJECTED,
    OUTREACH_STATUS_BOUNCED,
    OUTREACH_STATUS_INVALID,
    OUTREACH_STATUS_DO_NOT_CONTACT,
    OUTREACH_STATUS_CONTACTED_FORM,
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

# ---------------------------------------------------------------------------
# Order states (P5 — Paid Operations Workflow)
# ---------------------------------------------------------------------------
ORDER_STATE_QUOTED = "quoted"
ORDER_STATE_QUOTE_SENT = "quote_sent"
ORDER_STATE_PAYMENT_PENDING = "payment_pending"
ORDER_STATE_PAID = "paid"
ORDER_STATE_INTAKE_NEEDED = "intake_needed"
ORDER_STATE_IN_PRODUCTION = "in_production"
ORDER_STATE_OWNER_REVIEW = "owner_review"
ORDER_STATE_OWNER_APPROVED = "owner_approved"
ORDER_STATE_DELIVERED = "delivered"
ORDER_STATE_CLOSED = "closed"

ORDER_STATES = (
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
)

# Production-approval blocking: these states must be reached before
# production approval is allowed.
ORDER_STATES_BEFORE_PRODUCTION = {
    ORDER_STATE_QUOTED,
    ORDER_STATE_QUOTE_SENT,
    ORDER_STATE_PAYMENT_PENDING,
    ORDER_STATE_PAID,
    ORDER_STATE_INTAKE_NEEDED,
}

# ---------------------------------------------------------------------------
# Payment terms (full upfront for all packages)
# ---------------------------------------------------------------------------
PAYMENT_METHOD_BANK_TRANSFER = "bank_transfer"
PAYMENT_METHOD_MANUAL = "manual"

PAYMENT_TERMS_FULL_UPFRONT = "full_upfront"
PAYMENT_TERMS_DESCRIPTION = "Full payment upfront before production starts."
INVOICE_REGISTRATION_NUMBER = os.environ.get("WEBREFURB_INVOICE_REGISTRATION_NUMBER", "")
OWNER_UPLOAD_PRIVACY_NOTE = (
    "Owner-uploaded menu photos, source PDFs, contact details, and QR menu data are "
    "used only to produce and support the ordered menu package. Production source "
    "files are retained for 90 days after delivery unless the owner requests earlier "
    "deletion; hosted QR menu data is retained while hosting is active."
)

# ---------------------------------------------------------------------------
# Revision policy
# ---------------------------------------------------------------------------
DEFAULT_REVISION_LIMIT = 2  # rounds of revisions included in base price
CUSTOM_REVISION_PRICE_YEN = 5000  # per additional revision round

# ---------------------------------------------------------------------------
# Quote expiry
# ---------------------------------------------------------------------------
QUOTE_EXPIRY_DAYS = 30

# ---------------------------------------------------------------------------
# Package 2 delivery/print cost assumptions (for operator reference)
# ---------------------------------------------------------------------------
PACKAGE_2_PRINT_COST_ESTIMATE_YEN = 3000  # typical print + lamination
PACKAGE_2_DELIVERY_COST_ESTIMATE_YEN = 1000  # domestic courier

# ---------------------------------------------------------------------------
# Custom-quote triggers
# ---------------------------------------------------------------------------
CUSTOM_QUOTE_TRIGGERS = {
    "large_menu": "Menu exceeds 40 items or 4 sections",
    "multiple_sets": "Separate food, drink, course, or seasonal menus needed",
    "oversized_print": "Non-standard sizes (larger than A4/Letter)",
    "extra_copies": "More than 3 printed copies",
    "frequent_updates": "Expected seasonal or monthly menu changes",
}
