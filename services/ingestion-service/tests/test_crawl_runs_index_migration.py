"""INGEST-017: ingestion.crawl_runs (tenant_id, source, fetched_at DESC)
composite index, added via migration 0005.

Gated exactly the same way this service's other real-Postgres migration test
(`test_hypertable_chunk_interval_migration.py`) already is -- skipped, not
failed, when Postgres isn't reachable locally (e.g. Docker not running),
never mocked.

Per this ticket's Test acceptance criteria: the real `crawl_runs` table has
only 8 rows this session, too small to show a measurable Seq Scan -> Index
Scan timing delta either way. This test only confirms the index exists and
is structurally correct (columns, order); it does not assert a plan-shape or
timing outcome -- that disclosed-caveat live verification is the Tech Lead's
Review AC, run directly against the real container (see this ticket's
Outcome/Review notes), not something to fake a false positive for here.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

SERVICE_ROOT = Path(__file__).resolve().parent.parent

# Same literal loopback IP / credential convention as
# test_hypertable_chunk_interval_migration.py -- "localhost" can hang here on
# an IPv6-first resolution that Docker Desktop's 127.0.0.1-only port
# forwarding never answers.
POSTGRES_URL = "postgresql+psycopg://naive_first:naive_first_dev_password@127.0.0.1:5432/naive_first"


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


def test_crawl_runs_tenant_source_fetched_at_index_exists_after_upgrade() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_ROOT,
        env={**os.environ, "DATABASE_URL": POSTGRES_URL},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    engine = create_engine(POSTGRES_URL)
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = 'ingestion' AND tablename = 'crawl_runs' "
                "AND indexname = 'ix_crawl_runs_tenant_source_fetched_at'"
            )
        ).one_or_none()
    engine.dispose()

    assert row is not None, (
        "ix_crawl_runs_tenant_source_fetched_at not found on "
        "ingestion.crawl_runs after alembic upgrade head"
    )
    indexdef = row.indexdef
    # Structural correctness: composite btree on (tenant_id, source,
    # fetched_at DESC), the exact shape the DBA specified and
    # latest_crawl_run's WHERE/ORDER BY/LIMIT query needs.
    assert "tenant_id" in indexdef
    assert "source" in indexdef
    assert "fetched_at" in indexdef
    assert "DESC" in indexdef


def test_crawl_runs_index_round_trips_through_downgrade_and_upgrade() -> None:
    env = {**os.environ, "DATABASE_URL": POSTGRES_URL}

    upgrade_result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert upgrade_result.returncode == 0, upgrade_result.stderr

    # Downgrade to the specific revision immediately before this migration
    # (0004), not a relative "-1" -- "-1" only removes the current head
    # (0006 after INGEST-018 chains after this migration), not necessarily
    # 0005 itself, once later migrations exist on top of this one. Targeting
    # 0004 explicitly keeps this test correct regardless of how many
    # migrations are later chained after 0005.
    downgrade_result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0004"],
        cwd=SERVICE_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert downgrade_result.returncode == 0, downgrade_result.stderr

    engine = create_engine(POSTGRES_URL)
    with engine.connect() as connection:
        row_after_downgrade = connection.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE schemaname = 'ingestion' AND tablename = 'crawl_runs' "
                "AND indexname = 'ix_crawl_runs_tenant_source_fetched_at'"
            )
        ).one_or_none()
    engine.dispose()
    assert row_after_downgrade is None, (
        "index still present after alembic downgrade to 0004"
    )

    reupgrade_result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert reupgrade_result.returncode == 0, reupgrade_result.stderr

    engine = create_engine(POSTGRES_URL)
    with engine.connect() as connection:
        row_after_reupgrade = connection.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE schemaname = 'ingestion' AND tablename = 'crawl_runs' "
                "AND indexname = 'ix_crawl_runs_tenant_source_fetched_at'"
            )
        ).one_or_none()
    engine.dispose()
    assert row_after_reupgrade is not None, (
        "index missing again after re-running alembic upgrade head"
    )
