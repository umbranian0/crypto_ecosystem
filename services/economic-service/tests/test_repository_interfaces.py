"""Tests for ECON-002's repository interfaces.

Covers: the interfaces module having zero storage-driver import (enforced
mechanically via AST inspection, not just by eye -- mirrors
validation-service's own `test_repository_interfaces.py`), the Protocol
being non-instantiable directly, and a minimal fake implementation proving
the declared method set is actually implementable end to end.
"""

from __future__ import annotations

import ast
import inspect
from datetime import datetime

import pytest

from app.repositories.interfaces import (
    EconomicInputRepository,
    FeeScheduleRecord,
    SimulationConfigRecord,
    SlippageModelRecord,
)

_FORBIDDEN_MODULE_ROOTS = {"sqlite3", "psycopg", "sqlalchemy"}


def _imported_module_roots(source: str) -> set[str]:
    tree = ast.parse(source)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_interfaces_module_imports_no_storage_driver() -> None:
    source = inspect.getsource(inspect.getmodule(EconomicInputRepository))

    roots = _imported_module_roots(source)

    assert roots.isdisjoint(_FORBIDDEN_MODULE_ROOTS), (
        f"interfaces.py must stay storage-driver-free (ticket Design "
        f"section); found forbidden imports: {roots & _FORBIDDEN_MODULE_ROOTS}"
    )


def test_economic_input_repository_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        EconomicInputRepository()


class _FakeEconomicInputRepository:
    """Minimal in-memory implementation proving the interface is implementable."""

    def __init__(self) -> None:
        self._fee_schedules: dict[tuple[str, str], FeeScheduleRecord] = {}
        self._slippage_models: dict[tuple[str, str], SlippageModelRecord] = {}
        self._simulation_configs: dict[tuple[str, str], SimulationConfigRecord] = {}
        self._next_id = 0

    def _mint_id(self, prefix: str) -> str:
        self._next_id += 1
        return f"{prefix}-{self._next_id}"

    def create_fee_schedule(self, tenant_id, venue, fee_tiers) -> FeeScheduleRecord:
        record = FeeScheduleRecord(
            id=self._mint_id("fee"),
            tenant_id=tenant_id,
            venue=venue,
            fee_tiers=fee_tiers,
            created_at=datetime.now(),
        )
        self._fee_schedules[(tenant_id, record.id)] = record
        return record

    def get_fee_schedule(self, tenant_id, fee_schedule_id) -> FeeScheduleRecord | None:
        return self._fee_schedules.get((tenant_id, fee_schedule_id))

    def create_slippage_model(self, tenant_id, model_kind, parameters) -> SlippageModelRecord:
        record = SlippageModelRecord(
            id=self._mint_id("slip"),
            tenant_id=tenant_id,
            model_kind=model_kind,
            parameters=parameters,
            created_at=datetime.now(),
        )
        self._slippage_models[(tenant_id, record.id)] = record
        return record

    def get_slippage_model(self, tenant_id, slippage_model_id) -> SlippageModelRecord | None:
        return self._slippage_models.get((tenant_id, slippage_model_id))

    def create_simulation_config(
        self, tenant_id, validation_run_id, fee_schedule_id, slippage_model_id, turnover_assumptions
    ) -> SimulationConfigRecord:
        record = SimulationConfigRecord(
            id=self._mint_id("sim"),
            tenant_id=tenant_id,
            validation_run_id=validation_run_id,
            fee_schedule_id=fee_schedule_id,
            slippage_model_id=slippage_model_id,
            turnover_assumptions=turnover_assumptions,
            created_at=datetime.now(),
        )
        self._simulation_configs[(tenant_id, record.id)] = record
        return record

    def get_simulation_config(self, tenant_id, simulation_config_id) -> SimulationConfigRecord | None:
        return self._simulation_configs.get((tenant_id, simulation_config_id))


def test_fake_economic_input_repository_satisfies_protocol_and_round_trips() -> None:
    repo: EconomicInputRepository = _FakeEconomicInputRepository()
    assert isinstance(repo, EconomicInputRepository)

    fee = repo.create_fee_schedule("tenant-1", "binance", [{"maker_bps": 10}])
    assert repo.get_fee_schedule("tenant-1", fee.id) == fee
    assert repo.get_fee_schedule("other-tenant", fee.id) is None

    slippage = repo.create_slippage_model("tenant-1", "linear", {"impact_coefficient": 0.05})
    assert repo.get_slippage_model("tenant-1", slippage.id) == slippage

    sim = repo.create_simulation_config(
        "tenant-1", "run-abc123", fee.id, slippage.id, {"daily_turnover_pct": 5.0}
    )
    assert repo.get_simulation_config("tenant-1", sim.id) == sim
    assert repo.get_simulation_config("other-tenant", sim.id) is None
