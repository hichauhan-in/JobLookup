"""Tracks, feedback and inbox state never silently overwrite the career profile."""

import pytest

from joblookup import store
from joblookup.services import workflow
from tests.test_workbench import seed


def test_tracks_overlay_preferences_without_replacing_profile(database):
    store.save_profile({"target_titles": ["Support Engineer"], "skills": [{"name": "Python"}]})
    track = workflow.save_track(
        {"name": "Cloud", "preferences": {"target_titles": ["SRE"], "full_name": "Not allowed"}}
    )
    assert workflow.effective_profile(track["id"])["target_titles"] == ["SRE"]
    assert store.get_profile()["data"]["target_titles"] == ["Support Engineer"]
    assert "full_name" not in track["preferences"]


def test_deleted_tracks_are_not_silently_replaced_by_default(database):
    with pytest.raises(ValueError, match="no longer exists"):
        workflow.effective_profile(4321)


def test_seen_state_is_content_based_and_track_specific(database):
    job_id = seed()
    workflow.mark_seen([job_id])
    assert workflow.posting_hash(store.get_job(job_id)) == workflow.seen_hashes()[job_id]
    assert workflow.seen_hashes(7) == {}
    with database.transaction() as conn:
        conn.execute(
            "UPDATE job SET description = description || ' Changed duties.' WHERE id = ?", (job_id,)
        )
    assert workflow.posting_hash(store.get_job(job_id)) != workflow.seen_hashes()[job_id]


def test_original_source_refresh_can_replace_longer_stale_text(database):
    from joblookup.models import RawJob
    from joblookup.sources.normalize import normalize

    raw = RawJob(
        source_key="manual",
        title="Python Developer",
        company="Refresh test",
        location="India",
        url="https://example.org/refresh",
        work_mode="remote",
        description="Python systems development. " * 20,
        salary_min=100000,
        salary_max=120000,
        salary_currency="USD",
        salary_period="year",
    )
    job_id, _ = store.upsert_job(normalize(raw))
    workflow.mark_seen([job_id])
    raw.description = "Python role with revised responsibilities. " * 5
    raw.work_mode = "onsite"
    raw.salary_min = 1500000
    raw.salary_max = None
    raw.salary_currency = "INR"
    store.upsert_job(normalize(raw))
    refreshed = store.get_job(job_id)
    assert refreshed["description"] == raw.description.strip()
    assert refreshed["work_mode"] == "onsite"
    assert refreshed["salary_max"] is None
    assert refreshed["salary_currency"] == "INR"
    assert workflow.posting_hash(refreshed) != workflow.seen_hashes()[job_id]


def test_crawl_exact_duplicates_use_original_source_refresh(database, settings):
    from joblookup.models import CrawlStats, RawJob
    from joblookup.services.crawl import ingest_one

    raw = RawJob(
        source_key="manual",
        title="Python Developer",
        company="Crawl refresh",
        location="India",
        url="https://example.org/crawl-refresh",
        work_mode="remote",
        description="Python development responsibilities. " * 20,
    )
    job_id, _ = ingest_one(raw, settings, CrawlStats())
    raw.description = "Revised Python role requirements. " * 6
    raw.work_mode = "onsite"
    assert ingest_one(raw, settings, CrawlStats())[0] == job_id
    assert store.get_job(job_id)["work_mode"] == "onsite"
    assert store.get_job(job_id)["description"] == raw.description.strip()


def test_feedback_keeps_evidence_and_does_not_mutate_preferences(database):
    store.save_profile(
        {
            "target_titles": ["Python Developer"],
            "locations": ["India"],
            "skills": [{"name": "Python"}],
        }
    )
    job_id = seed()
    before = store.get_profile()
    workflow.save_feedback(job_id, {"label": "relevant"})
    assert store.get_profile() == before
    benchmark = workflow.benchmark()
    assert benchmark["sample_size"] == 1
    assert benchmark["false_exclusions"] == 0
    assert benchmark["top20_labeled_relevant"] == 1


def test_schema_migration_is_repeatable(database):
    database.apply_schema(database.db_path())
    assert database.connect().execute("PRAGMA foreign_key_check").fetchall() == []


def test_ai_review_identity_changes_with_track_preferences():
    from joblookup.server.workbench import _review_version

    assert _review_version(1, {}, 0) == 1
    assert _review_version(1, {"target_titles": ["Python"]}, 2) != _review_version(
        1, {"target_titles": ["SRE"]}, 2
    )


def test_track_inbox_and_feedback_routes(database, settings):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from joblookup.server.workbench import build_router as workbench_router
    from joblookup.server.workflow import build_router

    app = FastAPI()
    app.include_router(build_router(lambda: settings))
    app.include_router(workbench_router(lambda: settings))
    store.save_profile(
        {
            "target_titles": ["Python Developer"],
            "locations": ["India"],
            "skills": [{"name": "Python"}],
        }
    )
    job_id = seed()
    with TestClient(app) as client:
        track = client.post(
            "/api/tracks",
            json={"name": "Python", "preferences": {"target_titles": ["Python Developer"]}},
        ).json()
        assert (
            client.get(f"/api/opportunities?view=inbox&track_id={track['id']}").json()["total"] == 1
        )
        assert (
            client.post(
                "/api/inbox/seen", json={"job_ids": [job_id], "track_id": track["id"]}
            ).status_code
            == 200
        )
        assert (
            client.get(f"/api/opportunities?view=inbox&track_id={track['id']}").json()["total"] == 0
        )
        assert client.get("/api/opportunities?view=inbox").json()["total"] == 1
        assert (
            client.post(
                f"/api/opportunities/{job_id}/feedback", json={"label": "relevant"}
            ).status_code
            == 200
        )
        assert client.get("/api/benchmark").json()["sample_size"] == 1
        assert client.post("/api/tracks", json={"name": "Python"}).status_code == 409
