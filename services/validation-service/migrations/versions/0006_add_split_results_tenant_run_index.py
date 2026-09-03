"""add composite index on split_results(tenant_id, run_id)

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-02 00:00:00.000000

VS-026 / DBOPT-003: the DBA's live `EXPLAIN (ANALYZE, BUFFERS)` against the
real `validation.split_results` hypertable (108 chunks, 552 rows) found
`PostgresSplitResultRepository.get_splits` (`SELECT * FROM split_results
WHERE run_id = :run_id AND tenant_id = :tenant_id ORDER BY split_index`)
doing an `Append` of 108 unindexed per-chunk `Seq Scan`s, with Planning Time
alone at ~130ms -- `split_results`' only index is its widened PK
`(id, test_start)` (0004_convert_split_results_to_hypertable.py) plus
TimescaleDB's own `test_start` partitioning index, neither of which helps a
`run_id`/`tenant_id` predicate since `test_start` isn't part of it, so chunk
exclusion cannot narrow anything here.

Composite index, issued once against the hypertable's root table (not a
per-chunk loop) -- on this platform's TimescaleDB version (2.29.1, confirmed
live), a root-level `CREATE INDEX` auto-propagates to every existing chunk
and to future chunks via the chunk template. This doubles as the RLS-
tenant_id index this table was also missing (mirrors 0005's
`ix_runs_tenant_id_created_at`, same `tenant_id`-leading rationale).

Postgres-only-guarded, same idiom as
0004_convert_split_results_to_hypertable.py/0005_add_runs_tenant_created_at_
index.py: `test_models.py::test_alembic_upgrade_head_creates_matching_schema`
runs `alembic upgrade head` (this migration included) against a real
`sqlite:///` DATABASE_URL, so this must no-op there, not error.

Pure schema/index change -- no application code touched (`get_splits`'s
signature, SQL text, and ordering responsibility are unaffected; only the
query plan changes).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "CREATE INDEX ix_split_results_tenant_run "
        "ON validation.split_results (tenant_id, run_id)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_split_results_tenant_run")