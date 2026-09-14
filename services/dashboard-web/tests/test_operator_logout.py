"""SETUP-034: `POST /operator-logout` tests.

Mirrors `test_logout.py`'s (DASH-007) fixture/cleanup style one-for-one, for
the operator session instead of the tenant session.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.dependencies.operator_session import get_operator_session_store
from app.main import app

RAW_TOKEN = "super-secret-operator-token-do-not-leak"


@pytest.fixture(autouse=True)
def _clear_operator_sessions():
    yield
    get_operator_session_store()._sessions.clear()


def _login(client: TestClient) -> str:
    store = get_operator_session_store()
    session_id = store.create(RAW_TOKEN)
    client.cookies.set("operator_session_id", session_id)
    return session_id


def test_operator_logout_deletes_session_clears_cookie_and_redirects() -> None:
    client = TestClient(app)
    session_id = _login(client)

    response = client.post("/operator-logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/operator-login"
    assert get_operator_session_store().get(session_id) is None

    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any(
        header.startswith("operator_session_id=")
        and ("Max-Age=0" in header or "expires=" in header.lower())
        for header in set_cookie_headers
    )


def test_operator_logout_without_session_is_safe_no_op() -> None:
    client = TestClient(app)

    response = client.post("/operator-logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/operator-login"


def test_stale_operator_session_cookie_rejected_after_logout() -> None:
    client = TestClient(app)
    session_id = _login(client)

    logout_response = client.post("/operator-logout", follow_redirects=False)
    assert logout_response.status_code == 303

    client.cookies.set("operator_session_id", session_id)
    response = client.get("/settings/environment", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/operator-login"
