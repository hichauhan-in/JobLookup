"""Bounded query coverage with explicit partial-result accounting."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace

from joblookup.models import RawJob
from joblookup.sources.base import FetchContext, SourceError, as_list

QUERY_SOURCES = {"adzuna", "jooble", "usajobs", "reed", "jsearch", "remotive", "workday"}
MAX_COMBINATIONS = 24


def combinations(context: FetchContext) -> list[tuple[str, str]]:
    pending = context.config.get("_pending_queries")
    if pending:
        return [(str(entry["query"]), str(entry["location"])) for entry in pending]
    terms = list(
        dict.fromkeys([*context.queries, *as_list(context.config.get("extra_terms"))])
    ) or [""]
    locations = list(dict.fromkeys(context.locations)) or [""]
    return [(term, location) for term in terms for location in locations]


def execute_plan(
    context: FetchContext, fetch: Callable[[FetchContext], list[RawJob]]
) -> list[RawJob]:
    from joblookup.sources.tier_b.browser import TierBBlocked

    plan = combinations(context)
    budget = min(MAX_COMBINATIONS, max(1, context.limit))
    per_query = max(1, math.ceil(context.limit / min(len(plan), budget)))
    jobs: dict[str, RawJob] = {}
    stopped = ""
    for index, (term, location) in enumerate(plan):
        report = {"query": term, "location": location, "status": "pending", "count": 0}
        context.search_report.append(report)
        reason = stopped or (
            "cancelled"
            if context.cancelled()
            else "query budget"
            if index >= budget
            else "result limit"
            if len(jobs) >= context.limit
            else ""
        )
        if reason:
            report.update(status="skipped", reason=reason)
            continue
        settings = context.settings.model_copy(deep=True)
        settings.search.max_jobs_per_source = min(per_query, context.limit - len(jobs))
        child = replace(
            context,
            settings=settings,
            queries=[term],
            locations=[location],
            config=context.config | {"extra_terms": []},
        )
        context.log(f"Searching {term or 'latest jobs'} / {location or 'all locations'}")
        try:
            found = fetch(child)
        except (SourceError, TierBBlocked) as exc:
            report.update(status="failed", reason=str(exc))
            stopped = "source refused or failed; remaining requests stopped"
            continue
        report.update(status="complete", count=len(found))
        if child.stop_reason:
            report.update(status="partial", reason=child.stop_reason)
            stopped = "source blocked detail access; remaining requests stopped"
        for job in found:
            key = job.source_job_id or job.url or f"{job.title}|{job.company}|{job.location}"
            existing = jobs.get(key)
            if not existing or len(job.description) > len(existing.description):
                jobs[key] = job
    return list(jobs.values())[: context.limit]
