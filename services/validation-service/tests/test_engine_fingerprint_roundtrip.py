"""TRUST-003: `engine_version`/`config_fingerprint` persistence + round-trip
tests.

Covers: `POST /runs` -> `GET /runs/{id}` round-trip for both a successful and
a failed run (both fields non-null either way, per the binding "populated
regardless of outcome" decision in the ticket's Analysis section), and a
pre-migration-style row (constructed without these fields set) reading back
`None`/`None` through `get_run`/`RunDetailResponse`, never a fabricated
value.

Reuses the same per-test-SQLite-file + inline-dataset fixture pattern
`tests/test_runs_endpoint.py`/`tests/test_failure_handling.py` already use.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
from fastapi.testclient import TestClient

from app.fingerprint import compute_config_fingerprint, get_engine_version

VALID_CONFIG = {
    "horizon": 1,
    "purge_gap_hours": 0,
    "train_window": 10,
    "test_window": 5,
    "step": 5,
}


def _returns_like_values(n: int, seed: int = 7) -> list[float]:
    # MR-001 fixture precedent (test_runs_endpoint.py): a genuinely
    # returns-shaped series, not a monotonic ramp, so the price-level
    # guardrail never fires here.
    return np.random.default_rng(seed).normal(0.0, 0.01, size=n).tolist()


def _inline_dataset(n: int = 40) -> dict:
    start = datetime(2024, 1, 1)
    timestamps = [(start + timedelta(hours=i)).isoformat() for i in range(n)]
    values = _returns_like_values(n)
    return {"inline": {"timestamps": timestamps, "values": values}}


def test_successful_run_round_trips_non_null_engine_version_and_fingerprint(
    tmp_path, monkeypatch
):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        **VALID_CONFIG,
    }

    response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "completed"
    run_id = response.json()["id"]

    detail = client.get("/runs/" + run_id, headers={"X-Tenant-Id": "tenant-1"})
    assert detail.status_code == 200, detail.text
    body = detail.json()

    assert body["engine_version"] == get_engine_version()
    expected_fingerprint = compute_config_fingerprint(
        {
            "train_window": VALID_CONFIG["train_window"],
            "test_window": VALID_CONFIG["test_window"],
            "step": VALID_CONFIG["step"],
        }
    )
    assert body["config_fingerprint"] == expected_fingerprint


def test_failed_run_still_round_trips_non_null_engine_version_and_fingerprint(
    tmp_path, monkeypatch
):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    # Malformed per dataset_source.py (same fixture shape as
    # test_failure_handling.py's dataset-load-failure case): dict with
    # neither 'inline' nor 'path' key -> DatasetSourceError, raised before
    # any Series is built.
    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": {"not_inline_or_path": True},
        **VALID_CONFIG,
    }

    response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "failed"
    run_id = response.json()["id"]

    detail = client.get("/runs/" + run_id, headers={"X-Tenant-Id": "tenant-1"})
    assert detail.status_code == 200, detail.text
    body = detail.json()

    assert body["status"] == "failed"
    # Binding decision (Analysis): the fingerprint describes the engine
    # version/config that were about to be used -- knowable and persisted at
    # create_run time, independent of whether the run later fails.
    assert body["engine_version"] == get_engine_version()
    expected_fingerprint = compute_config_fingerprint(
        {
            "train_window": VALID_CONFIG["train_window"],
            "test_window": VALID_CONFIG["test_window"],
            "step": VALID_CONFIG["step"],
        }
    )
    assert body["config_fingerprint"] == expected_fingerprint


def test_pre_migration_style_run_reads_back_none_never_fabricated(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app
    from app.repositories.sqlite_repository import SQLiteValidationRunRepository

    # Simulates a run row that predates migration 0012: created via
    # create_run without engine_version/config_fingerprint keyword
    # arguments, exactly what every pre-TRUST-003 call site looked like.
    run_repo = SQLiteValidationRunRepository(db_path)
    run = run_repo.create_run(
        tenant_id="tenant-1",
        dataset_id="dataset-1",
        horizon=1,
        purge_gap_hours=0,
        split_config={"train_window": 10, "test_window": 5, "step": 5},
    )
    assert run.engine_version is None
    assert run.config_fingerprint is None

    client = TestClient(app)
    detail = client.get("/runs/" + run.id, headers={"X-Tenant-Id": "tenant-1"})
    assert detail.status_code == 200, detail.text
    body = detail.json()

    assert body["engine_version"] is None
    assert body["config_fingerprint"] is None
