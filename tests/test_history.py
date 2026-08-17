"""Search history: what a run produced, and forgetting it safely.

The important invariant is that deleting history is not deleting your work.
Postings, scores and applications all outlive the run that found them.
"""

from __future__ import annotations

from joblookup import store
from joblookup.config import Settings
from joblookup.models import CrawlStats, RawJob, Score
from joblookup.services.crawl import ingest_one
from joblookup.sources.normalize import parse_date


def raw(**overrides):
    base = {
        "source_key": "remoteok",
        "title": "Senior Platform Engineer",
        "company": "Globex Inc.",
        "location": "Remote, United States",
        "description": "Kubernetes and Terraform. " + "x" * 400,
        "url": "https://example.com/1",
        "posted_at": parse_date("1 day ago"),
    }
    base.update(overrides)
    return RawJob(**base)


# Deliberately unalike, so deduplication does not fold them into one posting.
ROLES = [
    ("Senior Platform Engineer", "Globex Inc.", "Kubernetes and Terraform across a fleet. "),
    ("Product Designer", "Initech", "Figma, design systems and user research. "),
    ("Financial Controller", "Umbrella Group", "Statutory reporting, audit and treasury. "),
]


def seed_run(sources=("remoteok",), postings=2):
    """One recorded run that produced `postings` distinct jobs."""
    run_id = store.start_run(list(sources))
    settings = Settings()
    stats = CrawlStats()
    produced = {}
    for index in range(postings):
        title, company, body = ROLES[index % len(ROLES)]
        kept = ingest_one(
            raw(
                title=title,
                company=company,
                description=body + "x" * 400,
                url=f"https://example.com/{index}",
            ),
            settings,
            stats,
        )
        assert kept is not None
        job_id, is_new = kept
        produced[job_id] = is_new
    store.link_run_jobs(run_id, produced)
    store.finish_run(run_id, status="ok", stats=stats.to_dict())
    return run_id, produced


class TestRecording:
    def test_a_run_remembers_what_it_found(self, database):
        run_id, produced = seed_run(postings=3)
        results = store.run_results(run_id)
        assert len(results) == len(produced) == 3
        assert all(result["is_new"] for result in results)

    def test_history_counts_results_and_new_postings(self, database):
        seed_run(postings=2)
        history = store.search_history()
        assert len(history) == 1
        assert history[0]["result_count"] == 2
        assert history[0]["new_count"] == 2
        assert history[0]["status"] == "ok"

    def test_a_second_run_finding_the_same_jobs_reports_them_as_not_new(self, database):
        seed_run(postings=2)
        second, _ = seed_run(postings=2)
        results = store.run_results(second)
        assert len(results) == 2
        assert not any(result["is_new"] for result in results)
        assert store.counts()["jobs"] == 2

    def test_linking_nothing_is_harmless(self, database):
        run_id = store.start_run(["remoteok"])
        store.link_run_jobs(run_id, {})
        assert store.run_results(run_id) == []

    def test_results_carry_the_score_when_there_is_one(self, database):
        run_id, produced = seed_run(postings=1)
        job_id = next(iter(produced))
        store.save_scores(
            [Score(job_id=job_id, composite=0.85, band="strong", direct_fit=0.9, model="test")]
        )
        result = store.run_results(run_id)[0]
        assert result["band"] == "strong"
        assert result["score"] == 0.85


class TestScopingMatchesToARun:
    def test_the_latest_run_is_the_newest_one_with_results(self, database):
        first, _ = seed_run(postings=1)
        second, _ = seed_run(postings=3)
        assert store.latest_run_id() == second
        assert second != first

    def test_a_run_that_produced_nothing_is_not_the_latest(self, database):
        real, _ = seed_run(postings=2)
        empty = store.start_run(["remoteok"])
        store.finish_run(empty, status="ok", stats={})
        # Otherwise Matches would default to an empty screen after a failed run.
        assert store.latest_run_id() == real

    def test_no_runs_at_all_means_no_scoping(self, database):
        assert store.latest_run_id() is None

    def test_listing_can_be_limited_to_one_run(self, database):
        first, _ = seed_run(postings=1)
        second, _ = seed_run(postings=3)
        assert len(store.list_jobs(scored_only=False, run_id=first)) == 1
        assert len(store.list_jobs(scored_only=False, run_id=second)) == 3
        assert len(store.list_jobs(scored_only=False)) == 3

    def test_scoping_to_a_forgotten_run_returns_nothing(self, database):
        run_id, _ = seed_run(postings=2)
        store.delete_run(run_id)
        assert store.list_jobs(scored_only=False, run_id=run_id) == []
        assert len(store.list_jobs(scored_only=False)) == 2


class TestForgetting:
    def test_deleting_a_run_keeps_the_postings(self, database):
        run_id, _ = seed_run(postings=2)
        assert store.delete_run(run_id) is True
        assert store.search_history() == []
        # The whole point: history is a record of searching, not the results.
        assert store.counts()["jobs"] == 2

    def test_deleting_a_run_that_is_gone_says_so(self, database):
        assert store.delete_run(999) is False

    def test_clearing_removes_every_finished_run(self, database):
        seed_run()
        seed_run()
        assert store.clear_history() == 2
        assert store.search_history() == []
        assert store.counts()["jobs"] == 2

    def test_clearing_leaves_a_run_still_in_progress(self, database):
        seed_run()
        running = store.start_run(["remoteok"])
        assert store.clear_history() == 1
        remaining = store.search_history()
        assert [run["id"] for run in remaining] == [running]

    def test_clearing_an_empty_history_is_not_an_error(self, database):
        assert store.clear_history() == 0
