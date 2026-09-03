"""Tests for `POST /connectors/{source}/run` (INGEST-008, extended by
INGEST-015 for the lock-gated/background-execution rewrite).

Mirrors `tests/test_health.py`'s `app.dependency_overrides` pattern: fakes
from `tests/fake_repository.py` are wired in via `app.dependency_overrides`,
not real Postgres. `RedditSentimentConnector.fetch` is monkeypatched at the
class level (not through `_client`/`praw`) so these tests never touch the
network, mirroring `tests/test_reddit_sentiment.py`'s own "replace the
lazily-built collaborator" approach applied one level up (the whole
`fetch()`), since `run_connector` calls `fetch()` directly, not `_client()`.

INGEST-015 note on `BackgroundTasks` timing: FastAPI's `TestClient` executes
scheduled `BackgroundTasks` synchronously, as part of the same call that
returns the response (observed directly below, and documented at each test
that depends on it) -- so a fake connector whose `fetch()` returns
immediately has *already* had its background `_execute_crawl` run to
completion by the time `test_client.post(...)` returns. The one exception is
the concurrency tests further down, which use a `fetch()` that blocks on a
`threading.Event`: those issue the request from a background `threading.
Thread` specifically so the blocking `fetch()` (and therefore the
synchronous-within-that-thread `BackgroundTasks` execution) doesn't hang the
main test thread, and the test explicitly releases the block once both
threads' `202`/`409` responses are observed.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.crawl_registry import CrawlRegistry
from connectors.base import FetchResult
from connectors.binance_price import MAX_KLINES_PER_REQUEST, BinancePriceConnector
from connectors.reddit_sentiment import RedditSentimentConnector
from fake_repository import FakeConnectorRecordRepository, FakeCredentialRepository


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.dependencies.repositories import (
        get_connector_record_repository,
        get_crawl_registry,
        get_credential_repository,
    )
    from app.main import app

    connector_repository = FakeConnectorRecordRepository()
    credential_repository = FakeCredentialRepository()
    # Fresh registry per test (test-isolation fix): without this override,
    # every test in this file shared the real process-lifetime module-level
    # `_crawl_registry` singleton from `app.dependencies.repositories`, so a
    # lock acquired (or not cleanly released) in one test could leak into a
    # later test using the same tenant_id+source, producing rare flakes in
    # the concurrency tests below.
    crawl_registry = CrawlRegistry()

    app.dependency_overrides[get_connector_record_repository] = lambda: connector_repository
    app.dependency_overrides[get_credential_repository] = lambda: credential_repository
    app.dependency_overrides[get_crawl_registry] = lambda: crawl_registry
    try:
        yield TestClient(app), connector_repository, credential_repository
    finally:
        app.dependency_overrides.pop(get_connector_record_repository, None)
        app.dependency_overrides.pop(get_credential_repository, None)
        app.dependency_overrides.pop(get_crawl_registry, None)


def _fake_binance_fetch(monkeypatch, rows: int = 1):
    fetched_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    records = pd.DataFrame({"symbol": ["BTCUSDT"] * rows, "open": [1.0] * rows})

    def _fetch(self, since, **_kwargs):
        return FetchResult(source=self.name, fetched_at=fetched_at, records=records)

    monkeypatch.setattr(BinancePriceConnector, "fetch", _fetch)
    return fetched_at


def test_unknown_source_returns_404(client):
    test_client, _connector_repo, _credential_repo = client

    response = test_client.post("/connectors/not_a_real_source/run", headers={"X-Tenant-Id": "tenant-a"})

    assert response.status_code == 404


def test_successful_trigger_writes_rows_via_repository(client, monkeypatch):
    test_client, connector_repo, _credential_repo = client
    _fake_binance_fetch(monkeypatch, rows=2)

    response = test_client.post(
        "/connectors/binance_price_btcusdt_1h/run", headers={"X-Tenant-Id": "tenant-a"}
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert "row_count" not in body
    assert "fetched_at" not in body

    assert len(connector_repo.price) == 1
    tenant_id, source, records = connector_repo.price[0]
    assert tenant_id == "tenant-a"
    assert source == "binance_price_btcusdt_1h"
    assert len(records) == 2

    # `TestClient` runs `BackgroundTasks` synchronously before returning the
    # response (see module docstring) -- by the time `.post()` returns, the
    # "queued" row `run_connector` wrote, the "running" row `_execute_crawl`
    # wrote (INGEST-021) before calling `fetch()`, and the "completed" row it
    # wrote afterward are all already present, in that order.
    assert len(connector_repo.crawl_runs) == 3
    queued_run, running_run, completed_run = connector_repo.crawl_runs
    assert queued_run[0] == "tenant-a"
    assert queued_run[5] == "queued"
    assert running_run[0] == "tenant-a"
    assert running_run[5] == "running"
    assert completed_run[0] == "tenant-a"
    assert completed_run[4] == 2
    assert completed_run[5] == "completed"


def test_running_row_written_before_terminal_row(client, monkeypatch):
    """INGEST-021: `_execute_crawl` writes a `status="running"` row
    immediately before calling `connector.fetch(...)`, not just at
    completion -- asserted here by exact sequence, not just presence."""
    test_client, connector_repo, _credential_repo = client
    _fake_binance_fetch(monkeypatch, rows=1)

    response = test_client.post(
        "/connectors/binance_price_btcusdt_1h/run", headers={"X-Tenant-Id": "tenant-a"}
    )

    assert response.status_code == 202
    statuses = [run[5] for run in connector_repo.crawl_runs if run[0] == "tenant-a"]
    assert statuses == ["queued", "running", "completed"]


def test_execute_crawl_wires_registrys_should_cancel_into_fetch():
    """INGEST-023: `_execute_crawl`'s `connector.fetch(...)` call passes
    `should_cancel=lambda: registry.should_cancel(tenant_id, connector.name)`
    -- proved directly (bypassing the HTTP layer, mirroring
    `test_crawl_registry.py`'s own unit-level style) by calling `_execute_crawl`
    with a registry that already has a matching cancel flag set and observing
    the fake connector's `fetch()` sees `should_cancel() is True`, then again
    with no flag set and observing `False`. Also proves the closure captures
    the *same* `tenant_id`/`connector.name` values `try_acquire` used (a
    mismatched key would silently make cancellation a no-op)."""
    from app.routers.connectors import _execute_crawl

    tenant_id = "tenant-a"
    fetched_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    seen: dict = {}

    class _FakeConnector:
        name = "binance_price_btcusdt_1h"

        def fetch(self, since, should_cancel=None, **_kwargs):
            seen["should_cancel"] = should_cancel() if should_cancel is not None else None
            return FetchResult(source=self.name, fetched_at=fetched_at, records=pd.DataFrame())

    repository = FakeConnectorRecordRepository()
    connector = _FakeConnector()

    registry = CrawlRegistry()
    registry.try_acquire(tenant_id, connector.name)
    registry.request_cancel(tenant_id, connector.name)

    _execute_crawl(repository, registry, tenant_id, connector, "price", None)

    assert seen["should_cancel"] is True

    seen.clear()
    registry2 = CrawlRegistry()
    registry2.try_acquire(tenant_id, connector.name)
    # No `request_cancel` this time -- the same key must read as not-cancelled.
    _execute_crawl(repository, registry2, tenant_id, connector, "price", None)

    assert seen["should_cancel"] is False


def test_cross_tenant_isolation(client, monkeypatch):
    test_client, connector_repo, _credential_repo = client
    _fake_binance_fetch(monkeypatch, rows=1)

    test_client.post("/connectors/binance_price_btcusdt_1h/run", headers={"X-Tenant-Id": "tenant-a"})
    test_client.post("/connectors/binance_price_btcusdt_1h/run", headers={"X-Tenant-Id": "tenant-b"})

    assert len(connector_repo.price) == 2
    tenants_written = {tenant_id for (tenant_id, _source, _records) in connector_repo.price}
    assert tenants_written == {"tenant-a", "tenant-b"}
    # One "queued" + one "running" + one "completed" row per tenant (see comment above).
    assert len(connector_repo.crawl_runs) == 6
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

    def _fetch(self, since, **_kwargs):
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

    def _fetch(self, since, **_kwargs):
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

    def _fetch(self, since, **_kwargs):
        return FetchResult(source=self.name, fetched_at=fetched_at, records=pd.DataFrame())

    monkeypatch.setattr(BinancePriceConnector, "fetch", _fetch)
    test_client, connector_repo, _credential_repo = client

    response = test_client.post(
        "/connectors/binance_price_btcusdt_1h/run", headers={"X-Tenant-Id": "tenant-a"}
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert "row_count" not in body
    assert connector_repo.price == []
    assert len(connector_repo.crawl_runs) == 3
    queued_run, running_run, completed_run = connector_repo.crawl_runs
    assert queued_run[5] == "queued"
    assert running_run[5] == "running"
    assert completed_run[4] == 0
    assert completed_run[5] == "completed"


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

    def _fetch(self, since, **_kwargs):
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

    def _fetch(self, since, **_kwargs):
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

    def _fetch(self, since, **_kwargs):
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

    def _fetch(self, since, **_kwargs):
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


def test_409_when_crawl_already_in_progress(client):
    """After `run_connector` acquires the lock, a second request for the
    same `(tenant_id, source)` gets an immediate `409` -- exercised here
    directly against the registry rather than real concurrency (the real
    concurrent-thread proof is `test_concurrent_requests_same_source_...`
    below); this test only pins the plain sequential-second-call behavior
    and the exact detail message.
    """
    from app.dependencies.repositories import get_crawl_registry
    from app.main import app

    test_client, _connector_repo, _credential_repo = client
    # Fetch the *same* per-test registry instance the `client` fixture wired
    # up as the override (not the real process-lifetime singleton -- see the
    # fixture's comment) so this test's manual `try_acquire` is actually
    # visible to the request issued below.
    registry = app.dependency_overrides[get_crawl_registry]()
    registry.try_acquire("tenant-a", "binance_price_btcusdt_1h")
    try:
        response = test_client.post(
            "/connectors/binance_price_btcusdt_1h/run", headers={"X-Tenant-Id": "tenant-a"}
        )
        assert response.status_code == 409
        assert "crawl already in progress" in response.json()["detail"]
        assert "binance_price_btcusdt_1h" in response.json()["detail"]
    finally:
        registry.release("tenant-a", "binance_price_btcusdt_1h")


def test_completed_crawl_observable_via_status_endpoint(client, monkeypatch):
    """A completed background crawl (INGEST-015) is observable via
    `GET /connectors/{source}/status` (INGEST-009) once the background task
    -- run synchronously by `TestClient` before `.post()` returns, per the
    module docstring -- has finished. `latest_crawl_run` (INGEST-009,
    unchanged by this ticket) picks the row with the max `fetched_at`
    (`ORDER BY fetched_at DESC LIMIT 1` in the real Postgres repository) --
    the fake `fetch()` here returns a fresh `datetime.now(timezone.utc)`
    (with a tiny sleep first) so the "completed" row's `fetched_at` is
    unambiguously later than the "queued" row's, exactly as it would be in a
    real crawl that takes measurable wall-clock time.
    """
    import time

    test_client, _connector_repo, _credential_repo = client

    def _fetch(self, since, **_kwargs):
        time.sleep(0.01)
        records = pd.DataFrame({"symbol": ["BTCUSDT"] * 3, "open": [1.0] * 3})
        return FetchResult(source=self.name, fetched_at=datetime.now(timezone.utc), records=records)

    monkeypatch.setattr(BinancePriceConnector, "fetch", _fetch)

    post_response = test_client.post(
        "/connectors/binance_price_btcusdt_1h/run", headers={"X-Tenant-Id": "tenant-a"}
    )
    assert post_response.status_code == 202

    status_response = test_client.get(
        "/connectors/binance_price_btcusdt_1h/status", headers={"X-Tenant-Id": "tenant-a"}
    )
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["status"] == "completed"
    assert body["row_count"] == 3


def test_failed_fetch_recorded_as_failed_and_releases_lock(client, monkeypatch):
    """A `fetch()` that raises is recorded as `status="failed"`, not left
    `"queued"` forever, and does not leave the lock held -- a subsequent
    request for the same source succeeds with `202`, not `409` (INGEST-015).
    A tiny sleep before raising guarantees the "failed" row's `fetched_at`
    (`utcnow()`, called in `_execute_crawl`'s exception handler) is
    unambiguously later than the "queued" row's, so `latest_crawl_run`'s
    `ORDER BY fetched_at DESC` deterministically picks it (see the previous
    test's docstring for why this matters)."""
    import time

    test_client, connector_repo, _credential_repo = client

    def _raising_fetch(self, since, **_kwargs):
        time.sleep(0.01)
        raise RuntimeError("upstream boom")

    monkeypatch.setattr(BinancePriceConnector, "fetch", _raising_fetch)

    response = test_client.post(
        "/connectors/binance_price_btcusdt_1h/run", headers={"X-Tenant-Id": "tenant-a"}
    )
    assert response.status_code == 202

    assert len(connector_repo.crawl_runs) == 3
    queued_run, running_run, failed_run = connector_repo.crawl_runs
    assert queued_run[5] == "queued"
    assert running_run[5] == "running"
    assert failed_run[5] == "failed"

    status_response = test_client.get(
        "/connectors/binance_price_btcusdt_1h/status", headers={"X-Tenant-Id": "tenant-a"}
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "failed"

    # Lock released -- a subsequent request succeeds, not a 409.
    monkeypatch.setattr(BinancePriceConnector, "fetch", lambda self, since, **_kwargs: FetchResult(
        source=self.name, fetched_at=datetime(2026, 3, 1, tzinfo=timezone.utc), records=pd.DataFrame()
    ))
    retry_response = test_client.post(
        "/connectors/binance_price_btcusdt_1h/run", headers={"X-Tenant-Id": "tenant-a"}
    )
    assert retry_response.status_code == 202


def test_before_fix_concurrent_writes_without_a_lock_raise(monkeypatch):
    """Permanent regression test for the pre-INGEST-015 bug mechanism --
    NOT an exercise of the new `CrawlRegistry` lock.

    Reproduces the exact race QA found: two callers directly run the old
    synchronous sequence (`latest_watermark_from_db` -> `connector.fetch` ->
    `add_price_records`), concurrently, with **no lock involved at all**.
    `FakeConnectorRecordRepository.add_price_records` is monkeypatched to
    raise on a second overlapping write for the same `(tenant_id, source)` --
    simulating Postgres's real `UniqueViolation` -- proving that without
    serialization, both callers resolve the same `since` and both attempt to
    write, and the second one blows up unhandled. This is the failure mode
    INGEST-015's lock exists to prevent; it must keep failing here forever,
    since this test intentionally never touches `CrawlRegistry`.
    """
    from connectors.base import latest_watermark_from_db

    repository = FakeConnectorRecordRepository()
    tenant_id = "tenant-a"
    source = "binance_price_btcusdt_1h"
    fetched_at = datetime(2026, 3, 1, tzinfo=timezone.utc)

    write_count = {"n": 0}
    original_add_price_records = FakeConnectorRecordRepository.add_price_records

    def _add_price_records_raise_on_second_overlap(self, tenant_id, source, records):
        write_count["n"] += 1
        if write_count["n"] >= 2:
            raise RuntimeError("simulated Postgres UniqueViolation: duplicate key value")
        return original_add_price_records(self, tenant_id, source, records)

    monkeypatch.setattr(
        FakeConnectorRecordRepository, "add_price_records", _add_price_records_raise_on_second_overlap
    )

    def _old_synchronous_crawl():
        since = latest_watermark_from_db(repository, tenant_id, source)
        if since is None:
            since = datetime(2017, 8, 17, tzinfo=timezone.utc)
        records = pd.DataFrame({"symbol": ["BTCUSDT"], "open": [1.0], "fetched_at": [fetched_at]})
        repository.add_price_records(tenant_id, source, records)

    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def _run():
        barrier.wait()
        try:
            _old_synchronous_crawl()
        except Exception as exc:  # noqa: BLE001 -- capturing for cross-thread assertion
            errors.append(exc)

    threads = [threading.Thread(target=_run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(errors) == 1
    assert "UniqueViolation" in str(errors[0])


class _BlockingFakeConnector:
    """Fake connector whose `fetch()` blocks on a `threading.Event` until
    released -- simulates the real ~70s Binance backfill for the after-fix
    concurrency proof below."""

    def __init__(self, name: str, release_event: threading.Event, entered_event: threading.Event):
        self.name = name
        self._release_event = release_event
        self._entered_event = entered_event

    def fetch(self, since, **_kwargs):
        self._entered_event.set()
        self._release_event.wait(timeout=5)
        return FetchResult(
            source=self.name,
            fetched_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
            records=pd.DataFrame({"symbol": ["BTCUSDT"], "open": [1.0]}),
        )


def test_concurrent_requests_same_source_one_202_one_409(client, monkeypatch):
    """After-fix proof, at the real HTTP layer (INGEST-015's headline
    acceptance criterion): two real `threading.Thread`s, synchronized via a
    `threading.Barrier(2)`, issue `client.post(.../run)` for the *same*
    `(tenant_id, source)` at effectively the same time. Exactly one gets
    `202`, the other `409` with "crawl already in progress"; after releasing
    the blocked `fetch()`, exactly one write occurs and exactly one
    `crawl_runs` row reaches "completed" -- no 500, no duplicate insert.

    Threading note: `TestClient` runs `BackgroundTasks` synchronously as part
    of the request/response cycle, so the thread that wins the lock blocks
    *inside* its own `.post()` call until `release_event` is set from the
    main test thread -- this is why the request must be issued from a
    background `threading.Thread` (not the main thread), and why the test
    waits for `entered_event` before setting `release_event`, rather than
    setting it eagerly (which could race ahead of `fetch()` even being
    called).

    Second synchronization point (`both_attempted_event`, added after a
    ~1/70 flake reproduced by looping this test): `entered_event` alone only
    proves the *winning* thread reached `fetch()` -- it says nothing about
    whether the *losing* thread has reached `registry.try_acquire` yet. If
    the OS scheduler is slow to run the losing thread, the winner's `fetch()`
    can be released and its lock fully released (`_execute_crawl`'s
    `finally: registry.release(...)`) before the loser ever calls
    `try_acquire`, so the loser then finds the lock free and also gets `202`
    -- observed directly as `[202, 202]` instead of `[202, 409]`. Wrapping
    `registry.try_acquire` to count both threads' attempts (regardless of
    outcome) and waiting for both before releasing `fetch()` closes that
    window deterministically, without touching production code.
    """
    from app.dependencies.repositories import get_crawl_registry
    from app.main import app

    test_client, connector_repo, _credential_repo = client

    registry = app.dependency_overrides[get_crawl_registry]()
    original_try_acquire = registry.try_acquire
    attempts_lock = threading.Lock()
    attempts = {"n": 0}
    both_attempted_event = threading.Event()

    def _counting_try_acquire(tenant_id: str, source: str) -> bool:
        result = original_try_acquire(tenant_id, source)
        with attempts_lock:
            attempts["n"] += 1
            if attempts["n"] >= 2:
                both_attempted_event.set()
        return result

    monkeypatch.setattr(registry, "try_acquire", _counting_try_acquire)

    release_event = threading.Event()
    entered_event = threading.Event()
    connector = _BlockingFakeConnector("binance_price_btcusdt_1h", release_event, entered_event)

    monkeypatch.setattr(BinancePriceConnector, "fetch", lambda self, since, **_kwargs: connector.fetch(since))

    barrier = threading.Barrier(2)
    responses: list = [None, None]

    def _post(index: int):
        barrier.wait()
        responses[index] = test_client.post(
            "/connectors/binance_price_btcusdt_1h/run", headers={"X-Tenant-Id": "tenant-a"}
        )

    threads = [threading.Thread(target=_post, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()

    # Wait for *both* threads to have called `try_acquire` (whichever order
    # they land in) before releasing the winner's blocked `fetch()` -- see
    # the docstring above for why `entered_event` alone wasn't sufficient.
    assert both_attempted_event.wait(timeout=5)
    # Exactly one thread will actually call `fetch()` and block there; the
    # other gets its `409` immediately (before the lock winner even starts
    # `fetch()`, but `entered_event` only ever fires once regardless).
    assert entered_event.wait(timeout=5)
    release_event.set()

    for thread in threads:
        thread.join(timeout=5)

    status_codes = sorted(response.status_code for response in responses)
    assert status_codes == [202, 409]

    conflict_response = responses[0] if responses[0].status_code == 409 else responses[1]
    assert "crawl already in progress" in conflict_response.json()["detail"]

    assert len(connector_repo.price) == 1
    completed_runs = [run for run in connector_repo.crawl_runs if run[5] == "completed"]
    assert len(completed_runs) == 1


# --- INGEST-024: POST /connectors/{source}/cancel ---------------------------


def test_cancel_unknown_source_returns_404(client):
    test_client, _connector_repo, _credential_repo = client

    response = test_client.post(
        "/connectors/not_a_real_source/cancel", headers={"X-Tenant-Id": "tenant-a"}
    )

    assert response.status_code == 404


def test_cancel_nothing_in_flight_returns_409(client):
    test_client, _connector_repo, _credential_repo = client

    response = test_client.post(
        "/connectors/binance_price_btcusdt_1h/cancel", headers={"X-Tenant-Id": "tenant-a"}
    )

    assert response.status_code == 409


def test_cancel_success_returns_202_and_writes_cancelling_row(client):
    """A `POST /cancel` while a crawl is genuinely in flight (proved via the
    same blocking-`fetch`-via-`threading.Event` pattern the concurrency tests
    above use) gets `202` + `{"status": "cancelling"}`, and a `"cancelling"`
    `crawl_runs` row is written."""
    from app.dependencies.repositories import get_crawl_registry
    from app.main import app

    test_client, connector_repo, _credential_repo = client

    release_event = threading.Event()
    entered_event = threading.Event()
    connector = _BlockingFakeConnector("binance_price_btcusdt_1h", release_event, entered_event)
    monkeypatch_target = BinancePriceConnector
    original_fetch = monkeypatch_target.fetch
    monkeypatch_target.fetch = lambda self, since, **_kwargs: connector.fetch(since)
    try:
        thread = threading.Thread(
            target=lambda: test_client.post(
                "/connectors/binance_price_btcusdt_1h/run", headers={"X-Tenant-Id": "tenant-a"}
            )
        )
        thread.start()
        assert entered_event.wait(timeout=5)

        cancel_response = test_client.post(
            "/connectors/binance_price_btcusdt_1h/cancel", headers={"X-Tenant-Id": "tenant-a"}
        )
        assert cancel_response.status_code == 202
        assert cancel_response.json() == {"source": "binance_price_btcusdt_1h", "status": "cancelling"}

        registry = app.dependency_overrides[get_crawl_registry]()
        assert registry.should_cancel("tenant-a", "binance_price_btcusdt_1h") is True

        cancelling_rows = [run for run in connector_repo.crawl_runs if run[5] == "cancelling"]
        assert len(cancelling_rows) == 1

        release_event.set()
        thread.join(timeout=5)
    finally:
        monkeypatch_target.fetch = original_fetch


def test_execute_crawl_race_finishes_completed_despite_pending_cancel():
    """INGEST-024's documented race, exercised non-tautologically: a fake
    connector whose `fetch()` returns `cancelled=True` (it honored
    `should_cancel`) resolves to `status="cancelled"`; a fake connector whose
    `fetch()` returns `cancelled=False` even though a cancel was *also*
    requested (the race) resolves to `status="completed"` -- proving
    `_execute_crawl` uses `result.cancelled`, not a fresh registry query."""
    from app.routers.connectors import _execute_crawl

    tenant_id = "tenant-a"
    fetched_at = datetime(2026, 3, 1, tzinfo=timezone.utc)

    class _FakeConnector:
        name = "binance_price_btcusdt_1h"

        def __init__(self, cancelled: bool):
            self._cancelled = cancelled

        def fetch(self, since, should_cancel=None, on_progress=None, **_kwargs):
            return FetchResult(
                source=self.name, fetched_at=fetched_at, records=pd.DataFrame(), cancelled=self._cancelled
            )

    # Case 1: connector honored should_cancel -> "cancelled".
    repository = FakeConnectorRecordRepository()
    registry = CrawlRegistry()
    connector = _FakeConnector(cancelled=True)
    registry.try_acquire(tenant_id, connector.name)
    registry.request_cancel(tenant_id, connector.name)

    _execute_crawl(repository, registry, tenant_id, connector, "price", None)

    terminal_status = repository.crawl_runs[-1][5]
    assert terminal_status == "cancelled"

    # Case 2 (the race): a cancel was also requested, but fetch() completed
    # naturally without ever observing it (cancelled=False) -> "completed".
    repository2 = FakeConnectorRecordRepository()
    registry2 = CrawlRegistry()
    connector2 = _FakeConnector(cancelled=False)
    registry2.try_acquire(tenant_id, connector2.name)
    registry2.request_cancel(tenant_id, connector2.name)

    _execute_crawl(repository2, registry2, tenant_id, connector2, "price", None)

    terminal_status2 = repository2.crawl_runs[-1][5]
    assert terminal_status2 == "completed"


def test_execute_crawl_wires_on_progress_into_fetch():
    """INGEST-024: `_execute_crawl` passes `on_progress=lambda n:
    repository.record_crawl_progress(tenant_id, connector.name, n)` into
    `connector.fetch(...)` -- proved by having the fake connector call
    `on_progress` mid-fetch and observing the "running" row's
    `rows_fetched_so_far` updated in place (no new row inserted)."""
    from app.routers.connectors import _execute_crawl

    tenant_id = "tenant-a"
    fetched_at = datetime(2026, 3, 1, tzinfo=timezone.utc)

    class _FakeConnector:
        name = "binance_price_btcusdt_1h"

        def fetch(self, since, should_cancel=None, on_progress=None, **_kwargs):
            on_progress(1)
            on_progress(2)
            return FetchResult(source=self.name, fetched_at=fetched_at, records=pd.DataFrame())

    repository = FakeConnectorRecordRepository()
    registry = CrawlRegistry()
    connector = _FakeConnector()
    registry.try_acquire(tenant_id, connector.name)

    rows_before = len(repository.crawl_runs)
    _execute_crawl(repository, registry, tenant_id, connector, "price", None)

    # "running" + "completed" only -- no extra row per on_progress call.
    assert len(repository.crawl_runs) == rows_before + 2
    running_run = [run for run in repository.crawl_runs if run[5] == "running"][0]
    assert running_run[6] == 2


def test_multi_page_binance_crawl_reports_progress_before_completion(client, monkeypatch):
    """INGEST-025: a real (not stand-in) `BinancePriceConnector`, given a
    fake `requests.Session` that returns two pages, drives `on_progress` via
    `_execute_crawl`'s wiring into `record_crawl_progress` -- proving the
    end-to-end path (not just `_execute_crawl` in isolation, as
    `test_execute_crawl_wires_on_progress_into_fetch` above already does with
    a stand-in connector). The `"running"` row's `rows_fetched_so_far` ends
    at the final page's cumulative count, observed before the terminal
    `"completed"` row is appended (`FakeConnectorRecordRepository.
    record_crawl_progress` updates in place, never appends).
    """
    monkeypatch.setattr("connectors.binance_price.time.sleep", lambda _seconds: None)
    test_client, connector_repo, _credential_repo = client

    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    start_ms = int(since.timestamp() * 1000) + 1
    full_page = [
        [start_ms + i * 60_000, "1", "1", "1", "1", "1", start_ms + i * 60_000 + 1, "1", 1, "1", "1", "0"]
        for i in range(MAX_KLINES_PER_REQUEST)
    ]
    partial_page = [
        [
            start_ms + MAX_KLINES_PER_REQUEST * 60_000,
            "1",
            "1",
            "1",
            "1",
            "1",
            start_ms + MAX_KLINES_PER_REQUEST * 60_000 + 1,
            "1",
            1,
            "1",
            "1",
            "0",
        ]
    ]

    class _FakeSession:
        def __init__(self, pages):
            self._pages = list(pages)

        def get(self, url, params, timeout):
            page = self._pages.pop(0) if self._pages else []
            return _FakeKlinesResponse(page)

    class _FakeKlinesResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    fake_session = _FakeSession([full_page, partial_page])
    real_connector = BinancePriceConnector(session=fake_session)
    monkeypatch.setattr(
        "app.routers.connectors._binance_source",
        lambda: (real_connector, datetime(2017, 8, 17, tzinfo=timezone.utc), "price", False, datetime(2017, 8, 17, tzinfo=timezone.utc)),
    )

    response = test_client.post(
        "/connectors/binance_price_btcusdt_1h/run", headers={"X-Tenant-Id": "tenant-a"}
    )

    assert response.status_code == 202
    assert len(connector_repo.crawl_runs) == 3
    queued_run, running_run, completed_run = connector_repo.crawl_runs
    assert queued_run[5] == "queued"
    assert running_run[5] == "running"
    assert running_run[6] == MAX_KLINES_PER_REQUEST + 1  # final cumulative count, in place
    assert completed_run[5] == "completed"
    assert completed_run[4] == MAX_KLINES_PER_REQUEST + 1


def test_concurrent_requests_different_sources_both_202(client, monkeypatch):
    """Third case for completeness: same two-thread setup, but for *different*
    `source` values (same tenant) -- both must succeed with `202`, proving
    the lock doesn't over-serialize unrelated crawls."""
    from connectors.blockchain_onchain import BlockchainInfoConnector

    test_client, connector_repo, _credential_repo = client

    fetched_at = datetime(2026, 3, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(
        BinancePriceConnector,
        "fetch",
        lambda self, since, **_kwargs: FetchResult(
            source=self.name, fetched_at=fetched_at, records=pd.DataFrame({"symbol": ["BTCUSDT"], "open": [1.0]})
        ),
    )
    monkeypatch.setattr(
        BlockchainInfoConnector,
        "fetch",
        lambda self, since, **_kwargs: FetchResult(
            source=self.name,
            fetched_at=fetched_at,
            records=pd.DataFrame({"timestamp_unix": [1], "date": [fetched_at], "hash-rate": [123.4]}),
        ),
    )

    barrier = threading.Barrier(2)
    responses: list = [None, None]
    paths = ["/connectors/binance_price_btcusdt_1h/run", "/connectors/blockchain_info_hash-rate/run"]

    def _post(index: int):
        barrier.wait()
        responses[index] = test_client.post(paths[index], headers={"X-Tenant-Id": "tenant-a"})

    threads = [threading.Thread(target=_post, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert [response.status_code for response in responses] == [202, 202]
    assert len(connector_repo.price) == 1
    assert len(connector_repo.onchain) == 1
