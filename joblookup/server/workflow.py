"""Local workflow controls used by the daily workspace."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from joblookup.config import Settings
from joblookup.db import session as db
from joblookup.server.schemas import ProfilePatch
from joblookup.services import applications, digest, workflow


class TrackBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    preferences: ProfilePatch = Field(default_factory=ProfilePatch)
    sources: list[str] = Field(default_factory=list, max_length=50)
    cv_id: int | None = Field(default=None, ge=1)
    schedule_enabled: bool = False
    schedule_hour: int = Field(default=9, ge=0, le=23)
    schedule_minute: int = Field(default=0, ge=0, le=59)
    schedule_weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], max_length=7)


class SeenBody(BaseModel):
    job_ids: list[int] = Field(max_length=2000)
    track_id: int = Field(default=0, ge=0)


class FeedbackBody(BaseModel):
    label: Literal["relevant", "adjacent", "irrelevant"]
    reason: Literal[
        "",
        "wrong_role",
        "too_senior",
        "too_junior",
        "wrong_location",
        "salary",
        "sponsorship",
        "not_interested",
        "good_fit",
    ] = ""
    notes: str = Field(default="", max_length=2000)
    track_id: int = Field(default=0, ge=0)


class ContactBody(BaseModel):
    contact_name: str = Field(default="", max_length=200)
    contact_email: str = Field(default="", max_length=320)
    submitted_version_id: int | None = Field(default=None, ge=1)


class ActionBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_at: datetime
    kind: Literal["followup", "interview", "deadline"] = "followup"


class CompleteBody(BaseModel):
    done: bool


def build_router(settings_getter: Callable[[], Settings]) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/digest")
    def brief(track_id: int = Query(default=0, ge=0)) -> dict[str, Any]:
        try:
            return digest.daily_brief(track_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/digest/export")
    def export_brief(track_id: int = Query(default=0, ge=0)) -> Response:
        return Response(
            digest.markdown_brief(brief(track_id)),
            media_type="text/markdown",
            headers={"Content-Disposition": 'attachment; filename="joblookup-daily-brief.md"'},
        )

    @router.get("/tracks")
    def tracks() -> dict[str, Any]:
        return {
            "items": workflow.list_tracks(),
            "scheduler": {
                "requires_running_app": True,
                "timezone": "computer local time",
                "missed_run_policy": "Once per scheduled day, on the next tick after startup",
            },
        }

    def save_track(body: TrackBody, track_id: int = 0) -> dict[str, Any]:
        if any(day < 0 or day > 6 for day in body.schedule_weekdays):
            raise HTTPException(422, "Weekdays must be between Monday (0) and Sunday (6).")
        try:
            return workflow.save_track(body.model_dump(exclude_none=True), track_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "A search track already uses that name.") from exc

    @router.post("/tracks")
    def create_track(body: TrackBody) -> dict[str, Any]:
        return save_track(body)

    @router.put("/tracks/{track_id}")
    def update_track(track_id: int, body: TrackBody) -> dict[str, Any]:
        return save_track(body, track_id)

    @router.delete("/tracks/{track_id}")
    def delete_track(track_id: int) -> dict[str, bool]:
        with db.transaction() as conn:
            removed = conn.execute("DELETE FROM search_track WHERE id = ?", (track_id,)).rowcount
            conn.execute("DELETE FROM inbox_state WHERE track_id = ?", (track_id,))
        if not removed:
            raise HTTPException(404, "This search track no longer exists.")
        return {"deleted": True}

    @router.post("/inbox/seen")
    def seen(body: SeenBody) -> dict[str, int]:
        try:
            return {"marked": workflow.mark_seen(body.job_ids, body.track_id)}
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.post("/opportunities/{job_id}/feedback")
    def save_feedback(job_id: int, body: FeedbackBody) -> dict[str, Any]:
        try:
            return workflow.save_feedback(job_id, body.model_dump(), body.track_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.delete("/opportunities/{job_id}/feedback")
    def delete_feedback(job_id: int, track_id: int = Query(default=0, ge=0)) -> dict[str, bool]:
        with db.transaction() as conn:
            conn.execute(
                "DELETE FROM job_feedback WHERE job_id = ? AND track_id = ?", (job_id, track_id)
            )
        return {"deleted": True}

    @router.get("/benchmark")
    def benchmark(track_id: int | None = Query(default=None, ge=0)) -> dict[str, Any]:
        return workflow.benchmark(track_id)

    @router.get("/benchmark/export")
    def export_benchmark() -> Response:
        records = [
            dict(row)
            for row in db.connect().execute("SELECT * FROM job_feedback ORDER BY job_id, track_id")
        ]
        for record in records:
            for key in ("job_snapshot", "profile_snapshot"):
                record[key] = db.loads(record[key])
        return Response(
            json.dumps({"format": "joblookup-relevance-v1", "labels": records}, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="relevance-benchmark.json"'},
        )

    @router.get("/agenda")
    def agenda() -> dict[str, Any]:
        return {"items": applications.agenda()}

    @router.get("/applications/{job_id}/activity")
    def activity(job_id: int) -> dict[str, Any]:
        try:
            return applications.details(job_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.put("/applications/{job_id}/contact")
    def contact(job_id: int, body: ContactBody) -> dict[str, Any]:
        try:
            return applications.set_contact(
                job_id, body.contact_name, body.contact_email, body.submitted_version_id
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/applications/{job_id}/actions")
    def add_action(job_id: int, body: ActionBody) -> dict[str, Any]:
        try:
            return applications.add_task(job_id, body.title, body.due_at, body.kind)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.patch("/actions/{task_id}")
    def complete(task_id: int, body: CompleteBody) -> dict[str, Any]:
        try:
            return applications.complete_task(task_id, body.done)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.delete("/actions/{task_id}")
    def delete_action(task_id: int) -> dict[str, bool]:
        with db.transaction() as conn:
            row = conn.execute("SELECT * FROM application_task WHERE id = ?", (task_id,)).fetchone()
            if not row:
                raise HTTPException(404, "This next action no longer exists.")
            conn.execute("DELETE FROM application_task WHERE id = ?", (task_id,))
            conn.execute(
                "INSERT INTO application_event(job_id, kind, detail) VALUES (?, 'task', ?)",
                (row["job_id"], f"Removed: {row['title']}"),
            )
        return {"deleted": True}

    @router.get("/opportunities/{job_id}/versions")
    def versions(job_id: int) -> dict[str, Any]:
        return {"items": applications.versions(job_id)}

    @router.get("/resume-versions/{version_id}")
    def version(version_id: int) -> dict[str, Any]:
        try:
            return applications.get_version(version_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/resume-versions/{version_id}/download")
    def download_version(version_id: int) -> Response:
        value = version(version_id)
        return Response(
            value["markdown"],
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="resume-version-{version_id}.md"'
            },
        )

    return router
