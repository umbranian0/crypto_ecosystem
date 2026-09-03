"""INGEST-003: Postgres-backed implementation of `interfaces.ConnectorRecordRepository`,
writing `connectors/*.py`'s `FetchResult.records` into the `ingestion` schema's
`price_ohlcv`/`onchain_metric`/`sentiment_score` tables (`INGEST-002`'s `app.models`).

Tenant scoping (LC-010, matching `validation-service`'s `postgres_repository.py`
precedent byte-for-byte): every transaction opened here issues
`SELECT set_config('app.tenant_id', :tenant_id, true)` as its first statement,
via `naive_first_common.db.tenant_scope` -- not a local reimplementation of that
statement. This is what makes `INGEST-002`'s RLS policies on these three tables
actually scope queries/writes to the calling tenant; the `.where(...)` clauses
below are retained anyway as defense in depth, not as the enforcement mechanism.

Column mapping (DataFrame -> model), one private function per table so each
connector's actual `fetch()` output shape (read from `connectors/*.py`, not
guessed) is translated in exactly one place:
- `price_ohlcv`: `BinancePriceConnector.fetch`'s columns, minus `symbol` (not a
  `price_ohlcv` column -- `source` already encodes the symbol/interval pair).
- `onchain_metric`: `BlockchainInfoConnector.fetch`'s columns (`timestamp_unix`,
  `date`, and one value column named after the chart, e.g. `hash-rate`) --
  the value column's name is not known ahead of time, so it's whichever column
  isn't `timestamp_unix`/`date`/`fetched_at`.
- `sentiment_score`: `RedditSentimentConnector.fetch`'s columns.

Every `add_*_records` method expects a `fetched_at` column already present on
`records` (added by `connectors/base.py`'s `run_incremental` from
`FetchResult.fetched_at` before calling this repository) -- this keeps this
ticket's `(tenant_id, source, records) -> int` method signatures exactly as
specified rather than growing a fourth `fetched_at` parameter.

`record_crawl_run` (INGEST-005) writes one `crawl_runs` row per `fetch()`
outcome (`id` generated here via `uuid.uuid4().hex`, matching
`validation-service/src/app/models.py`'s own `default=lambda: uuid.uuid4().hex`
precedent, since `CrawlRun.id` itself carries no column default) -- same
`_tenant_scoped_session` helper as every other method on this class, not a
new tenant-scoping mechanism.

`PostgresCredentialRepository` (INGEST-004) is `connector_credentials`'s own
implementation, kept in this same module for cohesion with
`PostgresConnectorRecordRepository` (both wrap the same `Engine`/tenant-scoped-
session helpers below) -- see `interfaces.CredentialRepository` for the
contract. Encryption/decryption is delegated entirely to
`app.credential_crypto` (`INGEST-011`); this module never handles a plaintext
credential value except to pass it straight into `encrypt`.

`get_credential_status` (`INGEST-012`) queries only the `updated_at` column
-- `client_id`/`client_secret` are never selected, so there is no ciphertext
in hand to (mis)decrypt in the first place, not just a "decrypt then discard
the plaintext" discipline.

`INGEST-009` (revised, ADR-0005): `_TABLE_SPECS` is the single place that
maps each of the three tables to its own event-time column and default
`field` (documented, per solution-design.md 8.3, in README.md's field-default
table) -- `list_datasets`/`read_series` both iterate it instead of each
hand-rolling its own "which table, which column" logic, and it is the same
three-model tuple `latest_fetched_at` above already iterates by hand.

`INGEST-019` (DBOPT-009): `list_datasets` now queries three
`<table>_daily_source_summary` materialized views (migration 0007) instead
of the raw hypertables -- cheap, but only as current as the last scheduled
refresh (see README.md's documented staleness window). These are plain
Postgres materialized views refreshed on a TimescaleDB-scheduled job
(`add_job`, every 5 minutes), not true TimescaleDB continuous aggregates as
originally designed -- TimescaleDB refuses to create a continuous aggregate
on a hypertable with row-level security enabled, see migration 0007's own
docstring for the full live-discovered blocker and the substituted design.
The view name is derived from `spec.model.__tablename__` rather than a
fourth ad hoc table list, so `_TABLE_SPECS` stays the single source of
truth for table order/names, per this ticket's own DRY check. These views
are plain materialized views, not hypertables with `FORCE ROW LEVEL
SECURITY` -- they inherit no RLS of their own, so the `WHERE tenant_id =
:tenant_id` predicate in `list_datasets`' raw SQL is the *only*
tenant-isolation mechanism for this one method, not defense-in-depth on top
of RLS like every other method on this class.
"""

