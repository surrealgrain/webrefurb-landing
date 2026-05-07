from __future__ import annotations

import os
import re
import secrets
from html import escape
from pathlib import Path
from typing import Any

from .constants import GENERIC_DEMO_URL, PROJECT_ROOT
from .lead_dossier import safe_customer_snippets
from .models import EvidenceAssessment
from .preview import build_preview_menu
from .utils import utc_now, write_text


TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,96}$")
DEFAULT_PUBLIC_BASE_URL = "https://webrefurb.com"


def default_sample_docs_root(*, state_root: Path | None = None) -> Path:
    """Return the static docs root used to publish public-but-unlisted samples."""
    configured = os.environ.get("WEBREFURB_SAMPLE_DOCS_ROOT", "").strip()
    if configured:
        return Path(configured)

    if state_root is not None:
        resolved_state = Path(state_root).resolve()
        default_state = (PROJECT_ROOT / "state").resolve()
        if resolved_state != default_state:
            return resolved_state / "docs"

    return PROJECT_ROOT / "docs"


def public_base_url(value: str | None = None) -> str:
    base = str(value or os.environ.get("WEBREFURB_PUBLIC_BASE_URL") or DEFAULT_PUBLIC_BASE_URL).strip()
    return base.rstrip("/") or DEFAULT_PUBLIC_BASE_URL


