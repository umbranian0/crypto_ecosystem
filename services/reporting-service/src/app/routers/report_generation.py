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

from fastapi import APIRouter, Depends, HTTPException
from naive_first_common import TenantContext, get_tenant_context
from pydantic import BaseModel

from app.dependencies.http_client import ValidationServiceClientDep
from app.dependencies.repositories import ReportRepositoryDep
from app.generation import (
    DownstreamResponseError,
    DownstreamTimeoutError,
    DownstreamUnavailableError,
    RunNotFoundError,
    generate_validation_audit_report,
)

router = APIRouter()


class GenerateReportRequest(BaseModel):
    run_id: str


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
