"""Capture is explicit, validates public URLs, and preserves unknown dates."""

import json

import pytest

from joblookup import store
from joblookup.services import capture
from joblookup.sources.base import SourceError
from tests.test_workbench import seed


def test_structured_capture_reads_job_fields_and_salary_units():
    payload = {
        "@type": "JobPosting",
        "title": "Python Developer",
        "hiringOrganization": {"name": "Example"},
        "description": "<p>Python systems</p>",
        "jobLocation": {"address": {"addressLocality": "Pune", "addressCountry": "India"}},
        "baseSalary": {
            "currency": "INR",
            "value": {"minValue": 1200000, "maxValue": 1800000, "unitText": "YEAR"},
        },
    }
    html = f'<script type="application/ld+json">{json.dumps(payload)}</script>'
    item = capture.parse_page(html, "https://example.org/job")[0]
    assert item["company"] == "Example"
    assert item["salary_period"] == "year"
    assert item["location"] == "Pune, India"
    assert item["posted_at"] is None


def test_capture_traverses_jsonld_graphs():
    html = (
        '<script type="application/ld+json">'
        + json.dumps(
            {
                "@graph": [
                    {"@type": "Organization", "name": "Not a job"},
                    {"@type": "JobPosting", "title": "Python Developer"},
                ]
            }
        )
        + "</script>"
    )
    assert capture.parse_page(html, "https://example.org/job")[0]["title"] == "Python Developer"


def test_extension_has_no_background_or_host_permissions(database, settings):
    import io
    import zipfile

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from joblookup.server.capture import build_router

    app = FastAPI()
    app.include_router(build_router(lambda: settings))
    with TestClient(app, base_url="http://127.0.0.1:8899") as client:
        response = client.get("/api/capture/extension")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert set(manifest["permissions"]) == {"activeTab", "scripting", "storage"}
        assert "background" not in manifest
        assert "host_permissions" not in manifest
        assert json.loads(archive.read("settings.json"))["origin"] == "http://127.0.0.1:8899"


def test_alert_links_are_deduplicated_and_private_urls_are_removed():
    items = capture.preview(
        "Job https://example.org/1\nhttps://example.org/1\nhttp://127.0.0.1/admin"
    )
    assert [item["url"] for item in items] == ["https://example.org/1"]


def test_capture_packet_never_requires_a_network_request():
    packet = json.dumps(
        {
            "format": "joblookup-capture-v1",
            "url": "https://example.org/job",
            "title": "Python",
            "text": "A description",
        }
    )
    assert capture.preview(packet)[0]["description"] == "A description"
    with pytest.raises(SourceError):
        capture.preview(packet.replace("https://example.org/job", "http://127.0.0.1/private"))


def test_import_preserves_unknown_date(database):
    result = capture.import_posting(
        {
            "title": "Python Developer",
            "company": "Example",
            "url": "https://example.org/job",
            "description": "Python" * 30,
        }
    )
    assert store.get_job(result["job_id"])["posted_at"] is None


def test_salary_and_partial_description_survive_storage(database):
    from joblookup.models import RawJob
    from joblookup.sources.normalize import normalize

    raw = RawJob(
        source_key="manual",
        title="Python Developer",
        company="Example",
        description="Pay USD 100000 per year. " + "Python " * 30,
        salary_min=100000,
        salary_currency="USD",
        raw={"partial_description": True},
    )
    job_id, _ = store.upsert_job(normalize(raw))
    saved = store.get_job(job_id)
    assert saved["salary_period"] == "year"
    assert saved["partial_description"] == 1
    assert store.match_candidates()[0]["salary_period"] == "year"


def test_closed_and_blocked_pages_are_distinguished(database, settings, monkeypatch):
    job_id = seed()
    monkeypatch.setattr(
        capture,
        "fetch_page",
        lambda *args: ("This job has been filled", 200, "https://example.org/job"),
    )
    assert capture.check_availability(job_id, settings)["availability"] == "closed"

    def blocked(*args):
        raise SourceError("Sign-in required")

    monkeypatch.setattr(capture, "fetch_page", blocked)
    assert capture.check_availability(job_id, settings)["availability"] == "unknown"


def test_public_fetch_preserves_404_for_availability_checks(settings, monkeypatch):
    import httpx

    original_client = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(404, text="Missing"))
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original_client(transport=transport, **kwargs)
    )
    settings.search.min_request_interval_s = 0
    assert capture.fetch_page("https://example.org/missing", settings)[1] == 404
