from __future__ import annotations

import pytest

from pipeline import translate_reply as tr
from pipeline.translate_reply import translate_reply, validate_translated_reply


GOOD_REPLY = """\
テストラーメン ご担当者様

ご連絡ありがとうございます。
ご希望の内容で確認用サンプルをお作りいたします。

どうぞよろしくお願いいたします。

Chris（クリス）"""


def _mock_llm(monkeypatch: pytest.MonkeyPatch, response: str, captured: dict | None = None) -> None:
    def fake_call_llm(**kwargs):
        if captured is not None:
            captured.update(kwargs)
        return response

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(tr, "call_llm", fake_call_llm)


def test_translate_reply_grammar_pass(monkeypatch: pytest.MonkeyPatch):
    _mock_llm(monkeypatch, GOOD_REPLY)
    output = translate_reply("Thank you. Please make the sample.", business_name="テストラーメン")
    assert [issue for issue in validate_translated_reply(output) if issue.startswith("grammar_")] == []


def test_translate_reply_politeness_pass(monkeypatch: pytest.MonkeyPatch):
    reply = """\
テストラーメン ご担当者様

ご連絡ありがとうございます。
ご検討いただけるよう、確認用サンプルをお作りいたします。

どうぞよろしくお願いいたします。

Chris（クリス）"""
    _mock_llm(monkeypatch, reply)
    output = translate_reply("Please prepare a polite reply.")
    issues = validate_translated_reply(output)
    assert not any(issue.startswith(("casual_form:", "missing_go_prefix:", "sender_action_not_humble:")) for issue in issues)


def test_translate_reply_tone_pass(monkeypatch: pytest.MonkeyPatch):
    reply = """\
テストラーメン ご担当者様

ご連絡ありがとうございます。
英語表記をご確認いただけるよう、確認用サンプルをお作りいたします。

どうぞよろしくお願いいたします。

Chris（クリス）"""
    _mock_llm(monkeypatch, reply)
    output = translate_reply("Use positive framing.")
    assert not any(issue.startswith("negative_or_revenue_framing:") for issue in validate_translated_reply(output))


def test_translate_reply_signoff_pass(monkeypatch: pytest.MonkeyPatch):
    _mock_llm(monkeypatch, GOOD_REPLY)
    output = translate_reply("Sign off correctly.")
    assert output.splitlines()[-1] == "Chris（クリス）"


def test_validator_rejects_plain_chris_signoff():
    issues = validate_translated_reply("ご連絡ありがとうございます。\n\nChris")
    assert "signoff_must_be_chris_with_katakana" in issues
    assert "plain_chris_signoff" in issues


def test_validator_rejects_english_leaks():
    issues = validate_translated_reply("ご検討ありがとうございます。\n\nThank you for your consideration.\n\nChris（クリス）")
    assert any(issue.startswith("english_leak:") for issue in issues)


def test_translate_reply_injects_business_name_context(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}
    _mock_llm(monkeypatch, GOOD_REPLY, captured)
    translate_reply("Please reply.", business_name="テストラーメン")
    assert "テストラーメン" in captured["user"]


@pytest.mark.parametrize("bad_text", ["AIを使って対応いたします。\n\nChris（クリス）", "自動化で作ります。\n\nChris（クリス）"])
def test_validator_rejects_ai_or_automation_mentions(bad_text: str):
    assert "internal_tool_or_ai_mention" in validate_translated_reply(bad_text)
