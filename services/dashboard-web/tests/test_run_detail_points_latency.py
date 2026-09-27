"""RAV-016: the sprint's own required automated latency test.

Fixture-level measurement only: network latency is mocked to near-zero via
`httpx.MockTransport` (in-memory, no real sockets) -- this proves the
`run_detail` code path itself (JSON parsing, the batched points call,
per-split chart-building) has no O(N)/pathological per-split cost, not a
substitute for the mandatory QA gate's real measurement against the actual
Docker stack (Sprint 60 QA measured the pre-RAV-016 550-split page at ~20s
server-side there).

A fixture 550-split run is used (exceeding a realistic single-page split
count) with a non-empty, distinct point payload for every split -- an
empty/degenerate fixture would pass regardless of implementation and would
not be a meaningful check of this code path's own cost.
"""

from __future__ import annotations

import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "super-secret-raw-api-key-do-not-leak"
RUN_ID = "11111111-1111-1111-1111-111111111111"

N_SPLITS = 550

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


def _make_split(index: int) -> dict:
    return {
        "split_index": index,
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


def _make_points(split_index: int, n_points: int = 20) -> list[dict]:
    """20 realistic (non-empty) points per baseline per split -- the same
    default per-split point count `GET /runs/{run_id}/splits/{split_index}/
    points` already defaults to (VS-033), so this fixture exercises a
    realistic per-split payload size, not a degenerate empty one."""
    points = []
    for i in range(n_points):
        points.append(
            {
                "timestamp": f"2026-01-10T{6 + (i % 18):02d}:00:00Z",
                "predicted": 1.0 + split_index * 0.001 + i * 0.01,
                "actual": 1.1 + split_index * 0.001 + i * 0.01,
                "baseline_key": "naive_last",
            }
        )
    return points


SPLITS_FIXTURE = [_make_split(i) for i in range(N_SPLITS)]


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


def test_run_detail_550_splits_completes_under_two_seconds(monkeypatch) -> None:
    """Hard `assert elapsed < 2.0` per the ticket's own Test AC -- not a
    printed/logged value only."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/runs/{RUN_ID}":
            return httpx.Response(200, json=RUN_DETAIL_BODY)
        if request.url.path == f"/runs/{RUN_ID}/splits/count":
            return httpx.Response(200, json={"total": N_SPLITS})
        if request.url.path == f"/runs/{RUN_ID}/splits":
            return httpx.Response(200, json=SPLITS_FIXTURE)
        if request.url.path == f"/runs/{RUN_ID}/splits/points":
            split_indices = [int(v) for v in request.url.params.get_list("split_index")]
            items = [
                {"split_index": idx, "points": _make_points(idx)} for idx in split_indices
            ]
            return httpx.Response(200, json={"items": items})
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    start = time.perf_counter()
    response = client.get(f"/runs/{RUN_ID}")
    elapsed = time.perf_counter() - start

    assert response.status_code == 200
    # Sanity: this really rendered all 550 splits' worth of table rows, not a
    # truncated/degenerate page that would pass this budget trivially.
    assert response.text.count("verdict-label-") == N_SPLITS

    print(
        f"\nRAV-016 fixture-level latency: run_detail for a {N_SPLITS}-split run took "
        f"{elapsed:.3f}s (network latency mocked to near-zero via httpx.MockTransport; "
        "not a substitute for the QA gate's real Docker-stack measurement)."
    )
    assert elapsed < 2.0, (
        f"run_detail for a {N_SPLITS}-split run took {elapsed:.3f}s (fixture-level, "
        "network latency mocked to near-zero) -- exceeds the 2s budget"
    )
