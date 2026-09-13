"""VS-029: `has_client_model` field on `RunDetailResponse` (`GET /runs/{id}`)
and `SplitResultResponse` (`GET /runs/{id}/splits`).

Reuses VS-017's own fixture pattern (`test_client_baseline_endpoint.py`):
a `client_prediction_reference`-bearing request must round-trip
`has_client_model=True` through both endpoints; a request with no
`client_prediction_reference` must round-trip `has_client_model=False`.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
from fastapi.testclient import TestClient

VALID_CONFIG = {
    "horizon": 1,
    "purge_gap_hours": 0,
    "train_window": 10,
    "test_window": 5,
    "step": 5,
}


def _inline_dataset(n: int = 40) -> dict:
    start = datetime(2024, 1, 1)
    timestamps = [(start + timedelta(hours=i)).isoformat() for i in range(n)]
    values = np.random.default_rng(7).normal(0.0, 0.01, size=n).tolist()
    return {"inline": {"timestamps": timestamps, "values": values}}


def _client_prediction_dataset(n: int = 40) -> dict:
    start = datetime(2024, 1, 1)
    timestamps = [(start + timedelta(hours=i)).isoformat() for i in range(n)]
    values = [42.0 for _ in range(n)]
    return {"inline": {"timestamps": timestamps, "values": values}}


def _client(tmp_path, monkeypatch) -> TestClient:
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    return TestClient(app)


def test_get_run_has_client_model_true_with_client_prediction_reference(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        "client_prediction_reference": _client_prediction_dataset(),
        **VALID_CONFIG,
    }
    create_response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert create_response.status_code == 201, create_response.text
    run_id = create_response.json()["id"]

    get_response = client.get(f"/runs/{run_id}", headers={"X-Tenant-Id": "tenant-1"})
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["has_client_model"] is True


def test_get_run_has_client_model_false_without_client_prediction_reference(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        **VALID_CONFIG,
    }
    create_response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert create_response.status_code == 201, create_response.text
    run_id = create_response.json()["id"]

    get_response = client.get(f"/runs/{run_id}", headers={"X-Tenant-Id": "tenant-1"})
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["has_client_model"] is False


def test_get_splits_has_client_model_true_per_split_with_client_prediction_reference(
    tmp_path, monkeypatch
):
    client = _client(tmp_path, monkeypatch)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        "client_prediction_reference": _client_prediction_dataset(),
        **VALID_CONFIG,
    }
    create_response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert create_response.status_code == 201, create_response.text
    run_id = create_response.json()["id"]

    splits_response = client.get(f"/runs/{run_id}/splits", headers={"X-Tenant-Id": "tenant-1"})
    assert splits_response.status_code == 200, splits_response.text
    splits = splits_response.json()
    assert len(splits) > 0
    assert all(split["has_client_model"] is True for split in splits)


def test_get_splits_has_client_model_false_per_split_without_client_prediction_reference(
    tmp_path, monkeypatch
):
    client = _client(tmp_path, monkeypatch)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        **VALID_CONFIG,
    }
    create_response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert create_response.status_code == 201, create_response.text
    run_id = create_response.json()["id"]

    splits_response = client.get(f"/runs/{run_id}/splits", headers={"X-Tenant-Id": "tenant-1"})
    assert splits_response.status_code == 200, splits_response.text
    splits = splits_response.json()
    assert len(splits) > 0
    assert all(split["has_client_model"] is False for split in splits)


def test_get_run_has_client_model_false_for_run_with_zero_splits(tmp_path, monkeypatch):
    """A run that failed before any splits were persisted (e.g. a load
    failure) has no splits to derive True from -- has_client_model must be
    False, not raise, on the `any()` over an empty list.
    """
    client = _client(tmp_path, monkeypatch)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": {"path": "/nonexistent/does-not-exist.csv"},
        **VALID_CONFIG,
    }
    create_response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert create_response.status_code == 201, create_response.text
    body = create_response.json()
    assert body["status"] == "failed"
    run_id = body["id"]

    get_response = client.get(f"/runs/{run_id}", headers={"X-Tenant-Id": "tenant-1"})
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["has_client_model"] is False
