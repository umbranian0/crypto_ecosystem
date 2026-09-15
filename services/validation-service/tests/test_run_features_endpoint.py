"""MR-007: `GET /runs/{run_id}/features` tests, following
`test_runs_endpoint.py`'s per-test-SQLite-file/`TestClient` convention.

MR-007's own binding design decision (see the ticket's Analysis section)
means this route cannot literally replay the original `assemble()` call --
`runs.missing_timestamp_policy` and the original `dataset_reference` dict are
not persisted. The 200-path tests below therefore override
`DatasetSourceDep`/`ConnectorStatusCheckerDep` with fakes that make
`dataset_source.load({"source": run.dataset_id})` (the one reconstructable
shape) succeed deterministically, without a real ingestion-service running --
the same "fake the dependency seam, don't hit a real network service"
convention `test_feature_dataset.py` already uses. The 422 test deliberately
does *not* override these, relying on the real `CompositeDatasetSource` ->
`IngestionServiceDatasetSource` failing to reach a real ingestion-service in
this test environment, which is itself the documented "not ingestion-service-
backed" / unreachable-reload failure mode this route must fail closed on.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app.dataset_source import DatasetSourceError, InlineOrLocalFileDatasetSource, LoadedSeries

VALID_CONFIG = {
    "horizon": 1,
    "purge_gap_hours": 0,
    "train_window": 10,
    "test_window": 5,
    "step": 5,
}


def _returns_like_values(n: int, seed: int = 7) -> list[float]:
    return np.random.default_rng(seed).normal(0.0, 0.01, size=n).tolist()


def _hourly_timestamps(n: int) -> list[str]:
    start = datetime(2024, 1, 1)
    return [(start + timedelta(hours=i)).isoformat() for i in range(n)]


def _inline_dataset(n: int = 40) -> dict:
    return {"inline": {"timestamps": _hourly_timestamps(n), "values": _returns_like_values(n)}}


def _hourly_index(n: int = 40) -> pd.DatetimeIndex:
    start = pd.Timestamp("2024-01-01")
    return pd.DatetimeIndex([start + pd.Timedelta(hours=i) for i in range(n)])


class _SourceBackedFakeDatasetSource:
    """`DatasetSource` test double (mirrors `test_feature_dataset.py`'s
    `_FakeDatasetSource` convention): `"inline"`-shaped references delegate
    to the real `InlineOrLocalFileDatasetSource` (unchanged POST /runs
    primary-load behavior); any `"source"`-shaped reference (both the
    feature reference and MR-007's own `{"source": run.dataset_id}` primary
    reload) returns one fixed, `fetched_at`-carrying series aligned onto the
    same index the inline primary dataset uses -- deterministic, no real
    ingestion-service network call.
    """

    def __init__(self, n: int = 40) -> None:
        self._index = _hourly_index(n)
        self._values = [42.0] * n

    def load(self, reference: object) -> LoadedSeries:
        if isinstance(reference, dict) and "inline" in reference:
            return InlineOrLocalFileDatasetSource().load(reference)
        if isinstance(reference, dict) and "source" in reference:
            return LoadedSeries(
                series=pd.Series(self._values, index=self._index, dtype="float64"),
                warnings=[],
                fetched_at=self._index,
            )
        raise DatasetSourceError(f"unsupported reference in test fake: {reference!r}")


class _AlwaysReadyConnectorStatusChecker:
    def check(self, tenant_id: str, source: str) -> None:
        return None


def _client_with_source_backed_fakes(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.dependencies.repositories import (
        get_connector_status_checker,
        get_dataset_source,
    )
    from app.main import app

    app.dependency_overrides[get_dataset_source] = lambda: _SourceBackedFakeDatasetSource()
    app.dependency_overrides[get_connector_status_checker] = (
        lambda: _AlwaysReadyConnectorStatusChecker()
    )

    def cleanup():
        app.dependency_overrides.pop(get_dataset_source, None)
        app.dependency_overrides.pop(get_connector_status_checker, None)

    return TestClient(app), cleanup


def _create_multimodal_run(client: TestClient, tenant_id: str = "tenant-1") -> str:
    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        "feature_references": [{"source": "binance_price", "field": "close"}],
        "missing_timestamp_policy": "drop_row",
        **VALID_CONFIG,
    }
    response = client.post("/runs", json=payload, headers={"X-Tenant-Id": tenant_id})
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "completed", response.text
    return response.json()["id"]


def test_no_multimodal_features_returns_404(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        **VALID_CONFIG,
    }
    create_response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert create_response.status_code == 201, create_response.text
    run_id = create_response.json()["id"]

    response = client.get(f"/runs/{run_id}/features", headers={"X-Tenant-Id": "tenant-1"})

    assert response.status_code == 404


def test_multimodal_run_returns_200_with_index_columns_data(tmp_path, monkeypatch):
    client, cleanup = _client_with_source_backed_fakes(tmp_path, monkeypatch)
    try:
        run_id = _create_multimodal_run(client)

        response = client.get(f"/runs/{run_id}/features", headers={"X-Tenant-Id": "tenant-1"})
    finally:
        cleanup()

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {"index", "columns", "data"}
    assert body["columns"] == ["binance_price.close"]
    assert len(body["index"]) == len(body["data"]) > 0


def test_repeated_calls_are_deterministic(tmp_path, monkeypatch):
    client, cleanup = _client_with_source_backed_fakes(tmp_path, monkeypatch)
    try:
        run_id = _create_multimodal_run(client)

        first = client.get(f"/runs/{run_id}/features", headers={"X-Tenant-Id": "tenant-1"})
        second = client.get(f"/runs/{run_id}/features", headers={"X-Tenant-Id": "tenant-1"})
    finally:
        cleanup()

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["columns"] == second.json()["columns"]
    assert first.json()["index"] == second.json()["index"]


def test_cross_tenant_returns_404_not_data(tmp_path, monkeypatch):
    client, cleanup = _client_with_source_backed_fakes(tmp_path, monkeypatch)
    try:
        run_id = _create_multimodal_run(client, tenant_id="tenant-a")

        response = client.get(f"/runs/{run_id}/features", headers={"X-Tenant-Id": "tenant-b"})
    finally:
        cleanup()

    assert response.status_code == 404
    body = response.json()
    assert set(body.keys()) == {"detail"}
    assert "binance_price" not in response.text


def test_unreloadable_primary_series_returns_422(tmp_path, monkeypatch):
    """AC/disclosed limitation: no dependency overrides here -- the real
    `CompositeDatasetSource` -> `IngestionServiceDatasetSource` cannot reach a
    real ingestion-service in this test environment, so
    `dataset_source.load({"source": run.dataset_id})` fails, and this route
    must fail closed with a 422 naming the limitation, never a silent
    empty/wrong table.
    """
    client, cleanup = _client_with_source_backed_fakes(tmp_path, monkeypatch)
    try:
        run_id = _create_multimodal_run(client)
    finally:
        cleanup()

    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    real_client = TestClient(app)
    response = real_client.get(f"/runs/{run_id}/features", headers={"X-Tenant-Id": "tenant-1"})

    assert response.status_code == 422, response.text
    assert "dataset_id" in response.json()["detail"] or "source" in response.json()["detail"]
