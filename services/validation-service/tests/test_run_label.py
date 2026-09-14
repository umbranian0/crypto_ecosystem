"""UAT-008: `RunRequest.label` persistence/return tests -- create with/without
label, assert persisted+returned correctly on `GET /runs`/`GET /runs/{id}`,
and that a label over 200 chars is rejected with 422 (Pydantic's own
`max_length` constraint, enforced before any downstream call). Mirrors
`test_runs_endpoint.py`'s per-test-SQLite-file setup rather than duplicating
it in a new module-level fixture.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient


def _returns_like_values(n: int, seed: int = 7) -> list[float]:
    return np.random.default_rng(seed).normal(0.0, 0.01, size=n).tolist()


def _inline_dataset(n: int = 40) -> dict:
    start = datetime(2024, 1, 1)
    timestamps = [(start + timedelta(hours=i)).isoformat() for i in range(n)]
    values = _returns_like_values(n)
    return {"inline": {"timestamps": timestamps, "values": values}}


VALID_CONFIG = {
    "horizon": 1,
    "purge_gap_hours": 0,
    "train_window": 10,
    "test_window": 5,
    "step": 5,
}


def test_run_with_label_persists_and_returns_it(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        "label": "weekly audit",
        **VALID_CONFIG,
    }
    response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]

    detail = client.get(f"/runs/{run_id}", headers={"X-Tenant-Id": "tenant-1"})
    assert detail.status_code == 200
    assert detail.json()["label"] == "weekly audit"

    listing = client.get("/runs", headers={"X-Tenant-Id": "tenant-1"})
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["label"] == "weekly audit"


def test_run_without_label_persists_and_returns_none(tmp_path, monkeypatch):
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
    run_id = response.json()["id"]

    detail = client.get(f"/runs/{run_id}", headers={"X-Tenant-Id": "tenant-1"})
    assert detail.status_code == 200
    assert detail.json()["label"] is None

    listing = client.get("/runs", headers={"X-Tenant-Id": "tenant-1"})
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["label"] is None


def test_run_with_label_over_200_chars_rejected_with_422(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        "label": "x" * 201,
        **VALID_CONFIG,
    }
    response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert response.status_code == 422, response.text
