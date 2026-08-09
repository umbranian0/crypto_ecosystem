"""GW-012: integration tests for `PostgresTenantRepository`/
`PostgresUserRepository`/`PostgresApiKeyRepository` against a REAL Postgres
(infra's Compose `postgres` service, reachable from the host at
`localhost:5432` -- see infra/.env.example), not a mock/sqlite stand-in.

Run against real Postgres deliberately (Test AC): RLS is enforced by the
database engine itself, so anything short of a real Postgres connection
(e.g. sqlite, or a mocked session) cannot actually prove the tenant-isolation
property this ticket exists to deliver.

`migrated_engine` runs this service's own `alembic upgrade head` (migrations
0001 + 0002, `env.py`'s identity-schema targeting) against that real
database before any test executes, exactly the way an operator/CI would --
not `Base.metadata.create_all`, which would skip migration 0002's RLS DDL
entirely and give every test here a false pass.

**Empirically discovered while writing this test (self-review finding, not
a design flaw in the migration or `postgres_repository.py`)**: this repo's
`infra/.env.example` / `infra/docker-compose.yml` credentials (`naive_first`)
are created by the official `postgres` Docker image's `POSTGRES_USER`
mechanism, which makes that role a superuser --
`SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'naive_first'`
returns `(true, true)` against the real Compose Postgres used for this
ticket. **Postgres superusers (and any role with `BYPASSRLS`) ignore RLS
entirely, `FORCE ROW LEVEL SECURITY` included** -- so running the app's own
repository code with the current infra credentials would never actually be
blocked by RLS, no matter how correct migration 0002's policies are. This is
an infra-provisioning gap (a non-superuser, non-`BYPASSRLS` application role
was never created -- INF-001 provisioned only the single superuser
`POSTGRES_USER`), not something this ticket's own files can fix without
reaching into `infra/` (out of this ticket's module). It's flagged
explicitly in this ticket's Outcome section as a follow-up, not silently
worked around.

To still give this ticket's core claim (RLS actually blocks cross-tenant
reads) a real, non-tautological proof, `restricted_role_engine` below
creates an ephemeral, test-only, non-superuser Postgres role (`NOSUPERUSER
NOBYPASSRLS`, dropped again at teardown) with exactly the grants a properly
provisioned application role would have, and the two RLS-proving tests run
through that role instead of `migrated_engine`'s (superuser) connection.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.repositories.postgres_repository import (
    PostgresApiKeyRepository,
    PostgresTenantRepository,
    PostgresUserRepository,
    _set_tenant_scope,
)

SERVICE_ROOT = Path(__file__).resolve().parent.parent

POSTGRES_TEST_URL = os.environ.get(
    "GATEWAY_API_TEST_DATABASE_URL",
    "postgresql+psycopg://naive_first:naive_first_dev_password@localhost:5432/naive_first",
)


@pytest.fixture(scope="module")
def migrated_engine():
    env = {**os.environ, "DATABASE_URL": POSTGRES_TEST_URL}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            "alembic upgrade head against real Postgres "
            f"({POSTGRES_TEST_URL}) failed:\n{result.stdout}\n{result.stderr}"
        )

    # pool_size=1/max_overflow=0 (test-only, not production config): forces
    # every sequential Session() in this module onto the SAME physical
    # connection, which is exactly what the pooled-connection-reuse test
    # needs to prove -- a bigger pool would make "was this actually the
    # same recycled connection" non-deterministic.
    #
    # search_path=identity mirrors app.dependencies.repositories'
    # _postgres_engine_url: the migration above put tenants/users/api_keys
    # in `identity`, so unqualified table names must resolve there too, or
    # every repository call below would 42P01 against `public`.
    engine_url = f"{POSTGRES_TEST_URL}?options={quote('-c search_path=identity')}"
    engine = create_engine(engine_url, pool_size=1, max_overflow=0)
    yield engine
    engine.dispose()


_RESTRICTED_ROLE = "gw012_rls_test_role"
_RESTRICTED_ROLE_PASSWORD = "gw012_rls_test_role_password"  # test-only, dropped at teardown


def _with_credentials(url: str, user: str, password: str) -> str:
    parts = urlsplit(url)
    netloc = f"{user}:{password}@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _drop_test_role_if_exists(conn) -> None:
    # `DROP ROLE` alone fails with "cannot be dropped because some objects
    # depend on it" once GRANTs exist against it (e.g. a previous test run
    # that crashed before its own teardown ran) -- `DROP OWNED BY` first
    # clears those dependent privileges.
    exists = conn.execute(
        text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": _RESTRICTED_ROLE}
    ).scalar()
    if exists:
        conn.execute(text(f"DROP OWNED BY {_RESTRICTED_ROLE}"))
        conn.execute(text(f"DROP ROLE {_RESTRICTED_ROLE}"))


@pytest.fixture(scope="module")
def restricted_role_engine(migrated_engine):
    """A non-superuser, non-BYPASSRLS role -- see module docstring for why
    the infra-provisioned `naive_first` credentials can't prove RLS
    enforcement on their own. Grants mirror exactly what a properly
    provisioned application role would need: schema USAGE plus
    SELECT/INSERT/UPDATE on the three identity tables, nothing else (no
    DELETE method exists on any of GW-003's interfaces).
    """
    with migrated_engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        _drop_test_role_if_exists(conn)
        conn.execute(
            text(
                f"CREATE ROLE {_RESTRICTED_ROLE} LOGIN PASSWORD "
                f"'{_RESTRICTED_ROLE_PASSWORD}' NOSUPERUSER NOBYPASSRLS"
            )
        )
        conn.execute(text(f"GRANT USAGE ON SCHEMA identity TO {_RESTRICTED_ROLE}"))
        conn.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE ON "
                "identity.tenants, identity.users, identity.api_keys "
                f"TO {_RESTRICTED_ROLE}"
            )
        )

    restricted_url = _with_credentials(
        POSTGRES_TEST_URL, _RESTRICTED_ROLE, _RESTRICTED_ROLE_PASSWORD
    )
    restricted_url = f"{restricted_url}?options={quote('-c search_path=identity')}"
    engine = create_engine(restricted_url, pool_size=1, max_overflow=0)
    yield engine
    engine.dispose()

    with migrated_engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        _drop_test_role_if_exists(conn)


@pytest.fixture()
def tenant_repo(migrated_engine) -> PostgresTenantRepository:
    return PostgresTenantRepository(engine=migrated_engine)


@pytest.fixture()
def user_repo(migrated_engine) -> PostgresUserRepository:
    return PostgresUserRepository(engine=migrated_engine)


@pytest.fixture()
def key_repo(migrated_engine) -> PostgresApiKeyRepository:
    return PostgresApiKeyRepository(engine=migrated_engine)


@pytest.fixture()
def unique() -> str:
    # This suite runs against a real, persistent Postgres database (not a
    # fresh tmp_path sqlite file per test) -- email/key_hash values must be
    # unique per test invocation, or a rerun collides with rows a previous
    # run already committed and `get_by_hash`/`get_user_by_email` (which
    # have no tenant_id filter by design) raise MultipleResultsFound
    # instead of exercising the behavior under test.
    return uuid4().hex[:8]


def test_create_tenant_persists_and_is_retrievable(tenant_repo) -> None:
    created = tenant_repo.create_tenant("Acme Corp (pg)")

    assert created.id
    fetched = tenant_repo.get_tenant(created.id)
    assert fetched == created


def test_get_tenant_returns_none_for_unknown_id(tenant_repo) -> None:
    assert tenant_repo.get_tenant("no-such-tenant") is None


def test_create_user_persists_and_is_retrievable_by_email(tenant_repo, user_repo, unique) -> None:
    tenant = tenant_repo.create_tenant("Acme Corp (pg users)")

    email = f"alice-pg-{unique}@acme.example"
    created = user_repo.create_user(tenant.id, email, "admin")

    assert created.tenant_id == tenant.id
    fetched = user_repo.get_user_by_email(email)
    assert fetched == created


def test_create_key_and_revoke_key_flags_not_deletes(tenant_repo, key_repo, unique) -> None:
    tenant = tenant_repo.create_tenant("Acme Corp (pg keys)")
    key_hash = f"pg-hash-to-revoke-{unique}"
    created = key_repo.create_key(tenant.id, key_hash)
    assert created.revoked_at is None

    key_repo.revoke_key(tenant.id, created.id)

    revoked = key_repo.get_by_hash(key_hash)
    assert revoked is not None
    assert revoked.revoked_at is not None


def test_revoke_key_does_not_affect_other_tenants_key(tenant_repo, key_repo, unique) -> None:
    tenant_a = tenant_repo.create_tenant("PG Tenant A (revoke)")
    tenant_b = tenant_repo.create_tenant("PG Tenant B (revoke)")
    key_hash = f"pg-hash-a-revoke-guard-{unique}"
    key_a = key_repo.create_key(tenant_a.id, key_hash)

    key_repo.revoke_key(tenant_b.id, key_a.id)

    still_active = key_repo.get_by_hash(key_hash)
    assert still_active is not None
    assert still_active.revoked_at is None


def test_rls_blocks_cross_tenant_reads_at_database_level(restricted_role_engine, unique) -> None:
    """Test AC: RLS blocks cross-tenant reads at the database level -- not
    an app-level `WHERE tenant_id = ...` check, a raw `SELECT ... WHERE
    id = :id` scoped to a *different* tenant's `app.tenant_id`, which the
    ORM-level query never adds a tenant filter to at all. Uses
    `restricted_role_engine` (see module docstring): the infra-provisioned
    `naive_first` superuser bypasses RLS unconditionally, so this must run
    as a real non-superuser/non-BYPASSRLS role for the assertion below to
    mean anything -- against `naive_first` this row always comes back
    regardless of whether migration 0002's policies are correct.
    """
    tenant_repo = PostgresTenantRepository(engine=restricted_role_engine)
    user_repo = PostgresUserRepository(engine=restricted_role_engine)

    tenant_a = tenant_repo.create_tenant("PG Tenant A (RLS)")
    tenant_b = tenant_repo.create_tenant("PG Tenant B (RLS)")
    user_a = user_repo.create_user(tenant_a.id, f"rls-a-{unique}@example.com", "member")

    with Session(restricted_role_engine) as session:
        _set_tenant_scope(session, tenant_b.id)
        rows = session.execute(
            text("SELECT id FROM users WHERE id = :id"), {"id": user_a.id}
        ).fetchall()
        session.commit()

    assert rows == []


def test_get_by_hash_and_get_user_by_email_resolve_across_tenants_despite_rls(
    restricted_role_engine, unique
) -> None:
    """Test AC: GW-003's two documented tenant-agnostic exceptions continue
    to resolve identity regardless of tenant, unchanged behavior, despite
    RLS now being enabled on both tables. Uses `restricted_role_engine`
    (see module docstring) so this actually exercises migration 0002's
    permissive "current_setting(...) IS NULL" policy clause, rather than
    trivially passing because the connecting role bypasses RLS anyway.
    """
    tenant_repo = PostgresTenantRepository(engine=restricted_role_engine)
    user_repo = PostgresUserRepository(engine=restricted_role_engine)
    key_repo = PostgresApiKeyRepository(engine=restricted_role_engine)

    tenant_a = tenant_repo.create_tenant("PG Tenant A (exempt)")
    tenant_b = tenant_repo.create_tenant("PG Tenant B (exempt)")
    email = f"exempt-a-{unique}@example.com"
    key_hash = f"pg-exempt-hash-b-{unique}"
    user_a = user_repo.create_user(tenant_a.id, email, "member")
    key_b = key_repo.create_key(tenant_b.id, key_hash)

    resolved_user = user_repo.get_user_by_email(email)
    resolved_key = key_repo.get_by_hash(key_hash)

    assert resolved_user is not None and resolved_user.id == user_a.id
    assert resolved_key is not None and resolved_key.id == key_b.id


def test_set_local_scope_does_not_leak_across_pooled_connection_reuse(
    restricted_role_engine,
) -> None:
    """THE core test (sprint-level flag, Tech Lead personally verifies this
    one): proves the SET LOCAL/set_config hook is genuinely per-transaction,
    not a one-time value that survives a connection's return to (and reuse
    from) the pool. Uses `restricted_role_engine` (see module docstring) --
    the "tenant B must not see tenant A's data" assertions below only mean
    something under a real non-superuser/non-BYPASSRLS role; the current
    infra-provisioned `naive_first` superuser bypasses RLS unconditionally.

    Deliberately non-tautological: the middle block below does NOT call
    `_set_tenant_scope` at all. It just checks, on the SAME physical
    connection (forced via `restricted_role_engine`'s pool_size=1) tenant
    A's transaction just used, whether `current_setting('app.tenant_id')`
    is still readable. If the hook were wired at engine-creation/startup
    time, or used plain `SET` instead of `SET LOCAL`/`set_config(...,
    true)`, this would still return tenant A's id here -- this test would
    fail. Since the real implementation scopes it to the transaction, it
    must come back NULL.
    """
    tenant_repo = PostgresTenantRepository(engine=restricted_role_engine)
    user_repo = PostgresUserRepository(engine=restricted_role_engine)

    tenant_a = tenant_repo.create_tenant("PG Tenant A (pool reuse)")
    tenant_b = tenant_repo.create_tenant("PG Tenant B (pool reuse)")
    user_a = user_repo.create_user(tenant_a.id, "pool-a@example.com", "member")
    user_b = user_repo.create_user(tenant_b.id, "pool-b@example.com", "member")

    # Acquire + release a connection scoped to tenant A.
    with Session(restricted_role_engine) as session:
        _set_tenant_scope(session, tenant_a.id)
        backend_pid_a = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
        seen_as_a = set(session.execute(text("SELECT id FROM users")).scalars())
        session.commit()

    assert user_a.id in seen_as_a
    assert user_b.id not in seen_as_a

    # Immediately after: open a NEW transaction, on what pool_size=1
    # guarantees is the SAME recycled physical connection, and check the
    # leftover state BEFORE this test itself sets anything.
    with Session(restricted_role_engine) as session:
        backend_pid_check = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
        assert backend_pid_check == backend_pid_a, (
            "test setup invariant violated: expected the exact same "
            "physical connection to be recycled from the pool -- if this "
            "assertion fails, the leak check below no longer proves "
            "anything about pooled-connection reuse"
        )

        leaked_value = session.execute(
            text("SELECT current_setting('app.tenant_id', true)")
        ).scalar_one()
        session.rollback()

    # Not `is None`: Postgres reverts a custom GUC's per-transaction
    # `SET LOCAL`/`set_config(..., true)` value to `''` (empty string), not
    # NULL, once that GUC's placeholder has been referenced at all on a
    # session/connection (see migration 0002_add_identity_rls.py's
    # docstring) -- `''`/falsy is the correctly-reverted state here, an
    # actual leak would be the literal `tenant_a.id` string.
    assert not leaked_value, (
        f"app.tenant_id leaked across pooled-connection reuse: {leaked_value!r} "
        "-- SET LOCAL/set_config(..., true) must revert at transaction end, "
        "not persist on the physical connection"
    )
    assert leaked_value != tenant_a.id

    # Now prove the actual tenant-B-scoped behavior on that same recycled
    # connection: sees tenant B's data, not tenant A's, and
    # current_setting correctly reflects tenant B.
    with Session(restricted_role_engine) as session:
        _set_tenant_scope(session, tenant_b.id)
        seen_as_b = set(session.execute(text("SELECT id FROM users")).scalars())
        current_tenant_b = session.execute(
            text("SELECT current_setting('app.tenant_id', true)")
        ).scalar_one()
        session.commit()

    assert user_b.id in seen_as_b
    assert user_a.id not in seen_as_b
    assert current_tenant_b == tenant_b.id
