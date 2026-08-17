"""Stage three: asking the model, in batches, and turning the answer into bands.

One call per job is the accurate, obvious, expensive design. Through a Copilot
seat it is also slow: a few hundred postings become a few hundred round trips.
Batching a dozen jobs into one call gives the same judgement for a twentieth of
the calls, because the task is scoring against a fixed candidate rather than
open-ended reasoning about each posting in isolation.

Two properties make batching safe:

* The reply is keyed by the job id we supplied, never by position. A model that
  drops, reorders or invents an entry costs that one score and nothing else.
* Any job missing from a reply is retried in a smaller batch, and only then
  given up on.

``matching.score_batch_size`` is a setting for exactly this reason: set it to 1
for maximum accuracy, raise it to spend less.
"""

from __future__ import annotations

from typing import Any

from joblookup import prompts
from joblookup.config import Settings
from joblookup.events import EventBus
from joblookup.llm import LLMClient
from joblookup.llm.base import LLMError, LLMUnavailableError
from joblookup.models import Score


def composite_score(direct: float, transferable: float, growth: float, settings: Settings) -> float:
    matching = settings.matching
    return (
        direct * matching.weight_direct
        + transferable * matching.weight_transferable
        + growth * matching.weight_growth
    )


def assign_band(composite: float, blocker: str | None, settings: Settings) -> str:
    if blocker:
        return "rejected"
    matching = settings.matching
    if composite >= matching.strong_threshold:
        return "strong"
    if composite >= matching.good_threshold:
        return "good"
    if composite >= matching.stretch_threshold:
        return "stretch"
    return "rejected"


def score_jobs(
    profile: dict[str, Any],
    jobs: list[dict[str, Any]],
    client: LLMClient,
    settings: Settings,
    bus: EventBus,
    profile_version: int,
    *,
    cancelled: Any = lambda: False,
) -> list[Score]:
    if not jobs:
        return []

    batch_size = max(1, settings.matching.score_batch_size)
    model = client.model
    scores: list[Score] = []
    missing: list[dict[str, Any]] = []
    done = 0

    for start in range(0, len(jobs), batch_size):
        if cancelled():
            break
        batch = jobs[start : start + batch_size]
        try:
            produced = _score_batch(profile, batch, client, settings, profile_version, model)
        except LLMUnavailableError:
            raise
        except LLMError as exc:
            bus.warn(f"A batch of {len(batch)} could not be scored: {exc}", stage="score")
            produced = {}

        for job in batch:
            score = produced.get(str(job["id"]))
            if score is None:
                missing.append(job)
            else:
                scores.append(score)

        done += len(batch)
        bus.progress("score", done / len(jobs), f"{done}/{len(jobs)} judged")

    # A model that skipped entries in a large batch usually manages them alone.
    if missing and not cancelled():
        bus.log(f"Retrying {len(missing)} posting(s) individually.", stage="score")
        for job in missing:
            if cancelled():
                break
            try:
                produced = _score_batch(profile, [job], client, settings, profile_version, model)
            except LLMError as exc:
                bus.warn(
                    f"{job.get('title', 'A posting')} could not be scored: {exc}", stage="score"
                )
                continue
            score = produced.get(str(job["id"]))
            if score is not None:
                scores.append(score)

    return scores


def _score_batch(
    profile: dict[str, Any],
    batch: list[dict[str, Any]],
    client: LLMClient,
    settings: Settings,
    profile_version: int,
    model: str,
) -> dict[str, Score]:
    payload = client.complete_json(
        prompts.SCORE_SYSTEM,
        prompts.score_user(profile, batch, settings.matching.description_chars),
        temperature=0.1,
        max_tokens=900 + 320 * len(batch),
    )
    entries = payload.get("scores") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise LLMError("The model did not return a list of scores.")

    wanted = {str(job["id"]): job for job in batch}
    results: dict[str, Score] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        job_id = str(entry.get("id") or "").strip()
        job = wanted.get(job_id)
        if job is None:
            # An id we never sent is a hallucination; dropping it is the whole
            # reason the reply is keyed rather than positional.
            continue
        results[job_id] = _build_score(entry, job, settings, profile_version, model)
    return results


def _build_score(
    entry: dict[str, Any],
    job: dict[str, Any],
    settings: Settings,
    profile_version: int,
    model: str,
) -> Score:
    direct = _clamp(entry.get("direct_fit"))
    transferable = _clamp(entry.get("transferable_fit"))
    growth = _clamp(entry.get("growth_fit"))
    blocker = _blocker(entry.get("blocker"))
    composite = composite_score(direct, transferable, growth, settings)

    return Score(
        job_id=int(job["id"]),
        profile_version=profile_version,
        recall_score=float(job.get("recall_score") or 0.0),
        direct_fit=direct,
        transferable_fit=transferable,
        growth_fit=growth,
        composite=composite,
        band=assign_band(composite, blocker, settings),
        rationale=str(entry.get("rationale") or "").strip()[:800],
        matched_skills=_strings(entry.get("matched_skills")),
        learnable_gaps=_strings(entry.get("learnable_gaps")),
        hard_gaps=_strings(entry.get("hard_gaps")),
        blocker=blocker,
        model=model,
    )


def _clamp(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _blocker(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"null", "none", "false", "n/a", "-"}:
        return None
    return text[:200]


def _strings(value: Any, limit: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:limit]
