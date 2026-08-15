"""ECON-002: `SQLiteEconomicInputRepository` against a real file-based SQLite
DB.

Tenant isolation (this ticket's load-bearing acceptance criterion) gets its
own dedicated test, written to genuinely fail if a `tenant_id` filter were
ever dropped from a query -- it creates two distinct tenants' records and
asserts the *absence* of cross-tenant data in both directions, not just that
same-tenant lookups work. Mirrors validation-service's own
`test_sqlite_repository.py` shape.
"""

from __future__ import annotations

import pytest

from app.repositories.sqlite_repository import SQLiteEconomicInputRepository


@pytest.fixture()
def repo(db_path) -> SQLiteEconomicInputRepository:
    return SQLiteEconomicInputRepository(db_path)


def test_create_fee_schedule_persists_and_is_retrievable(repo) -> None:
    created = repo.create_fee_schedule(
        tenant_id="tenant-1", venue="binance", fee_tiers=[{"maker_bps": 10, "taker_bps": 15}]
    )

    assert created.id
    assert created.venue == "binance"
    assert created.fee_tiers == [{"maker_bps": 10, "taker_bps": 15}]

    fetched = repo.get_fee_schedule("tenant-1", created.id)
    assert fetched == created


def test_get_fee_schedule_returns_none_for_unknown_id(repo) -> None:
    assert repo.get_fee_schedule("tenant-1", "no-such-fee-schedule") is None


def test_create_slippage_model_persists_and_is_retrievable(repo) -> None:
    created = repo.create_slippage_model(
        tenant_id="tenant-1", model_kind="linear", parameters={"impact_coefficient": 0.05}
    )

    assert created.id
    assert created.model_kind == "linear"
    assert created.parameters == {"impact_coefficient": 0.05}

    fetched = repo.get_slippage_model("tenant-1", created.id)
    assert fetched == created


def test_get_slippage_model_returns_none_for_unknown_id(repo) -> None:
    assert repo.get_slippage_model("tenant-1", "no-such-slippage-model") is None


def test_create_simulation_config_persists_and_is_retrievable(repo) -> None:
    fee = repo.create_fee_schedule(tenant_id="tenant-1", venue="binance", fee_tiers=[{"maker_bps": 10}])
    slippage = repo.create_slippage_model(
        tenant_id="tenant-1", model_kind="linear", parameters={"impact_coefficient": 0.05}
    )

    created = repo.create_simulation_config(
        tenant_id="tenant-1",
        validation_run_id="run-abc123",
        fee_schedule_id=fee.id,
        slippage_model_id=slippage.id,
        turnover_assumptions={"daily_turnover_pct": 5.0},
    )

    assert created.id
    assert created.validation_run_id == "run-abc123"
    assert created.fee_schedule_id == fee.id
    assert created.slippage_model_id == slippage.id
    assert created.turnover_assumptions == {"daily_turnover_pct": 5.0}

    fetched = repo.get_simulation_config("tenant-1", created.id)
    assert fetched == created


def test_get_simulation_config_returns_none_for_unknown_id(repo) -> None:
    assert repo.get_simulation_config("tenant-1", "no-such-simulation-config") is None


def test_tenant_isolation_never_leaks_across_tenants(repo) -> None:
    """The load-bearing test for this ticket.

    Creates two genuinely distinct tenants (`tenant-a`, `tenant-b`), each
    with their own fee schedule, slippage model, and simulation config. Then
    asserts, in *both* directions, that querying with the wrong tenant_id
    returns nothing -- not merely that querying with the right tenant_id
    works (which a broken/no-op filter would also satisfy).
    """
    fee_a = repo.create_fee_schedule(tenant_id="tenant-a", venue="binance", fee_tiers=[{"maker_bps": 10}])
    slippage_a = repo.create_slippage_model(
        tenant_id="tenant-a", model_kind="linear", parameters={"impact_coefficient": 0.05}
    )
    sim_a = repo.create_simulation_config(
        tenant_id="tenant-a",
        validation_run_id="run-a",
        fee_schedule_id=fee_a.id,
        slippage_model_id=slippage_a.id,
        turnover_assumptions={"daily_turnover_pct": 5.0},
    )

    fee_b = repo.create_fee_schedule(tenant_id="tenant-b", venue="coinbase", fee_tiers=[{"maker_bps": 20}])
    slippage_b = repo.create_slippage_model(
        tenant_id="tenant-b", model_kind="square_root", parameters={"impact_coefficient": 0.1}
    )
    sim_b = repo.create_simulation_config(
        tenant_id="tenant-b",
        validation_run_id="run-b",
        fee_schedule_id=fee_b.id,
        slippage_model_id=slippage_b.id,
        turnover_assumptions={"daily_turnover_pct": 10.0},
    )

    # tenant-b querying tenant-a's real ids: must see nothing.
    assert repo.get_fee_schedule("tenant-b", fee_a.id) is None
    assert repo.get_slippage_model("tenant-b", slippage_a.id) is None
    assert repo.get_simulation_config("tenant-b", sim_a.id) is None

    # tenant-a querying tenant-b's real ids: must see nothing.
    assert repo.get_fee_schedule("tenant-a", fee_b.id) is None
    assert repo.get_slippage_model("tenant-a", slippage_b.id) is None
    assert repo.get_simulation_config("tenant-a", sim_b.id) is None

    # Sanity: each tenant can still see its own data (rules out the isolation
    # assertions above passing merely because the ids/lookups are broken in
    # general rather than because of tenant filtering specifically).
    assert repo.get_fee_schedule("tenant-a", fee_a.id) is not None
    assert repo.get_fee_schedule("tenant-b", fee_b.id) is not None
    assert repo.get_simulation_config("tenant-a", sim_a.id) is not None
    assert repo.get_simulation_config("tenant-b", sim_b.id) is not None
