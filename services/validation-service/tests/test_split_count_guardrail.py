"""RSS-004: server-side split-count guardrail on `POST /runs`.

Every test here overrides `get_dataset_source` with a fake `DatasetSource`
that returns a cheaply-constructed `pandas.Series` (a `pandas.date_range` of
the desired length -- never real data), so a request that would otherwise
compute tens of thousands of splits, or take real wall-clock time to build a
79,180-row inline JSON payload, stays fast. The guardrail only cares about
`series.index`, so this is a faithful, non-tautological substitute for a real
dataset load, matching this module's existing "fake at the DI seam" testing
convention (see `test_runs_endpoint.py`'s `_RepositoryFakeThatFailsIfCalled`).

Expected split counts are always computed independently via
`naive_first_engine.splitting.generate_splits` (or, for the incident case,
asserted to be whatever that real function returns for that real input) --
never a hand-derived/hardcoded number trusted on faith, per this module's
existing convention (`test_runs_endpoint.py`'s own module docstring) and
`libs/naive_first_engine`'s split-count closed form used as a cross-check.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from naive_first_engine.splitting import generate_splits

VALID_CONFIG = {
    "horizon": 1,
    "purge_gap_hours": 0,
    "train_window": 10,
    "test_window": 5,
    "step": 5,
}


class _FakeDatasetSource:
    """Ignores `reference` entirely and always returns a pre-built series of
    `row_count` hourly rows -- the guardrail only ever reads `series.index`,
    so this is a faithful substitute regardless of which `dataset_reference`
    mode (`inline`/`path`/`source`) the request body claims to use.
    """

    def __init__(self, row_count: int):
        index = pd.date_range("2020-01-01", periods=row_count, freq="h")
        self.series = pd.Series(range(row_count), index=index, dtype=float)

    def load(self, reference: object) -> pd.Series:
        return self.series


class _SpyRunRepository:
    """Records every `create_run` call; every other method delegates to a
    real backing repository so the non-guardrail-rejection paths (used by
    the "still succeeds under the cap" boundary test) keep working normally.
    """

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


@pytest.mark.parametrize(
    "dataset_reference",
    [
        {"inline": {"timestamps": ["2024-01-01T00:00:00"], "values": [1.0]}},
        {"path": "does-not-matter.csv"},
        {"source": "does-not-matter"},
    ],
    ids=["inline", "path", "source"],
)
def test_incident_input_rejected_with_computed_split_count(tmp_path, monkeypatch, dataset_reference):
    client, app, _ = _client(tmp_path, monkeypatch)
    from app.dependencies.repositories import get_dataset_source

    fake_source = _FakeDatasetSource(row_count=79180)
    app.dependency_overrides[get_dataset_source] = lambda: fake_source

    config = {
        "horizon": 1,
        "purge_gap_hours": 24,
        "train_window": 360,
        "test_window": 1540,
        "step": 2,
    }

    expected_count = len(
        generate_splits(
            fake_source.series.index,
            config["train_window"],
            config["test_window"],
            config["step"],
            purge_gap=config["purge_gap_hours"],
        )
    )
    # Sanity: the incident is only interesting if it actually exceeds the cap.
    assert expected_count > 500

    try:
        response = client.post(
            "/runs",
            json=_payload(dataset_reference, config),
            headers={"X-Tenant-Id": "tenant-1"},
        )
    finally:
        app.dependency_overrides.pop(get_dataset_source, None)

    assert response.status_code == 422, response.text
    body = response.json()
    assert str(expected_count) in body["detail"]


def test_exactly_cap_splits_is_accepted(tmp_path, monkeypatch):
    client, app, _ = _client(tmp_path, monkeypatch)
    from app.dependencies.repositories import get_dataset_source

    # train_window=10, test_window=5, step=5, purge_gap=0 -> row_count=2510
    # yields exactly 500 splits (verified against generate_splits directly
    # below, not hand-derived alone) -- larger windows than the
    # train_window=1/test_window=1 combination used elsewhere in this file,
    # because that degenerate combination produces a NaN MASE (a single-point
    # training window has no meaningful naive-in-sample-error denominator),
    # which fails this table's NOT NULL constraint on `model_mase` downstream
    # of the guardrail entirely -- unrelated to what this test is proving.
    fake_source = _FakeDatasetSource(row_count=2510)
    expected_count = len(
        generate_splits(
            fake_source.series.index,
            VALID_CONFIG["train_window"],
            VALID_CONFIG["test_window"],
            VALID_CONFIG["step"],
            purge_gap=VALID_CONFIG["purge_gap_hours"],
        )
    )
    assert expected_count == 500

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


def test_cap_plus_one_splits_is_rejected(tmp_path, monkeypatch):
    client, app, _ = _client(tmp_path, monkeypatch)
    from app.dependencies.repositories import get_dataset_source

    # row_count=2515 -> 501 splits, exactly cap + 1 (same window/step/purge
    # choice as the exactly-500 boundary test above, for the same MASE-NaN
    # reason documented there).
    fake_source = _FakeDatasetSource(row_count=2515)
    expected_count = len(
        generate_splits(
            fake_source.series.index,
            VALID_CONFIG["train_window"],
            VALID_CONFIG["test_window"],
            VALID_CONFIG["step"],
            purge_gap=VALID_CONFIG["purge_gap_hours"],
        )
    )
    assert expected_count == 501

    app.dependency_overrides[get_dataset_source] = lambda: fake_source

    try:
        response = client.post(
            "/runs",
            json=_payload({"inline": {"timestamps": ["2024-01-01T00:00:00"], "values": [1.0]}}, VALID_CONFIG),
            headers={"X-Tenant-Id": "tenant-1"},
        )
    finally:
        app.dependency_overrides.pop(get_dataset_source, None)

    assert response.status_code == 422, response.text
    body = response.json()
    assert "501" in body["detail"]
    assert "500" in body["detail"]


def test_rejected_request_never_calls_create_run(tmp_path, monkeypatch):
    client, app, db_path = _client(tmp_path, monkeypatch)
    from app.dependencies.repositories import get_dataset_source, get_validation_run_repository
    from app.repositories.sqlite_repository import SQLiteValidationRunRepository

    fake_source = _FakeDatasetSource(row_count=2515)  # 501 splits (VALID_CONFIG windows), over the cap
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


@pytest.mark.parametrize(
    "dataset_reference",
    [
        {"inline": {"timestamps": ["2024-01-01T00:00:00"], "values": [1.0]}},
        {"path": "does-not-matter.csv"},
        {"source": "does-not-matter"},
    ],
    ids=["inline", "path", "source"],
)
def test_rejected_request_never_invokes_run_validation_protocol(tmp_path, monkeypatch, dataset_reference):
    from unittest.mock import patch

    client, app, _ = _client(tmp_path, monkeypatch)
    from app.dependencies.repositories import get_dataset_source

    fake_source = _FakeDatasetSource(row_count=2515)  # 501 splits (VALID_CONFIG windows), over the cap
    app.dependency_overrides[get_dataset_source] = lambda: fake_source

    try:
        with patch("app.routers.runs.run_validation_protocol") as mock_protocol:
            response = client.post(
                "/runs",
                json=_payload(dataset_reference, VALID_CONFIG),
                headers={"X-Tenant-Id": "tenant-1"},
            )
    finally:
        app.dependency_overrides.pop(get_dataset_source, None)

    assert response.status_code == 422, response.text
    mock_protocol.assert_not_called()


def test_dataset_load_failure_still_produces_failed_run_and_201(tmp_path, monkeypatch):
    """VS-012's pre-existing contract must survive this ticket's restructuring
    of `create_run`'s control flow: a dataset-load failure still results in a
    `"failed"` run row and a `201`, not a `422` or `500` -- the RSS-004
    guardrail only ever runs after a *successful* load.
    """
    client, app, _ = _client(tmp_path, monkeypatch)
    from app.dependencies.repositories import get_dataset_source

    class _AlwaysFailsDatasetSource:
        def load(self, reference: object) -> pd.Series:
            raise ValueError("boom: dataset failed to load")

    app.dependency_overrides[get_dataset_source] = lambda: _AlwaysFailsDatasetSource()

    try:
        response = client.post(
            "/runs",
            json=_payload({"inline": {"timestamps": ["2024-01-01T00:00:00"], "values": [1.0]}}, VALID_CONFIG),
            headers={"X-Tenant-Id": "tenant-1"},
        )
    finally:
        app.dependency_overrides.pop(get_dataset_source, None)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "failed"
