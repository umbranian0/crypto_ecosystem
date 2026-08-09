"""add row-level security to identity.tenants/users/api_keys (GW-012)

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-05 00:00:00.000000

Postgres-only (guarded on dialect, see below): enables RLS scoped to
`current_setting('app.tenant_id')`, set per-transaction by
`app.repositories.postgres_repository` (binding decision #8 -- see that
module's docstring for the full mechanism and why per-tenant Postgres roles
were rejected in favor of this).

`FORCE ROW LEVEL SECURITY` is required in addition to `ENABLE ROW LEVEL
SECURITY`: by default Postgres exempts a table's *owner* from its own RLS
policies, and the app connects as the same role that owns these tables (no
per-tenant/per-role split, per binding decision #8) -- without FORCE, RLS
would silently do nothing for every query this service ever issues.

Exemptions (GW-003's two documented tenant-agnostic lookups,
`ApiKeyRepository.get_by_hash` / `UserRepository.get_user_by_email`): rather
than routing those two specific queries around RLS entirely, `users` and
`api_keys` each get a policy whose USING clause also permits the read when
no `app.tenant_id` is set for the current transaction. `postgres_repository.py`
deliberately does not call `_set_tenant_scope` before those two queries, so
they hit this permissive fallback; every other method sets `app.tenant_id`
first, so the fallback never applies to them. This is the documented,
deliberate gap -- not an accidental one. The `WITH CHECK` clauses (governing
INSERT/UPDATE) do NOT carry the same fallback: writes always require a known
tenant, even though the matching read may not.

The "is it unset" check is `NULLIF(current_setting('app.tenant_id', true), '')
IS NULL`, not the more obvious `current_setting('app.tenant_id', true) IS
NULL` -- found empirically while writing this ticket's own tests. `true`
("missing_ok") makes `current_setting` return NULL only the *first* time a
custom GUC like `app.tenant_id` is ever referenced in a session/connection;
once anything (even a since-reverted `SET LOCAL`/`set_config(..., true)` in
an earlier, already-committed transaction on the same pooled physical
connection) has registered that placeholder, Postgres reverts it to `''`
(empty string) at transaction end, not back to NULL. Since connections are
pooled and reused across many transactions/tenants over their lifetime, this
is the common case, not an edge case -- `NULLIF(..., '') IS NULL` normalizes
both "never referenced" and "referenced, then reverted" to the same check.

`tenants` has no such exemption (no tenant-agnostic method on
`TenantRepository`): `create_tenant` sets `app.tenant_id` to the
newly-generated id *before* inserting, so its own USING/WITH CHECK
(`id = current_setting('app.tenant_id')`) is satisfied without needing a
fallback.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_POLICY_NAME = "tenant_isolation"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # RLS has no SQLite equivalent -- this service's own
        # tests/test_models.py runs `alembic upgrade head` against a real
        # sqlite file as a schema-parity check, and that run must stay a
        # no-op here rather than error.
        return

    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenants FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {_POLICY_NAME} ON tenants "
        "USING (id = current_setting('app.tenant_id', true)) "
        "WITH CHECK (id = current_setting('app.tenant_id', true))"
    )

    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {_POLICY_NAME} ON users "
        "USING ("
        "  tenant_id = current_setting('app.tenant_id', true)"
        "  OR NULLIF(current_setting('app.tenant_id', true), '') IS NULL"
        ") "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
    )

    op.execute("ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE api_keys FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {_POLICY_NAME} ON api_keys "
        "USING ("
        "  tenant_id = current_setting('app.tenant_id', true)"
        "  OR NULLIF(current_setting('app.tenant_id', true), '') IS NULL"
        ") "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in ("api_keys", "users", "tenants"):
        op.execute(f"DROP POLICY IF EXISTS {_POLICY_NAME} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
