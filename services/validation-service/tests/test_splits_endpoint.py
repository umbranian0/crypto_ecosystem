"""VS-008: `GET /runs/{id}/splits` endpoint tests.

Follows the same `TestClient`/per-test-SQLite-file setup pattern as
`test_runs_endpoint.py` (own file per this ticket's Design section, to avoid
touching `runs.py`/that test file, keeping VS-008 conflict-free with VS-007/
VS-009 which edit `runs.py`).

Round-trip test: the expected `SplitResult` list is computed independently by
calling `run_validation_protocol` directly in the test, on the same series/
config the endpoint's `POST /runs` call used -- not read back from the
endpoint's own response -- so this is a genuine check that the endpoint
surfaces what the protocol actually produced, not a tautology.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from naive_first_engine.protocol import (
    NAIVE0_KEY,
    NAIVE_LAST_KEY,
    ValidationConfig,
    run_validation_protocol,
)


def _returns_like_values(n: int, seed: int = 7) -> list[float]:
    """MR-001 fixture fix: was `[float(i) for i in range(n)]`, a monotonic
    ramp -- unrelated to this file's actual intent (round-trip parity between
    the endpoint's persisted output and directly calling
    `run_validation_protocol`), but which incidentally matched MR-001's
    price-level heuristic. Deterministic, zero-centered,
    low-autocorrelation values instead. Shared by `_inline_dataset`/`_series`
    (same seed) so both encode the identical underlying series -- required
    for this file's own round-trip comparison to be meaningful.
    """
    return np.random.default_rng(seed).normal(0.0, 0.01, size=n).tolist()


def _inline_dataset(n: int = 40) -> dict:
    start = datetime(2024, 1, 1)
    timestamps = [(start + timedelta(hours=i)).isoformat() for i in range(n)]
    values = _returns_like_values(n)
    return {"inline": {"timestamps": timestamps, "values": values}}


def _series(n: int = 40) -> pd.Series:
    start = pd.Timestamp("2024-01-01")
    index = pd.DatetimeIndex([start + pd.Timedelta(hours=i) for i in range(n)])
    return pd.Series(_returns_like_values(n), index=index, dtype="float64")


# train_window=10, test_window=5, step=5 over 40 points produces >= 2 splits.
VALID_CONFIG = {
    "horizon": 1,
    "purge_gap_hours": 0,
    "train_window": 10,
    "test_window": 5,
    "step": 5,
}


def _make_run(client: TestClient, tenant_id: str, dataset_id: str = "dataset-1") -> str:
    payload = {
        "dataset_id": dataset_id,
        "dataset_reference": _inline_dataset(),
        **VALID_CONFIG,
    }
    response = client.post("/runs", json=payload, headers={"X-Tenant-Id": tenant_id})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_splits_roundtrip_matches_independently_computed_protocol_output(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    run_id = _make_run(client, "tenant-1")

    # Independently computed expected splits -- calling run_validation_protocol
    # directly, on the same series/config the request used, not derived from
    # the endpoint response itself.
    config = ValidationConfig(
        train_window=VALID_CONFIG["train_window"],
        test_window=VALID_CONFIG["test_window"],
        step=VALID_CONFIG["step"],
        purge_gap=VALID_CONFIG["purge_gap_hours"],
        horizon=VALID_CONFIG["horizon"],
    )
    expected_results = run_validation_protocol(_series(), config)
    assert len(expected_results) >= 2  # sanity: multi-split dataset per AC

    response = client.get(f"/runs/{run_id}/splits", headers={"X-Tenant-Id": "tenant-1"})
    assert response.status_code == 200, response.text
    body = response.json()

    assert len(body) == len(expected_results)

    for actual, expected in zip(body, expected_results):
        model = expected.baseline_results[NAIVE_LAST_KEY]
        naive0 = expected.baseline_results[NAIVE0_KEY]
        dm_result = model.dm_result

        assert actual["split_index"] == expected.split_index

        assert actual["train_start"] == expected.boundaries.train_start.isoformat()
        assert actual["train_end"] == expected.boundaries.train_end.isoformat()
        assert actual["test_start"] == expected.boundaries.test_start.isoformat()
        assert actual["test_end"] == expected.boundaries.test_end.isoformat()

        assert actual["model_mae"] == model.metrics.mae
        assert actual["model_rmse"] == model.metrics.rmse
        assert actual["model_smape"] == model.metrics.smape
        assert actual["model_mase"] == model.metrics.mase
        assert actual["model_da"] == model.metrics.da
        assert actual["model_f1"] == model.metrics.f1
        assert actual["model_oos_r2"] == model.metrics.oos_r2

        assert actual["naive0_mae"] == naive0.metrics.mae
        assert actual["naive0_rmse"] == naive0.metrics.rmse
        assert actual["naive0_smape"] == naive0.metrics.smape
        assert actual["naive0_mase"] == naive0.metrics.mase
        assert actual["naive0_da"] == naive0.metrics.da
        assert actual["naive0_f1"] == naive0.metrics.f1
        assert actual["naive0_oos_r2"] == naive0.metrics.oos_r2

        assert actual["dm_statistic"] == dm_result.statistic
        assert actual["dm_pvalue"] == dm_result.p_value
        assert actual["dm_verdict"] == dm_result.verdict


def test_splits_returned_in_ascending_split_index_order(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    run_id = _make_run(client, "tenant-1")

    response = client.get(f"/runs/{run_id}/splits", headers={"X-Tenant-Id": "tenant-1"})
    assert response.status_code == 200, response.text
    body = response.json()

    indices = [row["split_index"] for row in body]
    assert len(indices) >= 2  # multi-split dataset, per AC
    assert indices == sorted(indices)
    assert indices == list(range(len(indices)))


def test_splits_cross_tenant_returns_404_with_no_leaked_data(tmp_path, monkeypatch):
    """Load-bearing tenant-isolation test (VS-008 AC2, same standard as
    VS-004/007). A run created for `tenant-a` (with a distinguishable
    dataset id) must be unreachable, and none of its split data observable,
    via a GET scoped to `tenant-b` -- a distinct tenant id, not a typo/variant
    of the same one.
    """
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    run_id = _make_run(client, "tenant-a", dataset_id="dataset-secret")

    response = client.get(f"/runs/{run_id}/splits", headers={"X-Tenant-Id": "tenant-b"})

    assert response.status_code == 404
    body_text = response.text
    # Not just a status-code check: assert none of tenant-a's split data
    # (including the run id itself, which would confirm the run exists) is
    # observable anywhere in the response body.
    assert run_id not in body_text
    assert "tenant-a" not in body_text
    assert "dataset-secret" not in body_text
    assert "split_index" not in body_text
    assert "train_start" not in body_text
    assert "dm_verdict" not in body_text
    body = response.json()
    assert set(body.keys()) == {"detail"}


def test_splits_nonexistent_run_returns_404(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    response = client.get("/runs/does-not-exist/splits", headers={"X-Tenant-Id": "tenant-1"})

    assert response.status_code == 404
    assert response.status_code != 500


def test_splits_with_limit_and_offset_returns_bounded_page(tmp_path, monkeypatch):
    """DBOPT-011: route test for `GET /runs/{run_id}/splits?limit=&offset=`.
    train_window=10, test_window=5, step=5 over 100 points produces 17
    splits, plenty to page through."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(n=100),
        "horizon": 1,
        "purge_gap_hours": 0,
        "train_window": 10,
        "test_window": 5,
        "step": 5,
    }
    response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]

    full_response = client.get(f"/runs/{run_id}/splits", headers={"X-Tenant-Id": "tenant-1"})
    assert full_response.status_code == 200
    full_body = full_response.json()
    assert len(full_body) >= 10  # sanity: enough splits to page through

    bounded_response = client.get(
        f"/runs/{run_id}/splits",
        params={"limit": 3, "offset": 6},
        headers={"X-Tenant-Id": "tenant-1"},
    )
    assert bounded_response.status_code == 200, bounded_response.text
    bounded_body = bounded_response.json()

    assert [row["split_index"] for row in bounded_body] == [6, 7, 8]
    assert bounded_body == full_body[6:9]


