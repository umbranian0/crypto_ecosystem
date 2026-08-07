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

import pandas as pd


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
