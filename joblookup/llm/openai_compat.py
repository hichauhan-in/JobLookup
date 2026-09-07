"""Any endpoint that speaks the OpenAI chat-completions shape.

Covers a local Ollama or LM Studio server, an internal gateway, Azure OpenAI, or
OpenAI itself. This is also the only provider that can produce embeddings, which
is why vector recall is opportunistic rather than required.

A key, when one is needed, is read from an environment variable rather than
stored in config, so a secret never lands in a YAML file that might be committed
or shared. Local runtimes need no key at all and are not asked for one.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from joblookup.config import OpenAICompatConfig
from joblookup.llm.base import (
    ChatMessage,
    LLMError,
    LLMUnavailableError,
    ProviderStatus,
)
from joblookup.services.secrets import llm_key

SETUP_HINT = (
    "Pick a preset on the Settings screen, or set llm.openai_compat.base_url in "
    "config/local.yaml and put the key in the environment variable named by "
    "llm.openai_compat.api_key_env."
)

#: Hosts that run on the machine and never authenticate.
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0", "host.docker.internal"}


def is_local(base_url: str | None) -> bool:
    if not base_url:
        return False
    try:
        host = urlparse(base_url).hostname or ""
    except ValueError:
        return False
    return host in _LOCAL_HOSTS


class OpenAICompatProvider:
    key = "openai_compat"
    label = "OpenAI-compatible endpoint"

    def __init__(self, config: OpenAICompatConfig) -> None:
        self.config = config

    # --- auth --------------------------------------------------------------
    def _api_key(self) -> str:
        return llm_key(self.config.api_key_env, self._base())

    def _needs_key(self) -> bool:
        return not is_local(self.config.base_url)

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        key = self._api_key()
        if key:
            if self.config.auth_style.lower() == "api-key":
                headers["api-key"] = key
            else:
                headers["authorization"] = f"Bearer {key}"
        return headers

    def _base(self) -> str:
        return (self.config.base_url or "").rstrip("/")

    # --- provider interface ------------------------------------------------
    def status(self) -> ProviderStatus:
        base = self._base()
        if not base:
            return ProviderStatus(
                self.key, self.label, False, "No endpoint configured.", setup_hint=SETUP_HINT
            )
        needs_key = self._needs_key()
        if needs_key and not self._api_key():
            return ProviderStatus(
                self.key,
                self.label,
                False,
                f"Environment variable {self.config.api_key_env} is not set.",
                setup_hint=SETUP_HINT,
                needs_paid_key=True,
            )

        try:
            response = httpx.get(f"{base}/models", headers=self._headers(), timeout=8.0)
            if response.status_code in (401, 403):
                return ProviderStatus(
                    self.key,
                    self.label,
                    False,
                    "The endpoint rejected the API key.",
                    setup_hint="Update your API key in Settings and test again.",
                )
            if response.status_code >= 400:
                # Plenty of gateways expose /chat/completions but not /models;
                # that is not a failure worth reporting as "unavailable".
                return ProviderStatus(
                    self.key,
                    self.label,
                    True,
                    f"Configured ({base}); model listing unavailable.",
                    active_model=self.config.model,
                    supports_embeddings=True,
                    needs_paid_key=needs_key,
                )
            payload: dict[str, Any] = response.json()
            models = [str(item.get("id")) for item in payload.get("data") or [] if item.get("id")]
        except Exception as exc:  # noqa: BLE001
            return ProviderStatus(
                self.key,
                self.label,
                False,
                f"Could not reach {base}: {exc}",
                setup_hint=SETUP_HINT,
                needs_paid_key=needs_key,
            )

        return ProviderStatus(
            self.key,
            self.label,
            True,
            f"Connected to {base}",
            models=sorted(models),
            active_model=self.config.model,
            supports_embeddings=True,
            needs_paid_key=needs_key,
        )

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        expect_json: bool = False,
    ) -> str:
        base = self._require_endpoint()

        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": [message.to_dict() for message in messages],
            "temperature": temperature,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens
        if expect_json:
            body["response_format"] = {"type": "json_object"}

        url = f"{base}/chat/completions"
        timeout = httpx.Timeout(15.0, read=self.config.request_timeout_s)
        try:
            response = httpx.post(url, headers=self._headers(), json=body, timeout=timeout)
            if response.status_code == 400 and expect_json:
                # Not every endpoint supports response_format; retry without it.
                body.pop("response_format", None)
                response = httpx.post(url, headers=self._headers(), json=body, timeout=timeout)
        except httpx.RequestError as exc:
            raise LLMUnavailableError(f"Could not reach {url}: {exc}") from exc

        if response.status_code >= 400:
            raise LLMError(f"Endpoint returned {response.status_code}: {response.text[:400]}")

        payload = response.json()
        content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content")
        if not content:
            raise LLMError("The endpoint returned an empty response.")
        return str(content)

    # --- optional embedding capability -------------------------------------
    def embed(self, texts: list[str], *, model: str = "") -> list[list[float]]:
        """Vectors for ``texts``. Raises rather than degrading silently; the
        caller decides whether to fall back to lexical recall."""
        if not texts:
            return []
        base = self._require_endpoint()
        name = model or self.config.embed_model
        if not name:
            raise LLMUnavailableError("No embedding model is configured for this endpoint.")

        try:
            response = httpx.post(
                f"{base}/embeddings",
                headers=self._headers(),
                json={"model": name, "input": texts},
                timeout=httpx.Timeout(15.0, read=self.config.request_timeout_s),
            )
        except httpx.RequestError as exc:
            raise LLMUnavailableError(f"Could not reach the embeddings endpoint: {exc}") from exc

        if response.status_code >= 400:
            raise LLMError(f"Embeddings returned {response.status_code}: {response.text[:300]}")

        data = response.json().get("data") or []
        vectors = [[float(value) for value in item.get("embedding") or []] for item in data]
        if len(vectors) != len(texts):
            raise LLMError(f"Asked for {len(texts)} embeddings and got {len(vectors)} back.")
        return vectors

    def _require_endpoint(self) -> str:
        base = self._base()
        if not base:
            raise LLMUnavailableError(f"No endpoint configured. {SETUP_HINT}")
        if self._needs_key() and not self._api_key():
            raise LLMUnavailableError(f"Environment variable {self.config.api_key_env} is not set.")
        return base
