"""DASH-113: `GET /operator-login` / `POST /operator-login` tests.

No `httpx` mocking needed here -- unlike `POST /login` (DASH-002), this
handler makes no outbound call to gateway-api at all (ticket Analysis
section: no gateway-api endpoint validates a bare operator token yet), so
"success" is purely a non-empty-token check plus a store write.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.dependencies.operator_session import get_operator_session_store
from app.main import app

RAW_TOKEN = "super-secret-operator-token"


@pytest.fixture(autouse=True)
def _clear_operator_sessions():
    yield
    get_operator_session_store()._sessions.clear()


def test_get_operator_login_renders_form() -> None:
    client = TestClient(app)
    response = client.get("/operator-login")

    assert response.status_code == 200
    assert "form" in response.text
    assert 'action="/operator-login"' in response.text


def test_valid_token_creates_operator_session_and_redirects() -> None:
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


def test_operator_cookie_name_distinct_from_tenant_cookie_name() -> None:
    """DASH-113's core structural requirement: the operator-session cookie
    is a different cookie entirely from DASH-002/003's `session_id` cookie.
    """
    client = TestClient(app)

    response = client.post(
        "/operator-login", data={"operator_token": RAW_TOKEN}, follow_redirects=False
    )

    assert set(response.cookies.keys()) == {"operator_session_id"}
