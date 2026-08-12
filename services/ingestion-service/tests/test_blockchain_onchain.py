"""Tests for `connectors.blockchain_onchain.BlockchainInfoConnector`, using a
fake `requests.Session`. Covers the client-side `since` filtering the module
docstring says is necessary because blockchain.info's own `start` boundary
is "inclusive-but-approximate".
"""

from __future__ import annotations

from datetime import datetime, timezone

from connectors.blockchain_onchain import BlockchainInfoConnector


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
