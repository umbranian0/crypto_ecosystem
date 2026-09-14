"""DASH-113: `GET /operator-login` / `POST /operator-login` tests.

SETUP-035: `POST /operator-login` now lazy-validates the submitted token
against gateway-api's `GET /tenants` (`SETUP-011`) before creating a
session. Mocks that call the same way `tests/test_monitoring.py` mocks
`GET /system/health` -- monkeypatching `httpx.Client` itself, since this
router builds `httpx.Client(base_url=...)` per-request rather than
depending on an injectable client (same established pattern, reused not
reinvented -- no `httpx.MockTransport`-via-DI-override shape like
`test_auth.py`'s, since `operator.py` has no injectable client).
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.operator_session import get_operator_session_store
from app.main import app

RAW_TOKEN = "super-secret-operator-token"


@pytest.fixture(autouse=True)
def _clear_operator_sessions():
    yield
    get_operator_session_store()._sessions.clear()


def _patch_transport(monkeypatch, handler) -> None:
    real_client_cls = httpx.Client

    def _fake_client(*, base_url="", **kwargs):
        return real_client_cls(base_url=base_url, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", _fake_client)


def _valid_token_handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/tenants"
    assert request.headers["x-operator-token"] == RAW_TOKEN
    return httpx.Response(200, json={"items": []})


def test_get_operator_login_renders_form() -> None:
    client = TestClient(app)
    response = client.get("/operator-login")

    assert response.status_code == 200
    assert "form" in response.text
    assert 'action="/operator-login"' in response.text


def test_valid_token_creates_operator_session_and_redirects(monkeypatch) -> None:
    _patch_transport(monkeypatch, _valid_token_handler)
    client = TestClient(app)

    response = client.post(
        "/operator-login", data={"operator_token": RAW_TOKEN}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/monitoring"
    assert "operator_session_id" in response.cookies
    assert "session_id" not in response.cookies

    store = get_operator_session_store()
    session_id = response.cookies["operator_session_id"]
    assert store.get(session_id) == RAW_TOKEN


def test_empty_token_rejected_and_redisplays_form() -> None:
    client = TestClient(app)

    response = client.post(
        "/operator-login", data={"operator_token": "   "}, follow_redirects=False
    )

    assert response.status_code == 422
    assert "operator_session_id" not in response.cookies
    assert len(get_operator_session_store()._sessions) == 0


def test_operator_cookie_name_distinct_from_tenant_cookie_name(monkeypatch) -> None:
    """DASH-113's core structural requirement: the operator-session cookie
    is a different cookie entirely from DASH-002/003's `session_id` cookie.
    """
    _patch_transport(monkeypatch, _valid_token_handler)
    client = TestClient(app)

    response = client.post(
        "/operator-login", data={"operator_token": RAW_TOKEN}, follow_redirects=False
    )

    assert set(response.cookies.keys()) == {"operator_session_id"}


def test_401_from_tenants_rejected_as_invalid_token(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={})

    _patch_transport(monkeypatch, handler)
    client = TestClient(app)

    response = client.post(
        "/operator-login", data={"operator_token": RAW_TOKEN}, follow_redirects=False
    )

    assert response.status_code == 422
    assert "Invalid operator token." in response.text
    assert "operator_session_id" not in response.cookies
    assert len(get_operator_session_store()._sessions) == 0


def test_403_from_tenants_also_rejected_as_invalid_token(monkeypatch) -> None:
    """SETUP-035's binding design decision: `403` is treated identically to
    `401`, not as a separate/different error.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={})

    _patch_transport(monkeypatch, handler)
    client = TestClient(app)

    response = client.post(
        "/operator-login", data={"operator_token": RAW_TOKEN}, follow_redirects=False
    )

    assert response.status_code == 422
    assert "Invalid operator token." in response.text
    assert "operator_session_id" not in response.cookies
    assert len(get_operator_session_store()._sessions) == 0


def test_connect_error_redisplays_with_unreachable_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, handler)
    client = TestClient(app)

    response = client.post(
        "/operator-login", data={"operator_token": RAW_TOKEN}, follow_redirects=False
    )

    assert response.status_code == 502
    assert "gateway-api is unreachable" in response.text
    assert "operator_session_id" not in response.cookies
    assert len(get_operator_session_store()._sessions) == 0
