"""Reading and writing the things the app is actually about.

The API layer and the pipelines both go through here, so the rules about what
counts as a duplicate, when a score becomes stale, and what "current" means for
a profile live in one place.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from joblookup.db import session as db
from joblookup.models import NormalizedJob, Score, utc_now_iso

# --- profile -----------------------------------------------------------------


def get_profile() -> dict[str, Any]:
    row = db.connect().execute("SELECT * FROM profile WHERE id = 1").fetchone()
    if row is None:
        return {"data": {}, "version": 1, "updated_at": None, "embed_model": ""}
    return {
        "data": db.loads(row["data"], {}),
        "version": int(row["version"]),
        "embedding": db.unpack_vector(row["embedding"]),
        "embed_model": row["embed_model"],
        "updated_at": row["updated_at"],
    }


def profile_version() -> int:
    row = db.connect().execute("SELECT version FROM profile WHERE id = 1").fetchone()
    return int(row["version"]) if row else 1


def save_profile(data: dict[str, Any], *, bump: bool = True) -> int:
    """Persist the profile. Bumping the version invalidates every score, which
    is the point: a changed profile means the old judgements no longer apply."""
    with db.transaction() as conn:
        conn.execute(
            "UPDATE profile SET data = ?, version = version + ?, "
            "updated_at = datetime('now') WHERE id = 1",
            (json.dumps(data, ensure_ascii=False), 1 if bump else 0),
        )
    return profile_version()


def save_profile_embedding(vector: list[float], model: str) -> None:
    with db.transaction() as conn:
        conn.execute(
            "UPDATE profile SET embedding = ?, embed_model = ? WHERE id = 1",
            (db.pack_vector(vector) if vector else None, model),
        )


# --- CVs ---------------------------------------------------------------------


def add_cv(*, label: str, filename: str, stored_path: Path, mime_type: str, raw_text: str) -> int:
    with db.transaction() as conn:
        cursor = conn.execute(
            "INSERT INTO cv (label, filename, stored_path, mime_type, raw_text, extract_state) "
            "VALUES (?, ?, ?, ?, ?, 'pending')",
            (label, filename, str(stored_path), mime_type, raw_text),
        )
        cv_id = int(cursor.lastrowid)
        # The first CV uploaded becomes the tailoring base until told otherwise.
        conn.execute(
            "UPDATE cv SET is_primary = 1 WHERE id = ? AND NOT EXISTS "
            "(SELECT 1 FROM cv WHERE is_primary = 1 AND id != ?)",
            (cv_id, cv_id),
        )
    return cv_id


def list_cvs() -> list[dict[str, Any]]:
    rows = db.connect().execute("SELECT * FROM cv ORDER BY created_at DESC").fetchall()
    result = []
    for row in rows:
        entry = dict(row)
        entry["extracted"] = db.loads(entry.get("extracted"), {})
        # The full text is often megabytes and no screen shows it.
        entry["raw_text_chars"] = len(entry.pop("raw_text", "") or "")
        result.append(entry)
    return result


def get_cv(cv_id: int) -> dict[str, Any]:
    row = db.connect().execute("SELECT * FROM cv WHERE id = ?", (cv_id,)).fetchone()
    if row is None:
        return {}
    entry = dict(row)
    entry["extracted"] = db.loads(entry.get("extracted"), {})
    return entry


def primary_cv() -> dict[str, Any]:
    row = db.connect().execute("SELECT * FROM cv WHERE is_primary = 1 LIMIT 1").fetchone()
    if row is None:
        row = db.connect().execute("SELECT * FROM cv ORDER BY created_at LIMIT 1").fetchone()
    if row is None:
        return {}
    entry = dict(row)
    entry["extracted"] = db.loads(entry.get("extracted"), {})
    return entry


def set_primary_cv(cv_id: int) -> None:
    with db.transaction() as conn:
        conn.execute("UPDATE cv SET is_primary = 0")
        conn.execute("UPDATE cv SET is_primary = 1 WHERE id = ?", (cv_id,))


def set_cv_extraction(cv_id: int, *, state: str, extracted: dict | None, error: str = "") -> None:
    with db.transaction() as conn:
        conn.execute(
            "UPDATE cv SET extract_state = ?, extracted = ?, extract_error = ?, "
            "updated_at = datetime('now') WHERE id = ?",
            (
                state,
                json.dumps(extracted, ensure_ascii=False) if extracted is not None else None,
                error,
                cv_id,
            ),
        )


def delete_cv(cv_id: int) -> str:
    """Remove the row and return the file that should now be deleted."""
    row = (
        db.connect()
        .execute("SELECT stored_path, is_primary FROM cv WHERE id = ?", (cv_id,))
        .fetchone()
    )
    if row is None:
        return ""
    with db.transaction() as conn:
        conn.execute("DELETE FROM cv WHERE id = ?", (cv_id,))
        if row["is_primary"]:
            conn.execute(
                "UPDATE cv SET is_primary = 1 WHERE id = "
                "(SELECT id FROM cv ORDER BY created_at LIMIT 1)"
            )
    return row["stored_path"]


# --- jobs --------------------------------------------------------------------


def upsert_job(job: NormalizedJob) -> tuple[int, bool]:
    """Insert or refresh a posting. Returns ``(job_id, is_new)``.

    A job already known from another source gains a second ``job_source`` row
    rather than a second card — that is what makes the deduplication visible
    instead of merely reducing the count.
    """
    conn = db.connect()
    existing = conn.execute(
        "SELECT id, description, posted_at FROM job WHERE fingerprint = ?", (job.fingerprint,)
    ).fetchone()

    with db.transaction() as tx:
        if existing is None:
            cursor = tx.execute(
                """
                INSERT INTO job (
                    fingerprint, title, title_norm, company, company_norm, location,
                    location_norm, country, work_mode, employment, seniority, description,
                    url, apply_url, posted_at, salary_min, salary_max, salary_currency
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.fingerprint,
                    job.title,
                    job.title_norm,
                    job.company,
                    job.company_norm,
                    job.location,
                    job.location_norm,
                    job.country,
                    job.work_mode,
                    job.employment,
                    job.seniority,
                    job.description,
                    job.url,
                    job.apply_url,
                    job.posted_at,
                    job.salary_min,
                    job.salary_max,
                    job.salary_currency,
                ),
            )
            job_id = int(cursor.lastrowid)
            is_new = True
        else:
            job_id = int(existing["id"])
            is_new = False
            # Keep the richest description and the earliest known posting date:
            # aggregators routinely truncate, and a re-listing is not a new job.
            better_description = (
                job.description
                if len(job.description) > len(existing["description"] or "")
                else existing["description"]
            )
            posted = _earliest(existing["posted_at"], job.posted_at)
            tx.execute(
                "UPDATE job SET description = ?, posted_at = ?, "
                "apply_url = COALESCE(NULLIF(?, ''), apply_url), "
                "last_seen_at = datetime('now'), archived = 0 WHERE id = ?",
                (better_description, posted, job.apply_url, job_id),
            )

        tx.execute(
            """
            INSERT INTO job_source (job_id, source_key, source_job_id, url, raw)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(job_id, source_key) DO UPDATE SET
                url = excluded.url, seen_at = datetime('now'), raw = excluded.raw
            """,
            (
                job_id,
                job.source_key,
                job.source_job_id,
                job.url,
                json.dumps(job.raw, ensure_ascii=False)[:20000],
            ),
        )
    return job_id, is_new


