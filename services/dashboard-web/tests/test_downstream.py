"""DASH-003: `get_session_headers`/`get_gateway_api_url` DI seam tests.

Proves the rejection-timing behavior non-tautologically: a dummy test-only
route is wired behind `DownstreamHeadersDep` whose body asserts `False` if
reached, so an unauthenticated request only passes this test if that route
body is *never executed* -- not merely that the final response happens to
carry a 303, which a bug in the dummy route itself could still coincidentally
produce.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.dependencies.downstream import (
    DownstreamHeadersDep,
    GatewayApiUrlDep,
    get_gateway_api_url,
    get_session_headers,
)
from app.dependencies.session import get_session_store

RAW_KEY = "super-secret-raw-api-key-do-not-leak"

_probe_app = FastAPI()


@_probe_app.get("/__probe__")
def _probe_route(headers: DownstreamHeadersDep):
    assert False, "route body must never execute for an unauthenticated request"
    return headers


@_probe_app.get("/__probe_success__")
def _probe_success_route(headers: DownstreamHeadersDep):
    return headers


@_probe_app.get("/__probe_url__")
def _probe_url_route(url: GatewayApiUrlDep):
    return {"url": url}


@pytest.fixture(autouse=True)
def _clear_sessions():
    yield
    get_session_store()._sessions.clear()


def test_valid_session_cookie_reaches_route_body_with_bearer_header() -> None:
    session_store = get_session_store()
    session_id = session_store.create(RAW_KEY)

    client = TestClient(_probe_app)
    client.cookies.set("session_id", session_id)

    response = client.get("/__probe_success__")

    assert response.status_code == 200
    assert response.json() == {"Authorization": f"Bearer {RAW_KEY}"}


def test_valid_session_cookie_header_shape() -> None:
    session_store = get_session_store()
    session_id = session_store.create(RAW_KEY)

    scope = {
        "type": "http",
        "headers": [(b"cookie", f"session_id={session_id}".encode())],
    }
    request = Request(scope)

    headers = get_session_headers(request, session_store)

    assert headers == {"Authorization": f"Bearer {RAW_KEY}"}


def test_missing_cookie_redirects_before_route_body_runs() -> None:
    client = TestClient(_probe_app)

    response = client.get("/__probe__", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_unknown_session_id_redirects_before_route_body_runs() -> None:
    client = TestClient(_probe_app)
    client.cookies.set("session_id", "not-a-real-session-id")

    response = client.get("/__probe__", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_get_gateway_api_url_default(monkeypatch) -> None:
    monkeypatch.delenv("GATEWAY_API_URL", raising=False)

    assert get_gateway_api_url() == "http://localhost:8000"


def test_get_gateway_api_url_reads_env_var(monkeypatch) -> None:
    monkeypatch.setenv("GATEWAY_API_URL", "http://gateway-api:9000")

    assert get_gateway_api_url() == "http://gateway-api:9000"
