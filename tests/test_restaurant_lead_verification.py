from __future__ import annotations

import json

from pipeline.restaurant_lead_verification import (
    source_strength_for,
    verify_restaurant_lead_queue,
    verify_restaurant_lead_record,
)


def _record(**overrides):
    base = {
        "lead_id": "wrm-email-test-owner-1234abcd",
        "generated_at": "2026-05-01T00:00:00+00:00",
        "business_name": "麺屋テスト",
        "locked_business_name": "麺屋テスト",
        "business_name_locked": True,
        "business_name_verified_by": ["restaurant_email_import"],
        "website": "https://menya-test.jp",
        "address": "東京都",
        "source_query": "restaurant_email_import",
        "source_file": "restaurant_email_leads.json",
        "source_count": 1,
        "source_coverage_score": 45,
        "source_urls": {
            "website": "https://menya-test.jp",
            "map_url": "",
            "evidence_urls": ["https://menya-test.jp/contact"],
        },
        "email": "owner@menya-test.jp",
        "email_source_url": "https://menya-test.jp/contact",
        "contacts": [
            {
                "type": "email",
                "value": "owner@menya-test.jp",
                "href": "mailto:owner@menya-test.jp",
                "source_url": "https://menya-test.jp/contact",
                "actionable": True,
            }
        ],
        "lead": True,
        "type_of_restaurant": "ramen",
        "primary_category_v1": "ramen",
        "menu_type": "ramen",
        "city": "Tokyo",
        "establishment_profile": "ramen_only",
        "english_menu_issue": True,
        "english_menu_state": "missing",
        "quality_tier": "high",
        "candidate_inbox_status": "pitch_ready",
        "pitch_ready": True,
        "review_status": "pending",
        "outreach_status": "new",
        "launch_readiness_status": "manual_review",
        "launch_readiness_reasons": [],
        "lead_evidence_dossier": {"english_menu_state": "missing"},
        "evidence_snippets": ["醤油ラーメン 味玉 トッピング メニュー"],
        "matched_friction_evidence": [],
        "status_history": [{"status": "new", "timestamp": "2026-05-01T00:00:00+00:00"}],
    }
    base.update(overrides)
    return base


def test_verification_demotes_imported_high_records_until_explicit_promotion():
    verified = verify_restaurant_lead_record(_record(), checked_at="2026-05-01T01:00:00+00:00")

    assert verified["email_verification_status"] == "verified"
    assert verified["name_verification_status"] == "single_source"
    assert verified["city_verification_status"] == "verified"
    assert verified["category_verification_status"] == "verified"
    assert verified["english_menu_check_status"] == "no_hard_reject"
    assert verified["verification_status"] == "needs_review"
    assert verified["pitch_readiness_status"] == "needs_name_review"
    assert verified["candidate_inbox_status"] == "needs_name_review"
    assert verified["pitch_card_status"] == "needs_name_review"
    assert verified["pitch_card_openable"] is True
    assert verified["opportunistic_pitch_candidate"] is True
    assert verified["pitch_ready"] is False
    assert verified["outreach_status"] == "needs_review"
    assert "restaurant_email_verification_not_promoted" in verified["launch_readiness_reasons"]


