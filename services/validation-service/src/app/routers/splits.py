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

`SplitResultResponse` is imported from `naive_first_common.contracts`
(ARCH-003) -- this router is the canonical source that shape was copied
from, and now imports the shared definition like `gateway-api`'s router
does, so there is exactly one definition instead of two hand-synced copies.

VS-017: `client_baseline` is `None` whenever the persisted
`client_baseline_results` column is `None` (no client prediction was
supplied for this run); otherwise `_client_baseline_response` builds the
nested `ClientBaselineResult`, embedding the mandatory positioning
disclaimer verbatim so it is present in the actual response body, not only
defined as an unused Python constant.

VS-033: `GET /runs/{run_id}/splits/{split_index}/points` added to this same
file (a natural extension of this router's existing splits concern, not a
disjoint one) -- per-split, paginated point drill-down, deliberately not a
field on `GET /runs/{id}/splits` above (payload-size rationale, this ticket's
Design section). `SplitPointResponse` is imported from
`naive_first_common.contracts` (ARCH-003), same single-canonical-shape
convention as `SplitResultResponse`. The `{items, limit, offset, total}`
envelope (`SplitPointsResponse`) stays local to this router, matching
`RunListResponse`'s own "local envelope, shared item shape" precedent
(runs.py). A `split_index` with no matching `split_results` row collapses
into the same 404 as a nonexistent/cross-tenant run (no distinct error
shape); a valid split whose points were pruned or never persisted returns
`200` with empty `items`/`total: 0` -- this falls out by construction from
`SplitPointRepository.get_points` already excluding pruned rows (VS-032).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from naive_first_common import TenantContext, get_tenant_context
from naive_first_common.contracts import (
    ClientBaselineResult,
    SplitPointResponse,
    SplitResultResponse,
)

from app.client_baseline import CLIENT_PREDICTION_AUDIT_DISCLAIMER
from app.dependencies.repositories import (
    SplitPointRepositoryDep,
    SplitResultRepositoryDep,
    ValidationRunRepositoryDep,
)

router = APIRouter()


class SplitPointsResponse(BaseModel):
    """VS-033 response envelope for `GET /runs/{run_id}/splits/{split_index}/
    points`: `items` is the current page (`SplitPointResponse`, imported from
    `naive_first_common.contracts`, never redefined here); `limit`/`offset`
    echo back the resolved query params; `total` is the unpaginated,
    retention-filtered count of this split's points. Local to this router,
    not a shared contract -- same "local envelope, shared item shape"
    precedent `RunListResponse` (runs.py) already established for
    `RunSummaryResponse`.
    """

    items: list[SplitPointResponse]
    limit: int
    offset: int
    total: int


def _client_baseline_response(client_baseline_results: dict | None) -> ClientBaselineResult | None:
    """VS-017: `None` whenever the persisted column is `None` (no client
    prediction was supplied for this run); otherwise builds the nested
    `ClientBaselineResult`, embedding the mandatory positioning disclaimer
    verbatim so it is present in the actual response body, not only defined
    as an unused Python constant.
    """
    if client_baseline_results is None:
        return None

    metrics = client_baseline_results["metrics"]
    return ClientBaselineResult(
        key=client_baseline_results["key"],
        mae=metrics["mae"],
        rmse=metrics["rmse"],
        smape=metrics["smape"],
        mase=metrics["mase"],
        da=metrics["da"],
        f1=metrics["f1"],
        oos_r2=metrics["oos_r2"],
        dm_statistic=client_baseline_results["dm_statistic"],
        dm_pvalue=client_baseline_results["dm_pvalue"],
        dm_verdict=client_baseline_results["dm_verdict"],
        disclaimer=CLIENT_PREDICTION_AUDIT_DISCLAIMER,
    )


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
            client_baseline=_client_baseline_response(split.client_baseline_results),
            has_client_model=split.client_baseline_results is not None,
        )
        for split in splits
    ]


@router.get("/runs/{run_id}/splits/{split_index}/points", response_model=SplitPointsResponse)
def get_split_points(
    run_id: str,
    split_index: int,
    run_repository: ValidationRunRepositoryDep,
    split_repository: SplitResultRepositoryDep,
    split_point_repository: SplitPointRepositoryDep,
    tenant: TenantContext = Depends(get_tenant_context),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> SplitPointsResponse:
    """VS-033: per-split point drill-down, deliberately not a field on
    `GET /runs/{id}/splits` -- see this ticket's Design section (payload-size
    rationale).

    Run-ownership check first, same collapsed-404 stance `get_splits` already
    uses above (module docstring). A `split_index` with no matching row in
    `split_results` also collapses into this same 404 -- `split_results` rows
    are never pruned (only `split_points` are, VS-032), so checking against
    them is how this handler tells "no such split" apart from "this split's
    points were pruned or never persisted" without duplicating any retention
    logic here.
    """
    run = run_repository.get_run(tenant.tenant_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    splits = split_repository.get_splits(tenant.tenant_id, run_id)
    if not any(split.split_index == split_index for split in splits):
        raise HTTPException(status_code=404, detail="run not found")

    # VS-032: already retention-filtered by this call -- no cutoff logic
    # duplicated here (Design section). Pagination is applied in-process
    # since SplitPointRepository.get_points has no limit/offset parameter
    # (VS-031/VS-032's own signature, unchanged by this ticket).
    points = split_point_repository.get_points(tenant.tenant_id, run_id, split_index)

    return SplitPointsResponse(
        items=[
            SplitPointResponse(
                timestamp=point.timestamp,
                predicted=point.predicted,
                actual=point.actual,
                baseline_key=point.baseline_key,
            )
            for point in points[offset : offset + limit]
        ],
        limit=limit,
        offset=offset,
        total=len(points),
    )
