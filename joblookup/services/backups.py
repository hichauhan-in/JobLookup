"""Portable data archives. Never export credentials, cookies or executable SQL."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import tempfile
import uuid
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from joblookup.db import session as db

TABLES = (
    "profile",
    "cv",
    "search_track",
    "job",
    "job_source",
    "resume_version",
    "tailored_cv",
    "application",
    "application_event",
    "application_task",
    "inbox_state",
    "job_feedback",
    "crawl_run",
    "crawl_run_job",
)
FORMAT = "joblookup-workspace-v1"
MAX_ARCHIVE = 80 * 1024 * 1024
MAX_EXPANDED = 160 * 1024 * 1024
JSON_FIELDS = {
    "profile": {"data": dict},
    "cv": {"extracted": dict},
    "search_track": {"preferences": dict, "sources": list, "schedule_weekdays": list},
    "job_source": {"raw": dict},
    "resume_version": {"content": dict, "prep_sheet": dict},
    "tailored_cv": {"content": dict, "prep_sheet": dict},
    "job_feedback": {"job_snapshot": dict, "profile_snapshot": dict},
    "crawl_run": {"sources": list, "stats": dict, "tokens": dict},
}


def export_workspace(root: Path) -> bytes:
    output = io.BytesIO()
    snapshot = sqlite3.connect(":memory:")
    snapshot.row_factory = sqlite3.Row
    db.connect().backup(snapshot)
    manifest: dict[str, Any] = {
        "format": FORMAT,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tables": {},
        "files": {},
        "missing_files": 0,
    }
    try:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for table in TABLES:
                records = []
                for row in snapshot.execute(f"SELECT * FROM {table}"):
                    record = {key: value for key, value in dict(row).items() if key != "embedding"}
                    if table == "job_source":
                        record["raw"] = "{}"
                    for column in ("stored_path", "docx_path", "export_path"):
                        if column not in record:
                            continue
                        value = record[column]
                        record[column] = ""
                        if not value:
                            continue
                        candidate = Path(value).resolve()
                        if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
                            manifest["missing_files"] += 1
                            continue
                        if candidate.stat().st_size > 25 * 1024 * 1024:
                            raise ValueError("A document exceeds the 25 MB backup file limit.")
                        name = f"files/{table}-{record['id']}-{column}{candidate.suffix.lower()}"
                        content = candidate.read_bytes()
                        archive.writestr(name, content)
                        manifest["files"][name] = hashlib.sha256(content).hexdigest()
                        record[column] = name
                    records.append(record)
                manifest["tables"][table] = records
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
    finally:
        snapshot.close()
    data = output.getvalue()
    if len(data) > MAX_ARCHIVE:
        raise ValueError("This workspace exceeds the 80 MB portable backup limit.")
    return data


def _validated_archive(data: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    if len(data) > MAX_ARCHIVE:
        raise ValueError("Backup exceeds the 80 MB upload limit.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if (
                len(entries) > 5000
                or len(names) != len(set(names))
                or sum(entry.file_size for entry in entries) > MAX_EXPANDED
            ):
                raise ValueError("Archive is oversized or contains duplicate entries.")
            for name in names:
                path = PurePosixPath(name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in name
                    or ":" in name
                    or (name != "manifest.json" and not name.startswith("files/"))
                ):
                    raise ValueError("Archive contains an unsafe file path.")
            if (
                "manifest.json" not in names
                or archive.getinfo("manifest.json").file_size > 64 * 1024 * 1024
            ):
                raise ValueError("A valid backup manifest is required.")
            manifest = json.loads(archive.read("manifest.json"))
            if (
                not isinstance(manifest, dict)
                or manifest.get("format") != FORMAT
                or not isinstance(manifest.get("tables"), dict)
                or set(manifest["tables"]) != set(TABLES)
            ):
                raise ValueError("This is not a supported JobLookup workspace backup.")
            files = manifest.get("files")
            if not isinstance(files, dict) or set(files) != set(names) - {"manifest.json"}:
                raise ValueError("The backup file inventory does not match its manifest.")
            contents = {name: archive.read(name) for name in files}
            if any(
                hashlib.sha256(content).hexdigest() != files[name]
                for name, content in contents.items()
            ):
                raise ValueError("A document failed its backup checksum.")
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeError, RuntimeError) as exc:
        raise ValueError("The backup is damaged or unreadable.") from exc
    for table, rows in manifest["tables"].items():
        allowed = {row["name"] for row in db.connect().execute(f"PRAGMA table_info({table})")} - {
            "embedding"
        }
        if not isinstance(rows, list) or len(rows) > 200000:
            raise ValueError("Backup contains an invalid record collection.")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not row
                or not set(row).issubset(allowed)
                or any(
                    not isinstance(value, (str, int, float, bool, type(None)))
                    for value in row.values()
                )
            ):
                raise ValueError(f"Backup contains invalid {table} fields.")
            for column, expected in JSON_FIELDS.get(table, {}).items():
                if row.get(column) is None:
                    continue
                try:
                    value = json.loads(row[column])
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"Backup contains invalid {table}.{column} JSON.") from exc
                if not isinstance(value, expected):
                    raise ValueError(f"Backup contains an invalid {table}.{column} value.")
                if (
                    table == "search_track"
                    and column == "schedule_weekdays"
                    and any(not isinstance(day, int) or day < 0 or day > 6 for day in value)
                ):
                    raise ValueError("Backup contains an invalid schedule weekday.")
            for column in ("stored_path", "docx_path", "export_path"):
                if row.get(column) and row[column] not in contents:
                    raise ValueError("A document reference is missing from the archive.")
    profiles = manifest["tables"]["profile"]
    if len(profiles) != 1 or profiles[0].get("id") != 1 or not profiles[0].get("data"):
        raise ValueError("Backup must contain exactly one career profile.")
    with tempfile.TemporaryDirectory(prefix="joblookup-validate-") as temporary:
        path = Path(temporary) / "validate.db"
        db.apply_schema(path)
        with closing(sqlite3.connect(path)) as staging, staging:
            staging.execute("PRAGMA foreign_keys = ON")
            try:
                _replace_rows(staging, manifest["tables"])
            except sqlite3.Error as exc:
                raise ValueError("Backup records fail schema or relationship validation.") from exc
    return manifest, contents


def _replace_rows(conn: sqlite3.Connection, tables: dict[str, list[dict[str, Any]]]) -> None:
    conn.execute("PRAGMA defer_foreign_keys = ON")
    conn.execute("DELETE FROM job_score")
    for table in reversed(TABLES):
        conn.execute(f"DELETE FROM {table}")
    for table in TABLES:
        for row in tables[table]:
            columns = list(row)
            conn.execute(
                f"INSERT INTO {table} ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})",
                tuple(row[column] for column in columns),
            )
    if conn.execute("PRAGMA foreign_key_check").fetchall():
        raise sqlite3.IntegrityError("Invalid backup relationships")


def preview_workspace(data: bytes) -> dict[str, Any]:
    manifest, contents = _validated_archive(data)
    return {
        "format": FORMAT,
        "created_at": manifest.get("created_at"),
        "counts": {table: len(rows) for table, rows in manifest["tables"].items()},
        "documents": len(contents),
        "missing_files": manifest.get("missing_files", 0),
        "sha256": hashlib.sha256(data).hexdigest(),
        "credentials_included": False,
    }


def restore_workspace(data: bytes, root: Path) -> dict[str, Any]:
    manifest, contents = _validated_archive(data)
    before = db.connect().execute("PRAGMA data_version").fetchone()[0]
    safety = export_workspace(root)
    backup_dir = root / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    safety_name = f"before-restore-{uuid.uuid4().hex[:12]}.zip"
    (backup_dir / safety_name).write_bytes(safety)
    restored = root / "restored" / uuid.uuid4().hex
    try:
        for name, content in contents.items():
            destination = restored / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        for table, rows in manifest["tables"].items():
            for row in rows:
                for column in ("stored_path", "docx_path", "export_path"):
                    if row.get(column):
                        row[column] = str(restored / row[column])
                if table == "search_track":
                    row["schedule_enabled"] = 0
        with db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("PRAGMA data_version").fetchone()[0] != before:
                raise ValueError(
                    "The workspace changed during preview. "
                    "Retry the restore with no other activity."
                )
            _replace_rows(conn, manifest["tables"])
            conn.execute("DELETE FROM setting WHERE key LIKE 'review:%'")
    except Exception:
        import shutil

        shutil.rmtree(restored, ignore_errors=True)
        raise
    return {
        "restored": True,
        "safety_backup": safety_name,
        "schedules_paused": True,
        "counts": {table: len(rows) for table, rows in manifest["tables"].items()},
    }
