"""The adapter registry and the source table it keeps in sync.

Adapters are discovered from code; the database holds only what the user chose —
enabled or not, the risk acknowledgement, the per-source configuration and the
outcome of the last run. That split means adding a source is a code change and
never a migration, and that a user's choices survive one.
"""

from __future__ import annotations

import json
from typing import Any

from joblookup.config import Settings
from joblookup.db import session as db
from joblookup.services import secrets
from joblookup.sources import regions
from joblookup.sources.ats import boards
from joblookup.sources.base import FetchContext, SourceAdapter, as_list
from joblookup.sources.tier_a import feeds, keyed
from joblookup.sources.tier_b.portal import PortalAdapter, build_adapters

#: Enabled the first time the database is created. Keyless, free and permitted.
DEFAULT_ENABLED = {"remoteok", "remotive", "arbeitnow", "himalayas", "themuse"}

_cache: dict[str, SourceAdapter] | None = None


def all_adapters(refresh: bool = False) -> dict[str, SourceAdapter]:
    global _cache
    if _cache is not None and not refresh:
        return _cache

    adapters: dict[str, SourceAdapter] = {}
    for cls in (*feeds.ADAPTERS, *keyed.ADAPTERS, *boards.ADAPTERS):
        instance = cls()
        adapters[instance.key] = instance
    for portal in build_adapters():
        adapters[portal.key] = portal

    _cache = adapters
    return adapters


def get_adapter(key: str) -> SourceAdapter | None:
    return all_adapters().get(key)


def sync_source_table() -> None:
    """Insert any adapter not in the database yet. Never overwrites user choices."""
    with db.transaction() as conn:
        existing = {row["key"] for row in conn.execute("SELECT key FROM source").fetchall()}
        for key, adapter in all_adapters(refresh=True).items():
            if key in existing:
                # Keep the display name current when an adapter is renamed.
                conn.execute(
                    "UPDATE source SET name = ?, tier = ?, requires_key = ? WHERE key = ?",
                    (adapter.name, adapter.tier, int(adapter.requires_key), key),
                )
                continue
            conn.execute(
                "INSERT INTO source (key, name, tier, enabled, requires_key, config) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    key,
                    adapter.name,
                    adapter.tier,
                    int(key in DEFAULT_ENABLED),
                    int(adapter.requires_key),
                    json.dumps({}),
                ),
            )


def source_config(key: str) -> dict[str, Any]:
    row = (
        db.connect().execute("SELECT config, risk_ack FROM source WHERE key = ?", (key,)).fetchone()
    )
    if row is None:
        return {}
    config = db.loads(row["config"], {})
    config["risk_ack"] = bool(row["risk_ack"])
    return config


def context_for(
    key: str,
    settings: Settings,
    *,
    queries: list[str] | None = None,
    locations: list[str] | None = None,
    log: Any = None,
    cancelled: Any = None,
    config: dict[str, Any] | None = None,
    secret: Any = None,
) -> FetchContext:
    return FetchContext(
        settings=settings,
        #: Callers that already hold the row pass it in. Re-reading it is a
        #: query per source, and the Sources screen asks about thirty.
        config=source_config(key) if config is None else config,
        queries=queries or [],
        locations=locations or [],
        secret=secret or secrets.get,
        log=log or (lambda message: None),
        cancelled=cancelled or (lambda: False),
    )


def _cached_secrets() -> Any:
    """``secrets.get`` that asks the credential store once per name.

    Readiness checks ask for the same handful of keys repeatedly, and on Windows
    each miss is a cross-process call into Credential Manager. Within one screen
    refresh the answer cannot change, so caching it is free.
    """
    seen: dict[str, str] = {}

    def get(name: str) -> str:
        if name not in seen:
            seen[name] = secrets.get(name)
        return seen[name]

    return get


def list_sources(settings: Settings) -> list[dict[str, Any]]:
    """Source rows enriched with live readiness from the adapter itself."""
    adapters = all_adapters()
    rows = db.connect().execute("SELECT * FROM source ORDER BY tier, name").fetchall()
    secret = _cached_secrets()

    result: list[dict[str, Any]] = []
    for row in rows:
        adapter = adapters.get(row["key"])
        entry = dict(row)
        entry["config"] = db.loads(entry.get("config"), {})
        entry["enabled"] = bool(entry["enabled"])
        entry["requires_key"] = bool(entry["requires_key"])
        entry["risk_ack"] = bool(entry["risk_ack"])

        if adapter is None:
            entry.update(
                ready=False,
                blocked_reason="This source no longer exists in this version.",
                homepage="",
                description="",
                fields=[],
                guide={},
                is_tier_b=row["tier"] == "b",
            )
            result.append(entry)
            continue

        context = context_for(
            row["key"],
            settings,
            config={**entry["config"], "risk_ack": entry["risk_ack"]},
            secret=secret,
        )
        ready, reason = adapter.is_configured(context)
        entry.update(
            ready=ready,
            blocked_reason=reason,
            homepage=adapter.homepage,
            description=adapter.description,
            fields=[field.to_dict() for field in adapter.config_fields()],
            guide=adapter.setup_guide().to_dict(),
            is_tier_b=adapter.tier == "b",
        )
        if isinstance(adapter, PortalAdapter):
            entry["login_url"] = adapter.login_url
            entry["selector_file"] = adapter.selector_file
        result.append(entry)
    return result


def enabled_adapters() -> list[SourceAdapter]:
    adapters = all_adapters()
    rows = db.connect().execute("SELECT key FROM source WHERE enabled = 1").fetchall()
    return [adapters[row["key"]] for row in rows if row["key"] in adapters]


