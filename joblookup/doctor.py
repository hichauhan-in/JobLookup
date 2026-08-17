"""Every health check behind the Diagnostics panel.

The rule for this file: a failing check must print the exact thing to do about
it. "Playwright not found" wastes the user's time; the command that installs it
does not.
"""

from __future__ import annotations

import importlib.util
import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from joblookup import __version__, store
from joblookup.config import Settings
from joblookup.db import session as db
from joblookup.llm import all_statuses, build_provider
from joblookup.llm.vscode_bridge import extension_state
from joblookup.services import secrets
from joblookup.sources import registry
from joblookup.sources.tier_b import browser

OK, WARN, FAIL = "ok", "warning", "failed"


@dataclass
class Check:
    key: str
    label: str
    status: str = OK
    detail: str = ""
    fix: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
            "fix": self.fix,
            "data": self.data,
        }


def run_all(settings: Settings) -> dict[str, Any]:
    checks = [
        _python(),
        _storage(settings),
        _database(),
        _fts(),
        _model(settings),
        _bridge(settings),
        _embeddings(settings),
        _sources(settings),
        _portals(settings),
        _optional_packages(),
        _secrets(),
    ]
    worst = (
        FAIL
        if any(c.status == FAIL for c in checks)
        else (WARN if any(c.status == WARN for c in checks) else OK)
    )
    return {
        "version": __version__,
        "status": worst,
        "checks": [check.to_dict() for check in checks],
    }


#: Checked at runtime rather than assumed: the package metadata says 3.10+, but
#: somebody can still point an older interpreter at the module directly.
MINIMUM_PYTHON = (3, 10)


def _python() -> Check:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info[:2] < MINIMUM_PYTHON:
        return Check(
            "python",
            "Python",
            FAIL,
            f"Python {version} is too old.",
            "Install Python 3.10 or newer from python.org and run the launcher again.",
        )
    return Check("python", "Python", OK, f"{version} ({sys.executable})")


def _storage(settings: Settings) -> Check:
    workspace = settings.paths.workspace_dir
    try:
        workspace.mkdir(parents=True, exist_ok=True)
        probe = workspace / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return Check(
            "storage",
            "Workspace",
            FAIL,
            f"Cannot write to {workspace}: {exc}",
            "Move JobLookup somewhere your account can write, or set paths.workspace "
            "in config/local.yaml to a writable folder.",
        )
    free = shutil.disk_usage(workspace).free / (1024**3)
    status = WARN if free < 1 else OK
    return Check(
        "storage",
        "Workspace",
        status,
        f"{workspace} · {free:.1f} GB free",
        "Free up some disk space." if status == WARN else "",
    )


def _database() -> Check:
    try:
        counts = store.counts()
    except (sqlite3.Error, RuntimeError) as exc:
        return Check(
            "database",
            "Database",
            FAIL,
            str(exc),
            "Delete workspace/joblookup.db and restart to rebuild it. You will lose "
            "stored postings, not your CVs.",
        )
    return Check(
        "database",
        "Database",
        OK,
        f"{counts['jobs']} posting(s), {counts['scored']} scored, {counts['cvs']} CV(s)",
        data=counts,
    )


def _fts() -> Check:
    """Lexical recall is the default, so its index working is not optional."""
    try:
        db.connect().execute("SELECT count(*) FROM job_fts").fetchone()
    except sqlite3.Error as exc:
        return Check(
            "fts",
            "Search index",
            WARN,
            f"The full-text index is unavailable ({exc}). Recall will use a slower "
            "fallback and rank less well.",
            "This build of SQLite lacks FTS5. Use the python.org build of Python.",
        )
    return Check("fts", "Search index", OK, "FTS5 available")


def _model(settings: Settings) -> Check:
    try:
        provider = build_provider(settings.llm)
        status = provider.status()
    except Exception as exc:  # noqa: BLE001
        return Check("model", "Language model", FAIL, str(exc))

    if not status.available:
        return Check(
            "model",
            "Language model",
            FAIL,
            f"{status.label}: {status.detail}",
            status.setup_hint,
            data={"provider": status.key},
        )
    return Check(
        "model",
        "Language model",
        OK,
        f"{status.label} · {status.active_model or 'auto'}",
        data={"provider": status.key, "models": status.models},
    )


def _bridge(settings: Settings) -> Check:
    state = extension_state(settings.llm.vscode.handshake_file)
    if settings.llm.provider != "vscode":
        return Check(
            "bridge",
            "VS Code bridge",
            OK,
            "Not in use, because a different provider is selected.",
            data=state,
        )
    if not state["extension_installed"]:
        return Check(
            "bridge",
            "VS Code bridge",
            FAIL,
            "The bridge extension is not installed in VS Code.",
            ".\\scripts\\install-bridge.ps1",
            data=state,
        )
    if not state["handshake_present"]:
        return Check(
            "bridge",
            "VS Code bridge",
            WARN,
            "The extension is installed but is not running.",
            "In VS Code press Ctrl+Shift+P and run 'Developer: Reload Window'. "
            "Keep a VS Code window open while JobLookup is scoring.",
            data=state,
        )
    return Check(
        "bridge", "VS Code bridge", OK, f"Handshake at {state['handshake_path']}", data=state
    )


