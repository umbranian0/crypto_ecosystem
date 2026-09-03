"""INGEST-016: price_ohlcv/onchain_metric/sentiment_score chunk_time_interval
retuned to 90 days via migration 0004.

Gated exactly the same way validation-service's test_hypertable_migration.py/
test_postgres_repository.py real-Postgres tests already are -- skipped, not
failed, when Postgres isn't reachable locally (e.g. Docker not running),
never mocked.

Deliberately does NOT assert existing chunk counts decrease for any of the
three tables (per this ticket's Test acceptance criteria) --
set_chunk_time_interval only affects chunks created after the call, it does
not retroactively resize or merge pre-existing chunks. This test only checks
timescaledb_information.dimensions reflects the new interval.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

SERVICE_ROOT = Path(__file__).resolve().parent.parent

# Matches infra/.env.example's POSTGRES_*/migration-time superuser
# credentials, reached via the host-published port (tests run outside
# Compose). Uses the literal loopback IP, not "localhost" -- same
# IPv6-hang finding as validation-service's test_postgres_repository.py/
# test_hypertable_migration.py (2026-09-01 QA sweep): resolving "localhost"
# can attempt an IPv6 (::1) connection first, which Docker Desktop's
# port-forwarding (127.0.0.1 only) never answers, hanging this file
# indefinitely instead of failing over to IPv4.
POSTGRES_URL = "postgresql+psycopg://naive_first:naive_first_dev_password@127.0.0.1:5432/naive_first"

_HYPERTABLES = ("price_ohlcv", "onchain_metric", "sentiment_score")


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


def test_chunk_time_interval_retuned_to_90_days_for_all_three_hypertables() -> None:
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
        rows = connection.execute(
            text(
                "SELECT hypertable_name, time_interval "
                "FROM timescaledb_information.dimensions "
                "WHERE hypertable_schema = 'ingestion' "
                "AND hypertable_name = ANY(:tables)"
            ),
            {"tables": list(_HYPERTABLES)},
        ).all()
    engine.dispose()

    intervals = {row.hypertable_name: row.time_interval for row in rows}
    assert set(intervals) == set(_HYPERTABLES)
    for table, interval in intervals.items():
        # timescaledb_information.dimensions.time_interval comes back to
        # psycopg3 as a native datetime.timedelta for a time-partitioned
        # dimension -- not a string -- so compare against timedelta(days=90)
        # directly rather than a formatted interval string.
        assert interval == timedelta(days=90), (
            f"{table} time_interval is {interval!r}, expected timedelta(days=90)"
        )
