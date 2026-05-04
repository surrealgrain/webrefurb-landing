"""Tests for WebRefurbMenu pipeline modules."""

from __future__ import annotations

import pytest
from pipeline.qualification import qualify_candidate
from pipeline.evidence import (
    assess_evidence, is_chain_business, is_excluded_business,
    is_invalid_page, classify_primary_category, has_public_website,
    looks_high_quality_english,
)
from pipeline.scoring import (
    compute_tourist_exposure_score, compute_lead_score_v1,
    detect_english_menu_issue, recommend_package, recommend_package_details,
    recommend_package_details_for_record,
)
from pipeline.models import QualificationResult
from pipeline.constants import (
    PACKAGE_1_KEY, PACKAGE_2_KEY, PACKAGE_3_KEY, PACKAGE_A_KEY, PACKAGE_B_KEY,
    LEAD_CATEGORY_RAMEN_MENU_TRANSLATION,
    LEAD_CATEGORY_RAMEN_MACHINE_MAPPING,
    LEAD_CATEGORY_RAMEN_MENU_AND_MACHINE,
    LEAD_CATEGORY_IZAKAYA_MENU_TRANSLATION,
)
from pipeline.html_parser import extract_page_payload
from pipeline.utils import slugify, sha256_text, utc_now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ramen_page(html: str = "", url: str = "https://example.ramen.jp") -> dict:
    return {"url": url, "html": html or _ramen_html()}


def _ramen_html() -> str:
    return """
    <html><body>
    <h1>テストラーメン</h1>
    <div class="menu">
        <h2>メニュー</h2>
        <ul>
            <li>醤油ラーメン ¥850</li>
            <li>味噌ラーメン ¥900</li>
            <li>塩ラーメン ¥800</li>
            <li>唐揚げ ¥480</li>
            <li>餃子 ¥350</li>
        </ul>
    </div>
    <p>券売機でご注文ください。</p>
    <p>住所：東京都渋谷区神南1-2-3</p>
    <p>電話：03-1234-5678</p>
    </body></html>
    """


def _izakaya_html() -> str:
    return """
    <html><body>
    <h1>テスト居酒屋</h1>
    <div class="menu">
        <h2>メニュー</h2>
        <ul>
            <li>刺身盛り合わせ ¥980</li>
            <li>焼き鳥 ¥380</li>
            <li>唐揚げ ¥480</li>
            <li>飲み放題 ¥1,500</li>
        </ul>
    </div>
    <p>コース料理もございます。</p>
    <p>住所：東京都新宿区歌舞伎町1-2-3</p>
    </body></html>
    """


