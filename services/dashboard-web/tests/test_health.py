"""DASH-008: `GET /health` tests.

Fakes gateway-api with `httpx.MockTransport`, mirroring DASH-004's
`tests/test_runs_detail.py` mocking approach -- `app.main.health` builds a
plain `httpx.get(...)` call rather than depending on an injectable client, so
the mock is wired in by monkeypatching `httpx.get` itself to route through a
`MockTransport`-backed client instead of a real network call.

This route is deliberately unauthenticated: no session cookie is set in any
test here, matching the ticket's Implementation acceptance criterion that no
`DownstreamHeadersDep`/session dependency is attached.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app


def _patch_get(monkeypatch, handler) -> None:
    def _fake_get(url, *, timeout=None, **kwargs):
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return client.get(url, timeout=timeout)

    monkeypatch.setattr(httpx, "get", _fake_get)


def test_health_success(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok"})

    _patch_get(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_non_200_from_gateway_api(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"status": "unhealthy", "detail": "database unreachable"})

    _patch_get(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy", "detail": "gateway-api unreachable"}
    assert "database unreachable" not in response.text


def test_health_connect_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_get(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy", "detail": "gateway-api unreachable"}
    assert "connection refused" not in response.text


def test_health_timeout(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    _patch_get(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy", "detail": "gateway-api unreachable"}


def test_health_requires_no_session() -> None:
    """No cookie is set anywhere in this file -- if this route accidentally
    depended on `DownstreamHeadersDep`, every test above would 303-redirect
    to /login instead of returning a JSON health body.
    """
    client = TestClient(app)
    response = client.get("/health", follow_redirects=False)

    assert response.status_code != 303
