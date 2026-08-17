"""Stage two: throwing away what the model does not need to see.

This costs nothing and runs before a single token is spent. It exists because a
model call that concludes "this Berlin-only role is not for you, you said remote
in the UK" is a call that never needed to happen.

Everything here is a rule the user stated, not a judgement. Anything requiring
judgement is left for the model, which is the whole point of the split.
"""

from __future__ import annotations

from typing import Any

from joblookup.config import Settings
from joblookup.models import seniority_rank
from joblookup.sources import regions
from joblookup.sources.normalize import age_days


def prefilter(
    jobs: list[dict[str, Any]],
    profile: dict[str, Any],
    settings: Settings,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Return ``(kept, reasons_dropped)``."""
    matching = settings.matching
    if not matching.prefilter_enabled:
        return jobs[: matching.prefilter_keep], {}

    dropped = {
        "too_senior": 0,
        "too_junior": 0,
        "excluded": 0,
        "work_mode": 0,
        "not_remote": 0,
        "stale": 0,
    }
    exclusions = [
        str(item).strip().lower() for item in profile.get("exclusions") or [] if str(item).strip()
    ]
    accepted_modes = {str(mode).strip().lower() for mode in profile.get("work_modes") or []}
    profile_rank = seniority_rank(profile.get("seniority"))
    recency = int(profile.get("recency_days") or settings.search.recency_days)
    # Either the pack says remote-only, or the user asked for it on top of a country.
    remote_only = settings.search.remote_only or regions.resolve(settings.search.region).remote_only

    kept: list[dict[str, Any]] = []
    for job in jobs:
        haystack = f"{job.get('title', '')} {job.get('company', '')}".lower()
        if exclusions and any(term in haystack for term in exclusions):
            dropped["excluded"] += 1
            continue

        # The remote pack means remote, so anything not positively identified
        # as remote goes. Unknown is treated as not-remote here, which is the
        # opposite of the rule below, because a posting that never mentions
        # working from home almost never is.
        if remote_only and str(job.get("work_mode") or "unknown").lower() != "remote":
            dropped["not_remote"] += 1
            continue

        if accepted_modes:
            mode = str(job.get("work_mode") or "unknown").lower()
            # "unknown" is missing data, not a mismatch — dropping it would hide
            # every posting from a source that does not publish the field.
            if mode != "unknown" and mode not in accepted_modes:
                dropped["work_mode"] += 1
                continue

        if profile_rank >= 0:
            job_rank = seniority_rank(job.get("seniority"))
            if job_rank >= 0:
                gap = job_rank - profile_rank
                if gap > matching.max_seniority_jump:
                    dropped["too_senior"] += 1
                    continue
                # Two levels down is a real demotion and rarely what anyone wants.
                if gap < -2:
                    dropped["too_junior"] += 1
                    continue

        age = age_days(job.get("posted_at"))
        if age is not None and age > recency:
            dropped["stale"] += 1
            continue

        kept.append(job)

    kept.sort(key=lambda job: _priority(job, recency), reverse=True)
    return kept[: matching.prefilter_keep], {key: value for key, value in dropped.items() if value}


def _priority(job: dict[str, Any], recency_days: int) -> float:
    """Recall score, nudged by freshness.

    A posting from this morning and one from six days ago with the same textual
    fit are not equally worth a model call — the fresher one is far more likely
    to still be open.
    """
    score = float(job.get("recall_score") or 0.0)
    age = age_days(job.get("posted_at"))
    if age is None:
        return score
    freshness = max(0.0, 1.0 - (age / max(1, recency_days)))
    return score + 0.15 * freshness