def ensure_hosted_menu_sample(
    record: dict[str, Any],
    *,
    docs_root: str | Path | None = None,
    state_root: Path | None = None,
    base_url: str | None = None,
    dry_run: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Legacy-only hosted preview helper for manually approved post-reply work."""
    updated = dict(record)
    token = _existing_or_new_token(updated)
    url = f"{public_base_url(base_url)}/s/{token}"
    root = Path(docs_root) if docs_root is not None else default_sample_docs_root(state_root=state_root)
    output_path = root / "s" / token / "index.html"
    html = build_hosted_menu_sample_html(updated, sample_url=url)
    timestamp = utc_now()

    common = {
        "hosted_menu_sample_token": token,
        "hosted_menu_sample_url": url,
        "sample_menu_url": url,
        "hosted_menu_sample_path": str(output_path),
        "hosted_menu_sample_public_path": f"/s/{token}",
        "hosted_menu_sample_publicly_listed": False,
        "hosted_menu_sample_noindex": True,
        "hosted_menu_sample_updated_at": timestamp,
    }
    updated.update(common)

    result = {
        "lead_id": updated.get("lead_id", ""),
        "business_name": updated.get("business_name", ""),
        "sample_menu_url": url,
        "hosted_menu_sample_url": url,
        "token": token,
        "path": str(output_path),
        "dry_run": bool(dry_run),
        "published": False,
        "ok": True,
        "error": "",
    }

    if dry_run:
        updated["hosted_menu_sample_status"] = "dry_run"
        updated["contact_form_outreach_ready"] = False
        result["html"] = html
        return updated, result

    try:
        write_text(output_path, html)
    except Exception as exc:  # pragma: no cover - exercised through callers.
        error = str(exc)
        updated["hosted_menu_sample_status"] = "publish_failed"
        updated["hosted_menu_sample_error"] = error
        updated["contact_form_outreach_ready"] = False
        result["ok"] = False
        result["error"] = error
        return updated, result

    updated["hosted_menu_sample_status"] = "published"
    updated["hosted_menu_sample_error"] = ""
    updated["hosted_menu_sample_published_at"] = timestamp
    updated["contact_form_outreach_ready"] = True
    result["published"] = True
    return updated, result


def build_hosted_menu_sample_html(record: dict[str, Any], *, sample_url: str = "") -> str:
    """Render a mobile-first public sample page from safe lead evidence."""
    business_name = str(record.get("business_name") or "貴店").strip()
    category = str(record.get("primary_category_v1") or record.get("category") or "").strip().lower()
    is_izakaya = category == "izakaya" or str(record.get("establishment_profile") or "").startswith("izakaya")
    is_ramen = category == "ramen" or str(record.get("establishment_profile") or "").startswith("ramen")
    snippets = _customer_safe_snippets(record)
    assessment = EvidenceAssessment(
        is_ramen_candidate=is_ramen,
        is_izakaya_candidate=is_izakaya,
        evidence_classes=list(record.get("evidence_classes") or []),
        menu_evidence_found=bool(record.get("menu_evidence_found", True)),
        machine_evidence_found=bool(record.get("machine_evidence_found", False)),
        course_or_drink_plan_evidence_found=bool(record.get("course_or_drink_plan_evidence_found", False)) or is_izakaya,
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
    sections_html = _render_sections(preview_menu.sections)
    if not sections_html:
        sections_html = _fallback_sample_sections(is_izakaya=is_izakaya)

    notes = _improvement_notes(record, is_izakaya=is_izakaya)
    notes_html = "".join(f"<li>{escape(note)}</li>" for note in notes)
    asset_links_html = _asset_links_html(record)
    url_note = f"<meta property=\"og:url\" content=\"{escape(sample_url, quote=True)}\">" if sample_url else ""

    title = f"{business_name} | WebRefurb English Menu Sample"
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta name="googlebot" content="noindex, nofollow">
{url_note}
<title>{escape(title)}</title>
<style>
:root {{
  color-scheme: light;
  --paper: #f7f3ea;
  --ink: #1f2523;
  --muted: #68706b;
  --line: #d8d0c2;
  --panel: #fffaf0;
  --brand: #0d4b3e;
  --accent: #b7372f;
  --soft: #ece4d5;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: "Hiragino Sans", "Yu Gothic", "Noto Sans JP", ui-sans-serif, sans-serif;
  line-height: 1.65;
}}
main {{
  width: min(100%, 760px);
  margin: 0 auto;
  padding: 18px 16px 40px;
}}
.brand {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0 18px;
  font-weight: 800;
  color: var(--brand);
  letter-spacing: 0;
}}
.brand span:last-child {{
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}}
.intro {{
  border-top: 5px solid var(--brand);
  padding: 18px 0 14px;
}}
h1 {{
  margin: 0 0 10px;
  font-size: clamp(26px, 9vw, 44px);
  line-height: 1.08;
  letter-spacing: 0;
}}
.lead {{
  margin: 0;
  color: var(--muted);
  font-size: 15px;
}}
.sample-card {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
  margin-top: 18px;
  box-shadow: 0 16px 36px rgba(31, 37, 35, 0.08);
}}
.sample-head {{
  background: var(--brand);
  color: #fffaf0;
  padding: 14px 16px;
}}
.sample-head strong {{
  display: block;
  font-size: 18px;
}}
.sample-head span {{
  display: block;
  font-size: 12px;
  opacity: 0.86;
}}
.menu-section {{
  padding: 16px;
  border-top: 1px solid var(--line);
}}
.menu-section:first-of-type {{ border-top: 0; }}
h2 {{
  margin: 0 0 10px;
  font-size: 17px;
  letter-spacing: 0;
}}
.item {{
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 3px;
  padding: 11px 0;
  border-top: 1px solid var(--soft);
}}
.item:first-of-type {{ border-top: 0; }}
.ja {{
  font-weight: 800;
  overflow-wrap: anywhere;
}}
.en {{
  color: var(--brand);
  font-weight: 800;
  overflow-wrap: anywhere;
}}
.price {{
  color: var(--muted);
  font-size: 13px;
}}
.notes {{
  margin: 18px 0 0;
  padding: 16px;
  background: #ffffff;
  border: 1px solid var(--line);
  border-radius: 8px;
}}
.notes h2 {{ color: var(--accent); }}
ul {{
  margin: 0;
  padding-left: 19px;
}}
li {{ margin: 6px 0; }}
.cta {{
  margin-top: 18px;
  padding: 18px 16px;
  background: var(--ink);
  color: #fffaf0;
  border-radius: 8px;
}}
.cta p {{ margin: 0; }}
.disclaimer {{
  margin-top: 14px;
  color: var(--muted);
  font-size: 12px;
}}
.asset-links a {{
  color: var(--brand);
  font-weight: 800;
  overflow-wrap: anywhere;
}}
@media (min-width: 640px) {{
  main {{ padding: 30px 24px 56px; }}
  .item {{
    grid-template-columns: minmax(0, 0.92fr) minmax(0, 1.08fr) auto;
    align-items: baseline;
    column-gap: 16px;
  }}
}}
</style>
</head>
<body>
<main>
  <div class="brand">
    <span>WebRefurb</span>
    <span>English QR Menu preview</span>
  </div>

  <section class="intro">
    <h1>{escape(business_name)}</h1>
    <p class="lead">これは手動確認後のプレビュー用ページです。初回のご案内では、店舗別ページではなく汎用デモをご案内します。</p>
  </section>

  <section class="sample-card" aria-label="Sample English menu">
    <div class="sample-head">
      <strong>英語メニュー改善サンプル</strong>
      <span>Sample English menu layout</span>
    </div>
    {sections_html}
  </section>

  <section class="notes">
    <h2>改善したポイント</h2>
    <ul>{notes_html}</ul>
    {asset_links_html}
  </section>

  <section class="cta">
    <p>初回案内用の汎用デモ：<a href="{escape(GENERIC_DEMO_URL)}">{escape(GENERIC_DEMO_URL)}</a></p>
  </section>

  <p class="disclaimer">このページは公開リストには掲載していません。価格、説明、原材料、アレルギー情報は店舗様の確認がある場合のみ公開します。</p>
</main>
</body>
</html>
"""


def _existing_or_new_token(record: dict[str, Any]) -> str:
    for key in ("hosted_menu_sample_token", "sample_menu_token"):
        token = str(record.get(key) or "").strip()
        if TOKEN_RE.fullmatch(token):
            return token

    for key in ("hosted_menu_sample_url", "sample_menu_url"):
        token = _token_from_url(str(record.get(key) or ""))
        if TOKEN_RE.fullmatch(token):
            return token

    return secrets.token_urlsafe(24)


def _token_from_url(url: str) -> str:
    match = re.search(r"/s/([A-Za-z0-9_-]{20,96})(?:/|$)", url)
    return match.group(1) if match else ""


def _customer_safe_snippets(record: dict[str, Any]) -> list[str]:
    proof_items = record.get("proof_items") or []
    snippets = [
        str(item.get("snippet") or "").strip()
        for item in proof_items
        if isinstance(item, dict) and item.get("customer_preview_eligible")
    ]
    if not snippets:
        snippets = [str(value or "").strip() for value in record.get("evidence_snippets") or []]
    return safe_customer_snippets(snippets)


def _render_sections(sections: list[Any]) -> str:
    html = ""
    for section in sections[:3]:
        items = getattr(section, "items", [])[:6]
        if not items:
            continue
        items_html = ""
        for item in items:
            items_html += (
                "<div class=\"item\">"
                f"<div class=\"ja\">{escape(str(getattr(item, 'ja', '') or ''))}</div>"
                f"<div class=\"en\">{escape(str(getattr(item, 'en', '') or ''))}</div>"
                f"<div class=\"price\">{escape(str(getattr(item, 'price', '') or ''))}</div>"
                "</div>"
            )
        html += (
            "<div class=\"menu-section\">"
            f"<h2>{escape(str(getattr(section, 'header_ja', '') or 'メニュー'))} "
            f"<span lang=\"en\">/ {escape(str(getattr(section, 'header_en', '') or 'Menu'))}</span></h2>"
            f"{items_html}"
            "</div>"
        )
    return html


def _fallback_sample_sections(*, is_izakaya: bool) -> str:
    rows = (
        [
            ("焼き鳥", "Yakitori skewers", ""),
            ("唐揚げ", "Fried chicken", ""),
            ("飲み放題ルール", "All-you-can-drink rules", ""),
        ]
        if is_izakaya
        else [
            ("醤油ラーメン", "Shoyu ramen", ""),
            ("味玉", "Flavored egg topping", ""),
            ("券売機ボタン対応", "Ticket-machine button mapping", ""),
        ]
    )
    items = "".join(
        "<div class=\"item\">"
        f"<div class=\"ja\">{escape(ja)}</div>"
        f"<div class=\"en\">{escape(en)}</div>"
        f"<div class=\"price\">{escape(price)}</div>"
        "</div>"
        for ja, en, price in rows
    )
    return f"<div class=\"menu-section\"><h2>サンプル項目 <span lang=\"en\">/ Sample items</span></h2>{items}</div>"


def _improvement_notes(record: dict[str, Any], *, is_izakaya: bool) -> list[str]:
    notes = [
        "日本語の料理名を、短く分かりやすい英語名に整理しています。",
        "海外のお客様が注文前に判断しやすいよう、種類・追加・セットを分けて表示しています。",
    ]
    if record.get("machine_evidence_found"):
        notes.append("券売機がある場合は、メニュー名とボタン表記が対応するようにできます。")
    if is_izakaya or record.get("course_or_drink_plan_evidence_found"):
        notes.append("飲み放題・コース・ドリンクのルールは、料理メニューとは分けて説明できます。")
    notes.append("実制作では店舗様の最新メニュー写真を確認して、価格・内容を正確に反映します。")
    return notes


def _asset_links_html(record: dict[str, Any]) -> str:
    urls = [
        str(record.get("sample_menu_asset_url") or "").strip(),
        str(record.get("hosted_menu_sample_asset_url") or "").strip(),
    ]
    urls = [url for url in urls if url.startswith(("https://", "http://"))]
    if not urls:
        return ""
    links = "".join(f"<li><a href=\"{escape(url, quote=True)}\">{escape(url)}</a></li>" for url in urls)
    return f"<div class=\"asset-links\"><h2>関連ファイル</h2><ul>{links}</ul></div>"
