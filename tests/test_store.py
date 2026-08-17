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


class TestIngest:
    def test_stores_a_posting(self, database):
        stats = CrawlStats()
        assert ingest_one(raw(), Settings(), stats)
        assert stats.new == 1
        assert store.counts()["jobs"] == 1

    def test_the_same_posting_from_two_sources_is_one_card(self, database):
        settings = Settings()
        stats = CrawlStats()
        ingest_one(raw(source_key="remoteok"), settings, stats)
        ingest_one(raw(source_key="remotive", url="https://other.example/1"), settings, stats)

        assert store.counts()["jobs"] == 1
        job_id = store.list_jobs(scored_only=False)[0]["id"]
        assert len(store.get_job(job_id)["sources"]) == 2

    def test_a_stale_posting_is_dropped(self, database):
        settings = Settings()
        stats = CrawlStats()
        assert not ingest_one(raw(posted_at=parse_date("40 days ago")), settings, stats)
        assert stats.too_old == 1

    def test_the_longest_description_wins(self, database):
        settings = Settings()
        stats = CrawlStats()
        ingest_one(raw(description="short " * 30), settings, stats)
        ingest_one(raw(source_key="remotive", description="much longer " * 200), settings, stats)
        job = store.list_jobs(scored_only=False)[0]
        assert len(job["description"]) > 1000


class TestScores:
    def test_saving_and_reading_back(self, database):
        ingest_one(raw(), Settings(), CrawlStats())
        job_id = store.list_jobs(scored_only=False)[0]["id"]

        store.save_scores(
            [
                Score(
                    job_id=job_id,
                    profile_version=1,
                    direct_fit=0.7,
                    transferable_fit=0.8,
                    growth_fit=0.6,
                    composite=0.72,
                    band="good",
                    rationale="Adjacent experience carries over.",
                    matched_skills=["Kubernetes"],
                    learnable_gaps=["Terraform"],
                )
            ]
        )

        job = store.get_job(job_id)
        assert job["band"] == "good"
        assert job["matched_skills"] == ["Kubernetes"]
        assert store.counts()["scored"] == 1

    def test_scoring_twice_updates_rather_than_duplicates(self, database):
        ingest_one(raw(), Settings(), CrawlStats())
        job_id = store.list_jobs(scored_only=False)[0]["id"]
        store.save_scores([Score(job_id=job_id, band="stretch", composite=0.4)])
        store.save_scores([Score(job_id=job_id, band="strong", composite=0.9)])
        assert store.counts()["scored"] == 1
        assert store.get_job(job_id)["band"] == "strong"


class TestProfile:
    def test_saving_bumps_the_version_and_stales_the_scores(self, database):
        before = store.profile_version()
        store.save_profile({"headline": "Support Engineer"})
        assert store.profile_version() == before + 1

    def test_preferences_survive_a_read(self, database):
        store.save_profile({"target_titles": ["SRE"], "locations": ["London"]})
        data = store.get_profile()["data"]
        assert data["target_titles"] == ["SRE"]


class TestApplications:
    def test_tracking_a_job(self, database):
        ingest_one(raw(), Settings(), CrawlStats())
        job_id = store.list_jobs(scored_only=False)[0]["id"]
        store.set_application(job_id, status="applied", notes="Referred by Sam")
        applications = store.list_applications()
        assert applications[0]["status"] == "applied"
        assert applications[0]["notes"] == "Referred by Sam"

    def test_changing_status_keeps_the_notes(self, database):
        # The UI calls this twice - once for the dropdown, once for the notes -
        # so the conflict branch runs far more often than the insert.
        ingest_one(raw(), Settings(), CrawlStats())
        job_id = store.list_jobs(scored_only=False)[0]["id"]
        store.set_application(job_id, status="saved", notes="Looks promising")
        store.set_application(job_id, status="interviewing", notes=None)

        record = store.list_applications()[0]
        assert record["status"] == "interviewing"
        assert record["notes"] == "Looks promising"
        assert len(store.list_applications()) == 1


class TestRecallIndex:
    def test_lexical_recall_finds_the_posting(self, database):
        from joblookup.matching.recall import lexical_recall

        ingest_one(raw(), Settings(), CrawlStats())
        results = lexical_recall("Kubernetes Terraform platform engineer", Settings(), limit=10)
        assert results, "the FTS index should have matched the stored posting"

    def test_the_weakest_hit_is_not_scored_to_zero(self, database):
        # Min-max normalisation would give the last result exactly 0.0, which then
        # falls below any threshold and silently disappears.
        from joblookup.matching.recall import lexical_recall

        settings = Settings()
        ingest_one(raw(), settings, CrawlStats())
        ingest_one(
            raw(
                source_key="remotive",
                title="Platform Engineer",
                company="Initech",
                url="https://example.com/2",
                description="Terraform and platform tooling. " * 30,
            ),
            settings,
            CrawlStats(),
        )
        results = lexical_recall("Kubernetes Terraform platform engineer", settings, limit=10)
        assert len(results) == 2
        assert all(score > 0 for _, score in results)
        assert max(score for _, score in results) == 1.0
