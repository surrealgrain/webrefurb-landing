from __future__ import annotations

from html import escape
from typing import Any

from .models import PreviewMenu, TicketMachineHint


def build_pitch(
    *,
    business_name: str,
    category: str,
    preview_menu: PreviewMenu,
    ticket_machine_hint: TicketMachineHint | None,
    recommended_package: str,
) -> dict[str, dict[str, str]]:
    """Build a legacy diagnosis pitch without leading on price."""

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

    subject = f"{business_name}様 — 英語注文ガイド制作のご提案"
    preview_sentence = (
        f"公開されているメニュー情報をもとに、小さな確認用サンプルを作るとこのような方向性になります：\n{preview_block}"
        if preview_block.strip()
        else "公開情報だけではお客様向けに安全にお見せできるサンプルが足りないため、現在のメニュー写真を拝見してから確認用サンプルを作成します。"
    )
    body = (
        f"{business_name}様\n\n"
        f"突然のご連絡失礼いたします。\n"
        f"貴店の注文導線を拝見し、海外からのお客様がメニュー内容や注文方法をすぐ理解できる英語の注文ガイドが役立つ可能性があると思いご連絡いたしました。\n\n"
        f"{preview_sentence}"
        f"{machine_block}\n\n"
        f"{preview_menu.disclaimer_ja}"
        f"\n\nご興味がございましたら、現在のメニューや券売機の写真を送っていただければ、貴店の実際の注文方法に合わせた確認用サンプルをお作りします。\n\n"
        f"よろしくお願いいたします。\n"
        f"Chris"
    )

    return {
        "native": {"subject": subject, "body": body},
    }
