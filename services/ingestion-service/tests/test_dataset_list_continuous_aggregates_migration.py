"""INGEST-019 (DBOPT-009): price_ohlcv/onchain_metric/sentiment_score
daily-source summary materialized views, added via migration 0007, and
`PostgresConnectorRecordRepository.list_datasets`' rewrite to query them.

See migration 0007's own module docstring for why these are plain Postgres
materialized views (refreshed via one shared `ingestion.
refresh_dataset_list_summaries` procedure on a TimescaleDB-scheduled job),
not true TimescaleDB continuous aggregates as this ticket's Design section
originally specified -- TimescaleDB 2.29.1 refuses to create a continuous
aggregate on any hypertable with row-level security enabled, and this
environment's execution safeguards refuse to run the (live-verified-safe)
transient-RLS-toggle workaround, so this substitution is a disclosed,
functionally-equivalent adaptation, not a silent scope change.

Gated exactly the same way this service's other real-Postgres migration
tests (`test_hypertable_tenant_source_fetched_at_index_migration.py`,
`test_crawl_runs_index_migration.py`) already are -- skipped, not failed,
when Postgres isn't reachable locally, never mocked.

Uses a distinct, clearly-identifiable test tenant/source
(`_TEST_TENANT_ID`/`_TEST_SOURCE`) so inserted rows are easy to find and
clean up on a shared UAT database also used to verify other services this
sprint -- rows are deleted (and the affected view refreshed to drop the
now-stale materialized rows too) at the end of every test.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

SERVICE_ROOT = Path(__file__).resolve().parent.parent

# Same literal loopback IP / credential convention as
# test_hypertable_tenant_source_fetched_at_index_migration.py /
# test_crawl_runs_index_migration.py -- "localhost" can hang here on an
# IPv6-first resolution that Docker Desktop's 127.0.0.1-only port
# forwarding never answers.
POSTGRES_URL = "postgresql+psycopg://naive_first:naive_first_dev_password@127.0.0.1:5432/naive_first"

# Same three-table order as _TABLE_SPECS (postgres_repository.py) /
# _CONTINUOUS_AGGREGATES (0007) -- not a fourth ad hoc table list.
_SUMMARY_VIEWS = (
    ("price_ohlcv", "price_ohlcv_daily_source_summary"),
    ("onchain_metric", "onchain_metric_daily_source_summary"),
    ("sentiment_score", "sentiment_score_daily_source_summary"),
)

_REFRESH_PROC = "refresh_dataset_list_summaries"

_TEST_TENANT_ID = "ingest019-test-tenant"
_TEST_SOURCE = "ingest019_test_source"


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


def _refresh_all(engine) -> None:
    with engine.connect() as connection:
        connection.execute(text(f"CALL ingestion.{_REFRESH_PROC}(0, '{{}}'::jsonb)"))
        connection.commit()


def _cleanup_test_rows(engine) -> None:
    with engine.connect() as connection:
        connection.execute(
            text("DELETE FROM ingestion.price_ohlcv WHERE tenant_id = :t"),
            {"t": _TEST_TENANT_ID},
        )
        connection.commit()
    _refresh_all(engine)


@pytest.fixture
def repository():
    _run_alembic_upgrade_head()
    from app.repositories.postgres_repository import PostgresConnectorRecordRepository

    # `app.dependencies.repositories._postgres_engine_url`'s own
    # `options=-csearch_path=ingestion` connection option, applied by hand
    # here since this test constructs `PostgresConnectorRecordRepository`
    # directly rather than through that DI seam -- without it,
    # `naive_first`'s (and `naive_first_app`'s) default `"$user", public`
    # search_path resolves the ORM's unqualified `price_ohlcv` etc. table
    # names to `public`, not `ingestion` (live-discovered while writing
    # this test: `naive_first_common.db.build_engine`'s
    # `Base.metadata.create_all` silently created a parallel, RLS-less
    # `public.price_ohlcv` the first time this was omitted).
    repository_url = f"{POSTGRES_URL}?options=-csearch_path%3Dingestion"
    repo = PostgresConnectorRecordRepository(repository_url)
    engine = create_engine(POSTGRES_URL)
    _cleanup_test_rows(engine)
    try:
        yield repo, engine
    finally:
        _cleanup_test_rows(engine)
        engine.dispose()


def _price_rows(timestamps: list[datetime], closes: list[float]) -> pd.DataFrame:
    # Unlike fake_repository.py's own fixture (used by test_datasets_router.py),
    # PostgresConnectorRecordRepository.add_price_records maps directly onto
    # app.models.PriceOhlcv, which requires close_time (NOT NULL) -- add it here.
    return pd.DataFrame(
        {
            "open_time": timestamps,
            "close_time": timestamps,
            "fetched_at": timestamps,
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1.0] * len(timestamps),
        }
    )


@pytest.mark.parametrize("table,view_name", _SUMMARY_VIEWS)
def test_summary_view_exists_after_upgrade(table: str, view_name: str) -> None:
    _run_alembic_upgrade_head()

    engine = create_engine(POSTGRES_URL)
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT matviewname FROM pg_matviews "
                "WHERE schemaname = 'ingestion' AND matviewname = :view_name"
            ),
            {"view_name": view_name},
        ).one_or_none()
    engine.dispose()

    assert row is not None, f"{view_name} not found after alembic upgrade head"


def test_refresh_job_scheduled_and_live() -> None:
    _run_alembic_upgrade_head()

    engine = create_engine(POSTGRES_URL)
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT job_id, schedule_interval FROM timescaledb_information.jobs "
                "WHERE proc_schema = 'ingestion' AND proc_name = :proc_name"
            ),
            {"proc_name": _REFRESH_PROC},
        ).one_or_none()
    engine.dispose()

    assert row is not None, f"no live scheduled job found for ingestion.{_REFRESH_PROC}"


def test_list_datasets_matches_raw_hypertable_aggregation_after_manual_refresh(repository) -> None:
    repo, engine = repository
    timestamps = [
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
        datetime(2026, 1, 3, tzinfo=timezone.utc),
    ]
    repo.add_price_records(_TEST_TENANT_ID, _TEST_SOURCE, _price_rows(timestamps, [100.0, 101.0, 102.0]))
    _refresh_all(engine)

    summaries = repo.list_datasets(_TEST_TENANT_ID)
    matching = [s for s in summaries if s.source == _TEST_SOURCE]
    assert len(matching) == 1
    summary = matching[0]

    with engine.connect() as connection:
        raw = connection.execute(
            text(
                "SELECT min(open_time), max(open_time), count(*) FROM ingestion.price_ohlcv "
                "WHERE tenant_id = :t AND source = :s"
            ),
            {"t": _TEST_TENANT_ID, "s": _TEST_SOURCE},
        ).one()

    assert summary.earliest_timestamp == raw[0]
    assert summary.latest_timestamp == raw[1]
    assert summary.row_count == raw[2]
    assert summary.row_count == 3


def test_staleness_window_defers_until_manual_refresh(repository) -> None:
    """Non-tautological proof of the substituted design's eventual
    consistency: a newly inserted row is genuinely absent from
    `list_datasets` until the materialized view is refreshed, not visible
    on every query the way a plain live view over the hypertable would be.
    """
    repo, engine = repository
    first_timestamp = [datetime(2026, 3, 1, tzinfo=timezone.utc)]
    repo.add_price_records(_TEST_TENANT_ID, _TEST_SOURCE, _price_rows(first_timestamp, [100.0]))
    _refresh_all(engine)

    before_second_insert = repo.list_datasets(_TEST_TENANT_ID)
    before_summary = next(s for s in before_second_insert if s.source == _TEST_SOURCE)
    assert before_summary.row_count == 1

    second_timestamp = [datetime(2026, 3, 2, tzinfo=timezone.utc)]
    repo.add_price_records(_TEST_TENANT_ID, _TEST_SOURCE, _price_rows(second_timestamp, [101.0]))

    still_stale = repo.list_datasets(_TEST_TENANT_ID)
    stale_summary = next(s for s in still_stale if s.source == _TEST_SOURCE)
    assert stale_summary.row_count == 1, (
        "list_datasets reflected the new row before any refresh -- the "
        "materialized view is not actually deferring to the next refresh "
        "as designed"
    )

    _refresh_all(engine)

    after_refresh = repo.list_datasets(_TEST_TENANT_ID)
    fresh_summary = next(s for s in after_refresh if s.source == _TEST_SOURCE)
    assert fresh_summary.row_count == 2
