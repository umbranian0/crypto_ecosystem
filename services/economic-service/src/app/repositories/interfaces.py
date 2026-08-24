"""Repository interfaces (implementation-plan.md section 7) for ECON-002's
inputs-only `economic` schema: `EconomicInputRepository`, plus ECON-013's
separate, guard-gated write path: `BacktestResultRepository`.

Single Protocol, one method group per table (design decision, documented per
this ticket's own "one Protocol per table, or one umbrella Protocol --
implementer's choice" instruction): all three tables
(`fee_schedules`/`slippage_models`/`simulation_configs`) are always read and
written together by the same caller (a simulation config always references a
fee schedule and a slippage model), so a single umbrella Protocol avoids
three near-identical interfaces with no independent caller ever needing just
one of them -- mirrors `validation-service`'s own two-Protocol split only
where two genuinely independent tables existed (`runs`/`split_results`); here
there is one natural caller-facing seam, not three.

Record types (mirrors `validation-service/src/app/repositories/interfaces.py`
verbatim in style): `FeeScheduleRecord`, `SlippageModelRecord`,
`SimulationConfigRecord` are plain `@dataclass(frozen=True)` types local to
this module, field-for-field mirrors of `app.models`'s SQLAlchemy models,
rather than reusing those models directly -- reusing them would pull
`sqlalchemy` into this module's import graph transitively, defeating this
ticket's own "zero sqlalchemy import in the interface module" requirement
even if no SQLAlchemy name were used directly in a method signature here.
`sqlite_repository.py` owns the conversion between these records and
`app.models` rows.

Protocol vs ABC: `typing.Protocol`, not `abc.ABC` -- no shared default method
is needed, matching `validation-service`'s own binding decision.

Every method's first parameter after `self` is `tenant_id` (ticket Design
section, no exceptions): tenant-scoped at the method-signature level, not
just by convention at the implementation.

`BacktestResultRepository` (ECON-013) is a deliberately SEPARATE Protocol,
not folded into `EconomicInputRepository` above: `backtest_results` is not a
simulation *input* record like the other three tables -- it is an eligible-
branch-only, guard-gated write path (see `app.models.BacktestResult`'s own
docstring), and mixing that into the unconditional input-record writes above
would blur that distinction. Write-once: only a `create_*` and a `get_*`
method, no update/delete.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FeeScheduleRecord:
    """Mirrors `app.models.FeeSchedule`'s columns exactly."""

    id: str
    tenant_id: str
    venue: str
    fee_tiers: dict
    created_at: datetime


@dataclass(frozen=True)
class SlippageModelRecord:
    """Mirrors `app.models.SlippageModel`'s columns exactly."""

    id: str
    tenant_id: str
    model_kind: str
    parameters: dict
    created_at: datetime


@dataclass(frozen=True)
class SimulationConfigRecord:
    """Mirrors `app.models.SimulationConfig`'s columns exactly.

    `validation_run_id` stays a plain string here too -- this record type
    must never grow a `ForeignKey`-shaped field referencing another
    service's schema (see `app.models`'s own module docstring).
    """

    id: str
    tenant_id: str
    validation_run_id: str
    fee_schedule_id: str
    slippage_model_id: str
    turnover_assumptions: dict
    created_at: datetime


@typing.runtime_checkable
class EconomicInputRepository(typing.Protocol):
    """Repository for the three `economic.*` input tables (ticket AC1 method set).

    Inputs-only, permanently: no method on this Protocol may ever return or
    accept a computed profitability figure (see `app.models`'s module
    docstring and `tests/test_no_profitability_columns.py`).
    """

    def create_fee_schedule(
        self, tenant_id: str, venue: str, fee_tiers: dict
    ) -> FeeScheduleRecord: ...

    def get_fee_schedule(self, tenant_id: str, fee_schedule_id: str) -> FeeScheduleRecord | None: ...

    def create_slippage_model(
        self, tenant_id: str, model_kind: str, parameters: dict
    ) -> SlippageModelRecord: ...

    def get_slippage_model(
        self, tenant_id: str, slippage_model_id: str
    ) -> SlippageModelRecord | None: ...

    def create_simulation_config(
        self,
        tenant_id: str,
        validation_run_id: str,
        fee_schedule_id: str,
        slippage_model_id: str,
        turnover_assumptions: dict,
    ) -> SimulationConfigRecord: ...

    def get_simulation_config(
        self, tenant_id: str, simulation_config_id: str
    ) -> SimulationConfigRecord | None: ...


@dataclass(frozen=True)
class BacktestResultRecord:
    """Mirrors `app.models.BacktestResult`'s columns exactly."""

    id: str
    tenant_id: str
    backtest_id: str
    run_id: str
    fee_schedule_id: str
    slippage_model_id: str
    cost_adjusted_return: float
    slippage_adjusted_return: float
    total_cost_bps: float
    upstream_dm_statistic: float
    upstream_dm_pvalue: float
    upstream_dm_verdict: str
    computed_at: datetime
    result_kind: str


@typing.runtime_checkable
class BacktestResultRepository(typing.Protocol):
    """Repository for the one guard-gated `economic.backtest_results` table
    (ECON-013). A SEPARATE Protocol from `EconomicInputRepository` above --
    see module docstring for why. `create_backtest_result` has no
    `result_kind` parameter: the fixed tag is always applied internally by
    the implementation (mirrors `app.models.RESULT_KIND_RETROSPECTIVE_BACKTEST`),
    never settable by a caller.
    """

    def create_backtest_result(
        self,
        tenant_id: str,
        backtest_id: str,
        run_id: str,
        fee_schedule_id: str,
        slippage_model_id: str,
        cost_adjusted_return: float,
        slippage_adjusted_return: float,
        total_cost_bps: float,
        upstream_dm_statistic: float,
        upstream_dm_pvalue: float,
        upstream_dm_verdict: str,
    ) -> BacktestResultRecord: ...

    def get_backtest_results(
        self, tenant_id: str, backtest_id: str
    ) -> list[BacktestResultRecord]: ...
