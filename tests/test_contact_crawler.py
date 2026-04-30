from __future__ import annotations

from pipeline.contact_crawler import (
    DiscoveryTarget,
    _official_external_url,
    contact_candidate_urls,
    dedupe_targets,
    extract_contact_signals,
    mock_llm_parse_contact_points,
    normalize_website_url,
)


def test_normalize_website_url_strips_tracking_and_forces_https():
    url = "http://WWW.Example.co.jp/menu/?utm_source=maps&lang=ja&gclid=abc#section"
    assert normalize_website_url(url) == "https://www.example.co.jp/menu?lang=ja"


def test_normalize_website_url_rejects_non_web_schemes():
    assert normalize_website_url("mailto:owner@example.jp") == ""
    assert normalize_website_url("tel:03-1234-5678") == ""


def test_official_external_url_unwraps_directory_redirects():
    href = "https://tabelog.com/redirect?url=https%3A%2F%2Fofficial-ramen.jp%2F%3Futm_source%3Dtabelog"
    assert _official_external_url("https://tabelog.com/fukuoka/", href) == "https://official-ramen.jp"


def test_dedupe_targets_by_domain_merges_sources():
    targets = [
        DiscoveryTarget(
            name="テストラーメン",
            website="http://example-ramen.jp/?utm_source=tabelog",
            category="ラーメン",
            city="福岡",
            source="google_places",
        ),
        DiscoveryTarget(
            name="テストラーメン",
            website="https://example-ramen.jp",
            category="ラーメン",
            city="福岡",
            source="tabelog",
        ),
    ]

    deduped = dedupe_targets(targets)

    assert len(deduped) == 1
    assert deduped[0].website == "https://example-ramen.jp"
    assert deduped[0].source == "google_places+tabelog"


def test_extract_contact_signals_finds_email_and_forms_only():
    html = """
    <html><body>
      <a href="mailto:Owner@Example-Ramen.jp">お問い合わせ</a>
      <a href="https://lin.ee/abc123">LINE</a>
      <a href="https://www.instagram.com/example_ramen/">Instagram</a>
      <p>LINE公式 @example-ramen</p>
      <form action="/contact"></form>
    </body></html>
    """

    signals = extract_contact_signals(html)

    assert signals.emails == ["owner@example-ramen.jp"]
    assert signals.has_form is True
    assert signals.form_actions == ["/contact"]


def test_extract_contact_signals_captures_form_actions_and_required_fields():
    html = """
    <html><body>
      <form action="/reservation">
        <input name="name" required>
        <input name="tel" required>
        <textarea name="message"></textarea>
      </form>
    </body></html>
    """

    signals = extract_contact_signals(html)

    assert signals.has_form is True
    assert signals.form_actions == ["/reservation"]
    assert signals.required_fields == ["name", "tel"]
    assert signals.contact_form_profile == "phone_required"


def test_extract_contact_signals_detects_javascript_contact_form_without_form_tag():
    html = """
    <html><body>
      <h1>お問い合わせフォーム</h1>
      <div class="fc-form">
        <input type="text" name="fullname" class="require">
        <input type="email" name="email" class="require check-email">
        <input type="tel" name="phone" class="check-phone">
        <textarea name="message" class="require"></textarea>
        <button type="submit">入力内容の確認へ進む</button>
      </div>
    </body></html>
    """

    signals = extract_contact_signals(html)

    assert signals.has_form is True
    assert signals.required_fields == ["fullname", "email", "message"]
    assert signals.form_field_names == ["fullname", "email", "phone", "message"]
    assert signals.contact_form_profile == "supported_inquiry"


def test_reservation_form_profile_is_not_supported_inquiry():
    html = """
    <html><body>
      <form action="/booking/confirm">
        <input name="name" required>
        <input name="reservation_date" required>
        <select name="reservation_time" required><option>18:00</option></select>
        <input name="party_size" required>
        <button type="submit">予約確認</button>
      </form>
    </body></html>
    """

    signals = extract_contact_signals(html)

    assert signals.has_form is True
    assert signals.contact_form_profile == "reservation_only"


