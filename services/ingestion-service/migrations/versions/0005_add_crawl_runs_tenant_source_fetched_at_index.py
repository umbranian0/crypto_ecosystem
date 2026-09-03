"""add crawl_runs (tenant_id, source, fetched_at desc) composite index

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-02 00:00:00.000000

INGEST-017 (DBOPT-006, `docs/product/backlog-db-optimization.md`):
`PostgresConnectorRecordRepository.latest_crawl_run` runs `SELECT ... FROM
crawl_runs WHERE tenant_id = :tenant_id AND source = :source ORDER BY
fetched_at DESC LIMIT 1`, backing the connector/dataset status surface.
`crawl_runs`' only index today is the PK on `id` -- no index supports this
filter+sort+limit shape, the same shape DBOPT-002 (`list_runs`) already had an
index added for.

DBA evidence is explicitly code-inferred, not live-EXPLAIN-verified: the real
table has only 8 rows this session, too few to show a measurable scan-cost
difference either way. This migration is evaluated on structural correctness
and planner-usability (`SET enable_seqscan = off` proof), not a timing delta
-- see this ticket's own Test/Review acceptance criteria.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Postgres-only, same guard idiom as 0002_add_row_level_security.py /
    0004_retune_hypertable_chunk_intervals.py. Adds a plain (non-hypertable)
    composite b-tree index serving `latest_crawl_run`'s
    `WHERE tenant_id = :t AND source = :s ORDER BY fetched_at DESC LIMIT 1`
    query, and doubling as the RLS `tenant_id`-index this table was also
    missing.
    """
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "CREATE INDEX ix_crawl_runs_tenant_source_fetched_at "
        "ON ingestion.crawl_runs (tenant_id, source, fetched_at DESC)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ingestion.ix_crawl_runs_tenant_source_fetched_at")