def _earliest(left: str | None, right: str | None) -> str | None:
    candidates = [value for value in (left, right) if value]
    return min(candidates) if candidates else None


def find_by_company(company_norm: str) -> list[dict[str, Any]]:
    """Existing postings from one company, for near-duplicate comparison."""
    rows = (
        db.connect()
        .execute(
            "SELECT id, title, title_norm, location_norm, description FROM job "
            "WHERE company_norm = ? AND archived = 0",
            (company_norm,),
        )
        .fetchall()
    )
    return [dict(row) for row in rows]


def list_jobs(
    *,
    bands: list[str] | None = None,
    max_age_days: int | None = None,
    work_modes: list[str] | None = None,
    statuses: list[str] | None = None,
    query: str = "",
    include_hidden: bool = False,
    scored_only: bool = True,
    run_id: int | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, Any]]:
    where = ["job.archived = 0"]
    params: list[Any] = []
    if not include_hidden:
        where.append("job.hidden = 0")
    if run_id is not None:
        where.append("job.id IN (SELECT job_id FROM crawl_run_job WHERE run_id = ?)")
        params.append(run_id)
    if bands:
        where.append(f"job_score.band IN ({','.join('?' * len(bands))})")
        params += bands
    if max_age_days:
        cutoff = f"datetime('now', '-{int(max_age_days)} days')"
        where.append(f"(job.posted_at IS NULL OR job.posted_at >= {cutoff})")
    if work_modes:
        where.append(f"job.work_mode IN ({','.join('?' * len(work_modes))})")
        params += work_modes
    if statuses:
        where.append(f"application.status IN ({','.join('?' * len(statuses))})")
        params += statuses
    if query:
        where.append("(job.title LIKE ? OR job.company LIKE ?)")
        params += [f"%{query}%", f"%{query}%"]

    join = "JOIN" if scored_only else "LEFT JOIN"
    sql = f"""
        SELECT job.*, job_score.band, job_score.composite, job_score.direct_fit,
               job_score.transferable_fit, job_score.growth_fit, job_score.rationale,
               job_score.matched_skills, job_score.learnable_gaps, job_score.hard_gaps,
               job_score.blocker, job_score.scored_at, job_score.profile_version,
               application.status AS application_status,
               (SELECT COUNT(*) FROM job_source WHERE job_source.job_id = job.id) AS source_count
        FROM job
        {join} job_score ON job_score.job_id = job.id
        LEFT JOIN application ON application.job_id = job.id
        WHERE {" AND ".join(where)}
        ORDER BY COALESCE(job_score.composite, 0) DESC, job.posted_at DESC
        LIMIT ? OFFSET ?
    """
    rows = db.connect().execute(sql, [*params, limit, offset]).fetchall()
    return [_shape_job(row) for row in rows]


