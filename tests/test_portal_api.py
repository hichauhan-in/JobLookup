from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from joblookup import store
from joblookup.config import Settings
from joblookup.server.portals import build_router
from joblookup.server.workbench import build_router as workspace_router
from joblookup.sources import registry
from joblookup.sources.tier_b import browser


@pytest.fixture
def client(database, tmp_path, monkeypatch):
    settings = Settings()
    settings.paths.workspace = str(tmp_path)
    registry.sync_source_table()
    monkeypatch.setattr(
        browser,
        "availability",
        lambda: {"installed": True, "browser_ready": True, "detail": "Ready"},
    )

    def save(values):
        settings.tier_b.enabled = values["tier_b"]["enabled"]

    monkeypatch.setattr("joblookup.server.portals.save_local_overrides", save)
    app = FastAPI()
    app.include_router(build_router(lambda: settings, lambda: settings))
    app.include_router(workspace_router(lambda: settings))
    with TestClient(app) as test_client:
        yield test_client


def test_all_portals_are_visible_with_truthful_session_status(client):
    result = client.get("/api/portals").json()
    assert len(result["portals"]) == 9
    linkedin = next(item for item in result["portals"] if item["key"] == "linkedin")
    assert linkedin["session"]["authenticated"] is False
    assert linkedin["public_supported"] is True
    assert "linkedin.com/jobs/search/" in linkedin["search_url"]
    assert "password" not in linkedin


def test_portals_require_global_optin_and_acknowledgement(client):
    body = {"enabled": True, "access_mode": "public", "acknowledged": True}
    assert client.put("/api/portals/linkedin", json=body).status_code == 400
    assert client.put("/api/portals", json={"enabled": True}).status_code == 200
    assert (
        client.put("/api/portals/linkedin", json=body | {"acknowledged": False}).status_code == 400
    )
    assert client.put("/api/portals/linkedin", json=body).status_code == 200
    linkedin = next(
        item for item in client.get("/api/portals").json()["portals"] if item["key"] == "linkedin"
    )
    assert linkedin["ready"] is True


def test_session_mode_without_login_is_not_ready(client):
    client.put("/api/portals", json={"enabled": True})
    client.put("/api/portals/linkedin", json={"enabled": True, "acknowledged": True})
    linkedin = next(
        item for item in client.get("/api/portals").json()["portals"] if item["key"] == "linkedin"
    )
    assert linkedin["ready"] is False
    assert "Sign in" in linkedin["blocked_reason"]


def test_manual_import_needs_neither_signin_nor_automation(client):
    body = {
        "title": "Python Developer",
        "company": "Example",
        "location": "India",
        "url": "https://www.linkedin.com/jobs/view/12345",
        "description": (
            "Build Python applications and support enterprise customers with reliable software. "
        )
        * 3,
    }
    response = client.post("/api/portals/linkedin/import", json=body)
    assert response.status_code == 200
    job = store.get_job(response.json()["job_id"])
    assert job["sources"][0]["source_key"] == "linkedin"
    assert job["posted_at"] is None
    assert client.post("/api/portals/linkedin/import", json=body).json()["created"] is False


@pytest.mark.parametrize(
    "url",
    [
        "https://linkedin.com.attacker.test/jobs/1",
        "javascript:alert(1)",
        "https://www.linkedin.com@attacker.test/jobs/1",
    ],
)
def test_import_requires_an_original_portal_url(client, url):
    body = {
        "title": "Python Developer",
        "company": "Example",
        "url": url,
        "description": "Python application development. " * 5,
    }
    assert client.post("/api/portals/linkedin/import", json=body).status_code == 400


def test_ready_public_portal_participates_in_discovery(client, monkeypatch):
    client.put("/api/portals", json={"enabled": True})
    client.put(
        "/api/portals/linkedin",
        json={"enabled": True, "acknowledged": True, "access_mode": "public"},
    )
    store.save_profile({"target_titles": ["Python Developer"]})
    scheduled = []

    def submit(kind, work, **kwargs):
        scheduled.append(work)
        return SimpleNamespace(summary=lambda: {"id": "test-search", "status": "queued"})

    monkeypatch.setattr("joblookup.server.workbench.manager.submit", submit)
    result = client.post("/api/discover", json={"sources": ["linkedin"]})
    assert result.status_code == 200
    assert scheduled
    from joblookup.events import NullBus
    from joblookup.models import CrawlStats

    def crawl(settings, bus, *, source_keys, cancelled):
        assert settings.tier_b.enabled is True
        assert source_keys == ["linkedin"]
        return CrawlStats()

    monkeypatch.setattr("joblookup.server.workbench.crawl.run_crawl", crawl)
    work = scheduled[0]
    outcome = work(
        NullBus(), SimpleNamespace(cancel_requested=SimpleNamespace(is_set=lambda: False))
    )
    assert outcome["partial"] is False


def test_portal_only_search_without_session_is_actionable(client):
    client.put("/api/portals", json={"enabled": True})
    client.put("/api/portals/linkedin", json={"enabled": True, "acknowledged": True})
    store.save_profile({"target_titles": ["Python Developer"]})
    response = client.post("/api/discover", json={"sources": ["linkedin"]})
    assert response.status_code == 400
    assert "sign-in" in response.json()["detail"]


def test_revoking_consent_disables_portal_access(client):
    client.put("/api/portals", json={"enabled": True})
    client.put(
        "/api/portals/linkedin",
        json={"enabled": True, "acknowledged": True, "access_mode": "public"},
    )
    client.put(
        "/api/portals/linkedin",
        json={"enabled": False, "acknowledged": False, "access_mode": "public"},
    )
    linkedin = next(
        item for item in client.get("/api/portals").json()["portals"] if item["key"] == "linkedin"
    )
    assert linkedin["enabled"] is False
    assert linkedin["ready"] is False


def test_disconnect_disables_portal_without_deleting_postings(client):
    client.put("/api/portals", json={"enabled": True})
    client.put(
        "/api/portals/linkedin",
        json={"enabled": True, "acknowledged": True, "access_mode": "public"},
    )
    assert client.delete("/api/portals/linkedin/session").status_code == 200
    linkedin = next(
        item for item in client.get("/api/portals").json()["portals"] if item["key"] == "linkedin"
    )
    assert linkedin["enabled"] is False
