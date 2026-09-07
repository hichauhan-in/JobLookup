"""Unattended searches.

A daemon thread that wakes once a minute and checks whether it is time. That is
enough for "run at 08:00 on weekdays" and avoids a dependency for something this
simple — APScheduler earns its place in a service with real cron semantics, not
in a single daily trigger.

The app has to be running for this to fire, which is stated plainly in the UI
rather than left for the user to discover.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any

from joblookup.config import Settings

Trigger = Callable[[], Any]


class Scheduler:
    def __init__(
        self,
        get_settings: Callable[[], Settings],
        trigger: Trigger,
        tick_hook: Trigger | None = None,
    ) -> None:
        self._get_settings = get_settings
        self._trigger = trigger
        self._tick_hook = tick_hook
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_fired: str = ""

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="joblookup-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def next_run(self) -> str:
        settings = self._get_settings().scheduler
        if not settings.enabled:
            return ""
        return f"{settings.hour:02d}:{settings.minute:02d}"

    def _loop(self) -> None:
        while not self._stop.wait(30):
            try:
                self._tick()
            except Exception:  # noqa: BLE001 - a bad tick must not kill the thread
                continue

    def _tick(self) -> None:
        if self._tick_hook:
            self._tick_hook()
        config = self._get_settings().scheduler
        if not config.enabled:
            return

        now = datetime.now()
        if config.weekdays and now.weekday() not in config.weekdays:
            return
        if now.hour != config.hour or now.minute != config.minute:
            return

        # One search per minute-slot, however many times the loop wakes inside it.
        slot = now.strftime("%Y-%m-%d %H:%M")
        if slot == self._last_fired:
            return
        self._last_fired = slot
        self._trigger()


def format_schedule(settings: Settings) -> str:
    config = settings.scheduler
    if not config.enabled:
        return "Off"
    days = "every day"
    if config.weekdays:
        names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        days = ", ".join(names[day] for day in sorted(config.weekdays) if 0 <= day < 7)
    return f"{config.hour:02d}:{config.minute:02d} {days} (only while JobLookup is running)"
