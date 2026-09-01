"""Tests for `GET /datasets`, `GET /datasets/{source}/series`,
`GET /connectors/{source}/status` (INGEST-009, revised per ADR-0005).

Mirrors `tests/test_connectors_router.py`'s `app.dependency_overrides`
pattern: `tests/fake_repository.py`'s `FakeConnectorRecordRepository` is
wired in as `get_connector_record_repository`'s override, never a live
Postgres (this service's existing "fake the client" test convention).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from fake_repository import FakeConnectorRecordRepository


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.dependencies.repositories import get_connector_record_repository
    from app.main import app

    connector_repository = FakeConnectorRecordRepository()

    app.dependency_overrides[get_connector_record_repository] = lambda: connector_repository
    try:
        yield TestClient(app), connector_repository
    finally:
        app.dependency_overrides.pop(get_connector_record_repository, None)


def _price_rows(timestamps: list[datetime], closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_time": timestamps,
            "fetched_at": timestamps,
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1.0] * len(timestamps),
        }
    )


def _onchain_rows(timestamps: list[datetime], values: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"timestamp": timestamps, "fetched_at": timestamps, "value": values})


def test_empty_tenant_gets_empty_items_not_404(client):
    test_client, _repo = client

    response = test_client.get("/datasets", headers={"X-Tenant-Id": "tenant-a"})

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_list_datasets_one_entry_per_source(client):
    test_client, repo = client
    timestamps = [datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 2, tzinfo=timezone.utc)]
    repo.add_price_records("tenant-a", "binance_btcusdt_1h", _price_rows(timestamps, [100.0, 101.0]))

    response = test_client.get("/datasets", headers={"X-Tenant-Id": "tenant-a"})

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["source"] == "binance_btcusdt_1h"
    assert item["row_count"] == 2
    assert item["earliest_timestamp"].startswith("2026-01-01")
    assert item["latest_timestamp"].startswith("2026-01-02")


def test_series_omitted_start_and_end_returns_whole_series(client):
    test_client, repo = client
    timestamps = [
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
        datetime(2026, 1, 3, tzinfo=timezone.utc),
    ]
    repo.add_price_records("tenant-a", "binance_btcusdt_1h", _price_rows(timestamps, [100.0, 101.0, 102.0]))

    response = test_client.get("/datasets/binance_btcusdt_1h/series", headers={"X-Tenant-Id": "tenant-a"})

    assert response.status_code == 200
    body = response.json()
    assert len(body["timestamps"]) == 3
    assert body["values"] == [100.0, 101.0, 102.0]


def test_series_omitted_start_only_uses_earliest_row(client):
    test_client, repo = client
    timestamps = [
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
        datetime(2026, 1, 3, tzinfo=timezone.utc),
    ]
    repo.add_price_records("tenant-a", "binance_btcusdt_1h", _price_rows(timestamps, [100.0, 101.0, 102.0]))

    response = test_client.get(
        "/datasets/binance_btcusdt_1h/series",
        params={"end": "2026-01-02T00:00:00Z"},
        headers={"X-Tenant-Id": "tenant-a"},
    )

    assert response.status_code == 200
    assert response.json()["values"] == [100.0, 101.0]


def test_series_omitted_end_only_uses_latest_row(client):
    test_client, repo = client
    timestamps = [
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
        datetime(2026, 1, 3, tzinfo=timezone.utc),
    ]
    repo.add_price_records("tenant-a", "binance_btcusdt_1h", _price_rows(timestamps, [100.0, 101.0, 102.0]))

    response = test_client.get(
        "/datasets/binance_btcusdt_1h/series",
        params={"start": "2026-01-02T00:00:00Z"},
        headers={"X-Tenant-Id": "tenant-a"},
    )

    assert response.status_code == 200
    assert response.json()["values"] == [101.0, 102.0]


def test_series_both_start_and_end_present_slices_range(client):
    test_client, repo = client
    timestamps = [
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
        datetime(2026, 1, 3, tzinfo=timezone.utc),
    ]
    repo.add_price_records("tenant-a", "binance_btcusdt_1h", _price_rows(timestamps, [100.0, 101.0, 102.0]))

    response = test_client.get(
        "/datasets/binance_btcusdt_1h/series",
        params={"start": "2026-01-02T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
        headers={"X-Tenant-Id": "tenant-a"},
    )

    assert response.status_code == 200
    assert response.json()["values"] == [101.0]


def test_series_multi_field_selection_uses_default_and_explicit_field(client):
    test_client, repo = client
    timestamps = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    repo.add_price_records("tenant-a", "binance_btcusdt_1h", _price_rows(timestamps, [100.0]))

    default_response = test_client.get(
        "/datasets/binance_btcusdt_1h/series", headers={"X-Tenant-Id": "tenant-a"}
    )
    explicit_response = test_client.get(
        "/datasets/binance_btcusdt_1h/series",
        params={"field": "volume"},
        headers={"X-Tenant-Id": "tenant-a"},
    )

    assert default_response.json()["values"] == [100.0]  # "close" default
    assert explicit_response.json()["values"] == [1.0]  # "volume" via field=


def test_series_onchain_default_field_is_value(client):
    test_client, repo = client
    timestamps = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    repo.add_onchain_records("tenant-a", "hash_rate", _onchain_rows(timestamps, [12345.0]))

    response = test_client.get("/datasets/hash_rate/series", headers={"X-Tenant-Id": "tenant-a"})

    assert response.status_code == 200
    assert response.json()["values"] == [12345.0]


def test_nonexistent_source_returns_404(client):
    test_client, _repo = client

    response = test_client.get("/datasets/no_such_source/series", headers={"X-Tenant-Id": "tenant-a"})

    assert response.status_code == 404


def test_cross_tenant_source_returns_same_404_as_nonexistent(client):
    test_client, repo = client
    timestamps = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    repo.add_price_records("tenant-a", "binance_btcusdt_1h", _price_rows(timestamps, [100.0]))

    own_tenant_response = test_client.get(
        "/datasets/binance_btcusdt_1h/series", headers={"X-Tenant-Id": "tenant-a"}
    )
    other_tenant_response = test_client.get(
        "/datasets/binance_btcusdt_1h/series", headers={"X-Tenant-Id": "tenant-b"}
    )
    nonexistent_response = test_client.get(
        "/datasets/binance_btcusdt_1h/series", headers={"X-Tenant-Id": "tenant-b"}
    )

    assert own_tenant_response.status_code == 200
    assert other_tenant_response.status_code == 404
    assert nonexistent_response.status_code == 404
    # non-tautological: the cross-tenant response is not merely "a 404" but
    # the exact same shape as a genuinely nonexistent source's 404, with no
    # distinguishing detail that would leak existence.
    assert other_tenant_response.json() == nonexistent_response.json()


def test_connector_status_returns_latest_crawl_run(client):
    test_client, repo = client
    fetched_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
    repo.record_crawl_run("tenant-a", "binance_btcusdt_1h", None, fetched_at, 5, "completed")

    response = test_client.get("/connectors/binance_btcusdt_1h/status", headers={"X-Tenant-Id": "tenant-a"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["row_count"] == 5
    assert body["timestamp"].startswith("2026-02-01")


def test_connector_status_unknown_source_returns_404(client):
    test_client, _repo = client

    response = test_client.get("/connectors/no_such_source/status", headers={"X-Tenant-Id": "tenant-a"})

    assert response.status_code == 404


def test_connector_status_cross_tenant_returns_404(client):
    test_client, repo = client
    fetched_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
    repo.record_crawl_run("tenant-a", "binance_btcusdt_1h", None, fetched_at, 5, "completed")

    response = test_client.get("/connectors/binance_btcusdt_1h/status", headers={"X-Tenant-Id": "tenant-b"})

    assert response.status_code == 404