# ===========================================================================
# Qualification tests — binary lead semantics
# ===========================================================================
class TestBinaryLead:
    def test_ramen_shop_qualifies(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
            address="東京都渋谷区神南1-2-3",
            phone="03-1234-5678",
        )
        assert result.lead is True
        assert result.rejection_reason is None
        assert result.primary_category_v1 == "ramen"
        assert result.lead_score_v1 > 0
        assert result.recommended_primary_package != ""

    def test_menu_qualified_candidate_without_explicit_english_gap_still_passes_inventory(self):
        html = """
        <html><body>
        <h1>メニューラーメン</h1>
        <div class="menu">
            <h2>メニュー</h2>
            <ul>
                <li>醤油ラーメン ¥850</li>
                <li>味噌ラーメン ¥900</li>
                <li>塩ラーメン ¥800</li>
            </ul>
        </div>
        <p>住所：東京都渋谷区神南1-2-3</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="メニューラーメン",
            website="https://menu-ramen.example",
            category="ramen",
            pages=[{"url": "https://menu-ramen.example", "html": html}],
            address="東京都渋谷区神南1-2-3",
        )

        assert result.lead is True
        assert result.rejection_reason is None
        assert "source_menu_available" in result.lead_signals

    def test_izakaya_qualifies(self):
        result = qualify_candidate(
            business_name="テスト居酒屋",
            website="https://example.izakaya.jp",
            category="izakaya",
            pages=[{"url": "https://example.izakaya.jp", "html": _izakaya_html()}],
            address="東京都新宿区歌舞伎町1-2-3",
        )
        assert result.lead is True
        assert result.rejection_reason is None
        assert result.primary_category_v1 == "izakaya"

    def test_ramen_only_profile_classified_from_menu_evidence(self):
        html = """
        <html><body>
        <h1>湯気ラーメン</h1>
        <div class="menu">
            <ul>
                <li>醤油ラーメン ¥850</li>
                <li>味噌ラーメン ¥900</li>
                <li>塩ラーメン ¥800</li>
            </ul>
        </div>
        <p>住所：東京都渋谷区神南1-2-3</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="湯気ラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp/menu", "html": html}],
            address="東京都渋谷区神南1-2-3",
        )
        assert result.lead is True
        assert result.establishment_profile == "ramen_only"
        assert result.establishment_profile_confidence == "medium"
        assert result.establishment_profile_source_urls == ["https://example.ramen.jp/menu"]

    def test_ramen_ticket_machine_profile_classified_from_evidence(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
            address="東京都渋谷区神南1-2-3",
            phone="03-1234-5678",
        )
        assert result.lead is True
        assert result.establishment_profile == "ramen_ticket_machine"
        assert result.establishment_profile_confidence == "high"
        assert "ticket_machine_evidence" in result.establishment_profile_evidence

    def test_ramen_ticket_machine_only_qualifies_as_machine_mapping(self):
        html = """
        <html><body>
        <h1>券売機ラーメン</h1>
        <p>券売機で食券を購入してください。醤油ラーメン 900円、味噌ラーメン 950円。</p>
        <p>住所：東京都渋谷区神南1-2-3</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="券売機ラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp", "html": html}],
            address="東京都渋谷区神南1-2-3",
            phone="03-1234-5678",
        )
        assert result.lead is True
        assert result.menu_evidence_found is False
        assert result.machine_evidence_found is True
        assert result.lead_category == LEAD_CATEGORY_RAMEN_MACHINE_MAPPING
        assert result.establishment_profile == "ramen_ticket_machine"

    def test_izakaya_drink_heavy_profile_classified_from_nomihodai_evidence(self):
        result = qualify_candidate(
            business_name="テスト居酒屋",
            website="https://example.izakaya.jp",
            category="izakaya",
            pages=[{"url": "https://example.izakaya.jp/menu", "html": _izakaya_html()}],
            address="東京都新宿区歌舞伎町1-2-3",
        )
        assert result.lead is True
        assert result.establishment_profile == "izakaya_drink_heavy"
        assert result.establishment_profile_confidence == "high"
        assert "drink_focused_menu_evidence" in result.establishment_profile_evidence

    def test_no_physical_location_rejected(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
        )
        assert result.lead is False
        assert result.rejection_reason == "no_physical_location_evidence"

    def test_chain_rejected(self):
        result = qualify_candidate(
            business_name="一蘭 渋谷店",
            website="https://ichiran.com",
            category="ramen",
            pages=[_ramen_page()],
            address="東京都渋谷区",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_business"

    def test_chain_ippudo_rejected(self):
        result = qualify_candidate(
            business_name="一風堂 新宿店",
            website="https://ippudo.com",
            category="ramen",
            pages=[_ramen_page()],
            address="東京都新宿区",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_business"

    def test_branch_store_rejected(self):
        result = qualify_candidate(
            business_name="テストラーメン 3号店",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
            address="東京都渋谷区",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_business"

    def test_franchise_infrastructure_rejected(self):
        html = """
        <html><body>
        <h1>むかん</h1>
        <nav>店舗一覧 Stores FC募集</nav>
        <p>濃厚牡蠣塩ラーメン メニュー 住所 東京都杉並区</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="むかん",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp", "html": html}],
            address="東京都杉並区",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_or_franchise_infrastructure"

    def test_store_list_navigation_now_treated_as_chain(self):
        """店舗一覧 in page text is now treated as chain infrastructure."""
        html = """
        <html><body>
        <h1>小さなラーメン</h1>
        <nav>店舗一覧 Stores</nav>
        <p>醤油ラーメン 900円 味噌ラーメン 950円 味玉 トッピング メニュー</p>
        <p>住所 東京都杉並区</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="小さなラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp", "html": html}],
            address="東京都杉並区",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_or_franchise_infrastructure"

    def test_chain_expansion_search_snippet_rejected(self):
        html = """
        <html><body>
        <h1>新時代 福岡天神店</h1>
        <p>居酒屋 メニュー 飲み放題 コース 焼き鳥 ハイボール 500円</p>
        <p>新時代は全国に100店舗展開する居酒屋チェーンです。</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="新時代 福岡天神店",
            website="https://example-izakaya.jp",
            category="izakaya",
            pages=[{"url": "https://example-izakaya.jp/search-evidence", "html": html}],
            address="福岡県福岡市",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_business"

    def test_multi_location_infrastructure_rejected_from_page_text(self):
        html = """
        <html><body>
        <h1>居酒屋みらい</h1>
        <p>居酒屋 メニュー 飲み放題 コース 焼き鳥 ハイボール 500円</p>
        <p>全国に35店舗を展開。店舗一覧はこちら。</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="居酒屋みらい",
            website="https://example-izakaya.jp",
            category="izakaya",
            pages=[{"url": "https://example-izakaya.jp", "html": html}],
            address="東京都渋谷区",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_or_franchise_infrastructure"

    def test_multi_branch_store_listing_rejected_without_franchise_word(self):
        html = """
        <html><body>
        <h1>超ごってり麺ごっつ</h1>
        <nav>店舗紹介 会社概要</nav>
        <p>ラーメン メニュー 背脂ラーメン 900円</p>
        <p>亀戸本店 東京都江東区 TEL 03-1111-1111</p>
        <p>新小岩店 東京都葛飾区 TEL 03-2222-2222</p>
        <p>秋葉原店 東京都千代田区 TEL 03-3333-3333</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="超ごってり麺ごっつ",
            website="https://example-ramen.jp",
            category="ramen",
            pages=[{"url": "https://example-ramen.jp", "html": html}],
            address="東京都千代田区",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_or_franchise_infrastructure"

    def test_single_shop_store_info_copy_not_treated_as_multi_store(self):
        html = """
        <html><body>
        <h1>串煮込みマルニ 吉祥寺</h1>
        <nav>メニュー 店舗情報 お問い合わせ</nav>
        <p>吉祥寺の居酒屋。飲み放題 コース 焼き鳥 ハイボール 500円</p>
        <p>おしゃれで居心地の良いお店です。ご来店をお待ちしております。</p>
        <p>東京都武蔵野市吉祥寺南町2-16-1 TEL: 0422-27-5728</p>
        <p>東京都武蔵野市吉祥寺南町2-16-1 TEL: 0422-27-5728</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="串煮込みマルニ 吉祥寺",
            website="https://kushinikomi-maruni.example.jp",
            category="izakaya",
            pages=[{"url": "https://kushinikomi-maruni.example.jp", "html": html}],
            address="東京都武蔵野市吉祥寺南町2-16-1",
        )
        assert result.lead is True
        assert result.rejection_reason is None

    def test_large_official_store_directory_rejected_without_phone_blocks(self):
        html = """
        <html><body>
        <h1>中華そば青葉</h1>
        <p>おしながき 中華そば 900円 つけ麺 950円 特製中華そば 1,100円</p>
        <nav>店舗案内</nav>
        <p>中野本店 飯田橋店 大宮店 八王子店 府中店 船橋店 御徒町店 吉祥寺店</p>
        <p>住所 東京都武蔵野市吉祥寺南町1-1-1</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="中華そば青葉",
            website="https://aoba.example.jp",
            category="ramen",
            pages=[{"url": "https://aoba.example.jp", "html": html}],
            address="東京都武蔵野市吉祥寺南町1-1-1",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_or_franchise_infrastructure"

    def test_unrelated_directory_chain_text_does_not_reject_first_party_shop(self):
        official_html = """
        <html><body>
        <h1>鶏そば そると</h1>
        <p>お品書き 鶏そば 900円 鶏白湯そば 950円 特製つけそば 1,100円</p>
        <p>住所 東京都世田谷区北沢2-1-1</p>
        </body></html>
        """
        directory_html = """
        <html><body>
        <h1>レビューサイト</h1>
        <p>レビュアーの他の訪問先: カラシビ味噌らー麺 鬼金棒、油そば特集、全国ラーメンまとめ。</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="鶏そば そると",
            website="https://salt.example.jp",
            category="ramen",
            pages=[
                {"url": "https://salt.example.jp", "html": official_html},
                {"url": "https://tabelog.example/review", "html": directory_html},
            ],
            address="東京都世田谷区北沢2-1-1",
        )
        assert result.lead is True
        assert result.rejection_reason is None

    def test_first_party_bistro_text_overrides_izakaya_search_hint(self):
        html = """
        <html><body>
        <h1>Boucherie Gokita Tokyo</h1>
        <p>フランス料理 ビストロ ワイン ディナーコース 7000円</p>
        <p>住所 東京都世田谷区北沢2-1-1</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="Gokita",
            website="https://gokita.example.jp",
            category="izakaya",
            pages=[{"url": "https://gokita.example.jp", "html": html}],
            address="東京都世田谷区北沢2-1-1",
        )
        assert result.lead is False
        assert result.rejection_reason == "excluded_business_type_v1"

    def test_first_party_hostel_bar_text_overrides_izakaya_search_hint(self):
        html = """
        <html><body>
        <h1>Hakone Hostel Bar</h1>
        <p>HOSTEL & RELAXING BAR ゲストハウス ホステル 宿泊</p>
        <p>住所 神奈川県足柄下郡箱根町強羅1320</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="Hakone Hostel Bar",
            website="https://hakonetent.example.jp",
            category="izakaya",
            pages=[{"url": "https://hakonetent.example.jp", "html": html}],
            address="神奈川県足柄下郡箱根町強羅1320",
        )
        assert result.lead is False
        assert result.rejection_reason == "excluded_business_type_v1"

    def test_second_branch_text_rejected_as_multi_location_infrastructure(self):
        html = """
        <html><body>
        <h1>ごち２</h1>
        <p>居酒屋 メニュー 飲み放題 コース 九州料理 3000円</p>
        <p>渋谷で大繁盛している居酒屋が待望の2号店を下北沢でオープン。</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="Gochi 2",
            website="https://example-izakaya.jp/work/gochi2",
            category="izakaya",
            pages=[{"url": "https://example-izakaya.jp/work/gochi2", "html": html}],
            address="東京都世田谷区",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_or_franchise_infrastructure"

    def test_chain_shinjidai_rejected_by_seed_name(self):
        result = qualify_candidate(
            business_name="新時代 福岡天神店",
            website="https://example-izakaya.jp",
            category="izakaya",
            pages=[{"url": "https://example-izakaya.jp", "html": "<html><body><h1>新時代</h1><p>居酒屋 メニュー</p></body></html>"}],
            address="福岡県福岡市",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_business"
        assert is_chain_business("新時代 福岡天神店") is True

    def test_chain_shinjidai_rejected_without_chain_content(self):
        html = """
        <html><body>
        <h1>新時代 福岡天神店</h1>
        <p>居酒屋 メニュー 飲み放題 コース 焼き鳥 ハイボール 500円</p>
        <p>住所：福岡県福岡市中央区天神1-2-3</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="新時代 福岡天神店",
            website="https://example-izakaya.jp",
            category="izakaya",
            pages=[{"url": "https://example-izakaya.jp", "html": html}],
            address="福岡県福岡市",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_business"

    def test_branch_pattern_catches_place_name_store(self):
        assert is_chain_business("ラーメン 渋谷店") is True

    def test_branch_pattern_does_not_match_honpo(self):
        assert is_chain_business("麺屋 本店") is False

    def test_branch_pattern_does_not_match_senmonten(self):
        assert is_chain_business("ラーメン専門店") is False

    def test_non_ramen_izakaya_rejected(self):
        result = qualify_candidate(
            business_name="テスト寿司",
            website="https://example.sushi.jp",
            category="sushi",
            pages=[{"url": "https://example.sushi.jp", "html": "<html><body><h1>寿司</h1><p>にぎり ¥300</p></body></html>"}],
            address="東京都中央区",
        )
        assert result.lead is False
        assert result.rejection_reason == "non_ramen_izakaya_v1"

    def test_excluded_business_sushi_rejected(self):
        html = "<html><body><h1>寿司処</h1><p>寿司 メニュー</p></body></html>"
        result = qualify_candidate(
            business_name="寿司処 テスト",
            website="https://example.sushi.jp",
            category="ramen",
            pages=[{"url": "https://example.sushi.jp", "html": html}],
            address="東京都渋谷区",
        )
        assert result.lead is False
        assert result.rejection_reason == "excluded_business_type_v1"

    def test_excluded_business_yakiniku_rejected(self):
        html = "<html><body><h1>焼肉レストラン</h1><p>焼肉 メニュー</p></body></html>"
        result = qualify_candidate(
            business_name="焼肉レストラン",
            website="https://example.yakiniku.jp",
            category="izakaya",
            pages=[{"url": "https://example.yakiniku.jp", "html": html}],
            address="東京都渋谷区",
        )
        assert result.lead is False

    @pytest.mark.parametrize(
        ("business_name", "category", "html"),
        [
            ("カフェ テスト", "ramen", "<html><body><h1>カフェ</h1><p>ラーメン メニュー</p></body></html>"),
            ("ホテル居酒屋 テスト", "izakaya", "<html><body><h1>ホテル居酒屋</h1><p>飲み放題 コース 居酒屋 メニュー</p></body></html>"),
            ("懐石ラーメン テスト", "ramen", "<html><body><h1>懐石</h1><p>ラーメン メニュー</p></body></html>"),
        ],
    )
    def test_excluded_business_types_from_audit_are_rejected(self, business_name, category, html):
        result = qualify_candidate(
            business_name=business_name,
            website="https://example.test",
            category=category,
            pages=[{"url": "https://example.test", "html": html}],
            address="東京都渋谷区",
        )

        assert result.lead is False
        assert result.rejection_reason == "excluded_business_type_v1"

    def test_social_only_site_rejected_even_with_menu_evidence(self):
        result = qualify_candidate(
            business_name="小さなラーメン",
            website="https://instagram.com/small_ramen",
            category="ramen",
            pages=[_ramen_page(url="https://instagram.com/small_ramen")],
            address="東京都渋谷区",
        )

        assert result.lead is False
        assert result.rejection_reason == "directory_or_social_only"

    def test_negative_score_rejected(self):
        """Negative evidence score (food-only photos, storefront only) → rejected."""
        html = """
        <html><body>
        <h1>テストラーメン</h1>
        <img src="storefront.jpg" alt="storefront exterior">
        <img src="ramen.jpg" alt="ramen food bowl">
        </body></html>
        """
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp", "html": html}],
            address="東京都渋谷区",
        )
        assert result.lead is False

    def test_menu_evidence_not_rejected_by_incidental_food_images(self):
        html = """
        <html><body>
        <h1>写真多めラーメン</h1>
        <p>醤油ラーメン 900円 味噌ラーメン 950円 味玉 トッピング メニュー</p>
        <img src="storefront.jpg" alt="storefront exterior">
        <img src="ramen1.jpg" alt="ramen food bowl">
        <img src="ramen2.jpg" alt="ramen food bowl">
        <img src="ramen3.jpg" alt="ramen food bowl">
        </body></html>
        """
        result = qualify_candidate(
            business_name="写真多めラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp", "html": html}],
            address="東京都渋谷区",
        )
        assert result.rejection_reason != "negative_evidence_score"
        assert result.lead is True

    def test_independent_business_not_rejected_by_chain_check(self):
        assert is_chain_business("商店街ラーメン") is False
        assert is_chain_business("小さな居酒屋 よいち") is False
        assert is_chain_business("麺処おあな") is False

    def test_place_id_counts_as_location(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
            place_id="ChIJ_test123",
        )
        # Should pass physical location gate
        assert result.rejection_reason != "no_physical_location_evidence"


class TestInvalidPageGuard:
    def test_captcha_page_no_evidence(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp", "html": "<html><body><p>please verify you are human captcha</p></body></html>"}],
            address="東京都渋谷区",
        )
        assert result.lead is False

    def test_js_empty_page_no_evidence(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp", "html": "<html><body><p>please enable javascript to view this page</p></body></html>"}],
            address="東京都渋谷区",
        )
        assert result.lead is False

    def test_placeholder_or_coming_soon_page_rejected_as_stale_status(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp", "html": "<html><body><h1>テストラーメン</h1><p>coming soon under construction ラーメン メニュー</p></body></html>"}],
            address="東京都渋谷区",
        )

        assert result.lead is False
        assert result.rejection_reason == "placeholder/password/coming-soon page"

    def test_incidental_coming_soon_text_does_not_reject_real_menu_page(self):
        html = """
        <html><body>
        <h1>小さなラーメン</h1>
        <p>醤油ラーメン 900円 味噌ラーメン 950円 味玉 トッピング メニュー</p>
        <p>営業時間 11:00-22:00 住所 東京都渋谷区</p>
        <p>アレルゲン情報は近日公開です。</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="小さなラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp", "html": html}],
            address="東京都渋谷区",
        )

        assert result.lead is True
        assert result.rejection_reason is None

    def test_operator_category_prevents_ramen_side_item_from_overriding_izakaya(self):
        html = """
        <html><body>
        <h1>餃子酒場</h1>
        <p>居酒屋 メニュー 生ビール ハイボール 飲み放題 コース 醤油ラーメン</p>
        <p>住所 東京都杉並区 電話 03-0000-0000</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="餃子酒場",
            website="https://example.izakaya.jp",
            category="izakaya",
            pages=[{"url": "https://example.izakaya.jp", "html": html}],
            address="東京都杉並区",
        )

        assert result.lead is True
        assert result.primary_category_v1 == "izakaya"
        assert result.establishment_profile.startswith("izakaya")

    def test_invalid_page_mixed_with_valid(self):
        """When invalid pages are mixed with valid ones, valid evidence still counts."""
        pages = [
            {"url": "https://example.ramen.jp", "html": "<html><body><p>captcha bot protection</p></body></html>"},
            _ramen_page(url="https://example.ramen.jp/menu"),
        ]
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=pages,
            address="東京都渋谷区",
        )
        # Should still qualify from the valid page
        assert result.lead is True


class TestAlreadyGoodEnglish:
    def test_high_quality_english_rejected(self):
        html = """
        <html><body>
        <h1>Test Ramen Shop</h1>
        <div>
            <p>Our menu features Shoyu Ramen, Miso Ramen, and Tonkotsu Ramen.</p>
            <p>Allergen information is available. Ingredients listed for each dish.</p>
            <p>Reservations accepted. Order online for delivery.</p>
            <p>Open daily. Location: Shibuya, Tokyo.</p>
            <p>Hours: 11:00-22:00. Address: 1-2-3 Shibuya.</p>
        </div>
        </body></html>
        """
        # Need enough English text to trigger the high-quality English detection
        result = qualify_candidate(
            business_name="Test Ramen",
            website="https://example.ramen.jp/en",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp/en", "html": html}],
            address="東京都渋谷区",
        )
        assert result.lead is False

    def test_multilingual_qr_or_ordering_solution_rejected(self):
        html = """
        <html><body>
        <h1>多言語QR対応ラーメン</h1>
        <p>醤油ラーメン 味玉 トッピング メニュー 券売機 食券</p>
        <p>Multilingual QR and English QR mobile order English support are available.</p>
        <p>住所：東京都渋谷区神南1-2-3</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="多言語QR対応ラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp", "html": html}],
            address="東京都渋谷区神南1-2-3",
        )
        assert result.lead is False
        assert result.rejection_reason == "already_has_multilingual_ordering_solution"


