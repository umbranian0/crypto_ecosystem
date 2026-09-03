"""In-memory test doubles for `app.repositories.interfaces` (INGEST-003's
`ConnectorRecordRepository`, INGEST-004's `CredentialRepository`), shared
across the DB-write-path tests in each connector's own test file plus the
cross-tenant isolation tests in `test_base.py`/`test_reddit_sentiment.py` --
one fake per Protocol, not one copy-pasted per test module.

`INGEST-009` (revised, ADR-0005): `list_datasets`/`read_series`/
`latest_crawl_run` are exercised in `tests/test_datasets_router.py` against
this same fake rather than a live Postgres, per this service's existing
"fake the client, never require a live Postgres for these specific tests"
convention (`tests/test_credential_repository.py`'s own precedent). The
per-list `(event_time_column, default_field)` mapping in `_FAKE_TABLE_SPECS`
mirrors `postgres_repository._TABLE_SPECS` -- same three tables, same
defaults, so a router test written against this fake exercises the same
field-default contract the real repository documents in README.md. Records
appended here are expected to already carry the same column names as the
matching `app.models` field (e.g. `timestamp` for `onchain`, not the raw
connector `fetch()` shape's `date`) -- this fake does no column-mapping of
its own, unlike `postgres_repository._onchain_rows`.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.repositories.interfaces import (
    CredentialStatus,
    Credentials,
    CrawlRunSummary,
    DatasetSummary,
    SeriesResult,
)

# (attribute name on FakeConnectorRecordRepository, event-time column,
# default `field` column) -- byte-identical defaults to
# postgres_repository._TABLE_SPECS, documented in README.md.
_FAKE_TABLE_SPECS: tuple[tuple[str, str, str], ...] = (
    ("price", "open_time", "close"),
    ("onchain", "timestamp", "value"),
    ("sentiment", "created_utc", "reddit_sid_com"),
)


class FakeConnectorRecordRepository:
    """Records every write in `self.price`/`self.onchain`/`self.sentiment`,
    each a list of `(tenant_id, source, records)` tuples -- kept as separate
    per-table lists (not one flat list with a `kind` field) so a test can
    assert against exactly the table family it cares about, mirroring the
    Protocol's own one-method-per-table shape.
    """

    def __init__(self) -> None:
        self.price: list[tuple[str, str, pd.DataFrame]] = []
        self.onchain: list[tuple[str, str, pd.DataFrame]] = []
        self.sentiment: list[tuple[str, str, pd.DataFrame]] = []
        # (tenant_id, source, since_watermark, fetched_at, row_count, status,
        # rows_fetched_so_far, updated_at) -- the last two are INGEST-024's
        # additions, mutated in place by `record_crawl_progress` (never
        # appended to), mirroring `PostgresConnectorRecordRepository`'s own
        # UPDATE-not-INSERT semantics for that one call path.
        self.crawl_runs: list[
            tuple[str, str, datetime | None, datetime, int, str, int | None, datetime | None]
        ] = []

    def add_price_records(self, tenant_id: str, source: str, records: pd.DataFrame) -> int:
        self.price.append((tenant_id, source, records))
        return len(records)

    def add_onchain_records(self, tenant_id: str, source: str, records: pd.DataFrame) -> int:
        self.onchain.append((tenant_id, source, records))
        return len(records)

    def add_sentiment_records(self, tenant_id: str, source: str, records: pd.DataFrame) -> int:
        self.sentiment.append((tenant_id, source, records))
        return len(records)

    def latest_fetched_at(self, tenant_id: str, source: str) -> datetime | None:
        candidates = [
            records["fetched_at"].max()
            for (t, s, records) in (*self.price, *self.onchain, *self.sentiment)
            if t == tenant_id and s == source and not records.empty
        ]
        return max(candidates) if candidates else None

    def record_crawl_run(
        self,
        tenant_id: str,
        source: str,
        since_watermark: datetime | None,
        fetched_at: datetime,
        row_count: int,
        status: str,
    ) -> None:
        # INGEST-024: mirrors the real repository's own `updated_at=utcnow()`
        # addition on every insert -- `rows_fetched_so_far` starts `None`
        # (never a fabricated 0), only ever set by `record_crawl_progress`.
        now = datetime.now(timezone.utc)
        self.crawl_runs.append((tenant_id, source, since_watermark, fetched_at, row_count, status, None, now))

    def record_crawl_progress(self, tenant_id: str, source: str, rows_fetched_so_far: int) -> None:
        """INGEST-024: updates the most recent `status="running"` entry for
        `(tenant_id, source)` in place -- replaces the tuple at the same list
        index rather than appending, mirroring the real repository's
        UPDATE-not-INSERT semantics (the fake's list length must not grow per
        progress call). A no-op if no matching `"running"` entry exists.
        """
        candidate_indices = [
            i
            for i, run in enumerate(self.crawl_runs)
            if run[0] == tenant_id and run[1] == source and run[5] == "running"
        ]
        if not candidate_indices:
            return
        latest_index = max(candidate_indices, key=lambda i: self.crawl_runs[i][7])
        run = self.crawl_runs[latest_index]
        self.crawl_runs[latest_index] = (
            run[0],
            run[1],
            run[2],
            run[3],
            run[4],
            run[5],
            rows_fetched_so_far,
            datetime.now(timezone.utc),
        )

    def list_datasets(self, tenant_id: str) -> list[DatasetSummary]:
        summaries: list[DatasetSummary] = []
        for attribute, time_column, _default_field in _FAKE_TABLE_SPECS:
            per_source: dict[str, list[pd.DataFrame]] = {}
            for t, s, records in getattr(self, attribute):
                if t != tenant_id or records.empty:
                    continue
                per_source.setdefault(s, []).append(records)
            for source, frames in per_source.items():
                combined = pd.concat(frames)
                summaries.append(
                    DatasetSummary(
                        source=source,
                        earliest_timestamp=combined[time_column].min(),
                        latest_timestamp=combined[time_column].max(),
                        row_count=len(combined),
                    )
                )
        return summaries

    def read_series(
        self,
        tenant_id: str,
        source: str,
        start: datetime | None,
        end: datetime | None,
        field: str | None,
    ) -> SeriesResult | None:
        for attribute, time_column, default_field in _FAKE_TABLE_SPECS:
            frames = [
                records
                for (t, s, records) in getattr(self, attribute)
                if t == tenant_id and s == source and not records.empty
            ]
            if not frames:
                continue

            combined = pd.concat(frames).sort_values(time_column)
            field_name = field or default_field
            if field_name not in combined.columns:
                raise ValueError(f"unknown field {field_name!r} for source {source!r}")

            if start is not None:
                combined = combined[combined[time_column] >= start]
            if end is not None:
                combined = combined[combined[time_column] <= end]

            return SeriesResult(
                timestamps=list(combined[time_column]),
                values=[float(value) for value in combined[field_name]],
            )
        return None

    def latest_crawl_run(self, tenant_id: str, source: str) -> CrawlRunSummary | None:
        matches = [c for c in self.crawl_runs if c[0] == tenant_id and c[1] == source]
        if not matches:
            return None
        (
            _t,
            _s,
            _since_watermark,
            fetched_at,
            row_count,
            status,
            rows_fetched_so_far,
            updated_at,
        ) = max(matches, key=lambda c: c[3])
        return CrawlRunSummary(
            status=status,
            fetched_at=fetched_at,
            row_count=row_count,
            rows_fetched_so_far=rows_fetched_so_far,
            updated_at=updated_at,
        )


class FakeCredentialRepository:
    """In-memory test double for `app.repositories.interfaces.CredentialRepository`
    (INGEST-004). Stores ciphertext (via `app.credential_crypto.encrypt`) in
    `self._rows`, keyed by `(tenant_id, source)`, exactly like
    `PostgresCredentialRepository` stores ciphertext columns -- this is what
    lets a test read `self._rows` directly to assert the raw stored value is
    not the plaintext, the same "read the raw column" discipline the ticket
    requires of a real-Postgres test, without needing a live database.
    """

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], dict[str, bytes]] = {}
        self._updated_at: dict[tuple[str, str], datetime] = {}

    def get_credentials(self, tenant_id: str, source: str) -> Credentials | None:
        from app import credential_crypto

        row = self._rows.get((tenant_id, source))
        if row is None:
            return None
        return Credentials(
            client_id=credential_crypto.decrypt(row["client_id"]),
            client_secret=credential_crypto.decrypt(row["client_secret"]),
        )

    def set_credentials(self, tenant_id: str, source: str, **fields: str) -> None:
        from app import credential_crypto

        unknown = set(fields) - {"client_id", "client_secret"}
        if unknown:
            raise ValueError(f"Unknown credential field(s): {sorted(unknown)}")
        row = self._rows.setdefault((tenant_id, source), {})
        for name, value in fields.items():
            row[name] = credential_crypto.encrypt(value)
        self._updated_at[(tenant_id, source)] = datetime.now(timezone.utc)

    def get_credential_status(self, tenant_id: str, source: str) -> CredentialStatus:
        last_set_at = self._updated_at.get((tenant_id, source))
        return CredentialStatus(
            source=source, credential_set=last_set_at is not None, last_set_at=last_set_at
        )
