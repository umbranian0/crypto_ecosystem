"""VS-012: `POST /runs` failure/status handling tests.

Reuses VS-009's `test_events.py` pattern for injecting a fake `EventPublisher`
via `app.dependency_overrides` -- a fresh `InProcessLogEventPublisher` per
test, so `.published` is never shared state across tests.
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


def _client_with_test_publisher(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.dependencies.repositories import EventPublisherDep, get_event_publisher
    from app.events import InProcessLogEventPublisher
    from app.main import app

    test_publisher = InProcessLogEventPublisher()
    app.dependency_overrides[get_event_publisher] = lambda: test_publisher

    return TestClient(app), test_publisher, (lambda: app.dependency_overrides.pop(get_event_publisher, None))


def test_dataset_source_failure_persists_failed_status_and_does_not_publish(tmp_path, monkeypatch):
    client, test_publisher, cleanup = _client_with_test_publisher(tmp_path, monkeypatch)

    # Malformed per dataset_source.py: dict with neither 'inline' nor 'path'
    # key -> DatasetSourceError("reference must contain either an 'inline'
    # or a 'path' key"), raised before any Series is built.
    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": {"not_inline_or_path": True},
        **VALID_CONFIG,
    }

    try:
        response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    finally:
        cleanup()

    # Not a bare 500: the request itself was handled correctly, only the
    # run failed.
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "failed"
    run_id = body["id"]

    detail = client.get("/runs/" + run_id, headers={"X-Tenant-Id": "tenant-1"})
    assert detail.status_code == 200, detail.text
    detail_body = detail.json()
    assert detail_body["status"] == "failed"
    assert detail_body["failure_reason"]
    assert "inline" in detail_body["failure_reason"] or "path" in detail_body["failure_reason"]

    # THE LOAD-BEARING ASSERTION: run.completed must never have been
    # recorded for this failed run -- a genuine check against the fake
    # publisher's recorded-events list, not an absence-of-error inference.
    assert test_publisher.published == []


def test_dataset_source_failure_second_variant_non_numeric_value_also_fails_cleanly(tmp_path, monkeypatch):
    # A second, distinct DatasetSource failure mode (non-numeric value in an
    # otherwise well-shaped inline payload) rather than a second
    # run_validation_protocol-internal failure: constructing a config that
    # passes VS-006's pydantic validation (horizon/purge_gap_hours/
    # train_window/test_window/step are all just positive ints -- there is
    # no combination of them that survives generate_splits and still makes
    # run_validation_protocol raise) but still causes run_validation_protocol
    # itself to raise would require reasoning about naive_first_engine's
    # internals, which this ticket's Design section says not to duplicate
    # knowledge of. The DatasetSourceError path is exercised twice instead,
    # covering two different malformed-reference shapes.
    client, test_publisher, cleanup = _client_with_test_publisher(tmp_path, monkeypatch)

    dataset = _inline_dataset()
    dataset["inline"]["values"][3] = "not-a-number"

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": dataset,
        **VALID_CONFIG,
    }

    try:
        response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    finally:
        cleanup()

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "failed"

    detail = client.get("/runs/" + body["id"], headers={"X-Tenant-Id": "tenant-1"})
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "failed"
    assert detail.json()["failure_reason"]

    assert test_publisher.published == []
