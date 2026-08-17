"""SQLite access.

One database file per storage root, opened per thread. Everything that touches
the database goes through :func:`connect`, so WAL mode, foreign keys and the
row factory are set in exactly one place.
"""

from __future__ import annotations

import json
import sqlite3
import struct
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from joblookup.paths import ensure_dir, package_dir

DB_NAME = "joblookup.db"

_local = threading.local()
_root: Path | None = None
_root_lock = threading.Lock()


def configure(storage_root: Path) -> Path:
    """Point the database at ``storage_root`` and apply the schema."""
    global _root
    with _root_lock:
        _root = ensure_dir(storage_root)
    path = db_path()
    apply_schema(path)
    return path


def db_path(storage_root: Path | None = None) -> Path:
    root = storage_root or _root
    if root is None:
        raise RuntimeError("Database root has not been configured.")
    return ensure_dir(root) / DB_NAME


def apply_schema(path: Path) -> None:
    sql = (package_dir() / "db" / "schema.sql").read_text(encoding="utf-8")
    with sqlite3.connect(path) as conn:
        conn.executescript(sql)


def connect(storage_root: Path | None = None) -> sqlite3.Connection:
    """A connection for the calling thread, created on first use."""
    path = db_path(storage_root)
    key = str(path)
    cache: dict[str, sqlite3.Connection] = getattr(_local, "connections", None) or {}
    existing = cache.get(key)
    if existing is not None:
        return existing

    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    cache[key] = conn
    _local.connections = cache
    return conn


@contextmanager
def transaction(storage_root: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Commit on success, roll back on failure."""
    conn = connect(storage_root)
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()


def close_all() -> None:
    cache: dict[str, sqlite3.Connection] = getattr(_local, "connections", None) or {}
    for conn in cache.values():
        try:
            conn.close()
        except sqlite3.Error:
            pass
    _local.connections = {}


# --- small helpers -----------------------------------------------------------
def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def loads(value: Any, default: Any = None) -> Any:
    """Parse a JSON column without making every call site defensive."""
    if not value:
        return default if default is not None else {}
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default if default is not None else {}


def pack_vector(values: list[float]) -> bytes:
    """Store an embedding as packed float32 — a quarter of the size of JSON and
    an order of magnitude faster to read back."""
    return struct.pack(f"<{len(values)}f", *values)


def unpack_vector(blob: bytes | None) -> list[float]:
    if not blob:
        return []
    count = len(blob) // 4
    return list(struct.unpack(f"<{count}f", blob[: count * 4]))


def get_setting(key: str, default: str = "") -> str:
    row = connect().execute("SELECT value FROM setting WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT INTO setting (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
