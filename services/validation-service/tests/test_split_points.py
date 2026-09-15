"""VS-031: `POST /runs` split_points persistence tests.

New file, mirroring `test_runs_endpoint.py`/`test_client_baseline_endpoint.py`'s
per-test-SQLite-file setup rather than duplicating it in a new fixture module.
Expected point counts/values are derived independently from
`naive_first_engine.splitting.generate_splits` plus the request's own
`train_window`/`test_window`/`step`, never read back from the endpoint's own
persisted rows -- a tautological "trust what was just written" check would not
actually prove the right values were captured.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from naive_first_engine.splitting import generate_splits

VALID_CONFIG = {
    "horizon": 1,
    "purge_gap_hours": 0,
    "train_window": 10,
    "test_window": 5,
    "step": 5,
}


def _returns_like_values(n: int, seed: int = 7) -> list[float]:
    return np.random.default_rng(seed).normal(0.0, 0.01, size=n).tolist()


def _inline_dataset(n: int = 40) -> dict:
    start = datetime(2024, 1, 1)
    timestamps = [(start + timedelta(hours=i)).isoformat() for i in range(n)]
    values = _returns_like_values(n)
    return {"inline": {"timestamps": timestamps, "values": values}}


def _index(n: int = 40) -> pd.DatetimeIndex:
    start = pd.Timestamp("2024-01-01")
    return pd.DatetimeIndex([start + pd.Timedelta(hours=i) for i in range(n)])


def _series(n: int = 40, seed: int = 7) -> pd.Series:
    return pd.Series(_returns_like_values(n, seed=seed), index=_index(n))


def _client(tmp_path, monkeypatch) -> tuple[TestClient, str]:
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    return TestClient(app), db_path


def test_post_runs_persists_expected_split_point_rows_and_values(tmp_path, monkeypatch):
    client, db_path = _client(tmp_path, monkeypatch)
    from app.repositories.sqlite_repository import SQLiteSplitPointRepository

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        **VALID_CONFIG,
    }
    response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]

    splits = generate_splits(
        _index(),
        VALID_CONFIG["train_window"],
        VALID_CONFIG["test_window"],
        VALID_CONFIG["step"],
        purge_gap=VALID_CONFIG["purge_gap_hours"],
    )
    expected_baselines = 2  # naive_last, naive0 -- no client_prediction_reference
    expected_row_count = len(splits) * expected_baselines * VALID_CONFIG["test_window"]

    point_repository = SQLiteSplitPointRepository(db_path)
    all_points = []
    for split_index in range(len(splits)):
        all_points.extend(point_repository.get_points("tenant-1", run_id, split_index))

    assert len(all_points) == expected_row_count

    series = _series()
    for split_index, split in enumerate(splits):
        test_window = series.loc[split.test_start : split.test_end]
        points = point_repository.get_points("tenant-1", run_id, split_index)
        for baseline_key in ("naive_last", "naive0"):
            baseline_points = sorted(
                (p for p in points if p.baseline_key == baseline_key),
                key=lambda p: p.timestamp,
            )
            assert [pd.Timestamp(p.timestamp) for p in baseline_points] == list(
                test_window.index
            )
            assert [p.actual for p in baseline_points] == list(test_window.to_numpy())
            if baseline_key == "naive0":
                # Naive0's own prediction convention (naive_first_engine.baselines)
                # is a flat 0.0 forecast -- verified structurally here, not
                # re-derived, since re-deriving it would duplicate that
                # module's own test suite.
                assert all(p.predicted == 0.0 for p in baseline_points)


def test_post_runs_with_no_client_baseline_persists_exactly_two_baselines_worth_of_points(
    tmp_path, monkeypatch
):
    client, db_path = _client(tmp_path, monkeypatch)
    from app.repositories.sqlite_repository import SQLiteSplitPointRepository

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        **VALID_CONFIG,
    }
    response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]

    point_repository = SQLiteSplitPointRepository(db_path)
    points = point_repository.get_points("tenant-1", run_id, split_index=0)

    baseline_keys = {p.baseline_key for p in points}
    assert baseline_keys == {"naive_last", "naive0"}
