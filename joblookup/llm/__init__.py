"""The language model layer: one interface, several ways to answer it."""

from __future__ import annotations

from joblookup.llm.base import (
    ChatMessage,
    EmbeddingProvider,
    LLMError,
    LLMProvider,
    LLMUnavailableError,
    ProviderStatus,
    extract_json,
)
from joblookup.llm.registry import (
    PRIMARY_KEYS,
    PROVIDER_KEYS,
    LLMClient,
    all_statuses,
    build_provider,
)

__all__ = [
    "PRIMARY_KEYS",
    "PROVIDER_KEYS",
    "ChatMessage",
    "EmbeddingProvider",
    "LLMClient",
    "LLMError",
    "LLMProvider",
    "LLMUnavailableError",
    "ProviderStatus",
    "all_statuses",
    "build_provider",
    "extract_json",
]
