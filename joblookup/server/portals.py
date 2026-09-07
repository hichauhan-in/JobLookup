"""Explicit portal access, locally owned browser sessions, and manual imports."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from joblookup import store
from joblookup.config import Settings, save_local_overrides
from joblookup.models import RawJob
from joblookup.services.crawl import profile_queries
from joblookup.sources import registry
from joblookup.sources.base import FetchContext
from joblookup.sources.normalize import normalize, parse_date
from joblookup.sources.tier_b import browser
from joblookup.sources.tier_b.access import portal_link
from joblookup.sources.tier_b.portal import RISK_NOTICE, PortalAdapter


class PortalSwitch(BaseModel):
    enabled: bool


class PortalOptions(BaseModel):
    enabled: bool = True
    acknowledged: bool = False
    access_mode: Literal["session", "public"] = "session"
    extra_terms: list[str] = Field(default_factory=list, max_length=10)


class PostingImport(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    company: str = Field(min_length=1, max_length=200)
    location: str = Field(default="", max_length=300)
    description: str = Field(min_length=80, max_length=100_000)
    url: str = Field(min_length=10, max_length=2048)
    posted_at: str | None = Field(default=None, max_length=50)
    work_mode: Literal["unknown", "remote", "hybrid", "onsite"] = "unknown"
    employment: Literal[
        "unknown", "full-time", "part-time", "contract", "internship", "temporary"
    ] = "unknown"

    @field_validator("title", "company", "description", "url", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


def adapter_for(key: str) -> PortalAdapter:
    adapter = registry.get_adapter(key)
    if not isinstance(adapter, PortalAdapter):
        raise HTTPException(404, "That job portal is not supported.")
    return adapter


def local_only(settings: Settings) -> None:
    if settings.server.multi_user:
        raise HTTPException(400, "Portal sessions can only be used in a local workspace.")


def build_router(
    settings_getter: Callable[[], Settings], reload_settings: Callable[[], Settings]
) -> APIRouter:
    router = APIRouter(prefix="/api/portals")

    @router.get("")
    def portals() -> dict[str, Any]:
        settings = settings_getter()
        titles, locations = profile_queries(settings)
        entries = []
        for row in registry.list_sources(settings):
            if row["tier"] != "b":
                continue
            adapter = adapter_for(row["key"])
            context = FetchContext(
                settings=settings, config=row["config"], queries=titles, locations=locations
            )
            entries.append(
                {
                    **row,
                    "session": browser.session_state(settings, row["key"]),
                    "public_supported": adapter.supports_public,
                    "access_mode": row["config"].get("access_mode", "session"),
                    "search_url": adapter.search_url(context, 0),
                }
            )
        return {
            "portals": entries,
            "enabled": settings.tier_b.enabled,
            "browser": browser.availability(),
            "risk_notice": RISK_NOTICE,
            "local_only": not settings.server.multi_user,
        }

    @router.put("")
    def set_portal_access(body: PortalSwitch) -> dict[str, Any]:
        local_only(settings_getter())
        save_local_overrides({"tier_b": {"enabled": body.enabled}})
        settings = reload_settings()
        return {"enabled": settings.tier_b.enabled}

    @router.put("/{key}")
    def configure_portal(key: str, body: PortalOptions) -> dict[str, Any]:
        adapter = adapter_for(key)
        settings = settings_getter()
        local_only(settings)
        if body.enabled and (not settings.tier_b.enabled or not body.acknowledged):
            raise HTTPException(
                400, "Enable portal access and acknowledge the portal's restrictions first."
            )
        if body.access_mode == "public" and not adapter.supports_public:
            raise HTTPException(
                400, "This connector has no public listing mode. Sign in or import a posting."
            )
        try:
            with browser.session_access(settings, key):
                registry.set_risk_ack(key, body.acknowledged)
                registry.update_config(
                    key,
                    {
                        "access_mode": body.access_mode,
                        "extra_terms": [
                            term.strip()[:150] for term in body.extra_terms if term.strip()
                        ],
                    },
                )
                registry.set_enabled(key, body.enabled)
        except browser.TierBBlocked as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"enabled": body.enabled, "access_mode": body.access_mode}

    @router.delete("/{key}/session")
    def disconnect(key: str) -> dict[str, Any]:
        adapter_for(key)
        settings = settings_getter()
        local_only(settings)
        try:
            browser.clear_session(settings, key)
        except browser.TierBBlocked as exc:
            raise HTTPException(409, str(exc)) from exc
        registry.set_enabled(key, False)
        return {"disconnected": True}

    @router.post("/{key}/import")
    def import_posting(key: str, body: PostingImport) -> dict[str, Any]:
        adapter = adapter_for(key)
        url = portal_link(adapter.homepage, body.url)
        if not url or not body.url.startswith(("https://", "http://")):
            raise HTTPException(400, f"Use an original {adapter.name} posting URL.")
        posted = parse_date(body.posted_at) if body.posted_at else None
        if body.posted_at and not posted:
            raise HTTPException(400, "The posting date could not be read.")
        raw = RawJob(
            source_key=key,
            title=body.title,
            company=body.company,
            description=body.description,
            location=body.location,
            url=url,
            posted_at=posted,
            work_mode=body.work_mode,
            employment=body.employment,
            raw={"portal": key, "access": "manual", "user_supplied": True},
        )
        job_id, created = store.upsert_job(normalize(raw))
        return {"job_id": job_id, "created": created, "access": "manual"}

    return router
