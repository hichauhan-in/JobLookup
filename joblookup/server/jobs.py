"""Background jobs: a queue, a bridge from worker threads to WebSockets, and
enough bookkeeping for the UI to show what is running.

Three things matter here.

**Work is queued, not piled on.** Running two searches at once finishes both
later than running them in sequence, and running two scoring passes at once just
hits the model's rate limit. Jobs go into lanes with a fixed number of workers.

**Every job keeps a bounded ring of its events**, so a browser that connects late
— or reconnects after navigating away — replays the history rather than joining
mid-stream.

**Finished results are kept**, so walking away from a long search does not lose
what it found.
"""

from __future__ import annotations

import queue
import threading
import time
import traceback
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from joblookup.events import EventBus, EventType, ProgressEvent

MAX_EVENTS = 600

#: How many jobs may run at once in each lane.
LANES: dict[str, int] = {
    # Sources are polite and paced; one search at a time is the whole point.
    "search": 1,
    # Model calls wait on a network, but a burst runs into rate limits and, on a
    # Copilot seat, spends quota faster than anyone intends.
    "model": 1,
    # A visible browser window the user is typing into. Exactly one.
    "interactive": 1,
}

KIND_LANE: dict[str, str] = {
    "search": "search",
    "match": "model",
    "cv-extract": "model",
    "tailor": "model",
    "sign-in": "interactive",
    "test-selectors": "interactive",
    "provision": "search",
}

KIND_LABEL: dict[str, str] = {
    "search": "Searching sources",
    "match": "Matching against your profile",
    "cv-extract": "Reading your CV",
    "tailor": "Tailoring your CV",
    "sign-in": "Signing in",
    "test-selectors": "Testing selectors",
    "provision": "Installing",
}

#: Which screen a job belongs to, so the UI can send the user back to it.
KIND_VIEW: dict[str, str] = {
    "search": "dashboard",
    "match": "matches",
    "cv-extract": "profile",
    "tailor": "job",
    "sign-in": "sources",
    "test-selectors": "sources",
    "provision": "settings",
}

ACTIVE_STATUSES = {"queued", "running"}


def lane_for(kind: str) -> str:
    return KIND_LANE.get(kind, "search")


@dataclass
class Job:
    id: str
    kind: str
    lane: str = "search"
    view: str = ""
    label: str = ""
    status: str = "queued"  # queued | running | done | failed | cancelled
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    finished_at: float = 0.0
    stage: str = ""
    fraction: float | None = None
    message: str = ""
    events: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=MAX_EVENTS))
    finished: threading.Event = field(default_factory=threading.Event)
    cancel_requested: threading.Event = field(default_factory=threading.Event)
    _listeners: list[Callable[[dict[str, Any]], None]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    def elapsed(self) -> float:
        if not self.started_at:
            return 0.0
        return (self.finished_at or time.time()) - self.started_at

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "lane": self.lane,
            "view": self.view,
            "label": self.label or KIND_LABEL.get(self.kind, self.kind),
            "status": self.status,
            "stage": self.stage,
            "fraction": self.fraction,
            "message": self.message,
            "error": self.error,
            "meta": self.meta,
            "elapsed": round(self.elapsed(), 1),
            "created_at": self.created_at,
            "has_result": bool(self.result),
        }

    # --- event plumbing ----------------------------------------------------
    def emit(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self.events.append(payload)
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(payload)
            except Exception:  # noqa: BLE001
                pass

    def listen(self, listener: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        """Subscribe and replay everything that has already happened."""
        with self._lock:
            history = list(self.events)
            self._listeners.append(listener)
        for payload in history:
            try:
                listener(payload)
            except Exception:  # noqa: BLE001
                pass

        def stop() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return stop


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._queues: dict[str, queue.Queue] = {}
        self._lock = threading.Lock()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        for lane, workers in LANES.items():
            self._queues[lane] = queue.Queue()
            for index in range(workers):
                thread = threading.Thread(
                    target=self._worker,
                    args=(lane,),
                    name=f"joblookup-{lane}-{index}",
                    daemon=True,
                )
                thread.start()

    # --- submission --------------------------------------------------------
    def submit(
        self,
        kind: str,
        work: Callable[[EventBus, Job], dict[str, Any]],
        *,
        label: str = "",
        meta: dict[str, Any] | None = None,
        single: bool = True,
    ) -> Job:
        """Queue some work.

        ``single`` refuses a second job of the same kind while one is active,
        which is what stops an impatient double-click from running two searches.
        """
        lane = lane_for(kind)
        with self._lock:
            if single:
                for existing in self._jobs.values():
                    if existing.kind == kind and existing.active:
                        return existing

            job = Job(
                id=uuid.uuid4().hex[:12],
                kind=kind,
                lane=lane,
                view=KIND_VIEW.get(kind, ""),
                label=label or KIND_LABEL.get(kind, kind),
                meta=meta or {},
            )
            self._jobs[job.id] = job
            self._prune()

        job.emit({"type": "queued", "job": job.summary()})
        self._queues[lane].put((job, work))
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or not job.active:
            return False
        job.cancel_requested.set()
        job.message = "Stopping..."
        job.emit({"type": "cancelling", "job": job.summary()})
        return True

    def active(self) -> list[dict[str, Any]]:
        return [job.summary() for job in self._jobs.values() if job.active]

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        jobs = sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)
        return [job.summary() for job in jobs[:limit]]

    # --- execution ---------------------------------------------------------
    def _worker(self, lane: str) -> None:
        work_queue = self._queues[lane]
        while True:
            job, work = work_queue.get()
            try:
                self._run(job, work)
            finally:
                work_queue.task_done()

    def _run(self, job: Job, work: Callable[[EventBus, Job], dict[str, Any]]) -> None:
        if job.cancel_requested.is_set():
            job.status = "cancelled"
            job.finished_at = time.time()
            job.finished.set()
            job.emit({"type": "done", "job": job.summary()})
            return

        job.status = "running"
        job.started_at = time.time()
        job.emit({"type": "started", "job": job.summary()})

        bus = EventBus()

        def forward(event: ProgressEvent) -> None:
            if event.stage:
                job.stage = event.stage
            if event.fraction is not None:
                job.fraction = event.fraction
            if event.message:
                job.message = event.message
            job.emit({"type": "event", "event": event.to_dict(), "job": job.summary()})

        bus.subscribe(forward)

        try:
            job.result = work(bus, job) or {}
            job.status = "cancelled" if job.cancel_requested.is_set() else "done"
            job.fraction = 1.0
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.error = str(exc) or exc.__class__.__name__
            bus.publish(ProgressEvent(EventType.ERROR, job.stage, job.error))
            job.emit(
                {
                    "type": "event",
                    "event": {
                        "type": "error",
                        "stage": job.stage,
                        "message": job.error,
                        "fraction": None,
                        "data": {"traceback": traceback.format_exc()[-2000:]},
                    },
                    "job": job.summary(),
                }
            )
        finally:
            job.finished_at = time.time()
            job.finished.set()
            job.emit({"type": "done", "job": job.summary(), "result": job.result})

    def _prune(self, keep: int = 60) -> None:
        finished = sorted(
            (job for job in self._jobs.values() if not job.active),
            key=lambda job: job.finished_at,
        )
        for job in finished[: max(0, len(finished) - keep)]:
            self._jobs.pop(job.id, None)


manager = JobManager()
