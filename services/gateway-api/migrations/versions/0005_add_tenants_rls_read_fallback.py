"""add tenant-agnostic read fallback to tenants RLS policy (SETUP-001)

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-08 00:00:00.000000

`PostgresTenantRepository.tenant_exists()` (SETUP-001, backing `GET
/setup/status`) is a third documented tenant-agnostic read, alongside
`get_by_hash`/`get_user_by_email` -- a fresh-install check must work with
`app.tenant_id` unset, since there is by definition no tenant to scope to
yet. Unlike those two, this one reads `tenants` itself, whose existing
`0002_add_identity_rls.py` policy has no such fallback: `create_tenant` was
the only existing tenant-agnostic-in-name-only method on this table (it
scopes to its own newly-generated id *before* inserting, so the strict
`id = current_setting('app.tenant_id', true)` clause was previously always
satisfiable without a fallback). `tenant_exists()` does not scope to any one
`id` at all, so it needs the same "or unset" read fallback `users`/`api_keys`
already carry.

This is a read-only (`USING`) relaxation -- the `WITH CHECK` clause governing
INSERT/UPDATE on `tenants` is left exactly as strict as `0002` made it
(`create_tenant` still must scope to its own id first); no write path is
widened by this migration.

`DROP POLICY` + `CREATE POLICY` rather than `ALTER POLICY`: Postgres's
`ALTER POLICY` cannot change a policy's `USING`/`WITH CHECK` expressions in
one statement across command forms portably here, and this repo's `0002`
precedent already establishes drop-then-recreate as the pattern for a
policy-shape change (see `downgrade()` below, symmetric with `0002`'s own).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_POLICY_NAME = "tenant_isolation"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # This service's own tests/test_models.py runs `alembic upgrade
        # head` against a real sqlite file as a schema-parity check -- that
        # run must stay a no-op here rather than error, same guard every
        # prior Postgres-only migration in this service uses.
        return

    op.execute(f"DROP POLICY IF EXISTS {_POLICY_NAME} ON tenants")
    op.execute(
        f"CREATE POLICY {_POLICY_NAME} ON tenants "
        "USING ("
        "  id = current_setting('app.tenant_id', true)"
        "  OR NULLIF(current_setting('app.tenant_id', true), '') IS NULL"
        ") "
        "WITH CHECK (id = current_setting('app.tenant_id', true))"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(f"DROP POLICY IF EXISTS {_POLICY_NAME} ON tenants")
    op.execute(
        f"CREATE POLICY {_POLICY_NAME} ON tenants "
        "USING (id = current_setting('app.tenant_id', true)) "
        "WITH CHECK (id = current_setting('app.tenant_id', true))"
    )
