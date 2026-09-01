"""convert price_ohlcv/onchain_metric/sentiment_score to TimescaleDB hypertables

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-25 00:00:00.000002

INGEST-002: hypertable-conversion idiom copied with attribution from
`validation-service`'s `migrations/versions/0004_convert_split_results_to_hypertable.py`
(INF-010) -- one hypertable per source family (solution-design.md 8.2),
partitioned on each table's own event-time column: `open_time`
(`price_ohlcv`), `timestamp` (`onchain_metric`), `created_utc`
(`sentiment_score`). `connector_credentials`/`crawl_runs` stay plain tables
(not per-source-family time series in the same sense, per 8.2's sketch).

Unlike INF-010's `split_results` (which needed a DROP/ADD CONSTRAINT
widened-PK fix in this same migration), 0001_create_ingestion_schema.py
already created these three tables with their partitioning column folded
into the primary key from the start -- no separate widening step needed
here, just the `create_hypertable` calls themselves.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_HYPERTABLES = (
    ("price_ohlcv", "open_time"),
    ("onchain_metric", "timestamp"),
    ("sentiment_score", "created_utc"),
)


def upgrade() -> None:
    """Upgrade schema.

    Postgres-only, same guard idiom as 0002_add_row_level_security.py.
    """
    if op.get_bind().dialect.name != "postgresql":
        return

    # The `timescale/timescaledb:latest-pg16` image ships the extension's
    # shared library, but the extension itself (its functions, e.g.
    # `create_hypertable`) still has to be created per-database -- copied
    # verbatim from INF-010's own comment, verified live against this
    # repo's running Compose Postgres container again for this ticket.
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    # `create_hypertable` lives in the `public` schema (where `CREATE
    # EXTENSION` above put it) -- migrations/env.py sets this connection's
    # search_path to `ingestion` only (not `ingestion, public`), so the call
    # must be schema-qualified or it resolves to nothing (same finding
    # INF-010 already made). `if_not_exists => TRUE` keeps this migration
    # idempotent-safe on re-run (INF-016's convention).
    for table, column in _HYPERTABLES:
        op.execute(
            f"SELECT public.create_hypertable("
            f"'ingestion.{table}', '{column}', "
            f"if_not_exists => TRUE, migrate_data => TRUE)"
        )


def downgrade() -> None:
    """Downgrade schema.

    TimescaleDB does not support cleanly converting a hypertable back into a
    plain table -- same documented, deliberate no-op-with-warning choice as
    INF-010's own downgrade(), copied with attribution rather than
    re-derived.
    """
    if op.get_bind().dialect.name != "postgresql":
        return
    print(
        "WARNING: downgrade of 0003_convert_to_hypertables is a no-op -- "
        "TimescaleDB does not support un-hypertabling a table. "
        "price_ohlcv/onchain_metric/sentiment_score remain hypertables. See "
        "this migration's downgrade() docstring for the manual rebuild "
        "procedure if one is ever needed."
    )
