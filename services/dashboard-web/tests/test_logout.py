"""DASH-007: `POST /logout` tests.

Mirrors `test_auth.py`'s fixture/cleanup style. The key assertion (Test AC1)
replays the now-deleted `session_id` cookie against `app.routers.runs`'
`GET /runs/{run_id}` (a real `DownstreamHeadersDep`-backed route, not a
dummy probe) to prove the deletion is real server-side state, not merely a
client-side cookie clear that a replayed old cookie could bypass.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "super-secret-raw-api-key-do-not-leak"


@pytest.fixture(autouse=True)
def _clear_sessions():
    yield
    get_session_store()._sessions.clear()


def _login(client: TestClient) -> str:
    session_store = get_session_store()
    session_id = session_store.create(RAW_KEY)
    client.cookies.set("session_id", session_id)
    return session_id


def test_logout_deletes_session_clears_cookie_and_redirects() -> None:
    client = TestClient(app)
    session_id = _login(client)

    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert get_session_store().get(session_id) is None

    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any(
        header.startswith("session_id=") and ("Max-Age=0" in header or "expires=" in header.lower())
        for header in set_cookie_headers
    )


def test_logout_without_valid_session_redirects_to_login() -> None:
    client = TestClient(app)

    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_stale_session_cookie_rejected_after_logout_on_other_route() -> None:
    client = TestClient(app)
    session_id = _login(client)

    logout_response = client.post("/logout", follow_redirects=False)
    assert logout_response.status_code == 303

    client.cookies.set("session_id", session_id)
    response = client.get("/runs/some-run-id", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
