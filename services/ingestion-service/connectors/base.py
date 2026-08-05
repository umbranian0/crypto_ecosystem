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
