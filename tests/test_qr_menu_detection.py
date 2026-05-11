from __future__ import annotations

from pipeline.qr_menu_detection import QRMenuDetection, classify_qr_menu_text, has_qr_menu_signals


def test_has_qr_menu_signals_japanese_qr_order():
    text = "お席にてQRコードでご注文いただけます"
    assert has_qr_menu_signals(text) is True


def test_has_qr_menu_signals_qr_menu():
    text = "当店ではQRメニューを導入しております"
    assert has_qr_menu_signals(text) is True


def test_has_qr_menu_signals_mobile_order():
    text = "モバイルオーダー対応店舗"
    assert has_qr_menu_signals(text) is True


def test_has_qr_menu_signals_platform_domain():
    text = "ご注文は o-ordering.com からどうぞ"
    assert has_qr_menu_signals(text) is True


def test_has_qr_menu_signals_english_terms():
    assert has_qr_menu_signals("scan to order your food") is True
    assert has_qr_menu_signals("we have a digital menu available") is True
    assert has_qr_menu_signals("qr menu available at your table") is True


def test_has_qr_menu_signals_no_match():
    assert has_qr_menu_signals("美味しいラーメン屋です") is False
    assert has_qr_menu_signals("English menu available") is False
    assert has_qr_menu_signals("") is False


def test_has_qr_menu_signals_self_order():
    assert has_qr_menu_signals("セルフオーダーでご注文ください") is True


def test_has_qr_menu_signals_smartphone_order():
    assert has_qr_menu_signals("スマホで注文できます") is True


def test_has_qr_menu_signals_tablet_order():
    assert has_qr_menu_signals("タブレットでオーダー可能") is True


def test_qr_menu_detection_dataclass():
    d = QRMenuDetection(detected=True, confidence="high", source="website", evidence=["platform: o-ordering.com"])
    assert d.detected is True
    assert d.confidence == "high"
    assert d.source == "website"
    assert len(d.evidence) == 1


def test_qr_menu_detection_defaults():
    d = QRMenuDetection()
    assert d.detected is False
    assert d.confidence == ""
    assert d.source == ""
    assert d.evidence == []


def test_classify_qr_menu_text_distinguishes_normal_website_menu():
    normal = classify_qr_menu_text("メニューはこちら menu.pdf")
    existing = classify_qr_menu_text("QRコードでメニューをご覧いただけます")
    multilingual = classify_qr_menu_text("多言語QRメニュー / English QR menu available")

    assert normal.normal_website_menu_only is True
    assert normal.existing_qr_menu is False
    assert existing.existing_qr_menu is True
    assert existing.confidence == "medium"
    assert multilingual.multilingual_qr_menu is True
    assert multilingual.confidence == "high"
