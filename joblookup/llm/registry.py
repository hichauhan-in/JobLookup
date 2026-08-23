"""Provider selection plus the retry and JSON behaviour every caller wants."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from joblookup.config import LLMConfig, Settings
from joblookup.llm.anthropic import AnthropicProvider
from joblookup.llm.base import (
    JSON_INSTRUCTION,
    ChatMessage,
    LLMError,
    LLMProvider,
    LLMUnavailableError,
    ProviderStatus,
    extract_json,
)
from joblookup.llm.copilot_cli import CopilotCliProvider
from joblookup.llm.openai_compat import OpenAICompatProvider
from joblookup.llm.usage import record as record_usage
from joblookup.llm.vscode_bridge import VSCodeBridgeProvider

PROVIDER_KEYS = ("vscode", "copilot_cli", "openai_compat", "anthropic")

#: Providers offered as top-level choices; the rest sit behind "another provider".
PRIMARY_KEYS = ("vscode", "copilot_cli")


def build_provider(config: LLMConfig, key: str | None = None) -> LLMProvider:
    key = key or config.provider
    if key == "vscode":
        return VSCodeBridgeProvider(config.vscode)
    if key == "copilot_cli":
        return CopilotCliProvider(config.copilot_cli)
    if key == "openai_compat":
        return OpenAICompatProvider(config.openai_compat)
    if key == "anthropic":
        return AnthropicProvider(config.anthropic)
    raise LLMError(f"Unknown LLM provider '{key}'. Choose one of: {', '.join(PROVIDER_KEYS)}")


def all_statuses(config: LLMConfig) -> list[ProviderStatus]:
    """Status of every provider, so the Settings screen can show the options.

    Every probe is a network call or a subprocess, and one unreachable endpoint
    used to hold the whole screen for as long as its timeout. They run together
    now, so the wait is the slowest single probe rather than the sum of four.
    """
    with ThreadPoolExecutor(max_workers=len(PROVIDER_KEYS)) as pool:
        futures = {key: pool.submit(_status_of, config, key) for key in PROVIDER_KEYS}
        return [futures[key].result() for key in PROVIDER_KEYS]


def _status_of(config: LLMConfig, key: str) -> ProviderStatus:
    try:
        return build_provider(config, key).status()
    except Exception as exc:  # noqa: BLE001
        return ProviderStatus(key, key, False, str(exc))


class LLMClient:
    """A provider wrapped in the retry and JSON-coercion logic the pipeline needs.

    Matching makes many calls and any one of them can come back as prose instead
    of JSON, or hit a transient rate limit. Handling that here keeps the scorer
    readable.

    It is also the one place every request passes through, which makes it the
    right place to count what those requests cost.
    """

    def __init__(
        self,
        provider: LLMProvider,
        *,
        json_retries: int = 2,
        purpose: str = "other",
    ) -> None:
        self.provider = provider
        self.json_retries = max(0, json_retries)
        #: What the next calls are for, so usage can be attributed.
        self.purpose = purpose

    @classmethod
    def from_settings(cls, settings: Settings, provider_key: str | None = None) -> LLMClient:
        return cls(
            build_provider(settings.llm, provider_key),
            json_retries=settings.llm.json_retries,
        )

    def for_purpose(self, purpose: str) -> LLMClient:
        """The same provider, with calls attributed to a different job."""
        clone = LLMClient(self.provider, json_retries=self.json_retries, purpose=purpose)
        return clone

    def _note(self, messages: list[ChatMessage], reply: str) -> None:
        record_usage(
            self.purpose,
            prompt="\n".join(message.content for message in messages),
            reply=reply,
            model=getattr(self.provider, "last_model", "") or "",
        )

    @property
    def key(self) -> str:
        return self.provider.key

    @property
    def model(self) -> str:
        return self.provider.status().active_model

    def status(self) -> ProviderStatus:
        return self.provider.status()

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        messages = [ChatMessage("system", system), ChatMessage("user", user)]
        reply = self._with_retry(
            lambda: self.provider.complete(messages, temperature=temperature, max_tokens=max_tokens)
        )
        self._note(messages, reply)
        return reply

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> Any:
        """Ask for JSON and keep asking until it parses (or attempts run out)."""
        system_prompt = f"{system}\n\n{JSON_INSTRUCTION}"
        messages = [ChatMessage("system", system_prompt), ChatMessage("user", user)]

        last_error: Exception | None = None
        for attempt in range(self.json_retries + 1):
            attempt_messages = messages
            try:
                raw = self._with_retry(
                    lambda payload=attempt_messages: self.provider.complete(
                        payload,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        expect_json=True,
                    )
                )
                # Retries are counted too: a reply that would not parse still
                # cost what it cost.
                self._note(attempt_messages, raw)
                return extract_json(raw)
            except LLMUnavailableError:
                raise
            except LLMError as exc:
                last_error = exc
                if attempt >= self.json_retries:
                    break
                messages = [
                    ChatMessage("system", system_prompt),
                    ChatMessage("user", user),
                    ChatMessage(
                        "user",
                        "Your previous reply could not be used. Everything needed is "
                        "in the message above — do not ask for more input. Reply with "
                        "one raw JSON object starting with { and ending with }, and "
                        "nothing else: no prose, no apology, no markdown fence.",
                    ),
                ]
        raise LLMError(str(last_error) if last_error else "The model did not return JSON.")

    def embed(self, texts: list[str], *, model: str = "") -> list[list[float]]:
        """Vectors, when the active provider can produce them.

        Copilot cannot, and that is fine — the caller falls back to lexical
        recall rather than treating this as an error the user must fix.
        """
        embedder = getattr(self.provider, "embed", None)
        if embedder is None:
            raise LLMUnavailableError(
                f"{self.provider.label} does not provide embeddings. "
                "Recall will use keyword scoring instead."
            )
        return embedder(texts, model=model)

    @property
    def supports_embeddings(self) -> bool:
        return hasattr(self.provider, "embed")

    def _with_retry(self, call, attempts: int = 3):
        """Retry transient failures with a short backoff.

        A missing or unconfigured provider is not transient, so it fails fast —
        the user needs to go and fix something.
        """
        delay = 1.5
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                return call()
            except LLMUnavailableError:
                raise
            except LLMError as exc:
                last_error = exc
                if attempt == attempts - 1:
                    break
                time.sleep(delay)
                delay *= 2
        raise last_error if last_error else LLMError("The model request failed.")
