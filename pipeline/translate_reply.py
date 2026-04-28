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