def test_unknown_english_menu_does_not_block_opportunistic_pitch_candidate():
    verified = verify_restaurant_lead_record(
        _record(
            english_menu_issue=False,
            english_menu_state="unknown",
            lead_evidence_dossier={"english_menu_state": "unknown"},
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["english_menu_check_status"] == "needs_review"
    assert verified["opportunistic_pitch_candidate"] is True


def test_two_source_manual_review_can_verify_but_keeps_import_blocked():
    verified = verify_restaurant_lead_record(
        _record(
            business_name="割烹 かじ 本店",
            type_of_restaurant="izakaya",
            primary_category_v1="izakaya",
            menu_type="seafood_izakaya",
            establishment_profile="izakaya_seafood_sake_oden",
            quality_tier="v1_clean",
            restaurant_lead_manual_review={
                "name_status": "accepted",
                "category_status": "accepted",
                "chain_status": "clear",
                "sources": [
                    "https://www.example-restaurant.test/",
                    "https://example-directory.test/kaji",
                ],
            },
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["name_verification_status"] == "manually_accepted"
    assert verified["category_verification_status"] == "verified"
    assert verified["chain_verification_status"] == "clear"
    assert verified["verification_status"] == "verified"
    assert verified["pitch_readiness_status"] == "needs_scope_review"
    assert verified["candidate_inbox_status"] == "needs_scope_review"
    assert verified["pitch_ready"] is False
    assert verified["launch_readiness_status"] == "manual_review"


def test_two_source_manual_category_rejection_overrides_imported_category():
    verified = verify_restaurant_lead_record(
        _record(
            business_name="楽仙樓",
            type_of_restaurant="izakaya",
            primary_category_v1="izakaya",
            menu_type="izakaya",
            establishment_profile="izakaya_food_and_drinks",
            restaurant_lead_manual_review={
                "category_status": "out_of_scope",
                "category_sources": [
                    "https://rakusenroh.jp/",
                    "https://www.ekiten.jp/shop_7099768/",
                ],
            },
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["category_verification_status"] == "rejected"
    assert verified["verification_status"] == "rejected"
    assert verified["pitch_readiness_status"] == "rejected"
    assert verified["pitch_ready"] is False


def test_manual_email_domain_review_requires_two_sources():
    one_source = verify_restaurant_lead_record(
        _record(
            email="info@operator-domain.jp",
            email_source_url="https://menya-test.jp/contact",
            website="https://menya-test.jp/contact",
            source_urls={"website": "https://menya-test.jp/contact", "evidence_urls": []},
            restaurant_lead_manual_review={
                "email_status": "accepted",
                "email_sources": ["https://menya-test.jp/contact"],
            },
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )
    two_sources = verify_restaurant_lead_record(
        _record(
            email="info@operator-domain.jp",
            email_source_url="https://menya-test.jp/contact",
            website="https://menya-test.jp/contact",
            source_urls={"website": "https://menya-test.jp/contact", "evidence_urls": []},
            restaurant_lead_manual_review={
                "email_status": "accepted",
                "email_sources": [
                    "https://menya-test.jp/contact",
                    "https://operator-domain.jp/company",
                ],
            },
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert one_source["email_verification_status"] == "needs_review"
    assert two_sources["email_verification_status"] == "verified"
    assert two_sources["pitch_ready"] is False
    assert two_sources["launch_readiness_status"] == "manual_review"


def test_manual_english_menu_hard_reject_overrides_missing_state():
    verified = verify_restaurant_lead_record(
        _record(
            restaurant_lead_manual_review={
                "english_menu_status": "already_english_supported",
                "english_menu_sources": [
                    "https://restaurant.example/en/",
                    "https://restaurant.example/en/menu/",
                ],
            },
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["english_menu_check_status"] == "rejected"
    assert verified["verification_status"] == "rejected"
    assert verified["pitch_readiness_status"] == "rejected"
    assert verified["pitch_ready"] is False


def test_verification_rejects_placeholder_email_without_discarding_record():
    verified = verify_restaurant_lead_record(
        _record(email="000000@gmail.com", email_source_url="https://menya-test.jp/contact"),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["email_verification_status"] == "rejected"
    assert verified["verification_status"] == "rejected"
    assert verified["pitch_readiness_status"] == "rejected"
    assert verified["lead"] is True
    assert verified["launch_readiness_status"] == "manual_review"


def test_verification_rejects_generic_page_title_names():
    verified = verify_restaurant_lead_record(
        _record(business_name="特定商取引法に基づく表記"),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["name_verification_status"] == "rejected"
    assert verified["verification_status"] == "rejected"
    assert verified["pitch_readiness_status"] == "rejected"


def test_verification_rejects_company_page_title_as_restaurant_name():
    verified = verify_restaurant_lead_record(
        _record(business_name="しょうゆ・つゆ・たれの大髙醤油株式会社"),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["name_verification_status"] == "rejected"
    assert verified["verification_status"] == "rejected"


def test_verification_rejects_support_platform_email_prefixes():
    verified = verify_restaurant_lead_record(
        _record(
            email="support-ecmall-karasuma@kyotobank.co.jp",
            email_source_url="https://www.kyotobank.co.jp/ecmall/creator/669/profile",
            website="https://www.kyotobank.co.jp/ecmall/creator/669/profile",
            source_urls={"website": "https://www.kyotobank.co.jp/ecmall/creator/669/profile", "evidence_urls": []},
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["email_verification_status"] == "rejected"
    assert verified["verification_status"] == "rejected"


def test_verification_rejects_academic_email_domains():
    verified = verify_restaurant_lead_record(
        _record(
            business_name="Noah",
            email="itsuro@ees.hokudai.ac.jp",
            email_source_url="https://noah.ees.hokudai.ac.jp/envmi/koizumilab/member/",
            website="https://noah.ees.hokudai.ac.jp/envmi/koizumilab/member/",
            source_urls={"website": "https://noah.ees.hokudai.ac.jp/envmi/koizumilab/member/", "evidence_urls": []},
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["email_verification_status"] == "rejected"
    assert verified["verification_status"] == "rejected"


def test_verification_rejects_escaped_email_artifacts():
    verified = verify_restaurant_lead_record(
        _record(email="u003ebeer@schmatz.jp"),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["email_verification_status"] == "rejected"
    assert verified["verification_status"] == "rejected"


def test_verification_rejects_placeholder_domains():
    verified = verify_restaurant_lead_record(
        _record(email="info@domain.com"),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["email_verification_status"] == "rejected"
    assert verified["verification_status"] == "rejected"


def test_manual_email_rejection_overrides_directory_email():
    verified = verify_restaurant_lead_record(
        _record(
            email="staff@example-operator.jp",
            email_source_url="https://tabelog.com/tokyo/A1301/A130101/13000000/",
            website="https://tabelog.com/tokyo/A1301/A130101/13000000/",
            source_urls={
                "website": "https://tabelog.com/tokyo/A1301/A130101/13000000/",
                "evidence_urls": ["https://example-directory.test/server-error"],
            },
            restaurant_lead_manual_review={
                "email_status": "rejected",
                "email_sources": [
                    "https://example-directory.test/server-error",
                    "https://example-directory.test/listing",
                ],
            },
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["email_verification_status"] == "rejected"
    assert verified["email_verification_reason"] == "email manually rejected with two source confirmations"
    assert verified["verification_status"] == "rejected"


def test_free_mail_isp_domains_need_review_even_from_official_pages():
    verified = verify_restaurant_lead_record(
        _record(email="shop@mail.com", email_source_url="https://menya-test.jp/contact"),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["email_verification_status"] == "needs_review"
    assert verified["pitch_readiness_status"] == "needs_email_review"
    assert verified["pitch_card_status"] == "needs_email_review"
    assert verified["pitch_card_openable"] is True


def test_hard_chain_block_quarantines_pitch_card():
    verified = verify_restaurant_lead_record(
        _record(
            business_name="鳥貴族 テスト店",
            locked_business_name="鳥貴族 テスト店",
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["chain_verification_status"] == "rejected"
    assert verified["pitch_card_status"] == "hard_blocked"
    assert verified["pitch_card_openable"] is False


def test_weak_email_source_remains_openable_pitch_card():
    verified = verify_restaurant_lead_record(
        _record(
            website="https://www.value-press.com/pressrelease/358032",
            email_source_url="https://www.value-press.com/pressrelease/358032",
            source_urls={"website": "https://www.value-press.com/pressrelease/358032", "evidence_urls": []},
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["source_strength"] == "weak_source"
    assert verified["pitch_card_status"] in {"needs_email_review", "needs_name_review", "needs_scope_review"}
    assert verified["pitch_card_openable"] is True


def test_organization_domains_need_email_review_even_from_official_pages():
    verified = verify_restaurant_lead_record(
        _record(email="office@kitayama.or.jp", email_source_url="https://kitayama.or.jp/"),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["email_verification_status"] == "needs_review"
    assert verified["pitch_readiness_status"] == "needs_email_review"


def test_mismatched_email_domain_needs_review_even_from_official_pages():
    verified = verify_restaurant_lead_record(
        _record(
            email="info@operator-domain.jp",
            email_source_url="https://menya-test.jp/contact",
            website="https://menya-test.jp/contact",
            source_urls={"website": "https://menya-test.jp/contact", "evidence_urls": []},
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["email_verification_status"] == "needs_review"
    assert verified["email_verification_reason"] == "email domain differs from recorded official source host"
    assert verified["pitch_readiness_status"] == "needs_email_review"


def test_subdomain_email_domain_matches_official_source():
    verified = verify_restaurant_lead_record(
        _record(
            email="info@menya-test.jp",
            email_source_url="https://contact.menya-test.jp/form",
            website="https://contact.menya-test.jp/form",
            source_urls={"website": "https://contact.menya-test.jp/form", "evidence_urls": []},
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["email_verification_status"] == "verified"


def test_mismatched_email_domain_does_not_match_directory_evidence_url():
    verified = verify_restaurant_lead_record(
        _record(
            email="info@o-2.jp",
            email_source_url="https://menya-test.jp/contact",
            website="https://menya-test.jp/contact",
            source_urls={
                "website": "https://menya-test.jp/contact",
                "evidence_urls": ["https://www.o-2.jp/contents/example/"],
            },
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["email_verification_status"] == "needs_review"
    assert verified["email_verification_reason"] == "email domain differs from recorded official source host"


def test_verification_rejects_missing_info_email_artifacts():
    verified = verify_restaurant_lead_record(
        _record(email="nfo@menya-test.jp"),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["email_verification_status"] == "rejected"
    assert verified["verification_status"] == "rejected"


def test_short_email_local_parts_need_review_even_from_official_pages():
    verified = verify_restaurant_lead_record(
        _record(email="to@menya-test.jp"),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["email_verification_status"] == "needs_review"
    assert verified["email_verification_reason"] == "short email local part needs owner confirmation"
    assert verified["pitch_readiness_status"] == "needs_email_review"


def test_verification_rejects_article_title_names():
    verified = verify_restaurant_lead_record(
        _record(business_name="大阪・堺に『麺ノ響』がオープン！"),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["name_verification_status"] == "rejected"
    assert verified["verification_status"] == "rejected"


def test_verification_rejects_out_of_scope_restaurant_categories():
    verified = verify_restaurant_lead_record(
        _record(business_name="鮨処 凜", menu_type="seafood_izakaya", type_of_restaurant="izakaya"),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["category_verification_status"] == "rejected"
    assert verified["verification_status"] == "rejected"


def test_verification_rejects_chinese_restaurant_category_artifacts():
    verified = verify_restaurant_lead_record(
        _record(business_name="お粥と京野菜中華 福住 （【旧店名】中華菜館 福住）", menu_type="izakaya", type_of_restaurant="izakaya"),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["category_verification_status"] == "rejected"
    assert verified["verification_status"] == "rejected"


def test_verification_rejects_non_ramen_non_izakaya_directory_categories():
    for business_name in [
        "タイ料理バンセーン 西新橋店 (虎ノ門ヒルズ/タイ料理)",
        "JACK 麻布十番店 (麻布十番/ダーツ)",
        "フジ葡萄酒店 (西鉄平尾/ワインバー)",
        "讃岐ブルース 飯田橋 (飯田橋/うどん)",
        "Bar 37℃ (神保町/バー)",
        "韓国料理店 ソル (瑞光四丁目/韓国料理)",
        "アサイーボウル専門店Rose (京都河原町/スイーツ)",
        "SOBASAY (小伝馬町/立ち食いそば)",
        "LeChic (天満橋/洋菓子)",
        "メキシコ料理 ドンブランコ (新橋/メキシコ料理)",
        "寿し心咲 （すしごころさく）",
        "鮓 有無",
        "生餃子製造トコロ てんしんのきもち",
    ]:
        verified = verify_restaurant_lead_record(
            _record(business_name=business_name, menu_type="izakaya", type_of_restaurant="izakaya"),
            checked_at="2026-05-01T01:00:00+00:00",
        )

        assert verified["category_verification_status"] == "rejected"
        assert verified["verification_status"] == "rejected"


def test_verification_holds_generic_japanese_cuisine_for_scope_review():
    for business_name in [
        "割烹 かじ 本店",
        "日本料理と日本酒 惠史",
        "出汁と小鉢の和食 なのに",
    ]:
        verified = verify_restaurant_lead_record(
            _record(
                business_name=business_name,
                menu_type="seafood_izakaya",
                type_of_restaurant="izakaya",
                quality_tier="v1_clean",
            ),
            checked_at="2026-05-01T01:00:00+00:00",
        )

        assert verified["category_verification_status"] == "needs_review"
        assert verified["verification_status"] == "needs_review"
        assert verified["pitch_readiness_status"] == "needs_scope_review"


def test_verification_rejects_tabelog_review_titles_and_handles():
    for business_name in [
        "(yoji.164)",
        "マスタ、の、もっとも、遅い夏休み、の、秋休み その６",
        "フォアグラもなか◎(眠り)",
        "確かな味を受け継ぐ銀座の老舗(JoeColombia)",
    ]:
        verified = verify_restaurant_lead_record(
            _record(
                business_name=business_name,
                website="https://tabelog.com/tokyo/A1302/A130202/13226416/dtlrvwlst/B525251501/",
                email_source_url="https://tabelog.com/tokyo/A1302/A130202/13226416/dtlrvwlst/B525251501/",
                source_urls={
                    "website": "https://tabelog.com/tokyo/A1302/A130202/13226416/dtlrvwlst/B525251501/",
                    "evidence_urls": [],
                },
            ),
            checked_at="2026-05-01T01:00:00+00:00",
        )

        assert verified["name_verification_status"] == "rejected"
        assert verified["verification_status"] == "rejected"


def test_english_language_source_url_needs_menu_review():
    verified = verify_restaurant_lead_record(
        _record(
            business_name="博多ごまサバ・博多もつ鍋 キッチンしゃもじ",
            website="https://locoplace.jp/en/about",
            email_source_url="https://locoplace.jp/en/about",
            source_urls={"website": "https://locoplace.jp/en/about", "evidence_urls": []},
            email="info@locoplace.jp",
            menu_type="seafood_izakaya",
            type_of_restaurant="izakaya",
            quality_tier="v1_clean",
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["english_menu_check_status"] == "needs_review"
    assert verified["pitch_readiness_status"] == "needs_scope_review"


def test_verification_rejects_out_of_scope_source_paths():
    verified = verify_restaurant_lead_record(
        _record(
            business_name="半兵衛茶寮 浅草",
            email="guide@hanbei.ltd",
            email_source_url="https://hanbei.ltd/mochishop/",
            website="https://hanbei.ltd/mochishop/",
            source_urls={"website": "https://hanbei.ltd/mochishop/", "evidence_urls": []},
            menu_type="izakaya",
            type_of_restaurant="izakaya",
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["category_verification_status"] == "rejected"
    assert verified["verification_status"] == "rejected"


def test_verification_rejects_known_multibranch_chain_domains():
    verified = verify_restaurant_lead_record(
        _record(
            business_name="博多もつ鍋おおやま 博多1番街",
            email="hakataeki@motu-ooyama.com",
            website="https://www.motu-ooyama.com/contact/?id=41",
            email_source_url="https://www.motu-ooyama.com/contact/?id=41",
            source_urls={"website": "https://www.motu-ooyama.com/contact/?id=41", "evidence_urls": []},
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["chain_verification_status"] == "rejected"
    assert verified["verification_status"] == "rejected"


def test_branch_like_store_names_need_operator_review():
    verified = verify_restaurant_lead_record(
        _record(
            business_name="博多鶏そば TORISOBA TORIDEN KITTE博多店 （【旧店名】博多担々麺 とり田）",
            menu_type="ramen",
            type_of_restaurant="ramen",
            quality_tier="v1_clean",
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["chain_verification_status"] == "needs_review"
    assert verified["chain_verification_reason"] == "branch-like store name needs operator confirmation"
    assert verified["verification_status"] == "needs_review"


def test_operator_source_paths_need_operator_review():
    verified = verify_restaurant_lead_record(
        _record(
            business_name="串焼 満天 六角編",
            email="info@fun-no1.com",
            website="https://fun-no1.com/business/restrant/manten/",
            email_source_url="https://fun-no1.com/business/restrant/manten/",
            source_urls={"website": "https://fun-no1.com/business/restrant/manten/", "evidence_urls": []},
            menu_type="yakitori",
            type_of_restaurant="izakaya",
            quality_tier="v1_clean",
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["chain_verification_status"] == "needs_review"
    assert verified["chain_verification_reason"] == "operator or multi-location source needs confirmation"
    assert verified["verification_status"] == "needs_review"


def test_verification_rejects_hotel_operator_domains():
    verified = verify_restaurant_lead_record(
        _record(
            business_name="うまいもの処 ゆめぜん 東大阪",
            email="info-higashiosaka@koko-hotels.com",
            website="https://koko-hotels.com/higashiosaka/?modal=meal",
            email_source_url="https://koko-hotels.com/higashiosaka/?modal=meal",
            menu_type="kushiage",
            type_of_restaurant="izakaya",
            source_urls={"website": "https://koko-hotels.com/higashiosaka/?modal=meal", "evidence_urls": []},
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["chain_verification_status"] == "rejected"
    assert verified["verification_status"] == "rejected"


def test_verification_rejects_restaurant_group_brand_domains():
    verified = verify_restaurant_lead_record(
        _record(
            business_name="赤坂 ごだいご",
            email="ms0722@daiwa-j.com",
            website="https://daiwa-j.com/brands/godaigo/akasaka/",
            email_source_url="https://daiwa-j.com/brands/godaigo/akasaka/",
            menu_type="yakitori",
            type_of_restaurant="izakaya",
            source_urls={"website": "https://daiwa-j.com/brands/godaigo/akasaka/", "evidence_urls": []},
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["chain_verification_status"] == "rejected"
    assert verified["verification_status"] == "rejected"


def test_verification_rejects_non_restaurant_source_domains():
    verified = verify_restaurant_lead_record(
        _record(
            business_name="めぐみ水産",
            email="info@toyocamerahouse.com",
            website="https://toyocamerahouse.com/rental.php",
            email_source_url="https://toyocamerahouse.com/rental.php",
            source_urls={"website": "https://toyocamerahouse.com/rental.php", "evidence_urls": []},
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["chain_verification_status"] == "rejected"
    assert verified["verification_status"] == "rejected"


def test_verification_rejects_repeated_placeholder_email_local_part():
    verified = verify_restaurant_lead_record(
        _record(email="oooo@kanefuku-fukutake.jp"),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["email_verification_status"] == "rejected"
    assert verified["verification_status"] == "rejected"


def test_directory_email_requires_direct_restaurant_confirmation():
    verified = verify_restaurant_lead_record(
        _record(
            email="info@o-2.jp",
            website="https://www.o-2.jp/contents/example/",
            email_source_url="https://www.o-2.jp/contents/example/",
            source_urls={"website": "https://www.o-2.jp/contents/example/", "evidence_urls": []},
        ),
        checked_at="2026-05-01T01:00:00+00:00",
    )

    assert verified["source_strength"] == "directory"
    assert verified["email_verification_status"] == "needs_review"
    assert verified["pitch_readiness_status"] == "needs_email_review"


def test_source_strength_classifies_owned_directory_and_official_sources():
    assert source_strength_for(_record(website="https://menya-test.jp"))[0] == "official_site"
    assert source_strength_for(_record(
        website="https://tabelog.com/tokyo/A0000/000000/",
        email_source_url="https://tabelog.com/tokyo/A0000/000000/",
        source_urls={"website": "https://tabelog.com/tokyo/A0000/000000/", "evidence_urls": []},
    ))[0] == "directory"
    assert source_strength_for(_record(
        website="https://www.e-ekichika.com/shop/hakkon",
        email_source_url="https://www.e-ekichika.com/shop/hakkon",
        source_urls={"website": "https://www.e-ekichika.com/shop/hakkon", "evidence_urls": []},
    ))[0] == "directory"
    assert source_strength_for(_record(
        website="https://lit.link/menyatest",
        email_source_url="https://lit.link/menyatest",
        source_urls={"website": "https://lit.link/menyatest", "evidence_urls": []},
    ))[0] == "restaurant_owned_page"
    assert source_strength_for(_record(
        website="https://mendokorooana.hp.peraichi.com",
        email_source_url="https://mendokorooana.hp.peraichi.com",
        source_urls={"website": "https://mendokorooana.hp.peraichi.com", "evidence_urls": []},
    ))[0] == "restaurant_owned_page"
    assert source_strength_for(_record(
        website="https://www.value-press.com/pressrelease/358032",
        email_source_url="https://www.value-press.com/pressrelease/358032",
        source_urls={"website": "https://www.value-press.com/pressrelease/358032", "evidence_urls": []},
    ))[0] == "weak_source"
    assert source_strength_for(_record(
        website="http://r.goope.jp/daruten",
        email_source_url="http://r.goope.jp/daruten",
        source_urls={"website": "http://r.goope.jp/daruten", "evidence_urls": []},
    ))[0] == "restaurant_owned_page"
    assert source_strength_for(_record(
        website="http://uplink-app-v3.com/app/download/sid/18989",
        email_source_url="http://uplink-app-v3.com/app/download/sid/18989",
        source_urls={"website": "http://uplink-app-v3.com/app/download/sid/18989", "evidence_urls": []},
    ))[0] == "weak_source"


def test_verify_restaurant_lead_queue_updates_only_restaurant_email_records(tmp_path):
    leads_dir = tmp_path / "leads"
    leads_dir.mkdir()
    restaurant = _record()
    other = {
        **_record(
            lead_id="wrm-manual-test",
            source_query="manual_add",
            source_file="",
            candidate_inbox_status="pitch_ready",
            pitch_ready=True,
        ),
    }
    (leads_dir / f"{restaurant['lead_id']}.json").write_text(json.dumps(restaurant), encoding="utf-8")
    (leads_dir / f"{other['lead_id']}.json").write_text(json.dumps(other), encoding="utf-8")

    summary = verify_restaurant_lead_queue(state_root=tmp_path)

    updated_restaurant = json.loads((leads_dir / f"{restaurant['lead_id']}.json").read_text())
    untouched_other = json.loads((leads_dir / f"{other['lead_id']}.json").read_text())
    assert summary["selected_records"] == 1
    assert summary["pitch_card_counts"]["reviewable_pitch_cards"] == 1
    assert updated_restaurant["verification_status"] == "needs_review"
    assert updated_restaurant["pitch_card_openable"] is True
    assert updated_restaurant["pitch_ready"] is False
    assert "verification_status" not in untouched_other
