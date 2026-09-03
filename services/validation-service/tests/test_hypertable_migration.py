"""INF-010: `validation.split_results` becomes a TimescaleDB hypertable,
partitioned on `test_start`, via migration 0003.

Gated exactly the same way test_postgres_repository.py's real-Postgres tests
already are -- skipped, not failed, when Postgres isn't reachable locally
(e.g. Docker not running), never mocked.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

SERVICE_ROOT = Path(__file__).resolve().parent.parent

# Matches infra/.env.example's POSTGRES_*/VALIDATION_SERVICE_DATABASE_URL
# defaults, reached via the host-published port (tests run outside Compose).
# Uses the literal loopback IP, not "localhost" -- same IPv6-hang finding
# as test_postgres_repository.py in this same directory (2026-09-01 QA
# sweep): resolving "localhost" can attempt an IPv6 (::1) connection first,
# which Docker Desktop's port-forwarding (127.0.0.1 only) never answers,
# hanging this file indefinitely instead of failing over to IPv4.
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


def test_split_results_is_a_hypertable_partitioned_on_test_start() -> None:
    import os

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
        hypertables = connection.execute(
            text(
                "SELECT hypertable_schema, hypertable_name "
                "FROM timescaledb_information.hypertables "
                "WHERE hypertable_schema = 'validation' "
                "AND hypertable_name = 'split_results'"
            )
        ).all()
        dimensions = connection.execute(
            text(
                "SELECT column_name FROM timescaledb_information.dimensions "
                "WHERE hypertable_schema = 'validation' "
                "AND hypertable_name = 'split_results'"
            )
        ).all()
    engine.dispose()

    assert len(hypertables) == 1
    assert {row.column_name for row in dimensions} == {"test_start"}
