"""The matching run, end to end.

Three stages, each cheaper than the one after it:

    everything stored  →  recall  →  prefilter  →  the model  →  bands

The shape is the whole cost story. Recall touches an index, not the model.
Prefilter applies rules the user already stated, for free. Only what survives
both reaches a Copilot call, and even then a dozen postings share one call.

Every threshold in here is a setting, because the right trade-off between
coverage and quota is a personal one.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from joblookup import store
from joblookup.config import Settings
from joblookup.cv.profile import profile_text
from joblookup.events import EventBus
from joblookup.llm import LLMClient
from joblookup.llm.base import LLMUnavailableError
from joblookup.matching.prefilter import prefilter
from joblookup.matching.recall import recall
from joblookup.matching.rerank import score_jobs

Cancelled = Callable[[], bool]


class ProfileMissing(RuntimeError):
    """There is nothing to match against yet."""


def run_matching(
    settings: Settings,
    client: LLMClient,
    bus: EventBus,
    *,
    cancelled: Cancelled = lambda: False,
) -> dict[str, Any]:
    profile_row = store.get_profile()
    profile = profile_row.get("data") or {}
    version = int(profile_row.get("version") or 1)

    if not profile.get("skills") and not profile.get("target_titles"):
        raise ProfileMissing(
            "There is no profile to match against yet. Upload a CV, or fill in the "
            "target titles on the Profile screen."
        )

    summary_text = profile_text(profile)

    # --- stage 1: recall ---------------------------------------------------
    bus.stage_start("recall", "Finding candidates")
    ranked, mode = recall(summary_text, client, settings, bus)
    how = "vector similarity" if mode == "vector" else "keyword match"
    bus.stage_end(
        "recall",
        f"{len(ranked)} candidate(s) by {how}",
        count=len(ranked),
        mode=mode,
    )
    if not ranked:
        return {
            "scored": 0,
            "recalled": 0,
            "considered": 0,
            "mode": mode,
            "dropped": {},
            "message": "Nothing matched your profile closely enough. Run a search first, "
            "or widen matching.recall_min_score in Settings.",
        }

    scores_by_id = dict(ranked)
    candidates = store.jobs_for_scoring(
        job_ids=[job_id for job_id, _ in ranked],
        profile_version_value=version,
        rescore=settings.matching.rescore_existing,
    )
    for job in candidates:
        job["recall_score"] = scores_by_id.get(int(job["id"]), 0.0)

    if not candidates:
        return {
            "scored": 0,
            "recalled": len(ranked),
            "considered": 0,
            "mode": mode,
            "dropped": {},
            "message": "Everything relevant has already been scored against this profile. "
            "Turn on matching.rescore_existing to judge them again.",
        }

    # --- stage 2: prefilter ------------------------------------------------
    bus.stage_start("prefilter", "Applying your own rules")
    kept, dropped = prefilter(candidates, profile, settings)
    bus.stage_end(
        "prefilter",
        f"{len(kept)} to judge, {sum(dropped.values())} ruled out for free",
        kept=len(kept),
        dropped=dropped,
    )
    if not kept:
        return {
            "scored": 0,
            "recalled": len(ranked),
            "considered": 0,
            "mode": mode,
            "dropped": dropped,
            "message": "Everything was ruled out by your own filters. Relax the work "
            "mode, seniority or exclusion settings on the Profile screen.",
        }

    # --- stage 3: the model ------------------------------------------------
    batches = -(-len(kept) // max(1, settings.matching.score_batch_size))
    bus.stage_start("score", f"Judging {len(kept)} posting(s) in {batches} model call(s)")
    try:
        scores = score_jobs(profile, kept, client, settings, bus, version, cancelled=cancelled)
    except LLMUnavailableError as exc:
        bus.warn(str(exc), stage="score")
        raise

    store.save_scores(scores)
    bands: dict[str, int] = {}
    for score in scores:
        bands[score.band] = bands.get(score.band, 0) + 1
    bus.stage_end(
        "score",
        ", ".join(f"{count} {band}" for band, count in sorted(bands.items())) or "nothing scored",
        **bands,
    )

    return {
        "scored": len(scores),
        "recalled": len(ranked),
        "considered": len(kept),
        "mode": mode,
        "dropped": dropped,
        "bands": bands,
        "model_calls": batches,
    }
