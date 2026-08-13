"""DASH-004: `GET /runs/{id}` tests.

Fakes gateway-api with `httpx.MockTransport`, mirroring gateway-api's own
`tests/test_runs_routing.py` mocking approach -- `app.routers.runs` builds
`httpx.Client(base_url=base_url)` per-request rather than depending on an
injectable client, so the mock is wired in by monkeypatching `httpx.Client`
itself to substitute a `MockTransport`-backed client instead of a real one,
preserving `base_url` so relative outbound paths still resolve correctly.
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
}

SPLIT_BODY = {
    "split_index": 0,
    "train_start": "2026-01-01T00:00:00Z",
    "train_end": "2026-01-10T00:00:00Z",
    "purge_start": "2026-01-10T00:00:00Z",
    "purge_end": "2026-01-10T06:00:00Z",
    "test_start": "2026-01-10T06:00:00Z",
    "test_end": "2026-01-11T00:00:00Z",
    "model_mae": 1.1,
    "model_rmse": 2.2,
    "model_smape": 3.3,
    "model_mase": 4.4,
    "model_da": 0.5,
    "model_f1": 0.6,
    "model_oos_r2": 0.1,
    "naive0_mae": 1.0,
    "naive0_rmse": 2.0,
    "naive0_smape": 3.0,
    "naive0_mase": 4.0,
    "naive0_da": 0.51,
    "naive0_f1": 0.61,
    "naive0_oos_r2": 0.12,
    "dm_statistic": -0.9,
    "dm_pvalue": 0.42,
    "dm_verdict": "no significant difference",
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
        return real_client_cls(
            base_url=base_url, transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(httpx, "Client", _fake_client)


def test_run_detail_success_with_splits(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {RAW_KEY}"
        if request.url.path == f"/runs/{RUN_ID}":
            return httpx.Response(200, json=RUN_DETAIL_BODY)
        if request.url.path == f"/runs/{RUN_ID}/splits":
            return httpx.Response(200, json=[SPLIT_BODY])
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 200
    assert RUN_ID in response.text
    assert "completed" in response.text
    assert "no significant difference" in response.text
    assert "1.1" in response.text


def test_run_detail_running_with_no_splits(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/runs/{RUN_ID}":
            body = {**RUN_DETAIL_BODY, "status": "running", "completed_at": None}
            return httpx.Response(200, json=body)
        if request.url.path == f"/runs/{RUN_ID}/splits":
            return httpx.Response(200, json=[])
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 200
    assert "running" in response.text
    assert "No per-split validation results yet" in response.text


def test_run_detail_404(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 404
    assert "not found" in response.text.lower()


def test_run_detail_502_from_gateway_api(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"detail": "downstream service unavailable"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 502
    assert "results currently unavailable" in response.text
    assert "downstream service unavailable" not in response.text


def test_run_detail_504_from_gateway_api(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(504, json={"detail": "downstream service timed out"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 504
    assert "results currently unavailable" in response.text
    assert "downstream service timed out" not in response.text


def test_run_detail_transport_connect_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 502
    assert "results currently unavailable" in response.text
    assert "connection refused" not in response.text


def test_run_detail_transport_timeout(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 504
    assert "results currently unavailable" in response.text


def test_run_detail_requires_session(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called without a session")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)

    response = client.get(f"/runs/{RUN_ID}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_run_detail_template_has_no_banned_positioning_words() -> None:
    template_path = (
        __import__("pathlib").Path(__file__).parent.parent
        / "src"
        / "app"
        / "templates"
        / "run_detail.html"
    )
    text = template_path.read_text(encoding="utf-8").lower()

    for banned in ("prediction", "forecast", "signal", "recommendation"):
        assert banned not in text, f"banned positioning word {banned!r} found in run_detail.html"
