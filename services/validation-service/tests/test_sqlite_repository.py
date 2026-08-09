"""VS-004: `SQLiteValidationRunRepository`/`SQLiteSplitResultRepository`
against a real file-based SQLite DB.

Tenant isolation (this ticket's load-bearing acceptance criterion) gets its
own dedicated test, `test_tenant_isolation_...`, written to genuinely fail
if a `tenant_id` filter were ever dropped from a query -- it creates two
distinct tenants' runs/splits and asserts the *absence* of cross-tenant data
in both directions, not just that same-tenant lookups work.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.repositories.interfaces import SplitResultRecord
from app.repositories.sqlite_repository import (
    SQLiteSplitResultRepository,
    SQLiteValidationRunRepository,
)

SPLIT_CONFIG = {"train_window": 100, "test_window": 20, "step": 10}


@pytest.fixture()
def run_repo(db_path) -> SQLiteValidationRunRepository:
    return SQLiteValidationRunRepository(db_path)


@pytest.fixture()
def split_repo(db_path) -> SQLiteSplitResultRepository:
    return SQLiteSplitResultRepository(db_path)


def _make_split(run_id: str, tenant_id: str, split_index: int, **overrides) -> SplitResultRecord:
    fields = dict(
        id=f"split-{tenant_id}-{split_index}",
        run_id=run_id,
        tenant_id=tenant_id,
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


def test_create_run_persists_and_is_retrievable(run_repo) -> None:
    created = run_repo.create_run(
        tenant_id="tenant-1",
        dataset_id="dataset-1",
        horizon=1,
        purge_gap_hours=4.0,
        split_config=SPLIT_CONFIG,
    )

    assert created.id
    assert created.status == "pending"
    assert created.completed_at is None
    assert created.failure_reason is None

    fetched = run_repo.get_run("tenant-1", created.id)
    assert fetched == created


def test_get_run_returns_none_for_unknown_run_id(run_repo) -> None:
    assert run_repo.get_run("tenant-1", "no-such-run") is None


def test_update_run_status_updates_status_and_completion_fields(run_repo) -> None:
    created = run_repo.create_run(
        tenant_id="tenant-1",
        dataset_id="dataset-1",
        horizon=1,
        purge_gap_hours=4.0,
        split_config=SPLIT_CONFIG,
    )

    run_repo.update_run_status(
        "tenant-1",
        created.id,
        "completed",
        completed_at=datetime(2026, 1, 2),
    )

    updated = run_repo.get_run("tenant-1", created.id)
    assert updated.status == "completed"
    assert updated.completed_at == datetime(2026, 1, 2)
    assert updated.failure_reason is None


def test_update_run_status_records_failure_reason(run_repo) -> None:
    created = run_repo.create_run(
        tenant_id="tenant-1",
        dataset_id="dataset-1",
        horizon=1,
        purge_gap_hours=4.0,
        split_config=SPLIT_CONFIG,
    )

    run_repo.update_run_status("tenant-1", created.id, "failed", failure_reason="dataset unreachable")

    updated = run_repo.get_run("tenant-1", created.id)
    assert updated.status == "failed"
    assert updated.failure_reason == "dataset unreachable"


def test_add_and_get_splits_round_trips_and_orders_by_split_index(run_repo, split_repo) -> None:
    run = run_repo.create_run(
        tenant_id="tenant-1",
        dataset_id="dataset-1",
        horizon=1,
        purge_gap_hours=4.0,
        split_config=SPLIT_CONFIG,
    )

    splits = [
        _make_split(run.id, "tenant-1", 2),
        _make_split(run.id, "tenant-1", 0),
        _make_split(run.id, "tenant-1", 1),
    ]
    split_repo.add_splits("tenant-1", run.id, splits)

    fetched = split_repo.get_splits("tenant-1", run.id)

    assert [s.split_index for s in fetched] == [0, 1, 2]
    assert fetched[0].model_mae == 0.1
    assert fetched[0].dm_verdict == "better"


def test_get_splits_returns_empty_list_for_run_with_no_splits(run_repo, split_repo) -> None:
    run = run_repo.create_run(
        tenant_id="tenant-1",
        dataset_id="dataset-1",
        horizon=1,
        purge_gap_hours=4.0,
        split_config=SPLIT_CONFIG,
    )

    assert split_repo.get_splits("tenant-1", run.id) == []


def test_tenant_isolation_get_run_and_get_splits_never_leak_across_tenants(run_repo, split_repo) -> None:
    """The load-bearing test for this ticket.

    Creates two genuinely distinct tenants (`tenant-a`, `tenant-b`), each with
    its own run and its own splits. Then asserts, in *both* directions, that
    querying with the wrong tenant_id returns nothing -- not merely that
    querying with the right tenant_id works (which a broken/no-op filter
    would also satisfy).
    """
    run_a = run_repo.create_run(
        tenant_id="tenant-a",
        dataset_id="dataset-a",
        horizon=1,
        purge_gap_hours=4.0,
        split_config=SPLIT_CONFIG,
    )
    run_b = run_repo.create_run(
        tenant_id="tenant-b",
        dataset_id="dataset-b",
        horizon=2,
        purge_gap_hours=8.0,
        split_config={"train_window": 50, "test_window": 10, "step": 5},
    )

    split_repo.add_splits("tenant-a", run_a.id, [_make_split(run_a.id, "tenant-a", 0)])
    split_repo.add_splits("tenant-b", run_b.id, [_make_split(run_b.id, "tenant-b", 0)])

    # tenant_b querying tenant_a's run/splits by tenant_a's real run_id: must
    # see nothing, not tenant_a's row.
    assert run_repo.get_run("tenant-b", run_a.id) is None
    assert split_repo.get_splits("tenant-b", run_a.id) == []

    # tenant_a querying tenant_b's run/splits by tenant_b's real run_id: must
    # see nothing, not tenant_b's row.
    assert run_repo.get_run("tenant-a", run_b.id) is None
    assert split_repo.get_splits("tenant-a", run_b.id) == []

    # Sanity: each tenant can still see its own data (rules out the isolation
    # assertions above passing merely because the run_ids/lookups are broken
    # in general rather than because of tenant filtering specifically).
    fetched_a = run_repo.get_run("tenant-a", run_a.id)
    fetched_b = run_repo.get_run("tenant-b", run_b.id)
    assert fetched_a is not None and fetched_a.dataset_id == "dataset-a"
    assert fetched_b is not None and fetched_b.dataset_id == "dataset-b"
    assert [s.tenant_id for s in split_repo.get_splits("tenant-a", run_a.id)] == ["tenant-a"]
    assert [s.tenant_id for s in split_repo.get_splits("tenant-b", run_b.id)] == ["tenant-b"]


def test_tenant_isolation_update_run_status_does_not_affect_other_tenant(run_repo) -> None:
    """A wrong-tenant `update_run_status` call must be a silent no-op on the
    other tenant's row, not an accidental cross-tenant write.
    """
    run_a = run_repo.create_run(
        tenant_id="tenant-a",
        dataset_id="dataset-a",
        horizon=1,
        purge_gap_hours=4.0,
        split_config=SPLIT_CONFIG,
    )

    # tenant_b attempts to update tenant_a's run by its real id.
    run_repo.update_run_status("tenant-b", run_a.id, "failed", failure_reason="not yours")

    # tenant_a's row is untouched.
    still_a = run_repo.get_run("tenant-a", run_a.id)
    assert still_a.status == "pending"
    assert still_a.failure_reason is None

    # And tenant_b still sees nothing under that run_id.
    assert run_repo.get_run("tenant-b", run_a.id) is None
