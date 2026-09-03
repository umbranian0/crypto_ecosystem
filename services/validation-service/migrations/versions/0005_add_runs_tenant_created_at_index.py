"""add composite index on runs(tenant_id, created_at desc)

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-02 00:00:00.000000

VS-025 / DBOPT-002: the DBA's live `EXPLAIN (ANALYZE, BUFFERS)` against the
real 1,928-row `validation.runs` table found both `list_runs` (`SELECT * ...
WHERE tenant_id = :tenant_id ORDER BY created_at DESC LIMIT ... OFFSET ...`)
and `count_runs` (`SELECT count(*) ... WHERE tenant_id = :tenant_id`) doing a
full `Seq Scan` -- `runs`' only index was the PK on `id`, and the RLS policy's
`USING (tenant_id = current_setting('app.tenant_id'))` clause has no index to
use either.

Composite index, `tenant_id` leading (serves the equality filter both
`list_runs`/`count_runs`/the RLS policy all share) and `created_at DESC`
trailing (serves `list_runs`'s `ORDER BY created_at DESC` directly from the
index, no separate `Sort` node needed).

Postgres-only-guarded, same idiom as
0002_add_row_level_security.py/0004_convert_split_results_to_hypertable.py:
`test_models.py::test_alembic_upgrade_head_creates_matching_schema` runs
`alembic upgrade head` (this migration included) against a real `sqlite:///`
DATABASE_URL, so this must no-op there, not error.

Pure schema/index change -- no application code touched (`list_runs`/
`count_runs`'s signatures, SQL text, and ordering responsibility are
unaffected; only the query plan changes).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "CREATE INDEX ix_runs_tenant_id_created_at "
        "ON validation.runs (tenant_id, created_at DESC)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_runs_tenant_id_created_at")