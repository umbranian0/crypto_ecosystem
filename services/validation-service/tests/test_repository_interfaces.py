"""Tests for VS-003's repository interfaces.

Covers: AC3 (no storage-driver import in interfaces.py, enforced mechanically
via AST inspection, not just by eye), the two Protocols being non-instantiable
directly, and a minimal fake implementation proving the declared method set is
actually implementable end to end.
"""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timezone

import pytest

from app.repositories.interfaces import (
    RunRecord,
    SplitResultRecord,
    SplitResultRepository,
    ValidationRunRepository,
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
    source = inspect.getsource(inspect.getmodule(ValidationRunRepository))

    roots = _imported_module_roots(source)

    assert roots.isdisjoint(_FORBIDDEN_MODULE_ROOTS), (
        f"interfaces.py must stay storage-driver-free (AC3); found forbidden "
        f"imports: {roots & _FORBIDDEN_MODULE_ROOTS}"
    )


def test_validation_run_repository_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        ValidationRunRepository()


def test_split_result_repository_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        SplitResultRepository()


class _FakeValidationRunRepository:
    """Minimal in-memory implementation proving the interface is implementable."""

    def __init__(self) -> None:
        self._runs: dict[tuple[str, str], RunRecord] = {}
        self._next_id = 0

    def create_run(self, tenant_id, dataset_id, horizon, purge_gap_hours, split_config) -> RunRecord:
        self._next_id += 1
        record = RunRecord(
            id=f"run-{self._next_id}",
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            horizon=horizon,
            purge_gap_hours=purge_gap_hours,
            split_config=split_config,
            status="pending",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            completed_at=None,
            failure_reason=None,
        )
        self._runs[(tenant_id, record.id)] = record
        return record

    def get_run(self, tenant_id, run_id) -> RunRecord | None:
        return self._runs.get((tenant_id, run_id))

    def update_run_status(self, tenant_id, run_id, status, *, completed_at=None, failure_reason=None) -> None:
        existing = self._runs[(tenant_id, run_id)]
        self._runs[(tenant_id, run_id)] = RunRecord(
            id=existing.id,
            tenant_id=existing.tenant_id,
            dataset_id=existing.dataset_id,
            horizon=existing.horizon,
            purge_gap_hours=existing.purge_gap_hours,
            split_config=existing.split_config,
            status=status,
            created_at=existing.created_at,
            completed_at=completed_at,
            failure_reason=failure_reason,
        )

    def list_runs(self, tenant_id, limit, offset) -> list[RunRecord]:
        matching = [r for (t, _), r in self._runs.items() if t == tenant_id]
        matching.sort(key=lambda r: r.created_at, reverse=True)
        return matching[offset : offset + limit]

    def count_runs(self, tenant_id) -> int:
        return sum(1 for (t, _) in self._runs if t == tenant_id)


class _FakeSplitResultRepository:
    """Minimal in-memory implementation proving the interface is implementable."""

    def __init__(self) -> None:
        self._splits: dict[tuple[str, str], list[SplitResultRecord]] = {}

    def add_splits(self, tenant_id, run_id, splits) -> None:
        self._splits.setdefault((tenant_id, run_id), []).extend(splits)

    def get_splits(self, tenant_id, run_id) -> list[SplitResultRecord]:
        return sorted(self._splits.get((tenant_id, run_id), []), key=lambda s: s.split_index)


def _make_split(split_index: int, **overrides) -> SplitResultRecord:
    fields = dict(
        id=f"split-{split_index}",
        run_id="run-1",
        tenant_id="tenant-1",
        split_index=split_index,
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
    return SplitResultRecord(**fields)


def test_fake_validation_run_repository_satisfies_protocol_and_round_trips() -> None:
    repo: ValidationRunRepository = _FakeValidationRunRepository()
    assert isinstance(repo, ValidationRunRepository)

    run = repo.create_run(
        tenant_id="tenant-1",
        dataset_id="dataset-1",
        horizon=1,
        purge_gap_hours=4.0,
        split_config={"train_window": 100, "test_window": 20, "step": 10},
    )
    assert repo.get_run("tenant-1", run.id) == run
    assert repo.get_run("other-tenant", run.id) is None

    repo.update_run_status("tenant-1", run.id, "completed", completed_at=datetime(2026, 1, 2))
    updated = repo.get_run("tenant-1", run.id)
    assert updated.status == "completed"
    assert updated.completed_at == datetime(2026, 1, 2)


def test_fake_split_result_repository_satisfies_protocol_and_orders_by_split_index() -> None:
    repo: SplitResultRepository = _FakeSplitResultRepository()
    assert isinstance(repo, SplitResultRepository)

    repo.add_splits("tenant-1", "run-1", [_make_split(2), _make_split(0), _make_split(1)])

    splits = repo.get_splits("tenant-1", "run-1")

    assert [s.split_index for s in splits] == [0, 1, 2]
    assert repo.get_splits("other-tenant", "run-1") == []