def get_job(job_id: int) -> dict[str, Any]:
    row = (
        db.connect()
        .execute(
            """
        SELECT job.*, job_score.band, job_score.composite, job_score.direct_fit,
               job_score.transferable_fit, job_score.growth_fit, job_score.rationale,
               job_score.matched_skills, job_score.learnable_gaps, job_score.hard_gaps,
               job_score.blocker, job_score.scored_at, job_score.profile_version,
               application.status AS application_status, application.notes AS application_notes
        FROM job
        LEFT JOIN job_score ON job_score.job_id = job.id
        LEFT JOIN application ON application.job_id = job.id
        WHERE job.id = ?
        """,
            (job_id,),
        )
        .fetchone()
    )
    if row is None:
        return {}
    job = _shape_job(row)
    job["sources"] = [
        dict(entry)
        for entry in db.connect()
        .execute(
            "SELECT source_key, url, source_job_id, seen_at FROM job_source "
            "WHERE job_id = ? ORDER BY seen_at",
            (job_id,),
        )
        .fetchall()
    ]
    return job


def _shape_job(row: Any) -> dict[str, Any]:
    job = dict(row)
    job.pop("embedding", None)
    for key in ("matched_skills", "learnable_gaps", "hard_gaps"):
        job[key] = db.loads(job.get(key), [])
    return job


