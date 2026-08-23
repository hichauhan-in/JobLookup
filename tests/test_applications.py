"""Starting over, and keeping track of what you applied to.

The rule worth pinning down is that clearing your matches must never quietly
take an application with it. Deleting a posting cascades to the application
attached to it, so anything you are tracking is protected by default.
"""

from __future__ import annotations

from joblookup import store
from joblookup.config import Settings
from joblookup.models import APPLICATION_STATUSES, CrawlStats, RawJob, Score
from joblookup.services.crawl import ingest_one
from joblookup.sources.normalize import parse_date

ROLES = [
    ("Senior Platform Engineer", "Globex Inc.", "Kubernetes and Terraform across a fleet. "),
    ("Product Designer", "Initech", "Figma, design systems and user research. "),
    ("Financial Controller", "Umbrella Group", "Statutory reporting and treasury. "),
]


def seed(count: int = 3) -> list[int]:
    settings = Settings()
    stats = CrawlStats()
    ids = []
    for index in range(count):
        title, company, body = ROLES[index % len(ROLES)]
        kept = ingest_one(
            RawJob(
                source_key="remoteok",
                title=title,
                company=company,
                location="Remote",
                description=body + "x" * 400,
                url=f"https://example.com/{index}",
                posted_at=parse_date("1 day ago"),
            ),
            settings,
            stats,
        )
        assert kept is not None
        ids.append(kept[0])
    return ids


def score_all(ids: list[int]) -> None:
    store.save_scores(
        [Score(job_id=job_id, composite=0.8, band="good", model="test") for job_id in ids]
    )


class TestClearingScores:
    def test_it_forgets_judgements_and_keeps_postings(self, database):
        ids = seed()
        score_all(ids)
        assert store.counts()["scored"] == len(ids)

        removed = store.clear_scores()

        assert removed == len(ids)
        assert store.counts()["scored"] == 0
        # The postings survive, so a re-score needs no new search.
        assert store.counts()["jobs"] == len(ids)

    def test_clearing_twice_is_harmless(self, database):
        score_all(seed())
        store.clear_scores()
        assert store.clear_scores() == 0


class TestClearingPostings:
    def test_it_empties_the_database_of_postings(self, database):
        seed()
        result = store.clear_postings()
        assert result["removed"] == 3
        assert store.counts()["jobs"] == 0

    def test_it_protects_anything_you_are_tracking(self, database):
        ids = seed()
        store.set_application(ids[0], status="applied")

        result = store.clear_postings(keep_tracked=True)

        assert result["removed"] == 2
        assert result["kept"] == 1
        # The whole contract: the application is still there.
        assert len(store.list_applications()) == 1

    def test_it_can_be_asked_to_take_everything(self, database):
        ids = seed()
        store.set_application(ids[0], status="applied")

        result = store.clear_postings(keep_tracked=False)

        assert result["removed"] == 3
        assert store.list_applications() == []

    def test_clearing_an_empty_database_is_not_an_error(self, database):
        assert store.clear_postings()["removed"] == 0


class TestTrackingApplications:
    def test_every_status_can_be_set(self, database):
        job_id = seed(1)[0]
        for status in APPLICATION_STATUSES:
            entry = store.set_application(job_id, status=status)
            assert entry["status"] == status

    def test_changing_status_does_not_duplicate_the_row(self, database):
        job_id = seed(1)[0]
        store.set_application(job_id, status="saved")
        store.set_application(job_id, status="applied")
        assert len(store.list_applications()) == 1

    def test_notes_survive_a_status_change(self, database):
        job_id = seed(1)[0]
        store.set_application(job_id, status="saved", notes="Referred by Sam")
        store.set_application(job_id, status="applied")
        assert store.list_applications()[0]["notes"] == "Referred by Sam"

    def test_removing_one_keeps_the_posting(self, database):
        ids = seed()
        store.set_application(ids[0], status="applied")

        assert store.delete_application(ids[0]) is True

        assert store.list_applications() == []
        assert store.counts()["jobs"] == len(ids)

    def test_removing_something_untracked_says_so(self, database):
        assert store.delete_application(9999) is False

    def test_the_list_carries_what_the_screen_needs(self, database):
        ids = seed(1)
        score_all(ids)
        store.set_application(ids[0], status="interviewing")
        entry = store.list_applications()[0]
        for key in ("job_id", "status", "title", "company", "url", "band", "updated_at"):
            assert key in entry
