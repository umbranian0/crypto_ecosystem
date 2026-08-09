"""`POST /runs` (VS-006): the service's literal trigger condition.

`RunRequest`/`RunResponse`/`RunDetailResponse` are imported from
`naive_first_common.contracts` (ARCH-003) -- this router is the canonical
source these shapes were copied from, and now imports the shared definition
like `gateway-api`'s router does, so there is exactly one definition instead
of two hand-synced copies.

Single responsibility: adapt an HTTP request into exactly one call to
`naive_first_engine.protocol.run_validation_protocol` (imported and invoked
as-is -- no wrapping/subclassing/reordering, per this ticket's Review
acceptance criteria) and persist its output via VS-003/004's repositories.
No split/baseline/metric/DM-test logic is reimplemented here.

Handler flow is fixed (VS-006 Design section, must match exactly):
validate request -> `DatasetSource.load` -> build `ValidationConfig` ->
`create_run` -> `run_validation_protocol` -> map each `SplitResult` to a
`split_results` row (model_*=naive_last, naive0_*=naive0, dm_*=naive_last's
DMResult -- app.models' module docstring) and persist via `add_splits` ->
`update_run_status("completed")` -> return `{id, status}`.

Synchronous by design (VS-006 Design section): this interim implementation
runs the whole protocol within the request/response cycle, so the initial
status `ValidationRunRepository.create_run` persists (`"pending"` -- VS-003/
VS-004's `create_run` signature takes no `status` argument, so this handler
cannot request `"running"` literally; `"pending"` is that same in-flight
placeholder in practice here) is immediately followed by `update_run_status`
to `"completed"` before the response is returned -- no Prefect/worker
orchestration exists yet (backlog AC5). A future async-execution ticket would
split `create_run` and the protocol call + `update_run_status` across a
request and a background job.

`dataset_id`: not part of a `datasets` registry (no such table exists in this
sprint's schema -- see solution-design.md section 4's `datasets` table, which
`validation-service` does not own or query). Passed through explicitly on the
request body; `tenant_id` is no longer a body field (VS-010) -- it is resolved
via `Depends(get_tenant_context)` from `naive_first_common` instead.

VS-012: `DatasetSource.load`, `run_validation_protocol`, and the split-mapping/
`add_splits` persistence that depends on their output are wrapped in a single
`try`/`except Exception`. `run_repository.create_run` happens *before* the
`try` (not after `DatasetSource.load` as VS-006 originally had it) so a
`run.id` always exists to attach a `"failed"` status to, even when the very
first thing inside the `try` (the dataset load) raises. On any exception, the
handler persists `status="failed"` + `failure_reason=str(exc)` via
`update_run_status` and returns immediately from inside the `except` block
with a `201` (the HTTP request was handled correctly -- a run that fails is a
completed *request*, just an unsuccessful *run*; a bare `500` would suggest
the service itself malfunctioned). That `return` is what makes
`event_publisher.publish("run.completed", ...)` structurally unreachable on
failure: it sits after the whole `try`/`except` statement, so the only way
to reach it is for the `try` block to finish without raising -- there is no
`finally`, no fallthrough, nothing that could route a caught exception back
into it.

`GET /runs/{id}` (VS-007): tenant is resolved the same way as `POST /runs`
(VS-010) -- via `Depends(get_tenant_context)`, not a query parameter. Tenant
isolation is load-bearing
(solution-design.md section 1 principle 3): `ValidationRunRepository.get_run`
(VS-004) already returns `None` for both "run doesn't exist" and "run belongs
to a different tenant" -- this handler translates `None` into a single `404`
for both cases, with no branch that would distinguish them (a `403`, or any
differently-shaped response for the cross-tenant case, would itself leak that
the run exists).
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from naive_first_common import TenantContext, get_tenant_context
from naive_first_common.contracts import RunDetailResponse, RunRequest, RunResponse
from naive_first_engine.protocol import (
    NAIVE0_KEY,
    NAIVE_LAST_KEY,
    ValidationConfig,
    run_validation_protocol,
)

from app.dependencies.repositories import (
    DatasetSourceDep,
    EventPublisherDep,
    SplitResultRepositoryDep,
    ValidationRunRepositoryDep,
)
from app.repositories.interfaces import SplitResultRecord

router = APIRouter()


@router.post("/runs", response_model=RunResponse, status_code=201)
def create_run(
    request: RunRequest,
    dataset_source: DatasetSourceDep,
    run_repository: ValidationRunRepositoryDep,
    split_repository: SplitResultRepositoryDep,
    event_publisher: EventPublisherDep,
    tenant: TenantContext = Depends(get_tenant_context),
) -> RunResponse:
    config = ValidationConfig(
        train_window=request.train_window,
        test_window=request.test_window,
        step=request.step,
        purge_gap=request.purge_gap_hours,
        horizon=request.horizon,
    )

    # Created before the try below (VS-012) so a run.id always exists to
    # attach a "failed" status to, even if DatasetSource.load is the very
    # first thing that raises.
    run = run_repository.create_run(
        tenant_id=tenant.tenant_id,
        dataset_id=request.dataset_id,
        horizon=request.horizon,
        purge_gap_hours=request.purge_gap_hours,
        split_config={
            "train_window": request.train_window,
            "test_window": request.test_window,
            "step": request.step,
        },
    )

    try:
        series = dataset_source.load(request.dataset_reference)
        results = run_validation_protocol(series, config)

        split_records = []
        for split in results:
            model = split.baseline_results[NAIVE_LAST_KEY]
            naive0 = split.baseline_results[NAIVE0_KEY]
            dm_result = model.dm_result
            split_records.append(
                SplitResultRecord(
                    id=uuid4().hex,
                    run_id=run.id,
                    tenant_id=tenant.tenant_id,
                    split_index=split.split_index,
                    train_start=split.boundaries.train_start,
                    train_end=split.boundaries.train_end,
                    purge_start=split.boundaries.purge_start,
                    purge_end=split.boundaries.purge_end,
                    test_start=split.boundaries.test_start,
                    test_end=split.boundaries.test_end,
                    model_mae=model.metrics.mae,
                    model_rmse=model.metrics.rmse,
                    model_smape=model.metrics.smape,
                    model_mase=model.metrics.mase,
                    model_da=model.metrics.da,
                    model_f1=model.metrics.f1,
                    model_oos_r2=model.metrics.oos_r2,
                    naive0_mae=naive0.metrics.mae,
                    naive0_rmse=naive0.metrics.rmse,
                    naive0_smape=naive0.metrics.smape,
                    naive0_mase=naive0.metrics.mase,
                    naive0_da=naive0.metrics.da,
                    naive0_f1=naive0.metrics.f1,
                    naive0_oos_r2=naive0.metrics.oos_r2,
                    dm_statistic=dm_result.statistic,
                    dm_pvalue=dm_result.p_value,
                    dm_verdict=dm_result.verdict,
                )
            )

        split_repository.add_splits(tenant.tenant_id, run.id, split_records)
    except Exception as exc:
        run_repository.update_run_status(
            tenant.tenant_id, run.id, status="failed", failure_reason=str(exc)
        )
        # Returning here ends the request. `event_publisher.publish` below
        # is unreachable from this branch by construction -- it sits after
        # this entire try/except statement, with no finally/fallthrough
        # connecting the two.
        return RunResponse(id=run.id, status="failed")

    completed_at = datetime.utcnow()
    run_repository.update_run_status(
        tenant.tenant_id, run.id, status="completed", completed_at=completed_at
    )

    event_publisher.publish(
        "run.completed",
        {
            "run_id": run.id,
            "tenant_id": tenant.tenant_id,
            "status": "completed",
            "completed_at": completed_at.isoformat(),
        },
    )

    return RunResponse(id=run.id, status="completed")


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
def get_run(
    run_id: str,
    run_repository: ValidationRunRepositoryDep,
    tenant: TenantContext = Depends(get_tenant_context),
) -> RunDetailResponse:
    # `get_run` already returns None for both "doesn't exist" and "wrong
    # tenant" (VS-004) -- both collapse into this single 404, no branch
    # distinguishes them (VS-007 Design section, AC2).
    run = run_repository.get_run(tenant.tenant_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    return RunDetailResponse(
        id=run.id,
        tenant_id=run.tenant_id,
        dataset_id=run.dataset_id,
        horizon=run.horizon,
        purge_gap_hours=run.purge_gap_hours,
        split_config=run.split_config,
        status=run.status,
        created_at=run.created_at,
        completed_at=run.completed_at,
        failure_reason=run.failure_reason,
    )