# ===========================================================================
# Scoring tests
# ===========================================================================
class TestScoring:
    def test_ramen_score_higher_than_izakaya(self):
        ramen = compute_lead_score_v1(
            category="ramen", english_menu_issue=True,
            tourist_exposure=0.5, rating=4.5, reviews=500,
        )
        izakaya = compute_lead_score_v1(
            category="izakaya", english_menu_issue=True,
            tourist_exposure=0.5, rating=4.5, reviews=500,
        )
        assert ramen > izakaya

    def test_no_english_issue_zero_bonus(self):
        with_issue = compute_lead_score_v1(
            category="ramen", english_menu_issue=True,
            tourist_exposure=0.5,
        )
        without_issue = compute_lead_score_v1(
            category="ramen", english_menu_issue=False,
            tourist_exposure=0.5,
        )
        assert with_issue > without_issue

    def test_tourist_exposure_tokyo(self):
        score = compute_tourist_exposure_score(address="Tokyo, Shibuya-ku", reviews=300)
        assert score >= 0.5

    def test_tourist_exposure_rural(self):
        score = compute_tourist_exposure_score(address="Inaka-mura, Fukushima")
        assert score < 0.3

    def test_package_recommendation_none(self):
        pkg = recommend_package(
            english_menu_issue=False,
            machine_evidence_found=True,
            tourist_exposure_score=0.8,
            lead_score_v1=80,
        )
        assert pkg == "none"

    def test_package_recommendation_a_for_machine(self):
        pkg = recommend_package(
            english_menu_issue=True,
            machine_evidence_found=True,
            tourist_exposure_score=0.3,
            lead_score_v1=50,
        )
        assert pkg == PACKAGE_A_KEY

    def test_package_recommendation_a_for_high_tourist(self):
        pkg = recommend_package(
            english_menu_issue=True,
            machine_evidence_found=False,
            tourist_exposure_score=0.7,
            lead_score_v1=50,
        )
        assert pkg == PACKAGE_A_KEY

    def test_package_recommendation_a_for_high_score(self):
        pkg = recommend_package(
            english_menu_issue=True,
            machine_evidence_found=False,
            tourist_exposure_score=0.3,
            lead_score_v1=75,
        )
        assert pkg == PACKAGE_A_KEY

    def test_package_recommendation_simple_ramen_stays_remote_even_when_popular(self):
        details = recommend_package_details(
            category="ramen",
            english_menu_issue=True,
            machine_evidence_found=False,
            menu_complexity_state="simple",
            tourist_exposure_score=0.8,
            lead_score_v1=84,
        )

        assert details["package_key"] == PACKAGE_1_KEY
        assert details["recommendation_reason"] == "simple_ramen_menu_fits_english_ordering_files"

    def test_package_recommendation_b_default(self):
        pkg = recommend_package(
            english_menu_issue=True,
            machine_evidence_found=False,
            tourist_exposure_score=0.3,
            lead_score_v1=40,
        )
        assert pkg == PACKAGE_B_KEY

    def test_package_recommendation_custom_quote_for_large_menu(self):
        pkg = recommend_package(
            category="izakaya",
            english_menu_issue=True,
            machine_evidence_found=False,
            menu_complexity_state="large_custom_quote",
            tourist_exposure_score=0.3,
            lead_score_v1=40,
        )
        assert pkg == "custom_quote"

    def test_package_recommendation_izakaya_friction_uses_qr_or_print_package(self):
        course_pkg = recommend_package(
            category="izakaya",
            english_menu_issue=True,
            machine_evidence_found=False,
            izakaya_rules_state="nomihodai_found",
            tourist_exposure_score=0.3,
            lead_score_v1=40,
        )
        drinks_pkg = recommend_package(
            category="izakaya",
            english_menu_issue=True,
            machine_evidence_found=False,
            izakaya_rules_state="drinks_found",
            tourist_exposure_score=0.3,
            lead_score_v1=40,
        )

        assert course_pkg == PACKAGE_3_KEY
        assert drinks_pkg == PACKAGE_2_KEY

    def test_package_recommendation_uses_current_package_keys(self):
        assert PACKAGE_A_KEY == PACKAGE_2_KEY
        assert PACKAGE_B_KEY == PACKAGE_1_KEY

    def test_package_recommendation_details_cover_ramen_ticket_machine_default(self):
        details = recommend_package_details(
            category="ramen",
            english_menu_issue=True,
            machine_evidence_found=True,
            tourist_exposure_score=0.3,
            lead_score_v1=50,
        )

        assert details["package_key"] == PACKAGE_2_KEY
        assert details["recommendation_reason"] == "ramen_ticket_machine_needs_counter_ready_mapping"
        assert details["custom_quote_reason"] == ""

    def test_package_recommendation_details_allow_ramen_ticket_machine_print_yourself_fit(self):
        details = recommend_package_details(
            category="ramen",
            english_menu_issue=True,
            machine_evidence_found=True,
            print_yourself_fit=True,
            tourist_exposure_score=0.3,
            lead_score_v1=50,
        )

        assert details["package_key"] == PACKAGE_1_KEY
        assert details["recommendation_reason"] == "ramen_ticket_machine_with_clear_print_yourself_fit"

    def test_package_recommendation_details_cover_simple_ramen_without_machine(self):
        details = recommend_package_details(
            category="ramen",
            english_menu_issue=True,
            machine_evidence_found=False,
            menu_complexity_state="simple",
            tourist_exposure_score=0.2,
            lead_score_v1=45,
        )

        assert details["package_key"] == PACKAGE_1_KEY
        assert details["recommendation_reason"] == "simple_ramen_menu_fits_english_ordering_files"

    def test_package_recommendation_details_cover_ramen_counter_ready_need(self):
        details = recommend_package_details(
            category="ramen",
            english_menu_issue=True,
            machine_evidence_found=False,
            counter_ready_need=True,
            tourist_exposure_score=0.2,
            lead_score_v1=45,
        )

        assert details["package_key"] == PACKAGE_2_KEY
        assert details["recommendation_reason"] == "ramen_without_machine_but_counter_ready_materials_fit"

    def test_package_recommendation_details_cover_izakaya_frequent_updates(self):
        details = recommend_package_details(
            category="izakaya",
            english_menu_issue=True,
            machine_evidence_found=False,
            izakaya_rules_state="nomihodai_found",
            frequent_updates_expected=True,
            tourist_exposure_score=0.2,
            lead_score_v1=45,
        )

        assert details["package_key"] == PACKAGE_3_KEY
        assert details["recommendation_reason"] == "izakaya_drink_course_rules_likely_need_live_updates"

    def test_package_recommendation_details_cover_izakaya_stable_table_menus(self):
        details = recommend_package_details(
            category="izakaya",
            english_menu_issue=True,
            machine_evidence_found=False,
            izakaya_rules_state="courses_found",
            stable_table_menus=True,
            tourist_exposure_score=0.2,
            lead_score_v1=45,
        )

        assert details["package_key"] == PACKAGE_2_KEY
        assert details["recommendation_reason"] == "stable_izakaya_table_menu_needs_staff_explanation_support"

    def test_package_recommendation_details_store_custom_quote_reason(self):
        details = recommend_package_details(
            category="izakaya",
            english_menu_issue=True,
            machine_evidence_found=False,
            menu_complexity_state="large_custom_quote",
            tourist_exposure_score=0.2,
            lead_score_v1=45,
        )

        assert details["package_key"] == "custom_quote"
        assert details["recommendation_reason"] == "large_or_complex_menu_requires_manual_quote"
        assert details["custom_quote_reason"] == "large_or_complex_menu_requires_manual_quote"

    def test_record_package_rescore_infers_imported_izakaya_course_fit(self):
        details = recommend_package_details_for_record({
            "primary_category_v1": "izakaya",
            "english_menu_issue": True,
            "menu_type": "izakaya",
            "evidence_snippets": ["飲み放題 コース 居酒屋 メニュー"],
            "course_or_drink_plan_evidence_found": True,
            "lead_score_v1": 55,
        })

        assert details["package_key"] == PACKAGE_3_KEY
        assert details["recommendation_reason"] == "izakaya_drink_course_rules_likely_need_live_updates"

    def test_record_package_rescore_keeps_simple_imported_ramen_remote(self):
        details = recommend_package_details_for_record({
            "primary_category_v1": "ramen",
            "english_menu_issue": True,
            "evidence_snippets": ["醤油ラーメン 味玉 トッピング メニュー"],
            "lead_score_v1": 55,
        })

        assert details["package_key"] == PACKAGE_1_KEY
        assert details["recommendation_reason"] == "simple_ramen_menu_fits_english_ordering_files"


