"""FHS-002: `GET /runs/horizon-summary` tests.

Fakes gateway-api with `httpx.MockTransport`, mirroring
`tests/test_runs_detail.py`'s mocking approach -- `app.routers.runs` builds
`httpx.Client(base_url=base_url)` per-request rather than depending on an
injectable client, so the mock is wired in by monkeypatching `httpx.Client`
itself to substitute a `MockTransport`-backed client instead of a real one.
"""

from __future__ import annotations

import pathlib

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "super-secret-raw-api-key-do-not-leak"

RUN_HORIZON_168 = {
    "id": "11111111-1111-1111-1111-111111111111",
    "tenant_id": "tenant-a",
    "dataset_id": "dataset-1",
    "horizon": 168,
    "status": "completed",
    "created_at": "2026-08-01T00:00:00Z",
    "completed_at": "2026-08-01T01:00:00Z",
}

RUN_HORIZON_720 = {
    "id": "22222222-2222-2222-2222-222222222222",
    "tenant_id": "tenant-a",
    "dataset_id": "dataset-2",
    "horizon": 720,
    "status": "completed",
    "created_at": "2026-08-02T00:00:00Z",
    "completed_at": "2026-08-02T01:00:00Z",
}

RUNS_BODY = {
    "items": [RUN_HORIZON_168, RUN_HORIZON_720],
    "limit": 50,
    "offset": 0,
    "total": 2,
}


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


def test_horizon_summary_no_days_shows_only_selector(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called until a horizon is selected")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary")

    assert response.status_code == 200
    assert "7 days" in response.text
    assert "15 days" in response.text
    assert "30 days" in response.text
    assert RUN_HORIZON_168["id"] not in response.text


def test_horizon_summary_days_7_shows_only_horizon_168_run(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {RAW_KEY}"
        assert request.url.path == "/runs"
        return httpx.Response(200, json=RUNS_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary?days=7")

    assert response.status_code == 200
    assert RUN_HORIZON_168["id"] in response.text
    assert RUN_HORIZON_720["id"] not in response.text


def test_horizon_summary_days_30_shows_disjoint_set(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=RUNS_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary?days=30")

    assert response.status_code == 200
    assert RUN_HORIZON_720["id"] in response.text
    assert RUN_HORIZON_168["id"] not in response.text


def test_horizon_summary_excludes_non_completed_runs_at_matching_horizon(monkeypatch) -> None:
    """FHS-002 bug fix (found in Sprint 27 QA): a `running`/`failed` run at
    the matching horizon is not backtested-validation evidence yet and must
    not appear on this page -- `runs_horizon_summary` filters on both
    `horizon` AND `status == "completed"`, not `horizon` alone.
    """
    running_run = {**RUN_HORIZON_168, "id": "33333333-3333-3333-3333-333333333333", "status": "running", "completed_at": None}
    failed_run = {**RUN_HORIZON_168, "id": "44444444-4444-4444-4444-444444444444", "status": "failed", "completed_at": None}
    body = {
        "items": [running_run, failed_run],
        "limit": 50,
        "offset": 0,
        "total": 2,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary?days=7")

    assert response.status_code == 200
    assert running_run["id"] not in response.text
    assert failed_run["id"] not in response.text
    assert "No completed runs at this horizon yet" in response.text


def test_horizon_summary_zero_matches_renders_empty_state(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=RUNS_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary?days=15")

    assert response.status_code == 200
    assert "No completed runs at this horizon yet" in response.text
    assert "/runs/new" in response.text
    assert "<table" not in response.text


def test_horizon_summary_502_from_gateway_api_reuses_error_template(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"detail": "downstream service unavailable"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary?days=7")

    assert response.status_code == 502
    assert "results currently unavailable" in response.text
    assert "downstream service unavailable" not in response.text


def test_horizon_summary_requires_session(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called without a session")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)

    response = client.get("/runs/horizon-summary", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_horizon_summary_template_has_no_banned_positioning_words() -> None:
    template_path = (
        pathlib.Path(__file__).parent.parent / "src" / "app" / "templates" / "horizon_summary.html"
    )
    text = template_path.read_text(encoding="utf-8").lower()

    for banned in ("prediction", "forecast", "signal", "target", "recommendation"):
        assert banned not in text, f"banned positioning word {banned!r} found in horizon_summary.html"
