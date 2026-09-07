"""Explicit, endpoint-scoped AI configuration without background model calls."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, SecretStr

from joblookup.config import Settings, save_local_overrides
from joblookup.events import EventBus
from joblookup.llm import presets
from joblookup.llm.base import ChatMessage
from joblookup.llm.openai_compat import is_local
from joblookup.llm.registry import build_provider
from joblookup.server.jobs import Job, manager
from joblookup.services import secrets


class ConnectionInput(BaseModel):
    provider: Literal["vscode", "copilot_cli", "openai_compat", "anthropic"]
    preset: str = Field(default="custom", max_length=80)
    base_url: str = Field(default="", max_length=2048)
    model: str = Field(default="", max_length=200)
    api_key: SecretStr | None = None
    clear_key: bool = False


def connection_details(settings: Settings) -> dict[str, Any]:
    key = settings.llm.provider
    config = getattr(settings.llm, key, settings.llm.vscode)
    base = str(getattr(config, "base_url", "") or "")
    environment = str(getattr(config, "api_key_env", "") or "")
    return {
        "provider": key,
        "preset": getattr(config, "preset", "anthropic" if key == "anthropic" else ""),
        "base_url": base,
        "model": getattr(config, "model", "") or "",
        "key_set": bool(secrets.llm_key(environment, base)) if environment else False,
        "presets": presets.as_dicts(),
        "local_matching": True,
    }


def build_router(
    settings_getter: Callable[[], Settings], reload_settings: Callable[[], Settings]
) -> APIRouter:
    router = APIRouter(prefix="/api/connections")

    @router.get("")
    def connection() -> dict[str, Any]:
        return connection_details(settings_getter())

    @router.get("/vscode/models")
    def bridge_models() -> dict[str, Any]:
        settings = settings_getter().model_copy(deep=True)
        settings.llm.vscode.model = None
        status = build_provider(settings.llm, "vscode").status()
        models = sorted({name for name in status.models if name}, key=str.casefold)
        return {
            "models": models,
            "default_model": status.active_model if status.active_model in models else "",
            "available": status.available,
            "detail": status.detail,
        }

    @router.put("")
    def update_connection(body: ConnectionInput) -> dict[str, Any]:
        patch: dict[str, Any] = {"llm": {"provider": body.provider, "auto": False}}
        selected: dict[str, Any] = {"model": body.model.strip() or None}
        secret_name = ""
        if body.provider in {"openai_compat", "anthropic"}:
            preset = presets.get(body.preset)
            if not preset or preset.provider != body.provider:
                raise HTTPException(400, "Choose a valid provider preset.")
            base_url = (body.base_url.strip() or preset.base_url).rstrip("/")
            try:
                address = urlsplit(base_url)
                valid = (
                    address.scheme in {"http", "https"}
                    and address.hostname
                    and not (
                        address.username or address.password or address.query or address.fragment
                    )
                )
                if not valid or (address.scheme == "http" and not is_local(base_url)):
                    raise ValueError
            except ValueError:
                raise HTTPException(
                    400,
                    "Use an HTTPS endpoint, or HTTP for a local model; "
                    "exclude credentials and query strings.",
                ) from None
            if not body.model.strip():
                raise HTTPException(400, "Enter the model or deployment name.")
            selected.update(base_url=base_url, api_key_env=preset.api_key_env)
            if body.provider == "openai_compat":
                selected.update(preset=preset.key, auth_style=preset.auth_style)
            secret_name = secrets.llm_secret_name(preset.api_key_env, base_url)
        patch["llm"][body.provider] = selected
        save_local_overrides(patch)
        if secret_name and (body.clear_key or (body.api_key and body.api_key.get_secret_value())):
            secrets.set(secret_name, "" if body.clear_key else body.api_key.get_secret_value())
        return connection_details(reload_settings())

    @router.post("/test")
    def test_connection() -> dict[str, Any]:
        settings = settings_getter().model_copy(deep=True)
        config = getattr(settings.llm, settings.llm.provider)
        config.request_timeout_s = min(config.request_timeout_s, 30)

        def work(bus: EventBus, task: Job) -> dict[str, Any]:
            bus.stage_start("connection", "Testing your selected model")
            provider = build_provider(settings.llm)
            reply = provider.complete(
                [ChatMessage("user", "Reply with the single word ready.")],
                temperature=0,
                max_tokens=16,
            )
            if not reply.strip():
                raise ValueError("The model returned an empty response.")
            return {
                "ok": True,
                "provider": settings.llm.provider,
                "model": getattr(config, "model", "") or "Default model",
                "detail": "Your model returned a response.",
            }

        return {
            "task": manager.submit("connection-test", work, label="Testing AI connection").summary()
        }

    return router
