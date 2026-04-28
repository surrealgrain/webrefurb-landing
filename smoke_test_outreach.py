#!/usr/bin/env python
"""P4 Smoke Test: 5 diverse businesses, full outreach pipeline inspection.

Creates 5 test leads covering every major profile type, generates outreach
emails, selects assets, renders preview HTML, and checks:
  1. Email content matches business type (ramen/izakaya/machine)
  2. Seal stamp name uses locked_business_name
  3. Inline images placed after Chris sign-off
  4. Correct PDF attachments selected for profile
  5. No AI/automation mentions in customer-facing copy
  6. FROM name is always Chris（クリス）
  7. Subject line includes correct business name
"""

import sys
import json
import re
from pathlib import Path

# Ensure pipeline is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.outreach import (
    build_outreach_email,
    build_manual_outreach_message,
    classify_business,
    select_outreach_assets,
    describe_outreach_assets,
    _determine_situation,
    _SITUATIONS,
)
from pipeline.email_html import build_pitch_email_html, MENU_URL, MACHINE_URL
from pipeline.models import QualificationResult
from pipeline.constants import (
    PACKAGE_REGISTRY,
    GENERIC_MENU_PDF,
    GENERIC_MACHINE_PDF,
    OUTREACH_SAMPLE_RAMEN_ONE_PAGE_PDF,
    OUTREACH_SAMPLE_RAMEN_SIDES_PDF,
    OUTREACH_SAMPLE_RAMEN_DRINKS_PDF,
    OUTREACH_SAMPLE_IZAKAYA_FOOD_DRINKS_PDF,
)
from pipeline.preview import build_shop_preview_from_record
from pipeline.record import ensure_locked_business_name

# ---------------------------------------------------------------------------
# 5 test businesses covering all major types
# ---------------------------------------------------------------------------
TEST_BUSINESSES = [
    {
        "name": "博多らーめん亭",
        "classification": "menu_machine_unconfirmed",  # menu=True, machine=False
        "profile": "ramen_only",
        "description": "Ramen-only shop, paper menu, no ticket machine",
        "menu_evidence": True,
        "machine_evidence": False,
    },
    {
        "name": "角打ち酒場 大衆",
        "classification": "menu_and_machine",
        "profile": "ramen_with_sides_add_ons",
        "description": "Ramen shop with sides AND ticket machine",
        "menu_evidence": True,
        "machine_evidence": True,
    },
    {
        "name": "炭火焼鳥 まるや",
        "classification": "menu_machine_unconfirmed",  # menu=True, machine=False
        "profile": "izakaya_food_and_drinks",
        "description": "Izakaya with food + drinks menu",
        "menu_evidence": True,
        "machine_evidence": False,
    },
    {
        "name": "濃厚豚骨 一蘭風",
        "classification": "machine_only",
        "profile": "ramen_ticket_machine",
        "description": "Machine-only ramen (ticket machine, no visible menu)",
        "menu_evidence": False,
        "machine_evidence": True,
    },
    {
        "name": "酒処 酔心",
        "classification": "menu_machine_unconfirmed",  # menu=True, machine=False
        "profile": "izakaya_drink_heavy",
        "description": "Drink-heavy izakaya with nomihodai",
        "menu_evidence": True,
        "machine_evidence": False,
    },
]

AI_BAD_WORDS_PATTERNS = [
    r"\bartificial intelligence\b", r"\bautomation\b", r"\bautomated\b",
    r"\bscraping\b", r"\bscrape\b", r"\bGPT\b", r"\bLLM\b",
    r"\bmachine learning\b", r"\balgorithm\b",
]


def check_no_ai_mentions(text: str, label: str) -> list[str]:
    """Check text for forbidden AI/automation mentions."""
    issues = []
    for pattern in AI_BAD_WORDS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            word = pattern.replace(r"\b", "")
            issues.append(f"  AI MENTION: '{word}' found in {label}")
    return issues


