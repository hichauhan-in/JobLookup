import json

import httpx
import pytest

from joblookup.config import VSCodeLLMConfig
from joblookup.llm.base import LLMUnavailableError
from joblookup.llm.vscode_bridge import VSCodeBridgeProvider


def provider(tmp_path, monkeypatch):
    monkeypatch.setattr("joblookup.llm.vscode_bridge.user_state_dir", lambda: tmp_path)
    (tmp_path / "bridges").mkdir()
    return VSCodeBridgeProvider(VSCodeLLMConfig())


def handshake(tmp_path, name, port):
    (tmp_path / "bridges" / name).write_text(
        json.dumps(
            {
                "base_url": f"http://127.0.0.1:{port}",
                "token": "x" * 64,
            }
        ),
        encoding="utf-8",
    )


def test_dead_window_does_not_hide_a_working_bridge(tmp_path, monkeypatch):
    client = provider(tmp_path, monkeypatch)
    handshake(tmp_path, "999-dead.json", 44001)
    handshake(tmp_path, "111-live.json", 44002)

    def get(url, **kwargs):
        if "44001" in url:
            raise httpx.ConnectError("closed")
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={
                "ok": True,
                "copilot_available": True,
                "consented": True,
                "models": ["test"],
                "default_model": "test",
            },
        )

    monkeypatch.setattr(httpx, "get", get)
    assert client.status().available is True
    assert "44002" in client.status().detail


def test_invalid_files_do_not_prevent_legacy_discovery(tmp_path, monkeypatch):
    client = provider(tmp_path, monkeypatch)
    (tmp_path / "bridges" / "invalid.json").write_text("not json")
    (tmp_path / "bridge.json").write_text(
        json.dumps({"base_url": "http://127.0.0.1:44003", "token": "x" * 64})
    )
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kwargs: httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={"ok": True, "copilot_available": True, "consented": True},
        ),
    )
    assert client.status().available is True


@pytest.mark.parametrize(
    "url",
    [
        "https://attacker.example",
        "http://127.0.0.1@attacker.example:80",
        "file:///secret",
        "http://127.0.0.1:1234/path",
        "http://127.0.0.1:1234?token=value",
    ],
)
def test_discovery_cannot_send_the_token_to_an_external_endpoint(url):
    client = VSCodeBridgeProvider(VSCodeLLMConfig(base_url=url, token="x" * 64))
    with pytest.raises(LLMUnavailableError, match="invalid"):
        client._endpoint()


def test_models_without_consent_are_not_available(tmp_path, monkeypatch):
    client = provider(tmp_path, monkeypatch)
    handshake(tmp_path, "live.json", 44002)
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kwargs: httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={"ok": True, "copilot_available": True, "consented": False},
        ),
    )
    assert client.status().available is False
    assert "consent" in client.status().detail.lower()
