"""Translate operator replies from English to natural Japanese business email text.

Uses the 5-pass verification rules as LLM system prompt to ensure output reads
as natural Japanese — not translated English.

Pass 1: Grammar — correct verb forms, keigo pairings, relative clauses
Pass 2: Naturalness — right word choices, no translated-sounding phrasing
Pass 3: Politeness — consistent 丁寧語 + 謙譲語, no level mixing
Pass 4: Tone — positive framing, no presumptuous problem statements
Pass 5: Full email — no English leaks, proper formatting, consistent sign-off
"""

from __future__ import annotations

import os
import re

from .llm_client import call_llm, LLMClientError

# ---------------------------------------------------------------------------
# System prompt encoding the 5-pass verification rules
# ---------------------------------------------------------------------------

TRANSLATE_SYSTEM_PROMPT = """You translate English business emails into natural Japanese. \
The output must read as if a Japanese person wrote it — never like a translation.

Rules:
1. Use consistent 丁寧語 (teineigo, です/ます) with appropriate 謙譲語 (kenjougo) \
   for the sender's actions. No casual forms (だね, してる) and no overly stiff \
   archaic forms (謹んで, 拝察).
2. Frame benefits positively. Never directly state problems or imply the \
   recipient has issues. Use patterns like 「〜いただけるようになります」\
   (it becomes possible to...) rather than "tourists can't understand".
3. Match standard Japanese business email structure: \
   greeting → context → body → closing. Use paragraph breaks (double newline) \
   between sections.
4. Sign off as: Chris（クリス） — never plain "Chris" without the katakana reading.
5. The sender introduces himself as someone who creates English menus for restaurants: \
   飲食店向けの英語メニュー制作を行っております、Chris（クリス）と申します。 \
   Only include this self-intro if the context suggests it's needed (e.g., first reply).
6. Never mention AI, automation, machine learning, or software tools.
7. For prices, use ¥ with comma separators (e.g., ¥30,000) or 円 (e.g., 30,000円).
8. Translate the intent and meaning, not word-by-word. A Japanese reader should \
   feel the email was written for them, not localized from English.
9. If the English mentions specific restaurant concepts (ramen, izakaya, toppings, \
   ticket machines, courses, drinks), use the natural Japanese terms the owner \
   would use (ラーメン, 居酒屋, トッピング, 券売機, コース, ドリンク).
10. Keep the same level of formality and warmth as these example templates:

Example ramen outreach:
「海外からのお客様にも、ラーメンの種類やトッピングが伝わる英語メニューをお作りしております。
英語メニューがあれば、お客様ご自身でメニュー内容をご確認いただけるようになります。」

Example izakaya outreach:
「海外からのお客様にも、お料理やドリンクの内容が伝わる英語メニューをお作りしております。
英語メニューがあれば、お客様ご自身でメニュー内容をご確認いただけるため、\
スタッフの方が個別にご説明する手間も省けます。」

Output ONLY the Japanese text. No romanji, no furigana, no explanations, no markdown."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def translate_reply(
    english_text: str,
    *,
    business_name: str | None = None,
    model: str = "google/gemini-2.0-flash-001",
) -> str:
    """Translate an English reply into natural Japanese business email text.

    Args:
        english_text: The English text to translate.
        business_name: Optional restaurant name to address the recipient.
        model: OpenRouter model to use.

    Returns:
        Japanese text that reads as natural business correspondence.

    Raises:
        LLMClientError: If the LLM call fails.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise LLMClientError("OPENROUTER_API_KEY not set")

    user_parts = [english_text]
    if business_name:
        user_parts.insert(0, f"Context: This is a reply to {business_name}.")

    return call_llm(
        model=model,
        system=TRANSLATE_SYSTEM_PROMPT,
        user="\n\n".join(user_parts),
        api_key=api_key,
        max_tokens=2048,
        timeout_seconds=30,
    ).strip()


