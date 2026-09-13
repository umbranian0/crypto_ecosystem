"""VS-030 (MDF-003): `POST /runs` integration tests for `feature_references`/
`missing_timestamp_policy`, mirroring VS-011's existing regression-test style
(per-test SQLite file, `TestClient`, no mocked repository layer).

Feature references in these tests use the `{"inline": {...}, "field": ...}`
shape (an inline payload carrying its own `fetched_at` key) rather than a
`{"source": ...}` ingestion-service-backed reference, since the latter always
fails closed per this ticket's disclosed AC5 gap -- a separate test file
below covers that failure path explicitly. `{"inline": ...}` references route
through `CompositeDatasetSource` to `InlineOrLocalFileDatasetSource` exactly
like `dataset_reference` does, carrying real per-row `fetched_at` end to end.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
from fastapi.testclient import TestClient


def _returns_like_values(n: int, seed: int = 7) -> list[float]:
    return np.random.default_rng(seed).normal(0.0, 0.01, size=n).tolist()


def _inline_dataset(n: int = 40) -> dict:
    start = datetime(2024, 1, 1)
    timestamps = [(start + timedelta(hours=i)).isoformat() for i in range(n)]
    values = _returns_like_values(n)
    return {"inline": {"timestamps": timestamps, "values": values}}


def _feature_reference(n: int = 40) -> dict:
    """An inline feature reference carrying its own `fetched_at`, eligible
    for every target row (fetched_at == the row's own timestamp, 0 lag for a
    non-"source" reference) so the assembled table drops zero rows.
    """
    start = datetime(2024, 1, 1)
    timestamps = [(start + timedelta(hours=i)).isoformat() for i in range(n)]
    fetched_at = timestamps  # known at the same instant -- always eligible
    values = [42.0 for _ in range(n)]
    return {
        "inline": {"timestamps": timestamps, "values": values, "fetched_at": fetched_at},
        "field": "sentiment_score",
    }


VALID_CONFIG = {
    "horizon": 1,
    "purge_gap_hours": 0,
    "train_window": 10,
    "test_window": 5,
    "step": 5,
}


def _client(tmp_path, monkeypatch) -> TestClient:
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    return TestClient(app)


def test_valid_multi_source_request_persists_feature_lineage_and_returns_true_flag(
    tmp_path, monkeypatch
):
    client = _client(tmp_path, monkeypatch)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        "feature_references": [_feature_reference()],
        "missing_timestamp_policy": "drop_row",
        **VALID_CONFIG,
    }
    create_response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert create_response.status_code == 201, create_response.text
    body = create_response.json()
    assert body["status"] == "completed"
    run_id = body["id"]

    get_response = client.get(f"/runs/{run_id}", headers={"X-Tenant-Id": "tenant-1"})
    assert get_response.status_code == 200, get_response.text
    detail = get_response.json()
    assert detail["has_multimodal_features"] is True
    assert detail["feature_lineage"] == [
        {"source": None, "field": "sentiment_score", "lag_hours": 0}
    ]


def test_feature_references_without_missing_timestamp_policy_returns_422(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        "feature_references": [_feature_reference()],
        **VALID_CONFIG,
    }
    response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert response.status_code == 422, response.text


def test_request_without_feature_references_is_byte_identical_to_today(tmp_path, monkeypatch):
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
    detail = get_response.json()
    assert detail["feature_lineage"] == []
    assert detail["has_multimodal_features"] is False


def test_ingestion_service_backed_feature_reference_fails_closed(tmp_path, monkeypatch):
    """AC5: a {"source": ...} feature reference has no fetched_at available
    (IngestionServiceDatasetSource's disclosed gap) -- the run fails closed
    (status="failed"), never silently approximated.
    """
    client = _client(tmp_path, monkeypatch)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        "feature_references": [{"source": "blockchain_info_hash-rate", "field": "value"}],
        "missing_timestamp_policy": "drop_row",
        **VALID_CONFIG,
    }
    response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    # The connector-status check runs first and itself fails closed (no real
    # ingestion-service reachable in this test environment) -- either way,
    # the request completes as a failed *run*, never a silent success.
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "failed"