def test_hidden_only_form_is_not_counted_as_contact_form():
    html = """
    <html><body>
      <form action="/search">
        <input type="hidden" name="token" value="abc">
        <input type="hidden" name="post_id" value="1">
      </form>
    </body></html>
    """

    signals = extract_contact_signals(html)

    assert signals.has_form is False
    assert signals.contact_form_profile == "hidden_only"


def test_contact_form_7_inquiry_form_is_supported():
    html = """
    <html><body>
      <form class="wpcf7-form" action="/contact/#wpcf7-f1-p1-o1">
        <input name="your-name" aria-required="true">
        <input name="your-email" aria-required="true">
        <textarea name="your-message" aria-required="true"></textarea>
        <input type="submit" value="送信">
      </form>
    </body></html>
    """

    signals = extract_contact_signals(html)

    assert signals.has_form is True
    assert signals.required_fields == ["your-name", "your-email", "your-message"]
    assert signals.contact_form_profile == "supported_inquiry"


def test_newsletter_order_and_recruit_forms_are_profiled_as_unsupported():
    cases = [
        ("newsletter", '<form action="/newsletter"><input name="email" required><button type="submit">Subscribe</button></form>'),
        ("commerce", '<form action="/order"><input name="email" required><button type="submit">注文</button></form>'),
        ("recruiting", '<form action="/recruit"><input name="email" required><button type="submit">応募</button></form>'),
    ]

    for expected, html in cases:
        signals = extract_contact_signals(html)
        assert signals.contact_form_profile == expected


def test_contact_candidate_urls_excludes_reservation_links():
    anchors = [
        {"href": "/contact", "text": "お問い合わせ"},
        {"href": "/reservation", "text": "ご予約"},
        {"href": "/yoyaku", "text": "予約フォーム"},
    ]

    assert contact_candidate_urls("https://example-ramen.jp", anchors) == ["https://example-ramen.jp/contact"]


def test_extract_contact_signals_ignores_telemetry_ingest_emails():
    html = """
    <html><body>
      <script>window.SENTRY_DSN = "https://abc@o462166.ingest.sentry.io/123";</script>
      <script>window.SENTRY_DSN = "https://abc@sentry-next.wixpress.com/123";</script>
      <img src="/assets/z_banbi_logo_header_light@2x.png">
      <a href="mailto:owner@real-ramen.jp">お問い合わせ</a>
    </body></html>
    """

    signals = extract_contact_signals(html)

    assert signals.emails == ["owner@real-ramen.jp"]


def test_extract_contact_signals_ignores_unsupported_social_routes():
    html = """
    <script type="application/ld+json">
    {"@context":"https://schema.org","@graph":[],"@type":"Restaurant"}
    </script>
    <style>@font-face { font-family: test; } @media (min-width: 1px) {}</style>
    <script>window.newrelic = "@newrelic";</script>
    """

    signals = extract_contact_signals(html)

    assert signals.emails == []
    assert signals.has_form is False


def test_contact_candidate_urls_prefers_same_site_contact_links():
    anchors = [
        {"href": "/contact", "text": "お問い合わせ"},
        {"href": "https://example-ramen.jp/company", "text": "会社概要"},
        {"href": "https://instagram.com/example", "text": "Instagram"},
        {"href": "https://other.example/contact", "text": "Contact"},
    ]

    urls = contact_candidate_urls("https://example-ramen.jp", anchors)

    assert urls == [
        "https://example-ramen.jp/contact",
        "https://example-ramen.jp/company",
    ]


def test_mock_llm_fallback_marks_contact_intent_without_guessing():
    signals = mock_llm_parse_contact_points(
        "お問い合わせフォームからご連絡ください。メールは画像内に掲載しています。",
        contact_intent=True,
    )

    assert signals.llm_mock_used is True
    assert signals.emails == []
    assert signals.llm_mock_reason == "contact_intent_without_regex_hit"