def validate_translated_reply(japanese_text: str) -> list[str]:
    """Return deterministic 5-pass quality issues for Japanese reply drafts."""
    text = str(japanese_text or "").strip()
    issues: list[str] = []
    if not text:
        return ["empty_text"]

    _validate_grammar(text, issues)
    _validate_naturalness(text, issues)
    _validate_politeness(text, issues)
    _validate_tone(text, issues)
    _validate_full_email(text, issues)
    return issues


def _non_empty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _validate_grammar(text: str, issues: list[str]) -> None:
    for line in _non_empty_lines(text):
        if _is_structural_line(line):
            continue
        if line.endswith(("る", "だ", "である")):
            issues.append(f"grammar_plain_ending:{line[-12:]}")
        if line.endswith(("。", "！", "？", "ます", "します", "いたします", "です")):
            continue
        if "。" not in line and len(line) <= 28:
            continue
        issues.append(f"grammar_sentence_ending:{line[-12:]}")


def _is_structural_line(line: str) -> bool:
    return (
        line == "Chris（クリス）"
        or line.endswith("ご担当者様")
        or "@" in line
        or line.startswith("http://")
        or line.startswith("https://")
    )


def _validate_naturalness(text: str, issues: list[str]) -> None:
    translated_phrases = {
        "分かる": "use_伝わる_or_ご確認いただける",
        "分かります": "use_伝わる_or_ご確認いただける",
        "問題": "avoid_problem_framing",
    }
    for phrase, code in translated_phrases.items():
        if phrase in text:
            issues.append(f"naturalness:{code}:{phrase}")


def _validate_politeness(text: str, issues: list[str]) -> None:
    for casual in ("だね", "してる", "だよ", "じゃ"):
        if casual in text:
            issues.append(f"casual_form:{casual}")
    for stiff in ("謹んで", "拝察", "伏して"):
        if stiff in text:
            issues.append(f"stiff_form:{stiff}")
    for plain_sender_action in ("作ります", "提案する"):
        if plain_sender_action in text:
            issues.append(f"sender_action_not_humble:{plain_sender_action}")

    for term in ("案内", "担当者様", "興味", "検討", "連絡", "自身", "希望", "返信"):
        for match in re.finditer(term, text):
            start = match.start()
            before = text[max(0, start - 1):start]
            quoted = start > 0 and text[start - 1:start] == "「"
            if before not in {"ご", "御"} and not quoted:
                issues.append(f"missing_go_prefix:{term}")
                break


def _validate_tone(text: str, issues: list[str]) -> None:
    for phrase in (
        "売上",
        "収入",
        "売上高",
        "利益",
        "お客様を逃す",
        "機会損失",
        "ロス",
        "問題があります",
        "課題がある",
        "困っている",
        "悩み",
    ):
        if phrase in text:
            issues.append(f"negative_or_revenue_framing:{phrase}")
    if "AI" in text or "自動化" in text or "automation" in text.lower():
        issues.append("internal_tool_or_ai_mention")


def _validate_full_email(text: str, issues: list[str]) -> None:
    lines = _non_empty_lines(text)
    if not lines or lines[-1] != "Chris（クリス）":
        issues.append("signoff_must_be_chris_with_katakana")
    if "Chris\n" in text or text.endswith("\nChris") or lines[-1:] == ["Chris"]:
        issues.append("plain_chris_signoff")
    if len(lines) > 2 and "\n\n" not in text:
        issues.append("missing_paragraph_breaks")
    if "今後このようなご案内が不要でしたら" in text and "どうぞよろしくお願いいたします。" not in text:
        issues.append("missing_standard_closing")

    scrubbed = text
    for allowed in ("Chris", "WebRefurb", "webrefurb.com", "chris@webrefurb.com"):
        scrubbed = scrubbed.replace(allowed, "")
    leaked = sorted(set(re.findall(r"[A-Za-z][A-Za-z0-9._%+-]*", scrubbed)))
    if leaked:
        issues.append("english_leak:" + ",".join(leaked[:5]))
