import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from joblookup import store
from joblookup.config import Settings
from joblookup.models import RawJob, Score
from joblookup.server.workbench import build_router
from joblookup.sources.normalize import normalize, parse_date


@pytest.fixture
def client(database):
    settings = Settings()
    application = FastAPI()
    application.include_router(build_router(lambda: settings))
    store.save_profile(
        {
            "target_titles": ["Python Developer"],
            "locations": ["India"],
            "work_modes": ["remote"],
            "seniority": "mid",
            "skills": [{"name": "Python"}],
        }
    )
    with TestClient(application) as test_client:
        yield test_client


def seed(title="Python Developer", location="India", posted_at=None):
    job_id, _ = store.upsert_job(
        normalize(
            RawJob(
                source_key="remoteok",
                title=title,
                company="Example " + title,
                description="Build and maintain Python applications, supporting our customers "
                "and collaborating with the team on reliable software releases.",
                location=location,
                work_mode="remote",
                url="https://example.org/jobs/1",
                posted_at=posted_at or parse_date("1 day ago"),
            )
        )
    )
    return job_id


def test_new_results_ignore_old_ai_scores(client):
    relevant = seed()
    unrelated = seed("Financial Controller")
    store.save_scores([Score(job_id=unrelated, composite=1, band="strong")])
    response = client.get("/api/opportunities")
    assert response.status_code == 200
    payload = response.json()
    assert [entry["id"] for entry in payload["items"]] == [relevant]
    assert payload["buckets"]["excluded"] == 1


def test_profile_changes_immediately_change_results(client):
    seed()
    assert client.get("/api/opportunities").json()["total"] == 1
    store.save_profile({"target_titles": ["Accountant"], "locations": ["India"]})
    assert client.get("/api/opportunities").json()["total"] == 0


def test_unknown_remote_location_is_in_review_not_recommended(client):
    seed(location="Remote")
    assert client.get("/api/opportunities").json()["total"] == 0
    assert client.get("/api/opportunities?view=review").json()["total"] == 1


def test_wrong_country_is_explained_in_all_results(client):
    job_id = seed(location="United States")
    assert client.get("/api/opportunities").json()["total"] == 0
    result = client.get(f"/api/opportunities/{job_id}").json()["job"]
    assert result["fit"]["blockers"]


def test_pagination_returns_a_real_total(client):
    seed()
    seed("Senior Python Developer")
    first = client.get("/api/opportunities?view=all&page_size=1").json()
    second = client.get("/api/opportunities?view=all&page_size=1&page=2").json()
    assert first["total"] == 2
    assert first["items"][0]["id"] != second["items"][0]["id"]


def test_hidden_jobs_are_recoverable(client):
    job_id = seed()
    store.set_hidden(job_id, True)
    assert client.get("/api/opportunities?view=all").json()["total"] == 0
    assert client.get("/api/opportunities?view=hidden").json()["items"][0]["id"] == job_id


def test_reset_protects_applications(client):
    kept = seed()
    seed("Senior Python Developer")
    store.set_application(kept, status="applied")
    response = client.post("/api/opportunities/reset", json={})
    assert response.status_code == 200
    assert response.json() == {"removed": 1, "kept": 1}
    assert len(store.list_applications()) == 1


def test_clear_applications_does_not_delete_jobs(client):
    job_id = seed()
    store.set_application(job_id, status="saved")
    assert client.delete("/api/applications").json()["removed"] == 1
    assert store.get_job(job_id)


def test_workspace_loads_without_probing_any_model(client, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Workspace must not probe an AI provider")

    monkeypatch.setattr("joblookup.llm.LLMClient.from_settings", forbidden)
    assert client.get("/api/workspace").status_code == 200


def test_empty_source_selection_does_not_search_everything(client):
    response = client.post("/api/discover", json={"sources": [], "days": 7})
    assert response.status_code == 400


def test_cached_results_change_when_posting_content_changes(client, monkeypatch):
    from joblookup.db import session as db

    job_id = seed()
    assert client.get("/api/opportunities").json()["total"] == 1
    with db.transaction() as conn:
        conn.execute(
            "UPDATE job SET location = ?, country = ? WHERE id = ?", ("United States", "US", job_id)
        )
    assert client.get("/api/opportunities").json()["total"] == 0
