"""SQLAlchemy 2.0 declarative models for the `economic` schema: `FeeSchedule`,
`SlippageModel`, `SimulationConfig` (ECON-002).

**Inputs-only, permanently (do not soften this note)**: these three tables
hold simulation *assumption* records -- fee tiers, slippage-model
parameters, and the config a would-be simulation would run against. None of
them stores a computed return/P&L/profitability figure, and none ever will
under this ticket's design (`ECON-002`/`ECON-010`'s Won't -- see README.md's
"Owns" section). `tests/test_no_profitability_columns.py` is the permanent,
introspection-based regression guard for this rule; it walks this module's
own `Base.metadata`, so a future column added here without updating that
test still fails it.

`SimulationConfig.validation_run_id` is a plain opaque string, never a
SQLAlchemy `ForeignKey` -- this schema must never read another service's DB
schema directly (CLAUDE.md, implementation-plan.md section 5); the only
legitimate way to reference a `validation-service` run is by the string id
`validation-service`'s own REST API already hands out.

Backend-agnostic (portable SQLAlchemy types only), mirroring
`validation-service`'s `app/models.py` precedent: same model classes serve
both the interim SQLite repository (`sqlite_repository.py`) and the Alembic
migration (`migrations/versions/0001_create_economic_schema.py`), so the
schema has a single source of truth.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid_hex() -> str:
    return uuid.uuid4().hex


class FeeSchedule(Base):
    __tablename__ = "fee_schedules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid_hex)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    venue: Mapped[str] = mapped_column(String, nullable=False)
    # List of tier dicts (e.g. maker/taker bps by volume threshold) -- one
    # JSON column instead of a column per tier, same rationale as
    # validation-service's `Run.split_config`.
    fee_tiers: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class SlippageModel(Base):
    __tablename__ = "slippage_models"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid_hex)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    # e.g. "fixed_bps" | "linear" | "square_root" -- the slippage curve shape,
    # not a computed slippage figure.
    model_kind: Mapped[str] = mapped_column(String, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class SimulationConfig(Base):
    __tablename__ = "simulation_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid_hex)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    # Opaque string/UUID handed out by validation-service's own REST API --
    # never a ForeignKey into another service's schema (see module docstring).
    validation_run_id: Mapped[str] = mapped_column(String, nullable=False)
    # FK within this same schema is fine (implementation-plan.md section 5
    # only forbids cross-*service* FKs) -- referential integrity for a
    # config's own fee/slippage assumption records.
    fee_schedule_id: Mapped[str] = mapped_column(
        String, ForeignKey("fee_schedules.id"), nullable=False
    )
    slippage_model_id: Mapped[str] = mapped_column(
        String, ForeignKey("slippage_models.id"), nullable=False
    )
    # Turnover assumption and any other simulation-input knobs -- one JSON
    # column rather than a column per knob, same rationale as `fee_tiers`.
    turnover_assumptions: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
