from __future__ import annotations

import base64
import json
import os
import socket
import time
import urllib.request
from urllib.error import HTTPError, URLError
from typing import Any


class LLMClientError(RuntimeError):
    """Raised when an LLM request fails after retrying."""


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
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
    }).encode("utf-8")
    return _extract_text(
        _request_openrouter(
            payload=payload,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
    )


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
        raise LLMClientError("OPENROUTER_API_KEY not set")

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
    return _extract_text(
        _request_openrouter(
            payload=payload,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
    )


def _request_openrouter(*, payload: bytes, api_key: str, timeout_seconds: int) -> dict[str, Any]:
    url = "https://openrouter.ai/api/v1/chat/completions"
    request = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://webrefurb-menu.local",
    })

    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if attempt < attempts and exc.code in {408, 409, 425, 429, 500, 502, 503, 504}:
                _sleep_before_retry(attempt)
                continue
            raise LLMClientError(f"OpenRouter request failed with HTTP {exc.code}") from exc
        except (URLError, TimeoutError, socket.timeout) as exc:
            if attempt < attempts:
                _sleep_before_retry(attempt)
                continue
            raise LLMClientError("OpenRouter request failed after retries") from exc
        except json.JSONDecodeError as exc:
            raise LLMClientError("OpenRouter returned invalid JSON") from exc

    raise LLMClientError("OpenRouter request failed after retries")


def _extract_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise LLMClientError("OpenRouter returned no choices")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict)
        ]
        joined = "".join(parts).strip()
        if joined:
            return joined
    raise LLMClientError("OpenRouter returned empty content")


def _sleep_before_retry(attempt: int) -> None:
    time.sleep(0.5 * (2 ** (attempt - 1)))