def _embeddings(settings: Settings) -> Check:
    """Never a failure. Vector recall is an upgrade, not a requirement."""
    from joblookup.llm import LLMClient
    from joblookup.matching.recall import embeddings_available

    try:
        client = LLMClient.from_settings(settings)
    except Exception as exc:  # noqa: BLE001
        return Check(
            "embeddings", "Vector recall", OK, f"Unavailable ({exc}). Using keyword recall."
        )

    if embeddings_available(client, settings):
        model = settings.embeddings.model or settings.llm.openai_compat.embed_model
        return Check("embeddings", "Vector recall", OK, f"On, using {model}")
    return Check(
        "embeddings",
        "Vector recall",
        OK,
        "Off, because the selected provider has no embeddings API. Keyword recall is in "
        "use, which is the normal setup for a Copilot seat. Pointing at a local Ollama "
        "server in Settings would switch vectors on.",
    )


def _sources(settings: Settings) -> Check:
    rows = registry.list_sources(settings)
    enabled = [row for row in rows if row["enabled"]]
    blocked = [row for row in enabled if not row["ready"]]
    failing = [row for row in enabled if row.get("last_status") == "failed"]

    if not enabled:
        return Check(
            "sources",
            "Sources",
            FAIL,
            "No sources are enabled, so a search would find nothing.",
            "Turn some on from the Sources screen. The keyless feeds need no setup.",
        )
    if blocked or failing:
        first = (blocked or failing)[0]
        return Check(
            "sources",
            "Sources",
            WARN,
            f"{len(enabled)} enabled, {len(blocked)} not ready, {len(failing)} failing "
            f"(e.g. {first['name']}: {first.get('blocked_reason') or first.get('last_error')})",
            "Open the Sources screen. Each one says what it needs.",
            data={"enabled": len(enabled), "blocked": len(blocked), "failing": len(failing)},
        )
    return Check("sources", "Sources", OK, f"{len(enabled)} enabled and ready")


def _portals(settings: Settings) -> Check:
    if not settings.tier_b.enabled:
        return Check(
            "portals",
            "Logged-in portals",
            OK,
            "Off. Public APIs and company boards are in use, which is the safer default.",
        )
    state = browser.availability()
    if not state["browser_ready"]:
        return Check(
            "portals",
            "Logged-in portals",
            WARN,
            state["detail"],
            state["fix"],
            data=state,
        )
    return Check(
        "portals", "Logged-in portals", OK, "Playwright and Chromium are ready", data=state
    )


def _optional_packages() -> Check:
    optional = {
        "rapidfuzz": "faster and more accurate duplicate detection",
        "numpy": "faster vector maths when embeddings are in use",
        "keyring": "stores job-board API keys in Windows Credential Manager",
        "docx": "DOCX export of tailored CVs",
        "apscheduler": "unattended scheduled searches",
        "playwright": "logged-in portal scraping",
    }
    missing = [name for name in optional if importlib.util.find_spec(name) is None]
    if not missing:
        return Check("extras", "Optional components", OK, "All installed")
    return Check(
        "extras",
        "Optional components",
        OK,
        "Not installed: " + ", ".join(f"{name} ({optional[name]})" for name in missing),
        ".\\.venv\\Scripts\\python.exe -m pip install "
        + " ".join("python-docx" if name == "docx" else name for name in missing),
    )


def _secrets() -> Check:
    state = secrets.status()
    stored = [name for name, present in state["set"].items() if present]
    return Check(
        "secrets",
        "API keys",
        OK,
        f"{len(stored)} stored in {state['backend']}"
        + (f" ({', '.join(stored)})" if stored else ". None are needed for the default sources."),
        data=state,
    )


def provider_matrix(settings: Settings) -> list[dict[str, Any]]:
    return [status.to_dict() for status in all_statuses(settings.llm)]


def paths_report(settings: Settings) -> dict[str, str]:
    from joblookup.paths import app_root, user_state_dir

    return {
        "app_root": str(app_root()),
        "workspace": str(settings.paths.workspace_dir),
        "database": str(db.db_path()) if _db_ready() else "(not configured)",
        "state": str(user_state_dir()),
        "config": str(Path(app_root()) / "config" / "local.yaml"),
    }


def _db_ready() -> bool:
    try:
        db.db_path()
    except RuntimeError:
        return False
    return True
