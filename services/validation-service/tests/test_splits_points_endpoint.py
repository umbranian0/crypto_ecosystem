"""RAV-016: `GET /runs/{run_id}/splits/points` batched endpoint tests.

Follows the same `TestClient`/per-test-SQLite-file setup pattern as
`test_split_points_endpoint.py`/`test_splits_summary_endpoint.py`. Router-level
tests are the ones that assert the per-requested-index completion contract
(one `SplitPoints` entry per requested `split_index`, `points: []` for an
absent one) -- the repository method itself may legitimately omit absent keys
per its own docstring, so that behavior is not what's under test at the
repository layer.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _returns_like_values(n: int, seed: int = 7) -> list[float]:
    return np.random.default_rng(seed).normal(0.0, 0.01, size=n).tolist()


def _inline_dataset(n: int = 60) -> dict:
    start = datetime(2024, 1, 1)
    timestamps = [(start + timedelta(hours=i)).isoformat() for i in range(n)]
    values = _returns_like_values(n)
    return {"inline": {"timestamps": timestamps, "values": values}}


# train_window=10, test_window=5, step=5 over 60 points produces >= 3 splits.
VALID_CONFIG = {
    "horizon": 1,
    "purge_gap_hours": 0,
    "train_window": 10,
    "test_window": 5,
    "step": 5,
}


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


def test_get_splits_points_returns_requested_splits_grouped_and_ordered(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    run_id = _make_run(client, "tenant-1")

    expected_0 = client.get(
        f"/runs/{run_id}/splits/0/points", headers={"X-Tenant-Id": "tenant-1"}
    ).json()["items"]
    expected_1 = client.get(
        f"/runs/{run_id}/splits/1/points", headers={"X-Tenant-Id": "tenant-1"}
    ).json()["items"]

    response = client.get(
        f"/runs/{run_id}/splits/points",
        params=[("split_index", 0), ("split_index", 1)],
        headers={"X-Tenant-Id": "tenant-1"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    items_by_split = {item["split_index"]: item["points"] for item in body["items"]}
    assert set(items_by_split.keys()) == {0, 1}
    assert items_by_split[0] == expected_0
    assert items_by_split[1] == expected_1
    # Split 2 was never requested -- must not leak into the response.
    assert 2 not in items_by_split


def test_get_splits_points_in_request_order(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    run_id = _make_run(client, "tenant-1")

    response = client.get(
        f"/runs/{run_id}/splits/points",
        params=[("split_index", 1), ("split_index", 0)],
        headers={"X-Tenant-Id": "tenant-1"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["split_index"] for item in body["items"]] == [1, 0]


def test_get_splits_points_unknown_index_degrades_to_empty_points_not_batch_404(
    tmp_path, monkeypatch
):
    client, _ = _client(tmp_path, monkeypatch)
    run_id = _make_run(client, "tenant-1")

    response = client.get(
        f"/runs/{run_id}/splits/points",
        params=[("split_index", 0), ("split_index", 9999)],
        headers={"X-Tenant-Id": "tenant-1"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    items_by_split = {item["split_index"]: item["points"] for item in body["items"]}
    # Every requested index gets exactly one entry -- the bad index degrades
    # to an empty list, it does not fail the whole batch.
    assert set(items_by_split.keys()) == {0, 9999}
    assert items_by_split[9999] == []
    assert items_by_split[0] != []


def test_get_splits_points_empty_split_index_list_returns_empty_items(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    run_id = _make_run(client, "tenant-1")

    response = client.get(
        f"/runs/{run_id}/splits/points", headers={"X-Tenant-Id": "tenant-1"}
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"items": []}


def test_get_splits_points_nonexistent_run_returns_404(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.get(
        "/runs/does-not-exist/splits/points",
        params=[("split_index", 0)],
        headers={"X-Tenant-Id": "tenant-1"},
    )
    assert response.status_code == 404


def test_get_splits_points_cross_tenant_returns_404_with_no_leaked_data(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    run_id = _make_run(client, "tenant-a", dataset_id="dataset-secret")

    response = client.get(
        f"/runs/{run_id}/splits/points",
        params=[("split_index", 0)],
        headers={"X-Tenant-Id": "tenant-b"},
    )
    assert response.status_code == 404
    body_text = response.text
    assert run_id not in body_text
    assert "tenant-a" not in body_text
    assert "dataset-secret" not in body_text
    assert "predicted" not in body_text


def test_get_splits_points_pruned_split_returns_empty_not_error(tmp_path, monkeypatch):
    client, db_path = _client(tmp_path, monkeypatch)
    run_id = _make_run(client, "tenant-1")

    from app.models import SplitPoint
    from app.repositories import sqlite_repository as sqlite_repository_module
    from app.repositories.sqlite_repository import SQLiteSplitPointRepository

    point_repository = SQLiteSplitPointRepository(db_path)
    engine = point_repository._engine

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
        f"/runs/{run_id}/splits/points",
        params=[("split_index", 0), ("split_index", 1)],
        headers={"X-Tenant-Id": "tenant-1"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    items_by_split = {item["split_index"]: item["points"] for item in body["items"]}
    # Split 0's points were pruned -- degrades to empty, same as the
    # single-split endpoint's own pruned-split behavior, not an error.
    assert items_by_split[0] == []
    assert items_by_split[1] != []


def test_get_splits_points_retention_excludes_rows_older_than_cutoff(tmp_path, monkeypatch):
    """VS-032 retention parity: a split whose only points are older than
    `SPLIT_POINT_RETENTION_DAYS` is excluded from this batched endpoint's
    result the same way it already is from the single-split endpoint --
    reuses `test_split_point_retention.py`'s own direct-insert pattern."""
    client, db_path = _client(tmp_path, monkeypatch)
    run_id = _make_run(client, "tenant-1")

    from app.models import SplitPoint
    from app.repositories import sqlite_repository as sqlite_repository_module
    from app.repositories.sqlite_repository import SQLiteSplitPointRepository

    point_repository = SQLiteSplitPointRepository(db_path)
    engine = point_repository._engine

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
                id="out-of-window-point",
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

    result = point_repository.get_points_for_splits("tenant-1", run_id, [0, 1])
    assert 0 not in result
    assert 1 in result


def test_existing_single_split_points_endpoint_tests_still_pass_unmodified(tmp_path, monkeypatch):
    """Regression sentinel: the shared `_split_point_to_response` extraction
    must not have altered the single-split endpoint's own response shape."""
    client, _ = _client(tmp_path, monkeypatch)
    run_id = _make_run(client, "tenant-1")

    response = client.get(
        f"/runs/{run_id}/splits/0/points", headers={"X-Tenant-Id": "tenant-1"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {"items", "limit", "offset", "total"}
    for item in body["items"]:
        assert set(item.keys()) == {"timestamp", "predicted", "actual", "baseline_key"}
