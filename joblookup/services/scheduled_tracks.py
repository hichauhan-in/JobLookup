"""Persistent once-per-day track scheduling with same-day catch-up."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from joblookup.config import Settings
from joblookup.db import session as db
from joblookup.events import EventBus
from joblookup.services import crawl, workflow
from joblookup.sources import registry


def due_tracks(now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now()
    today = now.date().isoformat()
    return [
        track
        for track in workflow.list_tracks()
        if track["schedule_enabled"]
        and (not track["schedule_weekdays"] or now.weekday() in track["schedule_weekdays"])
        and (now.hour, now.minute) >= (track["schedule_hour"], track["schedule_minute"])
        and track["last_slot"] != today
    ]


def queue_due_track(settings: Settings) -> None:
    from joblookup.server.jobs import Job, manager

    if settings.server.multi_user or any(task["kind"] == "search" for task in manager.active()):
        return
    for track in due_tracks():
        profile = workflow.effective_profile(track["id"])
        if not profile.get("target_titles"):
            continue
        sources = [
            row["key"]
            for row in registry.list_sources(settings)
            if row["enabled"]
            and row["ready"]
            and (not track["sources"] or row["key"] in track["sources"])
        ]
        if not sources:
            continue
        active = settings.model_copy(deep=True)
        active.search.recency_days = int(
            profile.get("recency_days") or settings.search.recency_days
        )

        def work(
            bus: EventBus,
            task: Job,
            *,
            run_settings: Settings = active,
            run_sources: list[str] = sources,
            run_profile: dict[str, Any] = profile,
            track_id: int = track["id"],
        ) -> dict[str, Any]:
            stats = crawl.run_crawl(
                run_settings,
                bus,
                source_keys=run_sources,
                profile=run_profile,
                cancelled=task.cancel_requested.is_set,
            )
            if stats.run_id:
                with db.transaction() as conn:
                    conn.execute(
                        "UPDATE crawl_run SET track_id = ? WHERE id = ?",
                        (track_id, stats.run_id),
                    )
            return {
                "crawl": stats.to_dict(),
                "track_id": track_id,
                "partial": bool(stats.failures),
            }

        manager.submit(
            "search",
            work,
            label=f"Scheduled: {track['name']}",
            meta={"track_id": track["id"]},
            single=False,
        )
        with db.transaction() as conn:
            conn.execute(
                "UPDATE search_track SET last_slot = ? WHERE id = ?",
                (datetime.now().date().isoformat(), track["id"]),
            )
        break
