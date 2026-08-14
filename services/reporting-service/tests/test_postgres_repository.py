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

Skipped, not failed, when Postgres isn't reachable (e.g. Docker not running
locally) -- CI/other devs without Compose up should not break on this file --
but does not silently skip when it *is* reachable.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.repositories.postgres_repository import PostgresReportRepository

SERVICE_ROOT = Path(__file__).resolve().parent.parent

# Matches infra/.env.example's POSTGRES_* defaults, reached via the
# host-published port (tests run outside Compose). Migration-time role
# (schema owner) -- same precedent validation-service's/gateway-api's own
# test_postgres_repository.py use for their main CRUD fixtures.
POSTGRES_URL = "postgresql+psycopg://naive_first:naive_first_dev_password@localhost:5432/naive_first"
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
    not _postgres_reachable(), reason="Postgres not reachable at localhost:5432"
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
    f"@localhost:5432/naive_first?{SEARCH_PATH_OPTION}"
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
