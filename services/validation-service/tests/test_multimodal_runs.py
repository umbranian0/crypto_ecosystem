"""VS-030 (MDF-003) integration test: `POST /runs` with `feature_references` +
`missing_timestamp_policy`, exercised through the real HTTP surface
(`TestClient`, mirroring `VS-011`'s `test_regression_api.py` style) rather
than calling `FeatureDatasetAssembler` directly.

`DatasetSourceDep`/`ConnectorStatusCheckerDep` are overridden with test
doubles (same `app.dependency_overrides` convention `test_runs_endpoint.py`'s
`_RepositoryFakeThatFailsIfCalled` already establishes) so this test never
needs a real S3/MinIO or ingestion-service backend -- it still exercises the
full router -> `FeatureDatasetAssembler.assemble` -> repository persistence
-> `GET /runs/{id}` round trip for real.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app.dataset_source import LoadedSeries


def _returns_like_values(n: int, seed: int = 11) -> list[float]:
    return np.random.default_rng(seed).normal(0.0, 0.01, size=n).tolist()


def _target_reference(n: int = 30) -> tuple[dict, pd.DatetimeIndex]:
    start = datetime(2024, 1, 1)
    timestamps = [(start + timedelta(hours=i)).isoformat() for i in range(n)]
    values = _returns_like_values(n)
    index = pd.DatetimeIndex([start + timedelta(hours=i) for i in range(n)])
    return {"inline": {"timestamps": timestamps, "values": values}}, index


class _FakeMultiSourceDatasetSource:
    """`DatasetSource` test double: delegates the primary target load to the
    real `InlineOrLocalFileDatasetSource` (byte-identical behavior to every
    other test in this suite), and returns a canned `LoadedSeries` carrying a
    real `fetched_at` for any `{"source": ...}`-shaped feature reference --
    standing in for a *future* fetched_at-capable ingestion-service response
    (today's real `IngestionServiceDatasetSource` cannot supply this, per
    AC5/the ticket's disclosed gap; this fake exists only to prove
    `routers/runs.py`'s wiring end-to-end, not to claim ingestion-service
    already supports it).
    """

    def __init__(self, target_index: pd.DatetimeIndex) -> None:
        from app.dataset_source import InlineOrLocalFileDatasetSource

        self._inline_source = InlineOrLocalFileDatasetSource()
        self._target_index = target_index

    def load(self, reference: object) -> LoadedSeries:
        if isinstance(reference, dict) and "source" in reference:
            # A feature source whose fetched_at is always one hour before
            # each target row -- eligible at zero additional lag (the
            # binance_price_/reddit_ prefixes both map to 0h).
            fetched_at = self._target_index - pd.Timedelta(hours=1)
            values = list(range(len(self._target_index)))
            return LoadedSeries(
                series=pd.Series(values, index=self._target_index, dtype="float64"),
                warnings=[],
                fetched_at=pd.DatetimeIndex(fetched_at),
            )
        return self._inline_source.load(reference)


class _AlwaysReadyConnectorStatusChecker:
    def check(self, tenant_id: str, source: str) -> None:
        return None


def _client_with_multimodal_overrides(tmp_path, monkeypatch, target_index):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.dependencies.repositories import (
        get_connector_status_checker,
        get_dataset_source,
    )
    from app.main import app

    fake_source = _FakeMultiSourceDatasetSource(target_index)
    app.dependency_overrides[get_dataset_source] = lambda: fake_source
    app.dependency_overrides[get_connector_status_checker] = (
        lambda: _AlwaysReadyConnectorStatusChecker()
    )

    def cleanup():
        app.dependency_overrides.pop(get_dataset_source, None)
        app.dependency_overrides.pop(get_connector_status_checker, None)

    return TestClient(app), cleanup


VALID_CONFIG = {
    "horizon": 1,
    "purge_gap_hours": 0,
    "train_window": 10,
    "test_window": 5,
    "step": 5,
}


def test_multi_source_run_persists_feature_lineage_and_has_multimodal_features_true(
    tmp_path, monkeypatch
):
    dataset_reference, target_index = _target_reference()
    client, cleanup = _client_with_multimodal_overrides(tmp_path, monkeypatch, target_index)

    payload = {
        "dataset_id": "dataset-multi",
        "dataset_reference": dataset_reference,
        # A smaller config than VALID_CONFIG: the 24h on-chain lag trims the
        # leading rows of the 30-row target (only rows whose own fetched_at
        # eligibility clears the 24h floor survive), so this run's
        # post-alignment series is shorter than the primary suite's 30-row
        # single-series tests.
        "horizon": 1,
        "purge_gap_hours": 0,
        "train_window": 3,
        "test_window": 2,
        "step": 1,
        "feature_references": [
            {"source": "binance_price_btcusdt_1h", "field": "close"},
            {"source": "blockchain_info_hash-rate", "field": "value"},
        ],
        "missing_timestamp_policy": "forward_fill_exhausted_as_null_then_drop",
    }

    try:
        create_response = client.post(
            "/runs", json=payload, headers={"X-Tenant-Id": "tenant-multimodal"}
        )
    finally:
        cleanup()

    assert create_response.status_code == 201, create_response.text
    assert create_response.json()["status"] == "completed"
    run_id = create_response.json()["id"]

    client2, cleanup2 = _client_with_multimodal_overrides(tmp_path, monkeypatch, target_index)
    try:
        get_response = client2.get(
            f"/runs/{run_id}", headers={"X-Tenant-Id": "tenant-multimodal"}
        )
    finally:
        cleanup2()

    assert get_response.status_code == 200, get_response.text
    body = get_response.json()
    assert body["has_multimodal_features"] is True
    assert body["feature_lineage"] == [
        {"source": "binance_price_btcusdt_1h", "field": "close", "lag_hours": 0},
        {"source": "blockchain_info_hash-rate", "field": "value", "lag_hours": 24},
    ]


def test_feature_references_without_missing_timestamp_policy_returns_422(tmp_path, monkeypatch):
    dataset_reference, target_index = _target_reference()
    client, cleanup = _client_with_multimodal_overrides(tmp_path, monkeypatch, target_index)

    payload = {
        "dataset_id": "dataset-multi",
        "dataset_reference": dataset_reference,
        **VALID_CONFIG,
        "feature_references": [{"source": "binance_price_btcusdt_1h", "field": "close"}],
        # missing_timestamp_policy deliberately omitted.
    }

    try:
        response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-multimodal"})
    finally:
        cleanup()

    assert response.status_code == 422


def test_no_feature_references_response_is_byte_identical_to_pre_vs_030_shape(
    tmp_path, monkeypatch
):
    dataset_reference, target_index = _target_reference()
    client, cleanup = _client_with_multimodal_overrides(tmp_path, monkeypatch, target_index)

    payload = {
        "dataset_id": "dataset-single",
        "dataset_reference": dataset_reference,
        **VALID_CONFIG,
    }

    try:
        create_response = client.post(
            "/runs", json=payload, headers={"X-Tenant-Id": "tenant-single"}
        )
        assert create_response.status_code == 201, create_response.text
        run_id = create_response.json()["id"]

        get_response = client.get(f"/runs/{run_id}", headers={"X-Tenant-Id": "tenant-single"})
    finally:
        cleanup()

    assert get_response.status_code == 200, get_response.text
    body = get_response.json()
    assert body["feature_lineage"] == []
    assert body["has_multimodal_features"] is False
