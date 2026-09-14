"""UAT-006: `POST /runs`'s persisted `failure_reason` must never be a bare,
non-numeric-looking string -- most concretely, never the literal `"0"`.

`_fail_run` (`app.routers.runs`) is the single failure-persistence path all
three `except Exception as exc` blocks in `create_run` now share (extract-
on-second-duplication, implementation-plan.md section 9). Two scenarios are
covered here:

1. The exact repro shape the live incident matches: an exception whose
   `str()` collapses to a bare digit (`str(KeyError(0)) == "0"`, since
   `BaseException.__str__` for a single-arg exception just returns
   `str(args[0])`). Triggered deterministically via a fake `DatasetSource`
   that raises `KeyError(0)` on `load()` -- the same shape this ticket's
   Analysis section identifies as the only built-in Python exception that
   genuinely stringifies to `"0"`.
2. A second, pre-existing deterministic failure path (DH-003's
   conflicting-timestamp hard-block, already exercised by
   `test_failure_handling.py`) re-asserted here specifically for its
   `failure_reason` shape, to prove the new `_fail_run` wrapping did not
   regress an already-descriptive message into something worse.
"""

from __future__ import annotations

from datetime import datetime, timedelta

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


class _KeyErrorZeroDatasetSource:
    """Deterministically raises `KeyError(0)` on `load()` -- the exact
    exception shape whose `str()` is the bare literal `"0"` this ticket was
    filed against, independent of whichever real code path first surfaced
    it live.
    """

    def load(self, reference: object) -> LoadedSeries:
        raise KeyError(0)


def _client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    return TestClient(app), app


def _inline_dataset(n: int = 40) -> dict:
    start = datetime(2024, 1, 1)
    timestamps = [(start + timedelta(hours=i)).isoformat() for i in range(n)]
    values = [float(i) for i in range(n)]
    return {"inline": {"timestamps": timestamps, "values": values}}


def _is_numeric_string(value: str) -> bool:
    return value.strip().lstrip("-").isdigit()


def test_keyerror_zero_dataset_load_failure_produces_non_numeric_failure_reason(
    tmp_path, monkeypatch
):
    client, app = _client(tmp_path, monkeypatch)
    from app.dependencies.repositories import get_dataset_source

    app.dependency_overrides[get_dataset_source] = lambda: _KeyErrorZeroDatasetSource()

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": {"inline": {"timestamps": [], "values": []}},
        **VALID_CONFIG,
    }

    try:
        response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    finally:
        app.dependency_overrides.pop(get_dataset_source, None)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "failed"
    run_id = body["id"]

    detail = client.get("/runs/" + run_id, headers={"X-Tenant-Id": "tenant-1"})
    assert detail.status_code == 200, detail.text
    failure_reason = detail.json()["failure_reason"]

    # THE LOAD-BEARING ASSERTION: never the bare literal "0" (or any other
    # digits-only string) -- this is the exact repro this ticket was filed
    # against.
    assert failure_reason != "0"
    assert failure_reason
    assert not _is_numeric_string(failure_reason)
    # Still descriptive: names the run id and the exception type, per
    # _fail_run's fallback message shape.
    assert run_id in failure_reason
    assert "KeyError" in failure_reason


def test_dh003_conflicting_timestamp_failure_reason_stays_descriptive(tmp_path, monkeypatch):
    """Second, distinct, pre-existing deterministic failure path (DH-003's
    conflicting-value hard-block) -- confirms `_fail_run`'s new wrapping
    still surfaces a genuinely descriptive `str(exc)` (prefixed, not
    replaced) rather than collapsing every failure into the same generic
    fallback message.
    """
    client, app = _client(tmp_path, monkeypatch)

    dataset = _inline_dataset()
    dataset["inline"]["timestamps"].append(dataset["inline"]["timestamps"][3])
    dataset["inline"]["values"].append(dataset["inline"]["values"][3] + 999.0)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": dataset,
        **VALID_CONFIG,
    }

    response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "failed"

    detail = client.get("/runs/" + body["id"], headers={"X-Tenant-Id": "tenant-1"})
    assert detail.status_code == 200, detail.text
    failure_reason = detail.json()["failure_reason"]

    assert failure_reason
    assert not _is_numeric_string(failure_reason)
    assert "conflicting values" in failure_reason
    assert "3.0" in failure_reason
    assert "1002.0" in failure_reason
    # Wrapped with fixed context, not a bare passthrough.
    assert failure_reason.startswith("Validation run failed:")
