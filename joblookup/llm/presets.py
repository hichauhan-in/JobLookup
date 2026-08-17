"""Ready-made settings for the endpoints people actually use.

Every one of these speaks the OpenAI chat-completions shape, so they are the same
provider with different values — except Anthropic, which has its own adapter.
Selecting a preset fills in the URL, the auth style and the environment variable
name, so nobody has to know that Azure sends the key in ``api-key`` while
everyone else uses a bearer token.

The free and local options come first on purpose. JobLookup's default route is
the GitHub Copilot seat you already have; nothing in this list is ever required.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Preset:
    key: str
    label: str
    #: The provider implementation this preset configures.
    provider: str = "openai_compat"
    base_url: str = ""
    auth_style: str = "bearer"
    api_key_env: str = "JOBLOOKUP_LLM_API_KEY"
    suggested_models: tuple[str, ...] = ()
    #: Embedding models this endpoint is likely to have. Blank means it has none,
    #: and recall stays lexical.
    suggested_embed_models: tuple[str, ...] = ()
    #: True when the URL contains something only the user knows (a tenant, a host).
    needs_base_url: bool = False
    #: True when using this costs money the user has to supply.
    needs_paid_key: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "provider": self.provider,
            "base_url": self.base_url,
            "auth_style": self.auth_style,
            "api_key_env": self.api_key_env,
            "suggested_models": list(self.suggested_models),
            "suggested_embed_models": list(self.suggested_embed_models),
            "needs_base_url": self.needs_base_url,
            "needs_paid_key": self.needs_paid_key,
            "note": self.note,
        }


PRESETS: tuple[Preset, ...] = (
    Preset(
        key="ollama",
        label="Ollama (runs locally, free)",
        base_url="http://127.0.0.1:11434/v1",
        suggested_models=("llama3.1:8b", "qwen2.5:14b", "mistral-nemo", "gemma3:12b"),
        suggested_embed_models=("bge-m3", "nomic-embed-text", "all-minilm"),
        note="Nothing leaves the machine and there is no key to buy. Also the only "
        "common way to get real embeddings for free, which upgrades recall from "
        "keyword scoring to vector similarity. Needs a reasonable amount of RAM.",
    ),
    Preset(
        key="lmstudio",
        label="LM Studio (runs locally, free)",
        base_url="http://127.0.0.1:1234/v1",
        suggested_models=("local-model",),
        suggested_embed_models=("text-embedding-nomic-embed-text-v1.5",),
        note="Start the local server from LM Studio's Developer tab. The model name "
        "is whatever you loaded there.",
    ),
    Preset(
        key="azure_openai",
        label="Azure OpenAI",
        auth_style="api-key",
        api_key_env="JOBLOOKUP_AZURE_OPENAI_KEY",
        needs_base_url=True,
        needs_paid_key=True,
        suggested_models=("gpt-4o", "gpt-4o-mini"),
        suggested_embed_models=("text-embedding-3-small", "text-embedding-3-large"),
        note="Use the v1 endpoint: https://<resource>.openai.azure.com/openai/v1, and the "
        "model name is your deployment name. Usually the right answer for a governed "
        "corporate setup, because the data stays in your tenant.",
    ),
    Preset(
        key="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key_env="JOBLOOKUP_OPENAI_API_KEY",
        needs_paid_key=True,
        suggested_models=("gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"),
        suggested_embed_models=("text-embedding-3-small", "text-embedding-3-large"),
        note="Pay as you go. Your CV and the job descriptions you match against would "
        "leave the machine.",
    ),
    Preset(
        key="anthropic",
        label="Anthropic Claude",
        provider="anthropic",
        base_url="https://api.anthropic.com",
        api_key_env="JOBLOOKUP_ANTHROPIC_API_KEY",
        needs_paid_key=True,
        suggested_models=("claude-sonnet-4-5", "claude-haiku-4-5"),
        note="Claude uses its own API shape, so JobLookup talks to it directly rather "
        "than through the OpenAI-compatible adapter. It has no embeddings API.",
    ),
    Preset(
        key="gemini",
        label="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key_env="JOBLOOKUP_GEMINI_API_KEY",
        needs_paid_key=True,
        suggested_models=("gemini-2.5-flash", "gemini-2.5-pro"),
        suggested_embed_models=("text-embedding-004",),
        note="Uses Google's OpenAI-compatible endpoint. Has a free tier with low limits.",
    ),
    Preset(
        key="openrouter",
        label="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="JOBLOOKUP_OPENROUTER_API_KEY",
        needs_paid_key=True,
        suggested_models=("openai/gpt-4o-mini", "anthropic/claude-sonnet-4.5"),
        note="One key, many models. Useful for trying providers before committing.",
    ),
    Preset(
        key="custom",
        label="Other OpenAI-compatible endpoint",
        needs_base_url=True,
        note="Any internal gateway or self-hosted server that implements "
        "/chat/completions. Add /embeddings too and vector recall switches itself on.",
    ),
)

BY_KEY: dict[str, Preset] = {preset.key: preset for preset in PRESETS}


def get(key: str) -> Preset | None:
    return BY_KEY.get(key)


def as_dicts() -> list[dict[str, object]]:
    return [preset.to_dict() for preset in PRESETS]