def test_splits_count_returns_correct_total(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    run_id = _make_run(client, "tenant-1")

    full_response = client.get(f"/runs/{run_id}/splits", headers={"X-Tenant-Id": "tenant-1"})
    assert full_response.status_code == 200
    expected_total = len(full_response.json())

    count_response = client.get(f"/runs/{run_id}/splits/count", headers={"X-Tenant-Id": "tenant-1"})

    assert count_response.status_code == 200, count_response.text
    assert count_response.json() == {"total": expected_total}


def test_splits_count_nonexistent_run_returns_404(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    response = client.get(
        "/runs/does-not-exist/splits/count", headers={"X-Tenant-Id": "tenant-1"}
    )

    assert response.status_code == 404
    assert response.status_code != 500


def test_splits_count_cross_tenant_returns_404_with_no_leaked_data(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    run_id = _make_run(client, "tenant-a", dataset_id="dataset-secret")

    response = client.get(f"/runs/{run_id}/splits/count", headers={"X-Tenant-Id": "tenant-b"})

    assert response.status_code == 404
    body = response.json()
    assert set(body.keys()) == {"detail"}
    assert "total" not in response.text


def test_splits_count_route_is_not_swallowed_by_split_index_points_route(tmp_path, monkeypatch):
    """DBOPT-011 regression: `/runs/{run_id}/splits/count` (4 segments) must
    resolve to `get_splits_count`, not be misrouted to
    `/runs/{run_id}/splits/{split_index}/points` (5 segments) or any other
    existing route -- a `{"total": ...}` shape (no `items`/`limit`/`offset`
    envelope) is proof it hit the right handler."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    run_id = _make_run(client, "tenant-1")

    response = client.get(f"/runs/{run_id}/splits/count", headers={"X-Tenant-Id": "tenant-1"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {"total"}
    assert isinstance(body["total"], int)
