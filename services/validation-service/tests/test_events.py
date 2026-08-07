"""VS-009: `run.completed` event publishing tests.

Overrides `EventPublisherDep` with a fresh `InProcessLogEventPublisher` per
test (via `app.dependency_overrides`) rather than relying on the module-level
singleton, so tests never share published state across runs.
"""

from __future__ import annotations

from datetime import datetime, timedelta

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
    values = [float(i) for i in range(n)]
    return {"inline": {"timestamps": timestamps, "values": values}}


def test_successful_run_publishes_run_completed_exactly_once(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.dependencies.repositories import EventPublisherDep, get_event_publisher
    from app.events import InProcessLogEventPublisher
    from app.main import app

    test_publisher = InProcessLogEventPublisher()
    app.dependency_overrides[get_event_publisher] = lambda: test_publisher

    client = TestClient(app)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        **VALID_CONFIG,
    }

    try:
        response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    finally:
        app.dependency_overrides.pop(get_event_publisher, None)

    assert response.status_code == 201, response.text
    run_id = response.json()["id"]

    # Exactly one, not "at least one" -- guards against accidental
    # double-publish (e.g. from a loop over splits).
    assert len(test_publisher.published) == 1

    entry = test_publisher.published[0]
    assert entry["event_name"] == "run.completed"
    payload_out = entry["payload"]
    assert payload_out["run_id"] == run_id
    assert payload_out["tenant_id"] == "tenant-1"
    assert payload_out["status"] == "completed"
    assert payload_out["completed_at"] is not None
