"""widen ix_split_results_tenant_run to (tenant_id, run_id, split_index)

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-27 00:00:00.000000

DBOPT-012: widens 0006's ix_split_results_tenant_run from (tenant_id, run_id)
to (tenant_id, run_id, split_index) so PostgresSplitResultRepository.get_splits'
`ORDER BY split_index` is served by the index directly, eliminating the
Sort node a live EXPLAIN found on top of the narrower index (see
docs/product/backlog-db-optimization.md's DBOPT-012 entry for the full
evidence). Combined with DBOPT-011's LIMIT/OFFSET, this also supports an
efficient bounded/ordered page read without a full re-scan.

Widen-in-place: same index name reused (not a new index alongside the
old one) via DROP INDEX; CREATE INDEX, issued against the hypertable
root -- same auto-propagation mechanism 0006 already established (a
root-level CREATE INDEX on this platform's TimescaleDB version, 2.29.1,
propagates to every existing chunk and to future chunks via the chunk
template). No other query in this repository uses (tenant_id, run_id)
without also implicitly wanting split_index order (add_splits is an
INSERT, unaffected by index column order) -- backward-compatible 1:1
replacement.

Does NOT touch FORCE ROW LEVEL SECURITY on split_results
(0002_add_row_level_security.py) -- this is DDL against the hypertable
root, not a data-path RLS bypass; runs under FORCE ROW LEVEL SECURITY
exactly as 0006's original index creation already did. DBOPT-008's
BLOCKED compression finding (ALTER TABLE ... SET (timescaledb.compress,
...) rejects any RLS-enabled table) does not apply to a plain CREATE
INDEX statement.

Postgres-only-guarded, same idiom as 0004/0005/0006:
test_models.py::test_alembic_upgrade_head_creates_matching_schema runs
`alembic upgrade head` (this migration included) against a real
sqlite:// DATABASE_URL, so this must no-op there, not error.

Pure schema/index change -- no application code touched (get_splits'
signature, SQL text structure, and ordering responsibility are
unaffected by this migration; DBOPT-011 is the separate ticket that
changes get_splits' own code).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_split_results_tenant_run")
    op.execute(
        "CREATE INDEX ix_split_results_tenant_run "
        "ON validation.split_results (tenant_id, run_id, split_index)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_split_results_tenant_run")
    op.execute(
        "CREATE INDEX ix_split_results_tenant_run "
        "ON validation.split_results (tenant_id, run_id)"
    )