def jobs_for_scoring(
    *, job_ids: list[int], profile_version_value: int, rescore: bool
) -> list[dict[str, Any]]:
    """The recalled postings that still need judging, in recall order.

    Restricted to ``job_ids`` on purpose: loading every stored description to
    then throw most of them away is the difference between a few megabytes and a
    few hundred on a database that has been running for a month.

    Already-scored postings are skipped unless the profile moved or the user
    asked for a re-score, because a model call that reproduces an existing
    answer is pure cost.
    """
    if not job_ids:
        return []

    clause = "" if rescore else "AND (job_score.job_id IS NULL OR job_score.profile_version != ?)"
    order = ",".join("?" * len(job_ids))
    params: list[Any] = [*job_ids]
    if not rescore:
        params.append(profile_version_value)

    rows = (
        db.connect()
        .execute(
            f"""
        SELECT job.id, job.title, job.company, job.location, job.work_mode, job.employment,
               job.seniority, job.description, job.posted_at
        FROM job
        LEFT JOIN job_score ON job_score.job_id = job.id
        WHERE job.id IN ({order}) AND job.archived = 0 AND job.hidden = 0 {clause}
        """,
            params,
        )
        .fetchall()
    )

    by_id = {int(row["id"]): dict(row) for row in rows}
    return [by_id[job_id] for job_id in job_ids if job_id in by_id]


def save_job_embeddings(pairs: list[tuple[int, list[float]]], model: str) -> None:
    if not pairs:
        return
    with db.transaction() as conn:
        conn.executemany(
            "UPDATE job SET embedding = ?, embed_model = ? WHERE id = ?",
            [(db.pack_vector(vector), model, job_id) for job_id, vector in pairs],
        )


def set_hidden(job_id: int, hidden: bool) -> None:
    with db.transaction() as conn:
        conn.execute("UPDATE job SET hidden = ? WHERE id = ?", (int(hidden), job_id))


def archive_stale(older_than_days: int) -> int:
    with db.transaction() as conn:
        cursor = conn.execute(
            "UPDATE job SET archived = 1 WHERE archived = 0 AND "
            f"last_seen_at < datetime('now', '-{int(older_than_days)} days')"
        )
    return cursor.rowcount or 0


