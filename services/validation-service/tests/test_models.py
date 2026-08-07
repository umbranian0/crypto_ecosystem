"""VS-002: `Run`/`SplitResult` models round-trip via SQLAlchemy, tenant_id is
non-nullable on both tables, and the Alembic revision creates a schema that
matches models.py's own columns exactly.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base, Run, SplitResult

SERVICE_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def _make_run(**overrides) -> Run:
    fields = dict(
        id="run-abc123",
        tenant_id="tenant-1",
        dataset_id="dataset-1",
        horizon=1,
        purge_gap_hours=4.0,
        split_config={"train_window": 100, "test_window": 20, "step": 10},
        status="completed",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None),
        completed_at=datetime(2026, 1, 2, tzinfo=timezone.utc).replace(tzinfo=None),
        failure_reason=None,
    )
    fields.update(overrides)
    return Run(**fields)


def _make_split_result(**overrides) -> SplitResult:
    fields = dict(
        id="split-1",
        run_id="run-abc123",
        tenant_id="tenant-1",
        split_index=0,
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
    return SplitResult(**fields)


def test_run_round_trips_all_fields(engine) -> None:
    run = _make_run()
    with Session(engine) as session:
        session.add(run)
        session.commit()

    with Session(engine) as session:
        fetched = session.get(Run, "run-abc123")
        assert fetched is not None
        assert fetched.tenant_id == "tenant-1"
        assert fetched.dataset_id == "dataset-1"
        assert fetched.horizon == 1
        assert fetched.purge_gap_hours == 4.0
        assert fetched.split_config == {"train_window": 100, "test_window": 20, "step": 10}
        assert fetched.status == "completed"
        assert fetched.created_at == datetime(2026, 1, 1)
        assert fetched.completed_at == datetime(2026, 1, 2)
        assert fetched.failure_reason is None


def test_split_result_round_trips_all_fields(engine) -> None:
    with Session(engine) as session:
        session.add(_make_run())
        session.add(_make_split_result())
        session.commit()

    with Session(engine) as session:
        fetched = session.get(SplitResult, "split-1")
        assert fetched is not None
        assert fetched.run_id == "run-abc123"
        assert fetched.tenant_id == "tenant-1"
        assert fetched.split_index == 0
        assert fetched.train_start == datetime(2026, 1, 1)
        assert fetched.train_end == datetime(2026, 1, 10)
        assert fetched.purge_start == datetime(2026, 1, 10)
        assert fetched.purge_end == datetime(2026, 1, 11)
        assert fetched.test_start == datetime(2026, 1, 11)
        assert fetched.test_end == datetime(2026, 1, 15)
        assert fetched.model_mae == 0.1
        assert fetched.model_rmse == 0.2
        assert fetched.model_smape == 0.3
        assert fetched.model_mase == 0.4
        assert fetched.model_da == 0.5
        assert fetched.model_f1 == 0.6
        assert fetched.model_oos_r2 == 0.7
        assert fetched.naive0_mae == 0.11
        assert fetched.naive0_rmse == 0.21
        assert fetched.naive0_smape == 0.31
        assert fetched.naive0_mase == 0.41
        assert fetched.naive0_da == 0.51
        assert fetched.naive0_f1 == 0.61
        assert fetched.naive0_oos_r2 == 0.71
        assert fetched.dm_statistic == 1.23
        assert fetched.dm_pvalue == 0.04
        assert fetched.dm_verdict == "better"


def test_split_result_purge_start_end_nullable(engine) -> None:
    # SplitBoundaries.purge_start/end are pd.Timestamp | None (no-purge-gap splits).
    with Session(engine) as session:
        session.add(_make_run())
        session.add(_make_split_result(id="split-2", purge_start=None, purge_end=None))
        session.commit()

    with Session(engine) as session:
        fetched = session.get(SplitResult, "split-2")
        assert fetched.purge_start is None
        assert fetched.purge_end is None


def test_run_requires_tenant_id(engine) -> None:
    with Session(engine) as session:
        session.add(_make_run(tenant_id=None))
        with pytest.raises(IntegrityError):
            session.commit()


def test_split_result_requires_tenant_id(engine) -> None:
    with Session(engine) as session:
        session.add(_make_run())
        session.commit()

    with Session(engine) as session:
        session.add(_make_split_result(tenant_id=None))
        with pytest.raises(IntegrityError):
            session.commit()


def test_alembic_upgrade_head_creates_matching_schema(tmp_path) -> None:
    db_path = tmp_path / "alembic_scratch.db"
    env = {"DATABASE_URL": f"sqlite:///{db_path}"}
    import os

    full_env = {**os.environ, **env}

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_ROOT,
        env=full_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"runs", "split_results"}.issubset(tables)

    run_columns = {c["name"] for c in inspector.get_columns("runs")}
    split_columns = {c["name"] for c in inspector.get_columns("split_results")}

    expected_run_columns = {c.name for c in Run.__table__.columns}
    expected_split_columns = {c.name for c in SplitResult.__table__.columns}

    assert run_columns == expected_run_columns
    assert split_columns == expected_split_columns
    engine.dispose()
