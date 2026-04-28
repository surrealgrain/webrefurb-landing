from __future__ import annotations

import re
from html import escape
from typing import Any

from .models import PreviewMenu, PreviewSection, PreviewItem, TicketMachineHint, EvidenceAssessment
from .constants import PRICE_RE


# Deterministic common translations for preview items
_COMMON_TRANSLATIONS: dict[str, str] = {
    "醤油ラーメン": "Shoyu Ramen",
    "味噌ラーメン": "Miso Ramen",
    "塩ラーメン": "Shio Ramen",
    "豚骨ラーメン": "Tonkotsu Ramen",
    "味玉ラーメン": "Ajitama Ramen (Flavored Egg)",
    "唐揚げ": "Fried Chicken",
    "餃子": "Gyoza Dumplings",
    "チャーシュー": "Chashu Pork",
    "替玉": "Extra Noodles (Kaedama)",
    "ご飯": "Rice",
    "ライス": "Rice",
    "生ビール": "Draft Beer",
    "ハイボール": "Highball",
    "日本酒": "Sake",
    "焼酎": "Shochu",
    "サワー": "Sour",
    "刺身": "Sashimi",
    "焼き鳥": "Yakitori (Grilled Chicken)",
    "揚げ物": "Fried Dishes",
    "一品料理": "Side Dishes",
    "おすすめ": "Today's Recommendation",
    "飲み放題": "All-You-Can-Drink",
    "コース": "Course Menu",
    "トッピング": "Toppings",
}


def _auto_translate(ja: str) -> str:
    """Deterministic translation for common items, fallback to romanized."""
    return _COMMON_TRANSLATIONS.get(ja, f"[{ja}]")


def build_preview_menu(
    *,
    assessment: EvidenceAssessment,
    snippets: list[str],
    business_name: str,
) -> PreviewMenu:
    """Build an illustrative preview menu from assessment + snippets."""
    sections: list[PreviewSection] = []
    items: list[PreviewItem] = []

    for snippet in snippets[:6]:
        prices = PRICE_RE.findall(snippet)
        price = prices[0] if len(prices) == 1 else ""
        # Try to extract a food term
        ja_name = snippet[:40].strip()
        en_name = _auto_translate(ja_name)
        items.append(PreviewItem(
            ja=ja_name,
            en=en_name,
            price=price,
            source_type="scraped_evidence",
            confidence="medium",
        ))

    if items:
        sections.append(PreviewSection(
            header_ja="メニュー",
            header_en="Menu",
            items=items[:5],
        ))

    if not sections:
        sections.append(PreviewSection(
            header_ja="メニュー",
            header_en="Menu",
            items=[PreviewItem(
                ja="[メニュー情報]",
                en="[Menu information — to be translated from owner's photos]",
                confidence="low",
            )],
        ))

    return PreviewMenu(
        sections=sections,
        disclaimer_ja=(
            "実際の制作時には、メニューや券売機の写真をお送りいただき、"
            "すべての項目を正確に反映した英語版をお作りします。"
            "上記は一部のイメージ例です。"
        ),
    )


def build_preview_html(
    *,
    preview_menu: PreviewMenu,
    ticket_machine_hint: TicketMachineHint | None,
    business_name: str,
    package_label: str = "",
) -> str:
    """Render the illustrative preview as HTML."""
    from .constants import PACKAGE_1_PRICE_YEN, PACKAGE_2_PRICE_YEN, PACKAGE_3_PRICE_YEN

    section_html = ""
    for section in preview_menu.sections:
        items_html = "".join(
            f"<tr>"
            f"<td class='ja'>{escape(item.ja)}</td>"
            f"<td class='arrow'>→</td>"
            f"<td class='en'>{escape(item.en)}</td>"
            f"<td class='price'>{escape(item.price)}</td>"
            f"</tr>"
            for item in section.items
        )
        section_html += (
            f"<h3>{escape(section.header_ja)} / {escape(section.header_en)}</h3>"
            f"<table class='preview-table'>{items_html}</table>"
        )

    machine_html = ""
    if ticket_machine_hint and ticket_machine_hint.has_ticket_machine:
        cells = "".join(
            f"<div class='machine-btn'>"
            f"<strong>{escape(btn.label)}</strong>"
            f"<span>{escape(_auto_translate(btn.label))}</span>"
            f"<span class='price'>{escape(btn.price)}</span>"
            f"</div>"
            for btn in ticket_machine_hint.buttons[:8]
        ) or "<div class='machine-btn'><em>Ticket machine detected — guide to be created from photos</em></div>"
        machine_html = (
            "<h3>券売機 / Ticket Machine Guide</h3>"
            f"<div class='machine-grid'>{cells}</div>"
        )

    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(business_name)} — English Menu Preview</title>
