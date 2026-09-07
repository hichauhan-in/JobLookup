"""Running a search: ask every enabled source, then reconcile the answers.

Sources are fetched concurrently because they are all network-bound and none of
them care about each other. Everything after that is sequential and single
threaded, because it writes to SQLite and because the deduplication decision for
one posting depends on the postings already stored.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from joblookup import store
from joblookup.config import Settings
from joblookup.db import session as db
from joblookup.events import EventBus
from joblookup.models import CrawlStats, NormalizedJob, RawJob, SourceResult
from joblookup.sources import normalize as norm
from joblookup.sources import registry
from joblookup.sources.base import SourceAdapter, SourceError
from joblookup.sources.tier_b.browser import PlaywrightMissing, TierBBlocked, TierBDisabled

Cancelled = Callable[[], bool]


def profile_queries(settings: Settings) -> tuple[list[str], list[str]]:
    """The titles and places the keyed APIs should search for.

    Falls back to nothing rather than to a guess: a source asked for "" returns
    its newest postings, which is a reasonable answer. A source asked for a
    wrong keyword returns confidently irrelevant results.
    """
    profile = store.get_profile().get("data") or {}
    titles = [str(item).strip() for item in profile.get("target_titles") or [] if str(item).strip()]
    locations = [str(item).strip() for item in profile.get("locations") or [] if str(item).strip()]
    return titles[:5], locations[:3]


def fetch_one(
    adapter: SourceAdapter,
    settings: Settings,
    queries: list[str],
    locations: list[str],
    bus: EventBus,
    cancelled: Cancelled,
) -> SourceResult:
    context = registry.context_for(
        adapter.key,
        settings,
        queries=queries,
        locations=locations,
        log=lambda message: bus.log(message, stage="fetch"),
        cancelled=cancelled,
    )
    ready, reason = adapter.is_configured(context)
    if not ready:
        return SourceResult(adapter.key, status="skipped", detail=reason)

    try:
        jobs = adapter.fetch(context)
    except TierBDisabled as exc:
        return SourceResult(adapter.key, status="skipped", detail=str(exc))
    except (TierBBlocked, PlaywrightMissing) as exc:
        return SourceResult(adapter.key, status="failed", error=str(exc))
    except SourceError as exc:
        return SourceResult(adapter.key, status="failed", error=str(exc))
    except Exception as exc:  # noqa: BLE001
        return SourceResult(adapter.key, status="failed", error=f"{type(exc).__name__}: {exc}")

    return SourceResult(adapter.key, status="ok" if jobs else "empty", jobs=jobs)


def run_crawl(
    settings: Settings,
    bus: EventBus,
    *,
    source_keys: list[str] | None = None,
    cancelled: Cancelled = lambda: False,
) -> CrawlStats:
    registry.sync_source_table()
    adapters = [
        adapter
        for adapter in registry.enabled_adapters()
        if not source_keys or adapter.key in source_keys
    ]
    if not adapters:
        bus.warn("No sources are enabled. Turn some on from the Sources screen.")
        return CrawlStats()

    queries, locations = profile_queries(settings)
    run_id = store.start_run([adapter.key for adapter in adapters])
    stats = CrawlStats()

    # --- fetch ------------------------------------------------------------
    bus.stage_start("fetch", f"Asking {len(adapters)} source(s)")
    results: list[SourceResult] = []
    workers = max(1, min(settings.search.max_concurrent_sources, len(adapters)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="joblookup-fetch") as pool:
        futures = {
            pool.submit(fetch_one, adapter, settings, queries, locations, bus, cancelled): adapter
            for adapter in adapters
        }
        for done, future in enumerate(as_completed(futures), start=1):
            adapter = futures[future]
            result = future.result()
            results.append(result)
            registry.record_result(result.key, result.status, result.count, result.error)

            stats.by_source[result.key] = result.count
            if result.status == "failed":
                stats.failures[result.key] = result.error
                bus.warn(f"{adapter.name}: {result.error}", stage="fetch")
            elif result.status == "skipped":
                bus.log(f"{adapter.name}: skipped — {result.detail}", stage="fetch")
            else:
                bus.log(f"{adapter.name}: {result.count} posting(s)", stage="fetch")
            bus.progress("fetch", done / len(adapters), f"{done}/{len(adapters)} sources")

    stats.fetched = sum(result.count for result in results)
    bus.stage_end("fetch", f"{stats.fetched} posting(s) fetched", fetched=stats.fetched)

    if cancelled():
        store.finish_run(run_id, status="cancelled", stats=stats.to_dict())
        return stats

    # --- reconcile ---------------------------------------------------------
    bus.stage_start("ingest", "Cleaning up and removing duplicates")
    raw_jobs = [job for result in results for job in result.jobs]
    produced: dict[int, bool] = {}
    for index, raw in enumerate(raw_jobs, start=1):
        if cancelled():
            break
        kept = ingest_one(raw, settings, stats)
        if kept is not None:
            job_id, is_new = kept
            # A posting seen twice in one run is new only if it was new the first time.
            produced[job_id] = produced.get(job_id, False) or is_new
        if index % 25 == 0:
            bus.progress("ingest", index / max(1, len(raw_jobs)), f"{index}/{len(raw_jobs)}")

    store.link_run_jobs(run_id, produced)

    archived = store.archive_stale(settings.search.archive_after_days)
    bus.stage_end(
        "ingest",
        f"{stats.new} new, {stats.updated} updated, {stats.duplicates} duplicate, "
        f"{stats.too_old} too old, {stats.thin} too thin",
        **stats.to_dict(),
    )
    if archived:
        bus.log(f"Archived {archived} posting(s) not seen for a while.", stage="ingest")

    status = (
        "failed" if stats.failures and not stats.kept else ("partial" if stats.failures else "ok")
    )
    store.finish_run(run_id, status=status, stats=stats.to_dict())
    return stats


def ingest_one(raw: RawJob, settings: Settings, stats: CrawlStats) -> tuple[int, bool] | None:
    """Normalise one posting and store it.

    Returns ``(job_id, was_new)`` for anything kept, so the caller can record
    which postings a run produced, and ``None`` for anything dropped.
    """
    job = norm.normalize(raw)
    if not job.title or not job.company_norm:
        stats.thin += 1
        return None

    age = norm.age_days(job.posted_at)
    if age is not None and age > settings.search.recency_days:
        stats.too_old += 1
        return None

    # Some sources genuinely publish no description. A title with a company and a
    # link is still worth keeping; a title with neither is not.
    if len(job.description) < settings.search.min_description_chars and not job.url:
        stats.thin += 1
        return None

    from joblookup.matching.dedupe import find_duplicate

    siblings = store.find_by_company(job.company_norm)
    duplicate_id = find_duplicate(job, siblings, settings.matching.dedupe)
    if duplicate_id is not None:
        _attach_source(duplicate_id, job)
        stats.duplicates += 1
        stats.kept += 1
        return duplicate_id, False

    job_id, is_new = store.upsert_job(job)
    stats.kept += 1
    if is_new:
        stats.new += 1
    else:
        stats.updated += 1
    return job_id, is_new


def _attach_source(job_id: int, job: NormalizedJob) -> None:
    """Record that an existing posting was also seen somewhere else.

    This is the whole visible payoff of deduplication: one card, five links. The
    stored copy is also upgraded where the new sighting is better — aggregators
    truncate descriptions, and a re-listing is not a new job, so the longest
    description and the earliest posting date win.
    """
    with db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO job_source (job_id, source_key, source_job_id, url, raw)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(job_id, source_key) DO UPDATE SET
                url = excluded.url, seen_at = datetime('now')
            """,
            (
                job_id,
                job.source_key,
                job.source_job_id,
                job.url,
                json.dumps(job.raw, ensure_ascii=False)[:20000],
            ),
        )
        conn.execute(
            """
            UPDATE job SET
                last_seen_at = datetime('now'),
                archived = 0,
                description = CASE
                    WHEN length(?) > length(description) THEN ? ELSE description END,
                posted_at = CASE
                    WHEN ? IS NOT NULL AND (posted_at IS NULL OR ? < posted_at)
                    THEN ? ELSE posted_at END,
                apply_url = COALESCE(NULLIF(?, ''), apply_url)
            WHERE id = ?
            """,
            (
                job.description,
                job.description,
                job.posted_at,
                job.posted_at,
                job.posted_at,
                job.apply_url,
                job_id,
            ),
        )


def source_summary(settings: Settings) -> list[dict[str, Any]]:
    return registry.list_sources(settings)
