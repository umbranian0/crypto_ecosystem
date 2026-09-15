"""Tests for `POST /internal/seed-platform-history` (INGEST-030).

Mirrors `tests/test_connectors_router.py`'s `app.dependency_overrides` +
`fake_repository.FakeConnectorRecordRepository` pattern -- no live Postgres.
`seed_tenant_platform_history` itself (INGEST-010) is exercised for real,
against small synthetic per-tenant CSVs written under a temp
`data/raw/_platform/` tree monkeypatched via `app.seed_platform_history.
_PLATFORM_ROOT`, so these tests prove this router calls the real write path
(no second implementation) without depending on the real, large platform
archive.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fake_repository import FakeConnectorRecordRepository

PRICE_CSV = """open_time,open,high,low,close,volume,close_time,quote_vol,trades,taker_buy_base,taker_buy_quote,ignore,symbol
2020-01-01T00:00:00Z,100,110,90,105,10,2020-01-01T00:59:59Z,1000,5,4,400,0,BTCUSDT
2020-01-01T01:00:00Z,105,115,95,110,12,2020-01-01T01:59:59Z,1200,6,5,500,0,BTCUSDT
"""

ONCHAIN_CSV = """timestamp,date,hash-rate
1577836800,2020-01-01,1.0
1577923200,2020-01-02,1.1
"""

SENTIMENT_CSV = """Date,Short Description,Accurate Sentiments
2021-11-05 04:42:00,headline one,0.5
2021-11-05 08:15:00,headline two,-0.2
"""


def _write_platform_tree(root: Path) -> None:
    (root / "price" / "binance_btcusdt_1h" / "seed").mkdir(parents=True)
    (root / "price" / "binance_btcusdt_1h" / "incremental").mkdir(parents=True)
    (root / "price" / "binance_btcusdt_1h" / "seed" / "seed.csv").write_text(PRICE_CSV)

    for chart_name, dirname in (
        ("hash-rate", "blockchain_info_hash-rate"),
        ("n-unique-addresses", "blockchain_info_n-unique-addresses"),
    ):
        (root / "onchain" / dirname / "seed").mkdir(parents=True)
        (root / "onchain" / dirname / "incremental").mkdir(parents=True)
        (root / "onchain" / dirname / "seed" / "seed.csv").write_text(
            ONCHAIN_CSV.replace("hash-rate", chart_name) if chart_name != "hash-rate" else ONCHAIN_CSV
        )

    (root / "sentiment" / "kaggle_bitcoin_sentiments_21_24" / "seed").mkdir(parents=True)
    (root / "sentiment" / "kaggle_bitcoin_sentiments_21_24" / "incremental").mkdir(parents=True)
    (root / "sentiment" / "kaggle_bitcoin_sentiments_21_24" / "seed" / "seed.csv").write_text(SENTIMENT_CSV)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("INGESTION_INTERNAL_TOKEN", "internal-secret")

    platform_root = tmp_path / "_platform"
    _write_platform_tree(platform_root)

    import app.seed_platform_history as seed_platform_history_module

    monkeypatch.setattr(seed_platform_history_module, "_PLATFORM_ROOT", platform_root)

    from app.dependencies.repositories import get_connector_record_repository
    from app.main import app

    connector_repository = FakeConnectorRecordRepository()
    app.dependency_overrides[get_connector_record_repository] = lambda: connector_repository
    try:
        yield TestClient(app), connector_repository
    finally:
        app.dependency_overrides.pop(get_connector_record_repository, None)


EXPECTED_SOURCES = {
    "binance_price_btcusdt_1h",
    "blockchain_info_hash-rate",
    "blockchain_info_n-unique-addresses",
    "kaggle_bitcoin_sentiments_21_24",
}


def test_missing_token_is_401_and_no_repository_calls(client):
    test_client, repository = client

    response = test_client.post("/internal/seed-platform-history", json={"tenant_id": "tenant-a"})

    assert response.status_code == 401
    assert repository.price == []
    assert repository.onchain == []
    assert repository.sentiment == []


def test_wrong_token_is_401_and_no_repository_calls(client):
    test_client, repository = client

    response = test_client.post(
        "/internal/seed-platform-history",
        json={"tenant_id": "tenant-a"},
        headers={"X-Internal-Token": "not-the-secret"},
    )

    assert response.status_code == 401
    assert repository.price == []
    assert repository.onchain == []
    assert repository.sentiment == []


def test_successful_call_seeds_all_four_sources_for_exactly_named_tenant(client):
    test_client, repository = client

    response = test_client.post(
        "/internal/seed-platform-history",
        json={"tenant_id": "tenant-a"},
        headers={"X-Internal-Token": "internal-secret"},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body["row_counts"].keys()) == EXPECTED_SOURCES
    assert body["row_counts"]["binance_price_btcusdt_1h"] == 2

    for record_kind in ("price", "onchain", "sentiment"):
        for tenant_id, _source, _records in getattr(repository, record_kind):
            assert tenant_id == "tenant-a"

    assert len(repository.price) == 1


def test_idempotent_second_call_produces_zero_additional_writes(client):
    test_client, repository = client
    headers = {"X-Internal-Token": "internal-secret"}

    first = test_client.post(
        "/internal/seed-platform-history", json={"tenant_id": "tenant-a"}, headers=headers
    )
    second = test_client.post(
        "/internal/seed-platform-history", json={"tenant_id": "tenant-a"}, headers=headers
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["row_counts"]["binance_price_btcusdt_1h"] == 2
    assert second.json()["row_counts"]["binance_price_btcusdt_1h"] == 0
    # Only the first call actually reached add_price_records with rows.
    assert len(repository.price) == 1


def test_repository_exception_mid_write_is_caught_and_returned_as_5xx(client, monkeypatch):
    test_client, repository = client

    def _boom(self, tenant_id, source, records):
        raise RuntimeError("connection to postgres://user:pass@host/db failed")

    monkeypatch.setattr(type(repository), "add_price_records", _boom)

    response = test_client.post(
        "/internal/seed-platform-history",
        json={"tenant_id": "tenant-a"},
        headers={"X-Internal-Token": "internal-secret"},
    )

    assert response.status_code >= 500
    body_text = response.text
    assert "postgres://" not in body_text
    assert "connection to" not in body_text
