"""DASH-002: `GET /login` / `POST /login` tests.

Fakes gateway-api with `httpx.MockTransport` (mirrors gateway-api's own
`tests/test_runs_routing.py` pattern for its `validation-service` client) via
`app.dependency_overrides[get_gateway_api_client]` -- `httpx.Client` is used
in production code (`app.dependencies.http_client`), so `MockTransport`
(sync) is used rather than `ASGITransport` (async-only).
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.http_client import get_gateway_api_client
from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "super-secret-raw-api-key-do-not-leak"


class _RecordingTransport:
    """Wraps a handler function and records every request it receives, so a
    test can assert zero outbound calls were made for an empty-key
    submission (Test AC1).
    """

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.calls: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return httpx.Response(self.status_code, json={})


def _make_client(transport: _RecordingTransport) -> TestClient:
    mock_client = httpx.Client(
        transport=httpx.MockTransport(transport.handler),
        base_url="http://gateway-api",
    )
    app.dependency_overrides[get_gateway_api_client] = lambda: mock_client
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides_and_sessions():
    yield
    app.dependency_overrides.clear()
    get_session_store()._sessions.clear()


def test_get_login_renders_form() -> None:
    client = TestClient(app)
    response = client.get("/login")

    assert response.status_code == 200
    assert "form" in response.text
    assert 'action="/login"' in response.text


def test_valid_key_creates_session_and_redirects() -> None:
    transport = _RecordingTransport(status_code=404)
    client = _make_client(transport)

    response = client.post(
        "/login", data={"api_key": RAW_KEY}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/runs/new"
    assert "session_id" in response.cookies
    assert len(transport.calls) == 1
    assert transport.calls[0].headers["authorization"] == f"Bearer {RAW_KEY}"

    store = get_session_store()
    session_id = response.cookies["session_id"]
    assert store.get(session_id) == RAW_KEY


def test_empty_key_rejected_before_any_outbound_call() -> None:
    transport = _RecordingTransport(status_code=200)
    client = _make_client(transport)

    response = client.post("/login", data={"api_key": "   "}, follow_redirects=False)

    assert response.status_code == 422
    assert len(transport.calls) == 0
    assert "session_id" not in response.cookies


def test_invalid_key_gets_401_and_is_not_stored() -> None:
    transport = _RecordingTransport(status_code=401)
    client = _make_client(transport)

    response = client.post(
        "/login", data={"api_key": RAW_KEY}, follow_redirects=False
    )

    assert response.status_code == 401
    assert "set-cookie" not in {k.lower() for k in response.headers.keys()}
    assert "session_id" not in response.cookies
    assert len(get_session_store()._sessions) == 0


def test_raw_key_never_appears_in_response_body_success_path() -> None:
    transport = _RecordingTransport(status_code=404)
    client = _make_client(transport)

    response = client.post(
        "/login", data={"api_key": RAW_KEY}, follow_redirects=False
    )

    assert RAW_KEY not in response.text


def test_raw_key_never_appears_in_response_body_failure_path() -> None:
    transport = _RecordingTransport(status_code=401)
    client = _make_client(transport)

    response = client.post(
        "/login", data={"api_key": RAW_KEY}, follow_redirects=False
    )

    assert RAW_KEY not in response.text
