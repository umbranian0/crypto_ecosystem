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
    RunSplitSummary,
    SplitPointResponse,
    SplitPoints,
    SplitResultResponse,
)

from app.client_baseline import CLIENT_PREDICTION_AUDIT_DISCLAIMER
from app.dependencies.repositories import (
    SplitPointRepositoryDep,
    SplitResultRepositoryDep,
    ValidationRunRepositoryDep,
)
from app.repositories.interfaces import SplitPointRecord, SplitResultRecord

router = APIRouter()


class RunSplitsSummaryResponse(BaseModel):
    """RAV-012 response envelope for `GET /runs/splits/summary`: `items` is
    `RunSplitSummary` (imported from `naive_first_common.contracts`, never
    redefined here) -- same "local envelope, shared item shape" precedent
    `SplitPointsResponse` below already established.
    """

    items: list[RunSplitSummary]


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


def _split_result_to_response(split: SplitResultRecord) -> SplitResultResponse:
    """Extracted from `get_splits` (RAV-012) so the 20-field mapping has
    exactly one copy -- reused by both `get_splits` and
    `get_splits_summary` below."""
    return SplitResultResponse(
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


@router.get("/runs/{run_id}/splits", response_model=list[SplitResultResponse])
def get_splits(
    run_id: str,
    run_repository: ValidationRunRepositoryDep,
    split_repository: SplitResultRepositoryDep,
    tenant: TenantContext = Depends(get_tenant_context),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[SplitResultResponse]:
    # Run-ownership check first, same 404-collapses-both-cases stance as
    # `GET /runs/{id}` (VS-007) -- see module docstring.
    run = run_repository.get_run(tenant.tenant_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    # DBOPT-011: omitting limit/offset is byte-identical to pre-ticket
    # behavior -- the full, unbounded, ordered list (binding AC). Response
    # shape (bare list) never changes, bounded or not.
    splits = split_repository.get_splits(tenant.tenant_id, run_id, limit=limit, offset=offset)

    return [_split_result_to_response(split) for split in splits]


class SplitCountResponse(BaseModel):
    """DBOPT-011: local envelope for GET /runs/{run_id}/splits/count -- a
    single scalar wrapped in an object (not a bare int), matching this
    router's existing "local envelope" convention (SplitPointsResponse,
    RunSplitsSummaryResponse) rather than a bare top-level int body.
    """

    total: int


@router.get("/runs/{run_id}/splits/count", response_model=SplitCountResponse)
def get_splits_count(
    run_id: str,
    run_repository: ValidationRunRepositoryDep,
    split_repository: SplitResultRepositoryDep,
    tenant: TenantContext = Depends(get_tenant_context),
) -> SplitCountResponse:
    """DBOPT-011: companion count endpoint mirroring VS-022's
    `list_runs`/`count_runs` pair. Route collision check (done before writing
    this route, not assumed): `/runs/{run_id}/splits/count` is 4 path
    segments (`runs`/`{run_id}`/`splits`/`count`) -- distinct from
    `/runs/{run_id}/splits` (3 segments) and
    `/runs/{run_id}/splits/{split_index}/points` (5 segments) by segment
    count alone. RAV-016 (sequenced after this ticket) will add
    `/runs/{run_id}/splits/points`, also 4 segments -- no collision with this
    route regardless of registration order since the literal 4th segment
    differs (`"count"` vs `"points"`), the same reasoning RAV-012's
    `"summary"` vs `"splits"` collision check already used.
    """
    run = run_repository.get_run(tenant.tenant_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return SplitCountResponse(total=split_repository.count_splits(tenant.tenant_id, run_id))


@router.get("/runs/splits/summary", response_model=RunSplitsSummaryResponse)
def get_splits_summary(
    split_repository: SplitResultRepositoryDep,
    tenant: TenantContext = Depends(get_tenant_context),
    run_id: list[str] = Query(default=[]),
) -> RunSplitsSummaryResponse:
    """RAV-012: batched form of `get_splits` above, for a page of run ids at
    once (the runs-list page's need -- see module docstring precedent for
    why this file owns every `split_results`-adjacent read). No run-ownership
    404 here -- unlike `get_splits`, an unknown/cross-tenant run id in a batch
    request is simply absent from the response, not a request-level error,
    since the caller supplied a page of ids it already believes are its own.
    3-path-segment route (`/runs/splits/summary`), chosen specifically to
    avoid colliding with `/runs/{run_id}` (different segment count) and with
    `/runs/{run_id}/splits` (also 3 segments, but this route's literal third
    segment is `"summary"` vs. that route's literal `"splits"` -- a real run
    id is always a uuid hex, never either literal string, so neither
    collides regardless of registration order).
    """
    if not run_id:
        return RunSplitsSummaryResponse(items=[])
    splits_by_run = split_repository.get_splits_for_runs(tenant.tenant_id, run_id)
    return RunSplitsSummaryResponse(
        items=[
            RunSplitSummary(
                run_id=rid,
                splits=[_split_result_to_response(s) for s in splits],
            )
            for rid, splits in splits_by_run.items()
        ]
    )


def _split_point_to_response(point: SplitPointRecord) -> SplitPointResponse:
    """Extracted from `get_split_points` (RAV-016) so the 4-field mapping
    has exactly one copy -- reused by both `get_split_points` and
    `get_splits_points` below."""
    return SplitPointResponse(
        timestamp=point.timestamp,
        predicted=point.predicted,
        actual=point.actual,
        baseline_key=point.baseline_key,
    )


class RunSplitPointsResponse(BaseModel):
    """RAV-016 response envelope for GET /runs/{run_id}/splits/points:
    `items` is `SplitPoints` (imported from naive_first_common.contracts,
    never redefined here) -- same "local envelope, shared item shape"
    precedent RunSplitsSummaryResponse above already established."""

    items: list[SplitPoints]


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
        items=[_split_point_to_response(point) for point in points[offset : offset + limit]],
        limit=limit,
        offset=offset,
        total=len(points),
    )


@router.get("/runs/{run_id}/splits/points", response_model=RunSplitPointsResponse)
def get_splits_points(
    run_id: str,
    run_repository: ValidationRunRepositoryDep,
    split_point_repository: SplitPointRepositoryDep,
    tenant: TenantContext = Depends(get_tenant_context),
    split_index: list[int] = Query(default=[]),
) -> RunSplitPointsResponse:
    """RAV-016: batched form of get_split_points above, for every
    rendered split of one run in a single round trip. Run-ownership
    check first (same collapsed-404 stance as get_splits/
    get_split_points) since a request is always scoped to exactly one
    run -- but, unlike get_split_points, does NOT additionally validate
    each requested split_index against split_results: the indices
    always come from run_detail's own already-validated
    rendered_splits, so a per-index 404 would only ever fire on an
    internal bug and would fail the whole batch over one bad index.
    Every requested split_index gets exactly one entry in `items`, in
    request order, with `points: []` for any index absent from the
    repository's result dict (pruned, never persisted -- degrades the
    same way the single-split endpoint's empty-items response already
    does, never an error).

    4-path-segment route (runs/{run_id}/splits/points), distinct in
    segment count from /runs/{run_id}/splits (3 segments) and
    /runs/{run_id}/splits/{split_index}/points (5 segments); shares a
    segment count with DBOPT-011's /runs/{run_id}/splits/count but
    differs in its literal 4th segment ("points" vs "count"), so
    neither collides regardless of registration order.
    """
    run = run_repository.get_run(tenant.tenant_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if not split_index:
        return RunSplitPointsResponse(items=[])
    points_by_split = split_point_repository.get_points_for_splits(
        tenant.tenant_id, run_id, split_index
    )
    return RunSplitPointsResponse(
        items=[
            SplitPoints(
                split_index=idx,
                points=[_split_point_to_response(p) for p in points_by_split.get(idx, [])],
            )
            for idx in split_index
        ]
    )
