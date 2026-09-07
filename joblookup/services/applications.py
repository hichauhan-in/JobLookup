"""Application next actions and immutable resume drafts."""

from __future__ import annotations

import difflib
import re
from datetime import datetime, timezone
from typing import Any

from joblookup.db import session as db
from joblookup.matching.evidence import skills_from_text


def require_application(job_id: int) -> dict[str, Any]:
    row = db.connect().execute("SELECT * FROM application WHERE job_id = ?", (job_id,)).fetchone()
    if not row:
        raise ValueError("Save this job to applications first.")
    return dict(row)


def details(job_id: int) -> dict[str, Any]:
    application = require_application(job_id)
    events = [
        dict(row)
        for row in db.connect().execute(
            "SELECT * FROM application_event WHERE job_id = ? ORDER BY id DESC", (job_id,)
        )
    ]
    tasks = [
        dict(row)
        for row in db.connect().execute(
            "SELECT * FROM application_task WHERE job_id = ? ORDER BY done_at IS NOT NULL, due_at",
            (job_id,),
        )
    ]
    return {
        "application": application,
        "events": events,
        "tasks": tasks,
        "versions": versions(job_id),
    }


def set_contact(job_id: int, name: str, email: str, version_id: int | None) -> dict[str, Any]:
    previous = require_application(job_id)
    if (
        version_id
        and not db.connect()
        .execute("SELECT 1 FROM resume_version WHERE id = ? AND job_id = ?", (version_id, job_id))
        .fetchone()
    ):
        raise ValueError(
            "That resume version belongs to a different application or no longer exists."
        )
    with db.transaction() as conn:
        conn.execute(
            "UPDATE application SET contact_name = ?, contact_email = ?, "
            "submitted_version_id = ?, updated_at = datetime('now') WHERE job_id = ?",
            (name, email, version_id, job_id),
        )
        if previous["submitted_version_id"] != version_id:
            conn.execute(
                "INSERT INTO application_event(job_id, kind, detail) VALUES (?, 'document', ?)",
                (
                    job_id,
                    f"Submitted resume set to version {version_id}."
                    if version_id
                    else "Submitted resume reference cleared.",
                ),
            )
        if (previous["contact_name"], previous["contact_email"]) != (name, email):
            conn.execute(
                "INSERT INTO application_event(job_id, kind, detail) VALUES (?, 'contact', ?)",
                (job_id, f"Recruiter contact updated: {name or email or 'cleared'}."),
            )
    return details(job_id)


def add_task(job_id: int, title: str, due_at: datetime, kind: str) -> dict[str, Any]:
    require_application(job_id)
    if due_at.tzinfo is None:
        raise ValueError("A reminder needs a timezone-aware due date.")
    if not title.strip():
        raise ValueError("Give the next action a title.")
    due = due_at.astimezone(timezone.utc).isoformat()
    with db.transaction() as conn:
        cursor = conn.execute(
            "INSERT INTO application_task(job_id, title, kind, due_at) VALUES (?, ?, ?, ?)",
            (job_id, title.strip(), kind, due),
        )
        conn.execute(
            "INSERT INTO application_event(job_id, kind, detail) VALUES (?, 'task', ?)",
            (job_id, f"Scheduled {title.strip()} for {due}."),
        )
    return dict(
        db.connect()
        .execute("SELECT * FROM application_task WHERE id = ?", (cursor.lastrowid,))
        .fetchone()
    )


def complete_task(task_id: int, done: bool) -> dict[str, Any]:
    row = db.connect().execute("SELECT * FROM application_task WHERE id = ?", (task_id,)).fetchone()
    if not row:
        raise ValueError("This next action no longer exists.")
    with db.transaction() as conn:
        conn.execute(
            "UPDATE application_task SET done_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat() if done else None, task_id),
        )
        if bool(row["done_at"]) != done:
            conn.execute(
                "INSERT INTO application_event(job_id, kind, detail) VALUES (?, 'task', ?)",
                (row["job_id"], f"{'Completed' if done else 'Reopened'}: {row['title']}"),
            )
    return dict(
        db.connect().execute("SELECT * FROM application_task WHERE id = ?", (task_id,)).fetchone()
    )


def agenda() -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in db.connect().execute(
            "SELECT application_task.*, job.title AS job_title, job.company, application.status "
            "FROM application_task JOIN job ON job.id = application_task.job_id "
            "JOIN application ON application.job_id = job.id "
            "WHERE done_at IS NULL ORDER BY due_at LIMIT 200"
        )
    ]


def versions(job_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in db.connect().execute(
            "SELECT resume_version.id, resume_version.cv_id, resume_version.created_at, "
            "cv.label AS cv_label FROM resume_version "
            "LEFT JOIN cv ON cv.id = resume_version.cv_id "
            "WHERE job_id = ? ORDER BY resume_version.id DESC",
            (job_id,),
        )
    ]


def get_version(version_id: int) -> dict[str, Any]:
    row = (
        db.connect().execute("SELECT * FROM resume_version WHERE id = ?", (version_id,)).fetchone()
    )
    if not row:
        raise ValueError("This resume version no longer exists.")
    version = dict(row)
    base = version["base_text"]
    draft = version["markdown"]
    version["diff"] = "\n".join(
        difflib.unified_diff(
            base.splitlines(),
            draft.splitlines(),
            fromfile="Original resume",
            tofile="Tailored draft",
            lineterm="",
        )
    )
    original_skills = {item["name"] for item in skills_from_text(base)}
    new_skills = sorted({item["name"] for item in skills_from_text(draft)} - original_skills)
    original_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)*%?", base))
    new_numbers = sorted(set(re.findall(r"\b\d+(?:[.,]\d+)*%?", draft)) - original_numbers)
    version["checks"] = {
        "new_skill_mentions": new_skills,
        "new_numeric_claims": new_numbers,
        "requires_review": bool(new_skills or new_numbers),
    }
    version["content"] = db.loads(version["content"])
    version["prep_sheet"] = db.loads(version["prep_sheet"])
    return version
