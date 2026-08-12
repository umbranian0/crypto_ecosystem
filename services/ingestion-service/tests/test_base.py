"""Tests for `connectors.base`: `latest_watermark` and `run_incremental`.

Flagged by the 2026-08-09 review as having zero test coverage despite
nontrivial logic (watermark resolution across incremental CSVs, and the
fetch/print/write orchestration every connector's `__main__` block shares
via `run_incremental`, extracted from three copy-pasted blocks the same
review found).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from connectors.base import FetchResult, IngestionSource, latest_watermark, run_incremental

SEED = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _write_csv(path: Path, column: str, timestamps: list[datetime]) -> None:
    pd.DataFrame({column: timestamps, "value": range(len(timestamps))}).to_csv(path, index=False)


def test_latest_watermark_returns_seed_when_dir_empty(tmp_path: Path) -> None:
    assert latest_watermark(tmp_path, "ts", SEED) == SEED


def test_latest_watermark_returns_seed_when_dir_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    assert latest_watermark(missing, "ts", SEED) == SEED


def test_latest_watermark_finds_max_across_multiple_files(tmp_path: Path) -> None:
    _write_csv(tmp_path / "2026-01-01.csv", "ts", [datetime(2026, 1, 1, tzinfo=timezone.utc)])
    _write_csv(
        tmp_path / "2026-01-03.csv",
        "ts",
        [datetime(2026, 1, 3, tzinfo=timezone.utc), datetime(2026, 1, 2, tzinfo=timezone.utc)],
    )

    result = latest_watermark(tmp_path, "ts", SEED)

    assert result == datetime(2026, 1, 3, tzinfo=timezone.utc)


def test_latest_watermark_ignores_non_csv_files(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("not a csv")

    assert latest_watermark(tmp_path, "ts", SEED) == SEED


class _FakeConnector(IngestionSource):
    def __init__(self, result: FetchResult) -> None:
        self.name = "fake_source"
        self._result = result
        self.received_since: datetime | None = None

    def fetch(self, since: datetime) -> FetchResult:
        self.received_since = since
        return self._result


def test_run_incremental_writes_csv_when_rows_returned(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    fetched_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    records = pd.DataFrame({"ts": [datetime(2026, 3, 1, tzinfo=timezone.utc)], "value": [1]})
    connector = _FakeConnector(FetchResult(source="fake_source", fetched_at=fetched_at, records=records))

    run_incremental(connector, incremental_dir=tmp_path, timestamp_column="ts", seed_watermark=SEED)

    assert connector.received_since == SEED  # resolved from the empty dir -> seed
    out_path = tmp_path / "2026-03-01.csv"
    assert out_path.exists()
    written = pd.read_csv(out_path)
    assert len(written) == 1
    assert "wrote" in capsys.readouterr().out


def test_run_incremental_writes_nothing_when_fetch_is_empty(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    connector = _FakeConnector(
        FetchResult(source="fake_source", fetched_at=datetime(2026, 3, 1, tzinfo=timezone.utc), records=pd.DataFrame())
    )

    run_incremental(connector, incremental_dir=tmp_path, timestamp_column="ts", seed_watermark=SEED)

    assert list(tmp_path.glob("*.csv")) == []
    assert "no new rows" in capsys.readouterr().out


def test_run_incremental_resolves_watermark_from_existing_incremental_files(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    _write_csv(tmp_path / "2026-01-01.csv", "ts", [datetime(2026, 1, 1, tzinfo=timezone.utc)])
    connector = _FakeConnector(
        FetchResult(source="fake_source", fetched_at=datetime(2026, 1, 2, tzinfo=timezone.utc), records=pd.DataFrame())
    )

    run_incremental(connector, incremental_dir=tmp_path, timestamp_column="ts", seed_watermark=SEED)

    assert connector.received_since == datetime(2026, 1, 1, tzinfo=timezone.utc)
