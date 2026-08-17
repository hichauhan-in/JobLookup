"""Anthropic Claude.

Claude has its own request shape — a top-level ``system`` string rather than a
system message, and ``max_tokens`` is mandatory — so it gets its own adapter
instead of being bent into the OpenAI-compatible one.

Listed for completeness. Nothing in JobLookup requires it: the default setup
uses the GitHub Copilot seat you already have and never asks for a paid key.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from joblookup.config import AnthropicConfig
from joblookup.llm.base import (
    ChatMessage,
    LLMError,
    LLMUnavailableError,
    ProviderStatus,
)

API_VERSION = "2023-06-01"
SETUP_HINT = (
    "Set the environment variable named by llm.anthropic.api_key_env to your "
    "Anthropic API key before starting JobLookup."
)


class AnthropicProvider:
    key = "anthropic"
    label = "Anthropic Claude"

    def __init__(self, config: AnthropicConfig) -> None:
        self.config = config

    def _api_key(self) -> str:
        return os.environ.get(self.config.api_key_env, "").strip()

    def _headers(self) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "x-api-key": self._api_key(),
            "anthropic-version": API_VERSION,
        }

    def status(self) -> ProviderStatus:
        if not self._api_key():
            return ProviderStatus(
                self.key,
                self.label,
                False,
                f"Environment variable {self.config.api_key_env} is not set.",
                setup_hint=SETUP_HINT,
                needs_paid_key=True,
            )
        base = self.config.base_url.rstrip("/")
        try:
            response = httpx.get(f"{base}/v1/models", headers=self._headers(), timeout=8.0)
        except Exception as exc:  # noqa: BLE001
            return ProviderStatus(
                self.key,
                self.label,
                False,
                f"Could not reach {base}: {exc}",
                setup_hint=SETUP_HINT,
                needs_paid_key=True,
            )
        if response.status_code >= 400:
            return ProviderStatus(
                self.key,
                self.label,
                True,
                f"Configured ({base}); model listing unavailable.",
                active_model=self.config.model,
                needs_paid_key=True,
            )
        models = [
            str(item.get("id")) for item in response.json().get("data") or [] if item.get("id")
        ]
        return ProviderStatus(
            self.key,
            self.label,
            True,
            f"Connected to {base}",
            models=sorted(models),
            active_model=self.config.model,
            needs_paid_key=True,
        )

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        expect_json: bool = False,
    ) -> str:
        if not self._api_key():
            raise LLMUnavailableError(f"Environment variable {self.config.api_key_env} is not set.")

        system = "\n\n".join(m.content.strip() for m in messages if m.role == "system").strip()
        turns = [
            {"role": "assistant" if m.role == "assistant" else "user", "content": m.content}
            for m in messages
            if m.role != "system" and m.content.strip()
        ]
        if not turns:
            raise LLMError("No user message was supplied.")

        body: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature,
            "messages": turns,
        }
        if system:
            body["system"] = system

        url = f"{self.config.base_url.rstrip('/')}/v1/messages"
        try:
            response = httpx.post(
                url,
                headers=self._headers(),
                json=body,
                timeout=httpx.Timeout(15.0, read=self.config.request_timeout_s),
            )
        except httpx.RequestError as exc:
            raise LLMUnavailableError(f"Could not reach {url}: {exc}") from exc

        if response.status_code >= 400:
            raise LLMError(f"Anthropic returned {response.status_code}: {response.text[:400]}")

        blocks = response.json().get("content") or []
        text = "".join(
            str(block.get("text") or "") for block in blocks if block.get("type") == "text"
        )
        if not text.strip():
            raise LLMError("Anthropic returned an empty response.")
        return text
