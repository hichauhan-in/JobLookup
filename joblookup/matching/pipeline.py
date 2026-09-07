"""Local matching is always available; AI review is a separate, explicit action."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from joblookup import store
from joblookup.config import Settings
from joblookup.events import EventBus
from joblookup.llm import LLMClient
from joblookup.matching.evidence import ENGINE_VERSION, evaluate_job
from joblookup.models import Score

Cancelled = Callable[[], bool]


class ProfileMissing(RuntimeError):
    """There is nothing to match against yet."""


def run_matching(
    settings: Settings,
    client: LLMClient | None,
    bus: EventBus,
    *,
    cancelled: Cancelled = lambda: False,
) -> dict[str, Any]:
    profile_row = store.get_profile()
    profile = profile_row.get("data") or {}
    version = int(profile_row.get("version") or 1)
    if not profile.get("target_titles"):
        raise ProfileMissing("Add at least one target role in your profile before matching.")
    candidates = [job for job in store.match_candidates() if not job["hidden"]]
    bus.stage_start("score", f"Checking {len(candidates)} postings against your profile")
    scores = []
    bands: dict[str, int] = {}
    for index, job in enumerate(candidates):
        if cancelled():
            break
        fit = evaluate_job(job, profile, recency_days=settings.search.recency_days)
        bands[fit["band"]] = bands.get(fit["band"], 0) + 1
        scores.append(
            Score(
                job_id=job["id"],
                profile_version=version,
                composite=fit["score"] / 100,
                band={"review": "stretch", "excluded": "rejected"}.get(fit["band"], fit["band"]),
                rationale=fit["summary"],
                matched_skills=[entry["skill"] for entry in fit["matched_skills"]],
                blocker=" ".join(fit["blockers"]) or None,
                model=ENGINE_VERSION,
            )
        )
        if index % 50 == 0:
            bus.progress(
                "score", index / max(1, len(candidates)), f"{index}/{len(candidates)} checked"
            )
    if store.profile_version() == version:
        store.save_scores(scores)
    bus.stage_end("score", f"{len(scores)} postings checked locally", **bands)
    return {
        "scored": len(scores),
        "recalled": len(candidates),
        "considered": len(candidates),
        "mode": "local",
        "dropped": {"ineligible": bands.get("excluded", 0)},
        "bands": bands,
        "model_calls": 0,
        "budget": None,
    }
