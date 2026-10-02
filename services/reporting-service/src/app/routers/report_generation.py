"""RS-004: `POST /reports/generate` -- manual, synchronous report
generation, ahead of RS-006's automatic `run.completed`-triggered path.

Deliberately its own module (not `reports.py`) so RS-005's `GET /reports/
{id}` can land in its own disjoint `report_retrieval.py` with zero file
overlap between the two tickets (ticket Design section), matching
validation-service's VS-007/VS-008 `runs.py`/`splits.py` split precedent.

Single responsibility: resolve tenant, call `app.generation`'s
`generate_validation_audit_report`, and translate its result/exceptions into
this endpoint's HTTP response. No fetch/render/persist logic is duplicated
here -- that all lives in `app.generation` (the module RS-006 will also
import).

Router-level prefix (`/reports`) is applied by `main.py`'s `include_router`
call (RS-005's `report_retrieval` router mounts under the same prefix), so
the route here is declared relative (`/generate`), not `/reports/generate`.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from naive_first_common import TenantContext, get_tenant_context
from pydantic import BaseModel, model_validator

from app.dependencies.http_client import ValidationServiceClientDep
from app.dependencies.repositories import ReportRepositoryDep
from app.generation import (
    DownstreamResponseError,
    DownstreamTimeoutError,
    DownstreamUnavailableError,
    RunNotFoundError,
    generate_consistency_trend_report,
    generate_validation_audit_report,
)

router = APIRouter()


class GenerateReportRequest(BaseModel):
    kind: Literal["validation_audit", "consistency_trend"] = "validation_audit"
    run_id: str | None = None
    dataset_id: str | None = None
    horizon: int | None = None

    @model_validator(mode="after")
    def _check_fields_for_kind(self) -> "GenerateReportRequest":
        if self.kind == "validation_audit":
            if self.run_id is None:
                raise ValueError("run_id is required for kind 'validation_audit'")
            if self.dataset_id is not None or self.horizon is not None:
                raise ValueError("dataset_id/horizon are not allowed for kind 'validation_audit'")
        else:
            if self.dataset_id is None or self.horizon is None:
                raise ValueError("dataset_id and horizon are required for kind 'consistency_trend'")
            if self.run_id is not None:
                raise ValueError("run_id is not allowed for kind 'consistency_trend'")
        return self


class GenerateReportResponse(BaseModel):
    id: str
    status: str


@router.post("/generate", response_model=GenerateReportResponse, status_code=201)
def generate_report(
    request: GenerateReportRequest,
    client: ValidationServiceClientDep,
    repository: ReportRepositoryDep,
    tenant: TenantContext = Depends(get_tenant_context),
) -> GenerateReportResponse:
    try:
        if request.kind == "consistency_trend":
            record = generate_consistency_trend_report(
                tenant_id=tenant.tenant_id,
                dataset_id=request.dataset_id,
                horizon=request.horizon,
                client=client,
                repository=repository,
            )
        else:
            record = generate_validation_audit_report(
                tenant_id=tenant.tenant_id,
                run_id=request.run_id,
                client=client,
                repository=repository,
            )
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    except DownstreamUnavailableError as exc:
        raise HTTPException(status_code=502, detail="downstream service unavailable") from exc
    except DownstreamTimeoutError as exc:
        raise HTTPException(status_code=504, detail="downstream service timed out") from exc
    except DownstreamResponseError as exc:
        raise HTTPException(status_code=502, detail="downstream service error") from exc

    return GenerateReportResponse(id=record.id, status=record.status)