# --- country packs ------------------------------------------------------------
def region_view(
    code: str, settings: Settings, *, sources: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """A country pack joined to the live state of each source it recommends.

    ``sources`` is there for the Sources screen, which has already built that
    list and would otherwise pay for it twice in one request.
    """
    region = regions.resolve(code)
    rows = {row["key"]: row for row in (sources if sources is not None else list_sources(settings))}
    picks = []
    for pick in region.picks:
        row = rows.get(pick.key)
        if row is None:
            continue
        companies = as_list(row.get("config", {}).get("slugs"))
        picks.append(
            {
                **row,
                "why": pick.why,
                "preset": dict(pick.config),
                "companies": companies,
                "company_count": len(companies),
            }
        )
    return {**region.to_dict(), "picks": picks}


def apply_region(
    code: str,
    settings: Settings,
    *,
    companies: int = 60,
    replace: bool = True,
) -> dict[str, Any]:
    """Set a pack up completely, and report exactly what it did.

    "Completely" is the point. Enabling a company board without giving it any
    companies leaves it switched on and unable to run, which reads as a button
    that did not work. So the boards in a pack are filled from the verified
    catalogue, ranked for this country and this profile, in the same action.

    Nothing needing a login is ever enabled here: that stays a deliberate,
    separate act.
    """
    from joblookup import store
    from joblookup.services import suggest

    # Writing to rows that do not exist yet silently does nothing, so make sure
    # every adapter has one before configuring any of them.
    sync_source_table()
    region = regions.resolve(code)
    adapters = all_adapters()
    pack_boards = [
        pick.key
        for pick in region.picks
        if (adapter := adapters.get(pick.key)) is not None and adapter.tier == "ats"
    ]

    # Companies are chosen for the country the pack is for, not for wherever the
    # settings happened to point when the button was pressed.
    for_region = settings.model_copy(deep=True)
    for_region.search.region = region.code
    profile = store.get_profile().get("data") or {}
    picked = (
        suggest.rank_companies(profile, for_region, limit=companies, boards=pack_boards)
        if pack_boards
        else []
    )
    by_board = suggest.grouped_slugs(picked)

    turned_on: list[dict[str, Any]] = []
    needs_setup: list[dict[str, str]] = []
    needs_login: list[str] = []

    for pick in region.picks:
        adapter = adapters.get(pick.key)
        if adapter is None:
            continue

        patch: dict[str, Any] = dict(pick.config)
        added = by_board.get(pick.key) or []
        if added:
            existing = [] if replace else as_list(source_config(pick.key).get("slugs"))
            patch["slugs"] = list(dict.fromkeys([*existing, *added]))
            # Provenance, so the sections below can say where a list came from
            # and the user can tell the pack's choices from their own.
            patch["from_region"] = region.code
        if patch:
            update_config(pick.key, patch)

        if adapter.tier == "b":
            needs_login.append(adapter.name)
            continue

        ready, reason = adapter.is_configured(context_for(pick.key, settings))
        if ready:
            set_enabled(pick.key, True)
            turned_on.append(
                {
                    "key": pick.key,
                    "name": adapter.name,
                    "companies": len(patch.get("slugs") or []),
                }
            )
        else:
            needs_setup.append({"name": adapter.name, "reason": reason, "key": pick.key})

    return {
        "region": region.code,
        "name": region.name,
        "enabled": turned_on,
        "needs_setup": needs_setup,
        "needs_login": needs_login,
        "companies": [entry.to_dict() for entry in picked],
        "company_count": len(picked),
    }


def clear_region(code: str) -> dict[str, Any]:
    """Undo what a pack configured, leaving anything the user added themselves.

    Only the companies the pack wrote are removed, which is why the slugs it
    added are recorded alongside them.
    """
    region = regions.resolve(code)
    adapters = all_adapters()
    cleared: list[str] = []

    for pick in region.picks:
        adapter = adapters.get(pick.key)
        if adapter is None:
            continue
        config = source_config(pick.key)
        if config.get("from_region") != region.code:
            continue
        update_config(pick.key, {"slugs": [], "from_region": ""})
        set_enabled(pick.key, False)
        cleared.append(adapter.name)

    return {"region": region.code, "name": region.name, "cleared": cleared}


def set_enabled(key: str, enabled: bool) -> None:
    with db.transaction() as conn:
        conn.execute("UPDATE source SET enabled = ? WHERE key = ?", (int(enabled), key))


def set_risk_ack(key: str, acknowledged: bool) -> None:
    with db.transaction() as conn:
        conn.execute("UPDATE source SET risk_ack = ? WHERE key = ?", (int(acknowledged), key))


def update_config(key: str, patch: dict[str, Any]) -> dict[str, Any]:
    current = db.loads(
        (
            db.connect().execute("SELECT config FROM source WHERE key = ?", (key,)).fetchone()
            or {"config": "{}"}
        )["config"],
        {},
    )
    current.update(patch)
    with db.transaction() as conn:
        conn.execute(
            "UPDATE source SET config = ? WHERE key = ?",
            (json.dumps(current, ensure_ascii=False), key),
        )
    return current


def record_result(key: str, status: str, count: int, error: str = "") -> None:
    with db.transaction() as conn:
        conn.execute(
            "UPDATE source SET last_run_at = datetime('now'), last_status = ?, "
            "last_count = ?, last_error = ? WHERE key = ?",
            (status, count, error, key),
        )
