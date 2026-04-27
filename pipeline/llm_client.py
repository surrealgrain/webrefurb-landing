from __future__ import annotations

import base64
import json
import os
import urllib.request
from typing import Any


def call_llm(
    *,
    model: str,
    system: str,
    user: str,
    api_key: str,
    max_tokens: int = 1024,
    timeout_seconds: int = 30,
) -> str:
    """Thin OpenRouter HTTP wrapper. Returns the text response."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
    }).encode("utf-8")

    request = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://webrefurb-menu.local",
    })

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        data = json.loads(response.read().decode("utf-8"))

    choices = data.get("choices") or []
    if not choices:
        return ""

    message = choices[0].get("message") or {}
    return str(message.get("content") or "")


def call_vision(
    *,
    image_path: str,
    system: str,
    user: str,
    model: str = "google/gemini-2.0-flash-001",
    max_tokens: int = 2048,
    timeout_seconds: int = 60,
) -> str:
    """OpenRouter vision API call with base64-encoded image.

    Sends an image as an inline data URL in the user message content.
    Returns the text response from the model.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    # Read and encode the image
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    # Detect MIME type from extension
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".webp": "image/webp", ".bmp": "image/bmp",
    }
    mime_type = mime_map.get(ext, "image/jpeg")

    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_data}",
                        },
                    },
                ],
            },
        ],
        "max_tokens": max_tokens,
    }).encode("utf-8")

    request = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://webrefurb-menu.local",
    })

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        data = json.loads(response.read().decode("utf-8"))

    choices = data.get("choices") or []
    if not choices:
        return ""

    message = choices[0].get("message") or {}
    return str(message.get("content") or "")
