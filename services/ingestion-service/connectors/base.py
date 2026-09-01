"""IngestionSource adapter interface.

Every external data source (exchange price feed, on-chain metric, sentiment
feed) implements this one interface, per the Adapter pattern named for this
service in docs/implementation-plan.md section 7. Adding a new source means
writing one new subclass here — nothing else in the ingestion pipeline
changes.

Causal-lag requirement (docs/da-tese-ao-produto.md section 1.6): every
connector must record *when a record became known* (`fetched_at`), not just
the timestamp the record describes. This is what keeps a future sentiment/
on-chain feature from silently reintroducing the leakage problem the naive
first_engine's purge gap exists to prevent, one layer upstream of the
validation engine.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:  # pragma: no cover - import-time only, avoids a hard runtime
    # dependency from this standalone-runnable module onto `app`'s src layout.
    from app.repositories.interfaces import ConnectorRecordRepository


@dataclass(frozen=True)
class FetchResult:
    source: str
    fetched_at: datetime
    records: pd.DataFrame

    def is_empty(self) -> bool:
        return self.records.empty


class IngestionSource(ABC):
    """One adapter per external data source. No I/O beyond this class's own fetch."""

    name: str

    @abstractmethod
    def fetch(self, since: datetime) -> FetchResult:
        """Return all records known to have become available strictly after `since`.

        Implementations must not backfill or mutate records already fetched in
        a prior call — this is an append-only, incremental interface so raw-zone
        writes stay immutable (docs/solution-design.md section 3.1).
        """
        raise NotImplementedError


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def latest_watermark(incremental_dir: str | Path, timestamp_column: str, seed_watermark: datetime) -> datetime:
    """Watermark for the next `fetch(since=...)` call: the max timestamp already
    written to `incremental_dir`'s CSVs, or `seed_watermark` if no incremental
    file exists yet.

    Without this, a connector's `__main__` block re-fetching from a hardcoded
    seed watermark on every run would re-download and re-write an almost-total
    duplicate of the previous run's output each time — discovered exactly this
    way (data/raw/_platform/price/.../incremental/2026-08-05.csv vs.
    2026-08-07.csv were near-duplicates) when the connectors were run twice.
    Only incremental/ is scanned, never the (potentially very large) seed/
    file, since the seed's own watermark is already known statically.
    """
    incremental_dir = Path(incremental_dir)
    latest: datetime | None = None
    for csv_path in incremental_dir.glob("*.csv"):
        column = pd.read_csv(csv_path, usecols=[timestamp_column])[timestamp_column]
        file_max = pd.to_datetime(column, utc=True).max()
        if file_max is not pd.NaT and (latest is None or file_max > latest):
            latest = file_max.to_pydatetime()
    return latest if latest is not None else seed_watermark


def latest_watermark_from_db(
    repository: "ConnectorRecordRepository", tenant_id: str, source: str
) -> datetime | None:
    """DB-backed sibling of `latest_watermark` (INGEST-003): the max
    `fetched_at` already written for `(tenant_id, source)`, or `None` if
    nothing has been written yet -- the caller (`run_incremental`) is
    responsible for falling back to a seed watermark in that case, mirroring
    `latest_watermark`'s own "seed if nothing found" contract.

    Delegates the actual query to the repository (`ConnectorRecordRepository.
    latest_fetched_at`) rather than running SQL here -- this module has no
    storage-driver dependency, and shouldn't gain one just to resolve a
    watermark.
    """
    return repository.latest_fetched_at(tenant_id, source)


def run_incremental(
    connector: IngestionSource,
    incremental_dir: str | Path,
    timestamp_column: str,
    seed_watermark: datetime,
    *,
    tenant_id: str | None = None,
    repository: "ConnectorRecordRepository | None" = None,
    record_kind: str | None = None,
) -> None:
    """Shared `__main__`-block runner: resolve the watermark, fetch, print
    progress, and write any new rows.

    Two mutually exclusive output paths:
    - CSV (default, unchanged): when `tenant_id`/`repository` are not both
      supplied, behaves exactly as before -- watermark from `latest_watermark`
      (CSV-scanning), writes an incremental CSV. This is the standalone/
      no-tenant fallback for local/offline dev (README.md).
    - DB (INGEST-003): when both `tenant_id` and `repository` are supplied,
      watermark comes from `latest_watermark_from_db` instead, and rows are
      written via one of `repository`'s three `add_*_records` methods instead
      of a CSV. `record_kind` (one of `"price"`/`"onchain"`/`"sentiment"`)
      selects which method -- `run_incremental` is shared across all three
      connectors' differently-shaped tables, so it cannot infer the right
      method from `connector` alone; each `__main__` block declares its own
      table family explicitly here, the same way it already declares its own
      `timestamp_column`.

    DB mode also calls `repository.record_crawl_run` (INGEST-005) after every
    write attempt -- success, empty-but-successful (row_count=0, status=
    "completed", not silently skipped), and failure (status="failed", the
    write exception re-raised unchanged afterward so this doesn't alter
    `run_incremental`'s existing exception-propagation behavior).
    """
    if tenant_id is not None and repository is not None:
        since = latest_watermark_from_db(repository, tenant_id, connector.name)
        if since is None:
            since = seed_watermark
        result = connector.fetch(since=since)
        print(f"{connector.name}: fetched {len(result.records)} rows since {since}")
        if not result.is_empty():
            records = result.records.copy()
            records["fetched_at"] = result.fetched_at
            write_method = getattr(repository, f"add_{record_kind}_records")
            try:
                rows_written = write_method(tenant_id, connector.name, records)
            except Exception:
                repository.record_crawl_run(tenant_id, connector.name, since, result.fetched_at, 0, "failed")
                raise
            repository.record_crawl_run(
                tenant_id, connector.name, since, result.fetched_at, rows_written, "completed"
            )
            print(f"wrote {rows_written} rows to db for tenant {tenant_id}")
        else:
            repository.record_crawl_run(tenant_id, connector.name, since, result.fetched_at, 0, "completed")
            print("no new rows, nothing written")
        return

    since = latest_watermark(incremental_dir, timestamp_column, seed_watermark)
    result = connector.fetch(since=since)
    print(f"{connector.name}: fetched {len(result.records)} rows since {since}")
    if not result.is_empty():
        out_path = f"{incremental_dir}/{result.fetched_at:%Y-%m-%d}.csv"
        result.records.to_csv(out_path, index=False)
        print(f"wrote {out_path}")
    else:
        print("no new rows, nothing written")