from __future__ import annotations

import dataclasses
import math
import uuid
from datetime import datetime

import pandas as pd
from sqlalchemy import Engine, select, func, text
from sqlalchemy.orm import Session

from app import credential_crypto
from app.models import Base, ConnectorCredentials, CrawlRun, OnchainMetric, PriceOhlcv, SentimentScore
from app.repositories.interfaces import (
    CredentialStatus,
    Credentials,
    CrawlRunSummary,
    DatasetSummary,
    SeriesResult,
)
from naive_first_common.db import build_engine
from naive_first_common.db import tenant_scope as _tenant_scope


def _tenant_scoped_session(engine: Engine, tenant_id: str) -> Session:
    session = Session(engine)
    _tenant_scope(session, tenant_id)
    return session


@dataclasses.dataclass(frozen=True)
class _TableSpec:
    model: type
    event_time_column: str
    default_field: str


# Field defaults per solution-design.md 8.3, flagged there (open question #2)
# for product confirmation -- documented again in README.md, not silently
# chosen with no trace.
_TABLE_SPECS: tuple[_TableSpec, ...] = (
    _TableSpec(model=PriceOhlcv, event_time_column="open_time", default_field="close"),
    _TableSpec(model=OnchainMetric, event_time_column="timestamp", default_field="value"),
    _TableSpec(model=SentimentScore, event_time_column="created_utc", default_field="reddit_sid_com"),
)


def _none_if_missing(value: object) -> object | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _price_rows(tenant_id: str, source: str, records: pd.DataFrame) -> list[PriceOhlcv]:
    return [
        PriceOhlcv(
            tenant_id=tenant_id,
            source=source,
            open_time=row["open_time"],
            fetched_at=row["fetched_at"],
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            close_time=row["close_time"],
            quote_volume=_none_if_missing(row.get("quote_volume")),
            trades=_none_if_missing(row.get("trades")),
            taker_buy_base=_none_if_missing(row.get("taker_buy_base")),
            taker_buy_quote=_none_if_missing(row.get("taker_buy_quote")),
        )
        for row in records.to_dict("records")
    ]


def _onchain_value_column(records: pd.DataFrame) -> str:
    return next(c for c in records.columns if c not in ("timestamp_unix", "date", "fetched_at"))


def _onchain_rows(tenant_id: str, source: str, records: pd.DataFrame) -> list[OnchainMetric]:
    value_column = _onchain_value_column(records)
    return [
        OnchainMetric(
            tenant_id=tenant_id,
            source=source,
            timestamp=row["date"],
            fetched_at=row["fetched_at"],
            value=float(row[value_column]),
        )
        for row in records.to_dict("records")
    ]


def _sentiment_rows(tenant_id: str, source: str, records: pd.DataFrame) -> list[SentimentScore]:
    return [
        SentimentScore(
            tenant_id=tenant_id,
            source=source,
            created_utc=row["created_utc"],
            fetched_at=row["fetched_at"],
            subreddit=_none_if_missing(row.get("subreddit")),
            post_id=row["post_id"],
            title=_none_if_missing(row.get("title")),
            score=_none_if_missing(row.get("score")),
            num_comments=_none_if_missing(row.get("num_comments")),
            reddit_sid_pos=float(row["reddit_sid_pos"]),
            reddit_sid_neg=float(row["reddit_sid_neg"]),
            reddit_sid_neu=float(row["reddit_sid_neu"]),
            reddit_sid_com=float(row["reddit_sid_com"]),
        )
        for row in records.to_dict("records")
    ]


