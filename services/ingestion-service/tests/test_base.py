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

from connectors.base import FetchResult, IngestionSource, latest_watermark, latest_watermark_from_db, run_incremental
from fake_repository import FakeConnectorRecordRepository

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


# --- INGEST-003: DB-write path -----------------------------------------------


def test_latest_watermark_from_db_returns_none_when_nothing_written() -> None:
    repository = FakeConnectorRecordRepository()

    assert latest_watermark_from_db(repository, "tenant-a", "fake_source") is None


def test_latest_watermark_from_db_returns_max_fetched_at() -> None:
    repository = FakeConnectorRecordRepository()
    repository.add_price_records(
        "tenant-a",
        "fake_source",
        pd.DataFrame({"fetched_at": [datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 5, tzinfo=timezone.utc)]}),
    )

    result = latest_watermark_from_db(repository, "tenant-a", "fake_source")

    assert result == datetime(2026, 1, 5, tzinfo=timezone.utc)


def test_run_incremental_resolves_watermark_from_db_when_repository_supplied(tmp_path: Path) -> None:
    repository = FakeConnectorRecordRepository()
    repository.add_price_records(
        "tenant-a", "fake_source", pd.DataFrame({"fetched_at": [datetime(2026, 1, 5, tzinfo=timezone.utc)]})
    )
    connector = _FakeConnector(
        FetchResult(source="fake_source", fetched_at=datetime(2026, 1, 6, tzinfo=timezone.utc), records=pd.DataFrame())
    )

    run_incremental(
        connector,
        incremental_dir=tmp_path,
        timestamp_column="ts",
        seed_watermark=SEED,
        tenant_id="tenant-a",
        repository=repository,
        record_kind="price",
    )

    assert connector.received_since == datetime(2026, 1, 5, tzinfo=timezone.utc)


def test_run_incremental_falls_back_to_seed_watermark_when_db_has_no_prior_rows(tmp_path: Path) -> None:
    repository = FakeConnectorRecordRepository()
    connector = _FakeConnector(
        FetchResult(source="fake_source", fetched_at=datetime(2026, 1, 6, tzinfo=timezone.utc), records=pd.DataFrame())
    )

    run_incremental(
        connector,
        incremental_dir=tmp_path,
        timestamp_column="ts",
        seed_watermark=SEED,
        tenant_id="tenant-a",
        repository=repository,
        record_kind="price",
    )

    assert connector.received_since == SEED


