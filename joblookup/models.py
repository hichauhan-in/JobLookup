"""The shapes that move between layers.

Source adapters produce :class:`RawJob`. Normalisation turns that into
:class:`NormalizedJob`, which is what reaches the database. Matching produces
:class:`Score`. Nothing else needs to agree on a format.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

WORK_MODES = ("remote", "hybrid", "onsite", "unknown")
EMPLOYMENT_TYPES = ("full-time", "part-time", "contract", "internship", "temporary", "unknown")

#: Ordered so "how far above me is this posting" is a subtraction.
SENIORITY_LADDER = ("intern", "junior", "mid", "senior", "lead", "principal", "director")

BANDS = ("strong", "good", "stretch", "rejected")
APPLICATION_STATUSES = (
    "saved",
    "considering",
    "applied",
    "interviewing",
    "offer",
    "rejected",
    "withdrawn",
)


def seniority_rank(value: str | None) -> int:
    """Position on the ladder, or ``-1`` when unknown."""
    if not value:
        return -1
    try:
        return SENIORITY_LADDER.index(value.strip().lower())
    except ValueError:
        return -1


@dataclass(slots=True)
class RawJob:
    """Exactly what a source gave us, before any interpretation."""

    source_key: str
    source_job_id: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""
    url: str = ""
    apply_url: str = ""
    posted_at: str | None = None
    work_mode: str = ""
    employment: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedJob:
    """A posting after cleaning, classification and fingerprinting."""

    fingerprint: str
    title: str
    title_norm: str
    company: str
    company_norm: str
    location: str
    location_norm: str
    country: str = ""
    work_mode: str = "unknown"
    employment: str = "unknown"
    seniority: str = ""
    description: str = ""
    url: str = ""
    apply_url: str = ""
    posted_at: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = ""
    source_key: str = ""
    source_job_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def searchable(self) -> str:
        """The text recall and embeddings actually look at."""
        parts = [self.title, self.company, self.location, self.seniority, self.description]
        return "\n".join(part for part in parts if part)


@dataclass(slots=True)
class Score:
    """One job judged against the profile."""

    job_id: int
    profile_version: int = 1
    recall_score: float = 0.0
    direct_fit: float = 0.0
    transferable_fit: float = 0.0
    growth_fit: float = 0.0
    composite: float = 0.0
    band: str = "stretch"
    rationale: str = ""
    matched_skills: list[str] = field(default_factory=list)
    learnable_gaps: list[str] = field(default_factory=list)
    hard_gaps: list[str] = field(default_factory=list)
    blocker: str | None = None
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SourceResult:
    """What one source produced in one run."""

    key: str
    status: str = "ok"  # ok | empty | skipped | failed
    jobs: list[RawJob] = field(default_factory=list)
    error: str = ""
    detail: str = ""

    @property
    def count(self) -> int:
        return len(self.jobs)


@dataclass(slots=True)
class CrawlStats:
    fetched: int = 0
    kept: int = 0
    new: int = 0
    updated: int = 0
    duplicates: int = 0
    too_old: int = 0
    thin: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
