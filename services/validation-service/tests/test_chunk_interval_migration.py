"""VS-027: `validation.split_results` chunk_time_interval retuned to 90 days
via migration 0007.

Gated exactly the same way test_hypertable_migration.py/
test_postgres_repository.py's real-Postgres tests already are -- skipped,
not failed, when Postgres isn't reachable locally (e.g. Docker not
running), never mocked.

Deliberately does NOT assert the existing 108 chunks' count decreases or
that any existing chunk changed size (per this ticket's Test acceptance
criteria) -- set_chunk_time_interval only affects chunks created after the
call, it does not retroactively resize or merge pre-existing chunks. This
test only checks timescaledb_information.dimensions reflects the new
interval, plus a rolled-back probe insert far beyond the current time range
to demonstrate the new interval genuinely governs a newly created chunk.
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

# Matches infra/.env.example's POSTGRES_*/VALIDATION_SERVICE_DATABASE_URL
# defaults, reached via the host-published port (tests run outside Compose).
# Uses the literal loopback IP, not "localhost" -- same IPv6-hang finding as
# test_postgres_repository.py/test_hypertable_migration.py in this same
# directory (2026-09-01 QA sweep): resolving "localhost" can attempt an
# IPv6 (::1) connection first, which Docker Desktop's port-forwarding
# (127.0.0.1 only) never answers, hanging this file indefinitely instead of
# failing over to IPv4.
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


def test_split_results_chunk_time_interval_retuned_to_90_days() -> None:
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
                "SELECT time_interval FROM timescaledb_information.dimensions "
                "WHERE hypertable_schema = 'validation' "
                "AND hypertable_name = 'split_results'"
            )
        ).one()
    engine.dispose()

    # timescaledb_information.dimensions.time_interval comes back to
    # psycopg3 as a native datetime.timedelta for a time-partitioned
    # dimension -- not a string -- so compare against timedelta(days=90)
    # directly rather than a formatted interval string (same convention as
    # ingestion-service's test_hypertable_chunk_interval_migration.py).
    assert row.time_interval == timedelta(days=90), (
        f"split_results time_interval is {row.time_interval!r}, "
        "expected timedelta(days=90)"
    )


def test_new_chunk_created_far_in_the_future_spans_90_days_not_7() -> None:
    """Rolled-back probe insert (never persisted): proves the new 90-day
    interval genuinely governs a newly created chunk, without leaving a
    probe row in this real, UAT-carrying table and without asserting
    anything about the pre-existing 108 chunks.
    """
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_ROOT,
        env={**os.environ, "DATABASE_URL": POSTGRES_URL},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    engine = create_engine(POSTGRES_URL)
    try:
        with engine.connect() as connection:
            with connection.begin() as transaction:
                connection.execute(text("SET LOCAL search_path TO validation"))
                # RLS on both tables is FORCE-enforced even for the owning
                # role (0002_add_row_level_security.py) -- both the parent
                # `runs` row (FK target of split_results.run_id) and the
                # probe split row must be inserted under the same
                # app.tenant_id GUC, mirroring postgres_repository.py's own
                # "SET LOCAL app.tenant_id" convention.
                connection.execute(
                    text("SET LOCAL app.tenant_id = 'vs-027-probe-tenant'")
                )
                connection.execute(
                    text(
                        "INSERT INTO runs ("
                        "id, tenant_id, dataset_id, horizon, "
                        "purge_gap_hours, split_config, status, created_at"
                        ") VALUES ("
                        "'vs-027-probe-run', 'vs-027-probe-tenant', "
                        "'vs-027-probe-dataset', 1, 0.0, '{}', "
                        "'completed', '2999-01-01'"
                        ")"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO split_results ("
                        "id, run_id, tenant_id, split_index, "
                        "train_start, train_end, purge_start, purge_end, "
                        "test_start, test_end, "
                        "model_mae, model_rmse, model_smape, model_mase, "
                        "model_da, model_f1, model_oos_r2, "
                        "naive0_mae, naive0_rmse, naive0_smape, naive0_mase, "
                        "naive0_da, naive0_f1, naive0_oos_r2, "
                        "dm_statistic, dm_pvalue, dm_verdict"
                        ") VALUES ("
                        "'vs-027-probe-row', 'vs-027-probe-run', "
                        "'vs-027-probe-tenant', 0, "
                        "'2999-01-01', '2999-01-02', '2999-01-02', "
                        "'2999-01-03', '2999-01-03', '2999-01-04', "
                        "0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "
                        "0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "
                        "0.0, 1.0, 'no significant difference'"
                        ")"
                    )
                )
                chunk_row = connection.execute(
                    text(
                        "SELECT c.range_start, c.range_end "
                        "FROM timescaledb_information.chunks c "
                        "WHERE c.hypertable_schema = 'validation' "
                        "AND c.hypertable_name = 'split_results' "
                        "AND c.range_start > TIMESTAMP '2998-01-01'"
                    )
                ).one()
                span = chunk_row.range_end - chunk_row.range_start
                assert span == timedelta(days=90), (
                    f"probe chunk span is {span!r}, expected timedelta(days=90)"
                )
                transaction.rollback()
    finally:
        engine.dispose()