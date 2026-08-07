"""`GET /runs/{id}/splits` (VS-008): separate router module, deliberately not
added to `runs.py` -- see this ticket's Design section. Kept as its own file
(mounted at the same `/runs` prefix) so it has no line overlap with VS-007
(also editing `runs.py`) or VS-009 (adding a `publish()` call to `runs.py`'s
`POST` handler), letting all three land/run in parallel.

Tenant isolation (load-bearing, same stance as VS-007): the run's tenant
ownership is checked first via `ValidationRunRepository.get_run` -- a `None`
result (nonexistent run, or a run that exists for a different tenant) is
translated into a single `404`, no branch distinguishing the two. This check
happens *before* `SplitResultRepository.get_splits` is ever called: defense
in depth, since `get_splits` is itself tenant-scoped (VS-004) and would
return `[]` for a cross-tenant `run_id` on its own, but a run that doesn't
exist for this tenant has no meaningful "splits" response either way (VS-008
Design section).

Ordering: `SplitResultRepository.get_splits` already returns splits ordered
by `split_index` (VS-003's binding decision, interfaces.py) -- this handler
does not re-sort.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from naive_first_common import TenantContext, get_tenant_context

from app.dependencies.repositories import (
    SplitResultRepositoryDep,
    ValidationRunRepositoryDep,
)

router = APIRouter()


class SplitResultResponse(BaseModel):
    """One `split_results` row, full field set (VS-008 AC1)."""

    split_index: int

    train_start: datetime
    train_end: datetime
    purge_start: datetime | None
    purge_end: datetime | None
    test_start: datetime
    test_end: datetime

    model_mae: float
    model_rmse: float
    model_smape: float
    model_mase: float
    model_da: float
    model_f1: float
    model_oos_r2: float

    naive0_mae: float
    naive0_rmse: float
    naive0_smape: float
    naive0_mase: float
    naive0_da: float
    naive0_f1: float
    naive0_oos_r2: float

    dm_statistic: float
    dm_pvalue: float
    dm_verdict: str


@router.get("/runs/{run_id}/splits", response_model=list[SplitResultResponse])
def get_splits(
    run_id: str,
    run_repository: ValidationRunRepositoryDep,
    split_repository: SplitResultRepositoryDep,
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[SplitResultResponse]:
    # Run-ownership check first, same 404-collapses-both-cases stance as
    # `GET /runs/{id}` (VS-007) -- see module docstring.
    run = run_repository.get_run(tenant.tenant_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    splits = split_repository.get_splits(tenant.tenant_id, run_id)

    return [
        SplitResultResponse(
            split_index=split.split_index,
            train_start=split.train_start,
            train_end=split.train_end,
            purge_start=split.purge_start,
            purge_end=split.purge_end,
            test_start=split.test_start,
            test_end=split.test_end,
            model_mae=split.model_mae,
            model_rmse=split.model_rmse,
            model_smape=split.model_smape,
            model_mase=split.model_mase,
            model_da=split.model_da,
            model_f1=split.model_f1,
            model_oos_r2=split.model_oos_r2,
            naive0_mae=split.naive0_mae,
            naive0_rmse=split.naive0_rmse,
            naive0_smape=split.naive0_smape,
            naive0_mase=split.naive0_mase,
            naive0_da=split.naive0_da,
            naive0_f1=split.naive0_f1,
            naive0_oos_r2=split.naive0_oos_r2,
            dm_statistic=split.dm_statistic,
            dm_pvalue=split.dm_pvalue,
            dm_verdict=split.dm_verdict,
        )
        for split in splits
    ]
