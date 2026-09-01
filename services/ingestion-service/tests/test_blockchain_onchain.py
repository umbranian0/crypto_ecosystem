"""Tests for `connectors.blockchain_onchain.BlockchainInfoConnector`, using a
fake `requests.Session`. Covers the client-side `since` filtering the module
docstring says is necessary because blockchain.info's own `start` boundary
is "inclusive-but-approximate".
"""

from __future__ import annotations

from datetime import datetime, timezone

from connectors.base import run_incremental
from connectors.blockchain_onchain import BlockchainInfoConnector
from fake_repository import FakeConnectorRecordRepository


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class _FakeSession:
    def __init__(self, values: list[dict]) -> None:
        self._values = values
        self.calls: list[dict] = []

    def get(self, url: str, params: dict, timeout: int) -> _FakeResponse:
        self.calls.append(params)
        return _FakeResponse({"values": self._values})


def test_fetch_filters_out_values_at_or_before_since() -> None:
    since = datetime(2026, 1, 2, tzinfo=timezone.utc)
    values = [
        {"x": int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()), "y": 1.0},  # before since
        {"x": int(since.timestamp()), "y": 2.0},  # exactly at since
        {"x": int(datetime(2026, 1, 3, tzinfo=timezone.utc).timestamp()), "y": 3.0},  # after since
    ]
    connector = BlockchainInfoConnector("hash-rate", session=_FakeSession(values))

    result = connector.fetch(since=since)

    assert len(result.records) == 1
    assert result.records.iloc[0]["hash-rate"] == 3.0


def test_fetch_returns_empty_dataframe_when_no_values() -> None:
    connector = BlockchainInfoConnector("hash-rate", session=_FakeSession([]))

    result = connector.fetch(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert result.is_empty()


def test_fetch_names_chart_column_after_chart_name() -> None:
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    values = [{"x": int(datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp()), "y": 42.0}]
    connector = BlockchainInfoConnector("n-unique-addresses", session=_FakeSession(values))

    result = connector.fetch(since=since)

    assert "n-unique-addresses" in result.records.columns


def test_fetch_requests_a_generous_timespan() -> None:
    session = _FakeSession([])
    connector = BlockchainInfoConnector("hash-rate", session=session)

    connector.fetch(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert int(session.calls[0]["timespan"].removesuffix("days")) >= 90


def test_run_incremental_writes_onchain_records_via_repository(tmp_path) -> None:
    """INGEST-003 DB-write path: writes via `repository.add_onchain_records`,
    including a value column named after the chart (`hash-rate`), not stored
    as a CSV.
    """
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    values = [{"x": int(datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp()), "y": 42.0}]
    connector = BlockchainInfoConnector("hash-rate", session=_FakeSession(values))
    repository = FakeConnectorRecordRepository()

    run_incremental(
        connector,
        incremental_dir=tmp_path,
        timestamp_column="date",
        seed_watermark=since,
        tenant_id="tenant-a",
        repository=repository,
        record_kind="onchain",
    )

    assert len(repository.onchain) == 1
    tenant_id, source, records = repository.onchain[0]
    assert tenant_id == "tenant-a"
    assert source == connector.name
    assert records.iloc[0]["hash-rate"] == 42.0
    assert "fetched_at" in records.columns
    assert list(tmp_path.glob("*.csv")) == []
