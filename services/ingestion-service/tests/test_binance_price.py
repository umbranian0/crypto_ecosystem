"""Tests for `connectors.binance_price.BinancePriceConnector`, using a fake
`requests.Session` (the constructor already accepts one for exactly this)
instead of hitting the real Binance API.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from connectors.base import run_incremental
from connectors.binance_price import MAX_KLINES_PER_REQUEST, BinancePriceConnector
from fake_repository import FakeConnectorRecordRepository


class _FakeResponse:
    def __init__(self, payload: list[list]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> list[list]:
        return self._payload


class _FakeSession:
    """Returns each entry in `pages` in order, one per `.get()` call."""

    def __init__(self, pages: list[list[list]]) -> None:
        self._pages = list(pages)
        self.calls: list[dict] = []

    def get(self, url: str, params: dict, timeout: int) -> _FakeResponse:
        self.calls.append(params)
        page = self._pages.pop(0) if self._pages else []
        return _FakeResponse(page)


def _kline(open_time_ms: int) -> list:
    # Binance kline shape: [open_time, open, high, low, close, volume,
    # close_time, quote_volume, trades, taker_buy_base, taker_buy_quote, ignore]
    return [open_time_ms, "1", "1", "1", "1", "1", open_time_ms + 1, "1", 1, "1", "1", "0"]


def test_fetch_stops_after_partial_page() -> None:
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session = _FakeSession(pages=[[_kline(int(since.timestamp() * 1000) + 1000)]])
    connector = BinancePriceConnector(session=session)

    result = connector.fetch(since=since)

    assert len(result.records) == 1
    assert list(result.records["symbol"]) == ["BTCUSDT"]
    assert "ignore" not in result.records.columns
    assert len(session.calls) == 1  # partial page (< MAX_KLINES_PER_REQUEST) means no second call


def test_fetch_pages_until_a_partial_page_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("connectors.binance_price.time.sleep", lambda _seconds: None)
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    start_ms = int(since.timestamp() * 1000) + 1
    full_page = [_kline(start_ms + i * 60_000) for i in range(MAX_KLINES_PER_REQUEST)]
    partial_page = [_kline(start_ms + MAX_KLINES_PER_REQUEST * 60_000)]
    session = _FakeSession(pages=[full_page, partial_page])
    connector = BinancePriceConnector(session=session)

    result = connector.fetch(since=since)

    assert len(result.records) == MAX_KLINES_PER_REQUEST + 1
    assert len(session.calls) == 2


def test_fetch_returns_empty_dataframe_when_no_data() -> None:
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session = _FakeSession(pages=[[]])
    connector = BinancePriceConnector(session=session)

    result = connector.fetch(since=since)

    assert result.is_empty()


def test_fetch_name_includes_symbol_and_interval() -> None:
    connector = BinancePriceConnector(symbol="ETHUSDT", interval="4h", session=_FakeSession(pages=[]))
    assert connector.name == "binance_price_ethusdt_4h"


def test_run_incremental_writes_price_records_via_repository(tmp_path) -> None:
    """INGEST-003 DB-write path: `run_incremental` with `tenant_id`/`repository`
    supplied writes via `repository.add_price_records`, not a CSV.
    """
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session = _FakeSession(pages=[[_kline(int(since.timestamp() * 1000) + 1000)]])
    connector = BinancePriceConnector(session=session)
    repository = FakeConnectorRecordRepository()

    run_incremental(
        connector,
        incremental_dir=tmp_path,
        timestamp_column="open_time",
        seed_watermark=since,
        tenant_id="tenant-a",
        repository=repository,
        record_kind="price",
    )

    assert len(repository.price) == 1
    tenant_id, source, records = repository.price[0]
    assert tenant_id == "tenant-a"
    assert source == connector.name
    assert len(records) == 1
    assert "fetched_at" in records.columns
    assert list(tmp_path.glob("*.csv")) == []  # DB path writes no CSV