class PostgresConnectorRecordRepository:
    """Postgres implementation of `ConnectorRecordRepository` (INGEST-003)."""

    def __init__(self, url: str, engine: Engine | None = None) -> None:
        self._engine = engine if engine is not None else build_engine(url, Base)

    def add_price_records(self, tenant_id: str, source: str, records: pd.DataFrame) -> int:
        if records.empty:
            return 0
        rows = _price_rows(tenant_id, source, records)
        with _tenant_scoped_session(self._engine, tenant_id) as session:
            session.add_all(rows)
            session.commit()
        return len(rows)

    def add_onchain_records(self, tenant_id: str, source: str, records: pd.DataFrame) -> int:
        if records.empty:
            return 0
        rows = _onchain_rows(tenant_id, source, records)
        with _tenant_scoped_session(self._engine, tenant_id) as session:
            session.add_all(rows)
            session.commit()
        return len(rows)

    def add_sentiment_records(self, tenant_id: str, source: str, records: pd.DataFrame) -> int:
        if records.empty:
            return 0
        rows = _sentiment_rows(tenant_id, source, records)
        with _tenant_scoped_session(self._engine, tenant_id) as session:
            session.add_all(rows)
            session.commit()
        return len(rows)

    def latest_fetched_at(self, tenant_id: str, source: str) -> datetime | None:
        with _tenant_scoped_session(self._engine, tenant_id) as session:
            candidates = []
            for model in (PriceOhlcv, OnchainMetric, SentimentScore):
                max_value = session.execute(
                    select(func.max(model.fetched_at)).where(
                        model.tenant_id == tenant_id, model.source == source
                    )
                ).scalar_one_or_none()
                if max_value is not None:
                    candidates.append(max_value)
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
        row = CrawlRun(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            source=source,
            since_watermark=since_watermark,
            fetched_at=fetched_at,
            row_count=row_count,
            status=status,
        )
        with _tenant_scoped_session(self._engine, tenant_id) as session:
            session.add(row)
            session.commit()

    def list_datasets(self, tenant_id: str) -> list[DatasetSummary]:
        # INGEST-019 (DBOPT-009): reads the `<table>_daily_source_summary`
        # materialized views (migration 0007), not the raw hypertables --
        # a second-level GROUP BY source over the small materialized rows,
        # not a full per-tenant, all-chunks scan. These are plain Postgres
        # materialized views (no FORCE ROW LEVEL SECURITY, unlike the raw
        # hypertables), so the `WHERE tenant_id = :tenant_id` predicate
        # below is the *only* tenant-isolation mechanism for this method --
        # RLS provides no defense-in-depth here the way it does elsewhere on
        # this class.
        summaries: list[DatasetSummary] = []
        with _tenant_scoped_session(self._engine, tenant_id) as session:
            for spec in _TABLE_SPECS:
                cagg_name = f"{spec.model.__tablename__}_daily_source_summary"
                rows = session.execute(
                    text(
                        f"SELECT source, min(bucket_min), max(bucket_max), sum(bucket_count) "
                        f"FROM ingestion.{cagg_name} "
                        f"WHERE tenant_id = :tenant_id "
                        f"GROUP BY source"
                    ),
                    {"tenant_id": tenant_id},
                ).all()
                summaries.extend(
                    DatasetSummary(
                        source=source,
                        earliest_timestamp=earliest,
                        latest_timestamp=latest,
                        row_count=row_count,
                    )
                    for source, earliest, latest, row_count in rows
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
        with _tenant_scoped_session(self._engine, tenant_id) as session:
            for spec in _TABLE_SPECS:
                model = spec.model
                exists = session.execute(
                    select(model.tenant_id)
                    .where(model.tenant_id == tenant_id, model.source == source)
                    .limit(1)
                ).first()
                if exists is None:
                    continue

                field_name = field or spec.default_field
                if field_name not in model.__table__.columns:
                    raise ValueError(f"unknown field {field_name!r} for source {source!r}")

                time_column = getattr(model, spec.event_time_column)
                value_column = getattr(model, field_name)
                conditions = [model.tenant_id == tenant_id, model.source == source]
                if start is not None:
                    conditions.append(time_column >= start)
                if end is not None:
                    conditions.append(time_column <= end)

                rows = session.execute(
                    select(time_column, value_column).where(*conditions).order_by(time_column)
                ).all()
                return SeriesResult(
                    timestamps=[timestamp for timestamp, _ in rows],
                    values=[float(value) for _, value in rows],
                )
        return None

    def latest_crawl_run(self, tenant_id: str, source: str) -> CrawlRunSummary | None:
        with _tenant_scoped_session(self._engine, tenant_id) as session:
            row = (
                session.execute(
                    select(CrawlRun)
                    .where(CrawlRun.tenant_id == tenant_id, CrawlRun.source == source)
                    .order_by(CrawlRun.fetched_at.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            if row is None:
                return None
            return CrawlRunSummary(status=row.status, fetched_at=row.fetched_at, row_count=row.row_count)


class PostgresCredentialRepository:
    """Postgres implementation of `CredentialRepository` (INGEST-004,
    ADR-0004). `client_id`/`client_secret` are the only two fields
    `connector_credentials` currently has (`app.models.ConnectorCredentials`);
    `set_credentials` accepts them as `**fields` per the ticket's own method
    signature, but every value passed through is required to be a known
    column name.
    """

    def __init__(self, url: str, engine: Engine | None = None) -> None:
        self._engine = engine if engine is not None else build_engine(url, Base)

    def get_credentials(self, tenant_id: str, source: str) -> Credentials | None:
        with _tenant_scoped_session(self._engine, tenant_id) as session:
            row = session.execute(
                select(ConnectorCredentials).where(
                    ConnectorCredentials.tenant_id == tenant_id,
                    ConnectorCredentials.source == source,
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return Credentials(
                client_id=credential_crypto.decrypt(row.client_id),
                client_secret=credential_crypto.decrypt(row.client_secret),
            )

    def set_credentials(self, tenant_id: str, source: str, **fields: str) -> None:
        unknown = set(fields) - {"client_id", "client_secret"}
        if unknown:
            raise ValueError(f"Unknown credential field(s): {sorted(unknown)}")
        with _tenant_scoped_session(self._engine, tenant_id) as session:
            row = session.execute(
                select(ConnectorCredentials).where(
                    ConnectorCredentials.tenant_id == tenant_id,
                    ConnectorCredentials.source == source,
                )
            ).scalar_one_or_none()
            now = datetime.now().astimezone()
            if row is None:
                row = ConnectorCredentials(
                    tenant_id=tenant_id,
                    source=source,
                    client_id=credential_crypto.encrypt(fields["client_id"]),
                    client_secret=credential_crypto.encrypt(fields["client_secret"]),
                    updated_at=now,
                )
                session.add(row)
            else:
                if "client_id" in fields:
                    row.client_id = credential_crypto.encrypt(fields["client_id"])
                if "client_secret" in fields:
                    row.client_secret = credential_crypto.encrypt(fields["client_secret"])
                row.updated_at = now
            session.commit()

    def get_credential_status(self, tenant_id: str, source: str) -> CredentialStatus:
        with _tenant_scoped_session(self._engine, tenant_id) as session:
            updated_at = session.execute(
                select(ConnectorCredentials.updated_at).where(
                    ConnectorCredentials.tenant_id == tenant_id,
                    ConnectorCredentials.source == source,
                )
            ).scalar_one_or_none()
        return CredentialStatus(
            source=source, credential_set=updated_at is not None, last_set_at=updated_at
        )
