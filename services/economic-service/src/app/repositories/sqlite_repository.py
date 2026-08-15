"""ECON-002: interim SQLite-backed implementation of `EconomicInputRepository`
(interfaces.py), storing `app.models.FeeSchedule`/`SlippageModel`/
`SimulationConfig` rows in a file-based SQLite database so state survives a
process restart -- mirrors `validation-service`'s own VS-004 precedent
(`SQLiteValidationRunRepository`).

Backend choice (documented per this ticket's Design section): SQLite-only for
this ticket, not dual-backend. Backlog explicitly does not require
dual-backend on day one, and this keeps the sprint fully self-contained (no
`infra/` dependency, no Postgres RLS wiring against real credentials). A
future ticket adding `PostgresEconomicInputRepository` behind this same DI
seam (`app.dependencies.repositories`) is the equivalent of
`validation-service`'s VS-013, not assumed here.

Conversion between `app.models` rows and `interfaces.py`'s dataclasses
happens once here (`_fee_schedule_to_record`, etc.) -- callers never build
these dataclasses by hand.

Tenant isolation: every query filters by `tenant_id` in the SQL `WHERE`
clause itself, never "fetch, then check tenant_id in Python" -- same
explicit ban as `validation-service`'s own Design section.

Engine construction uses the shared `naive_first_common.db.build_engine`
helper (ARCH-001) -- no second `create_engine` helper hand-rolled here.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from naive_first_common.db import build_engine
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.models import Base, FeeSchedule, SimulationConfig, SlippageModel
from app.repositories.interfaces import (
    FeeScheduleRecord,
    SimulationConfigRecord,
    SlippageModelRecord,
)


def _fee_schedule_to_record(row: FeeSchedule) -> FeeScheduleRecord:
    return FeeScheduleRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        venue=row.venue,
        fee_tiers=row.fee_tiers,
        created_at=row.created_at,
    )


def _slippage_model_to_record(row: SlippageModel) -> SlippageModelRecord:
    return SlippageModelRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        model_kind=row.model_kind,
        parameters=row.parameters,
        created_at=row.created_at,
    )


def _simulation_config_to_record(row: SimulationConfig) -> SimulationConfigRecord:
    return SimulationConfigRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        validation_run_id=row.validation_run_id,
        fee_schedule_id=row.fee_schedule_id,
        slippage_model_id=row.slippage_model_id,
        turnover_assumptions=row.turnover_assumptions,
        created_at=row.created_at,
    )


class SQLiteEconomicInputRepository:
    """SQLite implementation of `EconomicInputRepository` (ECON-002)."""

    def __init__(self, db_path: str, engine: Engine | None = None) -> None:
        self._engine = engine if engine is not None else build_engine(f"sqlite:///{db_path}", Base)

    def create_fee_schedule(self, tenant_id: str, venue: str, fee_tiers: dict) -> FeeScheduleRecord:
        row = FeeSchedule(
            id=uuid4().hex,
            tenant_id=tenant_id,
            venue=venue,
            fee_tiers=fee_tiers,
            created_at=datetime.utcnow(),
        )
        with Session(self._engine) as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return _fee_schedule_to_record(row)

    def get_fee_schedule(self, tenant_id: str, fee_schedule_id: str) -> FeeScheduleRecord | None:
        with Session(self._engine) as session:
            row = session.execute(
                select(FeeSchedule).where(
                    FeeSchedule.id == fee_schedule_id, FeeSchedule.tenant_id == tenant_id
                )
            ).scalar_one_or_none()
            return _fee_schedule_to_record(row) if row is not None else None

    def create_slippage_model(
        self, tenant_id: str, model_kind: str, parameters: dict
    ) -> SlippageModelRecord:
        row = SlippageModel(
            id=uuid4().hex,
            tenant_id=tenant_id,
            model_kind=model_kind,
            parameters=parameters,
            created_at=datetime.utcnow(),
        )
        with Session(self._engine) as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return _slippage_model_to_record(row)

    def get_slippage_model(self, tenant_id: str, slippage_model_id: str) -> SlippageModelRecord | None:
        with Session(self._engine) as session:
            row = session.execute(
                select(SlippageModel).where(
                    SlippageModel.id == slippage_model_id, SlippageModel.tenant_id == tenant_id
                )
            ).scalar_one_or_none()
            return _slippage_model_to_record(row) if row is not None else None

    def create_simulation_config(
        self,
        tenant_id: str,
        validation_run_id: str,
        fee_schedule_id: str,
        slippage_model_id: str,
        turnover_assumptions: dict,
    ) -> SimulationConfigRecord:
        row = SimulationConfig(
            id=uuid4().hex,
            tenant_id=tenant_id,
            validation_run_id=validation_run_id,
            fee_schedule_id=fee_schedule_id,
            slippage_model_id=slippage_model_id,
            turnover_assumptions=turnover_assumptions,
            created_at=datetime.utcnow(),
        )
        with Session(self._engine) as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return _simulation_config_to_record(row)

    def get_simulation_config(
        self, tenant_id: str, simulation_config_id: str
    ) -> SimulationConfigRecord | None:
        with Session(self._engine) as session:
            row = session.execute(
                select(SimulationConfig).where(
                    SimulationConfig.id == simulation_config_id,
                    SimulationConfig.tenant_id == tenant_id,
                )
            ).scalar_one_or_none()
            return _simulation_config_to_record(row) if row is not None else None