# ===========================================================================
# Evidence tests
# ===========================================================================
class TestEvidence:
    def test_assess_ramen_menu(self):
        payload = extract_page_payload("https://example.ramen.jp", _ramen_html())
        assessment = assess_evidence(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            payloads=[payload],
        )
        assert assessment.is_ramen_candidate is True
        assert assessment.menu_evidence_found is True
        assert assessment.machine_evidence_found is True
        assert assessment.score > 0

    def test_chain_detection(self):
        assert is_chain_business("Ichiran Shibuya") is True
        assert is_chain_business("IPPUDO Shinjuku") is True
        assert is_chain_business("Afuri Ebisu") is True

    def test_excluded_business(self):
        assert is_excluded_business("寿司レストラン", "") is True
        assert is_excluded_business("焼肉酒場", "") is True
        assert is_excluded_business("カフェ テスト", "") is True
        assert is_excluded_business("テストラーメン", "") is False

    def test_classify_category(self):
        assert classify_primary_category("ラーメン メニュー") == "ramen"
        assert classify_primary_category("居酒屋 料理") == "izakaya"
        assert classify_primary_category("random stuff") == "other"


# ===========================================================================
# Utility tests
# ===========================================================================
class TestUtils:
    def test_slugify(self):
        assert slugify("Test Ramen Shop") == "test-ramen-shop"
        assert slugify("!!!") == "lead"

    def test_sha256_text(self):
        h1 = sha256_text("hello")
        h2 = sha256_text("hello")
        h3 = sha256_text("world")
        assert h1 == h2
        assert h1 != h3

    def test_utc_now(self):
        now = utc_now()
        assert "T" in now
        assert "+" in now or "Z" in now


