"""add price_ohlcv/onchain_metric/sentiment_score (tenant_id, source, fetched_at) composite indexes

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-02 00:00:00.000000

INGEST-018 (DBOPT-007, `docs/product/backlog-db-optimization.md`):
`PostgresConnectorRecordRepository.latest_fetched_at` runs, for each of
`price_ohlcv`/`onchain_metric`/`sentiment_score`, `SELECT max(fetched_at)
FROM <table> WHERE tenant_id = :tenant_id AND source = :source` -- called by
`connectors/base.py`'s `run_incremental` on every scheduled crawl, not just
interactively. `fetched_at` is not the hypertable partitioning column
(`open_time`/`timestamp`/`created_utc` are) and is not part of any existing
index, so TimescaleDB's chunk exclusion cannot help this query at all -- it
must visit every chunk that could contain the tenant/source's rows.

DBA evidence, live-verified: `price_ohlcv` scoped to the real 79,127-row
tenant showed a `Finalize Aggregate` over a 472-chunk `Append`
(`Buffers: shared hit=2907`), 24ms -- not slow yet, but running on every
incremental crawl for every tenant/source pair, with cost scaling with chunk
count (INGEST-016), not with how recent the tenant's last-fetched row is.

`fetched_at` trailing, not leading, is deliberate (same rationale as
`0005_add_crawl_runs_tenant_source_fetched_at_index.py`'s `crawl_runs`
index): with `(tenant_id, source, fetched_at)`, `MAX(fetched_at)` for a given
`(tenant_id, source)` becomes an index-only backward scan taking the first
row, not a full per-chunk aggregate scan.

Issued against each hypertable's root table -- same TimescaleDB
root-to-existing-chunk index propagation this platform's version applies, as
`VS-026` (`validation-service`) already confirmed live for
`validation.split_results`; independently re-verified live for this
migration too rather than assumed from VS-026's own verification (see this
ticket's Outcome notes in `docs/tickets/INGEST-018.md`).

Same three tables, same order, as `_TABLE_SPECS`
(`src/app/repositories/postgres_repository.py`) and `_HYPERTABLES`
(`0003_convert_to_hypertables.py` / `0004_retune_hypertable_chunk_intervals.py`)
already iterate -- not a fourth ad hoc table list.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Same three-table order as _TABLE_SPECS (postgres_repository.py) /
# _HYPERTABLES (0003/0004) -- (table, index_name) pairs, fetched_at trailing.
_INDEXES = (
    ("price_ohlcv", "ix_price_ohlcv_tenant_source_fetched_at"),
    ("onchain_metric", "ix_onchain_metric_tenant_source_fetched_at"),
    ("sentiment_score", "ix_sentiment_score_tenant_source_fetched_at"),
)


def upgrade() -> None:
    """Upgrade schema.

    Postgres-only, same guard idiom as 0002_add_row_level_security.py /
    0003_convert_to_hypertables.py / 0004_retune_hypertable_chunk_intervals.py
    / 0005_add_crawl_runs_tenant_source_fetched_at_index.py. Adds a composite
    btree index on (tenant_id, source, fetched_at) -- fetched_at trailing --
    to each of the three hypertables' root tables, serving
    `latest_fetched_at`'s WHERE tenant_id = :t AND source = :s / MAX(fetched_at)
    query shape.
    """
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, index_name in _INDEXES:
        op.execute(
            f"CREATE INDEX {index_name} "
            f"ON ingestion.{table} (tenant_id, source, fetched_at)"
        )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    for _, index_name in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS ingestion.{index_name}")