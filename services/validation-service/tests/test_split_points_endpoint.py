"""VS-033: `GET /runs/{run_id}/splits/{split_index}/points` endpoint tests.

Follows the same per-test-SQLite-file `TestClient` setup as
`test_splits_endpoint.py`/`test_split_points.py`. The pruned-split test
reuses `test_split_point_retention.py`'s own direct-`Session`-insert pattern
(inserting a `SplitPoint` row with a controlled, out-of-window `created_at`)
and the real `SPLIT_POINT_RETENTION_DAYS` constant -- not a separately
hardcoded cutoff date.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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


def _client(tmp_path, monkeypatch) -> tuple[TestClient, str]:
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    return TestClient(app), db_path


def _make_run(client: TestClient, tenant_id: str, dataset_id: str = "dataset-1") -> str:
    payload = {
        "dataset_id": dataset_id,
        "dataset_reference": _inline_dataset(),
        **VALID_CONFIG,
    }
    response = client.post("/runs", json=payload, headers={"X-Tenant-Id": tenant_id})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_get_split_points_default_pagination(tmp_path, monkeypatch):
    client, db_path = _client(tmp_path, monkeypatch)
    run_id = _make_run(client, "tenant-1")

    from app.repositories.sqlite_repository import SQLiteSplitPointRepository

    point_repository = SQLiteSplitPointRepository(db_path)
    expected_points = point_repository.get_points("tenant-1", run_id, split_index=0)
    # naive_last + naive0, each test_window=5 rows -> 10 points for split 0.
    assert len(expected_points) == 10

    response = client.get(
        f"/runs/{run_id}/splits/0/points", headers={"X-Tenant-Id": "tenant-1"}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["limit"] == 20
    assert body["offset"] == 0
    assert body["total"] == 10
    assert len(body["items"]) == 10
    for item in body["items"]:
        assert set(item.keys()) == {"timestamp", "predicted", "actual", "baseline_key"}


def test_get_split_points_non_default_limit_offset(tmp_path, monkeypatch):
    client, db_path = _client(tmp_path, monkeypatch)
    run_id = _make_run(client, "tenant-1")

    from app.repositories.sqlite_repository import SQLiteSplitPointRepository

    point_repository = SQLiteSplitPointRepository(db_path)
    all_points = point_repository.get_points("tenant-1", run_id, split_index=0)

    response = client.get(
        f"/runs/{run_id}/splits/0/points?limit=3&offset=2",
        headers={"X-Tenant-Id": "tenant-1"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["limit"] == 3
    assert body["offset"] == 2
    assert body["total"] == len(all_points)
    assert len(body["items"]) == 3
    expected_slice = all_points[2:5]
    assert [item["predicted"] for item in body["items"]] == [p.predicted for p in expected_slice]


def test_get_split_points_nonexistent_run_returns_404(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.get(
        "/runs/does-not-exist/splits/0/points", headers={"X-Tenant-Id": "tenant-1"}
    )
    assert response.status_code == 404
    assert response.status_code != 500


def test_get_split_points_cross_tenant_returns_404_with_no_leaked_data(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    run_id = _make_run(client, "tenant-a", dataset_id="dataset-secret")

    response = client.get(
        f"/runs/{run_id}/splits/0/points", headers={"X-Tenant-Id": "tenant-b"}
    )
    assert response.status_code == 404
    body_text = response.text
    assert run_id not in body_text
    assert "tenant-a" not in body_text
    assert "dataset-secret" not in body_text
    assert "predicted" not in body_text
    assert "baseline_key" not in body_text
    body = response.json()
    assert set(body.keys()) == {"detail"}


def test_get_split_points_out_of_range_split_index_returns_404(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    run_id = _make_run(client, "tenant-1")

    response = client.get(
        f"/runs/{run_id}/splits/9999/points", headers={"X-Tenant-Id": "tenant-1"}
    )
    assert response.status_code == 404


def test_get_split_points_pruned_split_returns_empty_not_error(tmp_path, monkeypatch):
    client, db_path = _client(tmp_path, monkeypatch)
    run_id = _make_run(client, "tenant-1")

    from app.models import SplitPoint
    from app.repositories import sqlite_repository as sqlite_repository_module
    from app.repositories.sqlite_repository import SQLiteSplitPointRepository

    point_repository = SQLiteSplitPointRepository(db_path)
    engine = point_repository._engine

    # Delete the real, freshly-persisted points for split_index=0 so this
    # split's only remaining row is the deliberately out-of-window one below
    # -- proves the empty-not-error path, not merely "an empty split that
    # never had points".
    with Session(engine) as session:
        session.query(SplitPoint).filter(
            SplitPoint.run_id == run_id, SplitPoint.split_index == 0
        ).delete()
        session.commit()

    out_of_window = datetime.utcnow() - timedelta(
        days=sqlite_repository_module.SPLIT_POINT_RETENTION_DAYS + 1
    )
    with Session(engine) as session:
        session.add(
            SplitPoint(
                id="pruned-point",
                run_id=run_id,
                tenant_id="tenant-1",
                split_index=0,
                baseline_key="naive0",
                timestamp=out_of_window,
                predicted=0.0,
                actual=0.0,
                created_at=out_of_window,
            )
        )
        session.commit()

    response = client.get(
        f"/runs/{run_id}/splits/0/points", headers={"X-Tenant-Id": "tenant-1"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
