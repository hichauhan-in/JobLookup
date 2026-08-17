"""API keys for the job boards that need one.

Preference order:

1. An environment variable — ``JOBLOOKUP_SECRET_<NAME>`` — so a key can be
   supplied for one run without being stored at all.
2. Windows Credential Manager (or the platform keyring), when the optional
   ``keyring`` package is installed.
3. An owner-only JSON file under ``~/.joblookup``.

A key is never written to ``config/local.yaml``, because that file is meant to
be readable, diffable and occasionally shared.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from joblookup.paths import user_state_dir

SERVICE = "JobLookup"
ENV_PREFIX = "JOBLOOKUP_SECRET_"
FALLBACK_NAME = "secrets.json"

#: Every secret the app knows about, so Settings can show what is and is not set
#: without any source having to be loaded.
KNOWN = (
    "adzuna_app_id",
    "adzuna_app_key",
    "jooble",
    "usajobs",
    "usajobs_email",
    "findwork",
    "reed",
)


def _keyring() -> Any | None:
    try:
        import keyring

        # A backend that cannot actually store anything reports itself as such.
        from keyring.backends.fail import Keyring as FailKeyring

        if isinstance(keyring.get_keyring(), FailKeyring):
            return None
        return keyring
    except Exception:  # noqa: BLE001
        return None


def _fallback_path() -> Path:
    return user_state_dir() / FALLBACK_NAME


def _read_fallback() -> dict[str, str]:
    path = _fallback_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(key): str(value) for key, value in data.items()} if isinstance(data, dict) else {}


def _write_fallback(values: dict[str, str]) -> None:
    path = _fallback_path()
    path.write_text(json.dumps(values, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        # Windows ignores POSIX modes; the profile directory ACL already applies.
        pass


def get(name: str) -> str:
    from_env = os.environ.get(f"{ENV_PREFIX}{name.upper()}", "").strip()
    if from_env:
        return from_env

    ring = _keyring()
    if ring is not None:
        try:
            value = ring.get_password(SERVICE, name)
            if value:
                return value.strip()
        except Exception:  # noqa: BLE001
            pass

    return _read_fallback().get(name, "").strip()


def set(name: str, value: str) -> None:  # noqa: A001 - the verb is the point
    value = (value or "").strip()
    ring = _keyring()
    if ring is not None:
        try:
            if value:
                ring.set_password(SERVICE, name, value)
            else:
                ring.delete_password(SERVICE, name)
            return
        except Exception:  # noqa: BLE001
            # Fall through to the file so a broken keyring backend does not lose
            # the user's key.
            pass

    values = _read_fallback()
    if value:
        values[name] = value
    else:
        values.pop(name, None)
    _write_fallback(values)


def clear(name: str) -> None:
    set(name, "")


def status() -> dict[str, Any]:
    """Which keys are present, and where they are being kept. Never the values."""
    ring = _keyring()
    return {
        "backend": "keyring" if ring is not None else "file",
        "backend_detail": (str(ring.get_keyring()) if ring is not None else str(_fallback_path())),
        "set": {name: bool(get(name)) for name in KNOWN},
    }