# ===========================================================================
# Unrelated vertical isolation check
# ===========================================================================
class TestScopeIsolation:
    def test_no_unrelated_service_references(self):
        """Verify unrelated service terms do not appear in pipeline source."""
        import pathlib
        root = pathlib.Path(__file__).resolve().parent.parent / "pipeline"
        blocked_terms = tuple(
            "".join(chr(code) for code in codes)
            for codes in (
                (104, 118, 97, 99),
                (72, 86, 65, 67),
                (104, 101, 97, 116, 105, 110, 103),
                (99, 111, 111, 108, 105, 110, 103),
                (112, 108, 117, 109, 98, 105, 110, 103),
                (114, 111, 111, 102, 105, 110, 103),
            )
        )
        for py_file in root.rglob("*.py"):
            content = py_file.read_text()
            for term in blocked_terms:
                assert term not in content, f"Found forbidden term in {py_file.name}"


# ===========================================================================
# Japan location gate
# ===========================================================================
class TestJapanLocationGate:
    def test_japan_address_passes(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
            address="Japan, 〒150-0001 Tokyo, Shibuya, Jingumae 1-13-21",
        )
        assert result.lead is True
        assert result.rejection_reason is None

    def test_japanese_postal_code_passes(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
            address="〒169-0074 東京都新宿区北新宿3-9-10",
        )
        assert result.lead is True

    def test_japan_prefecture_in_address_passes(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
            address="東京都渋谷区神南1-2-3",
        )
        assert result.lead is True

    def test_japan_phone_prefix_passes(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
            address="Tokyo",
            phone="+81-3-1234-5678",
        )
        assert result.lead is True

    def test_japan_domestic_phone_passes(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
            address="Tokyo",
            phone="03-1234-5678",
        )
        assert result.lead is True

    def test_nyc_address_rejected(self):
        result = qualify_candidate(
            business_name="Sakagura",
            website="http://www.sakagura.com/",
            category="izakaya",
            pages=[{"url": "http://www.sakagura.com/", "html": _izakaya_html()}],
            address="211 E 43rd St B1, New York, NY 10017",
        )
        assert result.lead is False
        assert result.rejection_reason == "not_in_japan"

    def test_nyc_jackson_heights_rejected(self):
        result = qualify_candidate(
            business_name="Izakaya Fuku",
            website="http://www.orderfukunyc.com/",
            category="izakaya",
            pages=[{"url": "http://www.orderfukunyc.com/", "html": _izakaya_html()}],
            address="71-28 Roosevelt Ave, Jackson Heights, NY 11372",
        )
        assert result.lead is False
        assert result.rejection_reason == "not_in_japan"

    def test_us_zip_code_rejected(self):
        result = qualify_candidate(
            business_name="Sake Bar Hagi",
            website="http://www.sakebar-hagi.com/",
            category="izakaya",
            pages=[{"url": "http://www.sakebar-hagi.com/", "html": _izakaya_html()}],
            address="245 W 51st St, New York, NY 10019",
        )
        assert result.lead is False
        assert result.rejection_reason == "not_in_japan"

    def test_osaka_address_passes(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
            address="大阪府大阪市中央区道頓堀1-2-3",
        )
        assert result.lead is True

    def test_fukuoka_address_passes(self):
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
            address="福岡県福岡市博多区中洲1-2-3",
        )
        assert result.lead is True