def test_run_incremental_writes_nothing_to_csv_in_db_mode(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    repository = FakeConnectorRecordRepository()
    records = pd.DataFrame({"ts": [datetime(2026, 3, 1, tzinfo=timezone.utc)], "value": [1]})
    connector = _FakeConnector(
        FetchResult(source="fake_source", fetched_at=datetime(2026, 3, 1, tzinfo=timezone.utc), records=records)
    )

    run_incremental(
        connector,
        incremental_dir=tmp_path,
        timestamp_column="ts",
        seed_watermark=SEED,
        tenant_id="tenant-a",
        repository=repository,
        record_kind="price",
    )

    assert list(tmp_path.glob("*.csv")) == []
    assert len(repository.price) == 1
    assert "wrote 1 rows to db" in capsys.readouterr().out


def test_run_incremental_isolates_writes_by_tenant(tmp_path: Path) -> None:
    """Cross-tenant isolation (INGEST-003 test AC): two tenants writing
    through the same repository instance never collide -- asserted on which
    tenant's row content ends up where, not just a row count.
    """
    records_a = pd.DataFrame({"ts": [datetime(2026, 3, 1, tzinfo=timezone.utc)], "value": ["tenant-a-row"]})
    records_b = pd.DataFrame({"ts": [datetime(2026, 3, 2, tzinfo=timezone.utc)], "value": ["tenant-b-row"]})
    connector_a = _FakeConnector(
        FetchResult(source="fake_source", fetched_at=datetime(2026, 3, 1, tzinfo=timezone.utc), records=records_a)
    )
    connector_b = _FakeConnector(
        FetchResult(source="fake_source", fetched_at=datetime(2026, 3, 2, tzinfo=timezone.utc), records=records_b)
    )
    repository = FakeConnectorRecordRepository()

    run_incremental(
        connector_a,
        incremental_dir=tmp_path,
        timestamp_column="ts",
        seed_watermark=SEED,
        tenant_id="tenant-a",
        repository=repository,
        record_kind="price",
    )
    run_incremental(
        connector_b,
        incremental_dir=tmp_path,
        timestamp_column="ts",
        seed_watermark=SEED,
        tenant_id="tenant-b",
        repository=repository,
        record_kind="price",
    )

    assert len(repository.price) == 2
    tenant_a_rows = [records for (tenant_id, _source, records) in repository.price if tenant_id == "tenant-a"]
    tenant_b_rows = [records for (tenant_id, _source, records) in repository.price if tenant_id == "tenant-b"]
    assert len(tenant_a_rows) == 1
    assert len(tenant_b_rows) == 1
    assert tenant_a_rows[0]["value"].iloc[0] == "tenant-a-row"
    assert tenant_b_rows[0]["value"].iloc[0] == "tenant-b-row"
    assert "tenant-b-row" not in tenant_a_rows[0]["value"].values
    assert "tenant-a-row" not in tenant_b_rows[0]["value"].values


# --- INGEST-005: crawl-run tracking ------------------------------------------


def test_run_incremental_records_crawl_run_on_successful_write(tmp_path: Path) -> None:
    repository = FakeConnectorRecordRepository()
    records = pd.DataFrame({"ts": [datetime(2026, 3, 1, tzinfo=timezone.utc)], "value": [1]})
    connector = _FakeConnector(
        FetchResult(source="fake_source", fetched_at=datetime(2026, 3, 1, tzinfo=timezone.utc), records=records)
    )

    run_incremental(
        connector,
        incremental_dir=tmp_path,
        timestamp_column="ts",
        seed_watermark=SEED,
        tenant_id="tenant-a",
        repository=repository,
        record_kind="price",
    )

    assert len(repository.crawl_runs) == 1
    tenant_id, source, since_watermark, fetched_at, row_count, status, _rows_so_far, _updated_at = (
        repository.crawl_runs[0]
    )
    assert tenant_id == "tenant-a"
    assert source == "fake_source"
    assert since_watermark == SEED
    assert fetched_at == datetime(2026, 3, 1, tzinfo=timezone.utc)
    assert row_count == 1
    assert status == "completed"


def test_run_incremental_records_crawl_run_on_empty_success(tmp_path: Path) -> None:
    """An empty-but-successful crawl still writes a crawl_runs row
    (row_count=0, status="completed"), not silently skipped (INGEST-005 test
    AC)."""
    repository = FakeConnectorRecordRepository()
    connector = _FakeConnector(
        FetchResult(source="fake_source", fetched_at=datetime(2026, 3, 1, tzinfo=timezone.utc), records=pd.DataFrame())
    )

    run_incremental(
        connector,
        incremental_dir=tmp_path,
        timestamp_column="ts",
        seed_watermark=SEED,
        tenant_id="tenant-a",
        repository=repository,
        record_kind="price",
    )

    assert len(repository.crawl_runs) == 1
    _tenant_id, _source, _since, _fetched_at, row_count, status, _rows_so_far, _updated_at = (
        repository.crawl_runs[0]
    )
    assert row_count == 0
    assert status == "completed"


def test_run_incremental_records_crawl_run_as_failed_when_write_raises(tmp_path: Path) -> None:
    repository = FakeConnectorRecordRepository()

    def _raise(*_args, **_kwargs):
        raise RuntimeError("write failed")

    repository.add_price_records = _raise  # type: ignore[method-assign]
    records = pd.DataFrame({"ts": [datetime(2026, 3, 1, tzinfo=timezone.utc)], "value": [1]})
    connector = _FakeConnector(
        FetchResult(source="fake_source", fetched_at=datetime(2026, 3, 1, tzinfo=timezone.utc), records=records)
    )

    with pytest.raises(RuntimeError, match="write failed"):
        run_incremental(
            connector,
            incremental_dir=tmp_path,
            timestamp_column="ts",
            seed_watermark=SEED,
            tenant_id="tenant-a",
            repository=repository,
            record_kind="price",
        )

    assert len(repository.crawl_runs) == 1
    _tenant_id, _source, _since, _fetched_at, row_count, status, _rows_so_far, _updated_at = (
        repository.crawl_runs[0]
    )
    assert row_count == 0
    assert status == "failed"


def test_run_incremental_two_tenants_have_independent_crawl_runs_and_watermarks(tmp_path: Path) -> None:
    """Two tenants crawling the same source produce two independent
    `crawl_runs` rows and two independent watermarks -- tenant A running
    ahead never changes tenant B's `since` resolution (INGEST-005 test AC).
    Non-tautological: tenant B's own next-watermark value is asserted to
    stay anchored to tenant B's own last row, resolved via
    `latest_watermark_from_db` after both runs.
    """
    repository = FakeConnectorRecordRepository()
    tenant_a_last_fetched_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    tenant_b_last_fetched_at = datetime(2026, 1, 10, tzinfo=timezone.utc)
    connector_a = _FakeConnector(
        FetchResult(
            source="fake_source",
            fetched_at=tenant_a_last_fetched_at,
            records=pd.DataFrame({"ts": [tenant_a_last_fetched_at], "value": ["tenant-a-row"]}),
        )
    )
    connector_b = _FakeConnector(
        FetchResult(
            source="fake_source",
            fetched_at=tenant_b_last_fetched_at,
            records=pd.DataFrame({"ts": [tenant_b_last_fetched_at], "value": ["tenant-b-row"]}),
        )
    )

    # Tenant A crawls first and runs far ahead of tenant B.
    run_incremental(
        connector_a,
        incremental_dir=tmp_path,
        timestamp_column="ts",
        seed_watermark=SEED,
        tenant_id="tenant-a",
        repository=repository,
        record_kind="price",
    )
    run_incremental(
        connector_b,
        incremental_dir=tmp_path,
        timestamp_column="ts",
        seed_watermark=SEED,
        tenant_id="tenant-b",
        repository=repository,
        record_kind="price",
    )

    assert len(repository.crawl_runs) == 2
    tenant_a_runs = [run for run in repository.crawl_runs if run[0] == "tenant-a"]
    tenant_b_runs = [run for run in repository.crawl_runs if run[0] == "tenant-b"]
    assert len(tenant_a_runs) == 1
    assert len(tenant_b_runs) == 1

    # Tenant B's own next watermark stays anchored to tenant B's own last
    # row, unaffected by tenant A running far ahead through the same
    # repository/source.
    tenant_b_next_watermark = latest_watermark_from_db(repository, "tenant-b", "fake_source")
    assert tenant_b_next_watermark == tenant_b_last_fetched_at
    assert tenant_b_next_watermark != tenant_a_last_fetched_at