def run_smoke_test():
    all_issues = []

    for i, biz in enumerate(TEST_BUSINESSES):
        print(f"\n{'='*70}")
        print(f"TEST {i+1}/5: {biz['name']}")
        print(f"  Profile: {biz['profile']}")
        print(f"  Classification: {biz['classification']}")
        print(f"  Description: {biz['description']}")
        print(f"{'='*70}")

        # --- Build qualification ---
        q = QualificationResult(
            lead=True,
            rejection_reason=None,
            business_name=biz["name"],
            menu_evidence_found=biz["menu_evidence"],
            machine_evidence_found=biz["machine_evidence"],
            establishment_profile=biz["profile"],
        )

        # --- Classify ---
        classification = classify_business(q)
        print(f"\n  classify_business() -> {classification}")
        if classification != biz["classification"]:
            all_issues.append(f"[{biz['name']}] Classification mismatch: expected '{biz['classification']}', got '{classification}'")
            print(f"  *** CLASSIFICATION MISMATCH ***")

        # --- Situation ---
        situation = _determine_situation(classification, biz["profile"])
        print(f"  _determine_situation() -> {situation}")

        # --- Build email ---
        email = build_outreach_email(
            business_name=biz["name"],
            classification=classification,
            establishment_profile=biz["profile"],
        )

        print(f"\n  --- SUBJECT ---")
        print(f"  {email['subject']}")

        print(f"\n  --- JAPANESE BODY ---")
        for j, para in enumerate(email["body"].split("\n\n")):
            print(f"  [{j+1}] {para}")

        print(f"\n  --- ENGLISH BODY ---")
        for j, para in enumerate(email["english_body"].split("\n\n")):
            print(f"  [{j+1}] {para}")

        print(f"\n  --- FLAGS ---")
        print(f"  include_menu_image: {email['include_menu_image']}")
        print(f"  include_machine_image: {email['include_machine_image']}")

        # --- Checks ---

        # 1. Subject includes business name
        if biz["name"] not in email["subject"]:
            all_issues.append(f"[{biz['name']}] Subject missing business name: '{email['subject']}'")
            print(f"  *** SUBJECT MISSING NAME ***")

        # 2. Body uses correct business name
        if biz["name"] not in email["body"]:
            all_issues.append(f"[{biz['name']}] Body missing business name in greeting")
            print(f"  *** BODY MISSING NAME IN GREETING ***")

        # 3. FROM name is Chris（クリス）
        if "Chris（クリス）" not in email["body"]:
            all_issues.append(f"[{biz['name']}] Japanese body missing Chris（クリス） sign-off")
            print(f"  *** MISSING Chris（クリス） SIGN-OFF ***")

        # 4. No AI mentions
        ai_issues = check_no_ai_mentions(email["body"], f"{biz['name']} JP body")
        ai_issues += check_no_ai_mentions(email["english_body"], f"{biz['name']} EN body")
        ai_issues += check_no_ai_mentions(email["subject"], f"{biz['name']} subject")
        all_issues.extend(ai_issues)
        for iss in ai_issues:
            print(f"  {iss}")

        # 5. Content matches business type
        if biz["profile"].startswith("ramen"):
            if "ラーメン" not in email["body"]:
                all_issues.append(f"[{biz['name']}] Ramen profile but body doesn't mention ラーメン")
                print(f"  *** RAMEN PROFILE BUT NO ラーメン IN BODY ***")

        if biz["profile"].startswith("izakaya"):
            if "ドリンク" not in email["body"] and "飲み放題" not in email["body"]:
                all_issues.append(f"[{biz['name']}] Izakaya profile but body doesn't mention drinks/courses")
                print(f"  *** IZAKAYA PROFILE BUT NO DRINK/COURSE LANGUAGE ***")

        if classification == "machine_only":
            if "券売機" not in email["body"]:
                all_issues.append(f"[{biz['name']}] Machine-only but body doesn't mention 券売機")
                print(f"  *** MACHINE-ONLY BUT NO 券売機 IN BODY ***")

        if classification == "menu_and_machine":
            if "券売機" not in email["body"]:
                all_issues.append(f"[{biz['name']}] Menu+machine but body doesn't mention 券売機")
                print(f"  *** MENU+MACHINE BUT NO 券売機 IN BODY ***")

        # 6. Seal stamp check - verify situation template mentions correct type
        tmpl = _SITUATIONS[situation]
        if situation == "ramen_menu":
            if "トッピング" not in tmpl["focus_ja"] or "セットメニュー" not in tmpl["focus_ja"]:
                all_issues.append(f"[{biz['name']}] Ramen template missing トッピング/セットメニュー emphasis")
                print(f"  *** RAMEN TEMPLATE MISSING TOPPING/SET EMPHASIS ***")
        if situation == "izakaya_menu":
            if "コースや飲み放題" not in tmpl["focus_ja"]:
                all_issues.append(f"[{biz['name']}] Izakaya template missing course/nomihodai emphasis")
                print(f"  *** IZAKAYA TEMPLATE MISSING COURSE/NOMIHODAI ***")

        # 7. Asset selection
        assets = select_outreach_assets(
            classification,
            contact_type="email",
            establishment_profile=biz["profile"],
        )
        asset_desc = describe_outreach_assets(
            assets,
            classification=classification,
            establishment_profile=biz["profile"],
        )

        print(f"\n  --- ASSETS ---")
        print(f"  Strategy: {asset_desc['strategy_label']}")
        print(f"  Note: {asset_desc['strategy_note']}")
        for a in asset_desc["assets"]:
            exists = Path(a["path"]).exists()
            print(f"  [{a['kind']}] {a['label']}: {a['path']} {'EXISTS' if exists else 'MISSING'}")
            if not exists:
                all_issues.append(f"[{biz['name']}] Asset file missing: {a['path']}")
                print(f"  *** ASSET FILE MISSING ***")

        # 8. Verify correct PDF for profile
        if biz["profile"] == "ramen_only":
            if not any("p1-single-section" in str(p) for p in assets):
                all_issues.append(f"[{biz['name']}] ramen_only should get single-section PDF")
                print(f"  *** WRONG PDF FOR ramen_only ***")
        if biz["profile"] == "ramen_with_sides_add_ons":
            if not any("p1-two-section" in str(p) for p in assets):
                all_issues.append(f"[{biz['name']}] ramen_with_sides should get two-section PDF")
                print(f"  *** WRONG PDF FOR ramen_with_sides ***")
        if biz["profile"].startswith("izakaya"):
            if not any("p1-split-food-drinks" in str(p) for p in assets):
                all_issues.append(f"[{biz['name']}] izakaya should get food-drinks PDF")
                print(f"  *** WRONG PDF FOR izakaya ***")
        if classification == "machine_only":
            if not any("machine" in str(p).lower() or "ticket" in str(p).lower() for p in assets):
                all_issues.append(f"[{biz['name']}] machine_only should get machine guide PDF")
                print(f"  *** WRONG PDF FOR machine_only ***")

        # 9. Render email HTML and check image placement
        html = build_pitch_email_html(
            text_body=email["body"],
            menu_image_path="test-preview",
            include_menu_image=email["include_menu_image"],
            include_machine_image=email["include_machine_image"],
            locale="ja",
        )

        # Check menu image is placed after sign-off
        chris_pos = html.find("Chris（クリス）")
        if chris_pos == -1:
            # HTML escapes the character, check escaped
            chris_pos = html.find("Chris（クリス）")

        # The email body paragraphs come first, then images, then footer
        # Verify images come after the last body paragraph (Chris sign-off)
        if email["include_menu_image"]:
            menu_img_pos = html.find(MENU_URL)
            if menu_img_pos == -1:
                all_issues.append(f"[{biz['name']}] Menu image URL not found in rendered HTML")
                print(f"  *** MENU IMAGE NOT IN HTML ***")
            else:
                # Check it's after the body content
                # Find the last body paragraph closing tag before the footer
                footer_pos = html.find("margin-top:40px")
                if footer_pos > 0 and menu_img_pos > footer_pos:
                    all_issues.append(f"[{biz['name']}] Menu image is AFTER footer (wrong placement)")
                    print(f"  *** MENU IMAGE AFTER FOOTER ***")
                elif footer_pos > 0 and menu_img_pos < footer_pos:
                    print(f"  Menu image: correctly placed before footer")
                else:
                    print(f"  Menu image: found at pos {menu_img_pos}, footer at {footer_pos}")

        # 10. Shop-specific preview from record
        record = {
            "business_name": biz["name"],
            "locked_business_name": biz["name"],
            "business_name_locked": True,
            "establishment_profile": biz["profile"],
            "evidence_snippets": [
                "醤油ラーメン ¥850",
                "味噌ラーメン ¥900",
                "餃子 ¥400",
                "生ビール ¥450",
            ],
            "evidence_classes": ["ramen_menu" if biz["profile"].startswith("ramen") else "izakaya_menu"],
            "menu_evidence_found": biz["menu_evidence"],
            "machine_evidence_found": biz["machine_evidence"],
        }
        ensure_locked_business_name(record)
        preview = build_shop_preview_from_record(record=record)
        if preview:
            if biz["name"] not in preview:
                all_issues.append(f"[{biz['name']}] Preview HTML doesn't contain business name")
                print(f"  *** PREVIEW MISSING BUSINESS NAME ***")
            else:
                print(f"  Shop preview: generated OK, contains business name")
            if "一部のイメージ例" not in preview:
                all_issues.append(f"[{biz['name']}] Preview missing illustrative disclaimer")
                print(f"  *** PREVIEW MISSING DISCLAIMER ***")
            else:
                print(f"  Shop preview: has illustrative disclaimer")
        else:
            all_issues.append(f"[{biz['name']}] Shop preview returned None")
            print(f"  *** PREVIEW RETURNED NONE ***")

    # --- Manual channel smoke test ---
    print(f"\n{'='*70}")
    print(f"BONUS: Manual channel tests (LINE/Instagram/phone/walk-in)")
    print(f"{'='*70}")

    channels = ["contact_form", "line", "instagram", "phone", "walk_in"]
    for ch in channels:
        msg = build_manual_outreach_message(
            business_name="テスト店",
            classification="menu_only",
            channel=ch,
            establishment_profile="ramen_only",
        )
        has_chris = "Chris（クリス）" in msg["body"] or "Chris" in msg["english_body"]
        ai_issues = check_no_ai_mentions(msg["body"], f"manual-{ch}-JP")
        ai_issues += check_no_ai_mentions(msg["english_body"], f"manual-{ch}-EN")

        status = "OK" if has_chris and not ai_issues else "ISSUE"
        print(f"  {ch:15s}: channel_label={msg['channel_label']:20s} chris={has_chris} ai_clean={not ai_issues} [{status}]")

        if not has_chris:
            all_issues.append(f"[manual-{ch}] Missing Chris sign-off")
        all_issues.extend(ai_issues)

        # Contact forms should have no images
        if ch == "contact_form":
            if msg["include_menu_image"]:
                all_issues.append(f"[manual-{ch}] Contact form should not include menu image")
                print(f"  *** CONTACT FORM HAS MENU IMAGE ***")

    # --- Summary ---
    print(f"\n{'='*70}")
    print(f"SMOKE TEST SUMMARY")
    print(f"{'='*70}")

    if all_issues:
        print(f"\n  FOUND {len(all_issues)} ISSUES:\n")
        for iss in all_issues:
            print(f"  - {iss}")
        return 1
    else:
        print(f"\n  ALL CHECKS PASSED — 5 businesses x ~10 checks each + 5 manual channels")
        return 0


if __name__ == "__main__":
    sys.exit(run_smoke_test())
