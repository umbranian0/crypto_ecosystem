"""add row-level security

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    VS-013 binding decision (grooming #7): real Postgres RLS, not an
    application-side `WHERE tenant_id = ...` clause -- matches GW-012's
    mechanism. `PostgresValidationRunRepository`/`PostgresSplitResultRepository`
    (postgres_repository.py) issue `SET LOCAL app.tenant_id = :tenant_id` as
    the first statement of every transaction, which is what
    `current_setting('app.tenant_id')` below reads.

    Postgres-only DDL (`ENABLE`/`FORCE ROW LEVEL SECURITY`, `CREATE POLICY`)
    has no SQLite equivalent -- test_models.py's
    test_alembic_upgrade_head_creates_matching_schema runs `alembic upgrade
    head` (this migration included) against a real sqlite:/// DATABASE_URL,
    so this is a no-op there, same guard as migrations/env.py's own
    Postgres-only search_path/version_table_schema branch.
    """
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE runs ENABLE ROW LEVEL SECURITY")
    # FORCE, not just ENABLE: there is no separate non-owner app role in this
    # sprint's infra (INF-001) -- the app connects as the same `naive_first`
    # role that owns these tables, and Postgres exempts table owners from
    # ENABLE-only RLS by default. Without FORCE, the tenant-isolation test
    # would pass for any other role but silently not apply to the app itself.
    op.execute("ALTER TABLE runs FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON runs "
        "USING (tenant_id = current_setting('app.tenant_id')::text)"
    )
    op.execute("ALTER TABLE split_results ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE split_results FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON split_results "
        "USING (tenant_id = current_setting('app.tenant_id')::text)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP POLICY tenant_isolation ON split_results")
    op.execute("ALTER TABLE split_results DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY tenant_isolation ON runs")
    op.execute("ALTER TABLE runs DISABLE ROW LEVEL SECURITY")
