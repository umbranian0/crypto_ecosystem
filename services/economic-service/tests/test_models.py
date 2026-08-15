"""ECON-002: `FeeSchedule`/`SlippageModel`/`SimulationConfig` models round-trip
via SQLAlchemy, `tenant_id` is non-nullable on all three tables, and the
Alembic revision creates a schema that matches models.py's own columns
exactly. Mirrors validation-service's own `tests/test_models.py` shape.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base, FeeSchedule, SimulationConfig, SlippageModel

SERVICE_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def _make_fee_schedule(**overrides) -> FeeSchedule:
    fields = dict(
        id="fee-1",
        tenant_id="tenant-1",
        venue="binance",
        fee_tiers=[{"volume_gte": 0, "maker_bps": 10, "taker_bps": 15}],
        created_at=datetime(2026, 1, 1),
    )
    fields.update(overrides)
    return FeeSchedule(**fields)


def _make_slippage_model(**overrides) -> SlippageModel:
    fields = dict(
        id="slip-1",
        tenant_id="tenant-1",
        model_kind="linear",
        parameters={"impact_coefficient": 0.05},
        created_at=datetime(2026, 1, 1),
    )
    fields.update(overrides)
    return SlippageModel(**fields)


def _make_simulation_config(**overrides) -> SimulationConfig:
    fields = dict(
        id="sim-1",
        tenant_id="tenant-1",
        validation_run_id="run-abc123",
        fee_schedule_id="fee-1",
        slippage_model_id="slip-1",
        turnover_assumptions={"daily_turnover_pct": 5.0},
        created_at=datetime(2026, 1, 1),
    )
    fields.update(overrides)
    return SimulationConfig(**fields)


def test_fee_schedule_round_trips_all_fields(engine) -> None:
    with Session(engine) as session:
        session.add(_make_fee_schedule())
        session.commit()

    with Session(engine) as session:
        fetched = session.get(FeeSchedule, "fee-1")
        assert fetched is not None
        assert fetched.tenant_id == "tenant-1"
        assert fetched.venue == "binance"
        assert fetched.fee_tiers == [{"volume_gte": 0, "maker_bps": 10, "taker_bps": 15}]
        assert fetched.created_at == datetime(2026, 1, 1)


def test_slippage_model_round_trips_all_fields(engine) -> None:
    with Session(engine) as session:
        session.add(_make_slippage_model())
        session.commit()

    with Session(engine) as session:
        fetched = session.get(SlippageModel, "slip-1")
        assert fetched is not None
        assert fetched.tenant_id == "tenant-1"
        assert fetched.model_kind == "linear"
        assert fetched.parameters == {"impact_coefficient": 0.05}
        assert fetched.created_at == datetime(2026, 1, 1)


def test_simulation_config_round_trips_all_fields(engine) -> None:
    with Session(engine) as session:
        session.add(_make_fee_schedule())
        session.add(_make_slippage_model())
        session.add(_make_simulation_config())
        session.commit()

    with Session(engine) as session:
        fetched = session.get(SimulationConfig, "sim-1")
        assert fetched is not None
        assert fetched.tenant_id == "tenant-1"
        assert fetched.validation_run_id == "run-abc123"
        assert fetched.fee_schedule_id == "fee-1"
        assert fetched.slippage_model_id == "slip-1"
        assert fetched.turnover_assumptions == {"daily_turnover_pct": 5.0}
        assert fetched.created_at == datetime(2026, 1, 1)


def test_fee_schedule_requires_tenant_id(engine) -> None:
    with Session(engine) as session:
        session.add(_make_fee_schedule(tenant_id=None))
        with pytest.raises(IntegrityError):
            session.commit()


def test_slippage_model_requires_tenant_id(engine) -> None:
    with Session(engine) as session:
        session.add(_make_slippage_model(tenant_id=None))
        with pytest.raises(IntegrityError):
            session.commit()


def test_simulation_config_requires_tenant_id(engine) -> None:
    with Session(engine) as session:
        session.add(_make_fee_schedule())
        session.add(_make_slippage_model())
        session.commit()

    with Session(engine) as session:
        session.add(_make_simulation_config(tenant_id=None))
        with pytest.raises(IntegrityError):
            session.commit()


def test_simulation_config_validation_run_id_is_not_a_foreign_key(engine) -> None:
    """Load-bearing per the ticket's Review acceptance criteria:
    `validation_run_id` must be a plain opaque string column, never a
    SQLAlchemy `ForeignKey` into another service's schema.
    """
    column = SimulationConfig.__table__.columns["validation_run_id"]
    assert list(column.foreign_keys) == []


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
    assert {"fee_schedules", "slippage_models", "simulation_configs"}.issubset(tables)

    fee_columns = {c["name"] for c in inspector.get_columns("fee_schedules")}
    slippage_columns = {c["name"] for c in inspector.get_columns("slippage_models")}
    sim_columns = {c["name"] for c in inspector.get_columns("simulation_configs")}

    assert fee_columns == {c.name for c in FeeSchedule.__table__.columns}
    assert slippage_columns == {c.name for c in SlippageModel.__table__.columns}
    assert sim_columns == {c.name for c in SimulationConfig.__table__.columns}
    engine.dispose()
