from __future__ import annotations

import re
from html import escape
from typing import Any

from .models import PreviewMenu, PreviewSection, PreviewItem, TicketMachineHint, EvidenceAssessment
from .constants import PRICE_RE
from .lead_dossier import safe_customer_snippets


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
    """Deterministic translation for common items, never bracket fallback."""
    return _COMMON_TRANSLATIONS.get(ja, "English review sample")


def build_preview_menu(
    *,
    assessment: EvidenceAssessment,
    snippets: list[str],
    business_name: str,
) -> PreviewMenu:
    """Build an illustrative preview menu from assessment + snippets."""
    sections: list[PreviewSection] = []
    items: list[PreviewItem] = []

    safe_snippets = safe_customer_snippets(snippets)
    for snippet in safe_snippets[:6]:
        # Try to extract a food term
        ja_name = PRICE_RE.sub("", snippet)[:40].strip()
        en_name = _auto_translate(ja_name)
        items.append(PreviewItem(
            ja=ja_name,
            en=en_name,
            price="",
            source_type="scraped_evidence",
            confidence="medium",
        ))

    if items:
        sections.append(PreviewSection(
            header_ja="メニュー",
            header_en="Menu",
            items=items[:5],
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
    if not section_html:
        section_html = (
            "<div class='empty-proof'>Customer-visible preview is blocked until "
            "a safe menu or ordering proof item is selected by the operator.</div>"
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
:root {{ --ink:#f0ebe3; --muted:#a8a29e; --paper:#0f0d0b; --surface:#1c1917; --line:#292524; --accent:#c53d43; --soft:#1c1917; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:'Outfit',ui-sans-serif,system-ui,-apple-system,sans-serif; background:var(--paper); color:var(--ink); font-size:12pt; }}
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
.machine-btn {{ border:1px solid var(--line); border-radius:8px; padding:10px; background:var(--surface); }}
.machine-btn strong {{ display:block; }}
.machine-btn span {{ display:block; color:var(--muted); font-size:10pt; }}
.machine-btn .price {{ color:var(--accent); font-weight:600; }}
.disclaimer {{ margin-top:24px; padding:16px; background:var(--surface); border-radius:8px; color:var(--muted); font-size:10pt; line-height:1.6; border:1px solid var(--line); }}
.empty-proof {{ border:1px solid var(--line); background:var(--surface); border-radius:8px; padding:16px; color:var(--muted); line-height:1.5; }}
</style>
</head>
<body>
<main>
<h1>{escape(business_name)}</h1>
<p style="color:var(--muted)">English Menu Preview (illustrative example)</p>

<h2>Menu Preview</h2>
{section_html}
{machine_html}

<div class="disclaimer">
{escape(preview_menu.disclaimer_ja)}
</div>
</main>
</body>
</html>"""


def build_shop_preview_from_record(
    *,
    record: dict[str, Any],
) -> str | None:
    """Build a shop-specific preview HTML from a lead record's evidence.

    Returns None if there are no evidence snippets to build from.
    The preview is clearly marked as illustrative and partial — production
    always uses owner-provided photos and confirmation.
    """
    snippets: list[str] = record.get("evidence_snippets") or []
    business_name = record.get("business_name") or ""
    if not snippets or not business_name:
        return None
    if not safe_customer_snippets(snippets):
        return None

    from .models import EvidenceAssessment

    profile = record.get("establishment_profile", "")
    assessment = EvidenceAssessment(
        is_ramen_candidate=profile.startswith("ramen"),
        is_izakaya_candidate=profile.startswith("izakaya"),
        evidence_classes=record.get("evidence_classes") or [],
        menu_evidence_found=record.get("menu_evidence_found", False),
        machine_evidence_found=record.get("machine_evidence_found", False),
        course_or_drink_plan_evidence_found=profile.startswith("izakaya"),
        score=0,
        evidence_urls=[],
        best_evidence_url=None,
        best_evidence_reason="",
        false_positive_risk="low",
    )

    preview_menu = build_preview_menu(
        assessment=assessment,
        snippets=snippets,
        business_name=business_name,
    )

    ticket_hint: TicketMachineHint | None = None
    if assessment.machine_evidence_found:
        ticket_hint = TicketMachineHint(has_ticket_machine=True)

    return build_preview_html(
        preview_menu=preview_menu,
        ticket_machine_hint=ticket_hint,
        business_name=business_name,
    )
