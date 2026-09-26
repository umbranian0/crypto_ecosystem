"""RAV-012: `GET /runs/splits/summary` endpoint tests.

Follows the same `TestClient`/per-test-SQLite-file setup pattern as
`test_splits_endpoint.py`. Includes a regression-style assertion that this
path is genuinely handled by the new route -- not silently swallowed by
`GET /runs/{run_id}`'s pattern (the collision risk flagged in the ticket's
Analysis section).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
from fastapi.testclient import TestClient


def _returns_like_values(n: int, seed: int = 7) -> list[float]:
    """Same MR-001 fixture fix as test_splits_endpoint.py -- deterministic,
    zero-centered, low-autocorrelation values so `app.level_detection`'s
    price-level heuristic never rejects this fixture's inline dataset."""
    return np.random.default_rng(seed).normal(0.0, 0.01, size=n).tolist()


def _inline_dataset(n: int = 40) -> dict:
    start = datetime(2024, 1, 1)
    timestamps = [(start + timedelta(hours=i)).isoformat() for i in range(n)]
    values = _returns_like_values(n)
    return {"inline": {"timestamps": timestamps, "values": values}}


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


def test_splits_summary_returns_items_for_a_page_of_run_ids(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    run_id_1 = _make_run(client, "tenant-1", dataset_id="dataset-1")
    run_id_2 = _make_run(client, "tenant-1", dataset_id="dataset-2")

    expected_splits_1 = client.get(
        f"/runs/{run_id_1}/splits", headers={"X-Tenant-Id": "tenant-1"}
    ).json()
    expected_splits_2 = client.get(
        f"/runs/{run_id_2}/splits", headers={"X-Tenant-Id": "tenant-1"}
    ).json()

    response = client.get(
        "/runs/splits/summary",
        params=[("run_id", run_id_1), ("run_id", run_id_2)],
        headers={"X-Tenant-Id": "tenant-1"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    items_by_run_id = {item["run_id"]: item["splits"] for item in body["items"]}
    assert set(items_by_run_id.keys()) == {run_id_1, run_id_2}
    assert items_by_run_id[run_id_1] == expected_splits_1
    assert items_by_run_id[run_id_2] == expected_splits_2


def test_splits_summary_empty_run_id_list_returns_empty_items(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    response = client.get("/runs/splits/summary", headers={"X-Tenant-Id": "tenant-1"})

    assert response.status_code == 200, response.text
    assert response.json() == {"items": []}


def test_splits_summary_omits_unknown_and_foreign_tenant_run_ids(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    run_id_owned = _make_run(client, "tenant-1", dataset_id="dataset-owned")
    run_id_foreign = _make_run(client, "tenant-2", dataset_id="dataset-foreign")

    response = client.get(
        "/runs/splits/summary",
        params=[("run_id", run_id_owned), ("run_id", run_id_foreign), ("run_id", "does-not-exist")],
        headers={"X-Tenant-Id": "tenant-1"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    run_ids_in_response = {item["run_id"] for item in body["items"]}
    assert run_ids_in_response == {run_id_owned}


def test_splits_summary_route_not_swallowed_by_run_id_pattern(tmp_path, monkeypatch):
    """Regression-style assertion for this ticket's flagged collision risk:
    a request to `/runs/splits/summary` must resolve to the new handler, not
    `GET /runs/{run_id}`'s "run not found" 404."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    response = client.get("/runs/splits/summary", headers={"X-Tenant-Id": "tenant-1"})

    assert response.status_code == 200
    assert response.json() != {"detail": "run not found"}
    assert "items" in response.json()
