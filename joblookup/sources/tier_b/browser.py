"""Browser plumbing for the logged-in portals.

Everything here is deliberately conservative, because this is the one part of
JobLookup that can get a real account restricted:

* Playwright is imported lazily. It is an optional extra and a ~130 MB Chromium
  download, so a user who never enables a portal never pays for it.
* You sign in yourself, in a visible window, once. JobLookup has no field for a
  password and never sees one. The session cookie stays in a local profile
  directory that belongs to your user account.
* Actions are paced with randomised human-scale delays, page counts are bounded,
  and there is a daily run cap plus a global kill switch.

There is no CAPTCHA solving and no 2FA circumvention, and there will not be.
"""

from __future__ import annotations

import json
import random
import re
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from joblookup.config import Settings
from joblookup.db import session as db
from joblookup.paths import ensure_dir

_profile_locks: dict[str, threading.Lock] = {}
_profile_locks_guard = threading.Lock()


class TierBDisabled(RuntimeError):
    """The master switch is off."""


class TierBBlocked(RuntimeError):
    """This portal is not allowed to run right now, and the user can fix it."""


class PlaywrightMissing(RuntimeError):
    """Playwright is not installed, or its browser has not been downloaded."""


def profiles_root(settings: Settings) -> Path:
    return ensure_dir(settings.paths.workspace_dir / "browser_profiles")


def _profile_path(settings: Settings, portal_key: str) -> Path:
    if not re.fullmatch(r"[a-z0-9_-]+", portal_key):
        raise ValueError("Invalid portal identifier.")
    return settings.paths.workspace_dir / "browser_profiles" / portal_key


def profile_dir(settings: Settings, portal_key: str) -> Path:
    return ensure_dir(_profile_path(settings, portal_key))


@contextmanager
def session_access(settings: Settings, portal_key: str):
    key = str(_profile_path(settings, portal_key).resolve())
    with _profile_locks_guard:
        lock = _profile_locks.setdefault(key, threading.Lock())
    if not lock.acquire(blocking=False):
        raise TierBBlocked(f"{portal_key}: another browser operation is using this session.")
    try:
        yield
    finally:
        lock.release()


def has_session(settings: Settings, portal_key: str) -> bool:
    return session_state(settings, portal_key).get("authenticated") is True


def session_state(settings: Settings, portal_key: str) -> dict[str, Any]:
    marker = _profile_path(settings, portal_key) / ".session.json"
    try:
        state = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"authenticated": False}
    return state if isinstance(state, dict) else {"authenticated": False}


def record_session(settings: Settings, portal_key: str, *, authenticated: bool) -> None:
    marker = profile_dir(settings, portal_key) / ".session.json"
    marker.write_text(
        json.dumps(
            {"authenticated": authenticated, "checked_at": datetime.now(timezone.utc).isoformat()}
        ),
        encoding="utf-8",
    )


def clear_session(settings: Settings, portal_key: str) -> None:
    import shutil

    with session_access(settings, portal_key):
        directory = _profile_path(settings, portal_key)
        if directory.exists():
            shutil.rmtree(directory)


# --- availability ------------------------------------------------------------
_availability: dict[str, Any] | None = None
_availability_lock = threading.Lock()


def availability(*, refresh: bool = False) -> dict[str, Any]:
    """Whether portal automation could run, and what is missing if not.

    Cached, because probing it starts a Playwright driver process: the Sources
    screen asks once for the section and once per acknowledged portal, so an
    uncached answer spawned ten Node processes per page load. The result only
    changes when something is installed, and that path passes ``refresh``.
    """
    global _availability
    with _availability_lock:
        if _availability is None or refresh:
            _availability = _probe()
        return _availability


def _probe() -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return {
            "installed": False,
            "browser_ready": False,
            "detail": "Playwright is not installed.",
            "fix": ".\\.venv\\Scripts\\python.exe -m pip install playwright",
        }

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            path = playwright.chromium.executable_path
        ready = bool(path) and Path(path).exists()
    except Exception as exc:  # noqa: BLE001
        return {
            "installed": True,
            "browser_ready": False,
            "detail": f"Chromium is not available: {exc}",
            "fix": ".\\.venv\\Scripts\\python.exe -m playwright install chromium",
        }

    return {
        "installed": True,
        "browser_ready": ready,
        "detail": "Ready" if ready else "Chromium has not been downloaded yet.",
        "fix": "" if ready else ".\\.venv\\Scripts\\python.exe -m playwright install chromium",
    }


