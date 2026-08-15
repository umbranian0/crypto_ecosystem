"""add row-level security

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-14 00:00:01.000000

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

    Policy authored now even though enforcement against real non-superuser
    credentials is a later infra ticket (ticket Design section, mirroring
    validation-service's VS-013/INF-014 precedent) -- FORCE ROW LEVEL
    SECURITY, not just ENABLE, for the same reason validation-service's own
    0002 migration uses FORCE: this sprint's infra has no separate non-owner
    app role, so ENABLE-only RLS would silently not apply to the app's own
    connection.

    Postgres-only DDL -- no SQLite equivalent, same guard as
    migrations/env.py's own Postgres-only search_path/version_table_schema
    branch and validation-service's own 0002 migration.
    """
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in ("fee_schedules", "slippage_models", "simulation_configs"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (tenant_id = current_setting('app.tenant_id')::text)"
        )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in ("simulation_configs", "slippage_models", "fee_schedules"):
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
