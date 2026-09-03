"""RS-002: `PostgresReportRepository` against a real Postgres (`reporting`
schema, INF-001).

Mirrors validation-service's `tests/test_postgres_repository.py` shape (RS-002
ticket DRY check note) plus the two tests specific to this ticket's hard
requirements:

- `test_rls_blocks_cross_tenant_reads_at_the_database_level`: a genuine
  database-level proof, not an application-level filter test -- it issues a
  raw, unfiltered `SELECT tenant_id, id FROM reports` (no
  `WHERE tenant_id = ...` anywhere in this test) as tenant A's session and
  asserts tenant B's row is absent, proving the Postgres RLS policy itself
  (migrations/versions/0002_add_row_level_security.py) is what's doing the
  filtering. Runs as `naive_first_app` -- INF-014's real, already-provisioned
  `NOSUPERUSER NOBYPASSRLS` runtime role -- not an ephemeral test-only role:
  the ticket's fallback-role instruction only applies if that role is
  unreachable in this environment, and it is reachable here (verified via
  `pg_roles` before writing this test; see RS-002's Outcome section).
- `test_alembic_upgrade_head_lands_alembic_version_in_reporting_schema`:
  confirms `alembic_version` (not just `reports`) lands in the `reporting`
  schema, per this ticket's hard requirement (mirrors INF-005/VS-013).
- `test_set_local_scope_does_not_leak_across_pooled_connection_reuse`: mirrors
  gateway-api's `tests/test_postgres_repository.py` test of the same name
  exactly (a real bug of this class was found and fixed once already, VS-021
  in validation-service's `create_run`). Proves `_tenant_scoped_session`'s
  `SELECT set_config('app.tenant_id', :tenant_id, true)` is genuinely
  per-transaction, not a value that survives a connection's return to (and
  reuse from) the pool -- via `restricted_role_engine`'s `pool_size=1,
  max_overflow=0`, `pg_backend_pid()` to prove the same physical connection
  was actually recycled, and `current_setting('app.tenant_id', true)` to
  check for leakage.

Skipped, not failed, when Postgres isn't reachable (e.g. Docker not running
locally) -- CI/other devs without Compose up should not break on this file --
but does not silently skip when it *is* reachable.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.repositories.postgres_repository import PostgresReportRepository, _tenant_scoped_session

SERVICE_ROOT = Path(__file__).resolve().parent.parent

# Matches infra/.env.example's POSTGRES_* defaults, reached via the
# host-published port (tests run outside Compose). Migration-time role
# (schema owner) -- same precedent validation-service's/gateway-api's own
# test_postgres_repository.py use for their main CRUD fixtures.
# Uses the literal loopback IP, not the "localhost" hostname: found live
# (2026-09-01 QA sweep) that on this platform's Windows/Docker Desktop dev
# setup, resolving "localhost" can attempt an IPv6 (::1) connection first,
# which Docker Desktop's port-forwarding (bound to 127.0.0.1 only, per
# infra/docker-compose.yml's postgres service) never answers or rejects --
# the connection attempt hangs indefinitely instead of failing over to the
# working IPv4 address, hanging this entire test file (and anything that
# imports it, including plain `--collect-only`) with zero output. A literal
# IPv4 address sidesteps address-family resolution/ordering entirely and
# connects immediately, verified independently before this change.
POSTGRES_URL = "postgresql+psycopg://naive_first:naive_first_dev_password@127.0.0.1:5432/naive_first"
SEARCH_PATH_OPTION = "options=-csearch_path%3Dreporting"
ENGINE_URL = f"{POSTGRES_URL}?{SEARCH_PATH_OPTION}"


def _postgres_reachable() -> bool:
    try:
        engine = create_engine(POSTGRES_URL)
        with engine.connect():
            pass
        engine.dispose()
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _postgres_reachable(), reason="Postgres not reachable at 127.0.0.1:5432"
)


@pytest.fixture()
def engine():
    engine = create_engine(ENGINE_URL)
    yield engine
    engine.dispose()


@pytest.fixture()
def report_repo(engine) -> PostgresReportRepository:
    return PostgresReportRepository(ENGINE_URL, engine=engine)


def _unique_tenant(label: str) -> str:
    # Real, shared Postgres database (not a disposable per-test file like
    # SQLite) -- unique tenant ids per test avoid collisions with rows left
    # by other test runs/sibling tickets' suites, no truncation required.
    return f"{label}-{uuid4().hex[:8]}"


def test_create_report_persists_and_is_retrievable(report_repo) -> None:
    tenant = _unique_tenant("tenant")
    created = report_repo.create_report(
        tenant_id=tenant,
        run_id="run-1",
        report_kind="audit",
        content="<html>report</html>",
        status="generated",
    )

    assert created.id
    assert created.tenant_id == tenant
    assert created.run_id == "run-1"
    assert created.report_kind == "audit"
    assert created.content == "<html>report</html>"
    assert created.status == "generated"

    fetched = report_repo.get_report(tenant, created.id)
    assert fetched == created


def test_get_report_returns_none_for_nonexistent_id(report_repo) -> None:
    tenant = _unique_tenant("tenant")
    assert report_repo.get_report(tenant, "does-not-exist") is None


def test_get_report_returns_none_for_a_different_tenants_report(report_repo) -> None:
    tenant_a = _unique_tenant("tenant-a")
    tenant_b = _unique_tenant("tenant-b")

    created = report_repo.create_report(
        tenant_id=tenant_a,
        run_id="run-1",
        report_kind="audit",
        content="<html>report</html>",
        status="generated",
    )

    assert report_repo.get_report(tenant_b, created.id) is None
    # Repository-level non-disclosure (matching VS-007/GW-003's stance): a
    # nonexistent id and a real id belonging to a different tenant must both
    # return None indistinguishably, not e.g. a different exception/status.
    assert report_repo.get_report(tenant_b, created.id) == report_repo.get_report(
        tenant_b, "does-not-exist"
    )


APP_ROLE_ENGINE_URL = (
    f"postgresql+psycopg://naive_first_app:naive_first_app_dev_password"
    f"@127.0.0.1:5432/naive_first?{SEARCH_PATH_OPTION}"
)


@pytest.fixture()
def app_role_engine(engine):
    """`naive_first_app` -- INF-014's real runtime role, `NOSUPERUSER
    NOBYPASSRLS` (verified via `pg_roles` before this test was written; see
    RS-002's Outcome section for the exact query/result). Postgres
    superusers/`BYPASSRLS` roles ignore RLS unconditionally regardless of
    `ENABLE`/`FORCE ROW LEVEL SECURITY` -- `naive_first` (the role every
    other fixture in this file connects as, and the migration-owner role) IS
    exactly such a role, so any RLS assertion made through it would pass even
    if 0002_add_row_level_security.py's policy did nothing. This fixture
    grants the schema/table access `naive_first_app` needs (idempotent --
    infra/postgres-init only provisions this for `validation`/`identity`
    today, not yet `reporting`; see RS-002's Outcome section for the disclosed
    follow-up), so the proof test below exercises Postgres's real RLS
    enforcement path, the same one this service's own production DATABASE_URL
    (infra/.env.example) actually connects as.
    """
    with engine.connect() as conn:
        conn.execute(text("GRANT USAGE ON SCHEMA reporting TO naive_first_app"))
        conn.execute(text("GRANT SELECT ON reporting.reports TO naive_first_app"))
        conn.commit()

    app_engine = create_engine(APP_ROLE_ENGINE_URL)
    yield app_engine
    app_engine.dispose()


def test_rls_blocks_cross_tenant_reads_at_the_database_level(engine, app_role_engine) -> None:
    """The load-bearing test for this ticket's RLS acceptance criterion.

    Creates a report for tenant A and a report for tenant B via the
    repository (same production code path, connected as `naive_first`,
    the schema owner). Then, entirely independent of
    `PostgresReportRepository`, opens a session as `app_role_engine`
    (`naive_first_app` -- see that fixture's docstring for why this role,
    not `naive_first`, is what makes this proof genuine), issues
    `set_config('app.tenant_id', 'tenant A', true)` (SET LOCAL's
    parameter-bindable equivalent), and runs an *unfiltered*
    `SELECT tenant_id, id FROM reports` -- no `WHERE tenant_id = ...`
    anywhere in this query. If Postgres RLS
    (0002_add_row_level_security.py) is doing its job, only tenant A's row
    comes back; tenant B's row is invisible at the database level, not
    merely excluded by an application-side filter this test never applies.
    """
    tenant_a = _unique_tenant("rls-a")
    tenant_b = _unique_tenant("rls-b")

    report_repo = PostgresReportRepository(ENGINE_URL, engine=engine)
    report_a = report_repo.create_report(
        tenant_id=tenant_a,
        run_id="run-a",
        report_kind="audit",
        content="<html>a</html>",
        status="generated",
    )
    report_b = report_repo.create_report(
        tenant_id=tenant_b,
        run_id="run-b",
        report_kind="audit",
        content="<html>b</html>",
        status="generated",
    )

    with Session(app_role_engine) as session:
        session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_a})
        rows = session.execute(text("SELECT tenant_id, id FROM reports")).all()

    seen_tenant_ids = {row.tenant_id for row in rows}
    seen_ids = {row.id for row in rows}

    assert tenant_a in seen_tenant_ids
    assert report_a.id in seen_ids
    assert tenant_b not in seen_tenant_ids
    assert report_b.id not in seen_ids


def test_alembic_upgrade_head_lands_alembic_version_in_reporting_schema() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_ROOT,
        env={**__import__("os").environ, "DATABASE_URL": POSTGRES_URL},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    engine = create_engine(POSTGRES_URL)
    with engine.connect() as connection:
        connection.execute(text("SET search_path TO reporting"))
        rows = connection.execute(
            text(
                "SELECT table_schema FROM information_schema.tables "
                "WHERE table_name = 'alembic_version'"
            )
        ).all()
    engine.dispose()

    # This ticket's hard requirement is that *reporting-service's own*
    # alembic_version lands in `reporting`, not `public` -- not that no
    # other service's alembic_version exists anywhere else in this shared
    # Postgres database. validation-service's/gateway-api's own migrations
    # legitimately stamp their own `validation`/`identity`-schema
    # alembic_version in the same physical database; seeing those too is
    # expected, not a collision.
    schemas = {row.table_schema for row in rows}
    assert "reporting" in schemas
    assert "public" not in schemas

    inspector = inspect(create_engine(ENGINE_URL))
    report_columns = {c["name"] for c in inspector.get_columns("reports", schema="reporting")}
    assert {"id", "tenant_id", "run_id", "report_kind", "generated_at", "content", "status"}.issubset(
        report_columns
    )


_RESTRICTED_ROLE = "reporting_pool_reuse_test_role"
_RESTRICTED_ROLE_PASSWORD = "reporting_pool_reuse_test_role_password"  # test-only, dropped at teardown


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
def restricted_role_engine():
    """A non-superuser, non-BYPASSRLS role -- mirrors gateway-api's own
    `restricted_role_engine` fixture exactly (see that module's docstring
    for why an infra-provisioned superuser role can't prove RLS enforcement
    on its own: Postgres superusers, and any role with `BYPASSRLS`, ignore
    RLS entirely, `FORCE ROW LEVEL SECURITY` included). Grants mirror
    exactly what `PostgresReportRepository`'s two real methods need: schema
    USAGE plus SELECT/INSERT on `reporting.reports`, nothing else (no
    UPDATE/DELETE method exists on `ReportRepository`).

    `pool_size=1, max_overflow=0` (test-only, not production config): forces
    every sequential `Session()`/`_tenant_scoped_session()` call using this
    engine onto the SAME physical connection, which is exactly what the
    pooled-connection-reuse test below needs to prove -- a bigger pool would
    make "was this actually the same recycled connection" non-deterministic.
    """
    admin_engine = create_engine(POSTGRES_URL)
    with admin_engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        _drop_test_role_if_exists(conn)
        conn.execute(
            text(
                f"CREATE ROLE {_RESTRICTED_ROLE} LOGIN PASSWORD "
                f"'{_RESTRICTED_ROLE_PASSWORD}' NOSUPERUSER NOBYPASSRLS"
            )
        )
        conn.execute(text(f"GRANT USAGE ON SCHEMA reporting TO {_RESTRICTED_ROLE}"))
        conn.execute(text(f"GRANT SELECT, INSERT ON reporting.reports TO {_RESTRICTED_ROLE}"))
    admin_engine.dispose()

    restricted_url = _with_credentials(POSTGRES_URL, _RESTRICTED_ROLE, _RESTRICTED_ROLE_PASSWORD)
    restricted_url = f"{restricted_url}?{SEARCH_PATH_OPTION}"
    engine = create_engine(restricted_url, pool_size=1, max_overflow=0)
    yield engine
    engine.dispose()

    admin_engine = create_engine(POSTGRES_URL)
    with admin_engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        _drop_test_role_if_exists(conn)
    admin_engine.dispose()


def test_set_local_scope_does_not_leak_across_pooled_connection_reuse(
    restricted_role_engine,
) -> None:
    """THE core test: proves `_tenant_scoped_session`'s `set_config(...,
    true)` hook is genuinely per-transaction, not a one-time value that
    survives a connection's return to (and reuse from) the pool. Mirrors
    gateway-api's test of the same name exactly -- a real bug of this class
    was found and fixed once already (VS-021, validation-service's
    `create_run`). Uses `restricted_role_engine` (see its docstring): the
    "tenant B must not see tenant A's data" assertions below only mean
    something under a real non-superuser/non-BYPASSRLS role.

    Deliberately non-tautological: the middle block below does NOT call
    `_tenant_scoped_session` at all. It just checks, on the SAME physical
    connection (forced via `restricted_role_engine`'s pool_size=1) tenant
    A's transaction just used, whether `current_setting('app.tenant_id')`
    is still readable. If the hook were wired at engine-creation/startup
    time, or used plain `SET` instead of `set_config(..., true)`, this would
    still return tenant A's id here -- this test would fail. Since the real
    implementation scopes it to the transaction, it must come back empty.
    """
    report_repo = PostgresReportRepository(ENGINE_URL, engine=restricted_role_engine)

    tenant_a = _unique_tenant("pool-a")
    tenant_b = _unique_tenant("pool-b")
    report_a = report_repo.create_report(
        tenant_id=tenant_a,
        run_id="run-a",
        report_kind="audit",
        content="<html>a</html>",
        status="generated",
    )
    report_b = report_repo.create_report(
        tenant_id=tenant_b,
        run_id="run-b",
        report_kind="audit",
        content="<html>b</html>",
        status="generated",
    )

    # Acquire + release a connection scoped to tenant A.
    with _tenant_scoped_session(restricted_role_engine, tenant_a) as session:
        backend_pid_a = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
        session.commit()

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
    # `set_config(..., true)` value to `''` (empty string), not NULL, once
    # that GUC's placeholder has been referenced at all on a
    # session/connection -- `''`/falsy is the correctly-reverted state here,
    # an actual leak would be the literal `tenant_a` string.
    assert not leaked_value, (
        f"app.tenant_id leaked across pooled-connection reuse: {leaked_value!r} "
        "-- set_config(..., true) must revert at transaction end, not "
        "persist on the physical connection"
    )
    assert leaked_value != tenant_a

    # Now prove the actual tenant-B-scoped behavior on that same recycled
    # connection: sees tenant B's report, not tenant A's.
    fetched_b = report_repo.get_report(tenant_b, report_b.id)
    fetched_a_as_b = report_repo.get_report(tenant_b, report_a.id)

    assert fetched_b is not None
    assert fetched_b.id == report_b.id
    assert fetched_a_as_b is None
