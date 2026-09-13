"""MR-001: `POST /runs` price-level guardrail, integration-tested through the
real HTTP surface (FastAPI `TestClient`), same style as
`test_split_count_guardrail.py`.

Every test here overrides `get_dataset_source` with a fake `DatasetSource`
that returns a cheaply-constructed `pandas.Series` -- the guardrail only
cares about `series` values, so this is a faithful substitute for a real
dataset load, matching this module's existing "fake at the DI seam" testing
convention.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.dataset_source import LoadedSeries

VALID_CONFIG = {
    "horizon": 1,
    "purge_gap_hours": 0,
    "train_window": 10,
    "test_window": 5,
    "step": 5,
}


class _FakeDatasetSource:
    def __init__(self, series: pd.Series):
        self.series = series

    def load(self, reference: object) -> LoadedSeries:
        return LoadedSeries(series=self.series, warnings=[])


def _price_level_series() -> pd.Series:
    rng = np.random.default_rng(42)
    n = 500
    increments = rng.normal(0.0, 5.0, size=n)
    levels = 20000.0 + np.cumsum(increments)
    index = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.Series(levels, index=index)


def _returns_series() -> pd.Series:
    rng = np.random.default_rng(42)
    n = 500
    returns = rng.normal(0.0, 0.01, size=n)
    index = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.Series(returns, index=index)


class _SpyRunRepository:
    def __init__(self, backing):
        self._backing = backing
        self.create_run_calls: list[dict] = []

    def create_run(self, **kwargs):
        self.create_run_calls.append(kwargs)
        return self._backing.create_run(**kwargs)

    def get_run(self, *args, **kwargs):
        return self._backing.get_run(*args, **kwargs)

    def update_run_status(self, *args, **kwargs):
        return self._backing.update_run_status(*args, **kwargs)

    def list_runs(self, *args, **kwargs):
        return self._backing.list_runs(*args, **kwargs)

    def count_runs(self, *args, **kwargs):
        return self._backing.count_runs(*args, **kwargs)


def _client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    return TestClient(app), app, db_path


def _payload(dataset_reference: dict, config: dict) -> dict:
    return {
        "dataset_id": "dataset-1",
        "dataset_reference": dataset_reference,
        **config,
    }


def test_price_level_series_rejected_with_422_and_no_run_row(tmp_path, monkeypatch):
    client, app, db_path = _client(tmp_path, monkeypatch)
    from app.dependencies.repositories import get_dataset_source, get_validation_run_repository
    from app.repositories.sqlite_repository import SQLiteValidationRunRepository

    fake_source = _FakeDatasetSource(_price_level_series())
    spy_repository = _SpyRunRepository(SQLiteValidationRunRepository(db_path))

    app.dependency_overrides[get_dataset_source] = lambda: fake_source
    app.dependency_overrides[get_validation_run_repository] = lambda: spy_repository

    try:
        response = client.post(
            "/runs",
            json=_payload({"inline": {"timestamps": ["2024-01-01T00:00:00"], "values": [1.0]}}, VALID_CONFIG),
            headers={"X-Tenant-Id": "tenant-1"},
        )
    finally:
        app.dependency_overrides.pop(get_dataset_source, None)
        app.dependency_overrides.pop(get_validation_run_repository, None)

    assert response.status_code == 422, response.text
    assert spy_repository.create_run_calls == []


def test_price_level_series_never_invokes_run_validation_protocol(tmp_path, monkeypatch):
    from unittest.mock import patch

    client, app, _ = _client(tmp_path, monkeypatch)
    from app.dependencies.repositories import get_dataset_source

    fake_source = _FakeDatasetSource(_price_level_series())
    app.dependency_overrides[get_dataset_source] = lambda: fake_source

    try:
        with patch("app.routers.runs.run_validation_protocol") as mock_protocol:
            response = client.post(
                "/runs",
                json=_payload({"inline": {"timestamps": ["2024-01-01T00:00:00"], "values": [1.0]}}, VALID_CONFIG),
                headers={"X-Tenant-Id": "tenant-1"},
            )
    finally:
        app.dependency_overrides.pop(get_dataset_source, None)

    assert response.status_code == 422, response.text
    mock_protocol.assert_not_called()


def test_returns_series_still_proceeds_to_completed(tmp_path, monkeypatch):
    client, app, _ = _client(tmp_path, monkeypatch)
    from app.dependencies.repositories import get_dataset_source

    fake_source = _FakeDatasetSource(_returns_series())
    app.dependency_overrides[get_dataset_source] = lambda: fake_source

    try:
        response = client.post(
            "/runs",
            json=_payload({"inline": {"timestamps": ["2024-01-01T00:00:00"], "values": [1.0]}}, VALID_CONFIG),
            headers={"X-Tenant-Id": "tenant-1"},
        )
    finally:
        app.dependency_overrides.pop(get_dataset_source, None)

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "completed"