def counts() -> dict[str, int]:
    conn = db.connect()
    row = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM job WHERE archived = 0 AND hidden = 0)      AS jobs,
            (SELECT COUNT(*) FROM job_score WHERE band = 'strong')            AS strong,
            (SELECT COUNT(*) FROM job_score WHERE band = 'good')              AS good,
            (SELECT COUNT(*) FROM job_score WHERE band = 'stretch')           AS stretch,
            (SELECT COUNT(*) FROM job_score)                                  AS scored,
            (SELECT COUNT(*) FROM application)                                AS tracked,
            (SELECT COUNT(*) FROM cv)                                         AS cvs,
            (SELECT COUNT(*) FROM source WHERE enabled = 1)                   AS sources_enabled
        """
    ).fetchone()
    # sqlite3.Row iterates values, so .keys() is the only way to the column names.
    return {key: int(row[key]) for key in row.keys()}  # noqa: SIM118


# --- scores ------------------------------------------------------------------


def save_scores(scores: list[Score]) -> None:
    if not scores:
        return
    with db.transaction() as conn:
        conn.executemany(
            """
            INSERT INTO job_score (
                job_id, profile_version, band, composite, recall_score, direct_fit,
                transferable_fit, growth_fit, rationale, matched_skills, learnable_gaps,
                hard_gaps, blocker, model, scored_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(job_id) DO UPDATE SET
                profile_version = excluded.profile_version,
                band = excluded.band, composite = excluded.composite,
                recall_score = excluded.recall_score, direct_fit = excluded.direct_fit,
                transferable_fit = excluded.transferable_fit, growth_fit = excluded.growth_fit,
                rationale = excluded.rationale, matched_skills = excluded.matched_skills,
                learnable_gaps = excluded.learnable_gaps, hard_gaps = excluded.hard_gaps,
                blocker = excluded.blocker, model = excluded.model,
                scored_at = datetime('now')
            """,
            [
                (
                    score.job_id,
                    score.profile_version,
                    score.band,
                    score.composite,
                    score.recall_score,
                    score.direct_fit,
                    score.transferable_fit,
                    score.growth_fit,
                    score.rationale,
                    json.dumps(score.matched_skills, ensure_ascii=False),
                    json.dumps(score.learnable_gaps, ensure_ascii=False),
                    json.dumps(score.hard_gaps, ensure_ascii=False),
                    score.blocker,
                    score.model,
                )
                for score in scores
            ],
        )


def clear_scores() -> None:
    with db.transaction() as conn:
        conn.execute("DELETE FROM job_score")


# --- applications ------------------------------------------------------------


def set_application(job_id: int, *, status: str, notes: str | None = None) -> dict[str, Any]:
    applied = "datetime('now')" if status == "applied" else "applied_at"
    with db.transaction() as conn:
        conn.execute(
            f"""
            INSERT INTO application (job_id, status, notes)
            VALUES (?, ?, COALESCE(?, ''))
            ON CONFLICT(job_id) DO UPDATE SET
                status = excluded.status,
                notes = COALESCE(?, application.notes),
                applied_at = {applied},
                updated_at = datetime('now')
            """,
            (job_id, status, notes, notes),
        )
    row = db.connect().execute("SELECT * FROM application WHERE job_id = ?", (job_id,)).fetchone()
    return dict(row) if row else {}


def list_applications() -> list[dict[str, Any]]:
    rows = (
        db.connect()
        .execute(
            """
        SELECT application.*, job.title, job.company, job.location, job.url,
               job_score.band, job_score.composite
        FROM application
        JOIN job ON job.id = application.job_id
        LEFT JOIN job_score ON job_score.job_id = job.id
        ORDER BY application.updated_at DESC
        """
        )
        .fetchall()
    )
    return [dict(row) for row in rows]


# --- crawl runs --------------------------------------------------------------


def start_run(source_keys: list[str]) -> int:
    with db.transaction() as conn:
        cursor = conn.execute(
            "INSERT INTO crawl_run (sources) VALUES (?)",
            (json.dumps(source_keys),),
        )
    return int(cursor.lastrowid)


def finish_run(run_id: int, *, status: str, stats: dict[str, Any], error: str = "") -> None:
    with db.transaction() as conn:
        conn.execute(
            "UPDATE crawl_run SET finished_at = datetime('now'), status = ?, stats = ?, "
            "error = ? WHERE id = ?",
            (status, json.dumps(stats, ensure_ascii=False), error, run_id),
        )


def recent_runs(limit: int = 10) -> list[dict[str, Any]]:
    rows = (
        db.connect()
        .execute("SELECT * FROM crawl_run ORDER BY started_at DESC LIMIT ?", (limit,))
        .fetchall()
    )
    result = []
    for row in rows:
        entry = dict(row)
        entry["sources"] = db.loads(entry.get("sources"), [])
        entry["stats"] = db.loads(entry.get("stats"), {})
        result.append(entry)
    return result


def latest_run_id() -> int | None:
    """The newest search that actually produced postings, or None if none has.

    Runs recorded before results were linked have no postings attached, so they
    are skipped rather than showing an empty Matches screen.
    """
    row = (
        db.connect()
        .execute("SELECT run_id FROM crawl_run_job GROUP BY run_id ORDER BY run_id DESC LIMIT 1")
        .fetchone()
    )
    return int(row["run_id"]) if row else None


def link_run_jobs(run_id: int, produced: dict[int, bool]) -> None:
    """Record which postings a run produced, so history can show its results."""
    if not produced:
        return
    with db.transaction() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO crawl_run_job (run_id, job_id, is_new) VALUES (?, ?, ?)",
            [(run_id, job_id, int(is_new)) for job_id, is_new in produced.items()],
        )


def search_history(limit: int = 50) -> list[dict[str, Any]]:
    """Every past search, newest first, with how many postings each produced."""
    rows = (
        db.connect()
        .execute(
            """
            SELECT r.*,
                   COUNT(rj.job_id)                      AS result_count,
                   COALESCE(SUM(rj.is_new), 0)           AS new_count
            FROM crawl_run r
            LEFT JOIN crawl_run_job rj ON rj.run_id = r.id
            GROUP BY r.id
            ORDER BY r.started_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        .fetchall()
    )
    history = []
    for row in rows:
        entry = dict(row)
        entry["sources"] = db.loads(entry.get("sources"), [])
        entry["stats"] = db.loads(entry.get("stats"), {})
        history.append(entry)
    return history


