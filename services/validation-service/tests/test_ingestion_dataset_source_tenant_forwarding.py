"""VS-024: `POST /runs`'s tenant identity is forwarded to
`IngestionServiceDatasetSource`.

This is the ticket's own designated non-tautological test: two tenants each
have a same-named ingestion-service `source` (`binance_price_btcusdt_1h`)
backed by genuinely DIFFERENT values on the fake downstream. The assertions
below are on the actual persisted split metrics (independently computed from
each tenant's own known series via `run_validation_protocol` directly, the
same "not derived from the endpoint's own response" standard
`test_splits_endpoint.py` already uses) -- not on "a series came back" or
"no exception was raised". If `get_dataset_source()`'s tenant-forwarding wired
here were missing or wrong, either:
  - the fake ingestion-service handler below (which has no fallback branch
    for an unrecognized/missing `X-Tenant-Id`) would raise, flipping the
    run's status to `"failed"` instead of `"completed"`, or
  - the wrong tenant's values would silently come back, and the exact-value
    assertions against the independently-computed expected splits would fail.

Exercises the real `get_dataset_source()` DI provider end-to-end (not
`app.dependency_overrides` bypassing it) by monkeypatching only the
transport-level `httpx.Client` constructor the provider calls, mirroring this
module's own `httpx.MockTransport` precedent (`test_dataset_source.py`) one
layer up, at the real `POST /runs` HTTP surface.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx
import pandas as pd
from fastapi.testclient import TestClient

from naive_first_engine.protocol import (
    NAIVE0_KEY,
    NAIVE_LAST_KEY,
    ValidationConfig,
    run_validation_protocol,
)

_SOURCE = "binance_price_btcusdt_1h"
_INGESTION_SERVICE_URL = "http://ingestion-service:8003"

_N = 40
_TIMESTAMPS = [(datetime(2024, 1, 1) + timedelta(hours=i)).isoformat() for i in range(_N)]

# Deliberately NOT a shifted/rescaled copy of each other (a constant offset or
# scale factor would leave naive-baseline forecast errors identical between
# the two, defeating the point of this test), and NOT periodic (a repeating
# cycle produces a zero-variance/NaN DM statistic for some splits here, which
# `split_results.dm_statistic`'s `NOT NULL` column then rejects -- an
# unrelated pre-existing data-quality edge case, not a tenant-forwarding
# concern) -- two genuinely different, non-periodic value patterns behind the
# same source name.
_TENANT_A_VALUES = [float(i) for i in range(_N)]
_TENANT_B_VALUES = [
    63.94, 2.5, 27.5, 22.32, 73.65, 67.67, 89.22, 8.69, 42.19, 2.98,
    21.86, 50.54, 2.65, 19.88, 64.99, 54.49, 22.04, 58.93, 80.94, 0.65,
    80.58, 69.81, 34.03, 15.55, 95.72, 33.66, 9.27, 9.67, 84.75, 60.37,
    80.71, 72.97, 53.62, 97.31, 37.85, 55.2, 82.94, 61.85, 86.17, 57.74,
]

VALID_CONFIG = {
    "horizon": 1,
    "purge_gap_hours": 0,
    "train_window": 10,
    "test_window": 5,
    "step": 5,
}


def _handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == f"/datasets/{_SOURCE}/series"
    tenant_id = request.headers.get("x-tenant-id")
    if tenant_id == "tenant-a":
        values = _TENANT_A_VALUES
    elif tenant_id == "tenant-b":
        values = _TENANT_B_VALUES
    else:
        raise AssertionError(
            "unexpected/missing X-Tenant-Id header on outbound ingestion-service "
            f"call: {tenant_id!r}"
        )
    return httpx.Response(200, json={"timestamps": _TIMESTAMPS, "values": values})


def _series(values: list[float]) -> pd.Series:
    start = pd.Timestamp("2024-01-01")
    index = pd.DatetimeIndex([start + pd.Timedelta(hours=i) for i in range(len(values))])
    return pd.Series(values, index=index, dtype="float64")


def _patch_ingestion_http_client(monkeypatch) -> None:
    import app.dependencies.repositories as repositories_module

    # `httpx` is a single module object shared by this test file and
    # repositories.py's own `import httpx` -- captured here, before
    # patching, so the fake factory below constructs a REAL httpx.Client
    # (with a MockTransport) instead of recursing into itself.
    real_client_class = httpx.Client

    def fake_client_factory(*, base_url: str, timeout: float) -> httpx.Client:
        assert base_url == _INGESTION_SERVICE_URL
        return real_client_class(
            base_url=base_url, timeout=timeout, transport=httpx.MockTransport(_handler)
        )

    monkeypatch.setattr(repositories_module.httpx, "Client", fake_client_factory)
    monkeypatch.setenv("INGESTION_SERVICE_URL", _INGESTION_SERVICE_URL)


def test_post_runs_forwards_tenant_id_so_each_tenant_loads_only_its_own_series(
    tmp_path, monkeypatch
) -> None:
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    _patch_ingestion_http_client(monkeypatch)

    from app.main import app

    client = TestClient(app)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": {"source": _SOURCE},
        **VALID_CONFIG,
    }

    response_a = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-a"})
    assert response_a.status_code == 201, response_a.text
    assert response_a.json()["status"] == "completed", response_a.json()
    run_a_id = response_a.json()["id"]

    response_b = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-b"})
    assert response_b.status_code == 201, response_b.text
    assert response_b.json()["status"] == "completed", response_b.json()
    run_b_id = response_b.json()["id"]

    splits_a = client.get(f"/runs/{run_a_id}/splits", headers={"X-Tenant-Id": "tenant-a"})
    splits_b = client.get(f"/runs/{run_b_id}/splits", headers={"X-Tenant-Id": "tenant-b"})
    assert splits_a.status_code == 200, splits_a.text
    assert splits_b.status_code == 200, splits_b.text
    splits_a_body = splits_a.json()
    splits_b_body = splits_b.json()

    # Independently computed expected splits per tenant -- calling
    # run_validation_protocol directly on each tenant's own known series/
    # config, not derived from the endpoint's own response (same standard as
    # test_splits_endpoint.py's round-trip test).
    config = ValidationConfig(
        train_window=VALID_CONFIG["train_window"],
        test_window=VALID_CONFIG["test_window"],
        step=VALID_CONFIG["step"],
        purge_gap=VALID_CONFIG["purge_gap_hours"],
        horizon=VALID_CONFIG["horizon"],
    )
    expected_a = run_validation_protocol(_series(_TENANT_A_VALUES), config)
    expected_b = run_validation_protocol(_series(_TENANT_B_VALUES), config)

    assert len(splits_a_body) == len(expected_a) >= 2
    assert len(splits_b_body) == len(expected_b) >= 2

    for actual, expected in zip(splits_a_body, expected_a):
        model = expected.baseline_results[NAIVE_LAST_KEY]
        naive0 = expected.baseline_results[NAIVE0_KEY]
        assert actual["model_mae"] == model.metrics.mae
        assert actual["model_rmse"] == model.metrics.rmse
        assert actual["naive0_mae"] == naive0.metrics.mae
        assert actual["naive0_rmse"] == naive0.metrics.rmse

    for actual, expected in zip(splits_b_body, expected_b):
        model = expected.baseline_results[NAIVE_LAST_KEY]
        naive0 = expected.baseline_results[NAIVE0_KEY]
        assert actual["model_mae"] == model.metrics.mae
        assert actual["model_rmse"] == model.metrics.rmse
        assert actual["naive0_mae"] == naive0.metrics.mae
        assert actual["naive0_rmse"] == naive0.metrics.rmse

    # THE LOAD-BEARING CROSS-TENANT ASSERTION: the two tenants' persisted
    # metrics genuinely differ -- tenant A's run was computed from tenant A's
    # own values, not silently swapped for tenant B's same-named source, and
    # vice versa. A real forwarding bug would have already failed one of the
    # per-split exact-value assertions above; this is the direct,
    # by-actual-value confirmation the ticket's Test acceptance criteria ask
    # for.
    assert splits_a_body[0]["naive0_mae"] != splits_b_body[0]["naive0_mae"]
    assert splits_a_body[0]["model_mae"] != splits_b_body[0]["model_mae"]
