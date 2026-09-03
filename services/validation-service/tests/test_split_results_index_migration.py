"""VS-026: `validation.split_results` gains a composite index on
`(tenant_id, run_id)`, via migration 0006 -- issued against the hypertable's
root table, and confirmed here to propagate to existing chunks (not just the
root), proving the version-propagation assumption stated in VS-026's
Analysis section rather than trusting it.

Gated exactly the same way test_postgres_repository.py's/
test_hypertable_migration.py's/test_index_migration.py's real-Postgres tests
already are -- skipped, not failed, when Postgres isn't reachable locally
(e.g. Docker not running), never mocked.
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

# Matches infra/.env.example's POSTGRES_*/VALIDATION_SERVICE_DATABASE_URL
# defaults, reached via the host-published port (tests run outside Compose).
# Uses the literal loopback IP, not "localhost" -- same IPv6-hang finding as
# test_postgres_repository.py/test_hypertable_migration.py/
# test_index_migration.py in this same directory (2026-09-01 QA sweep):
# resolving "localhost" can attempt an IPv6 (::1) connection first, which
# Docker Desktop's port-forwarding (127.0.0.1 only) never answers, hanging
# this file indefinitely instead of failing over to IPv4.
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


def _run_alembic_upgrade_head() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_ROOT,
        env={**os.environ, "DATABASE_URL": POSTGRES_URL},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_split_results_tenant_run_index_exists_on_root_table() -> None:
    _run_alembic_upgrade_head()

    engine = create_engine(POSTGRES_URL)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = 'validation' AND tablename = 'split_results' "
                "AND indexname = 'ix_split_results_tenant_run'"
            )
        ).all()
    engine.dispose()

    assert len(rows) == 1
    indexdef = rows[0].indexdef.lower()
    assert "tenant_id" in indexdef
    assert "run_id" in indexdef


def test_split_results_tenant_run_index_propagated_to_existing_chunks() -> None:
    """Proves VS-026's Analysis-section assumption live: a root-level
    CREATE INDEX on a TimescaleDB hypertable propagates to every existing
    chunk, not only chunks created after the migration runs.

    Finds real `_hyper_*_chunk` relation names for `validation.split_results`
    via `timescaledb_information.chunks` (the catalog view this platform's
    TimescaleDB 2.29.1 exposes), then checks `pg_indexes` for a matching
    index on a sample of those chunk relations -- these chunks already
    existed before this test ran (this table has 108 chunks per the DBA's
    live finding in VS-026's ticket), so a hit here is proof of genuine
    propagation to pre-existing chunks, not just the root/future chunks.
    """
    _run_alembic_upgrade_head()

    engine = create_engine(POSTGRES_URL)
    with engine.connect() as connection:
        chunk_rows = connection.execute(
            text(
                "SELECT chunk_schema, chunk_name FROM timescaledb_information.chunks "
                "WHERE hypertable_schema = 'validation' "
                "AND hypertable_name = 'split_results' "
                "LIMIT 10"
            )
        ).all()
        assert len(chunk_rows) > 0, (
            "expected at least one existing chunk on validation.split_results "
            "to sample -- if this table has zero chunks the propagation claim "
            "below can't actually be exercised"
        )

        for chunk in chunk_rows:
            index_rows = connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = :schema AND tablename = :table "
                    "AND indexname LIKE '%ix_split_results_tenant_run%'"
                ),
                {"schema": chunk.chunk_schema, "table": chunk.chunk_name},
            ).all()
            assert len(index_rows) == 1, (
                f"expected a propagated ix_split_results_tenant_run-derived "
                f"index on chunk {chunk.chunk_schema}.{chunk.chunk_name}, "
                f"found {len(index_rows)}"
            )
            indexdef = index_rows[0].indexdef.lower()
            assert "tenant_id" in indexdef
            assert "run_id" in indexdef
    engine.dispose()