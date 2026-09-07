"""Local search tracks, inbox state and user-labeled relevance evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from joblookup import store
from joblookup.cv.profile import PREFERENCE_KEYS
from joblookup.db import session as db
from joblookup.matching.evidence import ENGINE_VERSION, evaluate_job
from joblookup.sources.normalize import age_days


def posting_hash(job: dict[str, Any]) -> str:
    values = {
        key: job.get(key)
        for key in (
            "title",
            "company",
            "description",
            "location",
            "country",
            "work_mode",
            "employment",
            "seniority",
            "posted_at",
            "salary_min",
            "salary_max",
            "salary_currency",
            "salary_period",
            "availability",
            "partial_description",
        )
    }
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def shape_track(row: Any) -> dict[str, Any]:
    track = dict(row)
    for key, default in (("preferences", {}), ("sources", []), ("schedule_weekdays", [])):
        track[key] = db.loads(track.get(key), default)
    track["schedule_enabled"] = bool(track["schedule_enabled"])
    return track


def list_tracks() -> list[dict[str, Any]]:
    return [
        shape_track(row) for row in db.connect().execute("SELECT * FROM search_track ORDER BY name")
    ]


def get_track(track_id: int) -> dict[str, Any]:
    row = db.connect().execute("SELECT * FROM search_track WHERE id = ?", (track_id,)).fetchone()
    if row is None:
        raise ValueError("This search track no longer exists.")
    return shape_track(row)


def effective_profile(track_id: int = 0) -> dict[str, Any]:
    profile = dict(store.get_profile().get("data") or {})
    if track_id:
        track = get_track(track_id)
        if track["cv_id"]:
            document = store.get_cv(track["cv_id"])
            extracted = document.get("extracted") or {}
            for key in ("skills", "headline", "summary", "roles", "total_years_experience"):
                if extracted.get(key):
                    profile[key] = extracted[key]
        profile.update(track["preferences"])
    return profile


def save_track(values: dict[str, Any], track_id: int = 0) -> dict[str, Any]:
    if track_id:
        get_track(track_id)
    if values.get("cv_id") and not store.get_cv(values["cv_id"]):
        raise ValueError("The selected resume no longer exists.")
    preferences = {
        key: value
        for key, value in values.get("preferences", {}).items()
        if key in (*PREFERENCE_KEYS, "seniority") and value is not None
    }
    fields = {
        "name": values["name"].strip(),
        "preferences": json.dumps(preferences),
        "sources": json.dumps(values.get("sources") or []),
        "cv_id": values.get("cv_id"),
        "schedule_enabled": int(values.get("schedule_enabled", False)),
        "schedule_hour": values.get("schedule_hour", 9),
        "schedule_minute": values.get("schedule_minute", 0),
        "schedule_weekdays": json.dumps(values.get("schedule_weekdays", [0, 1, 2, 3, 4])),
    }
    if not fields["name"]:
        raise ValueError("Give the search track a name.")
    with db.transaction() as conn:
        if track_id:
            assignment = ", ".join(f"{key} = ?" for key in fields)
            conn.execute(
                f"UPDATE search_track SET {assignment}, updated_at = datetime('now') WHERE id = ?",
                (*fields.values(), track_id),
            )
        else:
            cursor = conn.execute(
                f"INSERT INTO search_track ({', '.join(fields)}) "
                f"VALUES ({', '.join('?' for _ in fields)})",
                tuple(fields.values()),
            )
            track_id = int(cursor.lastrowid)
    return get_track(track_id)


def seen_hashes(track_id: int = 0) -> dict[int, str]:
    return {
        row["job_id"]: row["content_hash"]
        for row in db.connect().execute(
            "SELECT job_id, content_hash FROM inbox_state WHERE track_id = ?", (track_id,)
        )
    }


def mark_seen(job_ids: list[int], track_id: int = 0) -> int:
    if track_id:
        get_track(track_id)
    rows = []
    for job_id in dict.fromkeys(job_ids):
        job = store.get_job(job_id)
        if job:
            rows.append((job_id, track_id, posting_hash(job)))
    with db.transaction() as conn:
        conn.executemany(
            "INSERT INTO inbox_state(job_id, track_id, content_hash) VALUES (?, ?, ?) "
            "ON CONFLICT(job_id, track_id) DO UPDATE SET "
            "content_hash = excluded.content_hash, seen_at = datetime('now')",
            rows,
        )
    return len(rows)


def feedback(job_id: int, track_id: int = 0) -> dict[str, Any] | None:
    row = (
        db.connect()
        .execute(
            "SELECT label, reason, notes, updated_at FROM job_feedback "
            "WHERE job_id = ? AND track_id = ?",
            (job_id, track_id),
        )
        .fetchone()
    )
    return dict(row) if row else None


def save_feedback(job_id: int, values: dict[str, Any], track_id: int = 0) -> dict[str, Any]:
    job = store.get_job(job_id)
    if not job:
        raise ValueError("This job no longer exists.")
    profile = effective_profile(track_id)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO job_feedback(job_id, track_id, label, reason, notes, job_snapshot, "
            "profile_snapshot, posting_age) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(job_id, track_id) DO UPDATE SET label = excluded.label, "
            "reason = excluded.reason, notes = excluded.notes, "
            "job_snapshot = excluded.job_snapshot, "
            "profile_snapshot = excluded.profile_snapshot, posting_age = excluded.posting_age, "
            "updated_at = datetime('now')",
            (
                job_id,
                track_id,
                values["label"],
                values.get("reason", ""),
                values.get("notes", ""),
                json.dumps(job),
                json.dumps(profile),
                age_days(job.get("posted_at")),
            ),
        )
    return feedback(job_id, track_id) or {}


def benchmark(track_id: int | None = None) -> dict[str, Any]:
    clause = " WHERE track_id = ?" if track_id is not None else ""
    records = (
        db.connect()
        .execute("SELECT * FROM job_feedback" + clause, (track_id,) if track_id is not None else ())
        .fetchall()
    )
    results = []
    for record in records:
        job = db.loads(record["job_snapshot"])
        if record["posting_age"] is not None:
            job["posted_at"] = (
                datetime.now(timezone.utc) - timedelta(days=record["posting_age"])
            ).isoformat()
        profile = db.loads(record["profile_snapshot"])
        result = evaluate_job(job, profile, recency_days=profile.get("recency_days") or 14)
        results.append(
            {
                "job_id": record["job_id"],
                "track_id": record["track_id"],
                "title": job["title"],
                "label": record["label"],
                "reason": record["reason"],
                "score": result["score"],
                "band": result["band"],
                "eligible": result["eligible"],
            }
        )
    results.sort(key=lambda row: (row["eligible"], row["score"]), reverse=True)
    top = results[:20]
    relevant = [row for row in results if row["label"] == "relevant"]
    return {
        "engine": ENGINE_VERSION,
        "sample_size": len(results),
        "relevant": len(relevant),
        "false_exclusions": sum(not row["eligible"] for row in relevant),
        "top20_labeled_relevant": sum(row["label"] == "relevant" for row in top),
        "top20_labeled_count": len(top),
        "needs_review": sum(row["band"] == "review" for row in results),
        "results": results,
    }
