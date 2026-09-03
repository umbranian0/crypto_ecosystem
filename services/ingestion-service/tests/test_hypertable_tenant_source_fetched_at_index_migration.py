"""INGEST-018: price_ohlcv/onchain_metric/sentiment_score (tenant_id,
source, fetched_at) composite indexes, added via migration 0006.

Gated exactly the same way this service's other real-Postgres migration
tests (`test_hypertable_chunk_interval_migration.py`,
`test_crawl_runs_index_migration.py`) already are -- skipped, not failed,
when Postgres isn't reachable locally (e.g. Docker not running), never
mocked.

Also proves the same TimescaleDB root-to-existing-chunk index propagation
`VS-026` (`validation-service`) confirmed for `validation.split_results` --
independently re-verified here for `price_ohlcv`/`onchain_metric`, rather
than assumed from VS-026's own verification, since these are hypertables
(unlike `crawl_runs`, a plain table, which 0005's own test does not need to
check chunk propagation for).
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
# test_hypertable_chunk_interval_migration.py / test_crawl_runs_index_migration.py
# -- "localhost" can hang here on an IPv6-first resolution that Docker
# Desktop's 127.0.0.1-only port forwarding never answers.
POSTGRES_URL = "postgresql+psycopg://naive_first:naive_first_dev_password@127.0.0.1:5432/naive_first"

# Same three-table order as _TABLE_SPECS (postgres_repository.py) /
# _HYPERTABLES (0003/0004) / _INDEXES (0006) -- not a fourth ad hoc list.
_INDEXES = (
    ("price_ohlcv", "ix_price_ohlcv_tenant_source_fetched_at"),
    ("onchain_metric", "ix_onchain_metric_tenant_source_fetched_at"),
    ("sentiment_score", "ix_sentiment_score_tenant_source_fetched_at"),
)


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


@pytest.mark.parametrize("table,index_name", _INDEXES)
def test_tenant_source_fetched_at_index_exists_on_root_table(table: str, index_name: str) -> None:
    _run_alembic_upgrade_head()

    engine = create_engine(POSTGRES_URL)
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = 'ingestion' AND tablename = :table "
                "AND indexname = :index_name"
            ),
            {"table": table, "index_name": index_name},
        ).one_or_none()
    engine.dispose()

    assert row is not None, (
        f"{index_name} not found on ingestion.{table} after alembic upgrade head"
    )
    indexdef = row.indexdef.lower()
    # Check the column list itself (the "(...)" after "USING btree"), not the
    # whole indexdef string -- the index name (e.g.
    # "ix_price_ohlcv_tenant_source_fetched_at") also contains the substring
    # "source", which would otherwise be found before the real "tenant_id"
    # column and produce a false ordering failure.
    column_list = indexdef[indexdef.rindex("(") :]
    assert "tenant_id" in column_list
    assert "source" in column_list
    assert "fetched_at" in column_list
    tenant_pos = column_list.index("tenant_id")
    source_pos = column_list.index("source")
    fetched_at_pos = column_list.index("fetched_at")
    assert tenant_pos < source_pos < fetched_at_pos, (
        f"expected column order (tenant_id, source, fetched_at) in {column_list!r}"
    )


@pytest.mark.parametrize("table,index_name", _INDEXES)
def test_tenant_source_fetched_at_index_propagated_to_existing_chunks(
    table: str, index_name: str
) -> None:
    """Proves this migration's own root-level CREATE INDEX on a TimescaleDB
    hypertable propagates to every existing chunk, not only chunks created
    after the migration runs -- same verification approach VS-026 used for
    `validation.split_results` (`timescaledb_information.chunks` joined
    against `pg_indexes` on the real chunk relation names), independently
    re-run here rather than trusted from that service's own result.
    """
    _run_alembic_upgrade_head()

    engine = create_engine(POSTGRES_URL)
    with engine.connect() as connection:
        chunk_rows = connection.execute(
            text(
                "SELECT chunk_schema, chunk_name FROM timescaledb_information.chunks "
                "WHERE hypertable_schema = 'ingestion' "
                "AND hypertable_name = :table "
                "LIMIT 10"
            ),
            {"table": table},
        ).all()
        if not chunk_rows:
            pytest.skip(
                f"ingestion.{table} has zero existing chunks in this "
                f"environment (no rows ingested yet) -- the propagation "
                f"claim cannot be exercised without at least one real chunk; "
                f"see the live EXPLAIN/chunk-propagation proof for "
                f"price_ohlcv/onchain_metric in this ticket's Outcome notes, "
                f"which do have real backfilled data"
            )

        for chunk in chunk_rows:
            index_rows = connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = :schema AND tablename = :table "
                    "AND indexname LIKE :pattern"
                ),
                {"schema": chunk.chunk_schema, "table": chunk.chunk_name, "pattern": f"%{index_name}%"},
            ).all()
            assert len(index_rows) == 1, (
                f"expected a propagated {index_name}-derived index on chunk "
                f"{chunk.chunk_schema}.{chunk.chunk_name}, found {len(index_rows)}"
            )
            indexdef = index_rows[0].indexdef.lower()
            assert "tenant_id" in indexdef
            assert "source" in indexdef
            assert "fetched_at" in indexdef
    engine.dispose()


def test_tenant_source_fetched_at_indexes_round_trip_through_downgrade_and_upgrade() -> None:
    env = {**os.environ, "DATABASE_URL": POSTGRES_URL}

    upgrade_result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert upgrade_result.returncode == 0, upgrade_result.stderr

    # Target the explicit revision immediately before this migration (0005),
    # not a relative "-1" -- same fix applied to
    # test_crawl_runs_index_migration.py's own round-trip test for the same
    # reason: "-1" only removes the current head, which stops being this
    # migration's own revision once a later migration is chained after 0006.
    downgrade_result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0005"],
        cwd=SERVICE_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert downgrade_result.returncode == 0, downgrade_result.stderr

    engine = create_engine(POSTGRES_URL)
    with engine.connect() as connection:
        for table, index_name in _INDEXES:
            row = connection.execute(
                text(
                    "SELECT 1 FROM pg_indexes "
                    "WHERE schemaname = 'ingestion' AND tablename = :table "
                    "AND indexname = :index_name"
                ),
                {"table": table, "index_name": index_name},
            ).one_or_none()
            assert row is None, f"{index_name} still present after alembic downgrade to 0005"
    engine.dispose()

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
        for table, index_name in _INDEXES:
            row = connection.execute(
                text(
                    "SELECT 1 FROM pg_indexes "
                    "WHERE schemaname = 'ingestion' AND tablename = :table "
                    "AND indexname = :index_name"
                ),
                {"table": table, "index_name": index_name},
            ).one_or_none()
            assert row is not None, f"{index_name} missing again after re-running alembic upgrade head"
    engine.dispose()