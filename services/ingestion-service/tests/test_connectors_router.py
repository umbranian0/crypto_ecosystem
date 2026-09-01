"""Tests for `POST /connectors/{source}/run` (INGEST-008).

Mirrors `tests/test_health.py`'s `app.dependency_overrides` pattern: fakes
from `tests/fake_repository.py` are wired in via `app.dependency_overrides`,
not real Postgres. `RedditSentimentConnector.fetch` is monkeypatched at the
class level (not through `_client`/`praw`) so these tests never touch the
network, mirroring `tests/test_reddit_sentiment.py`'s own "replace the
lazily-built collaborator" approach applied one level up (the whole
`fetch()`), since `run_connector` calls `fetch()` directly, not `_client()`.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from connectors.base import FetchResult
from connectors.binance_price import BinancePriceConnector
from connectors.reddit_sentiment import RedditSentimentConnector
from fake_repository import FakeConnectorRecordRepository, FakeCredentialRepository


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.dependencies.repositories import get_connector_record_repository, get_credential_repository
    from app.main import app

    connector_repository = FakeConnectorRecordRepository()
    credential_repository = FakeCredentialRepository()

    app.dependency_overrides[get_connector_record_repository] = lambda: connector_repository
    app.dependency_overrides[get_credential_repository] = lambda: credential_repository
    try:
        yield TestClient(app), connector_repository, credential_repository
    finally:
        app.dependency_overrides.pop(get_connector_record_repository, None)
        app.dependency_overrides.pop(get_credential_repository, None)


def _fake_binance_fetch(monkeypatch, rows: int = 1):
    fetched_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    records = pd.DataFrame({"symbol": ["BTCUSDT"] * rows, "open": [1.0] * rows})

    def _fetch(self, since):
        return FetchResult(source=self.name, fetched_at=fetched_at, records=records)

    monkeypatch.setattr(BinancePriceConnector, "fetch", _fetch)
    return fetched_at


def test_unknown_source_returns_404(client):
    test_client, _connector_repo, _credential_repo = client

    response = test_client.post("/connectors/not_a_real_source/run", headers={"X-Tenant-Id": "tenant-a"})

    assert response.status_code == 404


def test_successful_trigger_writes_rows_via_repository(client, monkeypatch):
    test_client, connector_repo, _credential_repo = client
    fetched_at = _fake_binance_fetch(monkeypatch, rows=2)

    response = test_client.post(
        "/connectors/binance_price_btcusdt_1h/run", headers={"X-Tenant-Id": "tenant-a"}
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "completed"
    assert body["row_count"] == 2
    assert body["fetched_at"] == fetched_at.isoformat().replace("+00:00", "Z")

    assert len(connector_repo.price) == 1
    tenant_id, source, records = connector_repo.price[0]
    assert tenant_id == "tenant-a"
    assert source == "binance_price_btcusdt_1h"
    assert len(records) == 2

    assert len(connector_repo.crawl_runs) == 1
    assert connector_repo.crawl_runs[0][0] == "tenant-a"
    assert connector_repo.crawl_runs[0][4] == 2
    assert connector_repo.crawl_runs[0][5] == "completed"


def test_cross_tenant_isolation(client, monkeypatch):
    test_client, connector_repo, _credential_repo = client
    _fake_binance_fetch(monkeypatch, rows=1)

    test_client.post("/connectors/binance_price_btcusdt_1h/run", headers={"X-Tenant-Id": "tenant-a"})
    test_client.post("/connectors/binance_price_btcusdt_1h/run", headers={"X-Tenant-Id": "tenant-b"})

    assert len(connector_repo.price) == 2
    tenants_written = {tenant_id for (tenant_id, _source, _records) in connector_repo.price}
    assert tenants_written == {"tenant-a", "tenant-b"}
    assert len(connector_repo.crawl_runs) == 2
    crawl_tenants = {run[0] for run in connector_repo.crawl_runs}
    assert crawl_tenants == {"tenant-a", "tenant-b"}


def test_missing_reddit_credentials_returns_422_not_500(client):
    test_client, connector_repo, _credential_repo = client

    response = test_client.post(
        "/connectors/reddit_vader_sentiment/run", headers={"X-Tenant-Id": "tenant-a"}
    )

    assert response.status_code == 422
    assert "reddit_vader_sentiment" in response.json()["detail"]
    assert connector_repo.crawl_runs == []


def test_reddit_credentials_isolated_across_tenants(client, monkeypatch):
    from app import credential_crypto as cc

    monkeypatch.setenv("INGESTION_CREDENTIAL_ENCRYPTION_KEY", cc.generate_key().decode("utf-8"))
    test_client, connector_repo, credential_repository = client
    credential_repository.set_credentials(
        "tenant-a", "reddit_vader_sentiment", client_id="cid", client_secret="secret"
    )
    fetched_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    records = pd.DataFrame(
        {
            "created_utc": [fetched_at],
            "post_id": ["p1"],
            "reddit_sid_pos": [0.1],
            "reddit_sid_neg": [0.1],
            "reddit_sid_neu": [0.8],
            "reddit_sid_com": [0.0],
        }
    )

    def _fetch(self, since):
        return FetchResult(source=self.name, fetched_at=fetched_at, records=records)

    monkeypatch.setattr(RedditSentimentConnector, "fetch", _fetch)

    response_a = test_client.post(
        "/connectors/reddit_vader_sentiment/run", headers={"X-Tenant-Id": "tenant-a"}
    )
    response_b = test_client.post(
        "/connectors/reddit_vader_sentiment/run", headers={"X-Tenant-Id": "tenant-b"}
    )

    assert response_a.status_code == 202
    assert response_b.status_code == 422
    assert len(connector_repo.sentiment) == 1
    tenant_id, _source, _records = connector_repo.sentiment[0]
    assert tenant_id == "tenant-a"


def test_onchain_source_writes_via_repository(client, monkeypatch):
    from connectors.blockchain_onchain import BlockchainInfoConnector

    test_client, connector_repo, _credential_repo = client
    fetched_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    records = pd.DataFrame(
        {"timestamp_unix": [1], "date": [fetched_at], "hash-rate": [123.4]}
    )

    def _fetch(self, since):
        return FetchResult(source=self.name, fetched_at=fetched_at, records=records)

    monkeypatch.setattr(BlockchainInfoConnector, "fetch", _fetch)

    response = test_client.post(
        "/connectors/blockchain_info_hash-rate/run", headers={"X-Tenant-Id": "tenant-a"}
    )

    assert response.status_code == 202
    assert len(connector_repo.onchain) == 1
    tenant_id, source, _records = connector_repo.onchain[0]
    assert tenant_id == "tenant-a"
    assert source == "blockchain_info_hash-rate"


def test_empty_fetch_still_records_crawl_run(client, monkeypatch):
    fetched_at = datetime(2026, 3, 1, tzinfo=timezone.utc)

    def _fetch(self, since):
        return FetchResult(source=self.name, fetched_at=fetched_at, records=pd.DataFrame())

    monkeypatch.setattr(BinancePriceConnector, "fetch", _fetch)
    test_client, connector_repo, _credential_repo = client

    response = test_client.post(
        "/connectors/binance_price_btcusdt_1h/run", headers={"X-Tenant-Id": "tenant-a"}
    )

    assert response.status_code == 202
    body = response.json()
    assert body["row_count"] == 0
    assert body["status"] == "completed"
    assert connector_repo.price == []
    assert len(connector_repo.crawl_runs) == 1


def test_missing_tenant_header_returns_401(client):
    test_client, _connector_repo, _credential_repo = client

    response = test_client.post("/connectors/binance_price_btcusdt_1h/run")

    assert response.status_code == 401


def _fake_binance_fetch_capturing(monkeypatch, rows: int = 1):
    """Like `_fake_binance_fetch`, but also captures every `since` `fetch`
    was actually called with, for asserting the resolved watermark
    (INGEST-013)."""
    fetched_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    records = pd.DataFrame({"symbol": ["BTCUSDT"] * rows, "open": [1.0] * rows})
    seen_since: list[datetime] = []

    def _fetch(self, since):
        seen_since.append(since)
        return FetchResult(source=self.name, fetched_at=fetched_at, records=records)

    monkeypatch.setattr(BinancePriceConnector, "fetch", _fetch)
    return fetched_at, seen_since


def test_first_crawl_honors_since_override(client, monkeypatch):
    test_client, _connector_repo, _credential_repo = client
    _fetched_at, seen_since = _fake_binance_fetch_capturing(monkeypatch)

    response = test_client.post(
        "/connectors/binance_price_btcusdt_1h/run",
        params={"since": "2020-06-01"},
        headers={"X-Tenant-Id": "tenant-a"},
    )

    assert response.status_code == 202
    assert seen_since == [datetime(2020, 6, 1, tzinfo=timezone.utc)]


def test_first_crawl_no_override_uses_new_binance_default(client, monkeypatch):
    test_client, _connector_repo, _credential_repo = client
    _fetched_at, seen_since = _fake_binance_fetch_capturing(monkeypatch)

    response = test_client.post(
        "/connectors/binance_price_btcusdt_1h/run", headers={"X-Tenant-Id": "tenant-a"}
    )

    assert response.status_code == 202
    assert seen_since == [datetime(2017, 8, 17, tzinfo=timezone.utc)]


def test_first_crawl_no_override_uses_new_onchain_default(client, monkeypatch):
    from connectors.blockchain_onchain import BlockchainInfoConnector

    test_client, _connector_repo, _credential_repo = client
    fetched_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    seen_since: list[datetime] = []

    def _fetch(self, since):
        seen_since.append(since)
        return FetchResult(source=self.name, fetched_at=fetched_at, records=pd.DataFrame())

    monkeypatch.setattr(BlockchainInfoConnector, "fetch", _fetch)

    response = test_client.post(
        "/connectors/blockchain_info_hash-rate/run", headers={"X-Tenant-Id": "tenant-a"}
    )

    assert response.status_code == 202
    assert seen_since == [datetime(2009, 1, 3, tzinfo=timezone.utc)]


def test_non_first_crawl_ignores_since_override(client, monkeypatch):
    test_client, _connector_repo, _credential_repo = client
    fetched_at, seen_since = _fake_binance_fetch_capturing(monkeypatch)

    first = test_client.post(
        "/connectors/binance_price_btcusdt_1h/run", headers={"X-Tenant-Id": "tenant-a"}
    )
    assert first.status_code == 202

    second = test_client.post(
        "/connectors/binance_price_btcusdt_1h/run",
        params={"since": "2021-01-01"},
        headers={"X-Tenant-Id": "tenant-a"},
    )

    assert second.status_code == 202
    assert seen_since == [datetime(2017, 8, 17, tzinfo=timezone.utc), fetched_at]


def test_malformed_since_returns_422(client, monkeypatch):
    test_client, _connector_repo, _credential_repo = client
    _fake_binance_fetch_capturing(monkeypatch)

    response = test_client.post(
        "/connectors/binance_price_btcusdt_1h/run",
        params={"since": "not-a-date"},
        headers={"X-Tenant-Id": "tenant-a"},
    )

    assert response.status_code == 422


def test_future_since_returns_422(client, monkeypatch):
    test_client, _connector_repo, _credential_repo = client
    _fake_binance_fetch_capturing(monkeypatch)

    response = test_client.post(
        "/connectors/binance_price_btcusdt_1h/run",
        params={"since": "2999-01-01"},
        headers={"X-Tenant-Id": "tenant-a"},
    )

    assert response.status_code == 422


def test_since_before_binance_floor_returns_422(client, monkeypatch):
    test_client, _connector_repo, _credential_repo = client
    _fake_binance_fetch_capturing(monkeypatch)

    response = test_client.post(
        "/connectors/binance_price_btcusdt_1h/run",
        params={"since": "2010-01-01"},
        headers={"X-Tenant-Id": "tenant-a"},
    )

    assert response.status_code == 422


def test_since_before_onchain_floor_returns_422(client, monkeypatch):
    from connectors.blockchain_onchain import BlockchainInfoConnector

    test_client, _connector_repo, _credential_repo = client

    def _fetch(self, since):
        return FetchResult(source=self.name, fetched_at=datetime(2026, 3, 1, tzinfo=timezone.utc), records=pd.DataFrame())

    monkeypatch.setattr(BlockchainInfoConnector, "fetch", _fetch)

    response = test_client.post(
        "/connectors/blockchain_info_hash-rate/run",
        params={"since": "2008-01-01"},
        headers={"X-Tenant-Id": "tenant-a"},
    )

    assert response.status_code == 422


def test_reddit_since_older_than_five_years_has_no_floor(client, monkeypatch):
    from app import credential_crypto as cc

    monkeypatch.setenv("INGESTION_CREDENTIAL_ENCRYPTION_KEY", cc.generate_key().decode("utf-8"))
    test_client, _connector_repo, credential_repository = client
    credential_repository.set_credentials(
        "tenant-a", "reddit_vader_sentiment", client_id="cid", client_secret="secret"
    )
    fetched_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    seen_since: list[datetime] = []

    def _fetch(self, since):
        seen_since.append(since)
        return FetchResult(source=self.name, fetched_at=fetched_at, records=pd.DataFrame())

    monkeypatch.setattr(RedditSentimentConnector, "fetch", _fetch)

    response = test_client.post(
        "/connectors/reddit_vader_sentiment/run",
        params={"since": "2015-01-01"},
        headers={"X-Tenant-Id": "tenant-a"},
    )

    assert response.status_code == 202
    assert seen_since == [datetime(2015, 1, 1, tzinfo=timezone.utc)]
