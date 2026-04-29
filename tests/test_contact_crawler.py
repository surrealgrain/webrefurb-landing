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
