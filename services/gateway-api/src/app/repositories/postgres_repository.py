"""GW-012: Postgres-backed implementations of GW-003's repository interfaces
(`TenantRepository`, `UserRepository`, `ApiKeyRepository`), targeting the
`identity` schema, with row-level security (RLS) as the tenant-isolation
boundary -- same shape as VS-013's sibling work for validation-service.

**The core mechanism (binding decision #8, grooming -- "the subtlest
cross-story interaction in this sprint")**: RLS policies (migration
`0002_add_identity_rls.py`) scope every row to
`current_setting('app.tenant_id')`. That session variable is set **per
transaction, not once**, via `_set_tenant_scope`, called as the *first*
statement inside every method's own `Session(engine)` block, before any
real query. A SQLAlchemy `Session(engine)` does not check out a pooled
connection until its first `execute()` -- so `_set_tenant_scope` being that
first call means the tenant-scoping statement and the transaction's physical
connection checkout happen together, and the transaction's end (`commit()`/
`rollback()`/`session.close()` via the `with` block) is also when that
connection is released back to the pool. This matters because Postgres's
`SET LOCAL` (and the `set_config(..., is_local := true)` used here, see
below) is scoped to the *current transaction* -- it is automatically
unset/reverted when that transaction ends, before the connection is
recycled by the pool. A connection recycled from tenant A's request into
tenant B's request therefore never carries tenant A's `app.tenant_id`
forward; each new transaction starts with it unset (or overwritten by its
own `_set_tenant_scope` call). See
`tests/test_postgres_repository.py::test_set_local_scope_does_not_leak_across_pooled_connection_reuse`
for a test that forces exactly this recycling (a single-connection pool)
and proves the previous transaction's setting does NOT survive into the
next one on the same physical connection.

Why not `SET LOCAL app.tenant_id = :tenant_id` literally, and why not
per-tenant Postgres roles: Postgres's `SET`/`SET LOCAL` grammar does not
accept a bound/parameterized value (only a literal), so a naive `text("SET
LOCAL app.tenant_id = :tenant_id")` either can't be parameterized safely or
requires manually splicing the tenant id into the SQL string -- exactly the
injection risk parameterization exists to avoid. `SELECT
set_config('app.tenant_id', :tenant_id, true)` is the standard, safe
equivalent: `set_config` is an ordinary function call (so it accepts a bind
parameter like any other), and its third argument (`is_local`) set to `true`
gives it the exact same transaction-scoped-only semantics as `SET LOCAL`
(reverts at transaction end, never leaks via `SET` without `LOCAL`, which
would persist for the lifetime of the physical connection and leak across
pooled reuse). Per-tenant Postgres roles (one role per tenant, switched via
`SET ROLE`) were explicitly rejected in grooming (#8): this platform has one
application-level Postgres user across all tenants, and per-tenant roles
would mean provisioning/dropping a Postgres role per tenant, a much heavier
operational surface than a per-transaction session variable for the same
isolation guarantee RLS + `current_setting` already buys.

`get_by_hash` (`ApiKeyRepository`) and `get_user_by_email` (`UserRepository`)
are GW-003's documented tenant-agnostic exceptions (login/auth-time lookups
that resolve identity *before* a tenant is known). They deliberately do
**not** call `_set_tenant_scope` -- see migration `0002_add_identity_rls.py`
for the matching permissive RLS policy clause (and its docstring's note on
why it's `NULLIF(current_setting('app.tenant_id', true), '') IS NULL`, not
the more obvious plain `IS NULL`) that lets these two specific query shapes
resolve across tenants despite RLS being enabled on their tables.

`_set_tenant_scope` itself is now a thin alias for
`naive_first_common.db.tenant_scope` (LC-010) -- this module previously
defined the `SELECT set_config(...)` statement itself, byte-identical to
validation-service's own copy, which is the duplication LC-010 extracted.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app.models import ApiKey, Tenant, User
from app.repositories.interfaces import ApiKeyRecord, TenantRecord, UserRecord
from app.repositories.sqlite_repository import (
    _api_key_to_record,
    _tenant_to_record,
    _user_to_record,
)
from naive_first_common.db import tenant_scope as _set_tenant_scope


class PostgresTenantRepository:
    """Postgres implementation of `TenantRepository` (GW-003)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_tenant(self, name: str) -> TenantRecord:
        # No tenant_id is known yet (GW-003's documented exception on this
        # method) -- but a tenant's own `id` is what its RLS policy scopes
        # by, so generating the id first and scoping to it before the
        # INSERT satisfies that policy's WITH CHECK without needing a
        # separate NULL-fallback clause (unlike get_by_hash/get_user_by_email).
        tenant_id = uuid4().hex
        tenant = Tenant(id=tenant_id, name=name, created_at=datetime.utcnow())
        with Session(self._engine) as session:
            _set_tenant_scope(session, tenant_id)
            session.add(tenant)
            # Record built from the already-fully-populated object, not a
            # post-commit session.refresh(): every column here is set
            # client-side (no server-generated defaults), and refreshing
            # after commit() would issue a new SELECT in a *new*
            # transaction -- one _set_tenant_scope has not (yet) run
            # against, which RLS would then correctly, if surprisingly,
            # block (proof the per-transaction scoping really is
            # per-transaction).
            record = _tenant_to_record(tenant)
            session.commit()
            return record

    def get_tenant(self, tenant_id: str) -> TenantRecord | None:
        with Session(self._engine) as session:
            _set_tenant_scope(session, tenant_id)
            tenant = session.execute(
                select(Tenant).where(Tenant.id == tenant_id)
            ).scalar_one_or_none()
            return _tenant_to_record(tenant) if tenant is not None else None