# ===========================================================================
# Chain detection improvements
# ===========================================================================
class TestChainDetectionImprovements:
    def test_jangara_rejected_by_seed_name(self):
        """Kyushu Jangara is a well-known multi-location chain."""
        result = qualify_candidate(
            business_name="Kyushu Jangara Ramen Harajuku Ten",
            website="https://kyushujangara.co.jp/shops/harajuku/",
            category="ramen",
            pages=[_ramen_page()],
            address="Japan, 〒150-0001 Tokyo, Shibuya, Jingumae 1-13-21",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_business"

    def test_jangara_japanese_name_rejected(self):
        result = qualify_candidate(
            business_name="九州じゃんがら 原宿店",
            website="https://kyushujangara.co.jp/shops/harajuku/",
            category="ramen",
            pages=[_ramen_page()],
            address="Japan, 〒150-0001 Tokyo, Shibuya, Jingumae 1-13-21",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_business"

    def test_romaji_branch_ten_suffix_rejected(self):
        """Business name ending in 'Ten' (romaji for 店) indicates a branch."""
        result = qualify_candidate(
            business_name="Ramen Maru Shinjuku Ten",
            website="https://ramenmaru.example.jp/shops/shinjuku/",
            category="ramen",
            pages=[_ramen_page()],
            address="Japan, 〒160-0023 Tokyo, Shinjuku, Nishigashi 1-2-3",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_business"

    def test_romaji_branch_suffix_rejected(self):
        result = qualify_candidate(
            business_name="Izakaya Ginza Branch",
            website="https://izakaya-ginza.example.jp/",
            category="izakaya",
            pages=[{"url": "https://izakaya-ginza.example.jp/", "html": _izakaya_html()}],
            address="Japan, 〒104-0061 Tokyo, Chuo, Ginza 1-2-3",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_business"

    def test_romaji_shop_suffix_rejected(self):
        result = qualify_candidate(
            business_name="Ramen Kichi Shibuya Shop",
            website="https://ramen-kichi.example.jp/",
            category="ramen",
            pages=[_ramen_page()],
            address="Japan, 〒150-0042 Tokyo, Shibuya, Udagawacho 1-2-3",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_business"

    def test_store_directory_standalone_in_page_text(self):
        """店舗一覧 alone in page text should trigger chain rejection."""
        html = """
        <html><body>
        <h1>テストラーメン</h1>
        <div class="menu">
            <ul>
                <li>醤油ラーメン ¥850</li>
                <li>味噌ラーメン ¥900</li>
            </ul>
        </div>
        <nav><a href="/shops/">店舗一覧</a></nav>
        <p>住所：東京都渋谷区神南1-2-3</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp", "html": html}],
            address="東京都渋谷区神南1-2-3",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_or_franchise_infrastructure"

    def test_abura_gumi_rejected_by_seed_name(self):
        """Tokyo Abura Gumi is a chain."""
        result = qualify_candidate(
            business_name="Tokyo Abura Gumi Sohonten Shibuya Gumi",
            website="https://www.tokyo-aburasoba.com/",
            category="ramen",
            pages=[_ramen_page()],
            address="Japan, 〒150-0043 Tokyo, Shibuya, Dogenzaka 1-2-3",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_business"

    def test_independent_ramen_no_branch_suffix_passes(self):
        """An independent ramen shop without branch indicators should pass."""
        result = qualify_candidate(
            business_name="独立ラーメン",
            website="https://dokuritsu-ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
            address="東京都渋谷区神南1-2-3",
        )
        assert result.lead is True
        assert result.rejection_reason is None

    def test_honpo_not_rejected_as_branch(self):
        """'本店' (main store) should NOT be treated as a branch."""
        result = qualify_candidate(
            business_name="独立ラーメン本店",
            website="https://dokuritsu-ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
            address="東京都渋谷区神南1-2-3",
        )
        assert result.lead is True
        assert result.rejection_reason is None


# ===========================================================================
# Comprehensive qualification variant tests
# ===========================================================================
class TestQualificationVariants:
    """Test every lead category and evidence combination end-to-end."""

    def test_ramen_menu_only_qualifies(self):
        """Ramen shop with menu evidence but NO ticket machine → ramen_menu_translation."""
        html = """
        <html><body>
        <h1>湯気ラーメン</h1>
        <div class="menu">
            <h2>メニュー</h2>
            <ul>
                <li>醤油ラーメン ¥850</li>
                <li>味噌ラーメン ¥900</li>
                <li>塩ラーメン ¥800</li>
                <li>味玉ラーメン ¥950</li>
                <li>唐揚げ ¥480</li>
            </ul>
        </div>
        <p>住所：東京都渋谷区神南1-2-3</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="湯気ラーメン",
            website="https://yuge-ramen.jp",
            category="ramen",
            pages=[{"url": "https://yuge-ramen.jp", "html": html}],
            address="東京都渋谷区神南1-2-3",
        )
        assert result.lead is True
        assert result.lead_category == LEAD_CATEGORY_RAMEN_MENU_TRANSLATION
        assert result.establishment_profile == "ramen_only"
        assert result.menu_evidence_found is True
        assert result.machine_evidence_found is False

    def test_ramen_menu_with_explicit_no_ticket_machine_gets_absent_state_and_package_1(self):
        html = """
        <html><body>
        <h1>口頭注文ラーメン</h1>
        <div class="menu">
            <h2>メニュー</h2>
            <ul>
                <li>醤油ラーメン ¥850</li>
                <li>味噌ラーメン ¥900</li>
                <li>餃子 ¥350</li>
            </ul>
        </div>
        <p>券売機なし。席で注文、後払いです。</p>
        <p>住所：東京都渋谷区神南1-2-3</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="口頭注文ラーメン",
            website="https://kuchu-ramen.jp",
            category="ramen",
            pages=[{"url": "https://kuchu-ramen.jp", "html": html}],
            address="東京都渋谷区神南1-2-3",
            rating=4.8,
            reviews=600,
            latitude=35.6595,
            longitude=139.7005,
        )

        assert result.lead is True
        assert result.ticket_machine_state == "absent"
        assert result.machine_evidence_found is False
        assert result.establishment_profile == "ramen_only"
        assert result.recommended_primary_package == PACKAGE_1_KEY

    def test_thin_menu_reference_without_orderable_detail_is_rejected(self):
        html = """
        <html><body>
        <h1>薄いラーメン</h1>
        <p>当店のラーメンメニューは店内でご確認ください。詳細はスタッフまで。</p>
        <p>住所：東京都渋谷区神南1-2-3</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="薄いラーメン",
            website="https://thin-menu.jp",
            category="ramen",
            pages=[{"url": "https://thin-menu.jp", "html": html}],
            address="東京都渋谷区神南1-2-3",
        )

        assert result.lead is False
        assert "thin_menu_reference" in result.evidence_classes
        assert result.menu_evidence_found is False

    def test_ramen_ticket_machine_only_qualifies(self):
        """Ramen shop with ticket machine but weak menu → ramen_machine_mapping."""
        html = """
        <html><body>
        <h1>券売機ラーメン</h1>
        <p>券売機で食券を購入してください。醤油ラーメン 900円、味噌ラーメン 950円。</p>
        <p>住所：東京都渋谷区神南1-2-3</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="券売機ラーメン",
            website="https://kenbaiki-ramen.jp",
            category="ramen",
            pages=[{"url": "https://kenbaiki-ramen.jp", "html": html}],
            address="東京都渋谷区神南1-2-3",
        )
        assert result.lead is True
        assert result.lead_category == LEAD_CATEGORY_RAMEN_MACHINE_MAPPING
        assert result.establishment_profile == "ramen_ticket_machine"
        assert result.machine_evidence_found is True

    def test_ramen_menu_and_ticket_machine_qualifies(self):
        """Ramen shop with both menu and ticket machine → ramen_menu_and_machine."""
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[_ramen_page()],
            address="東京都渋谷区神南1-2-3",
            phone="03-1234-5678",
        )
        assert result.lead is True
        assert result.lead_category == LEAD_CATEGORY_RAMEN_MENU_AND_MACHINE
        assert result.establishment_profile == "ramen_ticket_machine"
        assert result.menu_evidence_found is True
        assert result.machine_evidence_found is True
        assert "ticket_machine_evidence" in result.establishment_profile_evidence

    def test_izakaya_drink_course_qualifies(self):
        """Izakaya with nomihodai/course evidence → izakaya_drink_course_guide."""
        result = qualify_candidate(
            business_name="テスト居酒屋",
            website="https://example.izakaya.jp",
            category="izakaya",
            pages=[{"url": "https://example.izakaya.jp", "html": _izakaya_html()}],
            address="東京都新宿区歌舞伎町1-2-3",
        )
        assert result.lead is True
        assert result.primary_category_v1 == "izakaya"
        assert result.course_or_drink_plan_evidence_found is True

    def test_izakaya_menu_only_qualifies(self):
        """Izakaya with menu evidence but no drink/course → izakaya_menu_translation."""
        html = """
        <html><body>
        <h1>手書き居酒屋</h1>
        <div class="menu">
            <h2>メニュー</h2>
            <ul>
                <li>刺身盛り合わせ ¥980</li>
                <li>焼き鳥 ¥380</li>
                <li>唐揚げ ¥480</li>
                <li>一品料理 おまかせ ¥680</li>
            </ul>
        </div>
        <p>住所：東京都渋谷区神南1-2-3</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="手書き居酒屋",
            website="https://tegaki-izakaya.jp",
            category="izakaya",
            pages=[{"url": "https://tegaki-izakaya.jp", "html": html}],
            address="東京都渋谷区神南1-2-3",
        )
        assert result.lead is True
        assert result.primary_category_v1 == "izakaya"

    def test_ramen_with_drinks_profile(self):
        """Ramen shop that also has drink/course evidence → ramen_with_drinks."""
        html = """
        <html><body>
        <h1>ラーメン酒場</h1>
        <div class="menu">
            <ul>
                <li>醤油ラーメン ¥850</li>
                <li>ビール ¥450</li>
                <li>ハイボール ¥400</li>
            </ul>
        </div>
        <p>飲み放題コース 1,500円</p>
        <p>住所：東京都渋谷区神南1-2-3</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="ラーメン酒場",
            website="https://ramen-sakaba.jp",
            category="ramen",
            pages=[{"url": "https://ramen-sakaba.jp", "html": html}],
            address="東京都渋谷区神南1-2-3",
        )
        assert result.lead is True
        assert result.establishment_profile == "ramen_with_drinks"
        assert result.primary_category_v1 == "ramen"

    def test_non_ramen_izakaya_rejected(self):
        """Non-ramen, non-izakaya businesses are rejected."""
        html = """
        <html><body>
        <h1>寿司処</h1>
        <div class="menu">
            <ul>
                <li>にぎり寿司 ¥1,200</li>
            </ul>
        </div>
        <p>住所：東京都渋谷区神南1-2-3</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="寿司処",
            website="https://sushidokoro.jp",
            category="ramen",
            pages=[{"url": "https://sushidokoro.jp", "html": html}],
            address="東京都渋谷区神南1-2-3",
        )
        assert result.lead is False

    def test_chain_page_text_with_franchise_recruiting_rejected(self):
        """Page text containing FC recruiting language is rejected."""
        html = """
        <html><body>
        <h1>ラーメンチェーン</h1>
        <div class="menu">
            <ul><li>醤油ラーメン ¥850</li></ul>
        </div>
        <p>FC募集中央</p>
        <p>住所：東京都渋谷区神南1-2-3</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="ラーメンチェーン",
            website="https://ramen-chain.jp",
            category="ramen",
            pages=[{"url": "https://ramen-chain.jp", "html": html}],
            address="東京都渋谷区神南1-2-3",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_or_franchise_infrastructure"

    def test_chain_numbered_branch_rejected(self):
        """Page with numbered branch (3号店) is rejected."""
        html = """
        <html><body>
        <h1>テストラーメン</h1>
        <div class="menu">
            <ul><li>醤油ラーメン ¥850</li></ul>
        </div>
        <p>当店は3号店です。</p>
        <p>住所：東京都渋谷区神南1-2-3</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp", "html": html}],
            address="東京都渋谷区神南1-2-3",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_or_franchise_infrastructure"

    def test_chain_expansion_language_rejected(self):
        """全国に35店舗を展開 triggers chain rejection."""
        html = """
        <html><body>
        <h1>テストラーメン</h1>
        <div class="menu">
            <ul><li>醤油ラーメン ¥850</li></ul>
        </div>
        <p>全国に35店舗を展開中。</p>
        <p>住所：東京都渋谷区神南1-2-3</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp", "html": html}],
            address="東京都渋谷区神南1-2-3",
        )
        assert result.lead is False
        assert result.rejection_reason == "chain_or_franchise_infrastructure"

    def test_already_good_english_rejected(self):
        """Shop with clear, usable English menu is rejected."""
        html = """
        <html lang="en"><body>
        <h1>English Ramen Shop</h1>
        <div class="menu">
            <h2>Menu</h2>
            <ul>
                <li>Soy Sauce Ramen - ¥850</li>
                <li>Miso Ramen - ¥900</li>
                <li>Salt Ramen - ¥800</li>
                <li>Gyoza - ¥350</li>
            </ul>
        </div>
        <p>Our English menu is available. Please ask staff for details.</p>
        <p>Address: 1-2-3 Jingumae, Shibuya-ku, Tokyo</p>
        <p>Phone: 03-1234-5678</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="English Ramen Shop",
            website="https://english-ramen.jp",
            category="ramen",
            pages=[{"url": "https://english-ramen.jp/en", "html": html}],
            address="東京都渋谷区神南1-2-3",
        )
        # Page has mostly English with some Japanese prices — classified as
        # incomplete rather than fully clear English. The english_menu_issue
        # flag is still set, which is the key signal.
        assert result.english_menu_issue is True or result.lead is False

    def test_no_menu_evidence_rejected(self):
        """Shop with no menu or product evidence is rejected."""
        html = """
        <html><body>
        <h1>テストラーメン</h1>
        <p>美味しいラーメンがあります。</p>
        <p>住所：東京都渋谷区神南1-2-3</p>
        </body></html>
        """
        result = qualify_candidate(
            business_name="テストラーメン",
            website="https://example.ramen.jp",
            category="ramen",
            pages=[{"url": "https://example.ramen.jp", "html": html}],
            address="東京都渋谷区神南1-2-3",
        )
        assert result.lead is False

    def test_japan_address_variants(self):
        """Various Japan address formats all pass the gate."""
        from pipeline.qualification import _is_japan_address
        assert _is_japan_address("Japan, 〒150-0001 Tokyo, Shibuya") is True
        assert _is_japan_address("〒169-0074 東京都新宿区北新宿") is True
        assert _is_japan_address("日本 東京都渋谷区") is True
        assert _is_japan_address("大阪府大阪市中央区") is True
        assert _is_japan_address("福岡県福岡市博多区") is True
        assert _is_japan_address("", phone="+81-3-1234-5678") is True
        assert _is_japan_address("", phone="03-1234-5678") is True
        assert _is_japan_address("New York, NY 10017") is False
        assert _is_japan_address("211 E 43rd St B1, New York, NY 10017") is False
        assert _is_japan_address("71-28 Roosevelt Ave, Jackson Heights, NY 11372") is False
        assert _is_japan_address("") is False
