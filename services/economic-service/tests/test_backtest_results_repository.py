"""ECON-013 tests: `SQLiteBacktestResultRepository` (round-trip, tenant
isolation) plus the ticket's own binding structural-reachability requirement
-- `create_backtest_result` must be reachable EXCLUSIVELY from inside
`routers/backtests.py`'s eligible branch, never from anywhere else. Mirrors
`test_sqlite_repository.py`'s round-trip/tenant-isolation shape and
`test_eligibility.py`'s own guard-structural-check shape (not literal code).
"""

from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path

import pytest

from app.repositories.sqlite_repository import SQLiteBacktestResultRepository

APP_SRC_DIR = Path(__file__).resolve().parent.parent / "src" / "app"


@pytest.fixture()
def repo(db_path) -> SQLiteBacktestResultRepository:
    return SQLiteBacktestResultRepository(db_path)


def _create(
    repo: SQLiteBacktestResultRepository,
    *,
    tenant_id: str,
    backtest_id: str,
    run_id: str,
):
    return repo.create_backtest_result(
        tenant_id=tenant_id,
        backtest_id=backtest_id,
        run_id=run_id,
        fee_schedule_id="fee-1",
        slippage_model_id="slip-1",
        cost_adjusted_return=3.21,
        slippage_adjusted_return=3.11,
        total_cost_bps=10.0,
        upstream_dm_statistic=3.21,
        upstream_dm_pvalue=0.004,
        upstream_dm_verdict="better",
    )


def test_create_backtest_result_persists_and_is_retrievable(repo) -> None:
    before = datetime.utcnow()

    created = _create(repo, tenant_id="tenant-1", backtest_id="batch-1", run_id="run-1")

    assert created.id
    assert created.tenant_id == "tenant-1"
    assert created.backtest_id == "batch-1"
    assert created.run_id == "run-1"
    assert created.fee_schedule_id == "fee-1"
    assert created.slippage_model_id == "slip-1"
    assert created.cost_adjusted_return == 3.21
    assert created.slippage_adjusted_return == 3.11
    assert created.total_cost_bps == 10.0
    assert created.upstream_dm_statistic == 3.21
    assert created.upstream_dm_pvalue == 0.004
    assert created.upstream_dm_verdict == "better"
    assert created.result_kind == "retrospective_backtest"
    assert created.computed_at >= before

    fetched = repo.get_backtest_results("tenant-1", "batch-1")
    assert fetched == [created]


def test_get_backtest_results_returns_empty_list_for_unknown_backtest_id(repo) -> None:
    assert repo.get_backtest_results("tenant-1", "no-such-batch") == []


def test_tenant_isolation_never_leaks_across_tenants(repo) -> None:
    """Load-bearing tenant-isolation test (ticket Test acceptance criteria).

    Uses the SAME `backtest_id` across two distinct tenants specifically so
    the assertion cannot pass merely because `backtest_id` alone happened to
    differ -- it genuinely exercises the `tenant_id` filter in
    `get_backtest_results`'s SQL `WHERE` clause.
    """
    row_a = _create(repo, tenant_id="tenant-a", backtest_id="shared-batch", run_id="run-a")
    row_b = _create(repo, tenant_id="tenant-b", backtest_id="shared-batch", run_id="run-b")

    # Each tenant sees only its own row for the shared backtest_id.
    assert repo.get_backtest_results("tenant-a", "shared-batch") == [row_a]
    assert repo.get_backtest_results("tenant-b", "shared-batch") == [row_b]

    # Cross-tenant read never leaks the other tenant's row in either direction.
    tenant_a_results = repo.get_backtest_results("tenant-a", "shared-batch")
    tenant_b_results = repo.get_backtest_results("tenant-b", "shared-batch")
    assert row_b not in tenant_a_results
    assert row_a not in tenant_b_results


def _find_create_backtest_result_call_sites() -> list[tuple[Path, int]]:
    call_sites: list[tuple[Path, int]] = []
    for py_file in APP_SRC_DIR.rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "create_backtest_result"
            ):
                call_sites.append((py_file, node.lineno))
    return call_sites


def test_create_backtest_result_has_exactly_one_call_site_in_backtests_eligible_branch() -> None:
    """The ticket's own binding structural requirement: `create_backtest_result`
    (the SQLite implementation's method name, shared with the Protocol) must
    be reachable EXCLUSIVELY from inside ECON-012's eligible branch in
    `routers/backtests.py` -- never from `routers/simulations.py`, never from
    anywhere else. AST-parses every `.py` file under `src/app` and asserts:
    (1) exactly one real call site exists across the whole module, (2) that
    call site lives in `routers/backtests.py`, and (3) it is lexically
    downstream of the `if not decision.is_eligible: ...` guard (i.e. only
    reachable once that guard has NOT triggered its own early `continue`).

    This is a structural proof, not merely a happy-path insert test -- see
    this ticket's own Review acceptance criteria: a second, illegitimate call
    site was temporarily added elsewhere during self-review to confirm this
    test genuinely fails in that case, then removed (see ECON-013.md's
    Outcome section for that record).
    """
    call_sites = _find_create_backtest_result_call_sites()

    assert len(call_sites) == 1, (
        f"create_backtest_result must have exactly one real call site across "
        f"src/app, found {len(call_sites)}: {call_sites}"
    )

    call_file, call_lineno = call_sites[0]
    assert call_file.name == "backtests.py" and call_file.parent.name == "routers", (
        f"the one call site must live in routers/backtests.py, found {call_file}"
    )

    backtests_source = call_file.read_text(encoding="utf-8")
    backtests_tree = ast.parse(backtests_source)
    guard_if = next(
        node
        for node in ast.walk(backtests_tree)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.op, ast.Not)
    )
    # The refusal branch's own `continue` must be inside this `if` -- rules
    # out this being some unrelated `if not ...` elsewhere in the file.
    assert any(isinstance(stmt, ast.Continue) for stmt in ast.walk(guard_if)), (
        "expected `if not decision.is_eligible: ... continue` guard was not "
        "found in the shape this test expects"
    )
    assert call_lineno > guard_if.lineno, (
        "create_backtest_result's call site must be lexically downstream of "
        "the `if not decision.is_eligible` guard's own continue -- i.e. only "
        "reached on the eligible branch, never inside the refusal branch"
    )


def test_simulations_router_never_references_create_backtest_result() -> None:
    """Belt-and-suspenders alongside the AST-wide scan above: explicitly
    confirms `routers/simulations.py` (the single-run endpoint, out of this
    ticket's scope to add persistence to) contains no reference to
    `create_backtest_result` at all.
    """
    simulations_source = (APP_SRC_DIR / "routers" / "simulations.py").read_text(encoding="utf-8")
    assert "create_backtest_result" not in simulations_source