class PostgresUserRepository:
    """Postgres implementation of `UserRepository` (GW-003)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_user(self, tenant_id: str, email: str, role: str) -> UserRecord:
        user = User(
            id=uuid4().hex,
            tenant_id=tenant_id,
            email=email,
            role=role,
            created_at=datetime.utcnow(),
        )
        with Session(self._engine) as session:
            _set_tenant_scope(session, tenant_id)
            session.add(user)
            # See create_tenant's comment: record built pre-commit, no
            # post-commit refresh().
            record = _user_to_record(user)
            session.commit()
            return record

    def get_user_by_email(self, email: str) -> UserRecord | None:
        # GW-003's documented exception: login-time lookup doesn't yet know
        # the tenant, so this deliberately does NOT call _set_tenant_scope --
        # relies on migration 0002's permissive
        # "current_setting('app.tenant_id', true) IS NULL" policy clause.
        with Session(self._engine) as session:
            user = session.execute(
                select(User).where(User.email == email)
            ).scalar_one_or_none()
            return _user_to_record(user) if user is not None else None


class PostgresApiKeyRepository:
    """Postgres implementation of `ApiKeyRepository` (GW-003)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_key(self, tenant_id: str, key_hash: str) -> ApiKeyRecord:
        api_key = ApiKey(
            id=uuid4().hex,
            tenant_id=tenant_id,
            key_hash=key_hash,
            created_at=datetime.utcnow(),
            revoked_at=None,
        )
        with Session(self._engine) as session:
            _set_tenant_scope(session, tenant_id)
            session.add(api_key)
            # See create_tenant's comment: record built pre-commit, no
            # post-commit refresh().
            record = _api_key_to_record(api_key)
            session.commit()
            return record

    def get_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        # GW-003's documented exception (same spirit as get_user_by_email
        # above): GW-006's auth check must resolve a raw key to its tenant,
        # not already know it, so this deliberately does NOT call
        # _set_tenant_scope -- relies on migration 0002's permissive
        # NULL-fallback policy clause.
        with Session(self._engine) as session:
            api_key = session.execute(
                select(ApiKey).where(ApiKey.key_hash == key_hash)
            ).scalar_one_or_none()
            return _api_key_to_record(api_key) if api_key is not None else None

    def revoke_key(self, tenant_id: str, key_id: str) -> None:
        # Sets revoked_at, never deletes the row (GW-006/GW-010 need the
        # revoked record still resolvable via get_by_hash). The WHERE clause
        # already scopes to tenant_id; RLS (USING, since this is an UPDATE)
        # scoping to the same current_setting is defense in depth, not the
        # only thing standing between tenants here.
        with Session(self._engine) as session:
            _set_tenant_scope(session, tenant_id)
            session.execute(
                update(ApiKey)
                .where(ApiKey.id == key_id, ApiKey.tenant_id == tenant_id)
                .values(revoked_at=datetime.utcnow())
            )
            session.commit()
