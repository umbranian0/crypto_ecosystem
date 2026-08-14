"""add row-level security

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-14 00:05:00.000000

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

    RS-002 binding decision (matches VS-013/GW-012's mechanism exactly, per
    the ticket's DRY check note): real Postgres RLS, not an application-side
    `WHERE tenant_id = ...` clause. `PostgresReportRepository`
    (postgres_repository.py) issues
    `SELECT set_config('app.tenant_id', :tenant_id, true)` as the first
    statement of every transaction, which is what
    `current_setting('app.tenant_id')` below reads.

    Postgres-only DDL (`ENABLE`/`FORCE ROW LEVEL SECURITY`, `CREATE POLICY`)
    has no SQLite equivalent -- guarded the same way migrations/env.py's own
    Postgres-only search_path/version_table_schema branch is, so a
    sqlite-target `alembic upgrade head` run stays a no-op here rather than
    failing.
    """
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE reports ENABLE ROW LEVEL SECURITY")
    # FORCE, not just ENABLE: the table-owning role (`naive_first`, the
    # migration-time role) is exempt from ENABLE-only RLS by default since
    # Postgres never applies row security to a table's owner unless FORCE is
    # also set. Without FORCE, the tenant-isolation test would pass for any
    # other role but silently not apply to the table owner itself.
    op.execute("ALTER TABLE reports FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON reports "
        "USING (tenant_id = current_setting('app.tenant_id')::text)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP POLICY tenant_isolation ON reports")
    op.execute("ALTER TABLE reports DISABLE ROW LEVEL SECURITY")
