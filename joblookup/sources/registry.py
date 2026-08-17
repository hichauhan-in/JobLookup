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
from joblookup.sources.base import FetchContext, SourceAdapter
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
) -> FetchContext:
    return FetchContext(
        settings=settings,
        config=source_config(key),
        queries=queries or [],
        locations=locations or [],
        secret=secrets.get,
        log=log or (lambda message: None),
        cancelled=cancelled or (lambda: False),
    )


def list_sources(settings: Settings) -> list[dict[str, Any]]:
    """Source rows enriched with live readiness from the adapter itself."""
    adapters = all_adapters()
    rows = db.connect().execute("SELECT * FROM source ORDER BY tier, name").fetchall()

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

        context = context_for(row["key"], settings)
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
def region_view(code: str, settings: Settings) -> dict[str, Any]:
    """A country pack joined to the live state of each source it recommends."""
    region = regions.resolve(code)
    rows = {row["key"]: row for row in list_sources(settings)}
    picks = []
    for pick in region.picks:
        row = rows.get(pick.key)
        if row is None:
            continue
        picks.append({**row, "why": pick.why, "preset": dict(pick.config)})
    return {**region.to_dict(), "picks": picks}


def apply_region(code: str, settings: Settings) -> dict[str, Any]:
    """Turn on everything in a pack that can run right now, and say what cannot.

    Country settings are filled in for every pick, because they are correct
    whether or not the source is on yet. Nothing needing a login is ever enabled
    here: that stays a deliberate, separate act.
    """
    region = regions.resolve(code)
    adapters = all_adapters()
    turned_on: list[str] = []
    needs_setup: list[dict[str, str]] = []
    needs_login: list[str] = []

    for pick in region.picks:
        adapter = adapters.get(pick.key)
        if adapter is None:
            continue
        if pick.config:
            update_config(pick.key, pick.config)
        if adapter.tier == "b":
            needs_login.append(adapter.name)
            continue
        ready, reason = adapter.is_configured(context_for(pick.key, settings))
        if ready:
            set_enabled(pick.key, True)
            turned_on.append(adapter.name)
        else:
            needs_setup.append({"name": adapter.name, "reason": reason, "key": pick.key})

    return {
        "region": region.code,
        "name": region.name,
        "enabled": turned_on,
        "needs_setup": needs_setup,
        "needs_login": needs_login,
    }


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
