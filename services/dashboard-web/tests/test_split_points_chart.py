"""DASH-129 (RAV-008): `GET /runs/{run_id}/splits/{split_index}/points-chart`
tests. Fakes gateway-api with `httpx.MockTransport`, mirroring
`tests/test_runs_detail.py`'s own mocking approach.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "super-secret-raw-api-key-do-not-leak"
RUN_ID = "11111111-1111-1111-1111-111111111111"

RUN_DETAIL_BODY = {
    "id": RUN_ID,
    "tenant_id": "tenant-a",
    "dataset_id": "dataset-1",
    "horizon": 24,
    "purge_gap_hours": 6,
    "split_config": {"train_window": 100, "test_window": 10, "step": 10},
    "status": "completed",
    "created_at": "2026-08-01T00:00:00Z",
    "completed_at": "2026-08-01T01:00:00Z",
    "failure_reason": None,
    "has_client_model": True,
}

POINTS_BODY = {
    "items": [
        {
            "timestamp": "2026-01-10T06:00:00Z",
            "predicted": 1.1,
            "actual": 1.5,
            "baseline_key": "naive_last",
        },
        {
            "timestamp": "2026-01-10T07:00:00Z",
            "predicted": 1.2,
            "actual": 1.4,
            "baseline_key": "naive_last",
        },
        {
            "timestamp": "2026-01-10T06:00:00Z",
            "predicted": 0.0,
            "actual": 1.5,
            "baseline_key": "naive0",
        },
        {
            "timestamp": "2026-01-10T07:00:00Z",
            "predicted": 0.0,
            "actual": 1.4,
            "baseline_key": "naive0",
        },
    ],
    "limit": 20,
    "offset": 0,
    "total": 4,
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


def test_split_points_chart_renders_model_and_naive0_series(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {RAW_KEY}"
        if request.url.path == f"/runs/{RUN_ID}":
            return httpx.Response(200, json=RUN_DETAIL_BODY)
        if request.url.path == f"/runs/{RUN_ID}/splits/0/points":
            return httpx.Response(200, json=POINTS_BODY)
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}/splits/0/points-chart")

    assert response.status_code == 200
    assert "<svg" in response.text
    assert "Actual value" in response.text
    assert "predicted value" in response.text
    assert "No per-point data available" not in response.text


def test_split_points_chart_no_points_renders_no_data_message(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/runs/{RUN_ID}":
            return httpx.Response(200, json=RUN_DETAIL_BODY)
        if request.url.path == f"/runs/{RUN_ID}/splits/0/points":
            return httpx.Response(200, json={"items": [], "limit": 20, "offset": 0, "total": 0})
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}/splits/0/points-chart")

    assert response.status_code == 200
    assert "No per-point data available for this split." in response.text
    assert "<svg" not in response.text


def test_split_points_chart_run_not_found(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}/splits/0/points-chart")

    assert response.status_code == 404


def test_split_points_chart_requires_session(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called without a session")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)

    response = client.get(f"/runs/{RUN_ID}/splits/0/points-chart", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_split_points_chart_template_has_no_banned_positioning_words(monkeypatch) -> None:
    """DASH-129 Test acceptance criteria: banned words are exactly
    `("prediction", "forecast", "signal", "recommendation")`, per
    `tests/test_datasets.py`'s own convention. "predicted value" is not
    incorrectly flagged since "predict" itself is not in that list.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/runs/{RUN_ID}":
            return httpx.Response(200, json=RUN_DETAIL_BODY)
        if request.url.path == f"/runs/{RUN_ID}/splits/0/points":
            return httpx.Response(200, json=POINTS_BODY)
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}/splits/0/points-chart")
    text = response.text.lower()

    assert "predicted value" in text
    for banned in ("prediction", "forecast", "signal", "recommendation"):
        assert banned not in text, f"banned positioning word {banned!r} found in rendered response"