def require_playwright() -> Any:
    state = availability()
    if not state["installed"]:
        raise PlaywrightMissing(
            "Portal automation needs Playwright, which is not installed. "
            "Install it from the Sources screen, or run: " + state["fix"]
        )
    if not state["browser_ready"]:
        raise PlaywrightMissing(
            "Playwright is installed but its Chromium browser has not been "
            "downloaded. Run: " + state["fix"]
        )
    from playwright.sync_api import sync_playwright

    return sync_playwright


# --- pacing and caps ---------------------------------------------------------
def human_pause(settings: Settings) -> None:
    """Pace requests to avoid burdening the portal."""
    low = max(0.5, settings.tier_b.min_action_delay_s)
    high = max(low + 0.5, settings.tier_b.max_action_delay_s)
    time.sleep(random.uniform(low, high))


def _cap_key(portal_key: str) -> str:
    return f"tier_b_runs:{portal_key}:{date.today().isoformat()}"


def runs_today(portal_key: str) -> int:
    return int(db.get_setting(_cap_key(portal_key), "0") or 0)


def check_daily_cap(settings: Settings, portal_key: str) -> None:
    cap = max(1, settings.tier_b.daily_run_cap)
    used = runs_today(portal_key)
    if used >= cap:
        raise TierBBlocked(
            f"{portal_key} has already run {used} times today, which is the cap "
            f"(tier_b.daily_run_cap = {cap}). It will reset tomorrow."
        )


def record_run(portal_key: str) -> None:
    db.set_setting(_cap_key(portal_key), str(runs_today(portal_key) + 1))


# --- contexts ----------------------------------------------------------------
def launch_context(settings: Settings, portal_key: str, *, headless: bool | None = None):
    """A persistent Chromium context that remembers the portal sign-in.

    Returns ``(playwright, context)``; the caller is responsible for closing
    both, in that order.
    """
    sync_playwright = require_playwright()
    playwright = sync_playwright().start()
    try:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir(settings, portal_key)),
            headless=settings.tier_b.headless if headless is None else headless,
            viewport={"width": 1440, "height": 900},
            locale="en-GB",
        )
    except Exception:
        playwright.stop()
        raise
    context.set_default_timeout(settings.tier_b.nav_timeout_s * 1000)
    return playwright, context


def sign_in(
    settings: Settings,
    portal_key: str,
    login_url: str,
    *,
    authenticated: Callable[[Any, Any], bool],
    cancelled: Callable[[], bool] = lambda: False,
    timeout_s: float = 600,
) -> dict[str, Any]:
    """Let the user authenticate directly with the portal, then verify the session."""
    with session_access(settings, portal_key):
        playwright, context = launch_context(settings, portal_key, headless=False)
        confirmed = False
        stopped = False
        expired = False
        closed = False

        def on_close(*args):
            nonlocal closed
            closed = True

        context.on("close", on_close)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(login_url, wait_until="domcontentloaded")
            deadline = time.monotonic() + timeout_s
            while not closed:
                if cancelled():
                    stopped = True
                    break
                if authenticated(page, context):
                    confirmed = True
                    break
                if time.monotonic() >= deadline:
                    expired = True
                    break
                if page.is_closed():
                    break
                page.wait_for_timeout(400)
        except Exception as exc:
            if not closed:
                raise TierBBlocked(
                    f"{portal_key}: sign-in could not be completed ({type(exc).__name__})."
                ) from exc
        finally:
            try:
                if not closed:
                    context.close()
            finally:
                playwright.stop()
                record_session(settings, portal_key, authenticated=confirmed)
        detail = (
            "Sign-in verified. The browser session is stored locally."
            if confirmed
            else "Sign-in cancelled."
            if stopped
            else "Sign-in timed out. Try again when you are ready."
            if expired
            else "The browser closed before sign-in could be verified."
        )
        return {"portal": portal_key, "session_saved": confirmed, "detail": detail}
