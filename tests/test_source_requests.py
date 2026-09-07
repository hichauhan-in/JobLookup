import json

import httpx
import pytest

from joblookup.config import Settings
from joblookup.sources.ats.boards import Greenhouse
from joblookup.sources.base import FetchContext, SourceError


def request(monkeypatch, handler, **kwargs):
    settings = Settings()
    settings.search.min_request_interval_s = 0
    adapter = Greenhouse()
    adapter.rate_limit_s = 0
    real_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **options: real_client(transport=httpx.MockTransport(handler), **options),
    )
    return adapter.request(FetchContext(settings=settings), "https://boards.example/jobs", **kwargs)


def test_307_preserves_post_body(monkeypatch):
    received = []

    def handler(outgoing):
        received.append(outgoing)
        return (
            httpx.Response(307, headers={"location": "/new"})
            if outgoing.url.path == "/jobs"
            else httpx.Response(200, json={"jobs": []})
        )

    assert (
        request(monkeypatch, handler, method="POST", json_body={"query": "engineer"}).status_code
        == 200
    )
    assert received[1].method == "POST"
    assert json.loads(received[1].content) == {"query": "engineer"}


def test_303_switches_to_get(monkeypatch):
    received = []

    def handler(outgoing):
        received.append(outgoing)
        return (
            httpx.Response(303, headers={"location": "/new"})
            if outgoing.url.path == "/jobs"
            else httpx.Response(200)
        )

    request(monkeypatch, handler, method="POST", json_body={"query": "engineer"})
    assert received[1].method == "GET"


def test_redirects_do_not_forward_keys_to_a_different_host(monkeypatch):
    received = []

    def handler(outgoing):
        received.append(outgoing)
        return (
            httpx.Response(302, headers={"location": "https://cdn.example/list"})
            if outgoing.url.host == "boards.example"
            else httpx.Response(200)
        )

    request(
        monkeypatch, handler, headers={"api-key": "test-key", "authorization": "Bearer test-token"}
    )
    assert "api-key" not in received[1].headers
    assert "authorization" not in received[1].headers


def test_private_redirects_are_refused_before_connecting(monkeypatch):
    calls = []

    def handler(outgoing):
        calls.append(outgoing)
        return httpx.Response(302, headers={"location": "http://127.0.0.1:8770/api/settings"})

    with pytest.raises(SourceError, match="Refusing"):
        request(monkeypatch, handler)
    assert len(calls) == 1


def test_redirect_loops_are_failures(monkeypatch):
    with pytest.raises(SourceError, match="redirect limit"):
        request(monkeypatch, lambda outgoing: httpx.Response(302, headers={"location": "/jobs"}))


def test_post_data_cannot_follow_cross_host_redirect(monkeypatch):
    with pytest.raises(SourceError, match="another host"):
        request(
            monkeypatch,
            lambda outgoing: httpx.Response(
                307, headers={"location": "https://another.example/path"}
            ),
            method="POST",
            json_body={"key": "test"},
        )
