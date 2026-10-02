"""RPT-004-01: `GET /reports/{report_id}/diff/{other_id}`.

Reports store rendered HTML only, so this is a run-data diff keyed by two
reports: each `validation_audit` report's stored `run_id` is re-fetched from
validation-service and per-split values are compared (`app.diff`). Unknown and
cross-tenant report ids both yield the same 404 as `GET /reports/{id}`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from naive_first_common import TenantContext, get_tenant_context

from app.dependencies.http_client import ValidationServiceClientDep
from app.dependencies.repositories import ReportRepositoryDep
from app.diff import (
    ReportDiffResponse,
    alignment_failure,
    comparability_failure,
    diff_splits,
)
from app.generation import (
    MAX_RENDERED_SPLITS,
    DownstreamResponseError,
    DownstreamTimeoutError,
    DownstreamUnavailableError,
    RunNotFoundError,
    fetch_all_splits,
    fetch_run,
    fetch_split_count,
)

router = APIRouter()

_AUDIT_KIND = "validation_audit"


def _unprocessable(reason: str) -> HTTPException:
    return HTTPException(status_code=422, detail=reason)


@router.get("/{report_id}/diff/{other_id}", response_model=ReportDiffResponse)
def diff_reports(
    report_id: str,
    other_id: str,
    client: ValidationServiceClientDep,
    report_repository: ReportRepositoryDep,
    tenant: TenantContext = Depends(get_tenant_context),
) -> ReportDiffResponse:
    base_report = report_repository.get_report(tenant.tenant_id, report_id)
    other_report = report_repository.get_report(tenant.tenant_id, other_id)
    if base_report is None or other_report is None:
        raise HTTPException(status_code=404, detail="report not found")

    if base_report.report_kind != _AUDIT_KIND or other_report.report_kind != _AUDIT_KIND:
        raise _unprocessable("both reports must be of kind 'validation_audit'")

    try:
        base_run = fetch_run(tenant.tenant_id, base_report.run_id, client)
        other_run = fetch_run(tenant.tenant_id, other_report.run_id, client)

        reason = comparability_failure(base_run, other_run)
        if reason is not None:
            raise _unprocessable(reason)

        for run_id in (base_run.id, other_run.id):
            if fetch_split_count(tenant.tenant_id, run_id, client) > MAX_RENDERED_SPLITS:
                raise _unprocessable("too many splits to diff")

        base_splits = fetch_all_splits(tenant.tenant_id, base_run.id, client)
        other_splits = fetch_all_splits(tenant.tenant_id, other_run.id, client)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    except DownstreamUnavailableError as exc:
        raise HTTPException(status_code=502, detail="downstream service unavailable") from exc
    except DownstreamTimeoutError as exc:
        raise HTTPException(status_code=504, detail="downstream service timed out") from exc
    except DownstreamResponseError as exc:
        raise HTTPException(status_code=502, detail="downstream service error") from exc

    reason = alignment_failure(base_splits, other_splits)
    if reason is not None:
        raise _unprocessable(reason)

    splits = diff_splits(base_splits, other_splits)
    return ReportDiffResponse(
        report_id=base_report.id,
        other_report_id=other_report.id,
        run_id=base_run.id,
        other_run_id=other_run.id,
        dataset_id=base_run.dataset_id,
        horizon=base_run.horizon,
        split_count=len(splits),
        verdict_changed_split_count=sum(1 for s in splits if s.dm_verdict.changed),
        splits=splits,
    )
