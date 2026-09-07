from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from joblookup.config import OpenAICompatConfig, Settings
from joblookup.llm.base import ProviderStatus
from joblookup.llm.openai_compat import OpenAICompatProvider
from joblookup.server.connections import build_router
from joblookup.services import secrets


@pytest.fixture
def client(monkeypatch):
    settings = Settings()
    monkeypatch.setattr(secrets, "llm_key", lambda *args: "")
    application = FastAPI()
    application.include_router(build_router(lambda: settings, lambda: settings))
    with TestClient(application) as test_client:
        yield test_client


def test_reading_connections_does_not_probe_network(client, monkeypatch):
    monkeypatch.setattr(
        httpx, "get", lambda *args, **kwargs: pytest.fail("Unexpected network call")
    )
    assert client.get("/api/connections").status_code == 200


def test_connection_settings_never_include_a_key(client):
    payload = client.get("/api/connections").json()
    assert "api_key" not in payload
    assert payload["key_set"] is False


def test_keys_are_scoped_to_the_exact_endpoint():
    assert secrets.llm_secret_name("SAMPLE", "https://first.example/v1") != secrets.llm_secret_name(
        "SAMPLE", "https://second.example/v1"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.example/v1",
        "file:///secret",
        "https://user:password@example.org/v1",
        "https://example.org/v1?key=secret",
    ],
)
def test_unsafe_endpoints_are_rejected(client, url):
    response = client.put(
        "/api/connections",
        json={
            "provider": "openai_compat",
            "preset": "custom",
            "base_url": url,
            "model": "example",
        },
    )
    assert response.status_code == 400


def test_api_key_is_not_put_into_settings(client, monkeypatch):
    patches, stored = [], []
    monkeypatch.setattr("joblookup.server.connections.save_local_overrides", patches.append)
    monkeypatch.setattr(secrets, "set", lambda name, value: stored.append((name, value)))
    response = client.put(
        "/api/connections",
        json={
            "provider": "openai_compat",
            "preset": "custom",
            "base_url": "https://example.org/v1",
            "model": "example",
            "api_key": "test-secret-not-real",
        },
    )
    assert response.status_code == 200
    assert "test-secret-not-real" not in str(patches)
    assert stored[0][1] == "test-secret-not-real"


def test_rejected_authentication_is_not_reported_as_available(monkeypatch):
    monkeypatch.setattr("joblookup.llm.openai_compat.llm_key", lambda *args: "fake")
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: httpx.Response(401))
    provider = OpenAICompatProvider(OpenAICompatConfig(base_url="https://example.org/v1"))
    assert provider.status().available is False


def test_bridge_models_are_live_and_do_not_change_saved_settings(monkeypatch):
    settings = Settings()
    settings.llm.provider = "anthropic"
    settings.llm.vscode.model = "previous-model"
    status = ProviderStatus(
        "vscode",
        "VS Code bridge",
        True,
        "Connected",
        models=["gpt-5-mini", "claude-sonnet-4.6", "gpt-5-mini", ""],
        active_model="gpt-5-mini",
    )

    def build(config, key):
        assert key == "vscode"
        assert config.provider == "anthropic"
        assert config.vscode.model is None
        return SimpleNamespace(status=lambda: status)

    monkeypatch.setattr("joblookup.server.connections.build_provider", build)
    application = FastAPI()
    application.include_router(build_router(lambda: settings, lambda: settings))
    with TestClient(application) as test_client:
        response = test_client.get("/api/connections/vscode/models")
    assert response.status_code == 200
    assert response.json() == {
        "models": ["claude-sonnet-4.6", "gpt-5-mini"],
        "default_model": "gpt-5-mini",
        "available": True,
        "detail": "Connected",
    }
    assert settings.llm.provider == "anthropic"
    assert settings.llm.vscode.model == "previous-model"


def test_bridge_models_remain_selectable_before_consent(client, monkeypatch):
    status = ProviderStatus(
        "vscode", "VS Code bridge", False, "Waiting for consent.", models=["gpt-5-mini"]
    )
    monkeypatch.setattr(
        "joblookup.server.connections.build_provider",
        lambda *args: SimpleNamespace(status=lambda: status),
    )
    payload = client.get("/api/connections/vscode/models").json()
    assert payload["models"] == ["gpt-5-mini"]
    assert payload["available"] is False
    assert payload["detail"] == "Waiting for consent."


def test_unreachable_bridge_does_not_invent_model_options(client, monkeypatch):
    status = ProviderStatus("vscode", "VS Code bridge", False, "No reachable bridge.")
    monkeypatch.setattr(
        "joblookup.server.connections.build_provider",
        lambda *args: SimpleNamespace(status=lambda: status),
    )
    assert client.get("/api/connections/vscode/models").json() == {
        "models": [],
        "default_model": "",
        "available": False,
        "detail": "No reachable bridge.",
    }