<style>
:root {{ --ink:#171717; --muted:#525252; --paper:#fffaf3; --line:#ddd3c3; --accent:#0f766e; --soft:#f5efe4; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; background:var(--paper); color:var(--ink); font-size:12pt; }}
main {{ max-width:720px; margin:0 auto; padding:28px 20px 56px; }}
h1 {{ font-size:24pt; margin:0 0 4px; }}
h2 {{ font-size:16pt; color:var(--accent); margin:24px 0 12px; }}
h3 {{ font-size:13pt; margin:16px 0 8px; }}
.preview-table {{ width:100%; border-collapse:collapse; }}
.preview-table td {{ padding:8px 4px; border-bottom:1px solid var(--line); }}
.preview-table .ja {{ font-weight:600; width:30%; }}
.preview-table .arrow {{ color:var(--accent); text-align:center; width:24px; }}
.preview-table .en {{ width:40%; }}
.preview-table .price {{ text-align:right; white-space:nowrap; }}
.machine-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:8px; }}
.machine-btn {{ border:1px solid var(--line); border-radius:8px; padding:10px; background:var(--soft); }}
.machine-btn strong {{ display:block; }}
.machine-btn span {{ display:block; color:var(--muted); font-size:10pt; }}
.machine-btn .price {{ color:var(--accent); font-weight:600; }}
.disclaimer {{ margin-top:24px; padding:16px; background:var(--soft); border-radius:8px; color:var(--muted); font-size:10pt; line-height:1.6; }}
.packages {{ margin-top:20px; display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }}
.pkg {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fff; }}
.pkg h4 {{ margin:0 0 8px; color:var(--accent); }}
.pkg .price {{ font-size:16pt; font-weight:700; }}
.pkg ul {{ margin:6px 0 0; padding-left:16px; color:var(--muted); font-size:10pt; }}
</style>
</head>
<body>
<main>
<h1>{escape(business_name)}</h1>
<p style="color:var(--muted)">English Menu Preview (illustrative example)</p>

<h2>Menu Preview</h2>
{section_html}
{machine_html}

<div class="packages">
  <div class="pkg">
    <h4>Online Delivery</h4>
    <div class="price">&yen;{PACKAGE_1_PRICE_YEN:,}</div>
    <ul>
      <li>Print-ready PDF + images</li>
      <li>Translation + layout</li>
      <li>Ticket machine guide</li>
      <li>You handle printing</li>
    </ul>
  </div>
  <div class="pkg">
    <h4>Printed and Delivered</h4>
    <div class="price">&yen;{PACKAGE_2_PRICE_YEN:,}</div>
    <ul>
      <li>Everything in Online Delivery</li>
      <li>Professional printing</li>
      <li>Lamination</li>
      <li>Delivered to your shop</li>
    </ul>
  </div>
  <div class="pkg">
    <h4>QR Menu System</h4>
    <div class="price">&yen;{PACKAGE_3_PRICE_YEN:,}</div>
    <ul>
      <li>Hosted English menu</li>
      <li>QR code + sign</li>
      <li>Reviewed before publish</li>
    </ul>
  </div>
</div>

<div class="disclaimer">
{escape(preview_menu.disclaimer_ja)}
</div>
</main>
</body>
</html>"""
