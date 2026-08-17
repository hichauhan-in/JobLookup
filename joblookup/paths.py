"""Where things live on disk.

Every path is derived from the repository root, so the whole tree — code, config,
vendored binaries and your own data — can be copied to another machine without
anything to reinstall or repoint.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

#: Env var that lets a packaged or relocated build say where it lives.
HOME_ENV = "JOBLOOKUP_HOME"
STATE_ENV = "JOBLOOKUP_STATE_DIR"


def app_root() -> Path:
    """The directory containing ``joblookup/``, ``config/`` and ``vendor/``."""
    override = os.environ.get(HOME_ENV)
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resolve(path: str | Path) -> Path:
    """Resolve ``path`` against the app root unless it is already absolute."""
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (app_root() / candidate).resolve()


def package_dir() -> Path:
    """The installed ``joblookup`` package, for reading bundled assets."""
    return Path(__file__).resolve().parent


def web_dir() -> Path:
    return package_dir() / "web"


def user_state_dir() -> Path:
    """Per-user directory for cross-process handshake files and local secrets.

    Deliberately outside the repo: it survives a re-clone and is never packaged.
    """
    base = os.environ.get(STATE_ENV)
    directory = Path(base).expanduser() if base else Path.home() / ".joblookup"
    directory.mkdir(parents=True, exist_ok=True)
    _restrict(directory)
    return directory


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def isolated_user_dir(root: Path, identity: str) -> Path:
    """A non-identifying, traversal-safe storage root for one authenticated user."""
    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    directory = root / "users" / key
    directory.mkdir(parents=True, exist_ok=True)
    _restrict(directory)
    return directory


def _restrict(path: Path) -> None:
    """Best-effort owner-only permissions. Windows ignores POSIX modes and
    inherits the profile ACL instead, which is already owner-only."""
    try:
        path.chmod(0o700)
    except OSError:
        pass
