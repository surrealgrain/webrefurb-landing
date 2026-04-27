from __future__ import annotations

from html import escape
from typing import Any

from .constants import (
    PACKAGE_A_PRICE_YEN, PACKAGE_B_PRICE_YEN,
    PACKAGE_A_KEY, PACKAGE_B_KEY,
    PACKAGE_A_LABEL, PACKAGE_B_LABEL,
)
from .models import PreviewMenu, TicketMachineHint


def build_pitch(
    *,
    business_name: str,
    category: str,
    preview_menu: PreviewMenu,
    ticket_machine_hint: TicketMachineHint | None,
    recommended_package: str,
) -> dict[str, dict[str, str]]:
    """Build a Japanese pitch with inline preview + both package prices."""

    # Build inline preview section
    preview_lines: list[str] = []
    for section in preview_menu.sections:
        preview_lines.append(f"\n{section.header_ja}")
        for item in section.items[:4]:
            preview_lines.append(f"・{item.ja} → {item.en}")

    preview_block = "\n".join(preview_lines)

    # Build ticket machine preview
    machine_block = ""
    if ticket_machine_hint and ticket_machine_hint.has_ticket_machine:
        btn_lines = []
        for btn in ticket_machine_hint.buttons[:4]:
            btn_lines.append(f"[{btn.label}]")
        machine_block = (
            "\n\n券売機の英語ガイドも、現在のボタン配置に合わせて作成できます：\n"
            + " ".join(btn_lines)
        )

    # Package pricing section
    pricing_block = (
        f"\n\n【料金】\n"
        f"・オンライン配送パッケージ：¥{PACKAGE_B_PRICE_YEN:,}（印刷用PDF・画像データ）\n"
        f"・対面配送パッケージ：¥{PACKAGE_A_PRICE_YEN:,}（印刷・ラミネート加工・店舗までお届け）"
    )

    subject = f"{business_name}様 — 英語メニュー翻訳サービスのご案内"
    body = (
        f"{business_name}様\n\n"
        f"突然のご連絡失礼いたします。\n"
        f"貴店のメニューを英語版にすることで、海外からのお客様がもっと注文しやすくなるのではないかと思い、ご連絡いたしました。\n\n"
        f"例として、貴店のメニューの一部を英語版にすると、このようなイメージになります：\n"
        f"{preview_block}"
        f"{machine_block}\n\n"
        f"{preview_menu.disclaimer_ja}"
        f"{pricing_block}\n\n"
        f"ご興味がございましたら、現在のメニューや券売機の写真を送っていただければ、正確な英語版をお作りします。\n\n"
        f"よろしくお願いいたします。\n"
        f"Chris"
    )

    return {
        "native": {"subject": subject, "body": body},
    }
