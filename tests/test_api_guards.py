"""The two guards that stand in for a password.

There is no login because the server is yours and it listens on loopback.
That only holds if a web page cannot reach it by pointing its own domain at
127.0.0.1, and cannot post to it from another origin. Both of those are the
browser's job to report honestly, and both are checked here.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from joblookup.config import Settings
from joblookup.server.app import create_app


def build(tmp_path, monkeypatch, **server):
    values = Settings()
    values.paths.workspace = str(tmp_path / "workspace")
    for key, value in server.items():
        setattr(values.server, key, value)
    monkeypatch.setattr("joblookup.server.app.load_settings", lambda: values)
    return values, create_app(values)


@pytest.fixture
def client(tmp_path, monkeypatch):
    _, app = build(tmp_path, monkeypatch)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


class TestHostGuard:
    @pytest.mark.parametrize("host", ["127.0.0.1:8770", "localhost:8770", "LocalHost"])
    def test_this_machine_by_any_of_its_names_is_fine(self, client, host):
        assert client.get("/api/state", headers={"host": host}).status_code == 200

    def test_a_rebound_domain_is_refused(self, client):
        response = client.get("/api/state", headers={"host": "evil.example.com"})
        assert response.status_code == 421
        assert "this machine" in response.json()["detail"]

    def test_it_guards_reads_as_well_as_writes(self, client):
        # A rebinding attack reads your CVs. Refusing only writes would miss it.
        assert client.get("/api/settings", headers={"host": "evil.example.com"}).status_code == 421

    def test_binding_wide_open_turns_the_name_check_off(self, tmp_path, monkeypatch):
        # Choosing a non-loopback host means choosing to be reachable, and we
        # cannot know which address the user will type.
        _, app = build(tmp_path, monkeypatch, host="0.0.0.0")
        with TestClient(app, base_url="http://127.0.0.1") as reachable:
            assert reachable.get("/api/state", headers={"host": "192.168.1.5"}).status_code == 200


class TestCrossSiteGuard:
    def test_a_write_from_another_site_is_refused(self, client):
        response = client.post(
            "/api/matches/reset", json={}, headers={"sec-fetch-site": "cross-site"}
        )
        assert response.status_code == 403
        assert "JobLookup itself" in response.json()["detail"]

    def test_a_write_from_our_own_page_is_allowed(self, client):
        response = client.post(
            "/api/matches/reset", json={}, headers={"sec-fetch-site": "same-origin"}
        )
        assert response.status_code == 200

    def test_a_client_that_sends_no_such_header_is_allowed(self, client):
        # curl and the CLI are not confused deputies for anybody's page.
        assert client.post("/api/matches/reset", json={}).status_code == 200

    def test_an_upload_cannot_be_smuggled_cross_site(self, client):
        # Multipart is CORS-safelisted, so it crosses origins with no preflight.
        response = client.post(
            "/api/cvs",
            files={"file": ("cv.txt", b"hello", "text/plain")},
            headers={"sec-fetch-site": "cross-site"},
        )
        assert response.status_code == 403

    def test_reads_from_another_site_are_left_to_cors(self, client):
        assert client.get("/api/state", headers={"sec-fetch-site": "cross-site"}).status_code == 200


class TestCorsCredentials:
    def test_a_wildcard_origin_never_gets_credentials(self, tmp_path, monkeypatch):
        # Starlette echoes the caller's origin for "*", so pairing it with
        # credentials would hand every site on the internet a session.
        _, app = build(tmp_path, monkeypatch, allowed_origins=["*"])
        with TestClient(app, base_url="http://127.0.0.1") as wide:
            response = wide.get("/api/state", headers={"origin": "https://evil.example.com"})
        assert response.headers.get("access-control-allow-credentials") is None

    def test_a_named_origin_still_gets_credentials(self, tmp_path, monkeypatch):
        _, app = build(tmp_path, monkeypatch, allowed_origins=["https://trusted.example.com"])
        with TestClient(app, base_url="http://127.0.0.1") as named:
            response = named.get("/api/state", headers={"origin": "https://trusted.example.com"})
        assert response.headers.get("access-control-allow-credentials") == "true"
