"""RAV-012: `runs_list`'s call to gateway-api's batched `GET /runs/splits/
summary`.

The sprint's own required test (RAV-012 Test AC): a fixture page of N>=3
runs must result in exactly ONE call to `/runs/splits/summary`, not one per
run -- asserted via a request-counting `httpx.MockTransport` handler, not a
docstring claim. Also covers the degrade-on-failure contract: a non-200/
transport failure on this one call must not block the page from rendering.

Same `_patch_transport`-style `httpx.Client` monkeypatch as
`test_runs_list.py` (this router builds `httpx.Client(base_url=...)`
per-request rather than depending on an injectable client).
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "super-secret-raw-api-key-do-not-leak"

RUN_ID_1 = "11111111-1111-1111-1111-111111111111"
RUN_ID_2 = "22222222-2222-2222-2222-222222222222"
RUN_ID_3 = "33333333-3333-3333-3333-333333333333"

# N=3 runs, per the ticket's own "N >= 3" Test AC wording.
RUNS_LIST_BODY = {
    "items": [
        {
            "id": RUN_ID_1,
            "dataset_id": "dataset-1",
            "horizon": 24,
            "status": "completed",
            "created_at": "2026-08-03T00:00:00Z",
            "completed_at": "2026-08-03T01:00:00Z",
        },
        {
            "id": RUN_ID_2,
            "dataset_id": "dataset-2",
            "horizon": 6,
            "status": "completed",
            "created_at": "2026-08-02T00:00:00Z",
            "completed_at": "2026-08-02T01:00:00Z",
        },
        {
            "id": RUN_ID_3,
            "dataset_id": "dataset-3",
            "horizon": 1,
            "status": "completed",
            "created_at": "2026-08-01T00:00:00Z",
            "completed_at": "2026-08-01T01:00:00Z",
        },
    ],
    "limit": 50,
    "offset": 0,
    "total": 3,
}

_SPLIT_RECORD = {
    "split_index": 0,
    "train_start": "2026-01-01T00:00:00",
    "train_end": "2026-01-08T00:00:00",
    "purge_start": "2026-01-08T00:00:00",
    "purge_end": "2026-01-08T02:00:00",
    "test_start": "2026-01-08T02:00:00",
    "test_end": "2026-01-15T02:00:00",
    "model_mae": 1.1,
    "model_rmse": 1.2,
    "model_smape": 1.3,
    "model_mase": 1.4,
    "model_da": 0.5,
    "model_f1": 0.6,
    "model_oos_r2": 0.7,
    "naive0_mae": 2.1,
    "naive0_rmse": 2.2,
    "naive0_smape": 2.3,
    "naive0_mase": 2.4,
    "naive0_da": 0.4,
    "naive0_f1": 0.3,
    "naive0_oos_r2": 0.2,
    "dm_statistic": 3.1,
    "dm_pvalue": 0.02,
    "dm_verdict": "model_better",
    "client_baseline": None,
    "has_client_model": False,
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


def test_runs_list_makes_exactly_one_splits_summary_call_for_n_runs(monkeypatch) -> None:
    """The sprint's own required test: N=3 rendered runs -> exactly one call
    to `/runs/splits/summary`, not O(N) calls -- counted via a real request
    counter on the mock transport, not inferred from the response body."""
    summary_call_count = 0
    forwarded_run_ids: list[str] | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal summary_call_count, forwarded_run_ids
        if request.url.path == "/runs":
            return httpx.Response(200, json=RUNS_LIST_BODY)
        assert request.url.path == "/runs/splits/summary"
        summary_call_count += 1
        forwarded_run_ids = request.url.params.get_list("run_id")
        return httpx.Response(
            200,
            json={
                "items": [
                    {"run_id": RUN_ID_1, "splits": [_SPLIT_RECORD]},
                    {"run_id": RUN_ID_2, "splits": []},
                ]
            },
        )

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs")

    assert response.status_code == 200
    assert summary_call_count == 1, (
        f"expected exactly one /runs/splits/summary call for {len(RUNS_LIST_BODY['items'])} "
        f"runs, got {summary_call_count}"
    )
    assert forwarded_run_ids == [RUN_ID_1, RUN_ID_2, RUN_ID_3]


def test_runs_list_zero_runs_makes_no_splits_summary_call(monkeypatch) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        if request.url.path == "/runs":
            return httpx.Response(200, json={"items": [], "limit": 50, "offset": 0, "total": 0})
        call_count += 1
        raise AssertionError("must not call /runs/splits/summary for zero rendered runs")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs")

    assert response.status_code == 200
    assert call_count == 0


def test_runs_list_degrades_on_splits_summary_non_200(monkeypatch) -> None:
    """Failure on the summary call must not block the page from rendering --
    the primary GET /runs call already succeeded."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/runs":
            return httpx.Response(200, json=RUNS_LIST_BODY)
        assert request.url.path == "/runs/splits/summary"
        return httpx.Response(500, json={"detail": "internal error"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs")

    assert response.status_code == 200
    for run_id in (RUN_ID_1, RUN_ID_2, RUN_ID_3):
        assert run_id in response.text


def test_runs_list_degrades_on_splits_summary_transport_failure(monkeypatch) -> None:
    """Same degrade contract, but a transport-level failure (not a non-200
    HTTP response) on the summary call."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/runs":
            return httpx.Response(200, json=RUNS_LIST_BODY)
        assert request.url.path == "/runs/splits/summary"
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs")

    assert response.status_code == 200
    for run_id in (RUN_ID_1, RUN_ID_2, RUN_ID_3):
        assert run_id in response.text
