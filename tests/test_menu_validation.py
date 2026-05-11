from __future__ import annotations

from pipeline.menu_validation import confirmation_summary, menu_publish_validation


def test_menu_publish_validation_blocks_unconfirmed_public_facts():
    source = {
        "restaurant_name": "Hinode Ramen",
        "items": [
            {
                "english_name": "Shoyu Ramen",
                "japanese_name": "醤油ラーメン",
                "price": "¥900",
                "description": "Soy sauce ramen",
                "ingredients": ["noodles", "soy sauce"],
                "allergens": ["wheat"],
                "approval_status": "pending_review",
            }
        ],
    }

    result = menu_publish_validation(source)

    assert result["ok"] is False
    assert "item_0_price_owner_confirmation_required" in result["errors"]
    assert "item_0_description_owner_confirmation_required" in result["errors"]
    assert "item_0_ingredients_owner_confirmation_required" in result["errors"]
    assert "item_0_allergens_owner_confirmation_required" in result["errors"]
    assert "item_0_translation_review_required" in result["errors"]


def test_menu_publish_validation_allows_owner_confirmed_menu():
    source = {
        "restaurant_name": "Hinode Ramen",
        "items": [
            {
                "english_name": "Shoyu Ramen",
                "japanese_name": "醤油ラーメン",
                "price": "¥900",
                "description": "Soy sauce ramen",
                "ingredients": ["noodles", "soy sauce"],
                "allergens": ["wheat"],
                "price_confirmed": True,
                "description_confirmed": True,
                "ingredients_confirmed": True,
                "allergens_confirmed": True,
                "approval_status": "owner_approved",
            }
        ],
    }

    assert menu_publish_validation(source)["ok"] is True
    assert confirmation_summary(source)["complete"] is True


def test_pending_combined_ingredient_allergen_confirmation_does_not_publish():
    source = {
        "restaurant_name": "Hinode Ramen",
        "items": [
            {
                "english_name": "Shoyu Ramen",
                "japanese_name": "醤油ラーメン",
                "ingredients": ["noodles"],
                "allergens": ["wheat"],
                "ingredient_allergen_confirmation": {"status": "pending_owner_confirmation"},
                "approval_status": "owner_approved",
            }
        ],
    }

    result = menu_publish_validation(source)

    assert result["ok"] is False
    assert "item_0_ingredients_owner_confirmation_required" in result["errors"]
    assert "item_0_allergens_owner_confirmation_required" in result["errors"]
