"""SQLAlchemy 2.0 declarative models for the `economic` schema: `FeeSchedule`,
`SlippageModel`, `SimulationConfig` (ECON-002), `BacktestResult` (ECON-013).

**Inputs-only, permanently, for the first three tables (do not soften this
note)**: `FeeSchedule`/`SlippageModel`/`SimulationConfig` hold simulation
*assumption* records -- fee tiers, slippage-model parameters, and the config
a would-be simulation would run against. None of them stores a computed
return/P&L/profitability figure, and none ever will under this ticket's
design (`ECON-002`/`ECON-010`'s Won't -- see README.md's "Owns" section).
`tests/test_no_profitability_columns.py` is the permanent, introspection-based
regression guard for this rule; it walks this module's own `Base.metadata`,
so a future column added here without updating that test still fails it.

**`BacktestResult` (`backtest_results`, ECON-013) is the one narrow,
separately-authorized exception to that Won't**, per this ticket's own
Analysis section: it persists ONLY rows that have already passed
`ECON-005`'s unmodified structural eligibility gate -- never a row for a
`NotEligibleForSimulation` refusal (nothing to store there, matching this
same module's own "inputs/earned-outputs only, never a placeholder" design
decision, extended -- not contradicted -- by this table: an *earned* output
is exactly what this table stores, once and only once a real gate-pass has
occurred). `tests/test_no_profitability_columns.py` is updated accordingly
to carve out this one table's `return`-containing column names (see that
file's own docstring for the exact, narrow scope of the carve-out) while
still rejecting `pnl`/`profit`/`net_return`/`revenue`/`forecast_*`/`win`/
`expected_return`-shaped names on this table exactly as on the other three.

`SimulationConfig.validation_run_id` is a plain opaque string, never a
SQLAlchemy `ForeignKey` -- this schema must never read another service's DB
schema directly (CLAUDE.md, implementation-plan.md section 5); the only
legitimate way to reference a `validation-service` run is by the string id
`validation-service`'s own REST API already hands out. `BacktestResult.run_id`
is the same kind of plain opaque string, for the same reason.

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


# Fixed, application-level constant (ECON-013 Design section: "a plain
# String column with an application-level constant default ... implementer's
# choice, document which") -- a CheckConstraint was the other option
# considered, but a plain Python-side default keeps this table's tagging
# mechanism consistent with `_uuid_hex()`'s own existing default-callable
# pattern above rather than introducing a second, DB-engine-specific
# constraint style into this module.
RESULT_KIND_RETROSPECTIVE_BACKTEST = "retrospective_backtest"


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


class BacktestResult(Base):
    """ECON-013: persists ONLY the eligible-branch rows of `POST /backtests`
    (`routers/backtests.py`) -- see module docstring above for why this one
    table is a narrow, separately-authorized exception to this schema's
    otherwise-permanent inputs-only rule. Write-once (no update/delete method
    exists on `BacktestResultRepository`, `repositories/interfaces.py`).
    """

    __tablename__ = "backtest_results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid_hex)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    # Groups every row persisted from one single POST /backtests call --
    # generated once per request in routers/backtests.py, not per run_id.
    backtest_id: Mapped[str] = mapped_column(String, nullable=False)
    # Opaque string handed out by validation-service, never a ForeignKey --
    # same rationale as SimulationConfig.validation_run_id above.
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    fee_schedule_id: Mapped[str] = mapped_column(
        String, ForeignKey("fee_schedules.id"), nullable=False
    )
    slippage_model_id: Mapped[str] = mapped_column(
        String, ForeignKey("slippage_models.id"), nullable=False
    )
    cost_adjusted_return: Mapped[float] = mapped_column(Float, nullable=False)
    slippage_adjusted_return: Mapped[float] = mapped_column(Float, nullable=False)
    total_cost_bps: Mapped[float] = mapped_column(Float, nullable=False)
    upstream_dm_statistic: Mapped[float] = mapped_column(Float, nullable=False)
    upstream_dm_pvalue: Mapped[float] = mapped_column(Float, nullable=False)
    upstream_dm_verdict: Mapped[str] = mapped_column(String, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Fixed tag, always RESULT_KIND_RETROSPECTIVE_BACKTEST -- never a caller-
    # settable parameter on the repository's create method (see
    # sqlite_repository.py), so no caller can construct any other value.
    result_kind: Mapped[str] = mapped_column(
        String, nullable=False, default=RESULT_KIND_RETROSPECTIVE_BACKTEST
    )
