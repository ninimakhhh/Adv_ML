"""
LLMClient — single abstraction over the DeepSeek (OpenAI-compatible) API.

To swap providers in the future, edit only this file.

Usage:
    from shared.llm_client import LLMClient

    llm = LLMClient()
    result = llm.chat([{"role": "user", "content": "Hello"}])
    # returns str

    data = llm.chat(messages, response_format="json")
    # returns dict (parsed) or {"error": ..., "raw": ...} on failure
"""

from __future__ import annotations

import json
import logging
import time
from functools import lru_cache
from typing import Any

from openai import OpenAI, APIStatusError, APIConnectionError, RateLimitError

from shared.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    require_deepseek_api_key,
)

logger = logging.getLogger(__name__)

_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY = 1.0  # seconds; doubles each attempt


class LLMClient:
    """Thin wrapper around the DeepSeek chat-completions endpoint."""

    def __init__(self) -> None:
        # Do not validate the key here — instantiation must not fail just
        # because the key is missing. The error is raised lazily on first call.
        self._client: OpenAI | None = None
        self._model = DEEPSEEK_MODEL

    def _ensure_client(self) -> OpenAI:
        if self._client is None:
            api_key = require_deepseek_api_key()
            self._client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        return self._client

    def chat(
        self,
        messages: list[dict[str, str]],
        response_format: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str | dict[str, Any]:
        if response_format == "json":
            messages = _inject_json_instruction(messages)

        extra: dict[str, Any] = {}
        if response_format == "json":
            extra["response_format"] = {"type": "json_object"}

        raw = self._call_with_retry(messages, temperature, max_tokens, extra)

        if response_format == "json":
            return _parse_json(raw)
        return raw

    def _call_with_retry(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        extra: dict,
    ) -> str:
        last_exc: Exception | None = None
        client = self._ensure_client()
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                response = client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **extra,
                )
                return response.choices[0].message.content or ""
            except (RateLimitError, APIStatusError) as exc:
                if isinstance(exc, APIStatusError) and exc.status_code < 500:
                    raise
                last_exc = exc
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning("LLMClient: transient error (attempt %d/%d), retrying in %.1fs — %s",
                               attempt + 1, _RETRY_ATTEMPTS, delay, exc)
                time.sleep(delay)
            except APIConnectionError as exc:
                last_exc = exc
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning("LLMClient: connection error (attempt %d/%d), retrying in %.1fs — %s",
                               attempt + 1, _RETRY_ATTEMPTS, delay, exc)
                time.sleep(delay)
            except Exception as exc:
                logger.error("LLMClient: unexpected error — %s", exc)
                raise

        logger.error("LLMClient: all %d attempts failed — %s", _RETRY_ATTEMPTS, last_exc)
        raise last_exc  # type: ignore[misc]


def _inject_json_instruction(messages: list[dict]) -> list[dict]:
    json_instruction = {
        "role": "system",
        "content": (
            "You must respond with ONLY valid JSON — no markdown fences, "
            "no explanatory text, no trailing commas. The response must be "
            "parseable by json.loads()."
        ),
    }
    if messages and messages[0]["role"] == "system":
        merged = dict(messages[0])
        merged["content"] = merged["content"] + "\n\n" + json_instruction["content"]
        return [merged] + list(messages[1:])
    return [json_instruction] + list(messages)


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("LLMClient: JSON parse failed — %s | raw: %.200s", exc, raw)
        return {"error": str(exc), "raw": raw[:500]}


# ---------------------------------------------------------------------------
# Convenience helpers — used by scripts and ticket_routing module
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_deepseek_client() -> OpenAI:
    api_key = require_deepseek_api_key()
    return OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)


# Alias for backwards compatibility
get_anthropic_client = get_deepseek_client
