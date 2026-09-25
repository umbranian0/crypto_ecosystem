"""create operator_audit_log (ADMIN-002-01)

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-25 00:00:00.000000

Plain, unguarded `op.create_table(...)` -- runs against both sqlite and
postgres, mirroring `0001_create_identity_schema.py`'s own unguarded
`create_table` calls. `env.py` already sets `search_path=identity` for
Postgres runs, so no explicit `schema=` kwarg is needed here either, same
precedent as `0001`.

**Deliberately no RLS on this table.** `operator_audit_log` is an
operator-only, cross-tenant resource, never queried under a tenant-scoped
session -- unlike `tenants`/`users`/`api_keys`, which are both operator- and
tenant-facing in different code paths. Every repository method on this table
(`OperatorAuditLogRepository.record`/`list_entries`, both storage backends)
is deliberately tenant-agnostic and never calls `_set_tenant_scope`, the same
category as `list_tenants()`/`tenant_exists()` -- so enabling RLS here would
add a policy that is never actually exercised from a tenant angle. This is a
considered, disclosed Tech Lead design call (ticket ADMIN-002-01's Design
section), not an oversight.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'operator_audit_log',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('target_tenant_id', sa.String(), nullable=True),
        sa.Column('correlation_id', sa.String(), nullable=False),
        sa.Column('at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['target_tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('operator_audit_log')
