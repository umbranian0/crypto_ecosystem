"""`GET /reports/{id}` (RS-005): retrieve a previously generated report.

Deliberately its own module, disjoint from RS-004's `report_generation.py`,
so both tickets run fully in parallel with zero file overlap (mirrors
validation-service's VS-007/VS-008 `runs.py`/`splits.py` split).

Tenant isolation is load-bearing (solution-design.md section 1 principle 3):
`ReportRepository.get_report` (RS-002) already returns `None` for both
"report doesn't exist" and "report belongs to a different tenant" -- this
handler translates `None` into a single `404` for both cases, with no branch
that would distinguish them (a `403`, or any differently-shaped response for
the cross-tenant case, would itself leak that the report exists), matching
`validation-service`'s `GET /runs/{id}` (VS-007) non-disclosure stance one
layer over.

Router-level prefix (`/reports`) is applied by `main.py`'s `include_router`
call (RS-004's `report_generation` router mounts under the same prefix), so
routes here are declared relative (`/{report_id}`), not `/reports/{...}`.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from naive_first_common import TenantContext, get_tenant_context

from app.dependencies.repositories import ReportRepositoryDep

router = APIRouter()


class ReportDetailResponse(BaseModel):
    id: str
    run_id: str
    report_kind: str
    generated_at: datetime
    status: str
    content: str


@router.get("/{report_id}", response_model=ReportDetailResponse)
def get_report(
    report_id: str,
    report_repository: ReportRepositoryDep,
    tenant: TenantContext = Depends(get_tenant_context),
) -> ReportDetailResponse:
    # `get_report` already returns None for both "doesn't exist" and "wrong
    # tenant" (RS-002) -- both collapse into this single 404, no branch
    # distinguishes them (RS-005 Design section).
    report = report_repository.get_report(tenant.tenant_id, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")

    return ReportDetailResponse(
        id=report.id,
        run_id=report.run_id,
        report_kind=report.report_kind,
        generated_at=report.generated_at,
        status=report.status,
        content=report.content,
    )
