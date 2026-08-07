"""VS-006: `POST /runs` endpoint tests. VS-007 extends this file with
`GET /runs/{id}` tests (reuses the same `TestClient`/per-test-SQLite-file
setup rather than duplicating it in a new file).

Each test gets its own SQLite file (via `VALIDATION_SERVICE_DB_PATH`,
monkeypatched before `app.main` is imported/exercised) so tests never share
persisted state.

Expected split count is computed independently via
`naive_first_engine.splitting.generate_splits` with the same params used in
the request, not read back from the endpoint's own response -- a tautological
"trust the endpoint's own count" assertion would not actually verify
`run_validation_protocol` was invoked correctly (Test acceptance criteria).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from naive_first_engine.splitting import generate_splits


def _inline_dataset(n: int = 40) -> dict:
    start = datetime(2024, 1, 1)
    timestamps = [(start + timedelta(hours=i)).isoformat() for i in range(n)]
    values = [float(i) for i in range(n)]
    return {"inline": {"timestamps": timestamps, "values": values}}


def _index(n: int = 40) -> pd.DatetimeIndex:
    start = pd.Timestamp("2024-01-01")
    return pd.DatetimeIndex([start + pd.Timedelta(hours=i) for i in range(n)])


VALID_CONFIG = {
    "horizon": 1,
    "purge_gap_hours": 0,
    "train_window": 10,
    "test_window": 5,
    "step": 5,
}


def test_valid_run_persists_run_and_expected_split_count(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app
    from app.repositories.sqlite_repository import (
        SQLiteSplitResultRepository,
        SQLiteValidationRunRepository,
    )

    client = TestClient(app)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        **VALID_CONFIG,
    }

    response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "completed"
    run_id = body["id"]

    expected_splits = generate_splits(
        _index(),
        VALID_CONFIG["train_window"],
        VALID_CONFIG["test_window"],
        VALID_CONFIG["step"],
        purge_gap=VALID_CONFIG["purge_gap_hours"],
    )
    assert len(expected_splits) > 0  # sanity: the config must actually produce splits

    run_repo = SQLiteValidationRunRepository(db_path)
    split_repo = SQLiteSplitResultRepository(db_path)

    run_record = run_repo.get_run("tenant-1", run_id)
    assert run_record is not None
    assert run_record.status == "completed"

    persisted_splits = split_repo.get_splits("tenant-1", run_id)
    assert len(persisted_splits) == len(expected_splits)


def test_invalid_config_returns_422_and_persists_nothing(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app
    from app.models import Base, Run, SplitResult
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    client = TestClient(app)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        **{**VALID_CONFIG, "horizon": 0},  # invalid: horizon must be >= 1
    }

    response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})

    assert response.status_code == 422

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert session.execute(select(Run)).scalars().all() == []
        assert session.execute(select(SplitResult)).scalars().all() == []


def test_invalid_config_never_invokes_run_validation_protocol(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        **{**VALID_CONFIG, "purge_gap_hours": -1},  # invalid: purge gap must be >= 0
    }

    with patch("app.routers.runs.run_validation_protocol") as mock_protocol:
        response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})

    assert response.status_code == 422
    mock_protocol.assert_not_called()


def test_get_run_returns_matching_fields_for_created_run(tmp_path, monkeypatch):
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

    get_response = client.get(f"/runs/{run_id}", headers={"X-Tenant-Id": "tenant-1"})

    assert get_response.status_code == 200, get_response.text
    body = get_response.json()
    assert body["id"] == run_id
    assert body["tenant_id"] == "tenant-1"
    assert body["dataset_id"] == "dataset-1"
    assert body["horizon"] == VALID_CONFIG["horizon"]
    assert body["purge_gap_hours"] == VALID_CONFIG["purge_gap_hours"]
    assert body["split_config"] == {
        "train_window": VALID_CONFIG["train_window"],
        "test_window": VALID_CONFIG["test_window"],
        "step": VALID_CONFIG["step"],
    }
    assert body["status"] == "completed"
    assert body["created_at"] is not None
    assert body["completed_at"] is not None


def test_get_run_cross_tenant_returns_404_with_no_leaked_data(tmp_path, monkeypatch):
    """Load-bearing tenant-isolation test (VS-007 AC2). A run created for
    `tenant-a` must be unreachable, and its data unobservable, via a GET
    scoped to `tenant-b` -- a distinct tenant id, not a typo/variant of the
    same one.
    """
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    payload = {
        "dataset_id": "dataset-secret",
        "dataset_reference": _inline_dataset(),
        **VALID_CONFIG,
    }

    create_response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-a"})
    assert create_response.status_code == 201, create_response.text
    run_id = create_response.json()["id"]

    get_response = client.get(f"/runs/{run_id}", headers={"X-Tenant-Id": "tenant-b"})

    assert get_response.status_code == 404
    body_text = get_response.text
    # Not just a status-code check: assert none of tenant-a's run data is
    # observable anywhere in the response body, including the run/dataset
    # ids that would themselves confirm the run exists.
    assert run_id not in body_text
    assert "tenant-a" not in body_text
    assert "dataset-secret" not in body_text
    assert "completed" not in body_text
    body = get_response.json()
    assert set(body.keys()) == {"detail"}


def test_get_run_nonexistent_id_returns_404(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    response = client.get("/runs/does-not-exist", headers={"X-Tenant-Id": "tenant-1"})

    assert response.status_code == 404
    assert response.status_code != 500


class _RepositoryFakeThatFailsIfCalled:
    """Stands in for `ValidationRunRepository`: any method call is a test
    failure, proving `Depends(get_tenant_context)` rejects the request
    (VS-010 AC3) before route-handler business logic ever reaches the
    repository -- not merely that the HTTP response happens to be 401.
    """

    def create_run(self, *args, **kwargs):
        raise AssertionError("repository.create_run must not be reached when tenant context resolution fails")

    def get_run(self, *args, **kwargs):
        raise AssertionError("repository.get_run must not be reached when tenant context resolution fails")

    def update_run_status(self, *args, **kwargs):
        raise AssertionError("repository.update_run_status must not be reached when tenant context resolution fails")


def _client_with_failing_repository(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.dependencies.repositories import get_validation_run_repository
    from app.main import app

    app.dependency_overrides[get_validation_run_repository] = lambda: _RepositoryFakeThatFailsIfCalled()

    return TestClient(app), (lambda: app.dependency_overrides.pop(get_validation_run_repository, None))


def test_post_runs_missing_tenant_header_rejected_before_repository_code(tmp_path, monkeypatch):
    client, cleanup = _client_with_failing_repository(tmp_path, monkeypatch)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        **VALID_CONFIG,
    }

    try:
        response = client.post("/runs", json=payload)  # no X-Tenant-Id header
    finally:
        cleanup()

    assert response.status_code == 401


def test_post_runs_empty_tenant_header_rejected_before_repository_code(tmp_path, monkeypatch):
    client, cleanup = _client_with_failing_repository(tmp_path, monkeypatch)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        **VALID_CONFIG,
    }

    try:
        response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "   "})
    finally:
        cleanup()

    assert response.status_code == 401


def test_get_run_missing_tenant_header_rejected_before_repository_code(tmp_path, monkeypatch):
    client, cleanup = _client_with_failing_repository(tmp_path, monkeypatch)

    try:
        response = client.get("/runs/some-run-id")  # no X-Tenant-Id header
    finally:
        cleanup()

    assert response.status_code == 401
