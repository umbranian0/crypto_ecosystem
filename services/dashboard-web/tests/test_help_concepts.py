"""UAT-014: `GET /help/concepts` tests.

`/help/concepts` itself has no downstream call and no session dependency
(per its own docstring), so a plain `TestClient` GET suffices for that route.
The nav/form-link assertions below exercise `/runs/new` (which does require a
session and calls `GET /ingestion/datasets`), mirroring
`tests/test_runs_submit.py`'s own `_login`/`_patch_transport` pattern.
"""

from __future__ import annotations

import pathlib

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "super-secret-raw-api-key-do-not-leak"


def _login(client: TestClient) -> None:
    session_store = get_session_store()
    session_id = session_store.create(RAW_KEY)
    client.cookies.set("session_id", session_id)


@pytest.fixture(autouse=True)
def _clear_sessions_and_overrides():
    yield
    app.dependency_overrides.clear()
    get_session_store()._sessions.clear()


def _patch_transport(monkeypatch, handler) -> None:
    real_client_cls = httpx.Client

    def _fake_client(*, base_url="", **kwargs):
        return real_client_cls(base_url=base_url, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", _fake_client)


def test_help_concepts_returns_200_and_expected_content_markers() -> None:
    client = TestClient(app)

    response = client.get("/help/concepts")

    assert response.status_code == 200
    assert "purge gap" in response.text.lower()
    assert "walk-forward" in response.text.lower()


def test_base_html_nav_links_to_help_concepts() -> None:
    client = TestClient(app)
    client.cookies.set("session_id", "irrelevant-tenant-session-value")

    response = client.get("/help/concepts")

    assert response.status_code == 200
    assert 'href="/help/concepts"' in response.text


def test_run_new_links_to_help_concepts(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": []})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/new")

    assert response.status_code == 200
    assert 'href="/help/concepts"' in response.text


def test_help_concepts_page_has_no_banned_positioning_words() -> None:
    """CLAUDE.md positioning scan, same convention as
    `test_runs_list_template_has_no_banned_positioning_words`/
    `test_horizon_summary_template_has_no_banned_positioning_words`."""
    template_path = (
        pathlib.Path(__file__).parent.parent
        / "src"
        / "app"
        / "templates"
        / "help_concepts.html"
    )
    text = template_path.read_text(encoding="utf-8").lower()

    for banned in ("prediction", "forecast", "signal", "recommendation"):
        assert banned not in text, f"banned positioning word {banned!r} found in help_concepts.html"