def run_results(run_id: int, limit: int = 200) -> list[dict[str, Any]]:
    """The postings one search produced, best score first."""
    rows = (
        db.connect()
        .execute(
            """
            SELECT j.id, j.title, j.company, j.location, j.url, j.posted_at,
                   j.work_mode, rj.is_new, s.composite AS score, s.band
            FROM crawl_run_job rj
            JOIN job j        ON j.id = rj.job_id
            LEFT JOIN job_score s ON s.job_id = j.id
            WHERE rj.run_id = ?
            ORDER BY COALESCE(s.composite, -1) DESC, j.posted_at DESC
            LIMIT ?
            """,
            (run_id, limit),
        )
        .fetchall()
    )
    return [dict(row) | {"is_new": bool(row["is_new"])} for row in rows]


def delete_run(run_id: int) -> bool:
    """Forget one search. The postings themselves are untouched."""
    with db.transaction() as conn:
        conn.execute("DELETE FROM crawl_run_job WHERE run_id = ?", (run_id,))
        cursor = conn.execute("DELETE FROM crawl_run WHERE id = ?", (run_id,))
    return cursor.rowcount > 0


def clear_history(keep_running: bool = True) -> int:
    """Forget every finished search. Postings, scores and applications survive."""
    clause = " WHERE status != 'running'" if keep_running else ""
    with db.transaction() as conn:
        conn.execute(
            f"DELETE FROM crawl_run_job WHERE run_id IN (SELECT id FROM crawl_run{clause})"
        )
        cursor = conn.execute(f"DELETE FROM crawl_run{clause}")
    return cursor.rowcount


# --- tailored CVs ------------------------------------------------------------


def save_tailored(
    *,
    job_id: int,
    cv_id: int,
    content: dict[str, Any],
    prep_sheet: dict[str, Any],
    markdown: str,
    docx_path: str = "",
) -> int:
    with db.transaction() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tailored_cv (job_id, cv_id, content, prep_sheet, markdown, docx_path)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, cv_id) DO UPDATE SET
                content = excluded.content, prep_sheet = excluded.prep_sheet,
                markdown = excluded.markdown, docx_path = excluded.docx_path,
                created_at = datetime('now')
            """,
            (
                job_id,
                cv_id,
                json.dumps(content, ensure_ascii=False),
                json.dumps(prep_sheet, ensure_ascii=False),
                markdown,
                docx_path,
            ),
        )
        rowid = cursor.lastrowid
    return int(rowid or 0)


def get_tailored(job_id: int, cv_id: int) -> dict[str, Any]:
    row = (
        db.connect()
        .execute("SELECT * FROM tailored_cv WHERE job_id = ? AND cv_id = ?", (job_id, cv_id))
        .fetchone()
    )
    if row is None:
        return {}
    entry = dict(row)
    entry["content"] = db.loads(entry.get("content"), {})
    entry["prep_sheet"] = db.loads(entry.get("prep_sheet"), {})
    return entry


def touch() -> str:
    return utc_now_iso()
