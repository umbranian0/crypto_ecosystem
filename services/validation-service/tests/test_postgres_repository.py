"""VS-013: `PostgresValidationRunRepository`/`PostgresSplitResultRepository`
against a real Postgres (`validation` schema, INF-001).

Mirrors test_sqlite_repository.py's method coverage plus two tests specific
to this ticket's hard requirements:

- `test_rls_blocks_cross_tenant_reads_at_the_database_level`: a genuine
  database-level proof, not an application-level filter test -- it issues a
  raw, unfiltered `SELECT * FROM runs` (no `WHERE tenant_id = ...` anywhere
  in this test) as tenant A's session and asserts tenant B's row is absent,
  proving the Postgres RLS policy itself (migrations/versions/
  0002_add_row_level_security.py) is what's doing the filtering.
- `test_alembic_upgrade_head_lands_alembic_version_in_validation_schema`:
  confirms `alembic_version` (not just `runs`/`split_results`) lands in the
  `validation` schema, per this ticket's hard requirement (INF-005).

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

from app.repositories.interfaces import SplitResultRecord
from app.repositories.postgres_repository import (
    PostgresSplitResultRepository,
    PostgresValidationRunRepository,
)

SERVICE_ROOT = Path(__file__).resolve().parent.parent

# Matches infra/.env.example's POSTGRES_*/VALIDATION_SERVICE_DATABASE_URL
# defaults, reached via the host-published port (tests run outside Compose).
POSTGRES_URL = "postgresql+psycopg://naive_first:naive_first_dev_password@localhost:5432/naive_first"
SEARCH_PATH_OPTION = "options=-csearch_path%3Dvalidation"
ENGINE_URL = f"{POSTGRES_URL}?{SEARCH_PATH_OPTION}"

SPLIT_CONFIG = {"train_window": 100, "test_window": 20, "step": 10}


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
def run_repo(engine) -> PostgresValidationRunRepository:
    return PostgresValidationRunRepository(ENGINE_URL, engine=engine)


@pytest.fixture()
def split_repo(engine) -> PostgresSplitResultRepository:
    return PostgresSplitResultRepository(ENGINE_URL, engine=engine)


def _unique_tenant(label: str) -> str:
    # Real, shared Postgres database (not a disposable per-test file like
    # SQLite) -- unique tenant ids per test avoid collisions with rows left
    # by other test runs/sibling tickets' suites, no truncation required.
    return f"{label}-{uuid4().hex[:8]}"


def _make_split(run_id: str, tenant_id: str, split_index: int, **overrides) -> SplitResultRecord:
    fields = dict(
        id=f"split-{tenant_id}-{split_index}",
        run_id=run_id,
        tenant_id=tenant_id,
        split_index=split_index,
        train_start=datetime(2026, 1, 1),
        train_end=datetime(2026, 1, 10),
        purge_start=datetime(2026, 1, 10),
        purge_end=datetime(2026, 1, 11),
        test_start=datetime(2026, 1, 11),
        test_end=datetime(2026, 1, 15),
        model_mae=0.1,
        model_rmse=0.2,
        model_smape=0.3,
        model_mase=0.4,
        model_da=0.5,
        model_f1=0.6,
        model_oos_r2=0.7,
        naive0_mae=0.11,
        naive0_rmse=0.21,
        naive0_smape=0.31,
        naive0_mase=0.41,
        naive0_da=0.51,
        naive0_f1=0.61,
        naive0_oos_r2=0.71,
        dm_statistic=1.23,
        dm_pvalue=0.04,
        dm_verdict="better",
    )
    fields.update(overrides)
    return SplitResultRecord(**fields)


def test_create_run_persists_and_is_retrievable(run_repo) -> None:
    tenant = _unique_tenant("tenant")
    created = run_repo.create_run(
        tenant_id=tenant,
        dataset_id="dataset-1",
        horizon=1,
        purge_gap_hours=4.0,
        split_config=SPLIT_CONFIG,
    )

    assert created.id
    assert created.status == "pending"

    fetched = run_repo.get_run(tenant, created.id)
    assert fetched == created


def test_update_run_status_updates_status_and_completion_fields(run_repo) -> None:
    tenant = _unique_tenant("tenant")
    created = run_repo.create_run(
        tenant_id=tenant,
        dataset_id="dataset-1",
        horizon=1,
        purge_gap_hours=4.0,
        split_config=SPLIT_CONFIG,
    )

    run_repo.update_run_status(tenant, created.id, "completed", completed_at=datetime(2026, 1, 2))

    updated = run_repo.get_run(tenant, created.id)
    assert updated.status == "completed"
    assert updated.completed_at == datetime(2026, 1, 2)


def test_add_and_get_splits_round_trips_and_orders_by_split_index(run_repo, split_repo) -> None:
    tenant = _unique_tenant("tenant")
    run = run_repo.create_run(
        tenant_id=tenant,
        dataset_id="dataset-1",
        horizon=1,
        purge_gap_hours=4.0,
        split_config=SPLIT_CONFIG,
    )

    splits = [
        _make_split(run.id, tenant, 2),
        _make_split(run.id, tenant, 0),
        _make_split(run.id, tenant, 1),
    ]
    split_repo.add_splits(tenant, run.id, splits)

    fetched = split_repo.get_splits(tenant, run.id)

    assert [s.split_index for s in fetched] == [0, 1, 2]
    assert fetched[0].dm_verdict == "better"


def test_tenant_isolation_get_run_and_get_splits_never_leak_across_tenants(run_repo, split_repo) -> None:
    """Application-level equivalent of test_sqlite_repository.py's load-bearing
    test. The genuine database-level RLS proof is
    `test_rls_blocks_cross_tenant_reads_at_the_database_level` below.
    """
    tenant_a = _unique_tenant("tenant-a")
    tenant_b = _unique_tenant("tenant-b")

    run_a = run_repo.create_run(
        tenant_id=tenant_a,
        dataset_id="dataset-a",
        horizon=1,
        purge_gap_hours=4.0,
        split_config=SPLIT_CONFIG,
    )
    run_b = run_repo.create_run(
        tenant_id=tenant_b,
        dataset_id="dataset-b",
        horizon=2,
        purge_gap_hours=8.0,
        split_config={"train_window": 50, "test_window": 10, "step": 5},
    )
    split_repo.add_splits(tenant_a, run_a.id, [_make_split(run_a.id, tenant_a, 0)])
    split_repo.add_splits(tenant_b, run_b.id, [_make_split(run_b.id, tenant_b, 0)])

    assert run_repo.get_run(tenant_b, run_a.id) is None
    assert split_repo.get_splits(tenant_b, run_a.id) == []
    assert run_repo.get_run(tenant_a, run_b.id) is None
    assert split_repo.get_splits(tenant_a, run_b.id) == []

    assert run_repo.get_run(tenant_a, run_a.id) is not None
    assert run_repo.get_run(tenant_b, run_b.id) is not None


RLS_TEST_ROLE = "validation_rls_test_role"
RLS_TEST_PASSWORD = "validation_rls_test_pw"
RLS_TEST_ENGINE_URL = (
    f"postgresql+psycopg://{RLS_TEST_ROLE}:{RLS_TEST_PASSWORD}"
    f"@localhost:5432/naive_first?{SEARCH_PATH_OPTION}"
)


@pytest.fixture()
def rls_test_role_engine(engine):
    """A non-superuser, non-BYPASSRLS role for the RLS proof test below.

    `naive_first` (the role every other test/repository in this file
    connects as, and the role INF-001 provisions the app with) is a Postgres
    *superuser* with the `Bypass RLS` attribute -- verified via `\\du
    naive_first` against the live Compose Postgres. Superusers ignore RLS
    unconditionally, regardless of `ENABLE`/`FORCE ROW LEVEL SECURITY`
    (Postgres docs: "row security is not applied ... to superusers"). Any
    RLS assertion made through that role would pass even if
    0002_add_row_level_security.py's policies did nothing -- not a genuine
    database-level proof. This fixture creates a disposable, ordinary role
    (idempotent -- reused across test runs, not dropped) so the proof test
    below exercises Postgres's real RLS enforcement path, the same one a
    non-superuser production app role would hit.
    """
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": RLS_TEST_ROLE}
        ).first()
        if exists is None:
            conn.execute(
                text(
                    f"CREATE ROLE {RLS_TEST_ROLE} LOGIN PASSWORD '{RLS_TEST_PASSWORD}' "
                    "NOSUPERUSER NOBYPASSRLS"
                )
            )
        conn.execute(text(f"GRANT USAGE ON SCHEMA validation TO {RLS_TEST_ROLE}"))
        conn.execute(text(f"GRANT SELECT ON validation.runs TO {RLS_TEST_ROLE}"))
        conn.commit()

    rls_engine = create_engine(RLS_TEST_ENGINE_URL)
    yield rls_engine
    rls_engine.dispose()


def test_rls_blocks_cross_tenant_reads_at_the_database_level(engine, rls_test_role_engine) -> None:
    """The load-bearing test for this ticket's RLS acceptance criterion.

    Creates a run for tenant A and a run for tenant B via the repository
    (same production code path, connected as `naive_first`). Then, entirely
    independent of `PostgresValidationRunRepository`, opens a session as
    `rls_test_role_engine` (a non-superuser role -- see that fixture's
    docstring for why this matters), issues `set_config('app.tenant_id',
    'tenant A', true)` (SET LOCAL's parameter-bindable equivalent), and runs
    an *unfiltered* `SELECT * FROM runs` -- no `WHERE tenant_id = ...`
    anywhere in this query. If Postgres RLS
    (0002_add_row_level_security.py) is doing its job, only tenant A's row
    comes back; tenant B's row is invisible at the database level, not
    merely excluded by an application-side filter this test never applies.
    """
    from sqlalchemy.orm import Session

    tenant_a = _unique_tenant("rls-a")
    tenant_b = _unique_tenant("rls-b")

    run_repo = PostgresValidationRunRepository(ENGINE_URL, engine=engine)
    run_a = run_repo.create_run(
        tenant_id=tenant_a,
        dataset_id="dataset-a",
        horizon=1,
        purge_gap_hours=4.0,
        split_config=SPLIT_CONFIG,
    )
    run_b = run_repo.create_run(
        tenant_id=tenant_b,
        dataset_id="dataset-b",
        horizon=1,
        purge_gap_hours=4.0,
        split_config=SPLIT_CONFIG,
    )

    with Session(rls_test_role_engine) as session:
        session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_a})
        rows = session.execute(text("SELECT tenant_id, id FROM runs")).all()

    seen_tenant_ids = {row.tenant_id for row in rows}
    seen_ids = {row.id for row in rows}

    assert tenant_a in seen_tenant_ids
    assert run_a.id in seen_ids
    assert tenant_b not in seen_tenant_ids
    assert run_b.id not in seen_ids


def test_alembic_upgrade_head_lands_alembic_version_in_validation_schema() -> None:
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
        connection.execute(text("SET search_path TO validation"))
        rows = connection.execute(
            text(
                "SELECT table_schema FROM information_schema.tables "
                "WHERE table_name = 'alembic_version'"
            )
        ).all()
    engine.dispose()

    # This ticket's hard requirement is that *validation-service's own*
    # alembic_version lands in `validation`, not `public` -- not that no
    # other service's alembic_version exists anywhere else in this shared
    # Postgres database. gateway-api's own migrations (GW-012, a sibling
    # ticket) legitimately stamp their own `identity`-schema
    # `alembic_version` in the same physical database; seeing that table
    # too is expected, not a collision.
    schemas = {row.table_schema for row in rows}
    assert "validation" in schemas
    assert "public" not in schemas

    inspector = inspect(create_engine(ENGINE_URL))
    run_columns = {c["name"] for c in inspector.get_columns("runs", schema="validation")}
    assert {"id", "tenant_id", "dataset_id"}.issubset(run_columns)


def test_list_runs_orders_by_created_at_descending(run_repo) -> None:
    tenant = _unique_tenant("tenant")
    run_1 = run_repo.create_run(
        tenant_id=tenant, dataset_id="dataset-1", horizon=1, purge_gap_hours=4.0, split_config=SPLIT_CONFIG
    )
    run_2 = run_repo.create_run(
        tenant_id=tenant, dataset_id="dataset-2", horizon=1, purge_gap_hours=4.0, split_config=SPLIT_CONFIG
    )
    run_3 = run_repo.create_run(
        tenant_id=tenant, dataset_id="dataset-3", horizon=1, purge_gap_hours=4.0, split_config=SPLIT_CONFIG
    )

    listed = run_repo.list_runs(tenant, limit=20, offset=0)

    assert [r.id for r in listed] == [run_3.id, run_2.id, run_1.id]


def test_list_runs_paginates_with_limit_and_offset(run_repo) -> None:
    tenant = _unique_tenant("tenant")
    created = [
        run_repo.create_run(
            tenant_id=tenant,
            dataset_id=f"dataset-{i}",
            horizon=1,
            purge_gap_hours=4.0,
            split_config=SPLIT_CONFIG,
        )
        for i in range(5)
    ]
    expected_desc_order = list(reversed([r.id for r in created]))

    page_1 = run_repo.list_runs(tenant, limit=2, offset=0)
    page_2 = run_repo.list_runs(tenant, limit=2, offset=2)
    page_3 = run_repo.list_runs(tenant, limit=2, offset=4)

    assert [r.id for r in page_1] == expected_desc_order[0:2]
    assert [r.id for r in page_2] == expected_desc_order[2:4]
    assert [r.id for r in page_3] == expected_desc_order[4:5]


def test_count_runs_returns_total_unpaginated_count(run_repo) -> None:
    tenant = _unique_tenant("tenant")
    for i in range(4):
        run_repo.create_run(
            tenant_id=tenant,
            dataset_id=f"dataset-{i}",
            horizon=1,
            purge_gap_hours=4.0,
            split_config=SPLIT_CONFIG,
        )

    assert run_repo.count_runs(tenant) == 4
    assert run_repo.count_runs(tenant) == len(run_repo.list_runs(tenant, limit=100, offset=0))


def test_list_runs_tenant_isolation_never_leaks_across_tenants(run_repo) -> None:
    tenant_a = _unique_tenant("tenant-a")
    tenant_b = _unique_tenant("tenant-b")

    run_a = run_repo.create_run(
        tenant_id=tenant_a, dataset_id="dataset-a", horizon=1, purge_gap_hours=4.0, split_config=SPLIT_CONFIG
    )
    run_b = run_repo.create_run(
        tenant_id=tenant_b, dataset_id="dataset-b", horizon=1, purge_gap_hours=4.0, split_config=SPLIT_CONFIG
    )

    tenant_a_ids = {r.id for r in run_repo.list_runs(tenant_a, limit=20, offset=0)}
    tenant_b_ids = {r.id for r in run_repo.list_runs(tenant_b, limit=20, offset=0)}

    assert tenant_a_ids == {run_a.id}
    assert tenant_b_ids == {run_b.id}
    assert run_a.id not in tenant_b_ids
    assert run_b.id not in tenant_a_ids
