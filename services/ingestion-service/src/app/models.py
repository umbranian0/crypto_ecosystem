"""SQLAlchemy 2.0 declarative models for the `ingestion` schema: `PriceOhlcv`,
`OnchainMetric`, `SentimentScore`, `ConnectorCredentials`, `CrawlRun`.

Field list is solution-design.md section 8.2's schema sketch, column-for-
column (INGEST-002's own AC). Defined once here and imported by the Alembic
migration (migrations/versions/0001_create_ingestion_schema.py) so the
schema has a single source of truth, mirroring validation-service's own
models.py -> migrations/env.py wiring (same precedent gateway-api/
reporting-service/economic-service already follow).

This module only defines the schema -- it does not read/write these tables
(that's INGEST-003/INGEST-004/INGEST-005's Repository-pattern code, per this
ticket's Design section) and is not imported by any other service (this
schema's own grep-verified boundary, implementation-plan.md section 2).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PriceOhlcv(Base):
    """source: binance_price connector (solution-design.md 8.2)."""

    __tablename__ = "price_ohlcv"

    tenant_id: Mapped[str] = mapped_column(String, primary_key=True)
    # e.g. 'binance_btcusdt_1h' -- room for more than one price feed later.
    source: Mapped[str] = mapped_column(String, primary_key=True)
    # The record's own time (kline open) -- also the hypertable partitioning
    # column (0003_convert_to_hypertables.py), widened into this composite PK
    # per the same TimescaleDB constraint INF-010 already hit.
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    # Causal-lag column, connectors/base.py's FetchResult.fetched_at.
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    close_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quote_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    trades: Mapped[float | None] = mapped_column(Float, nullable=True)
    taker_buy_base: Mapped[float | None] = mapped_column(Float, nullable=True)
    taker_buy_quote: Mapped[float | None] = mapped_column(Float, nullable=True)


class OnchainMetric(Base):
    """source: blockchain_onchain connector, parameterized per metric
    (solution-design.md 8.2)."""

    __tablename__ = "onchain_metric"

    tenant_id: Mapped[str] = mapped_column(String, primary_key=True)
    # e.g. 'hash_rate', 'n_unique_addresses'.
    source: Mapped[str] = mapped_column(String, primary_key=True)
    # Hypertable partitioning column (0003_convert_to_hypertables.py).
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)


class SentimentScore(Base):
    """source: reddit_vader_sentiment connector (solution-design.md 8.2)."""

    __tablename__ = "sentiment_score"

    tenant_id: Mapped[str] = mapped_column(String, primary_key=True)
    # 'reddit_vader_sentiment' today, room for a second sentiment source
    # later.
    source: Mapped[str] = mapped_column(String, primary_key=True)
    # Hypertable partitioning column (0003_convert_to_hypertables.py).
    created_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    subreddit: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Part of the composite PK per solution-design.md 8.2 ("created_utc alone
    # is not unique across posts in the same second") -- PK membership makes
    # this column NOT NULL, unlike subreddit/title above/below.
    post_id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_comments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reddit_sid_pos: Mapped[float] = mapped_column(Float, nullable=False)
    reddit_sid_neg: Mapped[float] = mapped_column(Float, nullable=False)
    reddit_sid_neu: Mapped[float] = mapped_column(Float, nullable=False)
    reddit_sid_com: Mapped[float] = mapped_column(Float, nullable=False)


class ConnectorCredentials(Base):
    """Decision #3 / solution-design.md 8.5 -- ciphertext columns only, never
    plaintext at rest. `INGEST-011` writes the actual encrypt/decrypt code;
    this ticket only needs the column types right (`bytea` via
    `LargeBinary`)."""

    __tablename__ = "connector_credentials"

    tenant_id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, primary_key=True)
    client_id: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    client_secret: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # Backs 8.5's read path ("credential is set" + timestamp, never the
    # plaintext/ciphertext itself).
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CrawlRun(Base):
    """One execution of a connector appending rows to a dataset
    (solution-design.md 8.1/8.2, unchanged from the backlog's design)."""

    __tablename__ = "crawl_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    since_watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    # INGEST-024: mid-fetch progress checkpoint count, updated in place by
    # `record_crawl_progress` rather than written via a new insert per
    # checkpoint (see postgres_repository.py). Nullable -- a source that
    # never reports progress (blockchain.info, or before Binance's first
    # page completes) has no value here, never a fabricated 0.
    rows_fetched_so_far: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # "Last touched" timestamp, distinct from `fetched_at` (which keeps its
    # existing "crawl outcome time"/ordering role, unchanged by this ticket).
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
