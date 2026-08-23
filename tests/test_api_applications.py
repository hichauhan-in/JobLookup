"""The HTTP surface for tracking applications and starting over.

The store tests prove the rules hold. These prove the routes actually reach
them, return what the screen reads, and say no clearly when asked for
something that is not there.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from joblookup import store
from joblookup.config import Settings
from joblookup.models import CrawlStats, RawJob, Score
from joblookup.server.app import create_app
from joblookup.services.crawl import ingest_one
from joblookup.sources.normalize import parse_date


@pytest.fixture
def client(tmp_path, monkeypatch):
    values = Settings()
    values.paths.workspace = str(tmp_path / "workspace")
    monkeypatch.setattr("joblookup.server.app.load_settings", lambda: values)
    app = create_app(values)
    #: The default "testserver" host is refused by LocalOnly, as it should be.
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


def seed(count: int = 3) -> list[int]:
    settings = Settings()
    stats = CrawlStats()
    ids = []
    for index in range(count):
        kept = ingest_one(
            RawJob(
                source_key="remoteok",
                title=f"Engineer {index}",
                company=f"Company {index}",
                location="Remote",
                description="Building and running services. " * 20,
                url=f"https://example.com/{index}",
                posted_at=parse_date("2 days ago"),
            ),
            settings,
            stats,
        )
        assert kept is not None
        ids.append(kept[0])
    store.save_scores(
        [Score(job_id=job_id, composite=0.7, band="good", model="test") for job_id in ids]
    )
    return ids


class TestApplicationRoutes:
    def test_the_list_carries_the_statuses_the_picker_needs(self, client):
        payload = client.get("/api/applications").json()
        assert payload["applications"] == []
        assert "applied" in payload["statuses"]

    def test_a_status_can_be_set_and_read_back(self, client):
        job_id = seed(1)[0]
        response = client.post(f"/api/jobs/{job_id}/application", json={"status": "interviewing"})
        assert response.status_code == 200
        assert response.json()["application"]["status"] == "interviewing"
        assert client.get("/api/applications").json()["applications"][0]["status"] == "interviewing"

    def test_an_invented_status_is_refused(self, client):
        job_id = seed(1)[0]
        response = client.post(f"/api/jobs/{job_id}/application", json={"status": "ghosted"})
        assert response.status_code == 400
        assert "Status must be one of" in response.json()["detail"]

    def test_tracking_a_posting_that_is_gone_is_refused(self, client):
        assert (
            client.post("/api/jobs/9999/application", json={"status": "saved"}).status_code == 404
        )

    def test_removing_one_returns_the_list_the_screen_redraws_from(self, client):
        ids = seed(2)
        client.post(f"/api/jobs/{ids[0]}/application", json={"status": "applied"})
        client.post(f"/api/jobs/{ids[1]}/application", json={"status": "saved"})

        payload = client.delete(f"/api/jobs/{ids[0]}/application").json()

        assert len(payload["applications"]) == 1
        assert payload["counts"]["jobs"] == 2

    def test_removing_something_untracked_is_a_clear_no(self, client):
        response = client.delete("/api/jobs/9999/application")
        assert response.status_code == 404
        assert response.json()["detail"] == "That job is not being tracked."


class TestResetRoute:
    def test_the_default_clears_scores_and_keeps_postings(self, client):
        ids = seed()

        payload = client.post("/api/matches/reset", json={}).json()

        assert payload["scores_cleared"] == len(ids)
        assert payload["postings"] == {"removed": 0, "kept": 0}
        assert payload["counts"]["jobs"] == len(ids)
        assert payload["counts"]["scored"] == 0

    def test_asking_for_postings_too_still_protects_what_you_track(self, client):
        ids = seed()
        client.post(f"/api/jobs/{ids[0]}/application", json={"status": "applied"})

        payload = client.post(
            "/api/matches/reset", json={"postings": True, "keep_tracked": True}
        ).json()

        assert payload["postings"] == {"removed": 2, "kept": 1}
        assert len(client.get("/api/applications").json()["applications"]) == 1

    def test_it_can_be_asked_to_take_everything(self, client):
        ids = seed()
        client.post(f"/api/jobs/{ids[0]}/application", json={"status": "applied"})

        payload = client.post(
            "/api/matches/reset", json={"postings": True, "keep_tracked": False}
        ).json()

        assert payload["counts"]["jobs"] == 0
        assert client.get("/api/applications").json()["applications"] == []

    def test_resetting_an_empty_database_is_not_an_error(self, client):
        payload = client.post("/api/matches/reset", json={"postings": True}).json()
        assert payload["scores_cleared"] == 0
