"""Comprehensive tests for the email discovery pipeline.

Tests cover:
  1. Email extraction with Japanese obfuscation normalization
  2. Email classification
  3. Genre classification
  4. Menu detection
  5. Compliance / refusal warning detection
  6. Tokushoho page parsing
  7. Operator company resolution
  8. Contact form detection
  9. Lead scoring
  10. Input loading / output writing
  11. Search query generation
  12. SQLite persistence
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _write_csv(path: str, rows: list[dict]):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# 1. Email extraction
# ---------------------------------------------------------------------------

class TestEmailExtraction:
    """Test email_extractor.py with Japanese obfuscation patterns."""

    def test_standard_email(self):
        from pipeline.email_discovery.email_extractor import extract_emails
        results = extract_emails(text="お問い合わせ: info@ramen-shop.jp")
        assert len(results) == 1
        assert results[0].email == "info@ramen-shop.jp"

    def test_mailto_link(self):
        from pipeline.email_discovery.email_extractor import extract_emails
        html = '<a href="mailto:contact@ramen-shop.jp">お問い合わせ</a>'
        results = extract_emails(text="", html=html)
        assert any(e.email == "contact@ramen-shop.jp" for e in results)

    def test_fullwidth_at(self):
        from pipeline.email_discovery.email_extractor import extract_emails
        text = "メール：info＠ramen-shop.jp"
        results = extract_emails(text=text)
        assert any(e.email == "info@ramen-shop.jp" for e in results)

    def test_bracket_at(self):
        from pipeline.email_discovery.email_extractor import extract_emails
        text = "メール: info [at] ramen-shop.jp"
        results = extract_emails(text=text)
        assert any(e.email == "info@ramen-shop.jp" for e in results)

    def test_paren_at(self):
        from pipeline.email_discovery.email_extractor import extract_emails
        text = "Email: info(at)ramen-shop.jp"
        results = extract_emails(text=text)
        assert any(e.email == "info@ramen-shop.jp" for e in results)

    def test_star_at_with_context(self):
        from pipeline.email_discovery.email_extractor import extract_emails
        text = "★を@に変換してお送りください: info★ramen-shop.jp"
        results = extract_emails(text=text)
        assert any(e.email == "info@ramen-shop.jp" for e in results)

    def test_star_at_without_context_not_extracted(self):
        from pipeline.email_discovery.email_extractor import extract_emails
        text = "info★ramen-shop.jp"
        results = extract_emails(text=text)
        assert not any(e.email == "info@ramen-shop.jp" for e in results)

    def test_japanese_prefix(self):
        from pipeline.email_discovery.email_extractor import extract_emails
        text = "メール：shop@ramen.co.jp"
        results = extract_emails(text=text)
        assert any(e.email == "shop@ramen.co.jp" for e in results)

    def test_email_prefix(self):
        from pipeline.email_discovery.email_extractor import extract_emails
        text = "E-mail: cs@izakaya.or.jp"
        results = extract_emails(text=text)
        assert any(e.email == "cs@izakaya.or.jp" for e in results)

    def test_false_positive_example_com(self):
        from pipeline.email_discovery.email_extractor import extract_emails
        text = "Contact us at info@example.com"
        results = extract_emails(text=text)
        assert not any("example.com" in e.email for e in results)

    def test_false_positive_tracking_id(self):
        from pipeline.email_discovery.email_extractor import extract_emails
        text = "ga-123456@example.com tracking-id-abc@example.com"
        results = extract_emails(text=text)
        assert len(results) == 0

    def test_deduplication(self):
        from pipeline.email_discovery.email_extractor import extract_emails
        text = "info@shop.jp and info@shop.jp again"
        results = extract_emails(text=text)
        emails = [e.email for e in results]
        assert emails.count("info@shop.jp") == 1

    def test_multiple_emails(self):
        from pipeline.email_discovery.email_extractor import extract_emails
        text = "お問い合わせ: info@shop.jp 採用: recruit@shop.jp"
        results = extract_emails(text=text)
        assert len(results) == 2

    def test_empty_input(self):
        from pipeline.email_discovery.email_extractor import extract_emails
        results = extract_emails(text="")
        assert results == []

    def test_fullwidth_hyphen_in_domain(self):
        from pipeline.email_discovery.email_extractor import extract_emails
        text = "info＠ramen－shop.jp"
        results = extract_emails(text=text)
        # Should normalize full-width hyphen
        assert any("ramen" in e.email for e in results)

    def test_trailing_punctuation_stripped(self):
        from pipeline.email_discovery.email_extractor import extract_emails
        text = "Email: info@shop.jp。"
        results = extract_emails(text=text)
        assert any(e.email == "info@shop.jp" for e in results)


# ---------------------------------------------------------------------------
# 2. Email classification
# ---------------------------------------------------------------------------

class TestEmailClassification:
    def test_general_business_info(self):
        from pipeline.email_discovery.email_classifier import classify_email
        from pipeline.email_discovery.email_extractor import ExtractedEmail
        from pipeline.email_discovery.models import EmailType

        ext = ExtractedEmail(email="info@ramen-shop.jp", method="standard")
        result = classify_email(ext, source_page_type="contact")
        assert result == EmailType.GENERAL_BUSINESS

    def test_operator_company(self):
        from pipeline.email_discovery.email_classifier import classify_email
        from pipeline.email_discovery.email_extractor import ExtractedEmail
        from pipeline.email_discovery.models import EmailType

        ext = ExtractedEmail(email="info@food-corp.jp", method="standard")
        result = classify_email(ext, source_page_type="company")
        assert result == EmailType.OPERATOR_COMPANY

    def test_tokushoho_email(self):
        from pipeline.email_discovery.email_classifier import classify_email
        from pipeline.email_discovery.email_extractor import ExtractedEmail
        from pipeline.email_discovery.models import EmailType

        ext = ExtractedEmail(email="shop@ramen-online.jp", method="standard")
        result = classify_email(ext, source_page_type="tokushoho")
        assert result == EmailType.ONLINE_SHOP

    def test_recruitment_email(self):
        from pipeline.email_discovery.email_classifier import classify_email
        from pipeline.email_discovery.email_extractor import ExtractedEmail
        from pipeline.email_discovery.models import EmailType

        ext = ExtractedEmail(email="recruit@shop.jp", method="standard")
        result = classify_email(ext, source_page_type="recruitment")
        assert result == EmailType.RECRUITMENT

    def test_personal_gmail(self):
        from pipeline.email_discovery.email_classifier import classify_email
        from pipeline.email_discovery.email_extractor import ExtractedEmail
        from pipeline.email_discovery.models import EmailType

        ext = ExtractedEmail(email="taro@gmail.com", method="standard")
        result = classify_email(ext, source_page_type="unknown")
        assert result == EmailType.PERSONAL_OR_UNCLEAR

    def test_rank_emails(self):
        from pipeline.email_discovery.email_classifier import rank_emails
        from pipeline.email_discovery.email_extractor import ExtractedEmail
        from pipeline.email_discovery.models import EmailType

        emails = [
            (ExtractedEmail(email="recruit@shop.jp", method="standard"), EmailType.RECRUITMENT),
            (ExtractedEmail(email="info@shop.jp", method="mailto"), EmailType.GENERAL_BUSINESS),
            (ExtractedEmail(email="taro@gmail.com", method="standard"), EmailType.PERSONAL_OR_UNCLEAR),
        ]
        ranked = rank_emails(emails)
        assert ranked[0][1] == EmailType.GENERAL_BUSINESS
        assert ranked[-1][1] == EmailType.PERSONAL_OR_UNCLEAR


# ---------------------------------------------------------------------------
# 3. Genre classification
# ---------------------------------------------------------------------------

class TestGenreClassification:
    def test_ramen_detected(self):
        from pipeline.email_discovery.genre_classifier import classify_genre
        result = classify_genre(genre_text="ラーメン")
        assert result.is_approved
        assert result.genre == "ramen"
        assert result.confidence >= 0.9

    def test_izakaya_detected(self):
        from pipeline.email_discovery.genre_classifier import classify_genre
        result = classify_genre(genre_text="居酒屋")
        assert result.is_approved
        assert result.genre == "izakaya"

    def test_yakitori_adjacent(self):
        from pipeline.email_discovery.genre_classifier import classify_genre
        result = classify_genre(genre_text="焼鳥")
        assert result.is_approved
        assert result.category == "adjacent"

    def test_sushi_excluded(self):
        from pipeline.email_discovery.genre_classifier import classify_genre
        result = classify_genre(genre_text="寿司")
        assert not result.is_approved
        assert result.category == "excluded"

    def test_ramen_in_shop_name(self):
        from pipeline.email_discovery.genre_classifier import classify_genre
        result = classify_genre(shop_name="麺屋武蔵 ラーメン")
        assert result.is_approved

    def test_unknown_genre(self):
        from pipeline.email_discovery.genre_classifier import classify_genre
        result = classify_genre(genre_text="レストラン")
        assert result.category == "unknown"
        assert not result.is_approved

    def test_empty_input(self):
        from pipeline.email_discovery.genre_classifier import classify_genre
        result = classify_genre()
        assert result.category == "unknown"


# ---------------------------------------------------------------------------
# 4. Menu detection
# ---------------------------------------------------------------------------

class TestMenuDetection:
    def test_basic_menu_terms(self):
        from pipeline.email_discovery.menu_detector import detect_menu_in_text
        result = detect_menu_in_text("当店のメニューをご覧ください")
        assert result.has_menu

    def test_ramen_terms(self):
        from pipeline.email_discovery.menu_detector import detect_menu_in_text
        result = detect_menu_in_text("醤油ラーメン 850円 味噌ラーメン 900円")
        assert result.has_ramen_terms

    def test_izakaya_terms(self):
        from pipeline.email_discovery.menu_detector import detect_menu_in_text
        result = detect_menu_in_text("飲み放題 1500円 生ビール 各種日本酒")
        assert result.has_izakaya_terms

    def test_ticket_machine(self):
        from pipeline.email_discovery.menu_detector import detect_menu_in_text
        result = detect_menu_in_text("食券をお買い求めください")
        assert result.has_ticket_machine

    def test_no_menu(self):
        from pipeline.email_discovery.menu_detector import detect_menu_in_text
        result = detect_menu_in_text("お問い合わせページ")
        assert not result.has_menu

    def test_menu_url_detection(self):
        from pipeline.email_discovery.menu_detector import detect_menu_url
        urls = detect_menu_url([
            "https://shop.jp/menu",
            "https://shop.jp/about",
            "https://shop.jp/contact",
        ])
        assert len(urls) == 1
        assert "menu" in urls[0]


# ---------------------------------------------------------------------------
# 5. Compliance / refusal detection
# ---------------------------------------------------------------------------

class TestCompliance:
    def test_refusal_detected(self):
        from pipeline.email_discovery.compliance import check_compliance
        result = check_compliance("当店への営業メールお断り")
        assert result.has_refusal_warning
        assert result.should_skip

    def test_sales_refusal(self):
        from pipeline.email_discovery.compliance import check_compliance
        result = check_compliance("セールスお断り")
        assert result.has_refusal_warning

    def test_no_issues(self):
        from pipeline.email_discovery.compliance import check_compliance
        result = check_compliance("お問い合わせはinfo@shop.jpまで")
        assert not result.is_problematic

    def test_reservation_only(self):
        from pipeline.email_discovery.compliance import check_compliance
        result = check_compliance("このメールアドレスは予約専用です")
        assert result.is_reservation_only

    def test_recruitment_only(self):
        from pipeline.email_discovery.compliance import check_compliance
        result = check_compliance("採用専用メールアドレス")
        assert result.is_recruitment_only

    def test_closure_detected(self):
        from pipeline.email_discovery.compliance import check_compliance
        result = check_compliance("令和5年3月31日をもちまして閉店いたしました")
        assert result.appears_closed

    def test_email_safety_check(self):
        from pipeline.email_discovery.compliance import is_email_safe_to_contact
        safe, reason = is_email_safe_to_contact("info@shop.jp", "営業メールお断り")
        assert not safe
        assert "Refusal" in reason

    def test_email_safety_ok(self):
        from pipeline.email_discovery.compliance import is_email_safe_to_contact
        safe, reason = is_email_safe_to_contact("info@shop.jp", "お問い合わせフォーム")
        assert safe
        assert reason == ""


# ---------------------------------------------------------------------------
# 6. Tokushoho parsing
# ---------------------------------------------------------------------------

class TestTokushoho:
    def test_is_tokushoho_page_by_url(self):
        from pipeline.email_discovery.tokushoho import is_tokushoho_page
        assert is_tokushoho_page("https://shop.jp/tokushoho")

    def test_is_tokushoho_page_by_title(self):
        from pipeline.email_discovery.tokushoho import is_tokushoho_page
        assert is_tokushoho_page("https://shop.jp/legal", title="特定商取引法に基づく表記")

    def test_is_tokushoho_page_by_content(self):
        from pipeline.email_discovery.tokushoho import is_tokushoho_page
        assert is_tokushoho_page("https://shop.jp/page", text="特定商取引法に基づく表記")

    def test_not_tokushoho(self):
        from pipeline.email_discovery.tokushoho import is_tokushoho_page
        assert not is_tokushoho_page("https://shop.jp/menu", title="メニュー")

    def test_parse_tokushoho_page(self):
        from pipeline.email_discovery.tokushoho import parse_tokushoho_page
        text = """
        特定商取引法に基づく表記
        販売業者：株式会社ラーメン foods
        代表者：山田太郎
        所在地：東京都新宿区西新宿1-1-1
        電話番号：03-1234-5678
        メールアドレス：info@ramen-foods.jp
        URL：https://ramen-foods.jp
        """
        result = parse_tokushoho_page(
            url="https://shop.jp/tokushoho",
            text=text,
        )
        assert result.is_tokushoho
        assert "株式会社ラーメン" in result.seller_name or "ラーメン" in result.seller_name
        assert result.email == "info@ramen-foods.jp"
        assert "03-1234-5678" in result.phone

    def test_find_tokushoho_links(self):
        from pipeline.email_discovery.tokushoho import find_tokushoho_links
        html = '<a href="/tokushoho">特定商取引法に基づく表記</a>'
        links = find_tokushoho_links(html)
        assert len(links) == 1
        assert "/tokushoho" in links[0]


# ---------------------------------------------------------------------------
# 7. Operator company resolution
# ---------------------------------------------------------------------------

class TestOperatorResolver:
    def test_extract_company_name(self):
        from pipeline.email_discovery.operator_resolver import extract_company_name
        text = "運営会社：株式会社ラーメンフーズ"
        name = extract_company_name(text)
        assert name is not None
        assert "株式会社" in name

    def test_extract_company_from_seller(self):
        from pipeline.email_discovery.operator_resolver import extract_company_name
        text = "販売業者：株式会社飲食ホールディングス"
        name = extract_company_name(text)
        assert name is not None
        assert "株式会社" in name

    def test_no_company_found(self):
        from pipeline.email_discovery.operator_resolver import extract_company_name
        text = "おいしいラーメン屋です"
        name = extract_company_name(text)
        assert name is None

    def test_extract_company_url(self):
        from pipeline.email_discovery.operator_resolver import extract_company_url
        text = "運営会社：株式会社ラーメン URL: https://ramen-corp.jp"
        url = extract_company_url(text, "株式会社ラーメン")
        assert url is not None
        assert "ramen-corp.jp" in url

    def test_resolve_from_page(self):
        from pipeline.email_discovery.operator_resolver import resolve_from_page
        text = "運営会社：株式会社フーズ\nURL：https://foods-corp.jp"
        info = resolve_from_page("https://shop.jp/about", text, "company")
        assert info is not None
        assert "株式会社" in info.name


# ---------------------------------------------------------------------------
# 8. Contact form detection
# ---------------------------------------------------------------------------

class TestContactFormDetection:
    def test_detect_official_form(self):
        from pipeline.email_discovery.contact_form_detector import detect_contact_form
        html = """
        <html><head><title>お問い合わせ</title></head>
        <body>
        <form method="post" action="/contact/submit">
            <input name="name" type="text">
            <input name="email" type="email">
            <textarea name="message"></textarea>
            <button type="submit">送信</button>
        </form>
        </body></html>
        """
        result = detect_contact_form("https://shop.jp/contact", html=html)
        assert result.is_contact_form
        assert result.form_type == "official"

    def test_reservation_form_not_detected(self):
        from pipeline.email_discovery.contact_form_detector import detect_contact_form
        html = """
        <html><head><title>ご予約</title></head>
        <body>
        <form method="post" action="/reserve">
            <input name="name" type="text">
            <input name="人数" type="number">
            <input name="date" type="date">
        </form>
        </body></html>
        """
        result = detect_contact_form("https://shop.jp/reserve", html=html)
        # Should NOT be detected as a contact form
        assert not result.is_contact_form or "予約" in str(result.field_names)

    def test_no_form_on_page(self):
        from pipeline.email_discovery.contact_form_detector import detect_contact_form
        result = detect_contact_form("https://shop.jp/about", html="<p>About us</p>")
        assert not result.is_contact_form

    def test_detect_forms_from_links(self):
        from pipeline.email_discovery.contact_form_detector import detect_contact_forms_from_links
        links = [
            "https://shop.jp/contact",
            "https://shop.jp/menu",
            "https://shop.jp/inquiry",
        ]
        forms = detect_contact_forms_from_links(links)
        assert len(forms) == 2
        assert all(f.form_type == "official" for f in forms)


# ---------------------------------------------------------------------------
# 9. Lead scoring
# ---------------------------------------------------------------------------

class TestLeadScoring:
    def test_high_score_with_good_email(self):
        from pipeline.email_discovery.scorer import score_lead
        from pipeline.email_discovery.models import EnrichedLead
        from pipeline.email_discovery.config import DiscoveryConfig

        lead = EnrichedLead(
            shop_name="テストラーメン",
            genre="ramen",
            genre_confidence=1.0,
            prefecture="東京都",
            address="東京都新宿区",
            best_email="info@test-ramen.jp",
            best_email_type="general_business_contact",
            email_source_url="https://test-ramen.jp/contact",
            menu_detected=True,
            official_site_url="https://test-ramen.jp",
            launch_ready=True,
        )
        score = score_lead(lead)
        assert score >= 60  # Should be a strong lead

    def test_low_score_no_email(self):
        from pipeline.email_discovery.scorer import score_lead
        from pipeline.email_discovery.models import EnrichedLead

        lead = EnrichedLead(
            shop_name="テスト",
            genre="ramen",
            genre_confidence=0.5,
        )
        score = score_lead(lead)
        assert score < 30  # Should be low without email

    def test_zero_score_with_refusal(self):
        from pipeline.email_discovery.scorer import score_lead
        from pipeline.email_discovery.models import EnrichedLead

        lead = EnrichedLead(
            shop_name="テスト",
            no_sales_warning=True,
            best_email="info@shop.jp",
            best_email_type="general_business_contact",
        )
        score = score_lead(lead)
        assert score < 10  # Should be near-zero

    def test_reason_codes_populated(self):
        from pipeline.email_discovery.scorer import score_lead
        from pipeline.email_discovery.models import EnrichedLead

        lead = EnrichedLead(
            genre="ramen",
            genre_confidence=1.0,
            prefecture="東京都",
            best_email="info@shop.jp",
            best_email_type="general_business_contact",
        )
        score_lead(lead)
        assert len(lead.reason_codes) > 0


# ---------------------------------------------------------------------------
# 10. Input loading / output writing
# ---------------------------------------------------------------------------

class TestInputOutput:
    def test_load_csv(self, tmp_path):
        from pipeline.email_discovery.input_loader import load_leads_csv
        csv_path = tmp_path / "test.csv"
        _write_csv(str(csv_path), [
            {"shop_name": "テストラーメン", "genre": "ラーメン", "city": "新宿区",
             "prefecture": "東京都", "phone": "03-1234-5678"},
        ])
        leads = load_leads_csv(str(csv_path))
        assert len(leads) == 1
        assert leads[0].shop_name == "テストラーメン"
        assert leads[0].genre == "ラーメン"

    def test_load_csv_dedup(self, tmp_path):
        from pipeline.email_discovery.input_loader import load_leads_csv
        csv_path = tmp_path / "dup.csv"
        _write_csv(str(csv_path), [
            {"shop_name": "テスト", "prefecture": "東京都"},
            {"shop_name": "テスト", "prefecture": "東京都"},
        ])
        leads = load_leads_csv(str(csv_path))
        assert len(leads) == 1

    def test_load_csv_skip_no_name(self, tmp_path):
        from pipeline.email_discovery.input_loader import load_leads_csv
        csv_path = tmp_path / "noname.csv"
        _write_csv(str(csv_path), [
            {"shop_name": "", "prefecture": "東京都"},
            {"shop_name": "ある店", "prefecture": "東京都"},
        ])
        leads = load_leads_csv(str(csv_path))
        assert len(leads) == 1

    def test_write_csv(self, tmp_path):
        from pipeline.email_discovery.output_writer import write_csv
        from pipeline.email_discovery.models import EnrichedLead

        leads = [EnrichedLead(shop_name="テスト", best_email="info@test.jp")]
        path = write_csv(leads, str(tmp_path / "out.csv"))
        assert Path(path).exists()
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["best_email"] == "info@test.jp"

    def test_write_jsonl(self, tmp_path):
        from pipeline.email_discovery.output_writer import write_jsonl
        from pipeline.email_discovery.models import EnrichedLead

        leads = [EnrichedLead(shop_name="テスト", best_email="info@test.jp")]
        path = write_jsonl(leads, str(tmp_path / "out.jsonl"))
        assert Path(path).exists()
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["best_email"] == "info@test.jp"

    def test_file_not_found(self):
        from pipeline.email_discovery.input_loader import load_leads_csv
        with pytest.raises(FileNotFoundError):
            load_leads_csv("/nonexistent/path.csv")


# ---------------------------------------------------------------------------
# 11. Search query generation
# ---------------------------------------------------------------------------

class TestQueryGeneration:
    def test_basic_queries(self):
        from pipeline.email_discovery.query_generator import generate_lead_queries
        from pipeline.email_discovery.models import InputLead

        lead = InputLead(shop_name="麺屋武蔵")
        queries = generate_lead_queries(lead, max_queries=5)
        assert len(queries) == 5
        assert any("麺屋武蔵" in q for q in queries)
        assert any("メールアドレス" in q for q in queries)
        assert any("特商法" in q or "特定商取引法" in q for q in queries)

    def test_phone_queries(self):
        from pipeline.email_discovery.query_generator import generate_lead_queries
        from pipeline.email_discovery.models import InputLead

        lead = InputLead(shop_name="テスト", phone="03-1234-5678")
        queries = generate_lead_queries(lead, max_queries=20)
        assert any("03-1234-5678" in q for q in queries)

    def test_address_queries(self):
        from pipeline.email_discovery.query_generator import generate_lead_queries
        from pipeline.email_discovery.models import InputLead

        lead = InputLead(shop_name="テスト", address="東京都新宿区西新宿1-1-1")
        queries = generate_lead_queries(lead, max_queries=20)
        # Should include address-based queries
        assert len(queries) > 5

    def test_max_queries_limit(self):
        from pipeline.email_discovery.query_generator import generate_lead_queries
        from pipeline.email_discovery.models import InputLead

        lead = InputLead(shop_name="テスト", phone="03-1234", address="東京都")
        queries = generate_lead_queries(lead, max_queries=3)
        assert len(queries) == 3

    def test_category_queries(self):
        from pipeline.email_discovery.query_generator import generate_category_queries
        queries = generate_category_queries()
        assert len(queries) > 0
        assert any("ラーメン" in q for q in queries)
        assert any("居酒屋" in q for q in queries)


# ---------------------------------------------------------------------------
# 12. SQLite persistence
# ---------------------------------------------------------------------------

class TestDatabase:
    def test_upsert_and_get(self, tmp_path):
        from pipeline.email_discovery.db import DiscoveryDB
        from pipeline.email_discovery.models import EnrichedLead

        db = DiscoveryDB(str(tmp_path / "test.db"))
        lead = EnrichedLead(
            lead_id="LD-test123",
            shop_name="テストラーメン",
            prefecture="東京都",
            best_email="info@test.jp",
            confidence_score=75.0,
            launch_ready=True,
        )
        db.upsert_lead(lead)

        fetched = db.get_lead("LD-test123")
        assert fetched is not None
        assert fetched["shop_name"] == "テストラーメン"
        assert fetched["best_email"] == "info@test.jp"
        assert fetched["launch_ready"] == 1
        db.close()

    def test_dedup_check(self, tmp_path):
        from pipeline.email_discovery.db import DiscoveryDB
        from pipeline.email_discovery.models import EnrichedLead

        db = DiscoveryDB(str(tmp_path / "test.db"))
        db.upsert_lead(EnrichedLead(
            lead_id="LD-abc",
            shop_name="テスト",
            prefecture="東京都",
        ))
        assert db.lead_exists("テスト", "東京都")
        assert not db.lead_exists("テスト", "大阪府")
        db.close()

    def test_stats(self, tmp_path):
        from pipeline.email_discovery.db import DiscoveryDB
        from pipeline.email_discovery.models import EnrichedLead

        db = DiscoveryDB(str(tmp_path / "test.db"))
        db.upsert_lead(EnrichedLead(
            lead_id="LD-1", shop_name="A", prefecture="東京都",
            best_email="a@test.jp", launch_ready=True, confidence_score=80,
        ))
        db.upsert_lead(EnrichedLead(
            lead_id="LD-2", shop_name="B", prefecture="大阪府",
            confidence_score=30,
        ))
        stats = db.stats()
        assert stats["total_leads"] == 2
        assert stats["launch_ready"] == 1
        assert stats["with_email"] == 1
        db.close()

    def test_insert_email(self, tmp_path):
        from pipeline.email_discovery.db import DiscoveryDB
        from pipeline.email_discovery.models import EnrichedLead, DiscoveredEmail, EmailType

        db = DiscoveryDB(str(tmp_path / "test.db"))
        db.upsert_lead(EnrichedLead(lead_id="LD-x", shop_name="X"))
        db.insert_email("LD-x", DiscoveredEmail(
            email="info@test.jp",
            email_type=EmailType.GENERAL_BUSINESS,
            source_url="https://test.jp/contact",
        ))
        emails = db.get_emails_for_lead("LD-x")
        assert len(emails) == 1
        assert emails[0]["email"] == "info@test.jp"
        db.close()


# ---------------------------------------------------------------------------
# 13. Config loading
# ---------------------------------------------------------------------------

class TestConfig:
    def test_default_config(self):
        from pipeline.email_discovery.config import load_config
        config = load_config()
        assert config.search.provider == "serper"
        assert config.scoring.launch_ready_threshold == 70.0
        assert len(config.allowed_genres) > 0
        assert len(config.refusal_phrases) > 0

    def test_yaml_override(self, tmp_path):
        from pipeline.email_discovery.config import load_config
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text("dry_run: true\nlog_level: DEBUG\n")
        config = load_config(str(yaml_path))
        assert config.dry_run is True
        assert config.log_level == "DEBUG"

    def test_env_override(self, monkeypatch):
        from pipeline.email_discovery.config import load_config
        monkeypatch.setenv("SERPER_API_KEY", "test-key-123")
        config = load_config()
        assert config.search.serper_api_key == "test-key-123"


# ---------------------------------------------------------------------------
# 14. Dry-run pipeline (integration)
# ---------------------------------------------------------------------------

class TestDryRunPipeline:
    def test_dry_run_no_network(self, tmp_path):
        """Verify pipeline runs in dry-run mode without any network calls."""
        from pipeline.email_discovery.pipeline import discover_emails
        from pipeline.email_discovery.config import DiscoveryConfig, PersistenceConfig

        csv_path = tmp_path / "leads.csv"
        _write_csv(str(csv_path), [
            {"shop_name": "テストラーメン", "genre": "ラーメン", "prefecture": "東京都"},
        ])

        config = DiscoveryConfig(
            dry_run=True,
            persistence=PersistenceConfig(
                sqlite_path=str(tmp_path / "test.db"),
                csv_output_path=str(tmp_path / "out.csv"),
                jsonl_output_path=str(tmp_path / "out.jsonl"),
            ),
        )

        results = discover_emails(
            input_csv=str(csv_path),
            config=config,
        )
        assert len(results) == 1
        # Should not have found emails (no network)
        assert results[0].shop_name == "テストラーメン"
        # Genre should be classified
        assert results[0].genre_confidence > 0

    def test_dry_run_genre_excluded(self, tmp_path):
        from pipeline.email_discovery.pipeline import discover_emails
        from pipeline.email_discovery.config import DiscoveryConfig, PersistenceConfig

        csv_path = tmp_path / "leads.csv"
        _write_csv(str(csv_path), [
            {"shop_name": "テスト寿司", "genre": "寿司", "prefecture": "東京都"},
        ])

        config = DiscoveryConfig(
            dry_run=True,
            persistence=PersistenceConfig(
                sqlite_path=str(tmp_path / "test.db"),
                csv_output_path=str(tmp_path / "out.csv"),
                jsonl_output_path=str(tmp_path / "out.jsonl"),
            ),
        )

        results = discover_emails(str(csv_path), config=config)
        assert len(results) == 1
        assert results[0].next_best_action == "SKIP_GENRE_MISMATCH"


# ---------------------------------------------------------------------------
# 15. WebRefurb bridge
# ---------------------------------------------------------------------------

class TestWebRefurbBridge:
    def test_lead_record_to_input_lead_extracts_existing_fields(self):
        from pipeline.email_discovery.bridge import lead_record_to_input_lead

        lead = lead_record_to_input_lead({
            "business_name": "麺屋テスト",
            "primary_category_v1": "ramen",
            "address": "東京都渋谷区神南1-2-3",
            "phone": "03-1234-5678",
            "website": "https://ramen-test.jp",
            "map_url": "https://maps.example/test",
            "evidence_urls": ["https://ramen-test.jp/menu"],
        })

        assert lead.shop_name == "麺屋テスト"
        assert lead.genre == "ramen"
        assert lead.prefecture == "東京都"
        assert lead.city == "渋谷区"
        assert lead.menu_url == "https://ramen-test.jp/menu"

    def test_enriched_to_contact_records_filters_non_outreach_emails(self):
        from pipeline.email_discovery.bridge import enriched_to_contact_records
        from pipeline.email_discovery.models import (
            DiscoveredContactForm,
            DiscoveredEmail,
            EmailType,
            EnrichedLead,
        )

        enriched = EnrichedLead(
            crawl_timestamp="2026-04-30T00:00:00+00:00",
            contact_form_url="https://ramen-test.jp/contact",
            contact_forms=[
                DiscoveredContactForm(
                    url="https://ramen-test.jp/contact",
                    form_type="official",
                    confidence=0.6,
                    source_url="https://ramen-test.jp/",
                ),
            ],
            all_emails=[
                DiscoveredEmail(
                    email="info@ramen-test.jp",
                    email_type=EmailType.GENERAL_BUSINESS,
                    source_url="https://ramen-test.jp/contact",
                    confidence=0.9,
                ),
                DiscoveredEmail(
                    email="recruit@ramen-test.jp",
                    email_type=EmailType.RECRUITMENT,
                    source_url="https://ramen-test.jp/recruit",
                    confidence=0.9,
                ),
                DiscoveredEmail(
                    email="owner@gmail.com",
                    email_type=EmailType.PERSONAL_OR_UNCLEAR,
                    source_url="https://ramen-test.jp/contact",
                    confidence=0.9,
                ),
            ],
        )

        contacts = enriched_to_contact_records(enriched)

        assert [contact["type"] for contact in contacts] == ["email", "contact_form"]
        assert contacts[0]["value"] == "info@ramen-test.jp"
        assert contacts[0]["actionable"] is True
        assert contacts[1]["actionable"] is True

    def test_enrich_lead_merges_contacts_and_metadata(self, monkeypatch):
        from pipeline.email_discovery import bridge
        from pipeline.email_discovery.config import DiscoveryConfig
        from pipeline.email_discovery.models import DiscoveredEmail, EmailType, EnrichedLead

        def fake_process_lead(input_lead, config):
            assert input_lead.shop_name == "麺屋テスト"
            return EnrichedLead(
                crawl_timestamp="2026-04-30T00:00:00+00:00",
                best_email="info@ramen-test.jp",
                best_email_type=EmailType.GENERAL_BUSINESS.value,
                confidence_score=84.0,
                reason_codes=["OFFICIAL_EMAIL_FOUND"],
                tokushoho_page_url="https://ramen-test.jp/legal",
                operator_company_name="株式会社テスト",
                all_emails=[
                    DiscoveredEmail(
                        email="info@ramen-test.jp",
                        email_type=EmailType.GENERAL_BUSINESS,
                        source_url="https://ramen-test.jp/contact",
                        confidence=0.9,
                    ),
                    DiscoveredEmail(
                        email="info@ramen-test.jp",
                        email_type=EmailType.GENERAL_BUSINESS,
                        source_url="https://ramen-test.jp/contact",
                        confidence=0.9,
                    ),
                ],
            )

        monkeypatch.setattr(bridge, "process_lead", fake_process_lead)

        updated = bridge.enrich_lead(
            {
                "lead_id": "wrm-test",
                "business_name": "麺屋テスト",
                "primary_category_v1": "ramen",
                "address": "東京都渋谷区神南1-2-3",
                "website": "https://ramen-test.jp",
                "contacts": [],
                "email": "",
            },
            config=DiscoveryConfig(dry_run=True),
        )

        email_contacts = [contact for contact in updated["contacts"] if contact["type"] == "email"]
        assert len(email_contacts) == 1
        assert updated["email"] == "info@ramen-test.jp"
        assert updated["primary_contact"]["type"] == "email"
        assert updated["has_supported_contact_route"] is True
        assert updated["email_discovery_score"] == 84.0
        assert updated["email_discovery_tokushoho_url"] == "https://ramen-test.jp/legal"
        assert updated["email_discovery_operator_company"] == "株式会社テスト"

    def test_inline_enrichment_extracts_obfuscated_email_from_current_html(self):
        from pipeline.email_discovery.bridge import enrich_lead_inline
        from pipeline.email_discovery.config import DiscoveryConfig

        html = """
        <html><head><title>お問い合わせ</title></head><body>
        メール：info＠ramen-test.jp
        </body></html>
        """

        contacts = enrich_lead_inline(
            business_name="麺屋テスト",
            website="https://ramen-test.jp/contact",
            html=html,
            address="東京都渋谷区神南1-2-3",
            genre="ramen",
            config=DiscoveryConfig(dry_run=True),
        )

        assert len(contacts) == 1
        assert contacts[0]["type"] == "email"
        assert contacts[0]["value"] == "info@ramen-test.jp"

    def test_cli_enrich_dry_run_smoke(self, tmp_path):
        state_leads = tmp_path / "leads"
        state_leads.mkdir(parents=True)
        (state_leads / "wrm-test.json").write_text(json.dumps({
            "lead_id": "wrm-test",
            "business_name": "麺屋テスト",
            "primary_category_v1": "ramen",
            "address": "東京都渋谷区神南1-2-3",
            "website": "https://ramen-test.jp",
            "contacts": [],
            "email": "",
            "lead_score_v1": 10,
        }, ensure_ascii=False), encoding="utf-8")
        config_path = tmp_path / "email_discovery.yaml"
        config_path.write_text("dry_run: true\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pipeline.cli",
                "enrich",
                "--all",
                "--dry-run",
                "--no-contact",
                "--config",
                str(config_path),
                "--state-root",
                str(tmp_path),
            ],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
            check=True,
        )
        summary = json.loads(result.stdout)

        assert summary["selected"] == 1
        assert summary["enriched"] == 1
        assert summary["dry_run"] is True
